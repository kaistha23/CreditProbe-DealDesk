"""The deal file the R12 review reads (PLAN §0: every fact from a Data Domains relation, through the shared readers).

`deal_file(sid)` returns one dict:

  subject        id, name, group, sector, segment, product, currency, rating, amount, existing, as_of
  financials     years [{year, kind, revenue, ebitda, net_profit, total_assets, current_assets, current_liabilities, net_worth,
                 total_debt, intangibles, related_party_receivable, related_party_payable, shareholder_accounts,
                 noncore_investments, receivables, recv_0_90, recv_91_180, recv_181_365, recv_over_365, top1_share, top2_share,
                 topn_share, topn_n, retention_receivable, retention_overdue, cash_cycle_days}], plus auditor, auditor_listed, opinion,
                 qualification_basis, qualification_amount, entity_scope
  bureau         entities [{entity, role, outstanding, overdue, returned_cheques, returned_cheque_dates, score, court_cases, provided,
                 not_provided_reason}], cbrbr [{entity, funded_limit, funded_os, nf_limit, nf_os, banks, classification}],
                 other_banks [{bank, entity, declared_limit, bureau_limit, letter}]
  conduct        months, turnover, avg_balance, returned_cheques, excess_days
  earlier        [{condition_id, text, kind, metric, required, achieved, unit, status, committee_ref}]
  insider        [{party, person, link, share, source_note}]
  group          entities [{name, role}], ubos [{name, share}], guarantors [{name, kind}], projects [{name}], collateral [{id, type}]
  documents      {evidence_key: {received, date, note}} for the document checklist
  r11            the R11 review facts (rules.json reads them)
  lineage        {block: src(relation, key, period, via)}

Each block is read from its relation through publish.read (E's dd_read). Until a relation has rows for the deal, the block
is built from the R11 evidence the bank already holds for that deal, and its lineage says so ("via": "r11-evidence").
"""
from __future__ import annotations

import functools
from typing import Any

from backend.dealdesk import review_facts as RF
from backend.dealdesk.review2 import publish as P

#: The fictional twins (PLAN N7): the R11 prepared cases and the names E publishes them under.
TWINS = {"PRP-A-GMC": {"twin": "B", "name": "Gulf Meridian Contracting", "product": "contracting"},
         "PRP-B-ASB": {"twin": "A", "name": "Al Sahel Building Materials Group", "product": "corporate"},
         "R12-TWB": {"twin": "B", "name": "Gulf Meridian Contracting", "product": "contracting"},
         "R12-TWA": {"twin": "A", "name": "Al Sahel Building Materials Group", "product": "corporate"}}

FIN_NUM = ("revenue", "ebitda", "net_profit", "total_assets", "current_assets", "current_liabilities", "net_worth", "total_debt",
           "intangibles", "related_party_receivable", "related_party_payable", "shareholder_accounts", "noncore_investments",
           "receivables", "recv_0_90", "recv_91_180", "recv_181_365", "recv_over_365", "top1_share", "top2_share", "topn_share",
           "topn_n", "retention_receivable", "retention_overdue", "cash_cycle_days", "goodwill_internal")


def known(sid: str) -> bool:
    from backend.dealdesk.review2 import base as BASE
    return BASE.known(sid)


def _num(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ the R11 evidence (fallback per block)

def _fallback_case(sid: str, f: dict[str, Any]) -> dict[str, Any]:
    c, ev = f["case"], f["ev"]
    fin, gov, bu, sec = c["financials"], ev.get("governance") or {}, ev.get("bureau") or {}, ev.get("security") or {}
    year: dict[str, Any] = {"year": 2025, "kind": "audited", "revenue": fin.get("revenue"), "ebitda": fin.get("ebitda"),
                            "total_debt": fin.get("net_debt"), "current_assets": fin.get("current_assets"),
                            "related_party_receivable": fin.get("related_party_receivable"),
                            "goodwill_internal": fin.get("goodwill_internal"),
                            "intangibles": fin.get("goodwill_internal"),
                            "noncore_investments": fin.get("noncore_property"), "shareholder_accounts": fin.get("shareholder_withdrawals"),
                            "cash_cycle_days": fin.get("cash_cycle_days"), "working_capital": fin.get("working_capital"),
                            "working_capital_prior": fin.get("working_capital_prior")}
    if fin.get("receivables_over_1y") is not None:
        year["recv_over_365_share"] = fin["receivables_over_1y"]
    if fin.get("related_party_share_ca") is not None:
        year["related_party_share_ca"] = fin["related_party_share_ca"]
    if fin.get("parent_related_party_share") is not None:
        year["related_party_share_ta"] = fin["parent_related_party_share"]
    rets = (ev.get("retentions") or {}).get("by_completion_year") or []
    if rets:
        year["retention_receivable"] = round(sum(r["amount"] for r in rets), 2)
        year["retention_overdue"] = round(sum(r["amount"] for r in rets), 2)  # every completion year is past the defects period
        year["retention_by_year"] = rets
    bs = fin.get("backlog_share") or {}
    if bs:
        shares = sorted(bs.values(), reverse=True)
        year["top1_share"] = shares[0]
        year["top2_share"] = round(sum(shares[:2]), 4)
        year["topn_share"], year["topn_n"] = round(sum(shares), 4), len(shares)
        year["top_names"] = [{"name": k, "share": v} for k, v in sorted(bs.items(), key=lambda kv: -kv[1])]
        year["concentration_basis"] = "backlog by employer"
    opinion = gov.get("audit_opinion") or "unqualified"
    approved = {a.lower() for a in (f.get("approved_auditors") or [])}
    auditor = gov.get("auditor")
    entities = [{"name": c["borrower"], "role": "borrower"}]
    core = {c["borrower"], c["group"]}
    for n in c.get("network") or []:
        if "staff" in n["from"].lower():
            continue
        for side in ("from", "to"):
            nm = n[side]
            if nm in {e["name"] for e in entities} or nm.lower().startswith("two group"):
                continue
            grp = n["kind"] in ("receivable", "ownership") and (nm == c["group"] or n["from"] in core)
            entities.append({"name": nm, "role": "group" if grp else "connected"})
    # bureau per entity
    b_entities = [{"entity": c["borrower"], "role": "subject", "outstanding": None, "overdue": None,
                   "returned_cheques": c["deposits"].get("returned_cheques") if c["deposits"].get("returned_cheques") else 0,
                   "returned_cheque_dates": bu.get("affiliate_returned_period"), "score": None, "court_cases": 0, "provided": True,
                   "not_provided_reason": None}]
    if bu.get("affiliate_returned_cheques"):
        b_entities[0]["returned_cheques"] = 0
        b_entities.append({"entity": f"{c['group']} Dubai affiliate", "role": "group", "outstanding": None, "overdue": None,
                           "returned_cheques": bu["affiliate_returned_cheques"], "returned_cheque_dates": bu.get("affiliate_returned_period"),
                           "score": None, "court_cases": 0, "provided": True, "not_provided_reason": None})
    for g in bu.get("group_entities_loss") or []:
        b_entities.append({"entity": g["name"], "role": "group", "outstanding": g["amount"], "overdue": g["amount"], "returned_cheques": None,
                           "returned_cheque_dates": None, "score": None, "court_cases": None, "provided": True, "classification": "Loss",
                           "not_provided_reason": None})
    for cx in (ev.get("connected") or {}).get("classified_elsewhere") or []:
        b_entities.append({"entity": cx["name"], "role": "connected", "outstanding": None, "overdue": None, "returned_cheques": None,
                           "returned_cheque_dates": None, "score": None, "court_cases": 1 if cx.get("litigation_aed_mn") else 0,
                           "litigation": cx.get("litigation_aed_mn"), "provided": True, "classification": cx.get("classification"),
                           "not_provided_reason": None})
    other = []
    if bu.get("client_reported_other_bank_limits") is not None or bu.get("cbrbr_other_bank_limits") is not None:
        other.append({"bank": f"Other banks ({c['other_banks']['banks'] if c.get('other_banks') else 'n'})", "entity": c["group"],
                      "declared_limit": bu.get("client_reported_other_bank_limits"), "bureau_limit": bu.get("cbrbr_other_bank_limits"),
                      "letter": bool((c.get("other_banks") or {}).get("facility_letters"))})
    cbrbr = []
    if bu.get("cbrbr_other_bank_limits") is not None:
        cbrbr.append({"entity": c["group"], "funded_limit": None, "funded_os": None, "nf_limit": None, "nf_os": None,
                      "total_limit": bu["cbrbr_other_bank_limits"], "banks": (c.get("other_banks") or {}).get("banks"), "classification": "Regular"})
    for g in bu.get("group_entities_loss") or []:
        cbrbr.append({"entity": g["name"], "funded_limit": None, "funded_os": g["amount"], "nf_limit": None, "nf_os": None,
                      "total_limit": None, "banks": None, "classification": "Loss"})
    earlier = []
    rt = ev.get("routing")
    if rt:
        earlier.append({"condition_id": f"{sid}-ROUTING", "text": f"Undertaking to route {rt['required_x']:g}x the limit through the bank",
                        "kind": "undertaking", "metric": "routing_x", "required": rt["required_x"], "achieved": rt["achieved_x"], "unit": "x",
                        "committee_ref": "previous renewal"})
    if gov.get("auditor_change_consent") is False:
        earlier.append({"condition_id": f"{sid}-AUDITOR", "text": "No change of auditor without the bank's prior consent", "kind": "covenant",
                        "metric": "auditor_change_consent", "required": 1, "achieved": 0, "unit": "flag", "committee_ref": "previous approval"})
    if sec.get("performance_bond_due"):
        earlier.append({"condition_id": f"{sid}-PB", "text": f"Performance bond submitted by {sec['performance_bond_due']}", "kind": "CP",
                        "metric": "performance_bond", "required": sec["performance_bond_due"], "achieved": sec.get("performance_bond_submitted"),
                        "unit": "date", "committee_ref": "previous approval"})
    insider = [{"party": s.get("party"), "person": s.get("person") or "Bank staff member", "link": s.get("link") or s.get("role") or "shareholding",
                "share": s.get("share"), "source_note": "Staff interest declarations"} for s in (ev.get("connected") or {}).get("staff_interest") or []]
    for n in (ev.get("connected") or {}).get("nominee_holdings") or []:
        insider.append({"party": n["name"], "person": f"{c['group']} (through {n.get('via', 'nominees')})", "link": "nominee holding",
                        "share": n.get("share"), "source_note": "Connected-party register", "kind": "related"})
    guarantors = [{"name": "Corporate guarantor", "kind": "corporate"}] if sec.get("corporate_guarantee_perfection") else []
    docs = {"audited": {"received": True, "date": "2026-04-30", "note": ev["sources"].get("audited")},
            "standalone": {"received": bool(gov.get("standalone_financials")), "date": "2026-04-30" if gov.get("standalone_financials") else None,
                           "note": None if gov.get("standalone_financials") else "Only consolidated accounts of the parent submitted"},
            "bureau": {"received": True, "date": "2026-10-10", "note": ev["sources"].get("bureau")},
            "cbrbr": {"received": True, "date": "2026-10-10", "note": ev["sources"].get("bureau")},
            "fal": {"received": bool((c.get("other_banks") or {}).get("facility_letters")), "date": None,
                    "note": "Facility letters for the new borrowing at other banks not provided" if not (c.get("other_banks") or {}).get("facility_letters") else None},
            "legal_opinion": {"received": bool(sec.get("legal_opinion_date")), "date": sec.get("legal_opinion_date"),
                              "note": None if sec.get("legal_opinion_date") else "No legal opinion on file"},
            "security_signed": {"received": sec.get("corporate_guarantee_perfection") == "perfected", "date": None,
                                "note": f"Corporate guarantee perfection {sec.get('corporate_guarantee_perfection')}" if sec.get("corporate_guarantee_perfection") else None},
            "contract": {"received": bool(ev.get("projects")), "date": None, "note": None},
            "ipc": {"received": bool(ev.get("projects")), "date": "2026-09-15" if ev.get("projects") else None, "note": None},
            "project_cashflow": {"received": bool(c.get("stress")), "date": "2026-09-30" if c.get("stress") else None, "note": None},
            "trade_licence": {"received": True, "date": "2026-02-01", "note": None},
            "moa": {"received": True, "date": "2019-03-10", "note": None},
            "board_resolution": {"received": True, "date": "2026-09-20", "note": None},
            "kyc": {"received": not gov.get("ownership_changed"), "date": None if gov.get("ownership_changed") else "2026-01-15",
                    "note": f"Ownership changed on {gov['ownership_changed']}; refreshed KYC not provided" if gov.get("ownership_changed") else None},
            "interim": {"received": False, "date": None, "note": "Interim financials for 2026 not provided"},
            "bank_statements": {"received": True, "date": "2026-09-30", "note": ev["sources"].get("conduct")},
            "net_worth": {"received": False, "date": None, "note": "Guarantor net-worth statement not provided"}}
    return {
        "financials": {"years": [year], "auditor": auditor, "auditor_listed": (auditor or "").lower() in approved if auditor else None,
                       "opinion": opinion, "qualification_basis": gov.get("qualification"), "qualification_amount": gov.get("qualification_amount"),
                       "entity_scope": "standalone" if gov.get("standalone_financials") else "consolidated (parent)",
                       "ownership_changed": gov.get("ownership_changed")},
        "bureau": {"entities": b_entities, "cbrbr": cbrbr, "other_banks": other},
        "conduct": {"months": 12, "turnover_to_revenue": c["deposits"].get("turnover_to_revenue"), "avg_balance": c["deposits"].get("avg_balance"),
                    "returned_cheques": c["deposits"].get("returned_cheques"), "note": c["deposits"].get("returned_cheque_note")},
        "earlier": earlier, "insider": insider,
        "group": {"entities": entities, "ubos": [], "guarantors": guarantors,
                  "projects": [{"name": p["name"]} for p in ev.get("projects") or []],
                  "collateral": []},
        "documents": docs,
    }


def _fallback_dd(sid: str, f: dict[str, Any]) -> dict[str, Any]:
    p = f["dd"]
    years = []
    for y in p["financials"]["years"]:
        row = {"year": y["year"], "kind": "audited" if y["kind"] == "actual" else "projection",
               **{k: y.get(k) for k in ("revenue", "ebitda", "total_debt", "net_worth", "debt_service")}}
        if y.get("current_ratio") is not None:
            row["current_ratio"] = y["current_ratio"]
        years.append(row)
    o = p["obligor"]
    conduct = f.get("conduct") or {}
    ent = [{"name": o["name"], "role": "borrower"}] + [{"name": c.get("name") or c["id"], "role": "connected"} for c in f.get("connected") or []]
    b_entities = [{"entity": o["name"], "role": "subject", "outstanding": (f.get("book") or {}).get("ead"), "overdue": None,
                   "returned_cheques": conduct.get("returned_cheques"), "returned_cheque_dates": None, "score": None, "court_cases": None,
                   "provided": True, "classification": "Regular" if (o.get("simah_flag") or "clear") == "clear" else str(o.get("simah_flag")).title(),
                   "not_provided_reason": None}]
    for c in f.get("connected") or []:
        b_entities.append({"entity": c.get("name") or c["id"], "role": "connected", "outstanding": c.get("ead"), "overdue": None,
                           "returned_cheques": None, "returned_cheque_dates": None, "score": None, "court_cases": None, "provided": True,
                           "classification": "Stage %d" % c.get("stage_max", 1), "not_provided_reason": None})
    coll = [{"id": c.get("collateral_id"), "type": c.get("type"), "valuation_date": c.get("valuation_date")} for c in f.get("collateral") or []]
    acts = [y for y in years if y["kind"] == "audited"]
    docs = {"audited": {"received": bool(acts), "date": f"{acts[-1]['year'] + 1}-04-30" if acts else None, "note": "Financial spreading"},
            "standalone": {"received": True, "date": f"{acts[-1]['year'] + 1}-04-30" if acts else None, "note": None},
            "projections": {"received": any(y["kind"] == "projection" for y in years), "date": None, "note": None},
            "bureau": ({"received": True, "date": None, "note": "SIMAH flag " + str(o.get("simah_flag")) + " in the proposal record"}
                       if str(o.get("simah_flag") or "").strip().lower() not in ("", "none", "nan") else
                       {"received": False, "date": None, "note": "SIMAH report not on file (a data gap, not a bureau hit)"}),
            "valuation": {"received": bool(coll), "date": max((c["valuation_date"] for c in coll if c.get("valuation_date")), default=None), "note": None},
            **({"bank_statements": {"received": True, "date": None, "note": conduct.get("source")}} if conduct else {})}
    return {
        "financials": {"years": years, "auditor": None, "auditor_listed": None, "opinion": None, "qualification_basis": None,
                       "qualification_amount": None, "entity_scope": "standalone", "ownership_changed": None},
        "bureau": {"entities": b_entities, "cbrbr": [], "other_banks": []},
        "conduct": conduct, "earlier": [], "insider": [],
        "group": {"entities": ent, "ubos": [], "guarantors": [{"name": g.get("guarantor_name") or g.get("guarantee_id"), "kind": g.get("type", "guarantee")}
                                                               for g in f.get("guarantees") or []],
                  "projects": [], "collateral": coll},
        "documents": docs,
    }


# ------------------------------------------------------------------ the Data Domains blocks (R12_DATA_CONTRACT)

def _pct(x: Any) -> float | None:
    v = _num(x)
    if v is None:
        return None
    return v / 100.0 if abs(v) > 1.0 else v


def _deal_row(sid: str) -> dict[str, Any] | None:
    rows = P.read("dd_deal", proposal_id=sid)
    return rows[0] if rows else None


def _entities(deal: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not deal or not deal.get("group_id"):
        return []
    return P.read("b360_entity", group_id=deal["group_id"])


def _dd_financials(sid: str, ents: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = P.read("dd_financials_detail", proposal_id=sid)
    if not rows:
        return None
    subj = {e["entity_id"] for e in ents if e.get("role") == "subject"}
    mine = [r for r in rows if r.get("entity_id") in subj] or [r for r in rows if r.get("entity_scope") in ("standalone", "branch")] or rows
    years = []
    for r in sorted(mine, key=lambda r: (str(r.get("period_end") or r.get("year")), str(r.get("period_kind")))):
        y: dict[str, Any] = {"year": r.get("year"), "kind": r.get("period_kind") or "audited", "label": r.get("period_label"),
                             "months": r.get("months"), "entity": r.get("entity_name"), "scope": r.get("entity_scope")}
        m = {"revenue": "revenue_mn", "ebitda": "ebitda_mn", "net_profit": "net_profit_mn", "total_assets": "total_assets_mn",
             "current_assets": "current_assets_mn", "current_liabilities": "current_liabilities_mn", "net_worth": "net_worth_mn",
             "intangibles": "intangibles_mn", "related_party_receivable": "due_from_related_mn", "related_party_payable": "due_to_related_mn",
             "shareholder_accounts": "shareholder_accounts_mn", "noncore_investments": "noncore_investments_mn", "receivables": "receivables_mn",
             "recv_0_90": "ageing_0_90_mn", "recv_91_180": "ageing_91_180_mn", "recv_181_365": "ageing_181_365_mn",
             "recv_over_365": "ageing_over_365_mn", "retention_receivable": "retention_receivables_mn", "cash_cycle_days": "cash_cycle_days",
             "operating_cash_flow": "operating_cash_flow_mn", "contingent_liabilities": "contingent_liabilities_mn", "backlog": "backlog_mn"}
        for k, c in m.items():
            v = _num(r.get(c))
            if v is not None:
                y[k] = v
        st, lt = _num(r.get("bank_debt_st_mn")), _num(r.get("bank_debt_lt_mn"))
        if st is not None or lt is not None:
            y["total_debt"] = (st or 0.0) + (lt or 0.0)
        for k, c in (("top1_share", "top1_receivable_pct"), ("top2_share", "top2_receivable_pct"), ("topn_share", "top5_receivable_pct")):
            v = _pct(r.get(c))
            if v is not None:
                y[k] = v
        if y.get("topn_share") is not None:
            y["topn_n"] = 5
        y["_row"] = r
        years.append(y)
    aud = [r for r in mine if str(r.get("period_kind")) == "audited"]
    last = aud[-1] if aud else mine[-1]
    op = str(last.get("opinion") or "").lower() or None
    return {"years": years, "auditor": last.get("auditor"),
            "auditor_listed": None if not last.get("auditor_panel") else str(last["auditor_panel"]).lower() == "listed",
            "opinion": {"clean": "unqualified"}.get(op or "", op), "qualification_basis": last.get("qualification_basis"),
            "qualification_amount": None, "entity_scope": last.get("entity_scope"), "ownership_changed": None,
            "entities_reported": sorted({str(r.get("entity_name")) for r in rows if r.get("entity_name")})}


_CLASS = {"regular": "Regular", "current": "Regular", "watch": "Watch", "substandard": "Substandard", "doubtful": "Doubtful", "loss": "Loss"}


def _dd_bureau(sid: str, ents: list[dict[str, Any]]) -> dict[str, Any] | None:
    ent = P.read("bureau_entity_report", proposal_id=sid)
    cb = P.read("bureau_cbrbr", proposal_id=sid)
    ob = P.read("other_bank_facility", proposal_id=sid)
    if not (ent or cb or ob):
        return None
    role = {e["entity_id"]: e.get("role") for e in ents}
    status = {e["entity_id"]: e.get("credit_status") for e in ents}
    out_e = []
    for r in ent:
        rl = role.get(r.get("entity_id")) or ("ubo" if r.get("entity_kind") == "ubo" else r.get("entity_kind") or "group")
        cls = r.get("worst_status")
        cs = status.get(r.get("entity_id")) or ""
        if cs.startswith("classified_"):
            cls = cs.split("_", 1)[1]
        out_e.append({"entity": r.get("entity_name"), "entity_id": r.get("entity_id"), "role": "subject" if rl == "subject" else rl,
                      "outstanding": _num(r.get("outstanding_mn")), "overdue": _num(r.get("overdue_mn")),
                      "returned_cheques": r.get("returned_cheques_n"), "returned_cheque_dates": r.get("returned_cheque_dates"),
                      "score": r.get("score"), "court_cases": r.get("court_cases_n"), "litigation": _num(r.get("court_cases_mn")),
                      "provided": bool(r.get("provided_flag", 1)), "not_provided_reason": r.get("not_provided_reason"),
                      "classification": _CLASS.get(str(cls or "").lower(), (f"{cls} past due" if str(cls or "").endswith("days") else cls)),
                      "report_date": r.get("report_date"),
                      "ref": {"relation": "bureau_entity_report", "key": {"report_id": r.get("report_id")}, "period": r.get("reporting_quarter")}})
    out_c = [{"entity": r.get("entity_name"), "funded_limit": _num(r.get("funded_limit_mn")), "funded_os": _num(r.get("funded_outstanding_mn")),
              "nf_limit": _num(r.get("non_funded_limit_mn")), "nf_os": _num(r.get("non_funded_outstanding_mn")),
              "total_limit": _num(r.get("total_limit_mn")), "total_os": _num(r.get("total_outstanding_mn")), "banks": r.get("banks_n"),
              "classification": _CLASS.get(str(r.get("classification") or "").lower(), r.get("classification")), "report_date": r.get("report_date")}
             for r in cb]
    out_o = [{"bank": r.get("bank_name"), "entity": r.get("entity_name"), "declared_limit": _num(r.get("declared_limit_mn")),
              "bureau_limit": _num(r.get("bureau_limit_mn")), "declared_os": _num(r.get("declared_outstanding_mn")),
              "bureau_os": _num(r.get("bureau_outstanding_mn")), "letter": None if r.get("fal_provided_flag") is None else bool(r["fal_provided_flag"]),
              "fal_date": r.get("fal_date"), "clarified": bool(r.get("clarified_flag")), "note": r.get("reconciliation_note"),
              "security": r.get("security_text")} for r in ob]
    return {"entities": out_e, "cbrbr": out_c, "other_banks": out_o}


_STATUS = {"met": "complied", "not_complied": "not complied", "breached": "not complied", "waived": "waived", "open": None}


def _dd_earlier(sid: str) -> list[dict[str, Any]] | None:
    rows = P.read("dd_condition", proposal_id=sid, source="prior_approval")
    out = []
    for r in rows:
        metric = str(r.get("trigger_metric") or "")
        unit = "x" if ("multiple" in metric or metric.endswith("_x")) else "%" if "pct" in metric else ""
        out.append({"condition_id": r.get("condition_id"), "text": r.get("text"), "kind": r.get("kind"), "metric": metric,
                    "required": _num(r.get("trigger_threshold")), "achieved": _num(r.get("measured_value")), "unit": unit,
                    "status": _STATUS.get(str(r.get("status") or ""), None), "committee_ref": r.get("prior_committee_ref"),
                    "measured_at": r.get("measured_at")})
    return out or None


def _dd_insider(ents: list[dict[str, Any]], guarantor_ids: set[str]) -> list[dict[str, Any]] | None:
    ids = {e["entity_id"] for e in ents} | guarantor_ids
    if not ids:
        return None
    names = {e["entity_id"]: e.get("entity_name") for e in ents}
    rows = P.read("b360_insider_link", entity_id=sorted(ids))
    out = []
    for r in rows:
        k = str(r.get("link_kind") or "")
        person = r.get("person_name") or "Bank staff member"
        if r.get("staff_role"):
            person = f"{person} ({r['staff_role']}{', ' + r['relationship'] if r.get('relationship') and r['relationship'] != 'self' else ''})"
        out.append({"party": names.get(r.get("entity_id")) or r.get("entity_id"), "person": person, "link": k.replace("_", " "),
                    "share": _pct(r.get("share_pct")), "kind": "staff" if k.startswith("staff") or k == "board_member_of_bank" else "related",
                    "disclosed": bool(r.get("disclosed_flag")), "source_note": r.get("detected_by") or "Borrower 360"})
    return out or None


def _dd_conduct(sid: str) -> dict[str, Any] | None:
    rows = P.read("dd_account_conduct", proposal_id=sid)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: str(r.get("month")))[-12:]
    return {"months": len(rows), "returned_cheques": int(sum(int(r.get("returned_cheques_n") or 0) for r in rows)),
            "returned_cheques_amount": round(sum(_num(r.get("returned_cheques_mn")) or 0 for r in rows), 3),
            "turnover": round(sum(_num(r.get("credit_turnover_mn")) or 0 for r in rows), 3),
            "avg_balance": round(sum(_num(r.get("avg_balance_mn")) or 0 for r in rows) / len(rows), 3),
            "routed": round(sum(_num(r.get("routed_business_mn")) or 0 for r in rows), 3),
            "past_due_days_max": max(int(r.get("past_due_days_max") or 0) for r in rows), "source": "dd_account_conduct"}


def _dd_security(sid: str) -> list[dict[str, Any]]:
    return P.read("dd_security", proposal_id=sid)


def _docs_from_domain(sec: list[dict[str, Any]], fin: dict[str, Any] | None, bureau: dict[str, Any] | None,
                      projects: list[dict[str, Any]]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    los = [s.get("legal_opinion_date") for s in sec if s.get("legal_opinion_date")]
    d["legal_opinion"] = {"received": bool(los), "date": max(los) if los else None, "note": None if los else "No legal opinion on file"}
    perf = [s for s in sec if s.get("perfection_status") not in (None, "not_applicable")]
    pend = [s for s in perf if s.get("perfection_status") != "perfected"]
    d["security_signed"] = {"received": bool(perf) and not pend, "date": None,
                            "note": ("; ".join(f"{s.get('kind', '').replace('_', ' ')} by {s.get('provider')}: {str(s.get('perfection_status')).replace('_', ' ')}"
                                               + (f", deadline {s['perfection_deadline']}" if s.get("perfection_deadline") else "") for s in pend[:3])) or None}
    gs = [s for s in sec if str(s.get("kind")) in ("personal_guarantee", "corporate_guarantee")]
    nws = [s.get("net_worth_statement_date") for s in gs if s.get("net_worth_statement_date")]
    if gs:
        d["net_worth"] = {"received": len(nws) == len(gs), "date": min(nws) if nws else None,
                          "note": None if len(nws) == len(gs) else "Net-worth statement not provided as per business"}
    vals = [s.get("valuation_date") for s in sec if s.get("valuation_date")]
    if vals:
        d["valuation"] = {"received": True, "date": min(vals), "note": None}
    ins = [s.get("insurance_expiry") for s in sec if s.get("insurance_expiry")]
    if ins:
        d["insurance"] = {"received": True, "date": None, "note": f"Insurance expires {min(ins)}"}
    if fin:
        ys = fin["years"]
        aud = [y for y in ys if y["kind"] == "audited"]
        intr = [y for y in ys if y["kind"] == "interim"]
        d["audited"] = {"received": bool(aud), "date": None, "note": f"{len(aud)} audited periods ({fin.get('auditor') or 'auditor not named'})" if aud else None}
        d["interim"] = {"received": bool(intr), "date": None, "note": None if intr else "Interim financials not provided"}
        d["standalone"] = {"received": any(str(y.get("scope")) in ("standalone", "branch") for y in aud), "date": None,
                           "note": None if any(str(y.get("scope")) in ("standalone", "branch") for y in aud) else "Only combined or consolidated statements submitted"}
        d["projections"] = {"received": any(y["kind"] == "projection" for y in ys), "date": None, "note": None}
    if bureau:
        rd = [e.get("report_date") for e in bureau["entities"] if e.get("provided") and e.get("report_date")]
        d["bureau"] = {"received": bool(rd), "date": min(rd) if rd else None, "note": None}
        d["bureau_by_party"] = {str(e.get("entity") or "").strip().lower(): {"received": bool(e.get("provided")), "date": e.get("report_date"),
                                                                             "note": e.get("not_provided_reason")} for e in bureau["entities"]}
        cd = [c.get("report_date") for c in bureau["cbrbr"] if c.get("report_date")]
        d["cbrbr"] = {"received": bool(bureau["cbrbr"]), "date": min(cd) if cd else None, "note": None if bureau["cbrbr"] else "CBRBR not on file"}
        ob = bureau["other_banks"]
        if ob:
            d["fal"] = {"received": all(o.get("letter") for o in ob), "date": None,
                        "note": None if all(o.get("letter") for o in ob) else f"{sum(1 for o in ob if not o.get('letter'))} other-bank facility letters not provided"}
    if projects:
        d["contract"] = {"received": True, "date": None, "note": None}
    return d


@functools.lru_cache(maxsize=64)
def _cached(sid: str, tag: str) -> dict[str, Any]:
    from backend.dealdesk.review2 import base as BASE
    f = BASE.facts(sid, with_ledger=False)
    s = f["subject"]
    is_case = RF.is_case(sid)
    fb = _fallback_case(sid, f) if is_case else _fallback_dd(sid, f)
    deal = _deal_row(sid)
    ents = _entities(deal)
    period = (deal or {}).get("reporting_quarter") or s.get("as_of")
    lin: dict[str, Any] = {}

    def tag_(block: str, relation: str, key: dict[str, Any], used: bool) -> None:
        lin[block] = P.src(relation, key, period, None if used else ("r11-evidence" if is_case else "proposal-record"))

    fin = _dd_financials(sid, ents)
    tag_("financials", "dd_financials_detail" if fin else "dd_obligor_financials", {"proposal_id": sid}, bool(fin) or not is_case)
    bureau = _dd_bureau(sid, ents)
    tag_("bureau", "bureau_entity_report", {"proposal_id": sid}, bool(bureau))
    tag_("cbrbr", "bureau_cbrbr", {"proposal_id": sid}, bool(bureau))
    tag_("other_banks", "other_bank_facility", {"proposal_id": sid}, bool(bureau))
    earlier = _dd_earlier(sid)
    tag_("earlier", "dd_condition", {"proposal_id": sid, "source": "prior_approval"}, bool(earlier))
    sec = _dd_security(sid)
    guarantor_ids = {str(x.get("provider_entity_id")) for x in sec if x.get("provider_entity_id")}
    insider = _dd_insider(ents, guarantor_ids)
    tag_("insider", "b360_insider_link", {"group_id": (deal or {}).get("group_id")}, bool(insider) or bool(ents))
    conduct = _dd_conduct(sid)
    tag_("conduct", "dd_account_conduct" if conduct else "dep_month", {"proposal_id": sid}, bool(conduct) or not is_case)
    tag_("group", "b360_entity" if ents else "rel_edge_quarter", {"group_id": (deal or {}).get("group_id")}, bool(ents))
    tag_("security", "dd_security", {"proposal_id": sid}, bool(sec))
    lin["documents"] = P.src("dd_document", {"proposal_id": sid}, period)
    projects = P.read("dd_project", proposal_id=sid)

    group = fb["group"]
    if ents:
        ubos = P.read("b360_shareholder", entity_id=[e["entity_id"] for e in ents if e.get("role") == "subject"]) if ents else []
        group = {"entities": [{"name": e["entity_name"], "role": "borrower" if e.get("role") == "subject" else
                               ("group" if e.get("role") in ("parent", "subsidiary", "sister") else e.get("role") or "connected"),
                               "entity_id": e["entity_id"], "credit_status": e.get("credit_status")} for e in ents],
                 "ubos": [{"name": u["holder_name"], "share": _pct(u.get("share_pct")), "entity_id": u.get("holder_id")} for u in ubos if u.get("ubo_flag")],
                 "guarantors": [{"name": x.get("provider"), "kind": x.get("kind"), "entity_id": x.get("provider_entity_id")}
                                for x in sec if str(x.get("kind")) in ("personal_guarantee", "corporate_guarantee")] or fb["group"]["guarantors"],
                 "projects": [{"name": pr.get("project_name") or pr.get("project_id")} for pr in projects] or fb["group"]["projects"],
                 "collateral": [{"id": x.get("security_id"), "type": str(x.get("kind")).replace("_", " ")} for x in sec if x.get("valuation_date")]
                               or fb["group"]["collateral"]}
    elif projects:
        group = {**group, "projects": [{"name": pr.get("project_name") or pr.get("project_id")} for pr in projects]}
    docs = {**fb["documents"], **(_docs_from_domain(sec, fin, bureau, projects) if (sec or fin or bureau or projects) else {})}

    tw = TWINS.get(sid, {})
    rec = f.get("dd") or {}
    product = (deal or {}).get("product") or tw.get("product") or "corporate"
    sme = product == "sme" or bool((rec.get("obligor") or {}).get("sme")) or "sme" in str((f.get("case") or {}).get("segment") or "").lower()
    subj = {**s, "segment": "sme" if sme else "corporate", "product": product, "twin": tw.get("twin"), "twin_name": tw.get("name"),
            "case_type": (deal or {}).get("case_type"), "group_id": (deal or {}).get("group_id"), "deal_name": (deal or {}).get("deal_name")}
    if deal and _num(deal.get("proposed_limits_mn")):
        subj["amount_ccy"] = _num(deal["proposed_limits_mn"])
        subj["existing_ccy"] = _num(deal.get("existing_limits_mn")) or subj.get("existing_ccy")
        subj["currency"] = deal.get("currency") or subj.get("currency")
    req = []
    if deal:
        purpose = (rec.get("purpose") or "").strip()
        if purpose:
            req.append(purpose)
        for lim in sorted(P.read("dd_facility_limit", proposal_id=sid), key=lambda r: r.get("seq") or 0):
            if lim.get("level") != 1:
                continue
            e, pr = _num(lim.get("existing_mn")) or 0.0, _num(lim.get("proposed_mn")) or 0.0
            nm = str(lim.get("limit_name") or "").split(" (")[0]
            nm = nm[0].lower() + nm[1:] if nm[1:2].islower() else nm
            ccy = deal.get("currency") or ""
            if not e and pr:
                req.append(f"New {nm} of {ccy} {pr:,.0f}m")
            elif pr > e:
                req.append(f"Increase the {nm} from {ccy} {e:,.0f}m to {pr:,.0f}m")
            elif pr < e:
                req.append(f"Reduce the {nm} from {ccy} {e:,.0f}m to {pr:,.0f}m")
            else:
                req.append(f"Renew the {nm} at {ccy} {pr:,.0f}m")
        if _num(deal.get("group_cap_proposed_mn")) and _num(deal.get("group_cap_proposed_mn")) != _num(deal.get("group_cap_existing_mn")):
            req.append(f"Raise the group exposure cap from {deal.get('currency')} {_num(deal.get('group_cap_existing_mn')):,.0f}m to "
                       f"{_num(deal['group_cap_proposed_mn']):,.0f}m")
    subj["request_summary"] = req
    raw = {"financials": [y["_row"] for y in (fin or {}).get("years", []) if y.get("_row")],
           "bureau_entity_report": P.read("bureau_entity_report", proposal_id=sid) if bureau else [],
           "other_bank_facility": P.read("other_bank_facility", proposal_id=sid) if bureau else [],
           "dd_condition": P.read("dd_condition", proposal_id=sid, source="prior_approval") if earlier else [],
           "b360_insider_link": P.read("b360_insider_link", entity_id=sorted({e["entity_id"] for e in ents} | guarantor_ids)) if insider and ents else []}
    if fin:
        for y in fin["years"]:
            y.pop("_row", None)
    promises = P.read("dd_promise", proposal_id=sid)
    lin["promises"] = P.src("dd_promise", {"proposal_id": sid}, period, None if promises else "none")
    return {"raw": raw, "promises": promises, "subject": subj, "deal": deal, "financials": fin or fb["financials"], "bureau": bureau or fb["bureau"],
            "conduct": conduct or fb["conduct"], "earlier": earlier or fb["earlier"], "insider": insider if insider is not None else fb["insider"],
            "group": group, "documents": docs, "security": sec, "projects": projects, "r11": f, "lineage": lin}


def deal_file(sid: str) -> dict[str, Any]:
    from backend.dealdesk import params
    v = ""
    try:
        from backend.dealdesk.data import store as DS
        v = "|".join(str(DS.version_of(r)) for r in ("dd_deal", "dd_financials_detail", "bureau_entity_report", "dd_condition", "dd_security"))
    except Exception:  # noqa: BLE001
        pass
    return _cached(sid, params.version_tag() + "|" + v)


def clear() -> None:
    _cached.cache_clear()
