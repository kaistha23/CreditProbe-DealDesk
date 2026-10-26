"""Round A: the agent's model calls, all through backend/convo/provider.py and measured (backend/convo/telemetry.py).

    available()                                   {model_available, provider, model}  (provider.describe())
    tool_call(log, purpose, system, content, tool)   one schema-constrained call (the document reader); returns the tool input
    stream_text(log, purpose, prompt, on_text, history)   the drafting call, streamed: on_text(text_so_far) as it writes

`log` is the run's list of calls (purpose, model, ms, tokens, ok): the run shows them, and the same calls are in the
telemetry store tagged with the run id (`telemetry.use(module="dealdesk_agent_intake", run_id=...)`, set by the caller in
each thread). With no model key `provider.default()` is None and the callers use the rule reader and the deterministic draft.

Streaming: the Anthropic provider's client streams text (messages.stream); the row is written in the provider's own telemetry
shape (with time to first token). Any other provider (an OpenAI-compatible server, the tests' Scripted provider) is called
through `step()` with a `write_markdown` tool and the text arrives in one piece.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

MODULE = "dealdesk_agent_intake"
_LOCK = threading.Lock()
WRITE = {"name": "write_markdown", "description": "Return the business request as markdown.",
         "input_schema": {"type": "object", "properties": {"markdown": {"type": "string"}}, "required": ["markdown"]}}
SYSTEM_DRAFT = "You write bank credit documents for a corporate relationship manager. Follow the user's structure and rules exactly."
MAX_TOKENS = 4000


class NoModel(RuntimeError):
    pass


def provider():
    try:
        from backend.convo import provider as prov
        return prov.default()
    except Exception:  # noqa: BLE001
        return None


def available() -> dict[str, Any]:
    try:
        from backend.convo import provider as prov
        d = prov.describe()
    except Exception:  # noqa: BLE001
        d = {"model_available": False, "model": None, "provider": None}
    return {"model_available": bool(d.get("model_available")), "provider": d.get("provider"), "model": d.get("model")}


def _note(log: list[dict[str, Any]], row: dict[str, Any]) -> None:
    with _LOCK:
        log.append(row)


def tool_call(log: list[dict[str, Any]], purpose: str, system: str, content: list[dict[str, Any]], tool: dict[str, Any],
              doc_id: str = "") -> dict[str, Any]:
    p = provider()
    if p is None:
        raise NoModel("no model key")
    t0 = time.monotonic()
    row: dict[str, Any] = {"purpose": purpose, "doc": doc_id, "provider": getattr(p, "name", ""), "model": p.model(), "ok": False}
    try:
        reply = p.step(purpose, system, [{"role": "user", "content": content}], [tool])
        use = next((u for u in reply.tool_uses() if u.get("name") == tool["name"]), None)
        row.update(ok=use is not None, input_tokens=(reply.usage or {}).get("input_tokens"), output_tokens=(reply.usage or {}).get("output_tokens"))
        if use is None:
            raise ValueError("the model gave no answer in the schema")
        return dict(use.get("input") or {})
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        raise
    finally:
        row["ms"] = int((time.monotonic() - t0) * 1000)
        _note(log, row)


def stream_text(log: list[dict[str, Any]], purpose: str, prompt: str, on_text: Callable[[str], None],
                history: list[dict[str, Any]] | None = None) -> str:
    """The drafting call. `history` (revise): earlier turns before the prompt."""
    p = provider()
    if p is None:
        raise NoModel("no model key")
    from backend.convo import provider as prov
    from backend.convo import telemetry
    messages = list(history or []) + [{"role": "user", "content": prompt}]
    t0 = time.monotonic()
    row: dict[str, Any] = {"purpose": purpose, "provider": getattr(p, "name", ""), "model": p.model(), "ok": False, "streamed": False}
    try:
        if isinstance(p, prov.Anthropic):
            trow: dict[str, Any] = {"purpose": purpose, "provider": p.name, "model": p.model(),
                                    "prompt_version": telemetry.prompt_version(SYSTEM_DRAFT, []), "n_messages": len(messages),
                                    "n_tools_offered": 0, "max_tokens": MAX_TOKENS}
            acc, ttft = "", None
            try:
                with p._client().messages.stream(model=p.model(), max_tokens=MAX_TOKENS, system=SYSTEM_DRAFT, messages=messages) as s:  # noqa: SLF001
                    for chunk in s.text_stream:
                        if ttft is None:
                            ttft = int((time.monotonic() - t0) * 1000)
                        acc += chunk
                        on_text(acc)
                    msg = s.get_final_message()
            except Exception as e:  # noqa: BLE001
                trow.update({"ms": int((time.monotonic() - t0) * 1000), "ok": False, "error": type(e).__name__})
                telemetry.record(trow)
                raise
            usage = {"input_tokens": getattr(msg.usage, "input_tokens", None), "output_tokens": getattr(msg.usage, "output_tokens", None)}
            trow.update({"ms": int((time.monotonic() - t0) * 1000), "ttft_ms": ttft, "ok": True, "stop": msg.stop_reason, **usage,
                         "served_model": getattr(msg, "model", "") or ""})
            telemetry.record(trow)
            row.update(ok=True, streamed=True, ttft_ms=ttft, stop=msg.stop_reason, **usage)
            return acc
        reply = p.step(purpose, SYSTEM_DRAFT, messages, [WRITE])
        use = next((u for u in reply.tool_uses() if u.get("name") == WRITE["name"]), None)
        text = str((use or {}).get("input", {}).get("markdown") or reply.text() or "")
        if not text.strip():
            raise ValueError("the model wrote nothing")
        on_text(text)
        row.update(ok=True, input_tokens=(reply.usage or {}).get("input_tokens"), output_tokens=(reply.usage or {}).get("output_tokens"))
        return text
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        raise
    finally:
        row["ms"] = int((time.monotonic() - t0) * 1000)
        _note(log, row)
