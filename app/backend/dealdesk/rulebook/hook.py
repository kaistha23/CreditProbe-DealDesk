"""Approved policies applied continuously: the proposal check (R14 p, every deal, every later upload) runs the Deal Desk
policy checks whose thresholds an approved regulation or policy set, and cites the clause.

    from backend.dealdesk.rulebook.hook import r_rulebook   # appended to proposal_check.rules.RULES (one line)

With no approved policy nothing runs (the check is unchanged byte for byte).
"""
from __future__ import annotations

from typing import Any


def _fact(pid: str) -> dict[str, Any]:
    from backend.dealdesk.rulebook import facts as FA
    rows = FA.pending() if FA._OVERRIDE[0] is not None else (FA._MEM.get("rows") or [])  # noqa: SLF001 - cached facts when warm
    for r in rows:
        if r["proposal_id"] == pid:
            return r
    return FA.one(pid)


def findings(pid: str) -> list[dict[str, Any]]:
    """The policy checks an approved policy moved, on this deal: [{check, label, why, clause, quote, reference, result}]."""
    from backend.dealdesk.rulebook import checks as CK
    from backend.dealdesk.rulebook import store
    ov = store.overlay()
    if not ov:
        return []
    out = []
    for r in CK.evaluate(_fact(pid), ov, list(ov)):
        if r["assessment_id"] and r["result"] in ("pass", "fail"):
            out.append({**r, "reference": next((e.get("reference") for e in ov.get(r["param"], []) if e.get("assessment_id") == r["assessment_id"]), "")})
    return out


def r_rulebook(C: Any) -> list[dict[str, Any]]:
    from backend.dealdesk.proposal_check.rules import F
    out = []
    for r in findings(C.D.pid):
        cite = f"{r['reference'] or 'Policy'} {r['clause']}".strip()
        if r["result"] == "fail":
            out.append(F(f"POL-{r['check']}", "policy", "major", "defect", "policy_threshold_breach", "exceptions",
                         f"{r['label']}: {r['why']} ({cite})", evidence=f"{cite}: “{r['quote'][:240]}”. Deal fact: {r['why']}.",
                         rel="dd_deal", key=f"proposal_id={C.D.pid}",
                         query=f"{cite} requires {r['label'][:1].lower() + r['label'][1:]} ({r['why']}). Please restructure, or list it as a policy exception with the "
                               "business reason and the approving authority."))
        else:
            out.append(F(f"POL-{r['check']}", "policy", "info", "pass", "", "exceptions", f"{r['label']}: {r['why']} ({cite})"))
    return out
