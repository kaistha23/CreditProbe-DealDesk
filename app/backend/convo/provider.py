"""The model behind every domain conversation (forked from the Cockpit's provider).

The Cockpit's key and model: `COCKPIT_ANTHROPIC_API_KEY` (or `CONVO_ANTHROPIC_API_KEY`),
model `CONVO_MODEL`, else `AI_COCKPIT_REASONING_MODEL` (the Cockpit's own). One
call is one step of the analyst loop: the model sees the domain's tools and either
calls some of them or finalizes. Every call is logged (timing, token counts, never
the key) through backend/convo/telemetry.py to var/convo/llm_calls.jsonl and llm_telemetry.sqlite.

Deal Desk edition: the same `step()` is also served by an OpenAI-compatible model
(backend/convo/openai_provider.py: vLLM on RunPod, llama.cpp or MLX on the Mac) when
`CONVO_PROVIDER=openai` or `CONVO_OPENAI_BASE_URL` is set; `default()` chooses.

With no key, `default()` is None and the agent runs the domain's deterministic
planner through the same tools and the same validation (what the sweep runs).
Tests install a `Scripted` provider to exercise the model path without a network.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.convo.store import V5

LOG = V5 / "var" / "convo" / "llm_calls.jsonl"
TIMEOUT_S = 90.0
MAX_TOKENS = 4000
_LOCK = threading.Lock()
_CLIENT: Any = None
_OVERRIDE: "Provider | None" = None


@dataclass
class Reply:
    content: list[dict[str, Any]]
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    def text(self) -> str:
        return "\n".join(b.get("text", "") for b in self.content if b.get("type") == "text").strip()


class ProviderFailure(RuntimeError):
    pass


class Provider:
    name = "provider"

    def model(self) -> str:
        return ""

    def step(self, purpose: str, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        raise NotImplementedError


def _key() -> str:
    for var in ("CONVO_ANTHROPIC_API_KEY", "COCKPIT_ANTHROPIC_API_KEY", "WHATIF_ANTHROPIC_API_KEY"):
        v = (os.environ.get(var) or "").strip()
        if re.match(r"^sk-ant-\S+$", v):
            return v
    return ""


def model_id() -> str:
    return (os.environ.get("CONVO_MODEL") or os.environ.get("AI_COCKPIT_REASONING_MODEL") or "claude-opus-5").strip()


def _log(row: dict[str, Any]) -> None:
    """One telemetry row per call (backend/convo/telemetry.py: llm_calls.jsonl + the sqlite the model lab reads)."""
    from backend.convo import telemetry
    telemetry.record(row)


class Anthropic(Provider):
    name = "anthropic"

    model_override: str = ""   # AI Studio's per-module model (PLAN_R5 A4); empty = the environment's model

    def model(self) -> str:
        return self.model_override or model_id()

    def _client(self):
        global _CLIENT
        with _LOCK:
            if _CLIENT is None:
                import anthropic
                _CLIENT = anthropic.Anthropic(api_key=_key(), timeout=TIMEOUT_S, max_retries=1)
            return _CLIENT

    def step(self, purpose: str, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        t0 = time.monotonic()
        from backend.convo import telemetry
        row: dict[str, Any] = {"purpose": purpose, "provider": self.name, "model": self.model(),
                               "prompt_version": telemetry.prompt_version(system, tools),
                               "n_messages": len(messages), "n_tools_offered": len(tools or []), "max_tokens": MAX_TOKENS}
        try:
            from backend.convo import efficiency   # Round E: cache the stable prompt head and the tool schemas
            req = efficiency.anthropic_request(system, tools, messages, purpose)
            msg = self._client().messages.create(model=self.model(), max_tokens=MAX_TOKENS, **req,
                                                 # every step is a tool call: an answer is published only
                                                 # through finalize_answer, where its figures are checked
                                                 tool_choice={"type": "any"})
        except Exception as e:  # noqa: BLE001 - surfaced to the loop as a provider failure, never swallowed
            row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": type(e).__name__})
            _log(row)
            raise ProviderFailure(f"{type(e).__name__}: {str(e)[:200]}") from e
        content: list[dict[str, Any]] = []
        for b in msg.content:
            t = getattr(b, "type", "")
            if t == "text":
                content.append({"type": "text", "text": b.text})
            elif t == "tool_use":
                content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input or {})})
        usage = {"input_tokens": getattr(msg.usage, "input_tokens", None),
                 "output_tokens": getattr(msg.usage, "output_tokens", None)}
        cached = (getattr(msg.usage, "cache_read_input_tokens", None) or 0) + (getattr(msg.usage, "cache_creation_input_tokens", None) or 0)
        row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": True, "stop": msg.stop_reason, **usage,
                    "cached_tokens": cached or None, **efficiency.usage_row(msg.usage), "served_model": getattr(msg, "model", "") or "",
                    "tools": [c["name"] for c in content if c["type"] == "tool_use"]})
        _log(row)
        return Reply(content=content, stop_reason=msg.stop_reason or "", usage=usage)


class Scripted(Provider):
    """Replays a fixed list of replies (tests, recorded runs). Each reply is a list of content
    blocks; `{"type": "tool_use", "name": ..., "input": ...}` ids are filled in."""
    name = "scripted"

    def __init__(self, replies: list[list[dict[str, Any]]]):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def model(self) -> str:
        return "scripted"

    def step(self, purpose: str, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        from backend.convo.efficiency import plain
        self.calls.append({"purpose": purpose, "system": plain(system), "messages": json.loads(json.dumps(messages, default=str)),
                           "tools": [t["name"] for t in tools]})
        if not self.replies:
            raise ProviderFailure("The script has no more replies.")
        blocks = []
        for i, b in enumerate(self.replies.pop(0)):
            b = dict(b)
            if b.get("type") == "tool_use":
                b.setdefault("id", f"tu_{len(self.calls)}_{i}")
            blocks.append(b)
        return Reply(content=blocks, stop_reason="tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn")


def set_override(p: Provider | None) -> None:
    """Install a provider for every domain (tests); None restores the environment's choice."""
    global _OVERRIDE
    _OVERRIDE = p


def default() -> Provider | None:
    """The model every domain talks to: the override (tests), else the OpenAI-compatible server when the gateway
    points at one (CONVO_PROVIDER=openai, or CONVO_OPENAI_BASE_URL set: vLLM on RunPod, llama.cpp/MLX on the Mac),
    else Anthropic when a key is present, else None (the deterministic planner)."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    if os.environ.get("CONVO_ASSISTANT_MODEL", "on") == "off":
        return None
    from backend.convo import openai_provider
    if openai_provider.enabled():
        return openai_provider.OpenAICompatible()
    if _key():
        return Anthropic()
    return None


def describe() -> dict[str, Any]:
    p = default()
    out = {"model_available": p is not None, "model": p.model() if p else None,
           "planner": "model" if p else "deterministic", "provider": p.name if p else None}
    if p is not None and p.name == "openai":
        out["base_url"] = getattr(p, "url", "")
        out["quant"] = os.environ.get("CONVO_OPENAI_QUANT") or ""
    out["experiment"] = os.environ.get("CONVO_EXPERIMENT") or ""
    return out
