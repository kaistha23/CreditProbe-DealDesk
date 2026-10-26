"""Traced figures (PLAN_R12 §0 rule 3, N5): the key numbers of the group, cap and conduct blocks as E's lineage figures,
`{"value", "unit", "source": {domain, relation, key, period, column}}`, each resolving to one registered row
(`backend.dealdesk.data.lineage`). They travel in the API response (`figures`) for (i), Trace and "Open in Data Domains",
and they are the lineage cases of Session C in `backend/tests/test_r12_lineage.py`.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.group import deal, facts_entity


def _fig(relation: str, row: dict[str, Any], column: str, unit: str, label: str) -> dict[str, Any] | None:
    from backend.dealdesk.data.lineage import figure
    if row.get(column) is None:
        return None
    f = figure(relation, row, column, unit)
    f["label"] = label
    return f


def build(pid: str) -> dict[str, list[dict[str, Any]]]:
    from backend.dealdesk.data.store import dd_read
    p = deal.get(pid)
    oid = deal.focal_id(p)
    out: dict[str, list[dict[str, Any]]] = {"group": [], "cap": [], "owners": [], "conduct": [], "bureau": []}

    def add(block: str, f: dict[str, Any] | None) -> None:
        if f is not None:
            out[block].append(f)

    subj = facts_entity.subject(p)
    if subj is not None:  # an entity group (R12 demo deals)
        for r in dd_read("dd_group_exposure", proposal_id=pid):
            add("group", _fig("dd_group_exposure", r, "total_proposed_mn", "SAR million", f"{r['entity_name']}: total proposed"))
            add("group", _fig("dd_group_exposure", r, "outstanding_mn", "SAR million", f"{r['entity_name']}: outstanding"))
        refs = [r for r in dd_read("dd_reference", proposal_id=pid) if r.get("group_cap_mn")]
        for r in refs:
            add("cap", _fig("dd_reference", r, "group_cap_mn", "SAR million", f"Group cap approved {r.get('ref_date')} ({r.get('ref_no')})"))
        for r in dd_read("dd_deal", columns=["proposal_id", "reporting_quarter", "group_cap_existing_mn", "group_cap_proposed_mn"], proposal_id=pid):
            add("cap", _fig("dd_deal", r, "group_cap_existing_mn", "SAR million", "Group cap today"))
            add("cap", _fig("dd_deal", r, "group_cap_proposed_mn", "SAR million", "Group cap asked"))
        for r in dd_read("b360_shareholder", entity_id=subj["entity_id"]):
            add("owners", _fig("b360_shareholder", r, "share_pct", "%", f"{r['holder_name']}: shareholding"))
        ac = sorted(dd_read("dd_account_conduct", obligor_id=oid), key=lambda r: r["month"])[-12:]
        for r in ac:
            if r.get("returned_cheques_n"):
                add("conduct", _fig("dd_account_conduct", r, "returned_cheques_n", "count", f"Returned cheques {r['month']}"))
        for r in dd_read("dd_condition", proposal_id=pid):
            if str(r.get("trigger_metric") or "").startswith("rout"):
                add("conduct", _fig("dd_condition", r, "measured_value", r.get("trigger_metric") or "", "Routing achieved"))
                add("conduct", _fig("dd_condition", r, "trigger_threshold", r.get("trigger_metric") or "", "Routing required"))
        for r in dd_read("bureau_entity_report", proposal_id=pid):
            if r.get("provided_flag"):
                add("bureau", _fig("bureau_entity_report", r, "court_cases_n", "count", f"{r['entity_name']}: court cases"))
        return out
    # a book borrower
    gq = dd_read("rel_group_quarter", reporting_quarter=deal.AS_OF, borrower_id=oid) if oid else []
    gid = gq[0]["group_id"] if gq else p["obligor"].get("group_id")
    if gid:
        for r in dd_read("rel_group_quarter", reporting_quarter=deal.AS_OF, group_id=gid):
            add("group", _fig("rel_group_quarter", r, "ownership_pct", "%", f"{r['borrower_id']}: {r['role']} held"))
    for r in dd_read("rel_person_role", borrower_id=oid, role="Owner") if oid else []:
        add("owners", _fig("rel_person_role", r, "ownership_pct", "%", f"{r['person_name']}: shareholding"))
    for r in dd_read("dep_derived", obligor_id=oid) if oid else []:
        add("conduct", _fig("dep_derived", r, "routing_actual_x", "x", "Routing achieved"))
        add("conduct", _fig("dep_derived", r, "routing_required_x", "x", "Routing required"))
        add("conduct", _fig("dep_derived", r, "returned_cheque_rate_pct", "%", "Returned-cheque rate"))
    for r in dd_read("bureau_corp_quarter", borrower_id=oid, reporting_quarter=deal.AS_OF) if oid else []:
        add("bureau", _fig("bureau_corp_quarter", r, "external_dpd_days", "days", "External days past due"))
        add("bureau", _fig("bureau_corp_quarter", r, "external_exposure_sar_mn", "SAR million", "External exposure"))
    return out
