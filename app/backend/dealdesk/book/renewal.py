"""Renewal of a back-book facility that has no Deal Desk file yet (PLAN_R12 §1.6: "start the renewal, which reopens the deal on
Proposal with last year's file, conditions status and drift").

The renewal proposal is pre-filled the way R11 pre-fills an existing borrower (ops/dealdesk_build.existing_obligor): identity,
rating, connected group, exposure, facilities and pledged collateral from the corporate book (`portfolio.borrower`, the
registered Cockpit relations), three years of actuals from the borrower history, and as the ask last year's terms (limit,
tenor, margin and fees from the origination record). It is created through `proposals.create` (R11's user-proposal store, which
the deal page and every Deal Desk step read) and its workflow event is published by `actions.start_renewal`.
"""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from backend.dealdesk import portfolio, proposals, seed
from backend.dealdesk.book import core

#: book product -> Deal Desk facility type
PRODUCT = {"term_loan": "term_loan", "project_finance": "term_loan", "asset_finance": "term_loan", "working_capital": "revolver",
           "revolving_credit": "revolver", "overdraft": "revolver", "supply_chain_finance": "revolver", "trade_finance": "trade_lc"}


def _financials(bid: str) -> list[dict[str, Any]]:
    h = portfolio.borrower_history(bid)
    years: list[dict[str, Any]] = []
    for y in (2023, 2024, 2025):
        q = h[h["reporting_quarter"] == f"{y}Q4"]
        if q.empty:
            continue
        q = q.iloc[0]
        roa = float(q["return_on_assets_pct"])
        nw = (q["ebit_sar_mn"] / (roa / 100.0) - q["total_debt_sar_mn"]) if roa > 0 else q["total_debt_sar_mn"]
        years.append({"year": y, "kind": "actual", "revenue": round(float(q["revenue_sar_mn"]), 3), "ebitda": round(float(q["ebitda_sar_mn"]), 3),
                      "total_debt": round(float(q["total_debt_sar_mn"]), 3),
                      "debt_service": round(float(q["ebitda_sar_mn"] / q["dscr_x"]), 3) if q["dscr_x"] else 0.0,
                      "net_worth": round(float(max(nw, 0.5 * q["total_debt_sar_mn"])), 3),
                      "current_ratio": round(float(q["current_ratio_x"]), 3), "source": f"corp_borrower_quarter {y}Q4"})
    if years:
        last = years[-1]
        for i, y in enumerate((2026, 2027, 2028), start=1):
            years.append({**{k: last[k] for k in ("revenue", "ebitda", "total_debt", "debt_service", "net_worth", "current_ratio")},
                          "year": y, "kind": "projection", "source": "Renewal: flat on the 2025 actuals until the RM's projections"})
    return years


def build(fid: str) -> dict[str, Any]:
    f, _ = core.frame()
    t = f[f.facility_id == fid]
    if not len(t):
        raise KeyError(fid)
    r = t.iloc[0]
    bid = r.borrower_id
    b = portfolio.borrower(bid)
    if b is None:
        raise KeyError(fid)
    rec = b["record"]
    rating = rec["rating_current"] if rec["rating_current"] in seed.MASTER_SCALE else r.orig_rating
    ob = {"obligor_id": bid, "existing": True, "name": rec["borrower_name"],
          "cr_number": "10" + hashlib.sha256(bid.encode()).hexdigest()[:8].translate(str.maketrans("abcdef", "123456")),
          "group_id": rec["connected_group_id"], "group_name": rec["connected_group_name"], "legacy_group_id": rec["group_id"],
          "sector": rec["sector"], "sub_sector": rec["sub_sector"], "segment": rec["sector"], "region": rec["region"], "sme": False,
          "gre": False, "internal_rating": rating, "external_rating": None, "pd_master_scale": seed.MASTER_SCALE[rating],
          "simah_flag": "clear", "existing_exposure_sar_mn": round(float(b["ead"]), 4),
          "existing_facilities": [{"facility_id": x["facility_id"], "product": x["product_type"], "limit": round(x["limit_sar_mn"], 4),
                                   "drawn": round(x["drawn_sar_mn"], 4), "ead": round(x["ead_sar_mn"], 4), "stage": int(x["stage"])}
                                  for x in b["facilities"]],
          "prefilled_from": "corporate book (Book renewal)", "gov_linked": False, "real_estate_finance": rec["sector"] == "Real Estate"}
    members = portfolio.frames()["borrower"]
    ob["connected_parties"] = sorted(members.loc[members["connected_group_id"] == ob["group_id"], "borrower_id"].tolist())
    coll = [{"collateral_id": f"C{i + 1}", "type": portfolio.COLLATERAL_KEY.get(c["collateral_type"], c["collateral_type"]),
             "value": round(float(c["market_value_sar_mn"]), 4), "currency": "SAR", "valuation_date": str(r.ref_date)[:10],
             "pledged_in_ask": c["facility_id"] == fid} for i, c in enumerate(b["collateral"])]
    coll = [c for c in coll if c["type"] in proposals.COLLATERAL_TYPES]
    ftype = PRODUCT.get(str(r.product_type), "term_loan")
    tenor = int(min(10, max(1, round(float(r.tenor_months) / 12))))
    ask = {"facility_type": ftype, "structure": "conventional", "currency": "SAR", "amount": round(float(r.limit_sar_mn), 2),
           "tenor_years": tenor, "grace_years": 0, "amortisation": "equal" if ftype == "term_loan" else "bullet", "balloon_pct": 0,
           "margin_bps": round(float(r.orig_margin_pct) * 100), "upfront_fee_bps": round(float(r.orig_fees_sar_mn) / max(float(r.orig_limit_sar_mn), 1e-9) * 1e4),
           "commitment_fee_bps": 0, "commission_bps": 100 if ftype in ("trade_lc", "performance_lg", "financial_lg") else 0,
           "utilisation_pct": round(float(min(max(r.util_now, 0.05), 1.0)) * 100), "funded_share_pct": 0 if ftype == "trade_lc" else 100,
           "unfunded_type": "trade_lc" if ftype == "trade_lc" else "performance_lg", "cash_margin_pct": 0,
           "collateral_ids": [c["collateral_id"] for c in coll if c["pledged_in_ask"]], "guarantee_id": None, "guarantee_coverage_pct": 0,
           "covenant_package": "standard"}
    ask["upfront_fee_bps"] = int(min(max(ask["upfront_fee_bps"], 0), 1000))
    years = _financials(bid)
    return {"status": "new", "rm": "", "business_unit": "Corporate Banking", "purpose": f"Renewal of {fid} ({str(r.product_type).replace('_', ' ')})",
            "obligor": ob, "financials": {"currency": "SAR", "unit": "SAR m", "years": years}, "ask": ask,
            "security": {"collateral": coll, "guarantees": [], "covenant_package": "standard",
                         "covenants": [{"type": "DSCR", "threshold": 1.20}, {"type": "Net debt / EBITDA", "threshold": 4.0}]},
            "business_case": {"ancillary_income_sar_mn_pa": {}, "currency": "SAR"}, "case": "book_renewal", "renewal_of": fid}


def create(fid: str, by: str) -> dict[str, Any]:
    p = proposals.create(build(fid), owner=by)
    return p


def _frame_date(f: pd.DataFrame) -> str:
    return str(f.ref_date.iloc[0]) if len(f) else ""
