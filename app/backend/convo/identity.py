"""PLAN_R9 G6: how CreditProbe describes itself -- one source for every assistant.

Reads docs/product_knowledge/intelligence.md (identity, distinction, where it runs, traceability and the seven
Intelligence Packs). `parse()` is the structured form (the product knowledge pack carries it as `intelligence`,
the Cockpit synopsis reads it through FX-A4); `charter_line()` is the sentence block every v5 assistant's system
prompt carries so "Who are you?" is answered in the intelligence framing in every module.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DOC = Path(__file__).resolve().parents[2] / "docs" / "product_knowledge" / "intelligence.md"


@lru_cache(maxsize=1)
def parse() -> dict[str, Any] | None:
    if not DOC.exists():
        return None
    text = DOC.read_text(encoding="utf-8")
    head, _, body = text.partition("\n## ")
    meta = dict(re.findall(r"^(\w[\w ]*?):\s*(.+)$", head, re.M))
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in body.splitlines()
            if ln.strip().startswith("|") and not re.match(r"^\|[\s|:-]+\|$", ln.strip())]
    packs = [{"id": r[0], "name": r[1], "knows": r[2], "shows_up_in": r[3]} for r in rows[1:] if len(r) >= 4]
    if not meta.get("Identity") or not packs:
        return None
    return {"identity": meta["Identity"], "distinction": meta.get("Distinction", ""),
            "runs_on": meta.get("Runs on", ""), "traceability": meta.get("Traceable", ""),
            "library": meta.get("Library", ""), "answer_note": meta.get("Answer", ""), "packs": packs}


@lru_cache(maxsize=1)
def charter_line() -> str:
    """The self-description block for an assistant's system prompt ('' if the doc is missing)."""
    p = parse()
    if not p:
        return ""
    packs = "; ".join(f"{x['id']} {x['name']} ({x['knows'].rstrip('.')})" for x in p["packs"])
    return (f"Who you are: {p['identity']} {p['distinction']} The seven Intelligence Packs: {packs}. "
            f"{p['runs_on']} {p['traceability']} If asked who you are or what CreditProbe can do, answer in this "
            "framing: the identity sentence, the seven packs one line each, that it runs on the bank's data beside "
            "its LOS, rating and ECL systems, and that every answer is traceable.")
