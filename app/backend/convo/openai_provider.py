"""An OpenAI-compatible model behind the same `Provider.step()` the domains call (Deal Desk edition, model lab).

vLLM, llama.cpp (`llama-server`), LM Studio, MLX (`mlx_lm.server`) and Ollama all speak the OpenAI chat-completions
dialect with function calling, so one provider covers the RunPod lab (vLLM on an NVIDIA GPU) and the bank's Mac box
(llama.cpp or MLX on Apple silicon). The domains keep sending Anthropic-shaped messages (content blocks: `text`,
`tool_use`, `tool_result`, `image`) and Anthropic-shaped tools (`input_schema`); this module translates both ways, so
nothing in backend/dealdesk, backend/convo/agent.py or any domain changes when the model does.

Environment (all read at call time; nothing is cached across calls except the HTTP client):

  CONVO_PROVIDER            anthropic | openai | auto (default auto: openai when CONVO_OPENAI_BASE_URL is set)
  CONVO_OPENAI_BASE_URL     e.g. http://127.0.0.1:8000/v1 (vLLM), http://127.0.0.1:8080/v1 (llama.cpp)
  CONVO_OPENAI_API_KEY      optional; local servers ignore it ("none" is sent when unset)
  CONVO_OPENAI_MODEL        the served model id, e.g. Qwen/Qwen3.8-27B (CONVO_MODEL is honoured when this is unset)
  CONVO_OPENAI_QUANT        a label for the telemetry only (fp8, q8_0, q4_k_m, mxfp4 ...)
  CONVO_OPENAI_TOOL_CHOICE  required (default: every step is a tool call, as the Anthropic path does) | auto
  CONVO_OPENAI_THINKING     off (default) | on -- Qwen3 "thinking" through chat_template_kwargs.enable_thinking
  CONVO_OPENAI_TIMEOUT_S    default 600 (a 27B model writing a full proposal can take minutes on a Mac)
  CONVO_MAX_TOKENS          default 4000 (the Anthropic path's MAX_TOKENS)
  CONVO_OPENAI_EXTRA_BODY   JSON merged into every request body (e.g. {"temperature": 0})

Every call writes one telemetry row (backend/convo/telemetry.py): tokens in, out, reasoning and cached as the server
reports them, wall time, time to first token when streaming is on (CONVO_OPENAI_STREAM=on), and the usual context.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from backend.convo import telemetry
from backend.convo.provider import Provider, ProviderFailure, Reply

_LOCK = threading.Lock()
_CLIENT: Any = None


def enabled() -> bool:
    choice = (os.environ.get("CONVO_PROVIDER") or "auto").strip().lower()
    if choice == "openai":
        return True
    if choice == "anthropic":
        return False
    return bool((os.environ.get("CONVO_OPENAI_BASE_URL") or "").strip())


def base_url() -> str:
    return (os.environ.get("CONVO_OPENAI_BASE_URL") or "http://127.0.0.1:8000/v1").strip().rstrip("/")


_DISCOVERED: dict[str, str] = {}


def model_id(url: str | None = None) -> str:
    """CONVO_OPENAI_MODEL; else the one model the server serves (GET /models, remembered per URL), so a pod that
    serves a single model needs no model name in its environment. CONVO_MODEL is used only when it is not an
    Anthropic model id (ops/v5.sh exports claude-opus-5 as the Anthropic default)."""
    m = (os.environ.get("CONVO_OPENAI_MODEL") or "").strip()
    if m:
        return m
    cm = (os.environ.get("CONVO_MODEL") or "").strip()
    if cm and not cm.startswith("claude"):
        return cm
    u = (url or base_url()).rstrip("/")
    if u not in _DISCOVERED:
        h = health(u)
        if h.get("models"):
            _DISCOVERED[u] = str(h["models"][0])
    return _DISCOVERED.get(u, "")


def _max_tokens() -> int:
    try:
        return int(os.environ.get("CONVO_MAX_TOKENS") or 4000)
    except ValueError:
        return 4000


def _timeout() -> float:
    try:
        return float(os.environ.get("CONVO_OPENAI_TIMEOUT_S") or 600)
    except ValueError:
        return 600.0


# ------------------------------------------------------------------ translation: Anthropic -> OpenAI

def _image_url(src: dict[str, Any]) -> str:
    if src.get("type") == "base64":
        return f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"
    return str(src.get("url") or "")


def _content_to_openai(content: Any) -> str | list[dict[str, Any]]:
    """A message's content (a string or Anthropic blocks) as OpenAI content; tool_use/tool_result handled by caller."""
    if isinstance(content, str):
        return content
    parts: list[dict[str, Any]] = []
    for b in content or []:
        t = b.get("type")
        if t == "text":
            parts.append({"type": "text", "text": b.get("text", "")})
        elif t == "image":
            parts.append({"type": "image_url", "image_url": {"url": _image_url(b.get("source") or {})}})
        elif t == "document":
            # An Anthropic document block (a PDF) has no OpenAI equivalent on a local server: the domains extract
            # text before the model sees a file, so this is a last resort and is said plainly to the model.
            parts.append({"type": "text", "text": "[A document was attached that this model cannot read directly.]"})
    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"]
    return parts


def _tool_result_text(block: dict[str, Any]) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return json.dumps(c, default=str) if c is not None else ""


def to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role == "assistant" and isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            calls = [{"id": b.get("id") or f"call_{i}", "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {}, default=str)}}
                     for i, b in enumerate(content) if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        elif role == "user" and isinstance(content, list) and any(b.get("type") == "tool_result" for b in content):
            rest = [b for b in content if b.get("type") != "tool_result"]
            for b in content:
                if b.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b.get("tool_use_id") or "", "content": _tool_result_text(b)})
            if rest:
                out.append({"role": "user", "content": _content_to_openai(rest)})
        else:
            out.append({"role": role or "user", "content": _content_to_openai(content)})
    return out


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}}}}
            for t in tools or []]


# ------------------------------------------------------------------ translation: OpenAI -> Anthropic

_JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    s = (raw or "").strip() if isinstance(raw, str) else ""
    if not s:
        return {}
    m = _JSON_FENCE.match(s)
    if m:
        s = m.group(1)
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {"value": v}
    except ValueError:
        # a trailing comma or a stray closing brace is the usual damage from a small model; one repair attempt
        s2 = re.sub(r",\s*([}\]])", r"\1", s)
        try:
            v = json.loads(s2)
            return v if isinstance(v, dict) else {"value": v}
        except ValueError as e:
            raise ProviderFailure(f"tool call arguments are not JSON: {str(e)[:80]}") from e


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text or "", flags=re.S).strip()


def from_openai_message(msg: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    content: list[dict[str, Any]] = []
    text = _strip_think(msg.get("content") or "") if isinstance(msg.get("content"), str) else ""
    if text:
        content.append({"type": "text", "text": text})
    for i, c in enumerate(msg.get("tool_calls") or []):
        fn = c.get("function") or {}
        content.append({"type": "tool_use", "id": c.get("id") or f"call_{i}", "name": fn.get("name", ""),
                        "input": _arguments(fn.get("arguments"))})
    return content, ("tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn")


_STOP = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens", "content_filter": "end_turn"}


# ------------------------------------------------------------------ the provider

class OpenAICompatible(Provider):
    name = "openai"
    model_override: str = ""   # AI Studio's per-module model, as on the Anthropic provider

    def __init__(self, url: str | None = None, model: str | None = None):
        self.url = (url or base_url()).rstrip("/")
        self._model = model or ""

    def model(self) -> str:
        return self.model_override or self._model or model_id(self.url)

    def _client(self):
        global _CLIENT
        with _LOCK:
            if _CLIENT is None:
                import httpx
                _CLIENT = httpx.Client(timeout=httpx.Timeout(_timeout(), connect=20.0))
            return _CLIENT

    def _body(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        from backend.convo.efficiency import plain   # Round E: the cache break is Anthropic's; one system string here
        body: dict[str, Any] = {"model": self.model(), "messages": to_openai_messages(plain(system), messages),
                                "max_tokens": _max_tokens(), "temperature": 0}
        if tools:
            body["tools"] = to_openai_tools(tools)
            choice = (os.environ.get("CONVO_OPENAI_TOOL_CHOICE") or "required").strip().lower()
            if choice == "required" and len(tools) == 1:
                body["tool_choice"] = {"type": "function", "function": {"name": tools[0]["name"]}}
            else:
                body["tool_choice"] = "required" if choice == "required" else "auto"
        thinking = (os.environ.get("CONVO_OPENAI_THINKING") or "off").strip().lower() == "on"
        body["chat_template_kwargs"] = {"enable_thinking": thinking}
        extra = (os.environ.get("CONVO_OPENAI_EXTRA_BODY") or "").strip()
        if extra:
            try:
                body.update(json.loads(extra))
            except ValueError:
                pass
        if (os.environ.get("CONVO_OPENAI_STREAM") or "off").strip().lower() == "on":
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        return body

    def step(self, purpose: str, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        t0 = time.monotonic()
        body = self._body(system, messages, tools)
        row: dict[str, Any] = {"purpose": purpose, "provider": self.name, "model": self.model(),
                               "quant": os.environ.get("CONVO_OPENAI_QUANT") or "",
                               "prompt_version": telemetry.prompt_version(system, tools),
                               "n_messages": len(messages), "n_tools_offered": len(tools or []),
                               "max_tokens": body["max_tokens"]}
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + (os.environ.get("CONVO_OPENAI_API_KEY") or "none")}
        try:
            if body.get("stream"):
                msg, usage, served, ttft = self._stream(body, headers)
                row["ttft_ms"] = ttft
            else:
                r = self._client().post(self.url + "/chat/completions", json=body, headers=headers)
                if r.status_code >= 400:
                    raise ProviderFailure(f"HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                msg["_finish"] = choice.get("finish_reason") or ""
                usage = data.get("usage") or {}
                served = data.get("model") or ""
        except ProviderFailure as e:
            row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": str(e)[:200]})
            telemetry.record(row)
            raise
        except Exception as e:  # noqa: BLE001 - surfaced to the loop as a provider failure, never swallowed
            row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": type(e).__name__})
            telemetry.record(row)
            raise ProviderFailure(f"{type(e).__name__}: {str(e)[:200]}") from e
        try:
            content, _ = from_openai_message(msg)
        except ProviderFailure as e:
            row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": str(e)[:200]})
            telemetry.record(row)
            raise
        stop = _STOP.get(msg.get("_finish") or "", "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn")
        details = usage.get("completion_tokens_details") or {}
        pdetails = usage.get("prompt_tokens_details") or {}
        use = {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
               "reasoning_tokens": details.get("reasoning_tokens"), "cached_tokens": pdetails.get("cached_tokens")}
        row.update({"ms": int((time.monotonic() - t0) * 1000), "ok": True, "stop": stop, "served_model": served, **use,
                    "tools": [c["name"] for c in content if c["type"] == "tool_use"]})
        telemetry.record(row)
        return Reply(content=content, stop_reason=stop, usage={k: v for k, v in use.items() if v is not None})

    def _stream(self, body: dict[str, Any], headers: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any], str, int | None]:
        """Consume an SSE stream; returns the assembled message, usage, served model and time to first token (ms)."""
        t0 = time.monotonic()
        ttft: int | None = None
        text_parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        served, finish = "", ""
        with self._client().stream("POST", self.url + "/chat/completions", json=body, headers=headers) as r:
            if r.status_code >= 400:
                raise ProviderFailure(f"HTTP {r.status_code}: {r.read()[:200]!r}")
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                served = ev.get("model") or served
                if ev.get("usage"):
                    usage = ev["usage"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    if d.get("content"):
                        if ttft is None:
                            ttft = int((time.monotonic() - t0) * 1000)
                        text_parts.append(d["content"])
                    for tc in d.get("tool_calls") or []:
                        if ttft is None:
                            ttft = int((time.monotonic() - t0) * 1000)
                        i = tc.get("index", 0)
                        slot = calls.setdefault(i, {"id": "", "function": {"name": "", "arguments": ""}})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["function"]["name"] = fn.get("name") or slot["function"]["name"]
                        slot["function"]["arguments"] += fn.get("arguments") or ""
                    finish = ch.get("finish_reason") or finish
        msg = {"role": "assistant", "content": "".join(text_parts), "_finish": finish,
               "tool_calls": [{"id": v["id"] or f"call_{i}", "type": "function", "function": v["function"]} for i, v in sorted(calls.items())]}
        return msg, usage, served, ttft


def health(url: str | None = None) -> dict[str, Any]:
    """Is the server up and which models does it serve (GET /models)?"""
    import httpx
    u = (url or base_url()).rstrip("/")
    try:
        r = httpx.get(u + "/models", timeout=10.0,
                      headers={"Authorization": "Bearer " + (os.environ.get("CONVO_OPENAI_API_KEY") or "none")})
        models = [m.get("id") for m in (r.json().get("data") or [])] if r.status_code < 400 else []
        return {"ok": r.status_code < 400, "url": u, "models": models, "status": r.status_code}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "url": u, "models": [], "error": type(e).__name__}
