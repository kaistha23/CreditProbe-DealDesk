"""Optional model polish (N6): when a model key is present, the model may tighten a section's prose in the house voice. The
polished text is accepted only if it keeps every figure of the deterministic text (no figure added or dropped) and passes the voice
rules; otherwise the deterministic text stands. Without a key (the cloud, the tests) this is a no-op.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.dealdesk.house_style.bankform import voice

FIG = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
TOOL = {"name": "polish", "description": "Return the same lines, tightened in the house voice.",
        "input_schema": {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}}, "required": ["lines"]}}
SYSTEM = ("You polish lines of a bank credit proposal. Keep every figure, date, name and attribution exactly; do not add any figure, "
          "adjective or conclusion; keep one fact per sentence; terse, formal banker English; prior-year figures stay in brackets.")


def _figs(t: str) -> list[str]:
    return sorted(x.replace(",", "") for x in FIG.findall(t))


def _provider():
    try:
        from backend.convo import provider as prov
        return prov.default()
    except Exception:  # noqa: BLE001
        return None


def section(s: dict[str, Any]) -> dict[str, Any]:
    if s.get("voice") == "form":
        return s
    p = _provider()
    if p is None:
        return s
    lines = [(i, j, b["text"] if b["t"] == "p" else b["items"][j]) for i, b in enumerate(s["blocks"]) if b["t"] in ("p", "bullets", "numbered")
             for j in (range(len(b["items"])) if b["t"] != "p" else [0])]
    if not lines:
        return s
    try:
        reply = p.step("dealdesk_bankform_polish", SYSTEM, [{"role": "user", "content": json.dumps({"voice": s["voice"], "lines": [x[2] for x in lines]})}], [TOOL])
        use = next((u for u in reply.tool_uses() if u.get("name") == "polish"), None)
        new = [str(x) for x in (use or {}).get("input", {}).get("lines", [])]
    except Exception:  # noqa: BLE001 - provider failure: the deterministic text stands
        return s
    if len(new) != len(lines):
        return s
    out = {**s, "blocks": [dict(b, items=list(b["items"])) if b["t"] in ("bullets", "numbered") else dict(b) for b in s["blocks"]]}
    changed = 0
    for (i, j, old), nt in zip(lines, new):
        if _figs(old) != _figs(nt) or any(voice.sentence_problems(x, s["voice"]) for x in voice.sentences(nt)):
            continue
        b = out["blocks"][i]
        if b["t"] == "p":
            b["text"] = nt
        else:
            b["items"][j] = nt
        changed += 1
    if changed:
        out["method"] = f"deterministic + model polish ({changed} of {len(lines)} lines)"
    return out
