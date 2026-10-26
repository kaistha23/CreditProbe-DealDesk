"""R12 Session I: the Book — existing customers inside Deal Desk (PLAN_R12 §1.6; I7, I8, I29, I31).

Modules: sources (registered relations only), drift (RAROC drift attribution), promises (against deposits), repricing,
core (the Book frame, filters, counts), actions (tier, EWS, renewal), feedback (ratchet, hurdle overrides), api, publish.

`landing_card(key)` feeds U's landing cards ("going_bad", "renewals", "conditions").
"""
from __future__ import annotations

from typing import Any

_CARD_FILTER = {"going_bad": "material_going_bad", "renewals": "material_renewals", "renewals_due": "renewals_due",
               "book_going_bad": "going_bad", "material_going_bad": "material_going_bad", "material_renewals": "material_renewals", "conditions": "conditions_due",
                "conditions_due": "conditions_due", "repricing": "repricing", "promises_unmet": "promises_unmet", "tier_high": "tier_high"}


def landing_card(key: str) -> dict[str, Any] | None:
    """{count, ead_sar_mn, line, rows (top 5), href} for a landing card, from the Book.

    R13 X (J9): "going_bad" and "renewals" count material names (distinct borrowers) through the materiality filters
    (core.material_going_bad / core.material_renewals): tier High, or relationship EAD at or above the materiality floor with
    Early Warning high or critical or RAROC drifted below hurdle by the drift gap; renewals within renewals_due_days and above
    the floor. The whole-book counts stay on the Book tab ("Going bad", "Renewals due").
    """
    from backend.dealdesk.book import core
    flt = _CARD_FILTER.get(key)
    if flt is None:
        return None
    lst = core.listing(flt, limit=5)
    c = core.counts()
    count = lst["total"]
    if flt == "material_going_bad":
        f, _ = core.frame()
        t = f[f.material_going_bad]
        count = int(t.borrower_id.nunique())
        m = c["materiality"]
        line = (f"{count:,} names, SAR {lst['ead_sar_mn']:,.0f}m EAD, above SAR {m['materiality_floor_sar_mn']:,.0f}m: "
                f"{int(t[t.tier == 'High'].borrower_id.nunique()):,} tier High, {int(t[t.flag_ews].borrower_id.nunique()):,} Early Warning, "
                f"{int(t[t.material_drift].borrower_id.nunique()):,} below hurdle")
    elif flt == "material_renewals":
        f, _ = core.frame()
        t = f[f.material_renewal]
        count = int(t.borrower_id.nunique())
        below = int(t[~t.above_now].borrower_id.nunique())
        line = f"{count:,} names in the next {int(core._bp()['renewals_due_days'])} days above SAR {c['materiality']['materiality_floor_sar_mn']:,.0f}m; {below:,} below hurdle"  # noqa: SLF001
    elif flt == "going_bad":
        r = c["going_bad_by_reason"]
        line = (f"{lst['total']:,} facilities (SAR {lst['ead_sar_mn']:,.0f}m EAD): {r['drift_below_hurdle']:,} drifted below hurdle, "
                f"{r['downgrade']:,} downgraded 2+ notches, {r['ews']:,} Early Warning high or critical, {r['stress_driver']:,} triggers hit")
    elif flt == "renewals_due":
        line = f"{lst['total']:,} renewals or reviews in the next 90 days; {c['renewals_due_repricing']:,} below hurdle need repricing"
    elif flt == "conditions_due":
        line = f"{lst['total']:,} facilities with a covenant in breach or a condition due this month"
    else:
        line = f"{lst['total']:,} facilities (SAR {lst['ead_sar_mn']:,.0f}m EAD)"
    rows = [{"facility_id": x["facility_id"], "proposal_id": x.get("proposal_id"), "borrower_name": x["borrower_name"],
             "line": "; ".join(x["reasons"][:2]) or x.get("action_text") or f"{x['renewal_kind']} {x['renewal_date']}"} for x in lst["rows"]]
    return {"count": count, "facilities": lst["total"], "ead_sar_mn": lst["ead_sar_mn"], "line": line, "rows": rows, "source": "book",
            "unit": "names" if flt.startswith("material_") else "facilities", "href": f"/deal-desk?tab=book&filter={flt}"}
