"""The conduct block: how the obligor runs its accounts with the bank (PLAN_R12 §1.4, I24; proposal section 8).

    turnover against limits      dep_month (credit turnover, 12 months) / corp_facility_quarter (approved limits);
                                 dep_derived (routing undertaking: required x, actual x)
    returned cheques             dep_month (count, amount, reason), dep_derived (rate)
    utilisation                  corp_facility_quarter (per facility, 4 quarters), dep_month (excess days, peak OD use)
    past dues                    corp_facility_quarter (DPD, past-due flag, 8 quarters)
    bureau trend                 bureau_corp_quarter (8 quarters), bureau_entity_report (E: score, returned cheques,
                                 court cases)
    relationship since           dep_account (earliest open date)

A new-to-bank obligor has no account history: the block says so and keeps the bureau view.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from backend.dealdesk.group import deal, sources as S
from backend.dealdesk.group.facts import _quarters_back

AS_OF = deal.AS_OF


def _src(relation: str, **keys: Any) -> dict[str, Any]:
    loc = S.locate(relation) or {}
    return {"domain": loc.get("domain"), "relation": relation, "keys": {k: v for k, v in keys.items() if v is not None}}


def _slope(ys: list[float]) -> float | None:
    ys = [y for y in ys if y is not None]
    if len(ys) < 3:
        return None
    x = np.arange(len(ys), dtype=float)
    return float(np.polyfit(x, np.asarray(ys, dtype=float), 1)[0])


def build(pid: str) -> dict[str, Any]:
    p = deal.get(pid)
    ob = p["obligor"]
    oid = deal.focal_id(p)
    out: dict[str, Any] = {"proposal_id": pid, "obligor_id": oid, "obligor": ob["name"], "as_of": AS_OF,
                           "existing": bool(ob.get("existing")), "source": []}

    ac = S.records(S.read("dd_account_conduct", None, obligor_id=oid)) if oid else []
    if ac:  # an R12 demo obligor (not in the Saudi book): its own conduct relations
        return _from_account_conduct(pid, p, oid, ac, out)

    # ---- accounts
    acc = S.records(S.read("dep_account", ["account_no", "type", "open_date", "status", "od_limit_sar_mn"], obligor_id=oid))
    months = S.records(S.read("dep_month", None, obligor_id=oid))
    months.sort(key=lambda m: m["month"])
    der = S.records(S.read("dep_derived", None, obligor_id=oid))
    d = der[0] if der else {}
    out["source"] += [_src("dep_account", obligor_id=oid), _src("dep_month", obligor_id=oid), _src("dep_derived", obligor_id=oid)]
    since = min((a["open_date"] for a in acc if a.get("open_date")), default=None)
    out["relationship"] = {"since": since, "accounts": len(acc), "active": sum(1 for a in acc if a.get("status") == "Active"),
                           "years": (int(AS_OF[:4]) - int(str(since)[:4])) if since else None}

    # ---- facilities: limits, utilisation, past dues
    qs = [_quarters_back(AS_OF, i) for i in range(8)][::-1]
    fac = S.records(S.read("corp_facility_quarter", ["facility_id", "reporting_quarter", "product_type", "facility_class", "limit_sar_mn",
                                                     "drawn_sar_mn", "utilisation_pct", "ead_sar_mn", "dpd_days", "past_due_flag", "stage"],
                           borrower_id=oid, reporting_quarter=qs)) if oid else []
    out["source"].append(_src("corp_facility_quarter", borrower_id=oid, reporting_quarter=[qs[0], qs[-1]]))
    now = [f for f in fac if f["reporting_quarter"] == AS_OF]
    limits = sum(f["limit_sar_mn"] or 0 for f in now)
    drawn = sum(f["drawn_sar_mn"] or 0 for f in now)
    last4 = set(qs[-4:])
    util_rows = []
    for f in now:
        hist = [x["utilisation_pct"] for x in fac if x["facility_id"] == f["facility_id"] and x["reporting_quarter"] in last4]
        util_rows.append({"facility_id": f["facility_id"], "product": f["product_type"], "class": f["facility_class"],
                          "limit": f["limit_sar_mn"], "drawn": f["drawn_sar_mn"], "utilisation_pct": f["utilisation_pct"],
                          "avg_4q_pct": float(np.mean(hist)) if hist else None, "max_4q_pct": float(max(hist)) if hist else None,
                          "dpd_now": f["dpd_days"], "stage": f["stage"]})
    by_q = []
    for q in qs:
        fq = [f for f in fac if f["reporting_quarter"] == q]
        if fq:
            by_q.append({"quarter": q, "max_dpd": int(max(f["dpd_days"] or 0 for f in fq)),
                         "past_due_facilities": int(sum(1 for f in fq if f.get("past_due_flag") or (f["dpd_days"] or 0) > 0)),
                         "utilisation_pct": 100 * sum(f["drawn_sar_mn"] or 0 for f in fq) / max(1e-9, sum(f["limit_sar_mn"] or 0 for f in fq))})
    pd_quarters = [b for b in by_q if b["max_dpd"] > 0]
    out["utilisation"] = {"limits_sar_mn": limits, "drawn_sar_mn": drawn, "utilisation_pct": 100 * drawn / limits if limits else None,
                          "facilities": util_rows, "over_90_4q": [u["facility_id"] for u in util_rows if (u["avg_4q_pct"] or 0) > 90],
                          "excess_days_12m": int(sum(m.get("excess_days") or 0 for m in months[-12:])),
                          "peak_od_use_pct_12m": max((m.get("peak_od_use_pct") or 0 for m in months[-12:]), default=None)}
    out["past_dues"] = {"quarters": by_q, "quarters_past_due_8q": len(pd_quarters),
                        "max_dpd_8q": max((b["max_dpd"] for b in by_q), default=0),
                        "max_dpd_4q": max((b["max_dpd"] for b in by_q if b["quarter"] in last4), default=0),
                        "last_past_due": pd_quarters[-1]["quarter"] if pd_quarters else None}

    # ---- turnover and routing
    last12 = months[-12:]
    credit = float(sum(m.get("credit_turnover_sar_mn") or 0 for m in last12))
    prev12 = months[-24:-12]
    credit_prev = float(sum(m.get("credit_turnover_sar_mn") or 0 for m in prev12)) if len(prev12) == 12 else None
    out["turnover"] = {"credit_turnover_12m_sar_mn": credit if last12 else None, "credit_turnover_prev_12m_sar_mn": credit_prev,
                       "growth_pct": 100 * (credit / credit_prev - 1) if credit_prev else None,
                       "to_limits_x": credit / limits if limits and last12 else None,
                       "avg_balance_12m_sar_mn": float(np.mean([m.get("avg_balance_sar_mn") or 0 for m in last12])) if last12 else None,
                       "routing_required_x": d.get("routing_required_x"), "routing_actual_x": d.get("routing_actual_x"),
                       "routing_compliant": None if not d else bool(d.get("routing_compliant")),
                       "routing_achieved_pct": (100 * d["routing_actual_x"] / d["routing_required_x"])
                       if d.get("routing_required_x") else None,
                       "turnover_to_revenue": d.get("turnover_to_revenue"),
                       "months": [{"month": m["month"], "credit_turnover_sar_mn": m.get("credit_turnover_sar_mn"),
                                   "avg_balance_sar_mn": m.get("avg_balance_sar_mn"),
                                   "cheques_returned_count": m.get("cheques_returned_count") or 0} for m in months[-24:]]}

    # ---- returned cheques
    ret = [m for m in last12 if (m.get("cheques_returned_count") or 0) > 0]
    deposited = float(sum(m.get("cheques_deposited_count") or 0 for m in last12))
    count = int(sum(m.get("cheques_returned_count") or 0 for m in last12))
    out["returned_cheques"] = {"count_12m": count, "amount_12m_sar_mn": float(sum(m.get("cheques_returned_sar_mn") or 0 for m in last12)),
                               "months_with_returns": len(ret), "last_return": ret[-1]["month"] if ret else None,
                               "reasons": sorted({str(m.get("cheque_return_reason")) for m in ret if m.get("cheque_return_reason")}),
                               "rate_pct": d.get("returned_cheque_rate_pct") if d else (100 * count / deposited if deposited else None),
                               "dates": [{"month": m["month"], "count": m["cheques_returned_count"], "amount": m.get("cheques_returned_sar_mn"),
                                          "reason": m.get("cheque_return_reason")} for m in ret]}

    # ---- bureau trend
    bq = S.records(S.read("bureau_corp_quarter", None, borrower_id=oid, reporting_quarter=qs)) if oid else []
    bq.sort(key=lambda r: r["reporting_quarter"])
    out["source"].append(_src("bureau_corp_quarter", borrower_id=oid, reporting_quarter=[qs[0], qs[-1]]))
    ber = S.records(S.read("bureau_entity_report", None, entity_id=oid))
    if not ber:
        ber = S.records(S.read("bureau_entity_report", None, proposal_id=pid))
    out["source"].append(_src("bureau_entity_report", entity_id=oid, proposal_id=pid))
    exp = [r.get("external_exposure_sar_mn") for r in bq]
    enq = [r.get("enquiries_q") for r in bq]
    dpd = [r.get("external_dpd_days") or 0 for r in bq]
    es = _slope(exp)
    trend = "not available"
    if bq:
        worse = (max(dpd[-4:], default=0) > max(dpd[:-4], default=0) and max(dpd[-4:], default=0) >= 30) \
            or any(r.get("external_default_flag") for r in bq[-4:]) \
            or (len(enq) >= 8 and sum(enq[-4:]) >= 2 * max(1, sum(enq[:4])) and sum(enq[-4:]) >= 8)
        trend = "deteriorating" if worse else ("rising exposure" if es and es > 0 and exp[-1] and exp[0] and exp[-1] > 1.25 * exp[0]
                                               else "stable")
    entity = []
    for r in ber:
        entity.append({"entity": S.pick(r, "entity_name", "name", "entity_id"), "role": S.pick(r, "entity_role", "role"),
                       "outstanding_sar_mn": S.pick(r, "outstanding_sar_mn", "outstanding"), "overdue_sar_mn": S.pick(r, "overdue_sar_mn", "overdue"),
                       "returned_cheques": S.pick(r, "returned_cheques", "returned_cheques_count"), "score": S.pick(r, "score", "bureau_score"),
                       "court_cases": S.pick(r, "court_cases", "court_cases_count"), "report_date": S.pick(r, "report_date", "as_of_date"),
                       "provided": bool(S.pick(r, "provided_flag", "provided", default=True))})
    out["bureau"] = {"quarters": [{"quarter": r["reporting_quarter"], "external_exposure_sar_mn": r.get("external_exposure_sar_mn"),
                                   "external_dpd_days": r.get("external_dpd_days"), "enquiries": r.get("enquiries_q"),
                                   "default": bool(r.get("external_default_flag"))} for r in bq],
                     "trend": trend, "exposure_slope_per_q": es,
                     "max_external_dpd_4q": max(dpd[-4:], default=None) if bq else None,
                     "enquiries_4q": int(sum(x or 0 for x in enq[-4:])) if bq else None,
                     "entity_reports": entity}
    out["headline"] = _headline(out)
    return out


def _from_account_conduct(pid: str, p: dict[str, Any], oid: str, ac: list[dict[str, Any]], out: dict[str, Any]) -> dict[str, Any]:
    """Conduct of an R12 demo obligor: dd_account_conduct (monthly), dd_returned_cheque, dd_deal (account opened),
    dd_condition (routing undertaking), bureau_entity_report. Same shape as the book path; `source` keeps its six slots
    (accounts, months, routing, facilities, bureau by quarter, bureau per entity)."""
    ac.sort(key=lambda r: r["month"])
    reg = S.records(S.read("dd_deal", ["proposal_id", "account_opened_date"], proposal_id=pid))
    since = (reg[0].get("account_opened_date") if reg else None) or None
    rq = [r for r in S.records(S.read("dd_condition", None, proposal_id=pid))
          if str(r.get("trigger_metric") or "").startswith("routing") or r.get("kind") == "routing"]
    cheques = S.records(S.read("dd_returned_cheque", None, obligor_id=oid))
    out["source"] = [_src("dd_deal", proposal_id=pid), _src("dd_account_conduct", obligor_id=oid), _src("dd_condition", proposal_id=pid),
                     _src("dd_account_conduct", obligor_id=oid), _src("bureau_entity_report", proposal_id=pid),
                     _src("bureau_entity_report", proposal_id=pid), _src("dd_returned_cheque", obligor_id=oid)]
    out["relationship"] = {"since": since, "accounts": 1 if since else 0, "active": 1 if since else 0,
                           "years": (int(AS_OF[:4]) - int(str(since)[:4])) if since else None}
    last12, prev12 = ac[-12:], ac[-24:-12]
    lim = float(last12[-1].get("limits_mn") or 0) if last12 else 0.0
    used = float(last12[-1].get("utilised_mn") or 0) if last12 else 0.0
    util = [r.get("utilisation_pct") for r in ac[-12:] if r.get("utilisation_pct") is not None]
    avg4 = float(np.mean(util)) if util else None
    out["utilisation"] = {"limits_sar_mn": lim, "drawn_sar_mn": used, "utilisation_pct": 100 * used / lim if lim else None,
                          "facilities": [{"facility_id": "ALL", "product": "all limits", "class": "total", "limit": lim, "drawn": used,
                                          "utilisation_pct": last12[-1].get("utilisation_pct") if last12 else None,
                                          "avg_4q_pct": avg4, "max_4q_pct": max(util) if util else None,
                                          "dpd_now": last12[-1].get("past_due_days_max") if last12 else None, "stage": None}],
                          "over_90_4q": ["ALL"] if (avg4 or 0) > 90 else [], "excess_days_12m": 0, "peak_od_use_pct_12m": max(util) if util else None}
    by_q: dict[str, dict[str, Any]] = {}
    for r in ac[-24:]:
        y, m = int(r["month"][:4]), int(r["month"][5:7])
        q = f"{y}Q{(m - 1) // 3 + 1}"
        b = by_q.setdefault(q, {"quarter": q, "max_dpd": 0, "past_due_facilities": 0, "utilisation_pct": r.get("utilisation_pct")})
        b["max_dpd"] = max(b["max_dpd"], int(r.get("past_due_days_max") or 0))
        b["past_due_facilities"] += 1 if (r.get("past_due_days_max") or 0) > 0 else 0
    qs = sorted(by_q)[-8:]
    pdq = [by_q[q] for q in qs]
    bad = [b for b in pdq if b["max_dpd"] > 0]
    out["past_dues"] = {"quarters": pdq, "quarters_past_due_8q": len(bad), "max_dpd_8q": max((b["max_dpd"] for b in pdq), default=0),
                        "max_dpd_4q": max((b["max_dpd"] for b in pdq[-4:]), default=0), "last_past_due": bad[-1]["quarter"] if bad else None}
    credit = float(sum(r.get("credit_turnover_mn") or 0 for r in last12))
    credit_prev = float(sum(r.get("credit_turnover_mn") or 0 for r in prev12)) if len(prev12) == 12 else None
    routed = float(sum(r.get("routed_business_mn") or 0 for r in last12))
    rc_row = next((r for r in rq if r.get("trigger_threshold") is not None), None)
    req = float(rc_row["trigger_threshold"]) if rc_row else None
    unit = "%" if rc_row and "share" in str(rc_row.get("trigger_metric")) else "x"
    if rc_row and rc_row.get("measured_value") is not None:  # the condition's own measurement (dd_condition)
        act = float(rc_row["measured_value"])
    else:
        act = routed / lim if lim else None
    out["turnover"] = {"credit_turnover_12m_sar_mn": credit, "credit_turnover_prev_12m_sar_mn": credit_prev,
                       "growth_pct": 100 * (credit / credit_prev - 1) if credit_prev else None, "to_limits_x": credit / lim if lim else None,
                       "avg_balance_12m_sar_mn": float(np.mean([r.get("avg_balance_mn") or 0 for r in last12])) if last12 else None,
                       "routing_required_x": req, "routing_actual_x": act,
                       "routing_compliant": None if req is None or act is None else bool(act >= req - 1e-9),
                       "routing_achieved_pct": 100 * act / req if req and act is not None else None, "turnover_to_revenue": None,
                       "routed_business_12m_sar_mn": routed, "routing_unit": unit,
                       "routing_text": (rc_row or {}).get("text"), "routing_measured_at": (rc_row or {}).get("measured_at"),
                       "months": [{"month": r["month"], "credit_turnover_sar_mn": r.get("credit_turnover_mn"), "avg_balance_sar_mn": r.get("avg_balance_mn"),
                                   "cheques_returned_count": r.get("returned_cheques_n") or 0} for r in ac[-24:]]}
    months12 = {r["month"] for r in last12}
    ch12 = [c for c in cheques if str(c.get("return_date") or "")[:7] in months12] if cheques else []
    cnt = int(sum(r.get("returned_cheques_n") or 0 for r in last12))
    amt = float(sum(r.get("returned_cheques_mn") or 0 for r in last12))
    ret = [r for r in last12 if (r.get("returned_cheques_n") or 0) > 0]
    out["returned_cheques"] = {"count_12m": cnt, "amount_12m_sar_mn": amt, "months_with_returns": len(ret),
                               "last_return": ret[-1]["month"] if ret else None,
                               "reasons": sorted({str(c["reason"]).replace("_", " ") for c in ch12 if c.get("reason")}),
                               "rate_pct": None, "regularised": sum(1 for c in ch12 if c.get("regularised_flag")),
                               "dates": [{"month": str(c.get("return_date")), "count": 1, "amount": c.get("amount_mn"),
                                          "reason": str(c.get("reason") or "").replace("_", " ")} for c in sorted(ch12, key=lambda c: str(c.get("return_date")))]
                               or [{"month": r["month"], "count": r.get("returned_cheques_n"), "amount": r.get("returned_cheques_mn"), "reason": None} for r in ret]}
    ber = S.records(S.read("bureau_entity_report", None, proposal_id=pid))
    entity = [{"entity": r.get("entity_name") or r.get("entity_id"), "role": r.get("entity_kind"), "outstanding_sar_mn": r.get("outstanding_mn"),
               "overdue_sar_mn": r.get("overdue_mn"), "returned_cheques": r.get("returned_cheques_n"), "score": r.get("score"),
               "court_cases": r.get("court_cases_n"), "report_date": r.get("report_date"), "provided": bool(r.get("provided_flag")),
               "not_provided_reason": r.get("not_provided_reason"), "worst_status": r.get("worst_status")} for r in ber]
    subj = [r for r in ber if r.get("entity_id") == oid]
    od = max((r.get("overdue_days_max") or 0 for r in subj), default=None) if subj else None
    worse = any((r.get("overdue_days_max") or 0) >= 30 for r in subj)  # court cases are their own flag
    out["bureau"] = {"quarters": [], "trend": ("deteriorating" if worse else "stable") if subj else "not available",
                     "exposure_slope_per_q": None, "max_external_dpd_4q": od, "enquiries_4q": None, "entity_reports": entity,
                     "not_provided": [e["entity"] for e in entity if not e["provided"]]}
    out["headline"] = _headline(out)
    return out


def _headline(c: dict[str, Any]) -> str:
    """One sentence in the proposal voice: every clause a number and a date."""
    parts = []
    r = c["relationship"]
    if r.get("since"):
        parts.append(f"Relationship since {r['since']} ({r['accounts']} account{'s' if r['accounts'] != 1 else ''})")
    t = c["turnover"]
    if t.get("credit_turnover_12m_sar_mn") is not None:
        s = f"credit turnover SAR {t['credit_turnover_12m_sar_mn']:,.1f}m in the 12 months to {AS_OF}"
        if t.get("credit_turnover_prev_12m_sar_mn"):
            s += f" (PY SAR {t['credit_turnover_prev_12m_sar_mn']:,.1f}m)"
        if t.get("to_limits_x") is not None:
            s += f", {t['to_limits_x']:.2f}x the limits of SAR {c['utilisation']['limits_sar_mn']:,.1f}m"
        parts.append(s)
    if t.get("routing_required_x"):
        if t.get("routing_unit") == "%":
            parts.append(f"routing undertaking {t['routing_required_x']:.0f}% of receipts, {t['routing_actual_x']:.0f}% routed")
        else:
            parts.append(f"routing undertaking {t['routing_required_x']:.1f}x the limits, {t['routing_achieved_pct']:.0f}% achieved")
    rc = c["returned_cheques"]
    if c["relationship"].get("accounts"):
        parts.append(f"{rc['count_12m']} returned cheque{'s' if rc['count_12m'] != 1 else ''} (SAR {rc['amount_12m_sar_mn']:,.2f}m) in 12 months")
    u = c["utilisation"]
    if u.get("utilisation_pct") is not None:
        parts.append(f"utilisation {u['utilisation_pct']:.0f}% of limits")
    pdq = c["past_dues"]
    if pdq["quarters"]:
        parts.append(f"past dues in {pdq['quarters_past_due_8q']} of the last {len(pdq['quarters'])} quarters (max {pdq['max_dpd_8q']} days)")
    b = c["bureau"]
    if b["quarters"]:
        parts.append(f"bureau trend {b['trend']}")
    if not parts:
        return "New to bank: no account history; conduct cannot be assessed from the bank's own records."
    s = "; ".join(parts)
    return s[0].upper() + s[1:] + "."
