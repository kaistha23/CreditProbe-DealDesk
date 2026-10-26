"""The contract-shaped reference engine: the Deal Desk engine API of
docs/v5/DEALDESK_API.md (Session C1), served only while `backend.dealdesk` is
not in this checkout.

Same paths, same request and response schemas, deterministic, with the
formulas of DEAL_DESK_PROMPT 3.1-3.6 in their simplest form. When the C1
engine is importable, `engine.py` routes every call to it and this module is
not used.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query

RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
           "B+", "B", "B-", "CCC", "CC", "C"]
PD_TTC = dict(zip(RATINGS, [0.0003, 0.0004, 0.0005, 0.0006, 0.0008, 0.0010, 0.0013, 0.0018, 0.0025, 0.0035,
                            0.0055, 0.0080, 0.0120, 0.0180, 0.0270, 0.0400, 0.1000, 0.1800, 0.2700]))
FACILITY_TYPES = ["term_loan", "revolver", "performance_lg", "financial_lg", "trade_lc"]
STRUCTURES = ["conventional", "murabaha", "tawarruq", "ijara", "musharaka"]
STATUSES = ["new", "in_review", "counter_offered", "approved", "declined"]
SECTORS = ["Contracting", "Real Estate", "Manufacturing", "Trading", "Healthcare", "Government-linked Suppliers", "SME"]
STRESS = [("downgrade_1", "Rating −1 notch", {"rating_shift": 1}), ("downgrade_2", "Rating −2 notches", {"rating_shift": 2}),
          ("collateral_20", "Collateral value −20%", {"collateral_shock": 0.20}),
          ("collateral_30", "Collateral value −30%", {"collateral_shock": 0.30}),
          ("saibor_200", "SAIBOR +200 bps", {"rate_shock_bps": 200}), ("utilisation", "Utilisation shock", {"utilisation_shock": 40})]
WEIGHTS = {"amount": 5.0, "tenor": 4.0, "margin": 3.0, "collateral": 2.0, "fees": 1.0}


def _rw(rating: str) -> float:
    i = RATINGS.index(rating)
    return 0.20 if i <= 3 else 0.50 if i <= 6 else 0.75 if i <= 9 else 1.00 if i <= 12 else 1.50


P = {
    "version": "ref-1", "hurdle": 0.15, "capital_ratio": 0.125, "capital_credit": 0.05, "zakat": 0.20, "discount": 0.10,
    "usd_sar": 3.75, "lgd_unsecured": 0.45, "lgd_floor": 0.10,
    "haircut": {"real_estate": 0.40, "cash": 0.0, "shares": 0.35, "receivables": 0.50, "plant_equipment": 0.55, "vehicles": 0.50},
    "structure_lgd": {"murabaha": 1.00, "tawarruq": 1.00, "ijara": 0.85, "musharaka": 1.10, "conventional": 1.00},
    "ccf": {"performance_lg": 0.50, "financial_lg": 1.00, "trade_lc": 0.20, "revolver_undrawn": 0.40},
    "ftp_base": {"SAR": 0.0550, "USD": 0.0480}, "lp_per_year": 0.0008,
    "opex_origination": 0.0025, "opex_servicing": 0.0020, "oprisk_share": 0.15,
    "tier1": 12000.0, "large_exposure_pct": 0.25, "min_rating": "B-",
    "max_tenor": {"A": 10, "BBB": 8, "BB": 6, "B": 4, "CCC": 2},
    "min_dscr": 1.25, "max_debt_ebitda": 4.5, "max_ltv": 0.70, "rwa_budget": 6000.0, "sector_cap_pct": 0.22,
    "doa": [(150, "Head of Credit"), (500, "Chief Risk Officer"), (1500, "Executive Credit Committee"), (1e12, "Board Credit Committee")],
    "margin_bounds": (125, 500), "upfront_bounds": (25, 150), "min_amount_share": 0.60,
}
PORTFOLIO = {"total": 101_500.0, "rwa_used": 4200.0,
             "sector": {"Contracting": 21_800.0, "Real Estate": 23_400.0, "Manufacturing": 14_100.0, "Trading": 15_900.0,
                        "Healthcare": 6_200.0, "Government-linked Suppliers": 9_800.0, "SME": 10_300.0},
             "collateral_type": {"real_estate": 31_200.0, "cash": 4_100.0, "receivables": 9_700.0, "shares": 2_900.0,
                                 "plant_equipment": 5_400.0, "unsecured": 48_200.0}}
COLLATERAL_CAP = {"real_estate": 0.33}


def _bucket(rating: str) -> str:
    i = RATINGS.index(rating)
    return "A" if i <= 6 else "BBB" if i <= 9 else "BB" if i <= 12 else "B" if i <= 15 else "CCC"


def _trace(kind: str, payload: Any) -> str:
    return "DT-" + hashlib.sha256(json.dumps([kind, payload], sort_keys=True, default=str).encode()).hexdigest()[:12]


# ------------------------------------------------------------------ proposals

NAMES = ["Al Waha Contracting", "Najd Towers Real Estate", "Eastern Polymers Industries", "Red Sea Trading House",
         "Riyadh Care Hospitals", "Hijaz Supply Services", "Qassim Foods", "Gulf Steel Fabrication",
         "Al Khobar Logistics Trading", "Tabuk Cement Manufacturing", "Makkah Hospitality Real Estate",
         "Jazan Medical Supplies", "Al Ahsa Dates", "Dammam Marine Contracting", "Yanbu Petrochem Services"]
REGIONS = ["Riyadh", "Riyadh", "Eastern Province", "Makkah", "Riyadh", "Makkah", "Qassim", "Eastern Province",
           "Eastern Province", "Tabuk", "Makkah", "Jazan", "Eastern Province", "Eastern Province", "Madinah"]
RMS = ["Faisal Al-Harbi", "Noura Al-Qahtani", "Omar Al-Shehri", "Layla Al-Otaibi", "Khalid Al-Dosari"]


def _seed() -> list[dict]:
    rnd = random.Random(20261011)
    ratings = ["BBB", "BB+", "A-", "A", "BBB-", "A", "B+", "BB-", "BBB+", "BB", "A-", "B", "BB+", "CCC", "BBB"]
    out = []
    for i, name in enumerate(NAMES):
        sector = SECTORS[i % len(SECTORS)]
        rating = ratings[i]
        existing = i % 3 != 2
        ft = ["term_loan", "revolver", "performance_lg", "term_loan", "trade_lc"][i % 5]
        amount = 2600.0 if i == 1 else float(round(rnd.uniform(60, 650) / 5) * 5)
        revenue = amount * rnd.uniform(5.0, 11.0)
        ebitda = revenue * rnd.uniform(0.10, 0.22)
        debt = ebitda * rnd.uniform(1.0, 3.2)
        coll = []
        if i % 4 != 3:
            coll.append({"collateral_id": "C1", "type": "real_estate" if sector in ("Real Estate", "Contracting") else "receivables",
                         "value": round(amount * rnd.uniform(0.9, 1.8), 1), "currency": "SAR", "valuation_date": "2026-06-30",
                         "pledged_in_ask": i % 2 == 0})
        coll.append({"collateral_id": "C2", "type": "shares", "value": round(amount * 0.3, 1), "currency": "SAR",
                     "valuation_date": "2026-09-30", "pledged_in_ask": False})
        ask = {"facility_type": ft, "structure": STRUCTURES[(i + 1) % 5], "currency": "USD" if i % 5 == 4 else "SAR",
               "amount": amount, "tenor_years": [5, 3, 7, 4, 2][i % 5], "grace_years": [1, 0, 1, 0, 0][i % 5],
               "amortisation": ["equal", "bullet", "equal", "balloon", "bullet"][i % 5], "balloon_pct": 40 if i % 5 == 3 else 0,
               "margin_bps": int(rnd.choice([150, 175, 200, 225, 250, 275])), "upfront_fee_bps": 50,
               "commitment_fee_bps": 25 if ft == "revolver" else 0, "commission_bps": 100 if ft in ("performance_lg", "trade_lc") else 0,
               "utilisation_pct": 60 if ft == "revolver" else 100, "funded_share_pct": 100 if ft in ("term_loan", "revolver") else 0,
               "unfunded_type": ft if ft not in ("term_loan", "revolver") else "performance_lg", "cash_margin_pct": 0,
               "collateral_ids": [c["collateral_id"] for c in coll if c["pledged_in_ask"]],
               "guarantee_id": "G1" if i % 4 == 1 else None, "guarantee_coverage_pct": 50 if i % 4 == 1 else 0,
               "covenant_package": "standard"}
        case = {1: "large_exposure", 3: "easy", 8: "concentrated_sector", 13: "infeasible"}.get(i, "")
        if i == 3:
            ask["margin_bps"] = 300
        if i == 13:
            ask["margin_bps"] = 150
        out.append({
            "proposal_id": f"DD-{i + 1:02d}", "status": STATUSES[i % 5] if i > 4 else "new", "rm": RMS[i % len(RMS)],
            "business_unit": "Corporate Banking", "received": f"2026-10-{1 + (i % 10):02d}", "purpose": "Working capital and capex",
            "obligor": {"obligor_id": f"CB{10_000 + i * 37:05d}" if existing else f"DN{i + 1:03d}", "existing": existing, "name": name,
                        "cr_number": f"10{rnd.randint(10_000_000, 99_999_999)}", "group_id": f"CG{4100 + i}",
                        "group_name": f"{name.split()[0]} {name.split()[1]} Group", "connected_parties": [f"CB{20_000 + i * 11 + k:05d}" for k in range(1 + i % 4)],
                        "sector": sector, "sub_sector": sector, "sector_code": "", "segment": sector, "region": REGIONS[i],
                        "sme": sector == "SME", "gre": sector == "Government-linked Suppliers", "internal_rating": rating,
                        "external_rating": None, "pd_master_scale": PD_TTC[rating], "simah_flag": "clear" if i % 6 else "watch",
                        "existing_exposure_sar_mn": round(amount * rnd.uniform(0.2, 0.9), 1) if existing else 0.0, "existing_facilities": []},
            "financials": {"currency": "SAR", "years": [
                {"year": y, "kind": "projection" if y > 2025 else "actual", "revenue": round(revenue * f, 1), "ebitda": round(ebitda * f, 1),
                 "total_debt": round(debt * f, 1), "debt_service": round(debt * f * 0.22, 1), "net_worth": round(revenue * 0.4 * f, 1),
                 "current_ratio": round(rnd.uniform(1.0, 1.9), 2)}
                for y, f in zip([2023, 2024, 2025, 2026, 2027], [0.86, 0.93, 1.0, 1.06, 1.12])]},
            "ask": ask,
            "security": {"collateral": coll,
                         "guarantees": [{"guarantee_id": "G1", "type": "corporate" if i % 2 else "kafalah", "guarantor": f"{name.split()[0]} Holding",
                                         "guarantor_rating": RATINGS[max(0, RATINGS.index(rating) - 2)], "coverage_pct": 50,
                                         "offered_in_ask": i % 4 == 1}],
                         "covenant_package": "standard", "covenants": [{"type": "DSCR", "threshold": 1.25}, {"type": "Debt/EBITDA", "threshold": 4.0}]},
            "business_case": {"ancillary_income_sar_mn_pa": {"cash_management": round(amount * 0.002, 2), "payroll": round(amount * 0.001, 2),
                                                             "fx": round(amount * 0.0015, 2), "trade": round(amount * 0.001, 2)}},
            "memo": f"DD-{i + 1:02d}.docx", "case": case})
    return out


_PROPOSALS: dict[str, dict] = {p["proposal_id"]: p for p in _seed()}


def _get(pid: str) -> dict:
    if pid not in _PROPOSALS:
        raise HTTPException(404, f"{pid} is not a Deal Desk proposal.")
    return _PROPOSALS[pid]


def summary(p: dict) -> dict:
    a = p["ask"]
    fx = P["usd_sar"] if a["currency"] == "USD" else 1.0
    return {"proposal_id": p["proposal_id"], "status": p["status"], "obligor_name": p["obligor"]["name"], "existing": p["obligor"]["existing"],
            "sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"], "rm": p["rm"], "facility_type": a["facility_type"],
            "structure": a["structure"], "currency": a["currency"], "amount": a["amount"], "amount_sar_mn": round(a["amount"] * fx, 3),
            "tenor_years": a["tenor_years"], "received": p["received"], "case": p.get("case", "")}


# ------------------------------------------------------------------ compute

def _merge(p: dict, terms: dict | None) -> dict:
    t = dict(p["ask"])
    t.update({k: v for k, v in (terms or {}).items() if v is not None or k == "guarantee_id"})
    t["tenor_years"] = max(1, min(10, int(round(float(t["tenor_years"])))))
    t["grace_years"] = max(0, min(int(t.get("grace_years") or 0), t["tenor_years"] - 1))
    return t


def compute(pid: str, terms: dict | None = None, rating_shift: int = 0, collateral_shock: float = 0.0,
            rate_shock_bps: int = 0, utilisation_shock: float = 0.0, el_view: str = "economic") -> dict:
    p = _get(pid)
    t = _merge(p, terms)
    ob = p["obligor"]
    i0 = RATINGS.index(ob["internal_rating"])
    rating = RATINGS[max(0, min(len(RATINGS) - 1, i0 + rating_shift))]
    pd12 = min(0.999, PD_TTC[rating] * 1.08)
    fx = P["usd_sar"] if t["currency"] == "USD" else 1.0
    amount = float(t["amount"]) * fx
    n, grace = t["tenor_years"], t["grace_years"]
    funded_share = float(t.get("funded_share_pct", 100)) / 100
    ft = t["facility_type"]
    util = min(1.0, (float(t.get("utilisation_pct", 100)) + utilisation_shock) / 100)
    ccf_un = P["ccf"].get(t.get("unfunded_type") or ft, 0.5)
    cash = amount * float(t.get("cash_margin_pct") or 0) / 100
    items = [c for c in p["security"]["collateral"] if c["collateral_id"] in (t.get("collateral_ids") or [])]
    recog = sum(c["value"] * (1 - collateral_shock) * (1 - P["haircut"].get(c["type"], 0.5)) for c in items)
    g = next((x for x in p["security"]["guarantees"] if x["guarantee_id"] == t.get("guarantee_id")), None)
    cover = float(t.get("guarantee_coverage_pct") or 0) / 100 if g else 0.0
    base = P["ftp_base"][t["currency"]] + rate_shock_bps / 10_000
    margin = t["margin_bps"] / 10_000
    lp = P["lp_per_year"] * n
    balloon = float(t.get("balloon_pct") or 0) / 100 if t.get("amortisation") == "balloon" else (1.0 if t.get("amortisation") == "bullet" else 0.0)
    amort_years = max(1, n - grace)
    bal = amount * funded_share
    unf = amount * (1 - funded_share)
    pnl, schedule, cap_rows, lgds = [], [], [], []
    surv = 1.0
    rap_pv = cap_pv = sva_pv = anc_pv = 0.0
    tot = {k: 0.0 for k in ("profit_income", "fees", "ftp", "opex", "el", "zakat", "capital_benefit")}
    anc = sum(p["business_case"]["ancillary_income_sar_mn_pa"].values()) * 0.7
    first: dict[str, float] = {}
    for y in range(1, n + 1):
        principal = 0.0 if y <= grace else (bal if y == n else amount * funded_share * (1 - balloon) / amort_years)
        start, end = bal, max(0.0, bal - principal)
        avg = (start + end) / 2 if principal else start
        drawn = avg * (util if ft == "revolver" else 1.0)
        undrawn = avg - drawn
        ead = drawn + P["ccf"]["revolver_undrawn"] * undrawn + ccf_un * unf * util
        ead_net = max(0.0, ead - cash)
        secured = min(ead_net, recog)
        lgd = 0.0 if ead <= 0 else max(P["lgd_floor"], (ead_net - secured) / ead * P["lgd_unsecured"]) * P["structure_lgd"].get(t["structure"], 1.0)
        pd_m = surv * pd12
        surv *= 1 - pd12
        g_rw = 0.0 if g and g["type"] in ("government", "kafalah") else _rw(g["guarantor_rating"]) if g else 0.0
        el = pd_m * lgd * ead_net * (1 - cover) + pd_m * 0.1 * lgd * ead_net * cover
        rwa = ead_net * ((1 - cover) * _rw(rating) + cover * g_rw)
        profit = drawn * (base + margin)
        fees = amount * t.get("upfront_fee_bps", 0) / 10_000 / n
        commit = undrawn * t.get("commitment_fee_bps", 0) / 10_000
        comm = unf * t.get("commission_bps", 0) / 10_000
        ftp = drawn * (base + lp) - cash * base
        opex = (amount * P["opex_origination"] if y == 1 else 0) + (avg + unf) * P["opex_servicing"]
        op_cap = P["oprisk_share"] * max(0.0, profit - drawn * base + fees + commit + comm)
        capital = rwa * P["capital_ratio"] + op_cap
        cap_b = capital * P["capital_credit"]
        pre = profit + fees + commit + comm - ftp - opex - el
        zakat = max(0.0, pre) * P["zakat"]
        rap = pre - zakat + cap_b
        df = (1 + P["discount"]) ** -y
        rap_pv += rap * df
        cap_pv += capital * df
        sva_pv += (rap - P["hurdle"] * capital) * df
        anc_pv += anc * df
        for k, v in (("profit_income", profit), ("fees", fees + commit + comm), ("ftp", ftp), ("opex", opex), ("el", el),
                     ("zakat", zakat), ("capital_benefit", cap_b)):
            tot[k] += v * df
        if y == 1:
            first = {"rwa": rwa + op_cap / P["capital_ratio"], "capital": capital, "el": el, "lgd": lgd, "ead": ead_net}
        lgds.append(round(lgd, 4))
        ds = principal + drawn * (base + margin)
        schedule.append({"year": y, "drawn_start": round(start, 3), "drawn_end": round(end, 3), "drawn_avg": round(drawn, 3),
                         "undrawn_avg": round(undrawn, 3), "unfunded_avg": round(unf, 3), "ead": round(ead_net, 3),
                         "principal": round(principal, 3), "profit_paid": round(profit, 3), "debt_service": round(ds, 3)})
        cap_rows.append({"year": y, "rwa": round(rwa, 3), "regulatory": round(rwa * P["capital_ratio"], 4), "economic": round(rwa * P["capital_ratio"] * 0.8, 4),
                         "operational": round(op_cap, 4), "capital": round(capital, 4)})
        pnl.append({"year": y, "profit_income": round(profit, 4), "fee_income": round(fees, 4), "commitment_fee": round(commit, 4),
                    "commission": round(comm, 4), "ftp": round(ftp, 4), "opex": round(opex, 4), "el": round(el, 4),
                    "day_one_ecl": round(pd12 * lgd * ead_net, 4) if y == 1 else 0.0, "ecl_change": 0.0, "credit_cost": round(el, 4),
                    "zakat": round(zakat, 4), "capital_benefit": round(cap_b, 4), "rap": round(rap, 4), "capital": round(capital, 4),
                    "raroc": round(rap / capital, 6) if capital else 0.0, "discount": round(df, 6), "ancillary": round(anc, 4)})
        bal = end
    raroc = rap_pv / cap_pv if cap_pv else 0.0
    rel_raroc = (rap_pv + anc_pv * (1 - P["zakat"])) / cap_pv if cap_pv else 0.0
    fin = next(x for x in p["financials"]["years"] if x["year"] == 2025)
    year1_ds = schedule[0]["debt_service"] if schedule else 0.0
    new_ds = fin["debt_service"] + max(year1_ds, amount * funded_share / n)
    dscr = fin["ebitda"] / new_ds if new_ds else None
    d_e = (fin["total_debt"] + amount * funded_share) / fin["ebitda"] if fin["ebitda"] else None
    cons = _constraints(p, t, rating, amount, n, first.get("rwa", 0.0), dscr, d_e, items, balloon)
    soft = [c for c in cons if c["status"] == "breach" and c["kind"] == "soft"]
    hard = [c for c in cons if c["status"] == "breach" and c["kind"] == "hard"]
    clears = raroc >= P["hurdle"]
    metrics = {"amount_sar_mn": round(amount, 3), "lifetime_raroc": round(raroc, 6), "hurdle": P["hurdle"], "clears_hurdle": clears,
               "sva": round(sva_pv, 4), "breakeven_margin_bps": None, "relationship_raroc": round(rel_raroc, 6),
               "relationship_sva": round(sva_pv + anc_pv * (1 - P["zakat"]), 4), "rwa_y1": round(first.get("rwa", 0), 3),
               "capital_y1": round(first.get("capital", 0), 4), "el_y1": round(first.get("el", 0), 4), "el_lifetime_pv": round(tot["el"], 4),
               "day_one_ecl": pnl[0]["day_one_ecl"], "pd_12m": round(pd12, 6), "lgd_y1": round(first.get("lgd", 0), 4),
               "ead_y1": round(first.get("ead", 0), 3), "dscr_post": round(dscr, 3) if dscr else None,
               "debt_ebitda_post": round(d_e, 3) if d_e else None, "robustness_notches": None}
    rap_total = tot["profit_income"] + tot["fees"] - tot["ftp"] - tot["opex"] - tot["el"] - tot["zakat"] + tot["capital_benefit"]
    waterfall = [{"step": "Profit income", "value": round(tot["profit_income"], 4)}, {"step": "Fees", "value": round(tot["fees"], 4)},
                 {"step": "FTP", "value": -round(tot["ftp"], 4)}, {"step": "Opex", "value": -round(tot["opex"], 4)},
                 {"step": "Expected loss", "value": -round(tot["el"], 4)}, {"step": "Zakat", "value": -round(tot["zakat"], 4)},
                 {"step": "Capital benefit", "value": round(tot["capital_benefit"], 4)},
                 {"step": "Risk-adjusted profit", "value": round(rap_total, 4), "total": True}]
    level = _approval(amount + ob["existing_exposure_sar_mn"], rating, soft)
    oor = [{"feature": "debt_ebitda_post", "value": round(d_e, 3), "p01": 0.2, "p99": 6.0, "min": 0.0, "max": 8.0, "status": "out_of_range"}] \
        if d_e and d_e > 6.0 else []
    return {"trace_id": _trace("compute", [pid, t, rating_shift, collateral_shock, rate_shock_bps, utilisation_shock]),
            "proposal_id": pid, "terms": t, "el_view": el_view, "capital_basis": "max", "fx_to_sar": fx, "metrics": metrics,
            "pd": {"model_version": "reference", "model_pd_12m": round(pd12, 6), "master_scale_pd_12m": PD_TTC[rating], "ttc_pd": PD_TTC[rating],
                   "term_structure": [{"year": r["year"], "marginal": round(pd12 * (1 - pd12) ** (r["year"] - 1), 6),
                                       "cumulative": round(1 - (1 - pd12) ** r["year"], 6), "source": "reference"} for r in pnl],
                   "out_of_range": {"status": "out_of_range" if oor else "in_range", "features": oor},
                   "monotonicity": {"status": "pass", "grid_points": 0, "adjustments": []},
                   "covenant_overlay": {"package": t.get("covenant_package", "standard"), "pd_multiplier": 1.0, "lgd_multiplier": 1.0}},
            "lgd": {"unsecured": P["lgd_unsecured"], "structure_multiplier": P["structure_lgd"].get(t["structure"], 1.0), "floor": P["lgd_floor"],
                    "collateral_recognised_sar_mn": round(recog, 3), "guarantee": g, "by_year": lgds},
            "schedule": schedule, "capital": {"basis": "max", "by_year": cap_rows}, "pnl": pnl, "waterfall": waterfall,
            "constraints": cons, "approval": level, "param_versions": {"all": P["version"]},
            "_rating": rating, "_hard": [c["name"] for c in hard]}


def _constraints(p, t, rating, amount, n, rwa, dscr, d_e, items, balloon) -> list[dict]:
    ob = p["obligor"]
    group_before = ob["existing_exposure_sar_mn"] + (5900.0 if p.get("case") == "large_exposure" else 400.0)
    sector_before = PORTFOLIO["sector"].get(ob["sector"], 0.0) + (900.0 if p.get("case") == "concentrated_sector" else 0.0)
    re_val = sum(c["value"] for c in items if c["type"] == "real_estate")
    rows = []

    def row(name, label, scope, before, deal, limit, unit, kind, basis, higher_is_worse=True):
        if before is None:
            return
        value = before + deal
        head = (limit - value) if higher_is_worse else (value - limit)
        rows.append({"name": name, "label": label, "scope": scope, "value": round(value, 4), "limit": round(limit, 4),
                     "headroom": round(head, 4), "unit": unit, "kind": kind, "status": "pass" if head >= -1e-9 else "breach",
                     "before": round(before, 4), "deal": round(deal, 4), "basis": basis})
    row("single_name", "Single name", ob["name"], ob["existing_exposure_sar_mn"], amount, 0.10 * P["tier1"], "SAR m", "hard", "10% of Tier 1")
    row("group_large_exposure", "Group large exposure", ob["group_name"], group_before, amount, P["large_exposure_pct"] * P["tier1"], "SAR m", "hard",
        f"25% of Tier 1 (SAR {P['tier1']:,.0f}m)")
    row("sector", "Sector concentration", ob["sector"], sector_before / (PORTFOLIO["total"] + amount), amount / (PORTFOLIO["total"] + amount),
        P["sector_cap_pct"], "share", "soft", "Share of the corporate book")
    if re_val:
        row("collateral_type", "Real-estate collateral concentration", "Real estate", PORTFOLIO["collateral_type"]["real_estate"] / PORTFOLIO["total"],
            0.0, COLLATERAL_CAP["real_estate"], "share", "soft", "Share of the corporate book")
    row("min_rating", "Minimum rating for new business", rating, -RATINGS.index(rating), 0, -RATINGS.index(P["min_rating"]), "notch", "hard",
        f"{P['min_rating']} or better", higher_is_worse=False)
    row("max_tenor", "Maximum tenor for the grade", rating, n, 0, P["max_tenor"][_bucket(rating)], "years", "hard", f"Grade bucket {_bucket(rating)}")
    if re_val:
        row("ltv", "Maximum LTV", "Pledged real estate", amount / re_val, 0, P["max_ltv"], "ratio", "soft", "Amount over pledged real-estate value")
    if dscr is not None:
        row("dscr", "Minimum DSCR after the deal", ob["name"], dscr, 0, P["min_dscr"], "x", "soft", "EBITDA over debt service", higher_is_worse=False)
    if d_e is not None:
        row("debt_ebitda", "Maximum Debt/EBITDA after the deal", ob["name"], d_e, 0, P["max_debt_ebitda"], "x", "soft", "Total debt over EBITDA")
    row("balloon", "Maximum balloon", "", balloon, 0, 0.5 if t["facility_type"] == "term_loan" else 1.0, "ratio", "soft", "Share repaid at maturity")
    row("bu_rwa_budget", "Business-unit RWA budget", "Corporate Banking", PORTFOLIO["rwa_used"], rwa, P["rwa_budget"], "SAR m", "soft", "Annual budget")
    return rows


def _approval(total: float, rating: str, soft: list[dict]) -> dict:
    i = next(k for k, (lim, _) in enumerate(P["doa"]) if total <= lim)
    reasons = [f"Total exposure SAR {total:,.0f}m"]
    if RATINGS.index(rating) >= RATINGS.index("BB-"):
        i = min(i + 1, len(P["doa"]) - 1)
        reasons.append(f"Rating {rating}")
    if soft:
        i = min(i + 1, len(P["doa"]) - 1)
        reasons.append(f"{len(soft)} soft breach{'es' if len(soft) > 1 else ''}")
    return {"level": P["doa"][i][1], "rank": i + 1, "reasons": reasons}


def public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ------------------------------------------------------------------ optimiser

def _distance(ask: dict, t: dict, w: dict) -> float:
    d = w["amount"] * max(0.0, (ask["amount"] - t["amount"]) / ask["amount"])
    d += w["tenor"] * max(0.0, (ask["tenor_years"] - t["tenor_years"]) / ask["tenor_years"])
    d += w["margin"] * max(0.0, (t["margin_bps"] - ask["margin_bps"]) / 300)
    added = len(set(t.get("collateral_ids") or []) - set(ask.get("collateral_ids") or [])) + (1 if t.get("guarantee_id") and not ask.get("guarantee_id") else 0)
    d += w["collateral"] * (added * 0.25 + float(t.get("cash_margin_pct") or 0) / 100)
    d += w["fees"] * max(0.0, (t["upfront_fee_bps"] - ask["upfront_fee_bps"]) / 100)
    return round(d, 6)


def _changes(ask: dict, t: dict) -> list[dict]:
    out = []
    for f, unit in (("amount", "m"), ("tenor_years", "years"), ("margin_bps", "bps"), ("upfront_fee_bps", "bps"), ("cash_margin_pct", "%"),
                    ("guarantee_coverage_pct", "%"), ("structure", ""), ("grace_years", "years")):
        if t.get(f) != ask.get(f):
            out.append({"field": f, "ask": ask.get(f), "value": t.get(f), "unit": unit})
    if sorted(t.get("collateral_ids") or []) != sorted(ask.get("collateral_ids") or []):
        out.append({"field": "collateral_ids", "ask": ask.get("collateral_ids"), "value": t.get("collateral_ids"), "unit": ""})
    return out


def optimize(req: dict) -> dict:
    pid = req["proposal_id"]
    p = _get(pid)
    ask = p["ask"]
    fixed = dict(req.get("fixed") or {})
    bounds = dict(req.get("bounds") or {})
    w = {**WEIGHTS, **(req.get("weights") or {})}
    allow_soft = bool(req.get("allow_soft"))
    lo, hi = bounds.get("margin_bps", P["margin_bounds"])
    amounts = [round(ask["amount"] * s, 3) for s in (1.0, 0.9, 0.8, 0.7, 0.6)]
    tenors = sorted({max(1, ask["tenor_years"] - d) for d in (0, 1, 2)}, reverse=True)
    margins = sorted({m for m in [ask["margin_bps"], *range(int(lo), int(hi) + 1, 25)] if lo <= m <= hi})
    excl = set(bounds.get("exclude_collateral_types") or [])
    avail = [c["collateral_id"] for c in p["security"]["collateral"] if c["type"] not in excl]
    base_coll = [c for c in ask["collateral_ids"] if c in avail]
    colls = [base_coll, sorted(set(base_coll) | set(avail))]
    gopts = [(ask.get("guarantee_id"), ask.get("guarantee_coverage_pct", 0))]
    if p["security"]["guarantees"] and not ask.get("guarantee_id"):
        g = p["security"]["guarantees"][0]
        gopts.append((g["guarantee_id"], g["coverage_pct"]))
    cands = {}
    for a, n, m, c, cl, (gid, gc), f in itertools.product(amounts, tenors, margins or [ask["margin_bps"]], (0, 10, 20, 30), colls, gopts,
                                                          (ask["upfront_fee_bps"], min(P["upfront_bounds"][1], ask["upfront_fee_bps"] + 50))):
        t = {"amount": a, "tenor_years": n, "margin_bps": m, "cash_margin_pct": c, "collateral_ids": cl, "guarantee_id": gid,
             "guarantee_coverage_pct": gc, "upfront_fee_bps": f}
        t.update(fixed)
        cands[json.dumps(t, sort_keys=True)] = t
    pts = []
    for t in cands.values():
        r = compute(pid, t)
        soft = [c["name"] for c in r["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
        ok = r["metrics"]["clears_hurdle"] and not r["_hard"] and (allow_soft or not soft)
        pts.append({"r": r, "distance": _distance(ask, r["terms"], w), "ok": ok, "soft": soft})
    feas = [x for x in pts if x["ok"]]
    a_res = compute(pid)
    ask_out = {"terms": a_res["terms"], "metrics": a_res["metrics"], "clears": a_res["metrics"]["clears_hurdle"] and not a_res["_hard"],
               "breaches": [c["name"] for c in a_res["constraints"] if c["status"] == "breach"]}
    trace = _trace("optimize", req)
    searched = {"combinations": len(cands), "feasible_points": len(feas), "seconds": 0.0}

    def sol(label: str, x: dict) -> dict:
        return {"label": label, "terms": x["r"]["terms"], "metrics": x["r"]["metrics"], "distance": x["distance"],
                "changes": _changes(ask, x["r"]["terms"]), "approval": x["r"]["approval"], "soft_breaches": x["soft"]}
    if not feas:
        return {"trace_id": trace, "feasible": False, "ask": ask_out, "closest": None, "max_sva": None, "counter_offers": None,
                "frontier": [], "binding": [], "relaxation": _relaxation(pid, a_res), "searched": searched}
    closest = min(feas, key=lambda x: (x["distance"], -x["r"]["metrics"]["sva"]))
    best = max(feas, key=lambda x: x["r"]["metrics"]["sva"])
    front = []
    for x in sorted(feas, key=lambda x: (x["distance"], -x["r"]["metrics"]["sva"])):
        if not front or x["r"]["metrics"]["sva"] > front[-1]["r"]["metrics"]["sva"] + 1e-9:
            front.append(x)
    offers = []
    seen = {json.dumps(closest["r"]["terms"], sort_keys=True), json.dumps(best["r"]["terms"], sort_keys=True)}
    for label, pred in (("Same amount, shorter tenor", lambda t: t["amount"] == ask["amount"] and t["tenor_years"] < ask["tenor_years"]),
                        ("Same tenor, cash margin", lambda t: t["tenor_years"] == ask["tenor_years"] and t["cash_margin_pct"] > 0),
                        ("Lower amount, current pricing", lambda t: t["amount"] < ask["amount"] and t["margin_bps"] == ask["margin_bps"]),
                        ("Added security", lambda t: t["collateral_ids"] != ask["collateral_ids"] or t["guarantee_id"] != ask.get("guarantee_id"))):
        c = [x for x in feas if pred(x["r"]["terms"]) and json.dumps(x["r"]["terms"], sort_keys=True) not in seen]
        if c:
            x = min(c, key=lambda x: x["distance"])
            seen.add(json.dumps(x["r"]["terms"], sort_keys=True))
            offers.append(sol(label, x))
    cl = closest["r"]
    binding = []
    if cl["metrics"]["lifetime_raroc"] - P["hurdle"] < 0.01:
        binding.append({"constraint": "hurdle", "shadow_price": round(cl["metrics"]["capital_y1"] * 0.01, 4), "unit": "SVA SAR m per 1pp of hurdle"})
    for c in cl["constraints"]:
        if c["status"] == "pass" and c["limit"] and abs(c["headroom"]) / max(abs(c["limit"]), 1e-9) < 0.10:
            binding.append({"constraint": c["name"], "shadow_price": round(abs(cl["metrics"]["sva"]) * 0.05, 4), "unit": "SVA SAR m per 10% of the limit"})
    return {"trace_id": trace, "feasible": True, "ask": ask_out, "closest": sol("Closest to ask", closest), "max_sva": sol("Maximum value", best),
            "counter_offers": offers[:3], "frontier": [{"distance": x["distance"], "sva": x["r"]["metrics"]["sva"],
                                                         "lifetime_raroc": x["r"]["metrics"]["lifetime_raroc"], "terms": x["r"]["terms"]} for x in front],
            "binding": binding, "relaxation": None, "searched": searched}


def _relaxation(pid: str, a_res: dict) -> list[dict]:
    p = _get(pid)
    ask = p["ask"]
    out = []
    to = None
    for m in range(ask["margin_bps"], 1501, 25):
        r = compute(pid, {"margin_bps": m})
        if r["metrics"]["clears_hurdle"] and not r["_hard"]:
            to = m
            break
    out.append({"lever": "margin_bps", "from": ask["margin_bps"], "to": to, "delta": (to - ask["margin_bps"]) if to else None, "unit": "bps",
                "beyond_market": bool(to and to > P["margin_bounds"][1])})
    out.append({"lever": "hurdle", "from": P["hurdle"], "to": round(a_res["metrics"]["lifetime_raroc"], 4),
                "delta": round(a_res["metrics"]["lifetime_raroc"] - P["hurdle"], 4), "unit": "ratio", "beyond_market": False})
    for name in a_res["_hard"]:
        c = next(c for c in a_res["constraints"] if c["name"] == name)
        out.append({"lever": name, "from": c["limit"], "to": c["value"], "delta": round(c["value"] - c["limit"], 4), "unit": c["unit"], "beyond_market": False})
    return out


def stress(pid: str, terms: dict | None, scenario: str = "all") -> dict:
    base = compute(pid, terms)
    rows = []
    for key, label, kw in STRESS:
        if scenario not in ("all", None, "") and key != scenario:
            continue
        r = compute(pid, terms, **kw)
        rows.append({"scenario": key, "label": label, "lifetime_raroc": r["metrics"]["lifetime_raroc"], "sva": r["metrics"]["sva"],
                     "el_lifetime_pv": r["metrics"]["el_lifetime_pv"], "rwa_y1": r["metrics"]["rwa_y1"], "dscr_post": r["metrics"]["dscr_post"],
                     "clears_hurdle": r["metrics"]["clears_hurdle"], "breaches": [c["name"] for c in r["constraints"] if c["status"] == "breach"]})
    notches = 0
    if base["metrics"]["clears_hurdle"]:
        for k in range(1, 8):
            if not compute(pid, terms, rating_shift=k)["metrics"]["clears_hurdle"]:
                break
            notches = k
    return {"trace_id": _trace("stress", [pid, terms, scenario]), "base": {"lifetime_raroc": base["metrics"]["lifetime_raroc"], "sva": base["metrics"]["sva"]},
            "rows": rows, "robustness_notches": notches}


def breakeven(pid: str, terms: dict | None, lever: str) -> dict:
    t = dict(terms or {})
    at_ask = compute(pid, t)["metrics"]["lifetime_raroc"] >= P["hurdle"]
    if lever != "margin_bps":
        return {"trace_id": _trace("breakeven", [pid, t, lever]), "lever": lever, "value": None, "unit": "", "feasible": False, "at_ask": at_ask,
                "note": "Only the margin is solved here."}
    lo, hi = 0.0, 1500.0
    if compute(pid, {**t, "margin_bps": hi})["metrics"]["lifetime_raroc"] < P["hurdle"]:
        return {"trace_id": _trace("breakeven", [pid, t, lever]), "lever": lever, "value": None, "unit": "bps", "feasible": False, "at_ask": at_ask, "note": ""}
    for _ in range(28):
        mid = (lo + hi) / 2
        if compute(pid, {**t, "margin_bps": mid})["metrics"]["lifetime_raroc"] >= P["hurdle"]:
            hi = mid
        else:
            lo = mid
    return {"trace_id": _trace("breakeven", [pid, t, lever]), "lever": lever, "value": round(hi, 1), "unit": "bps", "feasible": True, "at_ask": at_ask, "note": ""}


def grid(req: dict) -> dict:
    pid = req["proposal_id"]
    t = dict(req.get("terms") or {})
    x, y, metric = req["x"], req.get("y"), req.get("metric", "lifetime_raroc")
    xs, ys = req["x_values"], req.get("y_values") or [None]
    values = []
    for yv in ys:
        row = []
        for xv in xs:
            tt = {**t, x: xv}
            if y:
                tt[y] = yv
            row.append(compute(pid, tt)["metrics"][metric])
        values.append(row)
    ask = _get(pid)["ask"]
    return {"trace_id": _trace("grid", req), "x": xs, "y": ys if y else None, "values": values if y else values[0], "hurdle": P["hurdle"],
            "ask": {"x": ask.get(x), "y": ask.get(y) if y else None}}


def tornado(pid: str, terms: dict | None) -> dict:
    p = _get(pid)
    t = _merge(p, terms)
    base = compute(pid, t)["metrics"]["lifetime_raroc"]
    g = p["security"]["guarantees"][0] if p["security"]["guarantees"] else None
    levers = [("Margin", "−50 bps", {"margin_bps": t["margin_bps"] - 50}, "+50 bps", {"margin_bps": t["margin_bps"] + 50}),
              ("Tenor", "+1 year", {"tenor_years": t["tenor_years"] + 1}, "−1 year", {"tenor_years": max(1, t["tenor_years"] - 1)}),
              ("Amount", "+20%", {"amount": t["amount"] * 1.2}, "−20%", {"amount": t["amount"] * 0.8}),
              ("Cash margin", "0%", {"cash_margin_pct": 0}, "20%", {"cash_margin_pct": 20}),
              ("Upfront fee", "−25 bps", {"upfront_fee_bps": max(0, t["upfront_fee_bps"] - 25)}, "+25 bps", {"upfront_fee_bps": t["upfront_fee_bps"] + 25})]
    if g:
        levers.append(("Guarantee", "off", {"guarantee_id": None, "guarantee_coverage_pct": 0}, "on",
                       {"guarantee_id": g["guarantee_id"], "guarantee_coverage_pct": g["coverage_pct"]}))
    bars = []
    for name, ll, lo, hl, hi in levers:
        bars.append({"lever": name, "low_label": ll, "high_label": hl, "low": compute(pid, {**t, **lo})["metrics"]["lifetime_raroc"],
                     "high": compute(pid, {**t, **hi})["metrics"]["lifetime_raroc"]})
    bars.sort(key=lambda b: -abs(b["high"] - b["low"]))
    return {"trace_id": _trace("tornado", [pid, t]), "base_raroc": base, "bars": bars}


def headroom(proposal_id: str | None, dimension: str | None) -> dict:
    if dimension:
        src = PORTFOLIO["sector"] if dimension == "sector" else PORTFOLIO["collateral_type"] if dimension == "collateral_type" else {}
        rows = []
        for k, v in src.items():
            cap = P["sector_cap_pct"] if dimension == "sector" else COLLATERAL_CAP.get(k)
            share = v / PORTFOLIO["total"]
            rows.append({"key": k, "ead": v, "share": round(share, 4), "limit": cap, "headroom_share": round(cap - share, 4) if cap else None,
                         "headroom_sar_mn": round((cap - share) * PORTFOLIO["total"], 1) if cap else None, "kind": "soft"})
        return {"trace_id": _trace("headroom", dimension), "dimension": dimension, "rows": rows}
    p = _get(proposal_id or "")
    r = compute(p["proposal_id"])
    return {"trace_id": _trace("headroom", proposal_id), "obligor": {"obligor_id": p["obligor"]["obligor_id"],
            "existing_ead_sar_mn": p["obligor"]["existing_exposure_sar_mn"], "group_id": p["obligor"]["group_id"]},
            "limits": [{"name": c["name"], "label": c["label"], "used": c["before"], "limit": c["limit"], "headroom": round(c["limit"] - c["before"], 4)
                        if c["name"] != "min_rating" else None, "unit": c["unit"], "kind": c["kind"]} for c in r["constraints"]]}


EXPLAIN = {"single_name": "Exposure to the obligor after the deal against the single-name limit.",
           "group_large_exposure": "Connected-group exposure after the deal against the SAMA large exposure limit, 25% of Tier 1.",
           "sector": "The sector's share of the corporate book after the deal against the sector cap.",
           "collateral_type": "The collateral type's share of the corporate book against its cap.",
           "min_rating": "The obligor's grade against the minimum grade for new business.",
           "max_tenor": "The tenor against the maximum tenor for the grade.",
           "ltv": "The amount over the value of pledged real estate, against the maximum LTV.",
           "dscr": "EBITDA over debt service including the new facility, against the minimum DSCR.",
           "debt_ebitda": "Total debt after the deal over EBITDA, against the maximum leverage.",
           "balloon": "The share repaid at maturity against the maximum balloon.",
           "bu_rwa_budget": "Business-unit RWA after the deal against its budget.",
           "hurdle": "Lifetime RAROC, PV of risk-adjusted profit over PV of capital, against the hurdle rate."}


# ------------------------------------------------------------------ the app (C1's paths)

app = FastAPI(title="Deal Desk reference engine")
PREFIX = "/api/v1/dealdesk"


@app.get(PREFIX + "/health")
def _health() -> dict:
    return {"status": "ok", "service": "dealdesk-reference", "version": P["version"], "model_version": "reference", "param_version": P["version"]}


@app.get(PREFIX + "/meta")
def _meta() -> dict:
    return {"facility_types": FACILITY_TYPES, "structures": STRUCTURES, "profiles": ["equal", "bullet", "balloon"],
            "covenant_packages": ["none", "standard", "enhanced"], "statuses": STATUSES, "rating_order": RATINGS, "sectors": SECTORS, "rms": RMS,
            "stress_scenarios": [{"key": k, "label": lab} for k, lab, _ in STRESS], "weights": WEIGHTS,
            "levers": ["amount", "tenor_years", "grace_years", "amortisation", "balloon_pct", "margin_bps", "upfront_fee_bps", "commitment_fee_bps",
                       "commission_bps", "cash_margin_pct", "collateral_ids", "guarantee_id", "guarantee_coverage_pct", "funded_share_pct",
                       "structure", "covenant_package"],
            "hurdle": P["hurdle"], "market_bounds": {"margin_bps": P["margin_bounds"], "upfront_fee_bps": P["upfront_bounds"]}}


@app.get(PREFIX + "/proposals")
def _list(status: str = "", sector: str = "", rating: str = "", rm: str = "", q: str = "") -> dict:
    rows = [summary(p) for p in _PROPOSALS.values()]
    rows = [r for r in rows if (not status or r["status"] == status) and (not sector or r["sector"] == sector) and (not rating or r["rating"] == rating)
            and (not rm or r["rm"] == rm) and (not q or q.lower() in r["obligor_name"].lower())]
    return {"trace_id": _trace("list", [status, sector, rating, rm, q]), "proposals": rows}


@app.get(PREFIX + "/proposals/{pid}")
def _proposal(pid: str) -> dict:
    return {"trace_id": _trace("get", pid), "proposal": _get(pid)}


@app.post(PREFIX + "/proposals")
def _create(body: dict = Body(...)) -> dict:
    n = len(_PROPOSALS) + 1
    while f"DD-{n:02d}" in _PROPOSALS:
        n += 1
    pid = f"DD-{n:02d}"
    p = {**body, "proposal_id": pid, "status": "new"}
    _PROPOSALS[pid] = p
    return {"trace_id": _trace("create", pid), "proposal": p}


@app.post(PREFIX + "/proposals/{pid}/status")
def _status(pid: str, body: dict = Body(...)) -> dict:
    p = _get(pid)
    if body.get("status") not in STATUSES:
        raise HTTPException(422, f"Status must be one of {', '.join(STATUSES)}.")
    p["status"] = body["status"]
    return {"trace_id": _trace("status", [pid, body]), "proposal": p}


@app.get(PREFIX + "/proposals/{pid}/memo.docx")
def _memo(pid: str):
    from fastapi.responses import Response

    from backend.dealdesk_thread.ingest import write_memo
    return Response(content=write_memo(_get(pid)), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{pid}.docx"'})


@app.post(PREFIX + "/compute")
def _compute(body: dict = Body(...)) -> dict:
    r = compute(body["proposal_id"], body.get("terms"), el_view=body.get("el_view", "economic"))
    be = breakeven(body["proposal_id"], body.get("terms"), "margin_bps")
    r["metrics"]["breakeven_margin_bps"] = be["value"]
    return public(r)


@app.post(PREFIX + "/optimize")
def _optimize(body: dict = Body(...)) -> dict:
    return optimize(body)


@app.post(PREFIX + "/frontier")
def _frontier(body: dict = Body(...)) -> dict:
    o = optimize(body)
    return {"trace_id": o["trace_id"], "frontier": o["frontier"]}


@app.post(PREFIX + "/stress")
def _stress(body: dict = Body(...)) -> dict:
    return stress(body["proposal_id"], body.get("terms"), body.get("scenario") or "all")


@app.get(PREFIX + "/headroom")
def _headroom(proposal_id: str = "", obligor_id: str = "", dimension: str = "") -> dict:
    if obligor_id and not proposal_id:
        proposal_id = next((p["proposal_id"] for p in _PROPOSALS.values() if p["obligor"]["obligor_id"] == obligor_id), "")
    return headroom(proposal_id or None, dimension or None)


@app.get(PREFIX + "/constraints/{name}")
def _explain(name: str, proposal_id: str = Query("")) -> dict:
    if name not in EXPLAIN:
        raise HTTPException(404, f"{name} is not a Deal Desk constraint.")
    out = {"trace_id": _trace("explain", [name, proposal_id]), "name": name, "definition": EXPLAIN[name]}
    if proposal_id:
        r = compute(proposal_id)
        out["deal"] = next((c for c in r["constraints"] if c["name"] == name), None)
    return out


@app.post(PREFIX + "/compare")
def _compare(body: dict = Body(...)) -> dict:
    rows = []
    for ts in body["term_sets"]:
        r = compute(body["proposal_id"], ts.get("terms"))
        rows.append({"label": ts.get("label", ""), "terms": r["terms"], "metrics": r["metrics"], "approval": r["approval"]})
    fields = sorted({k for r in rows for k in r["terms"]})
    diffs = [{"field": f, "values": [r["terms"].get(f) for r in rows]} for f in fields if len({json.dumps(r["terms"].get(f)) for r in rows}) > 1]
    return {"trace_id": _trace("compare", body), "rows": rows, "differences": diffs}


@app.post(PREFIX + "/breakeven")
def _breakeven(body: dict = Body(...)) -> dict:
    return breakeven(body["proposal_id"], body.get("terms"), body.get("lever", "margin_bps"))


@app.post(PREFIX + "/grid")
def _grid(body: dict = Body(...)) -> dict:
    return grid(body)


@app.post(PREFIX + "/tornado")
def _tornado(body: dict = Body(...)) -> dict:
    return tornado(body["proposal_id"], body.get("terms"))


@app.get(PREFIX + "/params")
def _params() -> dict:
    return {"trace_id": _trace("params", P["version"]), "version": P["version"],
            "tables": [{"name": n, "owner": o, "version": P["version"], "effective_from": "2026-10-01", "approved_by": o}
                       for n, o in (("pd_master_scale", "Risk Models"), ("ftp", "Treasury"), ("returns", "CFO"), ("limits", "Risk"))]}


@app.get(PREFIX + "/model_card")
def _model_card(proposal_id: str = "") -> dict:
    out = {"trace_id": _trace("card", proposal_id), "model_version": "reference", "target": "12-month PD",
           "features": [], "monotonicity": {"status": "pass", "adjustments": []}}
    if proposal_id:
        out["out_of_range"] = compute(proposal_id)["pd"]["out_of_range"]
    return out


@app.get(PREFIX + "/portfolio")
def _portfolio() -> dict:
    return {"trace_id": _trace("portfolio", 0), "ead": PORTFOLIO["total"], "rwa": PORTFOLIO["rwa_used"],
            "by_sector": [{"key": k, "ead": v} for k, v in PORTFOLIO["sector"].items()],
            "by_collateral_type": [{"key": k, "ead": v} for k, v in PORTFOLIO["collateral_type"].items()]}
