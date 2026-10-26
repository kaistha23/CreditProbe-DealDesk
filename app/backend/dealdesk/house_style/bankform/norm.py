"""Contract rows (docs/v5/R12_DATA_CONTRACT.md) -> the field names the writers use. Each function keeps `_src` (the real
relation and row) and accepts the writers' own names too, so a row already in the writers' shape passes unchanged.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.house_style.bankform.source import first as f


def _keep(r: dict[str, Any], **kv: Any) -> dict[str, Any]:
    out = dict(r)
    for k, v in kv.items():
        if v is not None:
            out[k] = v
    return out


def _flag(v: Any) -> bool:
    return str(v) in ("1", "True", "true", "1.0")


def header(deal: dict[str, Any] | None, legacy: dict[str, Any] | None, pj: dict[str, Any] | None, subject: dict[str, Any] | None) -> dict[str, Any]:
    """The proposal's header and ask: dd_deal (header block) + its proposal record + dd_proposal (R11) + the subject entity."""
    deal, legacy, pj, subject = deal or {}, legacy or {}, pj or {}, subject or {}
    ob, ask = pj.get("obligor") or {}, pj.get("ask") or {}
    p: dict[str, Any] = {**legacy}
    p.update({k: v for k, v in deal.items() if v not in (None, "")})
    p["_src"] = deal.get("_src") or legacy.get("_src")
    p.update({
        "obligor_name": f(deal, "obligor_name", default=f(legacy, "obligor_name", default=ob.get("name"))),
        "obligor_id": f(deal, "cif", "obligor_id", default=f(legacy, "obligor_id", default=ob.get("obligor_id"))),
        "book_obligor_id": f(deal, "obligor_id", default=f(legacy, "obligor_id", default=ob.get("obligor_id"))),
        "group_id": f(deal, "group_id", default=f(legacy, "group_id", default=ob.get("group_id"))),
        "group_no": f(deal, "group_no", "group_id", default=f(legacy, "group_id")),
        "group_name": f(deal, "group_name", default=f(legacy, "group_name", default=ob.get("group_name"))),
        "sector": f(legacy, "sector", default=ob.get("sector")), "sub_sector": f(legacy, "sub_sector", default=ob.get("sub_sector")),
        "sector_code": f(legacy, "sector_code", default=ob.get("sector_code")),
        "internal_rating": f(deal, "rating_existing", default=f(legacy, "internal_rating", default=ob.get("internal_rating"))),
        "proposed_rating": f(deal, "rating_proposed", default=f(legacy, "internal_rating", default=ob.get("internal_rating"))),
        "currency": f(deal, "currency", default=f(legacy, "currency", default=ask.get("currency") or pj.get("deal_currency") or "SAR")),
        "request_kind": f(deal, "case_type", default=f(legacy, "case_type", default=pj.get("case") if isinstance(pj.get("case"), str) else None)),
        "account_opened": f(deal, "account_opened_date", "account_opened"),
        "purpose": f(legacy, "purpose", default=pj.get("purpose")),
        "received_date": f(deal, "received_date", default=f(legacy, "received_date", default=pj.get("received"))),
        "group_cap_existing": f(deal, "group_cap_existing_mn", "group_cap_existing"),
        "group_cap_proposed": f(deal, "group_cap_proposed_mn", "group_cap_proposed"),
        "group_exposure_total": f(deal, "group_exposure_mn", "group_exposure_total"),
        "existing_limits": f(deal, "existing_limits_mn"), "proposed_limits": f(deal, "proposed_limits_mn"),
        "approval_authority": f(deal, "approval_authority"),
        "amount": f(legacy, "amount", default=ask.get("amount")), "facility_type": f(legacy, "facility_type", default=ask.get("facility_type")),
        "tenor_years": f(legacy, "tenor_years", default=ask.get("tenor_years")), "margin_bps": f(legacy, "margin_bps", default=ask.get("margin_bps")),
        "existing_ead_sar_mn": f(legacy, "existing_ead_sar_mn", default=ob.get("existing_exposure_sar_mn")),
        # the subject entity (Borrower 360): trade licence and activity
        "trade_licence_no": f(subject, "licence_no", "trade_licence_no", default=f(deal, "trade_licence_no")),
        "incorporation_date": f(subject, "incorporation_date", default=f(deal, "incorporation_date")),
        "incorporation_place": f(subject, "incorporation_place", default=f(deal, "incorporation_place")),
        "legal_status": f(subject, "legal_status", default=f(deal, "legal_status")),
        "activity": f(subject, "activity", default=f(deal, "activity")),
        "staff_count": f(subject, "staff_count", default=f(deal, "staff_count")),
    })
    for k in list(p):
        if p[k] in (None, "") and deal.get(k) not in (None, ""):
            p[k] = deal[k]
    for k in ("sales_terms", "purchase_terms", "activity_mix", "study_fee", "previous_committee_ref", "previous_committee_date", "geopolitical_note",
              "as_of", "group_exposure_funded"):
        v = f(deal, k, default=pj.get(k))
        if v not in (None, ""):
            p[k] = v
    return p


def facility_limit(r: dict[str, Any]) -> dict[str, Any]:
    bench, spread, floor, comm = r.get("benchmark"), r.get("spread_pct"), r.get("floor_pct"), r.get("commission_pct_pa")
    pricing = r.get("pricing")
    if not pricing:
        bits = []
        if bench:
            bits.append(f"{bench} + {float(spread):.2f}%" if spread is not None else str(bench))
        if floor is not None and float(floor or 0) > 0:
            bits.append(f"floor {float(floor):.2f}%")
        if comm is not None and float(comm or 0) > 0:
            bits.append(f"commission {float(comm):.2f}% p.a.")
        pricing = ", ".join(bits)
    return _keep(r, name=f(r, "limit_name", "name"), existing=f(r, "existing_mn", "existing"), outstanding=f(r, "outstanding_mn", "outstanding"),
                 proposed=f(r, "proposed_mn", "proposed"), pricing=pricing or None, tenor=f(r, "tenor_text", "tenor"),
                 repayment=f(r, "repayment_text", "repayment"), validity=f(r, "particulars", "validity"))


KIND_LABEL = {"personal_guarantee": "Personal guarantee", "corporate_guarantee": "Corporate guarantee", "security_cheque": "Undated security cheque",
              "assignment_receivables": "Assignment of receivables", "assignment_insurance": "Assignment of insurance",
              "assignment_project_proceeds": "Assignment of project proceeds", "hypothecation": "Hypothecation", "subordination": "Subordination of shareholder accounts",
              "mortgage": "Mortgage", "cash_margin": "Cash margin", "pledge_shares": "Pledge of shares", "noc": "NOC", "undertaking": "Undertaking"}


def security(r: dict[str, Any], limit_names: dict[str, str]) -> dict[str, Any]:
    st = str(f(r, "perfection_status", default="") or "")
    st = {"perfected": "executed", "not_perfected": "pending", "not_applicable": ""}.get(st, st)
    lid = f(r, "limit_id")
    return _keep(r, item_type=f(r, "item_type", default=KIND_LABEL.get(str(r.get("kind")), str(r.get("kind") or "Security").replace("_", " ").capitalize())),
                 guarantor=f(r, "provider", "guarantor"), value=f(r, "amount_mn", "value_mn", "value"), guarantor_net_worth=f(r, "net_worth_mn", "guarantor_net_worth"),
                 nw_statement_date=f(r, "net_worth_statement_date", "nw_statement_date"), perfection_status=st or None,
                 perfection_due=f(r, "perfection_deadline", "perfection_due"),
                 limit_group=f(r, "limit_group", default=("All limits" if lid in (None, "", "ALL") else limit_names.get(str(lid), str(lid)))))


TNC_STATUS = {"new": "new", "complied": "complied", "not_complied": "not complied", "existing": "existing", "open": "existing", "met": "complied",
              "breached": "not complied", "waived": "waived"}


def tnc(r: dict[str, Any], limit_names: dict[str, str]) -> dict[str, Any]:
    lid = f(r, "limit_id")
    return _keep(r, limit_group=f(r, "limit_group", default=("All limits" if lid in (None, "", "ALL") else limit_names.get(str(lid), str(lid)))),
                 status=TNC_STATUS.get(str(f(r, "existing_status", "status", default="new")), str(f(r, "existing_status", "status", default=""))),
                 category=f(r, "category", default="term"))


def condition(r: dict[str, Any], limit_names: dict[str, str]) -> dict[str, Any]:
    lid = f(r, "limit_id")
    k = str(f(r, "kind", "category", default=""))
    return _keep(r, limit_group=f(r, "limit_group", default=("All limits" if lid in (None, "", "ALL") else limit_names.get(str(lid), str(lid)))),
                 status=TNC_STATUS.get(str(r.get("status")), r.get("status")), category=("cp" if k == "cp" else k),
                 committee_ref=f(r, "prior_committee_ref", "committee_ref"), due=f(r, "due_date", "due"),
                 achieved=f(r, "measured_value", "achieved"), required=f(r, "trigger_threshold", "required"))


def entity(r: dict[str, Any], exposure: dict[str, dict[str, Any]]) -> dict[str, Any]:
    e = exposure.get(str(r.get("entity_id")), {})
    cs = str(r.get("credit_status") or "")
    return _keep(r, entity=f(r, "entity_name", "entity"), relation=f(r, "relation", "role"),
                 exposure_funded=f(e, "funded_proposed_mn", default=f(r, "exposure_funded")), exposure_total=f(e, "total_proposed_mn", default=f(r, "exposure_total")),
                 classification=f(r, "classification", default=(cs.replace("_", " ").replace("classified ", "") if cs and cs != "performing" else "")),
                 litigation=1 if cs == "litigation" else r.get("litigation"))


def shareholder(r: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    by = r.get("birth_year")
    return _keep(r, entity=f(r, "entity", default=names.get(str(r.get("entity_id")), r.get("entity_id"))), holder=f(r, "holder_name", "holder"),
                 pct=f(r, "share_pct", "pct"), dob=(f"{int(by)}-01-01" if by else r.get("dob")))


def board(r: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    od = r.get("other_directorships")
    if isinstance(od, list):
        od = "; ".join(f"{x.get('entity_name')} ({x.get('role')})" for x in od if isinstance(x, dict)) or "None recorded"
    return _keep(r, entity=f(r, "entity", default=names.get(str(r.get("entity_id")), r.get("entity_id"))), person=f(r, "person_name", "person"),
                 role=str(f(r, "role", default="")).replace("_", " ").upper() if str(r.get("role", "")) in ("ceo", "cfo", "gm") else str(f(r, "role", default="")).replace("_", " ").capitalize(),
                 since=f(r, "appointed", "since"), other_directorships=od)


def insider(r: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    lk = str(r.get("link_kind") or "")
    label = {"staff_shareholding": "bank employee holding shares", "staff_relative": "relative of a bank employee",
             "board_member_of_bank": "board member of the bank", "related_party": "related party of the bank"}.get(lk, lk.replace("_", " "))
    return _keep(r, person=f(r, "person_name", "person"), entity=f(r, "entity", default=names.get(str(r.get("entity_id")), r.get("entity_id"))),
                 link_kind=label, as_of=f(r, "as_of", default=None))


def ownership_change(r: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    fp, tp = r.get("from_pct"), r.get("to_pct")
    pct = r.get("pct")
    if pct is None and tp is not None:
        pct = abs(float(tp) - float(fp or 0))
    who = r.get("holder_name")
    kind = str(r.get("kind") or "")
    return _keep(r, entity=f(r, "entity", default=names.get(str(r.get("entity_id")), r.get("entity_id"))), date=f(r, "change_date", "date"), pct=pct,
                 from_holder=f(r, "from_holder", default=(who if kind == "exit" else "existing holders")),
                 to_holder=f(r, "to_holder", default=(who if kind != "exit" else "other holders")))


def conduct(r: dict[str, Any]) -> dict[str, Any]:
    return _keep(r, month=f(r, "month", "reporting_month"), credit_turnover=f(r, "credit_turnover_mn", "credit_turnover_sar_mn", "credit_turnover"),
                 avg_balance=f(r, "avg_balance_mn", "avg_balance_sar_mn", "avg_balance"),
                 returned_cheques=f(r, "returned_cheques_n", "cheques_returned_count", "returned_cheques"), returned_cheques_amount=f(r, "returned_cheques_mn", "cheques_returned_sar_mn", "returned_cheques_amount"),
                 past_due_days_max=f(r, "past_due_days_max"))


def reference(r: dict[str, Any]) -> dict[str, Any]:
    return _keep(r, committee_ref=f(r, "ref_no", "committee_ref"), date=f(r, "ref_date", "date"), total_limit=f(r, "amount_mn", "total_limit"),
                 decision=f(r, "text", "decision", default=""))


def financials(r: dict[str, Any]) -> dict[str, Any]:
    m = lambda *k, default=None: f(r, *k, default=default)  # noqa: E731
    top = m("top2_receivable_pct")
    n = 2
    if top is None:
        top, n = m("top5_receivable_pct"), 5
    if top is None:
        top, n = m("top1_receivable_pct"), 1
    kind = str(m("period_kind", "kind") or "audited")
    return _keep(r, kind=("audited" if kind in ("audited", "actual") else kind), entity_scope=("standalone" if m("entity_scope") in ("branch",) else m("entity_scope")),
                 revenue=m("revenue_mn", "revenue", "revenue_sar_mn"), gross_profit=m("gross_profit_mn", "gross_profit"), operating_profit=m("operating_profit_mn", "operating_profit"),
                 net_profit=m("net_profit_mn", "net_profit"), ebitda=m("ebitda_mn", "ebitda", "ebitda_sar_mn"), total_assets=m("total_assets_mn", "total_assets"),
                 current_assets=m("current_assets_mn", "current_assets"), current_liabilities=m("current_liabilities_mn", "current_liabilities"),
                 inventory=m("inventory_mn", "inventory"), receivables=m("receivables_mn", "receivables"), retention_receivable=m("retention_receivables_mn", "retention_receivable"),
                 related_party_receivable=m("due_from_related_mn", "related_party_receivable"), intangibles=m("intangibles_mn", "intangibles"),
                 shareholder_accounts=m("shareholder_accounts_mn", "shareholder_accounts"), noncore_investments=m("noncore_investments_mn", "noncore_investments"),
                 cash=m("cash_mn", "cash"), bank_debt_st=m("bank_debt_st_mn", "bank_debt_st"), bank_debt_lt=m("bank_debt_lt_mn", "bank_debt_lt"),
                 net_worth=m("net_worth_mn", "net_worth", "net_worth_sar_mn"), ocf=m("operating_cash_flow_mn", "ocf"), contingent_liabilities=m("contingent_liabilities_mn", "contingent_liabilities"),
                 rec_0_90=m("ageing_0_90_mn", "rec_0_90"), rec_91_180=m("ageing_91_180_mn", "rec_91_180"), rec_181_365=m("ageing_181_365_mn", "rec_181_365"),
                 rec_over_365=m("ageing_over_365_mn", "rec_over_365"), top_n=m("top_n", default=n if top is not None else None), top_n_share=m("top_n_share", default=top),
                 backlog=m("backlog_mn", "backlog"), auditor_panel=({"listed": "on the bank panel", "unlisted": "not on the bank panel"}.get(str(m("auditor_panel")), m("auditor_panel"))),
                 note=m("note", "source") if m("entity_scope") == "consolidated" else r.get("note"))


def project(r: dict[str, Any], employer: dict[str, Any] | None = None) -> dict[str, Any]:
    st = str(r.get("status") or "")
    eot_days, formal = r.get("eot_days"), r.get("eot_formalised_flag")
    eot = r.get("eot_status")
    if not eot and eot_days:
        eot = f"EOT of {int(eot_days)} days " + ("formalised" if _flag(formal) else "requested; not formalised")
    prof = r.get("employer_profile")
    if not prof and employer:
        prof = (f"{employer.get('entity_name')}: {employer.get('legal_status') or 'legal status not provided'}, {employer.get('country') or ''}, "
                f"{'listed' if _flag(employer.get('listed_flag')) else 'unlisted'}, activity {employer.get('activity') or 'not provided'}"
                + (f", incorporated {employer.get('incorporation_date')}" if employer.get("incorporation_date") else "")
                + (f"; credit status {str(employer.get('credit_status')).replace('_', ' ')}" if employer.get("credit_status") else ""))
    return _keep(r, name=f(r, "project_name", "name"), contract_value_original=f(r, "contract_value_original_mn", "contract_value_original"),
                 contract_value_revised=f(r, "contract_value_revised_mn", "contract_value_revised"), end_date_original=f(r, "completion_original", "end_date_original"),
                 end_date_revised=f(r, "completion_revised", "end_date_revised"), wd_pct=f(r, "work_done_pct", "wd_pct"), received=f(r, "received_mn", "received"),
                 due=f(r, "due_mn", "due"), last_ipc_no=f(r, "last_cert_no", "last_ipc_no"), last_ipc_date=f(r, "last_cert_date", "last_ipc_date"),
                 eot_status=eot, note=f(r, "narrative", "note"), is_new=(1 if st == "new" or _flag(r.get("is_new")) else 0),
                 lg_requirement=f(r, "lg_requirements", "lg_requirement"), employer_profile=prof)


def cashflow(r: dict[str, Any]) -> dict[str, Any]:
    return _keep(r, month=f(r, "month_no", "month"), period=f(r, "period", default=r.get("month") if isinstance(r.get("month"), str) else None),
                 cost_materials=f(r, "cost_materials_mn", "cost_materials"), cost_subcontract=f(r, "cost_subcontract_mn", "cost_subcontract"),
                 cost_labour=f(r, "cost_labour_mn", "cost_labour"), cost_overheads=f(r, "cost_overheads_mn", "cost_overheads"),
                 receipts=f(r, "receipts_mn", "receipts"), retention_held=f(r, "retention_held_mn", "retention_held"), cumulative=f(r, "cumulative_mn", "cumulative"))


def bureau(r: dict[str, Any]) -> dict[str, Any]:
    rd = r.get("returned_cheque_dates")
    if isinstance(rd, str) and ";" in rd:
        ds = [x.strip() for x in rd.split(";") if x.strip()]
        rd = f"{ds[0]} to {ds[-1]}" if len(ds) > 1 else ds[0]
    return _keep(r, entity=f(r, "entity_name", "entity"), role=f(r, "entity_kind", "role"), outstanding=f(r, "outstanding_mn", "outstanding"),
                 overdue=f(r, "overdue_mn", "overdue"), returned_cheques=f(r, "returned_cheques_n", "returned_cheques"), returned_cheque_dates=rd,
                 court_cases=f(r, "court_cases_n", "court_cases"), provided=f(r, "provided_flag", "provided", default=1), reason=f(r, "not_provided_reason", "reason"))


def cbrbr(r: dict[str, Any]) -> dict[str, Any]:
    return _keep(r, entity=f(r, "entity_name", "entity"), funded_limit=f(r, "funded_limit_mn", "funded_limit"), funded_outstanding=f(r, "funded_outstanding_mn", "funded_outstanding"),
                 nonfunded_limit=f(r, "non_funded_limit_mn", "nonfunded_limit"), nonfunded_outstanding=f(r, "non_funded_outstanding_mn", "nonfunded_outstanding"),
                 banks=f(r, "banks_n", "banks"), classification=str(f(r, "classification", default="")).replace("_", " ").capitalize() or None)


def other_bank(r: dict[str, Any]) -> dict[str, Any]:
    note = f(r, "note", default=None)
    if not note and r.get("reconciliation_note"):
        note = str(r["reconciliation_note"]) + ("" if _flag(r.get("clarified_flag", 1)) or "not clarified" in str(r["reconciliation_note"]) else "; not clarified")
    if note and str(note).count("not clarified") > 1:
        note = str(note).replace("; not clarified", "")
    if not _flag(r.get("fal_provided_flag", 1)) and "facility letter" not in str(note or "").lower():
        note = (str(note) + "; " if note else "") + "facility letter not provided"
    return _keep(r, bank=f(r, "bank_name", "bank"), entity=f(r, "entity_name", "entity"), declared_limit=f(r, "declared_limit_mn", "declared_limit"),
                 bureau_limit=f(r, "bureau_limit_mn", "bureau_limit"), declared_outstanding=f(r, "declared_outstanding_mn", "declared_outstanding"),
                 bureau_outstanding=f(r, "bureau_outstanding_mn", "bureau_outstanding"), note=note)


SEV = {"critical": "critical", "high": "major", "medium": "major", "low": "minor", "info": "minor", "major": "major", "minor": "minor"}


def finding(r: dict[str, Any]) -> dict[str, Any]:
    kind = r.get("kind") or ("exception" if str(r.get("review_point")) == "5" or str(r.get("category", "")).startswith("policy") else "observation")
    claim = r.get("claim_text")
    return _keep(r, text=f(r, "finding_text", "text"), severity=SEV.get(str(r.get("severity")), r.get("severity")), kind=kind,
                 business_reason=f(r, "business_reason", default=(f"Business conveys: {claim}" if claim else None)))


QUAD = {"S": "strength", "W": "weakness", "O": "opportunity", "T": "threat"}


def swot(r: dict[str, Any]) -> dict[str, Any]:
    return _keep(r, kind=QUAD.get(str(r.get("quadrant")), r.get("kind")), evidence=f(r, "evidence_relation", "evidence"), mitigant=f(r, "mitigant_text", "mitigant"))


VERDICT = {"restructure": "Restructure", "approve_enhanced": "Approve with enhanced monitoring", "approve_standard": "Approve, standard monitoring", "approve": "Approve"}


def plan(r: dict[str, Any]) -> dict[str, Any]:
    trig = r.get("named_triggers")
    if isinstance(trig, list):
        trig = "; ".join(str(x.get("label") or f"{x.get('metric')} {x.get('operator')} {x.get('threshold')}") for x in trig if isinstance(x, dict))
    drv = r.get("drivers")
    if isinstance(drv, list):
        drv = "; ".join(str(x).replace("_", " ") for x in drv)
    return _keep(r, verdict=VERDICT.get(str(r.get("stress_verdict")), f(r, "verdict", "stress_verdict")), thresholds=f(r, "thresholds", default=trig), drivers=drv,
                 review_frequency=str(f(r, "review_frequency", default="")).replace("_", "-") or None, set_on=str(f(r, "set_at", "set_on", default=""))[:10] or None)


def stress(r: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    br = r.get("breaks")
    if isinstance(br, str) and not br.isdigit():
        what = "; ".join({"dscr": "DSCR below 1.0x", "covenant": "a covenant", "stage2": "Stage 2", "hurdle": "RAROC below hurdle", "limit": "a limit"}.get(x.strip(), x.strip())
                         for x in br.split(";") if x.strip())
        breaks = 1 if what else 0
    else:
        what, breaks = r.get("what_breaks") or "", 1 if _flag(br) else 0
    value = r.get("value")
    unit = ""
    if value is None:
        if "dscr" in str(br) or "covenant" in str(br):
            value, unit = r.get("dscr_x"), "x"
        elif "hurdle" in str(br):
            value, unit = r.get("raroc_pct"), "%"
    elif "RAROC" in str(what):
        unit = "%"
    elif "DSCR" in str(what) or "cover" in str(what).lower():
        unit = "x"
    if str(r.get("applicable_flag", 1)) in ("0", "0.0", "False"):
        breaks, what = 0, "not applicable to this deal"
    return _keep(r, scenario=f(r, "scenario", default=labels.get(str(r.get("scenario_id")), r.get("scenario_id"))), breaks=breaks, what_breaks=what,
                 value=(f"{float(value):,.2f}{unit}" if isinstance(value, (int, float)) else value))


def scenario(r: dict[str, Any]) -> dict[str, Any]:
    sh = r.get("shocks_json")
    narrative = r.get("narrative")
    if not narrative and isinstance(sh, dict):
        narrative = sh.get("narrative") or ", ".join(f"{k.replace('_', ' ').replace(' pct', '')} {'+' if isinstance(v, (int, float)) and v > 0 else ''}{v}"
                                                     + ("%" if k.endswith("_pct") else "") for k, v in sh.items()
                                                     if not str(k).startswith("_"))   # R13 S: the stored _meta is not a shock
    return _keep(r, name=f(r, "label", "name"), narrative=narrative, as_of=f(r, "effective_date", "as_of"))


def document(r: dict[str, Any], clauses: dict[str, str]) -> dict[str, Any]:
    return _keep(r, name=f(r, "doc_label", "name"), date=f(r, "doc_date", "date"), clause=f(r, "clause", default=clauses.get(str(r.get("rule_id")), "")))


def promise(r: dict[str, Any]) -> dict[str, Any]:
    mult = r.get("multiple_of_limit")
    if mult is not None:
        prom, unit = mult, "x the limit"
        dl = r.get("delivered_pct")
        deliv = round(float(mult) * float(dl) / 100.0, 2) if dl is not None else None
    else:
        prom, unit, deliv = r.get("promised_mn"), "m a year", r.get("delivered_mn")
    return _keep(r, promised=f(r, "promised", default=prom), delivered=f(r, "delivered", default=deliv), unit=f(r, "unit", default=unit), due=f(r, "window_to", "due"))
