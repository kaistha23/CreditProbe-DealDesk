"""D11 Renewal diff: for a renewal, what changed since the last approval, in one table.

Method (deterministic)
  * Last approval: the latest committee decision on file (dd_reference kind committee_decision) for the R12 deals; for
    book borrowers the latest credit decision in the governance history (gov_decision, fictional seed); else the
    annual review a year before the book quarter (stated).
  * Then vs now, each row with its source row:
      limits         approved amount (dd_reference / gov_decision) vs proposed (dd_deal.proposed_limits_mn)
      rating         rating at the approval (gov_decision / book quarter; R12: dd_deal.rating_existing) vs proposed /
                     current (dd_deal.rating_proposed / corp_borrower_quarter)
      financials     revenue, EBITDA, Debt/EBITDA, DSCR (book: corp_borrower_quarter at the approval quarter vs now;
                     R12: the last audited year before the approval vs the latest audited year, dd_financials_detail)
      conduct        monthly credit turnover, utilisation, returned cheques, worst days past due: the 12 months before
                     the approval vs the months since (dd_account_conduct; book: dep_month and corp_facility_quarter)
      conditions     conditions set by that approval: met, not complied, breached (dd_condition prior_committee_ref;
                     book: gov_decision counts)
      covenants      covenant tests breached or waived since the approval (corp_covenant_quarter; R12: dd_condition)
      group          group exposure and cap (dd_reference group cap vs dd_deal group exposure), connected parties now in
                     Stage 3, litigation or arrears (D12)
  * Direction: better / worse / same by the item's sense (e.g. leverage up = worse); a change counts when it is at
    least 5% (ratios 0.1x, one notch, one event).
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk.intel2 import common as C

QUARTER = "2026Q2"
RENEWAL = ("renewal", "renewal_and_new")


def _q_of(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def _dir(then: float | None, now: float | None, good_up: bool, tol: float) -> str:
    if then is None or now is None:
        return "n/a"
    d = now - then
    if abs(d) < tol:
        return "same"
    return "better" if (d > 0) == good_up else "worse"


def _row(area: str, item: str, then: Any, now: Any, unit: str, direction: str, ev: list[dict[str, Any] | None], note: str = "") -> dict[str, Any]:
    def s(v: Any) -> str:
        if v is None:
            return "n/a"
        if unit == "SAR m" and isinstance(v, (int, float)):
            return f"SAR {v:,.1f}m"
        if isinstance(v, float):
            return f"{v:,.2f}{unit}" if unit in ("x",) else f"{v:,.1f}{(' ' + unit) if unit and unit not in ('%',) else unit}"
        return f"{v}{(' ' + unit) if unit and isinstance(v, int) and unit not in ('%',) else ''}"
    ch = ""
    if isinstance(then, (int, float)) and isinstance(now, (int, float)) and not isinstance(then, bool):
        d = now - then
        ch = (f"{d:+,.2f}{unit}" if unit == "x" else f"{'+' if d >= 0 else '-'}SAR {abs(d):,.1f}m" if unit == "SAR m" else
              f"{d:+,.1f} pp" if unit == "%" else f"{d:+,.1f}{(' ' + unit) if unit else ''}") if isinstance(d, float) else f"{d:+d}"
        if then and unit not in ("x", "%", "notches") and isinstance(then, float):
            ch += f" ({d / then * 100:+.0f}%)"
    if area in ("Conditions", "Group") and not ch:
        ch = {"worse": "worse", "better": "better", "same": "no change"}.get(direction, "")
    return {"area": area, "item": item, "then": s(then), "now": s(now), "change": ch or ("changed" if then != now else "same"),
            "direction": direction, "evidence": [e for e in ev if e], "note": note}


def _rank(r: str | None) -> int | None:
    from backend.v5common.ratings import rank
    try:
        return rank(r) if r else None
    except Exception:  # noqa: BLE001
        return None


def _rating_row(then: str | None, now: str | None, ev: list[dict[str, Any] | None]) -> dict[str, Any]:
    a, b = _rank(then), _rank(now)
    d = "n/a" if a is None or b is None else "same" if a == b else "better" if b < a else "worse"
    r = _row("Rating", "Internal rating", then, now, "", d, ev)
    if a is not None and b is not None and a != b:
        r["change"] = f"{abs(b - a)} notch{'es' if abs(b - a) != 1 else ''} {'down' if b > a else 'up'}"
    return r


def _book(pid: str, p: dict[str, Any], reg: dict[str, Any], ob: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    g = C.records(C.frame("gov_decision", borrower_id=ob))
    g = sorted(g, key=lambda r: r["decided_on"])
    if g:
        last = g[-1]
        q0, when = last["decision_quarter"], last["decided_on"]
        approval = {"ref": last["decision_id"], "date": when, "authority": last["required_level"], "quarter": q0,
                    "basis": "governance history (gov_decision, fictional seed)",
                    "amount": C.bfig("gov_decision", last, "limit_sar_mn", "SAR m", "Limits approved")}
    else:
        last, q0, when = None, "2025Q2", "2025-06-30"
        approval = {"ref": "annual review", "date": when, "authority": "", "quarter": q0, "basis": "no decision on file: the annual review a year ago"}
    b = {r["reporting_quarter"]: r for r in C.records(C.frame("corp_borrower_quarter", borrower_id=ob))}
    b0, b1 = b.get(q0), b.get(QUARTER)
    rows = []
    if last:
        rows.append(_row("Limits", "Total limits", C.finite(last["limit_sar_mn"]), C.finite(reg.get("proposed_limits_mn")), "SAR m",
                         "n/a", [approval["amount"], C.rfig("dd_deal", reg, "proposed_limits_mn", "SAR m", "Proposed limits")]))
    if b0 and b1:
        rows.append(_rating_row(b0["rating_current"], b1["rating_current"], [C.bfig("corp_borrower_quarter", b0, "rating_current"),
                                                                           C.bfig("corp_borrower_quarter", b1, "rating_current")]))
        for col, lab, unit, up, tol in (("revenue_sar_mn", "Revenue (annualised)", "SAR m", True, None), ("ebitda_sar_mn", "EBITDA", "SAR m", True, None),
                                        ("leverage_x", "Debt / EBITDA", "x", False, 0.1), ("dscr_x", "DSCR", "x", True, 0.1),
                                        ("current_ratio_x", "Current ratio", "x", True, 0.1)):
            t0, t1 = C.finite(b0.get(col)), C.finite(b1.get(col))
            tl = tol if tol is not None else (abs(t0) * 0.05 if t0 else 0.01)
            rows.append(_row("Financials", lab, t0, t1, unit, _dir(t0, t1, up, tl),
                             [C.bfig("corp_borrower_quarter", b0, col, unit), C.bfig("corp_borrower_quarter", b1, col, unit)]))
        w0, w1 = int(b0.get("watchlist_flag") or 0), int(b1.get("watchlist_flag") or 0)
        rows.append(_row("Rating", "Watchlist", "yes" if w0 else "no", "yes" if w1 else "no", "", "same" if w0 == w1 else ("worse" if w1 else "better"),
                         [C.bfig("corp_borrower_quarter", b1, "watchlist_flag")]))
    dm = C.frame("dep_month", obligor_id=ob)
    if len(dm):
        dm = dm.sort_values("month")
        m0 = when[:7]
        pre, post = dm[dm["month"] <= m0].tail(12), dm[dm["month"] > m0].tail(12)
        if len(pre) and len(post):
            a0, a1 = float(pre["credit_turnover_sar_mn"].mean()), float(post["credit_turnover_sar_mn"].mean())
            r0 = C.records(post.tail(1))[0]
            rows.append(_row("Conduct", "Monthly credit turnover (avg)", round(a0, 2), round(a1, 2), "SAR m", _dir(a0, a1, True, a0 * 0.05),
                             [C.bfig("dep_month", r0, "credit_turnover_sar_mn", "SAR m")], f"12 months before the approval vs the last {len(post)} months"))
            c0, c1 = int(pre["cheques_returned_count"].sum()), int(post["cheques_returned_count"].sum())
            rows.append(_row("Conduct", "Returned cheques", c0, c1, "", _dir(c0, c1, False, 1), [C.bfig("dep_month", r0, "cheques_returned_count")]))
    fq = C.records(C.frame("corp_facility_quarter", borrower_id=ob))
    f0 = [r for r in fq if r["reporting_quarter"] == q0]
    f1 = [r for r in fq if r["reporting_quarter"] == QUARTER]
    if f0 and f1:
        s0, s1 = max(int(r["stage"]) for r in f0), max(int(r["stage"]) for r in f1)
        rows.append(_row("Conduct", "Worst stage", s0, s1, "", _dir(s0, s1, False, 1), [C.bfig("corp_facility_quarter", f1[0], "stage")]))
        d0, d1 = max(int(r["dpd_days"] or 0) for r in f0), max(int(r["dpd_days"] or 0) for r in f1)
        rows.append(_row("Conduct", "Worst days past due", d0, d1, "days", _dir(d0, d1, False, 1), [C.bfig("corp_facility_quarter", f1[0], "dpd_days")]))
    cv = C.records(C.frame("corp_covenant_quarter", borrower_id=ob))
    since = [r for r in cv if r["reporting_quarter"] > q0]
    if since:
        br = sum(int(r["breach_flag"] or 0) for r in since)
        wv = sum(int(r["waiver_flag"] or 0) for r in since)
        rows.append(_row("Covenants", "Covenant tests breached since approval", 0, br, "", "same" if not br else "worse",
                         [C.bfig("corp_covenant_quarter", since[-1], "breach_flag")], f"{len(since)} tests; {wv} waived"))
    if last:
        rows.append(_row("Conditions", "Conditions set at the approval", None, f"{last['conditions_met']} met, {last['conditions_breached']} breached of {last['conditions_set']}",
                         "", "worse" if last["conditions_breached"] else "same", [C.bfig("gov_decision", last, "conditions_breached")]))
    return approval, rows


def _r12(pid: str, p: dict[str, Any], reg: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    refs = sorted([r for r in C.rows("dd_reference", proposal_id=pid) if r["kind"] == "committee_decision"], key=lambda r: r["ref_date"])
    if not refs:
        return None, []
    last = refs[-1]
    when = last["ref_date"]
    approval = {"ref": last["ref_no"], "date": when, "authority": last.get("authority"), "quarter": _q_of(when), "basis": "dd_reference committee decision",
                "text": last["text"], "amount": C.rfig("dd_reference", last, "amount_mn", "SAR m", "Limits approved")}
    rows = [_row("Limits", "Total limits", C.finite(last["amount_mn"]), C.finite(reg.get("proposed_limits_mn")), "SAR m", "n/a",
                 [approval["amount"], C.rfig("dd_deal", reg, "proposed_limits_mn", "SAR m", "Proposed limits")])]
    if last.get("group_cap_mn") is not None and reg.get("group_exposure_mn") is not None:
        rows.append(_row("Group", "Group exposure vs approved cap", C.finite(last["group_cap_mn"]), C.finite(reg["group_exposure_mn"]), "SAR m",
                         "worse" if float(reg["group_exposure_mn"]) > float(last["group_cap_mn"]) else "same",
                         [C.rfig("dd_reference", last, "group_cap_mn", "SAR m"), C.rfig("dd_deal", reg, "group_exposure_mn", "SAR m")],
                         "then = cap approved; now = group exposure after the proposal"))
    rows.append(_rating_row(reg.get("rating_existing"), reg.get("rating_proposed"), [C.rfig("dd_deal", reg, "rating_existing"), C.rfig("dd_deal", reg, "rating_proposed")]))
    fd = sorted([r for r in C.rows("dd_financials_detail", proposal_id=pid) if r.get("entity_scope") == "standalone" and r.get("period_kind") == "audited"],
                key=lambda r: r["period_end"])
    before = [r for r in fd if r["period_end"] < when]
    if before and fd and fd[-1] is not before[-1]:
        f0, f1 = before[-1], fd[-1]

        def lev(r: dict[str, Any]) -> float | None:
            d = (C.finite(r.get("bank_debt_st_mn")) or 0) + (C.finite(r.get("bank_debt_lt_mn")) or 0)
            e = C.finite(r.get("ebitda_mn"))
            return round(d / e, 2) if e else None

        def cr(r: dict[str, Any]) -> float | None:
            a, b = C.finite(r.get("current_assets_mn")), C.finite(r.get("current_liabilities_mn"))
            return round(a / b, 2) if a and b else None
        lab = f"{f0['period_label']} vs {f1['period_label']}"
        for col, name, up in (("revenue_mn", "Revenue", True), ("ebitda_mn", "EBITDA", True), ("net_profit_mn", "Net profit", True),
                              ("net_worth_mn", "Net worth", True), ("due_from_related_mn", "Due from related parties", False)):
            t0, t1 = C.finite(f0.get(col)), C.finite(f1.get(col))
            rows.append(_row("Financials", name, t0, t1, "SAR m", _dir(t0, t1, up, abs(t0 or 0) * 0.05 or 0.01),
                             [C.rfig("dd_financials_detail", f0, col, "SAR m"), C.rfig("dd_financials_detail", f1, col, "SAR m")], lab))
        l0, l1 = lev(f0), lev(f1)
        rows.append(_row("Financials", "Bank debt / EBITDA", l0, l1, "x", _dir(l0, l1, False, 0.1),
                         [C.rfig("dd_financials_detail", f1, "ebitda_mn", "SAR m")], lab))
        c0, c1 = cr(f0), cr(f1)
        rows.append(_row("Financials", "Current ratio", c0, c1, "x", _dir(c0, c1, True, 0.1), [C.rfig("dd_financials_detail", f1, "current_assets_mn", "SAR m")], lab))
        if f0.get("opinion") != f1.get("opinion"):
            rows.append(_row("Financials", "Audit opinion", f0.get("opinion"), f1.get("opinion"), "",
                             "worse" if f1.get("opinion") in ("qualified", "adverse", "disclaimer") else "better",
                             [C.rfig("dd_financials_detail", f1, "opinion")], f"{f1.get('qualification_basis') or ''}"[:140]))
        if f0.get("auditor") != f1.get("auditor"):
            rows.append(_row("Financials", "Auditor", f0.get("auditor"), f1.get("auditor"), "", "worse" if f1.get("auditor_panel") == "unlisted" else "same",
                             [C.rfig("dd_financials_detail", f1, "auditor")], f"panel: {f1.get('auditor_panel')}"))
    ac = sorted(C.rows("dd_account_conduct", proposal_id=pid), key=lambda r: r["month"])
    m0 = when[:7]
    pre, post = [r for r in ac if r["month"] <= m0][-12:], [r for r in ac if r["month"] > m0][-12:]
    if pre and post:
        def avg(rs: list[dict[str, Any]], k: str) -> float:
            return round(sum(float(r[k] or 0) for r in rs) / len(rs), 2)
        note = f"12 months to {m0} vs {len(post)} months since"
        for k, name, unit, up, tol in (("credit_turnover_mn", "Monthly credit turnover (avg)", "SAR m", True, None),
                                       ("utilisation_pct", "Limit utilisation (avg)", "%", False, 5.0),
                                       ("routed_business_mn", "Business routed through us (monthly avg)", "SAR m", True, None)):
            a0, a1 = avg(pre, k), avg(post, k)
            rows.append(_row("Conduct", name, a0, a1, unit, _dir(a0, a1, up, tol if tol is not None else abs(a0) * 0.05 or 0.01),
                             [C.rfig("dd_account_conduct", post[-1], k, unit)], note))
        c0, c1 = sum(int(r["returned_cheques_n"] or 0) for r in pre), sum(int(r["returned_cheques_n"] or 0) for r in post)
        rows.append(_row("Conduct", "Returned cheques", c0, c1, "", _dir(c0, c1, False, 1), [C.rfig("dd_account_conduct", post[-1], "returned_cheques_n")], note))
        d0, d1 = max(int(r["past_due_days_max"] or 0) for r in pre), max(int(r["past_due_days_max"] or 0) for r in post)
        rows.append(_row("Conduct", "Worst days past due", d0, d1, "days", _dir(d0, d1, False, 1), [C.rfig("dd_account_conduct", post[-1], "past_due_days_max")], note))
    conds = [c for c in C.rows("dd_condition", proposal_id=pid) if c.get("prior_committee_ref") == last["ref_no"]]
    for c in conds:
        st = c.get("status") or "open"
        mv, th = c.get("measured_value"), c.get("trigger_threshold")
        rows.append(_row("Conditions", c["text"][:90] + ("…" if len(c["text"]) > 90 else ""), "set", st.replace("_", " ")
                         + (f" ({mv} vs {th})" if mv is not None and th is not None else ""), "",
                         "worse" if st in ("not_complied", "breached") else "same" if st == "met" else "n/a",
                         [C.rfig("dd_condition", c, "measured_value") if isinstance(mv, (int, float)) else
                          {"value": None, "source": C.row_source("dd_condition", c, "status")}]))
    return approval, rows


def _short(r: dict[str, Any]) -> str:
    if r["area"] == "Conditions":
        return f"condition {r['now']}: {r['item'][:50].rstrip('.…')}"
    if r["area"] == "Group" and r["then"] == "n/a":
        return f"{r['item'].lower()}: {r['now']}"
    return f"{r['item'][:1].lower() + r['item'][1:]} {r['then']} to {r['now']}"


@functools.lru_cache(maxsize=64)
def _diff(pid: str, pv: str) -> str:
    p = C.proposal(pid)
    reg = C.C.register_row(pid)
    case = reg.get("case_type") or "new"
    ob = reg.get("obligor_id") or ""
    if case not in RENEWAL:
        out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "case_type": case, "applies": False,
               "headline": f"{p['obligor']['name']} is a {case.replace('_', ' ')} case: there is no earlier approval to compare with.",
               "plain": C.plain("This shows what changed since the bank last approved this client.", "This is not a renewal: 0 earlier approvals to compare with.",
                                "Use the Review step for a new client."), "rows": [], "approval": None}
        return json.dumps(out, default=str)
    approval, rows = _r12(pid, p, reg)
    if approval is None and str(ob).startswith("CB"):
        approval, rows = _book(pid, p, reg, ob)
    try:
        from backend.dealdesk.intel2 import contagion
        g = contagion.contagion(pid, "ask")
        adv = [x for x in g["parties"] if x["adverse"]]
        if adv:
            rows.append(_row("Group", "Connected parties in Stage 3, litigation or arrears", None, ", ".join(f"{x['name']} ({x['status']})" for x in adv), "",
                             "worse", [x["exposure"] for x in adv[:3]], "today (D12); not on file at the approval"))
    except Exception:  # noqa: BLE001
        pass
    worse = [r for r in rows if r["direction"] == "worse"]
    better = [r for r in rows if r["direction"] == "better"]
    when = (approval or {}).get("date", "")
    head = (f"Since the last approval ({(approval or {}).get('ref', '')}, {when}) {len(worse)} thing{'s' if len(worse) != 1 else ''} got worse and {len(better)} better"
            + (": " + "; ".join(_short(r) for r in worse[:4]) if worse else "") + ".")
    top = worse[0] if worse else None
    pl = C.plain("This shows what changed since the bank last approved this client.",
                 f"{len(worse)} thing{'s' if len(worse) != 1 else ''} got worse and {len(better)} better since {when}" + (f"; first: {_short(top)[:90]}." if top else "."),
                 ("Explain each worse line in the renewal paper, or tighten the terms." if worse else "Nothing material got worse; a light renewal note is enough."))
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "case_type": case, "applies": True, "approval": approval, "headline": head,
           "plain": pl, "rows": rows, "counts": {"worse": len(worse), "better": len(better), "rows": len(rows)},
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def renewal_diff(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_diff(pid, C.cache_key()))
