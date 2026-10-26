"""R14 E (K22, D3): the one capacity engine, by product.

    from backend.dealdesk.capacity import capacity
    capacity("R12-TWA")                 # the ask
    capacity("R12-TWA", {"amount": 90}) # a structure

Method by product:
* working-capital, revolving and trade lines (revolver, trade LC, LGs): **borrowing base** on the working-capital cycle
      eligible receivables  = receivables aged 0-90 days × advance + 91-180 days × advance (older: 0), less the largest
                              debtor's share above the single-debtor cap; related-party receivables are a separate line
                              and never eligible
      eligible inventory    = inventory × advance
      borrowing base        = eligible receivables + eligible inventory − short-term bank debt already drawn against them
  with the working-capital gap (receivables + inventory − trade payables) shown as a cross-check;
* term loans: **DSCR and leverage**: the smaller of
      leverage capacity     = max leverage × EBITDA − total debt
      cash-flow capacity    = (EBITDA / minimum DSCR − existing debt service) × annuity factor over the tenor at the hurdle.
When the deal has no receivables ageing in dd_financials_detail, a WC line falls back to DSCR and leverage and says so.

Ask above capacity is a CRITICAL finding (findings engine), and the counter-offer cuts the amount to capacity.
Advance rates: backend/dealdesk/capacity/policy.json (credit policy setting, labelled). Leverage and DSCR minimums:
dd_parameter desk (max_leverage, cash_flow_cover).
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from backend.dealdesk import desk_params, engine
from backend.dealdesk.economics import deal as D

POLICY_FILE = Path(__file__).with_name("policy.json")
WC_TYPES = ("revolver", "trade_lc", "performance_lg", "financial_lg")


@functools.lru_cache(maxsize=1)
def policy() -> dict[str, Any]:
    return json.loads(POLICY_FILE.read_text())


def _mn(x: Any) -> str:
    return "n/a" if not isinstance(x, (int, float)) else f"SAR {x:,.1f}m"


def _fin_rows(pid: str) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data.store import dd_read
        return dd_read("dd_financials_detail", proposal_id=pid)
    except Exception:  # noqa: BLE001
        return []


def _subject_period(pid: str, p: dict[str, Any]) -> dict[str, Any] | None:
    """The borrower's latest audited period with receivables ageing (the entity whose revenue matches the proposal's
    latest actual); the latest interim when no audited period has ageing."""
    rows = [r for r in _fin_rows(pid) if r.get("ageing_0_90_mn") is not None and r.get("receivables_mn") is not None]
    if not rows:
        return None
    rev = float(engine.latest_actual(p).get("revenue") or 0.0)
    by_ent: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_ent.setdefault(r["entity_id"], []).append(r)

    def latest(rs: list[dict[str, Any]]) -> dict[str, Any]:
        aud = [r for r in rs if r.get("period_kind") == "audited"]
        return max(aud or rs, key=lambda r: (int(r.get("year") or 0), str(r.get("period_end") or "")))
    cands = [latest(rs) for rs in by_ent.values()]
    return min(cands, key=lambda r: abs(float(r.get("revenue_mn") or 0.0) - rev))


def _v(r: dict[str, Any], k: str) -> float:
    x = r.get(k)
    return float(x) if isinstance(x, (int, float)) else 0.0


def _src(pid: str, r: dict[str, Any], col: str) -> dict[str, Any]:
    return {"relation": "dd_financials_detail", "key": {"proposal_id": pid, "entity_id": r.get("entity_id"), "period_label": r.get("period_label")},
            "column": col}


def _borrowing_base(pid: str, r: dict[str, Any]) -> dict[str, Any]:
    pol = policy()["borrowing_base"]
    a090, a91 = _v(r, "ageing_0_90_mn"), _v(r, "ageing_91_180_mn")
    old = _v(r, "ageing_181_365_mn") + _v(r, "ageing_over_365_mn")
    rec = _v(r, "receivables_mn")
    top1 = _v(r, "top1_receivable_pct") / 100.0
    conc_excess = max(0.0, top1 - float(pol["single_debtor_cap"])) * rec
    elig_rec = max(0.0, a090 * float(pol["advance_0_90"]) + a91 * float(pol["advance_91_180"]) - conc_excess * float(pol["advance_0_90"]))
    inv = _v(r, "inventory_mn")
    elig_inv = inv * float(pol["advance_inventory"])
    st_debt = _v(r, "bank_debt_st_mn")
    bb = elig_rec + elig_inv
    cap = max(0.0, bb - st_debt)
    payables = max(0.0, _v(r, "current_liabilities_mn") - st_debt - _v(r, "due_to_related_mn"))
    wc_gap = rec + inv - payables
    inputs = [
        {"name": "Receivables aged 0-90 days", "value": a090, "unit": "SAR m", "advance": pol["advance_0_90"], "source": _src(pid, r, "ageing_0_90_mn")},
        {"name": "Receivables aged 91-180 days", "value": a91, "unit": "SAR m", "advance": pol["advance_91_180"], "source": _src(pid, r, "ageing_91_180_mn")},
        {"name": "Receivables older than 180 days (not eligible)", "value": old, "unit": "SAR m", "advance": 0.0,
         "source": _src(pid, r, "ageing_181_365_mn")},
        {"name": f"Largest debtor above the {pol['single_debtor_cap']:.0%} cap (excluded)", "value": conc_excess, "unit": "SAR m",
         "advance": -float(pol["advance_0_90"]), "source": _src(pid, r, "top1_receivable_pct")},
        {"name": "Related-party receivables (never eligible)", "value": _v(r, "due_from_related_mn"), "unit": "SAR m", "advance": 0.0,
         "source": _src(pid, r, "due_from_related_mn")},
        {"name": "Inventory", "value": inv, "unit": "SAR m", "advance": pol["advance_inventory"], "source": _src(pid, r, "inventory_mn")},
        {"name": "Short-term bank debt already drawn", "value": st_debt, "unit": "SAR m", "advance": -1.0, "source": _src(pid, r, "bank_debt_st_mn")},
        {"name": "Trade and other payables (current liabilities − short-term bank debt − due to related)", "value": payables, "unit": "SAR m",
         "advance": None, "source": _src(pid, r, "current_liabilities_mn")},
    ]
    formula = (f"Borrowing base = eligible receivables {_mn(elig_rec)} (0-90 days × {pol['advance_0_90']:.0%} + 91-180 days × "
               f"{pol['advance_91_180']:.0%}, older 0, concentration excess out) + inventory × {pol['advance_inventory']:.0%} {_mn(elig_inv)} "
               f"− short-term bank debt {_mn(st_debt)} = {_mn(cap)}")
    return {"capacity": cap, "formula": formula, "inputs": inputs, "eligible_receivables": elig_rec, "eligible_inventory": elig_inv,
            "gross_base": bb, "short_term_debt": st_debt, "wc_gap": wc_gap, "payables": payables,
            "period": {"entity_id": r.get("entity_id"), "entity_name": r.get("entity_name"), "period_label": r.get("period_label"),
                       "period_kind": r.get("period_kind")},
            "cross_check": f"Working-capital gap (receivables + inventory − payables) {_mn(wc_gap)} against short-term bank debt {_mn(st_debt)}"}


def _dscr_leverage(p: dict[str, Any], terms: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    dp = desk_params.rows()
    fin = engine.latest_actual(p)
    ebitda, debt, ds = float(fin["ebitda"]), float(fin["total_debt"]), float(fin["debt_service"])
    lev = float(dp["max_leverage"])
    cover = float(dp["cash_flow_cover"])
    h = float(a["metrics"]["hurdle"])
    T = max(1, int(terms["tenor_years"]))
    ann = sum((1 + h) ** -t for t in range(1, T + 1))
    lev_cap = max(0.0, lev * ebitda - debt)
    free = max(0.0, ebitda / cover - ds)
    cf_cap = free * ann
    cap = min(lev_cap, cf_cap)
    src = {"relation": "dd_obligor_financials", "key": {"proposal_id": p["proposal_id"], "year": fin.get("year")}}
    inputs = [{"name": "EBITDA (latest actual)", "value": ebitda, "unit": "SAR m", "source": src},
              {"name": "Total debt", "value": debt, "unit": "SAR m", "source": src},
              {"name": "Existing debt service", "value": ds, "unit": "SAR m", "source": src},
              {"name": "Maximum leverage", "value": lev, "unit": "x", "source": {"relation": "dd_parameter", "key": {"name": "max_leverage"}}},
              {"name": "Minimum DSCR", "value": cover, "unit": "x", "source": {"relation": "dd_parameter", "key": {"name": "cash_flow_cover"}}}]
    formula = (f"Capacity = min(leverage: {lev:g}× EBITDA {_mn(ebitda)} − debt {_mn(debt)} = {_mn(lev_cap)}; "
               f"cash flow: (EBITDA / {cover:g} − debt service {_mn(ds)}) × annuity {ann:.2f} ({T}y at {h:.1%}) = {_mn(cf_cap)}) = {_mn(cap)}")
    return {"capacity": cap, "formula": formula, "inputs": inputs, "ebitda_based": lev_cap, "cash_flow_based": cf_cap}


def _project(pid: str) -> dict[str, Any] | None:
    """R16 x: a new project limit (a level-1 limit named "Project limit ..." with no existing amount, and the deal's dd_project row
    of status new) is self-liquidating on its contract: it is sized on the project, never on the company's borrowing base.
      guarantees and LCs   = the project's non-funded sub-limits, covered by the remaining assigned contract proceeds
      funded (DMCCM)       = the project's peak cash deficit with certificates paid 2 months late (credit's re-performance:
                             work evenly over the tenor, costs at 1 - gross margin paid the following month, advance at start,
                             10% retention and advance recovery, certificates paid 2 months after certification), rounded up
                             to SAR 5m and not above the funded line asked
    None for every other deal (R12-R15 deals unchanged)."""
    try:
        from backend.dealdesk.data.store import dd_read
        lims = dd_read("dd_facility_limit", proposal_id=pid)
        # only a new project read from an uploaded business request (credit_response.projects tags its row "[business request]"):
        # the seeded R12-R15 deals keep their capacity method
        prj = [r for r in dd_read("dd_project", proposal_id=pid) if str(r.get("status")) == "new" and "[business request]" in str(r.get("narrative") or "")]
    except Exception:  # noqa: BLE001
        return None
    import re
    top = next((r for r in lims if int(r.get("level") or 0) == 1 and re.search(r"\bproject\b", str(r.get("limit_name") or ""), re.I)
                and not (r.get("existing_mn") or 0) and (r.get("proposed_mn") or 0) > 0), None)
    if top is None or not prj:
        return None
    pr = prj[-1]
    value = float(pr.get("contract_value_original_mn") or pr.get("contract_value_revised_mn") or 0.0)
    try:
        from datetime import date
        s, e = date.fromisoformat(str(pr.get("start_date"))[:10]), date.fromisoformat(str(pr.get("completion_original"))[:10])
        months = max(1, round((e - s).days / 30.44))
    except (TypeError, ValueError):
        return None
    kids = [r for r in lims if str(r.get("parent_limit_id") or "") == str(top.get("limit_id"))]
    funded = [r for r in kids if int(r.get("funded_flag") or 0) == 1]
    nonf = [r for r in kids if int(r.get("funded_flag") or 0) != 1]
    if not value or not funded:
        return None
    fins = sorted(_fin_rows(pid), key=lambda r: (str(r.get("period_end") or ""), int(r.get("year") or 0)))
    gm = next((float(r["gross_profit_mn"]) / float(r["revenue_mn"]) for r in reversed(fins)
               if isinstance(r.get("gross_profit_mn"), (int, float)) and r.get("revenue_mn")), 0.10)
    adv = next((float(r.get("proposed_mn") or 0) / value for r in nonf if re.search(r"advance payment", str(r.get("limit_name") or ""), re.I)), 0.10)
    from backend.dealdesk.credit_response.projects import cash_gap
    peak, when = cash_gap(value, months, gm, advance=adv, delay=2)
    asked_f = sum(float(r.get("proposed_mn") or 0) for r in funded)
    f_cap = min(asked_f, -(-peak // 5) * 5.0)
    nf = sum(float(r.get("proposed_mn") or 0) for r in nonf)
    nf_cap = min(nf, value)
    cap = round(nf_cap + f_cap, 1)
    src = {"relation": "dd_project", "key": {"proposal_id": pid, "project_id": pr.get("project_id")}}
    inputs = [{"name": "Contract value", "value": value, "unit": "SAR m", "source": src},
              {"name": "Tenor", "value": months, "unit": "months", "source": src},
              {"name": "Gross margin (latest statements)", "value": round(gm, 4), "unit": "ratio", "source": {"relation": "dd_financials_detail", "key": {"proposal_id": pid}}},
              {"name": "Peak deficit, certificates 2 months late", "value": peak, "unit": "SAR m", "source": {"relation": "re-performance", "key": {"month": when}}}]
    formula = (f"Project capacity = non-funded sub-limits {_mn(nf)} covered by the contract {_mn(value)} = {_mn(nf_cap)} + funded line at the peak "
               f"deficit with certificates paid 2 months late {_mn(peak)} (month {when}, rounded up to SAR 5m, asked {_mn(asked_f)}) = {_mn(f_cap)}; total {_mn(cap)}")
    return {"capacity": cap, "formula": formula, "inputs": inputs, "project": {"project_id": pr.get("project_id"), "limit_id": top.get("limit_id"),
            "funded_cap_sar_mn": f_cap, "funded_asked_sar_mn": asked_f, "peak_deficit_2m_sar_mn": peak, "months": months, "gross_margin": gm}}


def plain_title(ask: float, cap: float, method: str) -> str:
    """R15 b (L13 (5)): the capacity finding in plain words, the same sentence in the banner, the tile and the plain words.

    "The client asks SAR 24.0m but its cash flow can carry about SAR 14.6m (the ask is 1.6× what it can service)."
    """
    what = {"borrowing_base": "its working-capital cycle supports", "project": "the project's contract and cash flow support"}.get(method, "its cash flow can carry")
    if cap <= 0:
        return f"The client asks {_mn(ask)} but {what} no new debt on its current finances"
    if ask - cap <= 1e-6:
        return f"The client asks {_mn(ask)} and {what} about {_mn(cap)}, so the ask fits"
    return f"The client asks {_mn(ask)} but {what} about {_mn(cap)} (the ask is {ask / cap:.1f}× what it can service)"


def capacity(pid: str, structure: Any = None) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    st = D.structure_terms(pid, structure)
    t = st["terms"]
    a = D.analysis(pid, t)
    p = D.proposal(pid)
    ask_sar = float(a["metrics"]["amount_sar_mn"])
    dl = _dscr_leverage(p, t, a)
    note = None
    pj = _project(pid)
    if pj is not None:
        method, cap, formula, inputs = "project", pj["capacity"], pj["formula"], pj["inputs"]
        extra = {"project": pj["project"]}
        note = "A new project limit is sized on its project (contract proceeds and the project's cash gap), not on the company's borrowing base."
    elif t["facility_type"] in WC_TYPES:
        r = _subject_period(pid, p)
        if r is not None:
            bb = _borrowing_base(pid, r)
            method, cap, formula, inputs = "borrowing_base", bb["capacity"], bb["formula"], bb["inputs"]
            extra = {"borrowing_base": {k: bb[k] for k in ("eligible_receivables", "eligible_inventory", "gross_base", "short_term_debt",
                                                           "wc_gap", "payables", "period", "cross_check")}}
        else:
            method, cap, formula, inputs = "dscr_leverage", dl["capacity"], dl["formula"], dl["inputs"]
            note = "No receivables ageing in dd_financials_detail for this deal: the working-capital line is sized on DSCR and leverage."
            extra = {}
    else:
        method, cap, formula, inputs = "dscr_leverage", dl["capacity"], dl["formula"], dl["inputs"]
        extra = {}
    gap = ask_sar - cap
    within = gap <= 1e-6
    ratio = ask_sar / cap if cap > 0 else None
    sev = None if within else "critical"  # PLAN_R14 e: ask above capacity is a critical finding
    lab = {"borrowing_base": "borrowing base", "project": "project capacity"}.get(method, "DSCR and leverage capacity")
    title = plain_title(ask_sar, cap, method)
    short = (f"Ask within capacity: {_mn(ask_sar)} vs {lab} {_mn(cap)}" if within else
             f"Ask above capacity: {_mn(ask_sar)} vs {lab} {_mn(cap)}")
    rec_amt = None if within else max(0.0, cap)
    return {"proposal_id": pid, "structure": {"key": st["key"], "label": st["label"]}, "facility_type": t["facility_type"],
            "method": method, "method_label": {"borrowing_base": "Borrowing base (working-capital cycle)", "project": "Project (contract proceeds and cash gap)"}.get(method, "DSCR and leverage"),
            "formula": formula, "inputs": inputs, "capacity_sar_mn": cap, "ask_sar_mn": ask_sar, "gap_sar_mn": gap,
            "ask_to_capacity": ratio, "within": within, "severity": sev, "finding_title": title, "short_title": short,
            "recommended_amount_sar_mn": rec_amt, "note": note,
            "alt": {"ebitda_based_sar_mn": dl["ebitda_based"], "cash_flow_based_sar_mn": dl["cash_flow_based"]},
            **extra, "policy": {"file": "backend/dealdesk/capacity/policy.json", **policy()},
            "source": "backend.dealdesk.capacity (dd_financials_detail, dd_obligor_financials, dd_parameter)"}
