"""R14 session p: the bank's own book for a deal whose R12 deal-file relations are thin (SIB_GAP_AUDIT A8: DD-06 and the other
book obligors). When the obligor is a book borrower (dd_deal / dd_proposal book_obligor_id), the sections whose R12 relation is
empty are completed from the registered book relations, through the papers' source door (lineage on every row):

    corp_borrower_quarter (rating, ratios, financials by quarter), corp_facility_quarter (limits, drawn, stage, DPD, ECL),
    corp_collateral_quarter (collateral, haircut, coverage, valuation age), corp_covenant_quarter (covenant tests),
    bureau_corp_quarter (external exposure, DPD, defaults, enquiries), openbanking_corp_quarter (other banks' inflows,
    returned payments), rel_edge_quarter (suppliers, customers, guarantees).

    augment(key, writer) -> writer      wraps a section writer: R12 text first, then "From the bank's book" blocks when the R12
                                        section had a data gap and the book has rows
"""
from __future__ import annotations

from typing import Any, Callable

from backend.dealdesk.house_style.bankform import source as S
from backend.dealdesk.house_style.bankform.blocks import H, P, T
from backend.dealdesk.house_style.bankform.ctx import Deal, num

Out = tuple[list[dict[str, Any]], list[str]]
N_Q = 8


def _bid(D: Deal) -> str | None:
    b = D.get("book_obligor_id", default=None)
    if b:
        return str(b)
    oid = str(D.get("obligor_id", default="") or "")
    return oid if oid.startswith("CB") else None


def load(D: Deal) -> dict[str, list[dict[str, Any]]]:
    if getattr(D, "_book", None) is not None:
        return D._book  # type: ignore[attr-defined]
    bid = _bid(D)
    out: dict[str, list[dict[str, Any]]] = {}
    if bid:
        for rel in ("corp_borrower_quarter", "corp_facility_quarter", "corp_collateral_quarter", "corp_covenant_quarter", "bureau_corp_quarter",
                    "openbanking_corp_quarter"):
            out[rel] = sorted(S.read(rel, borrower_id=bid), key=lambda r: str(r.get("reporting_quarter")))
        last = out["corp_borrower_quarter"][-1]["reporting_quarter"] if out.get("corp_borrower_quarter") else None
        if last:
            out["edges_out"] = S.read("rel_edge_quarter", source_borrower_id=bid, reporting_quarter=last)
            out["edges_in"] = S.read("rel_edge_quarter", target_borrower_id=bid, reporting_quarter=last)
            gid = out["corp_borrower_quarter"][-1].get("group_id")
            out["group"] = S.read("corp_borrower_quarter", group_id=gid, reporting_quarter=last) if gid else []
            members = [str(r.get("borrower_id")) for r in out["group"]]
            out["group_fac"] = S.read("corp_facility_quarter", borrower_id=members, reporting_quarter=last) if members else []
    D._book = out  # type: ignore[attr-defined]
    return out


def _last(rows: list[dict[str, Any]], n: int = N_Q) -> list[dict[str, Any]]:
    return rows[-n:]


def _latest_q(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    q = max(str(r.get("reporting_quarter")) for r in rows)
    return [r for r in rows if str(r.get("reporting_quarter")) == q]


def _m(x: Any, dp: int = 1) -> str:
    v = num(x)
    return "–" if v is None else f"{v:,.{dp}f}"


def _src(rel: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return rel
    qs = sorted({str(r.get("reporting_quarter")) for r in rows})
    return f"Data Domains · {rel} · {len(rows)} rows · {qs[0]}–{qs[-1]}" if len(qs) > 1 else f"Data Domains · {rel} · {len(rows)} rows · {qs[0]}"


def b_relationship(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    bq = _last(B.get("corp_borrower_quarter") or [])
    if bq:
        out += [H("Rating and watch-list history (bank's book)"),
                T(["Quarter", "Rating", "PD TTC 12m", "Outlook", "Watch list", "Leverage", "DSCR", "Current ratio"],
                  [[r.get("reporting_quarter"), r.get("rating_current"), f"{(num(r.get('pd_ttc_12m')) or 0) * 100:.2f}%", r.get("rating_outlook"),
                    "Yes" if int(num(r.get("watchlist_flag")) or 0) else "No", f"{_m(r.get('leverage_x'), 2)}x", f"{_m(r.get('dscr_x'), 2)}x",
                    f"{_m(r.get('current_ratio_x'), 2)}x"] for r in bq], source=_src("corp_borrower_quarter", bq), widths=[1.6, 1.3, 1.8, 1.6, 1.5, 1.6, 1.4, 1.8], size=7.0)]
        first, last = bq[0], bq[-1]
        out.append(P(f"Rating {last.get('rating_current')} in {last.get('reporting_quarter')} (PY {first.get('rating_current')} in {first.get('reporting_quarter')}), "
                     f"{int(num(last.get('rating_notches_from_origination')) or 0)} notch(es) from origination; watch list {'on' if int(num(last.get('watchlist_flag')) or 0) else 'off'} "
                     f"as per corp_borrower_quarter."))
    fac = _latest_q(B.get("corp_facility_quarter") or [])
    if fac:
        out += [H("Facilities in the bank's book"),
                T(["Facility", "Product", "Class", "Limit", "Drawn", "Utilisation", "Stage", "DPD", "ECL", "Since"],
                  [[r.get("facility_id"), str(r.get("product_type") or "").replace("_", " "), r.get("facility_class"), _m(r.get("limit_sar_mn")), _m(r.get("drawn_sar_mn")),
                    f"{_m(r.get('utilisation_pct'))}%", r.get("stage"), r.get("dpd_days"), _m(r.get("ecl_sar_mn"), 3), r.get("origination_quarter")] for r in fac],
                  source=_src("corp_facility_quarter", fac), widths=[1.9, 2.2, 1.4, 1.3, 1.3, 1.6, 1.0, 1.0, 1.3, 1.5], size=7.0)]
        lim = sum(num(r.get("limit_sar_mn")) or 0 for r in fac)
        dr = sum(num(r.get("drawn_sar_mn")) or 0 for r in fac)
        out.append(P(f"{len(fac)} facilities with limits of {D.money(lim)} and {D.money(dr)} drawn ({dr / lim * 100 if lim else 0:,.1f}% utilised) in "
                     f"{fac[0].get('reporting_quarter')}; worst DPD {max(int(num(r.get('dpd_days')) or 0) for r in fac)} days, as per corp_facility_quarter."))
    return out


def b_security(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    col = _latest_q(B.get("corp_collateral_quarter") or [])
    if not col:
        return []
    rows = []
    for r in col:
        age = int(num(r.get("valuation_age_quarters")) or 0)
        rows.append([r.get("collateral_id"), r.get("facility_id"), r.get("collateral_type"), _m(r.get("market_value_sar_mn")), f"{_m(r.get('haircut_pct'), 0)}%",
                     _m(r.get("allocated_value_sar_mn")), f"{_m(r.get('coverage_pct'))}%", f"{_m(r.get('ltv_pct'))}%",
                     (f"__{age} quarters__" if age > 4 else f"{age} quarters")])
    old = [r for r in col if int(num(r.get("valuation_age_quarters")) or 0) > 4]
    out = [H("Collateral held in the bank's book"),
           T(["Collateral", "Facility", "Type", "Market value", "Haircut", "Allocated", "Coverage", "LTV", "Valuation age"], rows,
             source=_src("corp_collateral_quarter", col), widths=[1.9, 1.9, 2.6, 1.6, 1.3, 1.5, 1.4, 1.3, 1.8], size=7.0)]
    cov = sum(num(r.get("allocated_value_sar_mn")) or 0 for r in col)
    out.append(P(f"Allocated collateral value of {D.money(cov)} after haircuts in {col[0].get('reporting_quarter')}"
                 + (f"; __{len(old)} valuation(s) older than 4 quarters__" if old else "; every valuation within 4 quarters") + ", as per corp_collateral_quarter."))
    return out


def b_terms(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    cv = _latest_q(B.get("corp_covenant_quarter") or [])
    if not cv:
        return []
    rows = [[r.get("covenant_id"), r.get("facility_id"), r.get("covenant_type"), _m(r.get("threshold_value"), 2), _m(r.get("observed_value"), 2),
             f"{_m(r.get('headroom_pct'))}%", ("__" + str(r.get("test_status")) + "__") if str(r.get("test_status")) != "PASS" else r.get("test_status"),
             r.get("consecutive_breaches"), r.get("waiver_status")] for r in cv]
    out = [H("Existing covenants tested in the bank's book"),
           T(["Covenant", "Facility", "Type", "Threshold", "Observed", "Headroom", "Test", "Breaches in a row", "Waiver"], rows,
             source=_src("corp_covenant_quarter", cv), widths=[1.9, 1.9, 2.2, 1.4, 1.4, 1.4, 1.2, 1.6, 1.4], size=7.0)]
    br = [r for r in cv if int(num(r.get("breach_flag")) or 0)]
    low = min(cv, key=lambda r: num(r.get("headroom_pct")) or 0)
    out.append(P(f"{len(br)} of {len(cv)} covenant tests breached in {cv[0].get('reporting_quarter')}; the tightest is {low.get('covenant_type')} with "
                 f"{_m(low.get('headroom_pct'))}% headroom, as per corp_covenant_quarter."))
    return out


def b_group(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    g, gf = B.get("group") or [], B.get("group_fac") or []
    if not g:
        return []
    by: dict[str, list[dict[str, Any]]] = {}
    for f in gf:
        by.setdefault(str(f.get("borrower_id")), []).append(f)
    rows, tl, td = [], 0.0, 0.0
    for m in g:
        fs = by.get(str(m.get("borrower_id")), [])
        lim, dr = sum(num(f.get("limit_sar_mn")) or 0 for f in fs), sum(num(f.get("drawn_sar_mn")) or 0 for f in fs)
        tl, td = tl + lim, td + dr
        rows.append([m.get("borrower_name"), m.get("borrower_id"), m.get("rating_current"), len(fs), _m(lim), _m(dr), max((int(num(f.get("stage")) or 1) for f in fs), default="–")])
    rows.append(["**Total group**", "", "", sum(len(v) for v in by.values()), _m(tl), _m(td), ""])
    return [H("Group exposure in the bank's book"),
            T(["Group member", "Borrower", "Rating", "Facilities", "Limits", "Drawn", "Worst stage"], rows, source=_src("corp_facility_quarter", gf),
              widths=[5.0, 1.8, 1.3, 1.3, 1.5, 1.5, 1.5], size=7.2),
            P(f"Group {g[0].get('group_name')}: {len(g)} member(s) with limits of {D.money(tl)} and {D.money(td)} drawn in {g[0].get('reporting_quarter')}; "
              f"this request adds {D.money(D.get('amount'))} of new limit, taking group limits to {D.money(tl + (num(D.get('amount')) or 0))}, as per corp_facility_quarter.")]


def b_background(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    eo, ei = B.get("edges_out") or [], B.get("edges_in") or []
    sup = [e for e in ei if e.get("rel_type") == "SUPPLIES"]
    cus = [e for e in eo if e.get("rel_type") == "SUPPLIES"]
    gua = [e for e in eo + ei if e.get("rel_type") == "GUARANTEES"]
    if not (sup or cus or gua):
        return []
    names = {}
    ids = {str(e.get("source_borrower_id")) for e in ei} | {str(e.get("target_borrower_id")) for e in eo}
    if ids:
        for r in S.read("corp_borrower_quarter", borrower_id=sorted(ids), reporting_quarter=(B.get("corp_borrower_quarter") or [{}])[-1].get("reporting_quarter")):
            names[str(r.get("borrower_id"))] = r.get("borrower_name")
    rows = []
    for e in sorted(sup, key=lambda e: -(num(e.get("purchase_share_pct")) or 0)):
        rows.append(["Supplier", names.get(str(e.get("source_borrower_id")), e.get("source_borrower_id")), f"{_m(e.get('purchase_share_pct'))}% of purchases",
                     _m(e.get("annual_value_sar_mn"), 2)])
    for e in sorted(cus, key=lambda e: -(num(e.get("revenue_share_pct")) or 0)):
        rows.append(["Customer", names.get(str(e.get("target_borrower_id")), e.get("target_borrower_id")), f"{_m(e.get('revenue_share_pct'))}% of revenue",
                     _m(e.get("annual_value_sar_mn"), 2)])
    for e in gua:
        other = e.get("target_borrower_id") if str(e.get("source_borrower_id")) == _bid(D) else e.get("source_borrower_id")
        rows.append(["Guarantee " + ("given" if str(e.get("source_borrower_id")) == _bid(D) else "received"), names.get(str(other), other),
                     f"{e.get('facility_id')}", _m(e.get("guarantee_amount_sar_mn"), 2)])
    top = max(sup, key=lambda e: num(e.get("purchase_share_pct")) or 0) if sup else None
    out = [H("Counterparties in the bank's book (Borrower 360)"),
           T(["Link", "Counterparty", "Share / facility", "Annual value or amount (SAR m)"], rows, source=_src("rel_edge_quarter", eo + ei), widths=[2.6, 6.4, 3.8, 3.4], size=7.2)]
    if top:
        out.append(P(f"Top supplier {names.get(str(top.get('source_borrower_id')), top.get('source_borrower_id'))} carries {_m(top.get('purchase_share_pct'))}% of purchases "
                     f"in {top.get('reporting_quarter')}" + (" (__single-supplier concentration above 50%__)" if (num(top.get("purchase_share_pct")) or 0) > 50 else "")
                     + ", as per rel_edge_quarter."))
    return out


def b_cbrbr(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    bq = _last(B.get("bureau_corp_quarter") or [])
    if not bq:
        return []
    out = [H("External exposure reported by the bureau feed (bank's book)"),
           T(["Quarter", "External exposure (SAR m)", "External DPD", "External default", "Enquiries", "First external report"],
             [[r.get("reporting_quarter"), _m(r.get("external_exposure_sar_mn"), 2), r.get("external_dpd_days"), "Yes" if int(num(r.get("external_default_flag")) or 0) else "No",
               r.get("enquiries_q"), "Yes" if int(num(r.get("external_first_flag")) or 0) else "No"] for r in bq],
             source=_src("bureau_corp_quarter", bq), widths=[1.8, 3.0, 2.0, 2.2, 1.6, 2.6], size=7.2)]
    a, b = bq[0], bq[-1]
    out.append(P(f"External exposure of {D.money(b.get('external_exposure_sar_mn'), 2)} in {b.get('reporting_quarter')} (PY {D.money(a.get('external_exposure_sar_mn'), 2)} in "
                 f"{a.get('reporting_quarter')}), as per bureau_corp_quarter."))
    return out


def b_bureau(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    bq = B.get("bureau_corp_quarter") or []
    if not bq:
        return []
    mx = max(int(num(r.get("external_dpd_days")) or 0) for r in bq)
    dft = sum(int(num(r.get("external_default_flag")) or 0) for r in bq)
    enq = sum(int(num(r.get("enquiries_q")) or 0) for r in bq[-4:])
    return [H("Bureau record in the bank's feed"),
            P(f"Over {len(bq)} quarters to {bq[-1].get('reporting_quarter')}: {dft} external default flag(s), worst external DPD {mx} days and {enq} credit enquiries in the "
              f"last 4 quarters, as per bureau_corp_quarter; the individual SIMAH reports of the entity and its UBOs are not provided in Data Domains.")]


def b_other_banks(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    ob = _last(B.get("openbanking_corp_quarter") or [])
    if not ob:
        return []
    out = [H("Accounts at other banks (open banking, bank's book)"),
           T(["Quarter", "Operating inflows (SAR m)", "Inflow trend", "Balance buffer", "Returned payments"],
             [[r.get("reporting_quarter"), _m(r.get("operating_inflows_sar_mn"), 2), f"{_m(r.get('inflow_trend_pct'))}%", f"{_m(r.get('balance_buffer_months'), 2)} months",
               r.get("returned_payments_q")] for r in ob], source=_src("openbanking_corp_quarter", ob), widths=[1.8, 3.2, 2.0, 2.4, 2.4], size=7.2)]
    yr = sum(num(r.get("operating_inflows_sar_mn")) or 0 for r in ob[-4:])
    rp = sum(int(num(r.get("returned_payments_q")) or 0) for r in ob[-4:])
    rev = num((B.get("corp_borrower_quarter") or [{}])[-1].get("revenue_sar_mn"))
    out.append(P(f"Operating inflows at other banks of {D.money(yr)} over the 4 quarters to {ob[-1].get('reporting_quarter')}"
                 + (f" ({yr / rev * 100:,.1f}% of book revenue of {D.money(rev)})" if rev else "") + f" with {rp} returned payment(s), as per openbanking_corp_quarter."))
    return out


def b_financials(D: Deal, B: dict[str, Any]) -> list[dict[str, Any]]:
    bq = _last(B.get("corp_borrower_quarter") or [])
    if not bq:
        return []
    keys = [("Revenue (12m, SAR m)", "revenue_sar_mn", 1), ("EBITDA", "ebitda_sar_mn", 1), ("EBIT", "ebit_sar_mn", 1), ("Operating cash flow", "operating_cash_flow_sar_mn", 1),
            ("Total debt", "total_debt_sar_mn", 1), ("Cash", "cash_sar_mn", 1), ("Net debt", "net_debt_sar_mn", 1), ("Leverage (x)", "leverage_x", 2),
            ("DSCR (x)", "dscr_x", 2), ("Interest cover (x)", "interest_cover_x", 2), ("Current ratio (x)", "current_ratio_x", 2), ("EBITDA margin (%)", "ebitda_margin_pct", 1),
            ("Cash conversion (%)", "cash_conversion_pct", 1)]
    rows = [[lab] + [_m(r.get(k), dp) for r in bq] for lab, k, dp in keys]
    a, b = bq[0], bq[-1]
    return [H("Quarterly financials in the bank's book"),
            T(["SAR m"] + [str(r.get("reporting_quarter")) for r in bq], rows, source=_src("corp_borrower_quarter", bq), widths=[3.6] + [1.6] * len(bq), size=6.9),
            P(f"Revenue of {D.money(b.get('revenue_sar_mn'))} on a 12-month basis in {b.get('reporting_quarter')} (PY {D.money(a.get('revenue_sar_mn'))} in {a.get('reporting_quarter')}) "
              f"and leverage of {_m(b.get('leverage_x'), 2)}x (PY {_m(a.get('leverage_x'), 2)}x), as per corp_borrower_quarter.")]


AUG: dict[str, Callable[[Deal, dict[str, Any]], list[dict[str, Any]]]] = {
    "relationship": b_relationship, "security": b_security, "terms": b_terms, "group_exposure": b_group, "background": b_background,
    "cbrbr": b_cbrbr, "bureau": b_bureau, "other_banks": b_other_banks, "financials": b_financials}


def augment(key: str, writer: Callable[[Deal], Out]) -> Callable[[Deal], Out]:
    fn = AUG[key]

    def w(D: Deal) -> Out:
        blocks, gaps = writer(D)
        if not _bid(D):
            return blocks, gaps
        thin = bool(gaps) or key in ("security", "terms") and not D.rows("dd_facility_limit")
        if not thin:
            return blocks, gaps
        extra = fn(D, load(D))
        return (blocks + extra, gaps) if extra else (blocks, gaps)
    w.__name__ = getattr(writer, "__name__", key)
    return w
