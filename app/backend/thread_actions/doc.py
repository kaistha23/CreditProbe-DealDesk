"""The answer document every module hands to the thread actions (R16 t, M7).

One shape for Cockpit, Noor, Deal Desk, What-If, Lenses, Early Warning, Borrower 360, Scorecard, Playbook and the
intel panels; the frontend builds it from the module's own turn (frontend/src/lib/v5/thread-actions.ts, one
normaliser per module) and the backend only validates and bounds it:

    {"module": "dealdesk", "thread_id": "...", "title": "...", "href": "/deal-desk?thread=...",
     "turns": [{"question": "...", "answer_id": "...",
                "blocks": [{"kind": "text", "text": "..."},
                           {"kind": "bullets", "items": ["..."]},
                           {"kind": "figures", "items": [{"label": "...", "value": "..."}]},
                           {"kind": "table", "title": "...", "columns": ["..."], "rows": [["..."]]}],
                "sources": [{"kind": "relation" | "query" | "row" | "document" | "run" | "engine",
                             "label": "...", "relation": "...", "domain": "...", "sql": "...", "keys": {...},
                             "period": "...", "rows": 12, "href": "..."}]}]}
"""
from __future__ import annotations

import re
from typing import Any

MODULES = {
    "cockpit": "Cockpit", "noor": "Noor", "dealdesk": "Deal Desk", "whatif": "What-If", "lenses": "Lenses",
    "ews": "Early Warning", "b360": "Borrower 360", "scorecard": "Scorecard Validation", "playbook": "Playbook",
    "intel": "Intelligence", "agents": "Agents",
}
SOURCE_KINDS = ("relation", "query", "row", "document", "run", "engine")
MAX_TURNS, MAX_BLOCKS, MAX_ROWS, MAX_COLS, MAX_TEXT, MAX_SOURCES = 40, 40, 200, 14, 8000, 60


class Invalid(ValueError):
    pass


def _s(v: Any, n: int = 400) -> str:
    if v is None:
        return ""
    t = str(v)
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    return t[:n]


def _block(b: Any) -> dict[str, Any] | None:
    if not isinstance(b, dict):
        return None
    k = b.get("kind")
    if k == "text":
        t = _s(b.get("text"), MAX_TEXT).strip()
        return {"kind": "text", "text": t} if t else None
    if k == "bullets":
        items = [_s(i, 600).strip() for i in (b.get("items") or [])[:60]]
        items = [i for i in items if i]
        return {"kind": "bullets", "items": items, "title": _s(b.get("title"), 200)} if items else None
    if k == "figures":
        items = [{"label": _s(i.get("label"), 120), "value": _s(i.get("value"), 120)}
                 for i in (b.get("items") or [])[:24] if isinstance(i, dict) and i.get("label")]
        return {"kind": "figures", "items": items} if items else None
    if k == "table":
        cols = [_s(c, 80) for c in (b.get("columns") or [])[:MAX_COLS]]
        if not cols:
            return None
        rows = []
        for r in (b.get("rows") or [])[:MAX_ROWS]:
            if isinstance(r, dict):
                r = [r.get(c, "") for c in cols]
            if not isinstance(r, (list, tuple)):
                continue
            cells = [_cell(c) for c in list(r)[:len(cols)]]
            cells += [""] * (len(cols) - len(cells))
            rows.append(cells)
        total = b.get("row_count")
        return {"kind": "table", "title": _s(b.get("title"), 200), "columns": cols, "rows": rows,
                "row_count": int(total) if isinstance(total, (int, float)) and total >= len(rows) else len(rows)}
    return None


def _cell(c: Any) -> Any:
    if isinstance(c, bool):
        return "Yes" if c else "No"
    if isinstance(c, (int, float)):
        return c
    return _s(c, 300)


def _source(s: Any) -> dict[str, Any] | None:
    if not isinstance(s, dict):
        return None
    kind = s.get("kind") if s.get("kind") in SOURCE_KINDS else "engine"
    out = {"kind": kind, "label": _s(s.get("label") or s.get("relation") or s.get("purpose") or kind, 240)}
    for k in ("relation", "domain", "period", "href", "method", "status"):
        if s.get(k):
            out[k] = _s(s[k], 300)
    if s.get("sql"):
        out["sql"] = _s(s["sql"], 4000)
    if isinstance(s.get("rows"), (int, float)):
        out["rows"] = int(s["rows"])
    if isinstance(s.get("keys"), dict):
        out["keys"] = {_s(k, 60): _s(v, 120) for k, v in list(s["keys"].items())[:12]}
    elif isinstance(s.get("keys"), list):
        out["keys"] = {f"key{i + 1}": _s(v, 120) for i, v in enumerate(s["keys"][:12])}
    return out


def normalise(payload: Any) -> dict[str, Any]:
    """Validate and bound an answer document; raises Invalid with a plain message."""
    if not isinstance(payload, dict):
        raise Invalid("The document must be an object.")
    module = payload.get("module")
    if module not in MODULES:
        raise Invalid(f"Unknown module '{module}'.")
    turns = []
    for t in (payload.get("turns") or [])[:MAX_TURNS]:
        if not isinstance(t, dict):
            continue
        blocks = [b for b in (_block(x) for x in (t.get("blocks") or [])[:MAX_BLOCKS]) if b]
        sources = [s for s in (_source(x) for x in (t.get("sources") or [])[:MAX_SOURCES]) if s]
        q = _s(t.get("question"), 600).strip()
        if not blocks and not q:
            continue
        turns.append({"question": q, "answer_id": _s(t.get("answer_id"), 120), "blocks": blocks, "sources": sources})
    if not turns or not any(t["blocks"] for t in turns):
        raise Invalid("There is no answer to write up yet. Ask a question first.")
    return {"module": module, "module_label": MODULES[module], "thread_id": _s(payload.get("thread_id"), 120),
            "title": _s(payload.get("title"), 200).strip() or (turns[0]["question"] or MODULES[module])[:200],
            "href": _s(payload.get("href"), 400), "turns": turns}


def numbers_in(text: str) -> int:
    return len(re.findall(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?%?", text or ""))
