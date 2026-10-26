"""Renewal repricing (PLAN_R12 §1.6, I8 part 2): the reprice or restructure that brings a below-hurdle facility back.

For a book facility the Deal Desk pricing levers are solved on the same one-year RAROC as the drift (it is linear in
margin, fee and LGD at today's inputs), within the market bounds for today's rating bucket (`market_bounds`):
  1. renewal fee: if the upfront fee has been fully earned, take a renewal fee at the bucket's lower bound;
  2. margin: the margin that reaches the hurdle, rounded up to 5 bps, if it is within the bucket's upper bound
     (plus the sector add-on) -> **Reprice**;
  3. otherwise, at the upper bound, the LGD that reaches the hurdle and the collateral it takes
     (`relationship.book.lgd_collateral_haircut`) -> **Restructure**; if even full cover does not, **Exit or reduce**.
Recoverable RAROC = what the action recovers, capped at the hurdle; ranked by it on the repricing list.
For a facility that came through Deal Desk (it has a proposal), `detail()` also runs the Deal Desk optimiser on the
renewal proposal (closest-to-ask structure), so the Book shows the optimiser's own reprice or restructure.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk import params
from backend.dealdesk.seed import GRADES, bucket


def _bucket(r: Any) -> str:
    r = str(r)
    return bucket(r) if r in GRADES else "CCC-C"


def solve(f: pd.DataFrame) -> pd.DataFrame:
    mb = params.rows("market_bounds")
    addon = mb.get("sector_margin_addon_bps", {})
    floor = float(params.rows("lgd")["floor"])
    h = float(params.rows("relationship")["book"]["lgd_collateral_haircut"])
    bk = f.rating_now.fillna(f.orig_rating).map(_bucket)
    m_hi = bk.map(lambda b: mb["by_bucket"][b]["margin_bps"][1]) + f.sector.map(lambda s: addon.get(s, 0))
    fee_lo = bk.map(lambda b: mb["by_bucket"][b]["upfront_fee_bps"][0])
    m0 = f.orig_margin_pct * 100
    need = ~f.above_now & ~f.defaulted & f.raroc_now.notna() & f.hurdle.notna()
    fee_take = need & (f.fee_now_sar_mn <= 0)
    fee_sar = np.where(fee_take, fee_lo / 1e4 * f.limit_sar_mn, 0.0)
    r1 = f.raroc_now + f.slope_fee * fee_sar
    gap = (f.hurdle - r1).clip(lower=0)
    sm = f.slope_margin.where(f.slope_margin > 0)
    m_need = m0 + (gap / sm * 1e4).fillna(np.inf)
    m_need = np.ceil(m_need / 5) * 5
    reprice = need & (m_need <= m_hi)
    m_new = np.where(reprice, np.maximum(m_need, m0), np.where(need, np.maximum(m_hi, m0), m0))
    r2 = r1 + f.slope_margin * (m_new - m0) / 1e4
    gap2 = (f.hurdle - r2).clip(lower=0)
    sl = f.slope_lgd.where(f.slope_lgd < 0)
    lgd_need = (f.lgd_now - gap2 / sl.abs()).where(sl.notna(), -np.inf)
    cov_n = (f.collateral_value_sar_mn / f.ead_sar_mn.where(f.ead_sar_mn > 0)).clip(0, 1).fillna(0)
    lgd_base = f.lgd_now / (1 - h * cov_n)
    cov_need = ((1 - lgd_need / lgd_base) / h)
    restructure = need & ~reprice & (lgd_need >= floor) & (cov_need <= 1.0)
    extra = np.where(restructure, ((cov_need - cov_n).clip(lower=0) * f.ead_sar_mn), 0.0)
    exit_ = need & ~reprice & ~restructure
    achieved = np.where(reprice | restructure, f.hurdle, r2)
    rec = np.where(need, np.minimum(achieved, f.hurdle) - f.raroc_now, 0.0)
    action = np.select([~need, reprice, restructure, exit_], ["None", "Reprice", "Restructure", "Exit or reduce"], "None")
    out = pd.DataFrame(index=f.index)
    out["action"] = action
    out["new_margin_bps"] = np.where(need, m_new, np.nan)
    out["margin_change_bps"] = np.where(need, m_new - m0, np.nan)
    out["renewal_fee_bps"] = np.where(fee_take, fee_lo, 0.0)
    out["extra_collateral_sar_mn"] = extra
    out["lgd_needed"] = np.where(restructure, lgd_need, np.nan)
    out["recoverable_raroc"] = rec
    out["recoverable_sva_sar_mn"] = rec * f.capital_now_sar_mn.fillna(0)
    out["action_text"] = [_text(a, fee, mc, mn, ex, mh) for a, fee, mc, mn, ex, mh in
                          zip(action, out.renewal_fee_bps, out.margin_change_bps, out.new_margin_bps, extra, m_hi)]
    return out


def _text(a: str, fee: float, mc: float, mn: float, ex: float, mh: float) -> str:
    fee_t = f"renewal fee {fee:.0f} bps, " if fee else ""
    if a == "Reprice":
        return f"Reprice at renewal: {fee_t}margin {'+' if mc >= 0 else ''}{mc:.0f} bps to {mn:.0f} bps"
    if a == "Restructure":
        return (f"Restructure at renewal: {fee_t}margin to the market cap of {mh:.0f} bps and SAR {ex:,.1f}m more collateral")
    if a == "Exit or reduce":
        return f"Exit or reduce at renewal: even at {mh:.0f} bps with full collateral cover the facility stays below hurdle"
    return ""


def detail(r: pd.Series) -> dict[str, Any]:
    out = {"action": r.action, "text": r.action_text, "new_margin_bps": None if not r.new_margin_bps == r.new_margin_bps else float(r.new_margin_bps),
           "margin_change_bps": None if not r.margin_change_bps == r.margin_change_bps else float(r.margin_change_bps),
           "renewal_fee_bps": float(r.renewal_fee_bps), "extra_collateral_sar_mn": float(r.extra_collateral_sar_mn),
           "recoverable_raroc": float(r.recoverable_raroc), "recoverable_sva_sar_mn": float(r.recoverable_sva_sar_mn),
           "method": "Deal Desk pricing levers on the one-year RAROC within the market bounds for today's rating", "optimiser": None}
    pid = r.get("proposal_id")
    if isinstance(pid, str) and pid:
        out["optimiser"] = optimiser_for(pid)
    return out


def optimiser_for(pid: str) -> dict[str, Any] | None:
    """The Deal Desk optimiser's closest-to-ask structure on the deal's file (renewal), when the deal is a Deal Desk deal."""
    try:
        from backend.dealdesk import optimizer
        try:  # the one deal registry (DD, PL and R12 deals: Session E)
            from backend.dealdesk.data import deals
            p = deals.get(pid)
        except (ImportError, KeyError):
            from backend.dealdesk import proposals
            p = proposals.get(pid)
        res = optimizer.optimize(p, counter_offers=False)
    except Exception as e:  # noqa: BLE001 -- the deal file is not loadable: say so, not a number
        return {"proposal_id": pid, "available": False, "why": str(e)[:200]}
    c = res.get("closest") or res.get("max_sva")
    if not c:
        rel = res.get("relaxation") or []
        return {"proposal_id": pid, "available": True, "feasible": False,
                "relaxation": [{k: x.get(k) for k in ("lever", "label", "from", "to")} for x in rel[:3]]}
    m = c.get("metrics", {})
    return {"proposal_id": pid, "available": True, "feasible": True, "label": c.get("label"), "changes": c.get("changes"),
            "lifetime_raroc": m.get("lifetime_raroc"), "sva": m.get("sva"),
            "terms": {k: c.get("terms", {}).get(k) for k in ("amount", "tenor_years", "margin_bps", "upfront_fee_bps", "cash_margin_pct")}}


import functools as _ft


@_ft.lru_cache(maxsize=32)
def optimiser_cached(pid: str) -> dict[str, Any] | None:
    return optimiser_for(pid)


def optimiser_action(o: dict[str, Any] | None) -> tuple[str, str]:
    """The Book's action and text from the Deal Desk optimiser's result on the deal file."""
    if not o or not o.get("available"):
        return "None", ""
    if not o.get("feasible"):
        rel = ", ".join(x.get("label") or x.get("lever") or "" for x in o.get("relaxation") or [])
        return "Exit or reduce", f"Deal Desk optimiser: no structure clears every limit on the deal file{'; relax ' + rel if rel else ''}"
    ch = o.get("changes") or []
    def num(v: Any) -> str:
        return f"{v:,.0f}" if isinstance(v, (int, float)) and abs(v - round(v)) < 0.05 else (f"{v:,.1f}" if isinstance(v, (int, float)) else str(v))
    words = ", ".join(f"{str(c.get('field', '')).replace('_bps', '').replace('_pct', '').replace('_', ' ')} {num(c.get('ask'))} → "
                      f"{num(c.get('value'))}{' ' + c['unit'] if c.get('unit') else ''}" for c in ch)
    kind = "Reprice" if ch and all(str(c.get("field", "")).endswith(("_bps",)) for c in ch) else "Restructure"
    rr = o.get("lifetime_raroc")
    return kind, (f"Deal Desk optimiser on {o['proposal_id']} ({o.get('label', 'closest to ask')}): {words or 'the ask clears'}"
                  + (f"; lifetime RAROC {rr:.1%}" if isinstance(rr, (int, float)) else ""))


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
