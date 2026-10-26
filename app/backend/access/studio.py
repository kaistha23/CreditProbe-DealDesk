"""The live AI Studio configuration of a module, as the conversational layer reads it (PLAN_R5 A3/A4).

`killed(domain_key)`: Agent Operations' kill switch is on for the module (the assistant falls back to planner mode).
`config(module)`: the live studio configuration (model, instructions, glossary, guardrails, answer style).
Read-only from the Admin store, cached a few seconds.
"""
from __future__ import annotations

import time
from typing import Any

from backend.access import policy as pol

#: Conversational domain key -> Admin module key.
DOMAIN_MODULE = {"whatif": "what_if", "scorecard": "scorecard", "dealdesk": "deal_desk", "playbook": "playbook",
                 "lenses": "lenses", "admin": "admin", "cockpit": "cockpit"}
_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}


def module_of(domain_key: str) -> str:
    k = str(domain_key or "")
    if k in DOMAIN_MODULE:
        return DOMAIN_MODULE[k]
    if k.startswith("project") or k.startswith("ai_work") or k.startswith("pj"):
        return "projects"
    return k


def _all() -> dict[str, dict[str, Any]]:
    hit = _CACHE.get("all")
    if hit and time.monotonic() - hit[0] < pol.TTL:
        return hit[1]
    out = {c.get("module", c.get("id", "")): c for c in pol._live("studio")}  # noqa: SLF001
    _CACHE["all"] = (time.monotonic(), out)
    return out


def config(module: str) -> dict[str, Any]:
    return _all().get(module, {})


def killed(domain_key: str) -> bool:
    return bool(config(module_of(domain_key)).get("kill_switch"))


def clear_cache() -> None:
    _CACHE.clear()


def model(domain_key: str) -> str:
    return str(config(module_of(domain_key)).get("model") or "")


def addendum(domain_key: str) -> str:
    """The bank's AI Studio configuration for the module, appended to the system prompt: instructions, house tone,
    glossary and answer style (the Cockpit's own prompt is frozen and never reads this)."""
    c = config(module_of(domain_key))
    if not c or c.get("read_only"):
        return ""
    parts = []
    if c.get("instructions"):
        parts.append(str(c["instructions"]))
    if c.get("tone"):
        parts.append(f"House tone: {c['tone']}")
    if c.get("glossary"):
        parts.append("Bank glossary: " + "; ".join(f"{g['term']} = {g['meaning']}" for g in c["glossary"]))
    st = c.get("answer_style") or {}
    if st:
        parts.append(f"Answer length: {st.get('length', 'medium')}"
                     + ("; no tables" if st.get("tables") is False else "") + ("; no charts" if st.get("charts") is False else ""))
    return ("\n\nBank configuration (AI Studio):\n" + "\n".join(parts)) if parts else ""


def disabled_tools(domain_key: str) -> set[str]:
    """Tools the bank switched off in AI Studio: known to the configuration but no longer in its allowed list. A tool
    a module adds later is not known yet, so it stays on until someone switches it off."""
    c = config(module_of(domain_key))
    return set(c.get("known_tools") or []) - set(c.get("tools") or [])
