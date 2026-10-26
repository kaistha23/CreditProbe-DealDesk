"""The structure step: a number the analyst wants changed goes to the engine, never into the text.

    paper2, info = proposal_terms(paper, [{"field": "amount", "value": 20, "mode": "to", "sign": 1}])
        new terms = the selected structure's terms with the field changed; the bank-form writer re-runs on them (bankform/feed.py
        prices them: economics, approval authority, capacity) and every section is re-rendered from the engine's figures.
    paper2, info = request_ask(paper, "increase the overdraft to SAR 35m")
        the RM's ask is the business request's structure: the clause for that facility is replaced (or added) and the request is
        written again by R16 b's deterministic writer.

Sections the analyst had reworded keep the wording when the engine's text of that section did not change; otherwise the engine's
new text replaces it and the reply says so.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from backend.dealdesk.paperws import sources

LABEL = {"amount": "amount (SAR m)", "tenor_years": "tenor (years)", "margin_bps": "margin (bps)", "cash_margin_pct": "cash margin (%)",
         "upfront_fee_bps": "upfront fee (bps)"}
BOUNDS = {"amount": (0.01, 100_000), "tenor_years": (0.08, 30), "margin_bps": (0, 2_000), "cash_margin_pct": (0, 100), "upfront_fee_bps": (0, 1_000)}


class StructureError(ValueError):
    pass


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def carry_edits(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """(new paper with the analyst's wording kept where the engine's text is unchanged, sections the engine changed,
    sections whose wording was replaced)."""
    old_by = {s["key"]: s for s in old.get("sections") or []}
    changed, replaced = [], []
    secs = []
    for s in new.get("sections") or []:
        o = old_by.get(s["key"])
        if o is None:
            secs.append(s)
            changed.append(s["key"])
            continue
        engine_old = o.get("engine_blocks", o.get("blocks"))
        if _same(engine_old, s.get("blocks")):
            secs.append(copy.deepcopy(o))           # engine text unchanged: the analyst's current wording stands
        else:
            secs.append(s)
            changed.append(s["key"])
            if "engine_blocks" in o:
                replaced.append(s["key"])
    return {**new, "sections": secs}, changed, replaced


def proposal_terms(paper: dict[str, Any], fields: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    pid = paper["proposal_id"]
    terms = dict(paper.get("structure_terms") or {})
    if not terms:
        try:
            from backend.dealdesk.house_style.bankform import feed as FD
            terms = dict(FD.feed(pid, "ask").structure.get("terms") or {})
        except Exception:  # noqa: BLE001
            terms = {}
    if not terms:
        raise StructureError("The structure step needs the structure's terms: choose a structure on the deal's Structure step first.")
    moves = []
    for f in fields:
        k = f["field"]
        cur = terms.get(k)
        if f["mode"] == "by":
            if not isinstance(cur, (int, float)):
                raise StructureError(f"The {LABEL[k]} is not on the selected structure, so it cannot be moved by an amount.")
            new = float(cur) + f["sign"] * float(f["value"])
        else:
            new = float(f["value"])
        lo, hi = BOUNDS[k]
        if not lo <= new <= hi:
            raise StructureError(f"{LABEL[k].capitalize()} {new:g} is outside what the engine prices ({lo:g} to {hi:g}).")
        terms[k] = round(new, 4)
        moves.append({"field": k, "label": LABEL[k], "from": cur, "to": terms[k]})
    new_paper = sources.rewrite_proposal(pid, terms)
    merged, changed, replaced = carry_edits(paper, new_paper)
    f = new_paper.get("feed") or {}
    return merged, {"fields": moves, "changed": changed, "replaced": replaced, "engine": (f.get("sources") or {}).get("economics", ""),
                    "raroc": f.get("raroc"), "hurdle": f.get("hurdle"), "approval": f.get("approval"), "terms": terms}


def is_request_ask(instruction: str) -> bool:
    from backend.dealdesk.rm_request import ask as A
    return bool(A.facility_of(instruction) and A.amounts(instruction) and A.action_of(instruction, default=""))


def request_ask(paper: dict[str, Any], instruction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from backend.dealdesk.rm_request import ask as A
    from backend.dealdesk.rm_request import inputs as I
    from backend.dealdesk.rm_request import paper as PA
    ref = paper.get("customer_key") or paper.get("proposal_id")
    try:
        cf = I.load(ref)
    except Exception as e:  # noqa: BLE001
        raise StructureError(f"The customer file {ref} could not be read ({type(e).__name__}).") from None
    fac = A.facility_of(instruction)
    clauses = A.clauses(paper.get("ask_text") or "")
    clause = instruction.strip().rstrip(".")
    hit = False
    out = []
    for c in clauses:
        if not hit and A.facility_of(c) == fac:
            out.append(clause)
            hit = True
        else:
            out.append(c)
    if not hit:
        out.append(clause)
    ask_text = "; ".join(out)
    new = PA.write(cf, ask_text, paper.get("notes_text") or "", rm=paper.get("rm") or "", written=paper.get("as_of") or I.AS_OF)
    new["doc_kind"] = "request"
    new["written_at"] = paper.get("written_at")
    merged, changed, replaced = carry_edits(paper, new)
    t0, t1 = (paper.get("totals") or {}).get("proposed"), (new.get("totals") or {}).get("proposed")
    return merged, {"fields": [{"field": "ask", "label": f"{fac[0]} in the ask", "from": paper.get("ask_text"), "to": ask_text}],
                    "changed": changed, "replaced": replaced, "engine": "R16 b ask parser and writer (rm_request)",
                    "total_from": t0, "total_to": t1, "ask_text": ask_text}
