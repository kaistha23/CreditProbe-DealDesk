"""R16 d: the Borrower 360 overlay for demo customers 1 and 2 and their connected parties (python -m ops.r16_customers.b360).

Writes data/dealdesk/demo_customers/bank_b360/<relation>.parquet with exactly the columns and types of the corporate
book relations Borrower 360 reads (backend/b360/paths.RELATIONS), for 20 quarters 2021Q3-2026Q2. backend/b360/store.py
unions each overlay file with its book relation in Borrower 360's own read-only views; the Cockpit lake, the EWS release
and every other reader are untouched, so no Cockpit, What-If or Early Warning number moves. EWS scores are computed with
the live rule set (gw-ews-1.3.0) from the same fields as the book.
"""
from __future__ import annotations

import json
import pathlib

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from backend.b360 import paths
from backend.dealdesk.seed import MASTER_SCALE
from backend.ews_domain import ews_rules
from ops.r16_customers import c1, c2

OUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "dealdesk" / "demo_customers" / "bank_b360"
QUARTERS = [f"{y}Q{q}" for y in range(2021, 2027) for q in range(1, 5)][2:22]   # 2021Q3 .. 2026Q2
T = "demo-tenant"
REL = "v4-saudi-corporate-20q-v4"
PRODUCT = {"TL": ("working_capital", "funded"), "TR": ("working_capital", "funded"), "OD": ("overdraft", "funded"),
           "DMCCM_PC": ("project_finance", "funded"), "LC_SIGHT": ("trade_finance", "non_funded"), "LC_USANCE": ("trade_finance", "non_funded"),
           "LG": ("trade_finance", "non_funded"), "APG": ("trade_finance", "non_funded"), "PB": ("trade_finance", "non_funded"),
           "TERM": ("term_loan", "funded")}


def _rating_at(hist: dict[str, str], q: str) -> str:
    r = None
    for k in sorted(hist):
        if k <= q:
            r = hist[k]
    return r or sorted(hist.items())[0][1]


def _borrowers() -> list[dict]:
    """One dict per overlay borrower with everything the frames need."""
    sp1, sp2 = c1.spec(), c2.spec()
    b1, b2 = c1.bank(sp1), c2.bank(sp2)
    out = []

    def years(sp, extra):
        fs = sp["fs"]
        y = {2023: fs["FY2023"], 2024: fs["FY2024"], 2025: fs["FY2025"]}
        m9 = dict(fs["9M2026"])
        for k in ("revenue", "ebitda", "operating_profit", "net_profit", "finance_cost", "operating_cash_flow"):
            m9[k] = fs["9M2026"][k] / 9 * 12
        y[2026] = m9
        y.update(extra)
        return y
    y1 = years(sp1, {2021: {"revenue": 128.0, "ebitda": 17.1, "operating_profit": 14.6, "finance_cost": 2.9, "operating_cash_flow": 11.2, "cash": 8.1,
                            "short_term_borrowings": 22.0, "current_portion_ltd": 2.0, "long_term_borrowings": 14.0, "current_assets": 82.0, "current_liabilities": 50.0,
                            "inventory": 30.0, "total_assets": 108.0, "net_profit": 10.9},
                     2022: {"revenue": 141.0, "ebitda": 19.0, "operating_profit": 16.3, "finance_cost": 3.3, "operating_cash_flow": 12.0, "cash": 9.0,
                            "short_term_borrowings": 25.5, "current_portion_ltd": 2.0, "long_term_borrowings": 12.0, "current_assets": 88.0, "current_liabilities": 52.0,
                            "inventory": 33.0, "total_assets": 114.0, "net_profit": 12.2}})
    y2 = years(sp2, {2021: {"revenue": 288.0, "ebitda": 33.0, "operating_profit": 23.4, "finance_cost": 6.1, "operating_cash_flow": 18.0, "cash": 15.0,
                            "short_term_borrowings": 44.0, "current_portion_ltd": 9.0, "long_term_borrowings": 45.0, "current_assets": 170.0, "current_liabilities": 128.0,
                            "inventory": 8.0, "total_assets": 230.0, "net_profit": 11.9},
                     2022: {"revenue": 322.0, "ebitda": 36.5, "operating_profit": 26.0, "finance_cost": 6.9, "operating_cash_flow": 19.5, "cash": 16.1,
                            "short_term_borrowings": 51.0, "current_portion_ltd": 9.0, "long_term_borrowings": 40.0, "current_assets": 190.0, "current_liabilities": 140.0,
                            "inventory": 9.0, "total_assets": 252.0, "net_profit": 13.6}})
    conduct = {r["obligor_id"] + r["month"]: r for r in b1["conduct"] + b2["conduct"]}
    out.append({"id": "CB09001", "name": sp1["co"]["name"], "group_id": "CG9001", "group_name": "Naseem Holding Group", "sector": "Wholesale Trade",
                "sub_sector": "Medical Supplies Distribution", "region": "Riyadh", "tier": "Core", "ratings": b1["ratings"]["CB09001"], "years": y1,
                "limits": [(L, {"2021Q3": 0.737, "2025Q1": 1.0}) for L in b1["limits"] if L["level"] == 1],
                "limit_hist": {"2021Q3": 70.0, "2025Q1": 95.0}, "external": 37.8, "enq": {"2026Q2": 1}, "ext_dpd": {}, "returned": {"2026Q1": 1},
                "watch": {}, "dpd": {}, "stage": {}, "coll": ("Real Estate", 31.5, 2), "cov": ("Current Ratio", 1.2), "conduct": conduct,
                "role": "parent", "parent": "CB09001"})
    out.append({"id": "CB09005", "name": c1.LAB, "group_id": "CG9001", "group_name": "Naseem Holding Group", "sector": "Wholesale Trade",
                "sub_sector": "Laboratory Equipment", "region": "Riyadh", "tier": "Transactional", "ratings": b1["ratings"]["CB09005"],
                "years": {y: {"revenue": r, "ebitda": e, "operating_profit": e * 0.75, "finance_cost": 1.6, "operating_cash_flow": e * 0.6, "cash": 0.8,
                              "short_term_borrowings": 14.0, "current_portion_ltd": 1.0, "long_term_borrowings": 8.0, "current_assets": 21.0,
                              "current_liabilities": 19.0, "inventory": 6.0, "total_assets": 33.0, "net_profit": e * 0.3}
                          for y, r, e in ((2021, 38.0, 4.9), (2022, 40.5, 5.0), (2023, 39.2, 4.1), (2024, 35.8, 2.9), (2025, 31.1, 1.6), (2026, 26.4, 0.4))},
                "limits": [({"limit_id": "LAB1", "limit_name": "Letters of guarantee", "product_code": "LG", "existing_mn": 5.0, "outstanding_mn": 4.2}, {"2021Q3": 1.0})],
                "limit_hist": {}, "external": 22.0, "enq": {"2026Q1": 2, "2026Q2": 2}, "ext_dpd": {"2026Q2": 95}, "returned": {"2026Q2": 2},
                "watch": {}, "dpd": {}, "stage": {"2026Q2": 2}, "coll": ("Cash Deposit", 0.5, 1), "cov": ("Current Ratio", 1.0), "conduct": conduct,
                "role": "affiliate", "parent": "CB09001"})
    out.append({"id": "CB09002", "name": sp2["co"]["name"], "group_id": "CG9002", "group_name": "Sawaed Group", "sector": "Construction",
                "sub_sector": "Building and Infrastructure Contracting", "region": "Eastern Province", "tier": "Core", "ratings": b2["ratings"]["CB09002"],
                "years": y2, "limits": [(L, {"2021Q3": 0.708, "2022Q4": 0.75, "2024Q4": 1.0}) for L in b2["limits"] if L["level"] == 2 and L["existing_mn"] > 0],
                "limit_hist": {}, "external": 125.0, "enq": {"2026Q2": 1}, "ext_dpd": {}, "returned": {}, "watch": {}, "dpd": {}, "stage": {},
                "coll": ("Receivables", 486.0 * 0.2, 4), "cov": ("DSCR", 1.25), "conduct": conduct, "role": "parent", "parent": "CB09002"})
    out.append({"id": "CB09003", "name": "Sawaed Heavy Equipment Rental Co.", "group_id": "CG9002", "group_name": "Sawaed Group", "sector": "Construction",
                "sub_sector": "Equipment Rental", "region": "Eastern Province", "tier": "Transactional", "ratings": b2["ratings"]["CB09003"],
                "years": {y: {"revenue": r, "ebitda": e, "operating_profit": e * 0.45, "finance_cost": 1.3, "operating_cash_flow": e * 0.55, "cash": 0.4,
                              "short_term_borrowings": 6.0, "current_portion_ltd": 2.6, "long_term_borrowings": 7.0, "current_assets": 12.0,
                              "current_liabilities": 27.0, "inventory": 0.5, "total_assets": 58.0, "net_profit": e * 0.1}
                          for y, r, e in ((2021, 21.0, 8.8), (2022, 22.4, 9.0), (2023, 22.9, 8.6), (2024, 23.6, 8.1), (2025, 24.1, 6.9), (2026, 21.5, 4.6))},
                "limits": [({"limit_id": "HE1", "limit_name": "Overdraft", "product_code": "OD", "existing_mn": 6.0, "outstanding_mn": 5.8}, {"2021Q3": 1.0}),
                           ({"limit_id": "HE2", "limit_name": "Term loan (equipment)", "product_code": "TERM", "existing_mn": 12.0, "outstanding_mn": 9.4}, {"2021Q3": 1.0})],
                "limit_hist": {}, "external": 4.1, "enq": {"2026Q2": 2}, "ext_dpd": {}, "returned": {"2026Q1": 1, "2026Q2": 1},
                "watch": {}, "dpd": {"2026Q2": 45}, "stage": {"2026Q2": 2}, "coll": ("Plant and Equipment", 16.0, 3), "cov": ("DSCR", 1.2), "conduct": conduct,
                "role": "affiliate", "parent": "CB09002"})
    return out


def _qyear(q: str) -> tuple[int, int]:
    return int(q[:4]), int(q[-1])


def _ttm(years: dict, q: str, k: str) -> float:
    y, n = _qyear(q)
    a, b = years.get(y - 1, years[min(years)]), years.get(y, years[max(years)])
    return round(a.get(k, 0.0) + (b.get(k, 0.0) - a.get(k, 0.0)) * n / 4, 3)


def _factor(hist: dict[str, float], q: str) -> float:
    f = None
    for k in sorted(hist):
        if k <= q:
            f = hist[k]
    return f if f is not None else hist[min(hist)]


def frames() -> dict[str, pd.DataFrame]:
    rows = {k: [] for k in ("corp_borrower", "corp_facility", "corp_collateral", "corp_covenant", "ews_corp", "bureau_corp", "ob_corp",
                            "rel_group", "rel_edge", "rel_person", "rel_shared")}
    order = {r: i for i, r in enumerate(MASTER_SCALE)}
    for B in _borrowers():
        prev_rating = None
        for qi, q in enumerate(QUARTERS):
            y = B["years"]
            rev, ebitda = _ttm(y, q, "revenue"), _ttm(y, q, "ebitda")
            debt = round(_ttm(y, q, "short_term_borrowings") + _ttm(y, q, "current_portion_ltd") + _ttm(y, q, "long_term_borrowings"), 3)
            cash = _ttm(y, q, "cash")
            fin_cost = max(_ttm(y, q, "finance_cost"), 0.1)
            r = _rating_at(B["ratings"], q)
            notches = 0 if prev_rating is None else order[prev_rating] - order[r]
            ca, cl, inv = _ttm(y, q, "current_assets"), _ttm(y, q, "current_liabilities"), _ttm(y, q, "inventory")
            watch = B["watch"].get(q, 0)
            rows["corp_borrower"].append({
                "tenant_id": T, "dataset_release_id": REL, "domain_id": "corporate", "reporting_currency": "SAR", "borrower_id": B["id"],
                "borrower_name": B["name"], "group_id": B["group_id"], "group_name": B["group_name"], "reporting_quarter": q, "sector": B["sector"],
                "sub_sector": B["sub_sector"], "region": B["region"], "relationship_tier": B["tier"], "rating_current": r,
                "rating_previous": prev_rating or r, "rating_at_origination": _rating_at(B["ratings"], QUARTERS[0]), "rating_notches_moved": notches,
                "rating_notches_from_origination": order[_rating_at(B["ratings"], QUARTERS[0])] - order[r],
                "rating_migration": "DOWNGRADE" if notches < 0 else ("UPGRADE" if notches > 0 else "STABLE"),
                "rating_outlook": "Negative" if order[r] >= order["B+"] or notches < 0 else "Stable",
                "rating_driver": "Liquidity" if notches < 0 else "None", "pd_ttc_12m": MASTER_SCALE[r], "revenue_sar_mn": rev, "ebitda_sar_mn": ebitda,
                "ebit_sar_mn": _ttm(y, q, "operating_profit"), "operating_cash_flow_sar_mn": _ttm(y, q, "operating_cash_flow"), "total_debt_sar_mn": debt,
                "cash_sar_mn": cash, "net_debt_sar_mn": round(debt - cash, 3), "leverage_x": round((debt - cash) / max(ebitda, 0.1), 3),
                "dscr_x": round(ebitda / (fin_cost + _ttm(y, q, "current_portion_ltd")), 3), "interest_cover_x": round(ebitda / fin_cost, 3),
                "current_ratio_x": round(ca / cl, 3), "quick_ratio_x": round((ca - inv) / cl, 3), "ebitda_margin_pct": round(100 * ebitda / rev, 3),
                "return_on_assets_pct": round(100 * _ttm(y, q, "net_profit") / max(_ttm(y, q, "total_assets"), 1), 3),
                "cash_conversion_pct": round(100 * _ttm(y, q, "operating_cash_flow") / max(ebitda, 0.1), 3), "qualitative_score": 70.0 if order[r] < order["BB"] else 55.0,
                "watchlist_flag": watch, "watchlist_reason": "Past due at another lender; returned cheques" if watch else "", "restructured_flag": 0,
                "quarters_on_watchlist": watch})
            prev_rating = r
            # account conduct of the quarter (when the Bank has it) feeds open banking
            mm = [f"{q[:4]}-{m:02d}" for m in range(3 * int(q[-1]) - 2, 3 * int(q[-1]) + 1)]
            cr = [B["conduct"].get(B["id"] + m) for m in mm]
            infl = round(sum(c["credit_turnover_mn"] for c in cr), 3) if all(cr) else round(rev / 4 * 1.08, 3)
            yq = f"{int(q[:4]) - 1}{q[4:]}"
            mm_y = [f"{yq[:4]}-{m:02d}" for m in range(3 * int(q[-1]) - 2, 3 * int(q[-1]) + 1)]
            cy = [B["conduct"].get(B["id"] + m) for m in mm_y]
            infl_y = sum(c["credit_turnover_mn"] for c in cy) if all(cy) else (_ttm(y, yq, "revenue") / 4 * 1.08 if int(yq[:4]) >= 2021 else infl)
            trend = round(100 * (infl / infl_y - 1), 1) if infl_y else 0.0
            ret = B["returned"].get(q, 0)
            rows["ob_corp"].append({"tenant_id": T, "borrower_id": B["id"], "reporting_quarter": q, "operating_inflows_sar_mn": infl, "inflow_trend_pct": trend,
                                    "balance_buffer_months": 0.6 if B["id"] == "CB09003" and q >= "2026Q1" else 1.8, "returned_payments_q": ret,
                                    "external_first_flag": 0})
            ext_dpd = B["ext_dpd"].get(q, 0)
            enq = B["enq"].get(q, 0)
            rows["bureau_corp"].append({"tenant_id": T, "borrower_id": B["id"], "reporting_quarter": q, "external_exposure_sar_mn": B["external"],
                                        "external_dpd_days": ext_dpd, "external_default_flag": 0, "enquiries_q": enq, "external_first_flag": 0})
            stage = B["stage"].get(q, 1)
            dpd = B["dpd"].get(q, 0)
            for li, (L, hist) in enumerate(B["limits"]):
                fid = f"CF{B['id'][2:]}{li + 1:02d}"
                prod, cls = PRODUCT.get(L["product_code"], ("working_capital", "funded"))
                lim = round(L["existing_mn"] * _factor(hist, q), 3)
                util = (L["outstanding_mn"] / L["existing_mn"]) if L["existing_mn"] else 0.0
                util = min(1.0, util * (0.85 + 0.15 * qi / 19))
                drawn = round(lim * util, 3)
                ead = round(drawn + (0.5 if cls == "funded" else 0.2) * (lim - drawn), 3)
                pd12 = MASTER_SCALE[r]
                pdl = round(1 - (1 - pd12) ** 3, 6)
                lgd = 42.0 if cls == "funded" else 54.0
                e12, elt = round(pd12 * lgd / 100 * ead, 4), round(pdl * lgd / 100 * ead, 4)
                ecl = elt if stage >= 2 else e12
                fac = {"tenant_id": T, "dataset_release_id": REL, "domain_id": "corporate", "reporting_currency": "SAR", "facility_id": fid,
                       "borrower_id": B["id"], "borrower_name": B["name"], "reporting_quarter": q, "product_type": prod, "facility_class": cls,
                       "sector": B["sector"], "sub_sector": B["sub_sector"], "region": B["region"], "relationship_tier": B["tier"], "limit_sar_mn": lim,
                       "drawn_sar_mn": drawn, "undrawn_sar_mn": round(lim - drawn, 3), "utilisation_pct": round(100 * util, 3), "ead_sar_mn": ead,
                       "stage": stage, "sicr_flag": int(stage >= 2), "default_flag": 0, "dpd_days": dpd, "pd_pit_12m": pd12, "pd_lifetime": pdl,
                       "lgd_pct": lgd, "ecl_12m_sar_mn": e12, "ecl_lifetime_sar_mn": elt, "ecl_sar_mn": ecl, "ecl_coverage_pct": round(100 * ecl / max(ead, 0.001), 3),
                       "write_off_sar_mn": 0.0, "recovery_sar_mn": 0.0, "cure_flag": 0, "past_due_flag": int(dpd > 0), "quarters_in_stage": 1,
                       "origination_quarter": QUARTERS[0]}
                rows["corp_facility"].append(fac)
                ctype, cval, age = B["coll"]
                cv = round(cval * (lim / max(sum(x[0]["existing_mn"] for x in B["limits"]), 0.1)), 3)
                rows["corp_collateral"].append({"tenant_id": T, "dataset_release_id": REL, "domain_id": "corporate", "reporting_currency": "SAR",
                                                "collateral_id": f"CC{B['id'][2:]}{li + 1:02d}", "facility_id": fid, "borrower_id": B["id"], "reporting_quarter": q,
                                                "collateral_type": ctype, "sector": B["sector"], "market_value_sar_mn": cv, "haircut_pct": 30.0,
                                                "allocated_value_sar_mn": round(cv * 0.7, 3), "coverage_pct": round(100 * cv * 0.7 / max(ead, 0.001), 3),
                                                "ltv_pct": round(100 * ead / max(cv, 0.001), 3), "valuation_age_quarters": age})
                ctyp, thr = B["cov"]
                obs = {"Current Ratio": ca / cl, "DSCR": ebitda / (fin_cost + _ttm(y, q, "current_portion_ltd")),
                       "Leverage": (debt - cash) / max(ebitda, 0.1)}[ctyp]
                breach = (obs > thr) if ctyp == "Leverage" else (obs < thr)
                rows["corp_covenant"].append({"tenant_id": T, "dataset_release_id": REL, "domain_id": "corporate", "reporting_currency": "SAR",
                                              "covenant_id": f"CV{B['id'][2:]}{li + 1:02d}", "facility_id": fid, "borrower_id": B["id"], "reporting_quarter": q,
                                              "sector": B["sector"], "covenant_type": ctyp, "threshold_value": thr, "observed_value": round(obs, 3),
                                              "headroom_pct": round(100 * ((thr - obs) / thr if ctyp == "Leverage" else (obs - thr) / thr), 3),
                                              "test_status": "BREACH" if breach else "PASS", "breach_flag": int(breach), "waiver_flag": 0, "waiver_status": "NONE",
                                              "waiver_quarter": "", "consecutive_breaches": int(breach)})
                ews = dict(fac)
                ews.update({"ews_release_id": paths.EWS_CORP, "source_release_id": REL, "source_dataset_release_id": REL, "source_table": "corp_facility_quarter",
                            "ews_grain": "facility_quarter", "watchlist_flag": watch, "rating_notches_moved": notches, "covenant_breaches": float(int(breach)),
                            "collateral_value_sar_mn": round(cv * 0.7, 3), "collateral_ltv_pct": round(100 * ead / max(cv, 0.001), 3),
                            "external_exposure_sar_mn": B["external"], "external_dpd_days": ext_dpd, "external_default_flag": 0, "enquiries_q": enq,
                            "operating_inflows_sar_mn": infl, "inflow_trend_pct": trend, "balance_buffer_months": rows["ob_corp"][-1]["balance_buffer_months"],
                            "returned_payments_q": ret, "ews_ruleset_version": "gw-ews-1.3.0"})
                rows["ews_corp"].append(ews)
            rows["rel_group"].append({"tenant_id": T, "reporting_quarter": q, "group_id": B["group_id"], "group_name": B["group_name"],
                                      "legacy_group_id": B["group_id"], "legacy_group_name": B["group_name"], "borrower_id": B["id"], "role": B["role"],
                                      "ownership_pct": 100.0 if B["role"] == "parent" else 0.0, "parent_borrower_id": B["parent"]})
    # edges and persons (every quarter)
    edges = [("SUPPLIES", "CB09005", "CB09001", "laboratory equipment servicing; SAR 5.0m due to the borrower", None),
             ("SUPPLIES", "CB09003", "CB09002", "equipment hire; advances due to the borrower SAR 24.6m", None)]
    for q in QUARTERS:
        for i, (t, s, d, det, g) in enumerate(edges, 1):
            rows["rel_edge"].append({"tenant_id": T, "reporting_quarter": q, "edge_id": f"ER16{i:02d}", "rel_type": t, "source_borrower_id": s,
                                     "target_borrower_id": d, "relation_detail": det, "group_id": g, "ownership_pct": None,
                                     "purchase_share_pct": 4.3 if s == "CB09003" else 1.2, "revenue_share_pct": 80.0 if s == "CB09003" else 9.0,
                                     "annual_value_sar_mn": 17.8 if s == "CB09003" else 2.6, "facility_id": None, "book_collateral_id": None,
                                     "guarantee_amount_sar_mn": None, "collateral_id": None})
    persons = [("PR1601", "Fahad Saad Al-Naseem", "CB09001", "Chairman", 68.0), ("PR1602", "Majed Saad Al-Naseem", "CB09001", "Director", 32.0),
               ("PR1602", "Majed Saad Al-Naseem", "CB09005", "CEO", None), ("PR1601", "Fahad Saad Al-Naseem", "CB09005", "Owner", 60.0),
               ("PR1603", "Turki Hamad Al-Sawaed", "CB09002", "Chairman", 65.0), ("PR1604", "Nasser Hamad Al-Sawaed", "CB09002", "Director", 35.0),
               ("PR1604", "Nasser Hamad Al-Sawaed", "CB09003", "Owner", 100.0)]
    for pid, n, b, role, pct in persons:
        rows["rel_person"].append({"tenant_id": T, "person_id": pid, "person_name": n, "borrower_id": b, "role": role, "ownership_pct": pct,
                                   "valid_from_quarter": QUARTERS[0], "valid_to_quarter": None})
    out = {k: pd.DataFrame(v) for k, v in rows.items() if v}
    # EWS score and band with the live rule set
    e = out["ews_corp"]
    con = duckdb.connect()
    con.register("e", e)
    terms = " + ".join(f"(CASE WHEN {r['sql']} THEN {r['weight']} ELSE 0 END)" for r in ews_rules.RULES["corporate"])
    labels = [f"CASE WHEN {r['sql']} THEN '{r['label']}' END" for r in ews_rules.RULES["corporate"]]
    res = con.execute(f"SELECT {terms} AS s, concat_ws('; ', {', '.join(labels)}) AS why FROM e").df()
    e["ews_score"] = res["s"].astype("int32")
    e["ews_reasons"] = res["why"].fillna("")
    mod, high, crit = ews_rules.BAND_FLOORS["corporate"]
    e["ews_band"] = e["ews_score"].map(lambda s: "critical" if s >= crit else "high" if s >= high else "moderate" if s >= mod else "low" if s >= 1 else "none")
    return out


def write() -> dict[str, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, df in frames().items():
        schema = pq.read_schema(paths.RELATIONS[name])
        df = df[[f.name for f in schema]]
        table = pa.Table.from_pandas(df, schema=schema.remove_metadata(), preserve_index=False)
        pq.write_table(table, OUT / f"{name}.parquet")
        counts[name] = len(df)
    (OUT / "README.md").write_text("# Borrower 360 overlay (R16 d)\n\nFictional demo customers 1 and 2 and their connected parties "
                                   "(CB09001-CB09005), 2021Q3-2026Q2, in the corporate book's columns. Read by backend/b360/store.py beside the book "
                                   "(set B360_OVERLAY=off to hide). Generated by `python -m ops.r16_customers.b360`.\n\n"
                                   + json.dumps(counts, indent=1) + "\n")
    return counts


if __name__ == "__main__":
    print(write())
