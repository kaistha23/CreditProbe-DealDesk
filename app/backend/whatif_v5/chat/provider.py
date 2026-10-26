"""The model behind the What-If assistant (forked from the Cockpit's provider, re-keyed).

The Cockpit's key and model are used: `COCKPIT_ANTHROPIC_API_KEY` (or
`WHATIF_ANTHROPIC_API_KEY`), model `WHATIF_MODEL` or `AI_COCKPIT_REASONING_MODEL`.
Every call is one forced tool call with a bounded output and timeout, and its
result is validated before anything uses it. Every call is logged (timing and
token counts, never the key) to var/whatif/llm_calls.jsonl.

With no key, `available()` is False and the assistant answers with its
deterministic planner: the same tools, the same validation, recorded
behaviour (this is what the automated sweep exercises).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from backend.whatif_v5 import paths

LOG = paths.V5 / "var" / "whatif" / "llm_calls.jsonl"
TIMEOUT_S = 30.0
MAX_TOKENS = 1200
_LOCK = threading.Lock()
_CLIENT: Any = None


def _key() -> str:
    for var in ("WHATIF_ANTHROPIC_API_KEY", "COCKPIT_ANTHROPIC_API_KEY"):
        v = (os.environ.get(var) or "").strip()
        if re.match(r"^sk-ant-\S+$", v):
            return v
    return ""


def model_id() -> str:
    return (os.environ.get("WHATIF_MODEL") or os.environ.get("AI_COCKPIT_REASONING_MODEL") or "claude-opus-5").strip()


def available() -> bool:
    return bool(_key()) and os.environ.get("WHATIF_ASSISTANT_MODEL", "on") != "off"


def describe() -> dict[str, Any]:
    return {"model_available": available(), "model": model_id() if available() else None,
            "planner": "model + deterministic validation" if available() else "deterministic"}


def _client():
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            import anthropic
            _CLIENT = anthropic.Anthropic(api_key=_key(), timeout=TIMEOUT_S, max_retries=0)
        return _CLIENT


def _log(row: dict[str, Any]) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def structured(purpose: str, system: str, user: str, tool: dict[str, Any]) -> dict[str, Any] | None:
    """One forced tool call. Returns the tool input, or None (unavailable, timed out or refused)."""
    if not available():
        return None
    t0 = time.monotonic()
    row: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "purpose": purpose, "model": model_id()}
    try:
        msg = _client().messages.create(
            model=model_id(), max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": user}], tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]})
        row.update({"ms": int((time.monotonic() - t0) * 1000), "stop": msg.stop_reason,
                    "input_tokens": getattr(msg.usage, "input_tokens", None),
                    "output_tokens": getattr(msg.usage, "output_tokens", None)})
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use" and block.name == tool["name"]:
                row["ok"] = True
                _log(row)
                return dict(block.input)
        row["ok"] = False
    except Exception as e:  # noqa: BLE001 - any provider failure falls back to the deterministic path
        row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": type(e).__name__})
    _log(row)
    return None
