"""Workout optimiser (R14 backlog #11): for a stressed name, compare reschedule, extra collateral, partial exit, sale and
legal action (and holding as the baseline) on recovery NPV, ECL, capital and stage, counting the CBUAE three-restructuring
rule.

Inputs per obligor (all facilities): EAD, PD and LGD of the current ECL run (ecl_runs.ecl_facility 2026Q3), stage, EWS band,
CRWA (collateral.col_crwa), collateral after haircut (collateral.col_item), perfected guarantees (collateral.col_guarantee),
distressed restructurings in the last 24 months (collateral.col_restructured count_24m) and deferrals and UTP
(classification.cls_exposure). Expert assumptions: backend/intel/portfolio/assumptions.json (labelled in every answer).

    legal PV(X, Cnet)  = [min(X, Cnet x (1 - forced)) + max(X - Cnet x (1 - forced), 0) x unsecured_recovery]
                         x (1 - legal_cost) / (1 + r)^legal_years
    hold               p_ok x X + (1 - p_ok) x legal PV / (1 + r);  p_ok = 1 - PD12 (Stage 1-2) or the observed 4-quarter
                       Stage 3 cure rate (ews.corp_exposure)
    reschedule         restructuring n = count_24m + 1; p_ok = p_ok(hold) + (1 - p_ok(hold)) x cure probability for n, on
                       X x (1 - concession); n >= 3 -> Stage 3 (CBUAE CRM 9.29);
                       UTP or Stage 3 now -> Stage 3 (9.28); otherwise Stage 2 (9.30)
    extra collateral   Cnet + extra_cover x X at the real-estate haircut; stage unchanged (no concession)
    partial exit       share s repaid now at a concession, the rest held with all the collateral
    sale               price = X x (1 - discount(Stage 3 or bucket)); derecognised; a loss over 30% is a UTP indicator (6.8(c))
    legal action       legal PV now; Stage 3 (filing is a UTP indicator, 6.8(d))
ECL after: Stage 3 = max(X x LGD, X - recovery PV); Stage 2 = X x PDlifetime x LGD; Stage 1 = X x PD12 x LGD.
Capital after: (X - CRM) x RW x capital_ratio_target, RW 150% in Stage 3 (100% once provisions reach 20% of EAD).
Ranking: recovery NPV less one year of capital at the hurdle (returns.hurdle), the cost of carrying the option.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk import params
from backend.intel.portfolio import common as C

CLAUSES = {"9.29": "Any Credit Facility restructured 3 times or more in a context of financial difficulty must be migrated to Stage 3.",
           "9.28": "Distressed restructured facilities meeting UTP or over 90 days past due at the conclusion are Stage 3.",
           "9.30": "Other distressed restructured facilities are allocated to Stage 2 or Stage 3.",
           "6.8(c)": "Selling part of a facility at an economic loss over 30% is an unlikeliness-to-pay indicator.",
           "6.8(d)": "Filing for the obligor's bankruptcy or a similar order is an unlikeliness-to-pay indicator."}


@functools.lru_cache(maxsize=1)
def _cure_rate() -> tuple[float, int]:
    from backend.intel.portfolio.ecl_bridge import _ews, _transitions
    e = _ews()
    tr = _transitions(e, e["reporting_quarter"].max(), 8)
    s3 = tr[tr["stage"] == 3]
    q = float((s3["next"].isin(["1", "2"])).mean()) if len(s3) else 0.0
    return 1 - (1 - q) ** 4, int(len(s3))


def _data(lin: C.Lineage) -> dict[str, pd.DataFrame]:
    run = C.read(lin, "ecl_runs", "ecl_facility", ["exposure_id", "obligor_id", "book", "ead_sar_mn", "pd_12m_pct",
                                                   "pd_lifetime_pct", "lgd_pct", "stage", "rating", "ecl_sar_mn", "dpd_days"],
                 period=("run_id", C.RUN_CURRENT))
    run = run[run["book"] == "corporate"]
    cls = C.read(lin, "classification", "cls_exposure", ["exposure_id", "book", "utp_flag", "deferrals_24m", "ews_bucket",
                                                         "restructured_flag"])
    cls = cls[cls["book"] == "corporate"]
    crwa = C.read(lin, "collateral", "col_crwa", ["exposure_id", "book", "crm_sar_mn", "risk_weight_pct", "crwa_sar_mn"])
    crwa = crwa[crwa["book"] == "corporate"]
    item = C.read(lin, "collateral", "col_item", ["exposure_id", "book", "type", "value_sar_mn", "haircut_pct", "registration_status"])
    item = item[item["book"] == "corporate"]
    gua = C.read(lin, "collateral", "col_guarantee", ["exposure_id", "obligor_id", "amount_sar_mn", "perfected", "guarantor_name"])
    rs = C.read(lin, "collateral", "col_restructured", ["exposure_id", "obligor_id", "book", "count_24m", "restructure_type",
                                                       "status", "probation_end"])
    rs = rs[rs["book"] == "corporate"]
    f = run.merge(cls.drop(columns="book"), on="exposure_id", how="left").merge(crwa.drop(columns="book"), on="exposure_id", how="left")
    return {"f": f, "item": item, "gua": gua, "rs": rs}


@functools.lru_cache(maxsize=1)
def _cached() -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    lin = C.Lineage()
    d = _data(lin)
    return d, lin.list()


def candidates(limit: int = 30) -> dict[str, Any]:
    """Stressed names: any Stage 3 facility, EWS high or critical, or restructured in the last 24 months.

    Ordered Stage 3 first, then by Early Warning severity, restructurings in 24 months and EAD."""
    d, lin_items = _cached()
    f = d["f"]
    g = f.groupby("obligor_id").agg(ead=("ead_sar_mn", "sum"), stage=("stage", "max"), rating=("rating", "first"),
                                    restructured=("restructured_flag", "max"), utp=("utp_flag", "max"),
                                    band=("ews_bucket", lambda s: "critical" if (s == "critical").any() else "high" if (s == "high").any()
                                          else str(s.mode().iloc[0]) if len(s.mode()) else "none"))
    rsn = d["rs"].groupby("obligor_id")["count_24m"].max()
    g["restructurings_24m"] = g.index.map(rsn).fillna(0).astype(int)
    g = g[(g["stage"] >= 3) | g["band"].isin(["high", "critical"]) | (g["restructured"] == 1)]
    names = C._frame("cockpit", "corp_borrower_quarter")
    names = names[names["reporting_quarter"] == C.AS_OF_QUARTER].set_index("borrower_id")[["borrower_name", "sector"]]
    g = g.join(names)
    g["sev"] = g["band"].map({"critical": 3, "high": 2, "moderate": 1}).fillna(0)
    g = g.sort_values(["stage", "sev", "restructurings_24m", "ead"], ascending=False)
    rows = [{"borrower_id": k, "borrower_name": r["borrower_name"], "sector": r["sector"], "ead_sar_mn": float(r["ead"]),
             "stage": int(r["stage"]), "rating": r["rating"], "ews_band": r["band"], "restructurings_24m": int(r["restructurings_24m"]),
             "third_restructuring_next": bool(r["restructurings_24m"] >= 2)} for k, r in g.head(limit).iterrows()]
    return C.clean({"engine": "intel.portfolio.workout.candidates", "version": C.VERSION, "as_of": C.AS_OF_QUARTER,
                    "total": int(len(g)), "rows": rows, "lineage": lin_items,
                    "headline": f"{len(g)} stressed names (Stage 3, Early Warning high or critical, or restructured in 24 months); "
                                f"{int((g['restructurings_24m'] >= 2).sum())} would reach a third restructuring with the next one."})


def compute(borrower_id: str) -> dict[str, Any]:
    lin = C.Lineage()
    d, lin_items = _cached()
    for it in lin_items:
        lin.items[f"{it['domain']}.{it['relation']}"] = dict(it)
    f = d["f"][d["f"]["obligor_id"] == borrower_id]
    if f.empty:
        raise KeyError(borrower_id)
    k = C.capital_ratio(lin)
    r = float(C.A("discount_rate", lin))
    legal_years = float(C.A("legal_years", lin))
    legal_cost = float(C.A("legal_cost_pct", lin))
    forced = float(C.A("forced_sale_haircut_extra", lin))
    unsec = float(C.A("unsecured_recovery_legal", lin))
    cure = C.A("reschedule_cure_prob", lin)
    conc = float(C.A("reschedule_concession_pct", lin))
    extra_cover = float(C.A("extra_collateral_cover", lin))
    pe_share = float(C.A("partial_exit_share", lin))
    pe_cost = float(C.A("partial_exit_cost_pct", lin))
    disc = C.A("sale_discount_by_bucket", lin)
    prov_min = float(C._assumptions()["rows"]["defaulted_rw_provisioned"]["provision_min"])
    C.A("defaulted_rw_provisioned", lin)
    re_haircut = 0.3
    lin.param("lgd", "collateral.real_estate.haircut")
    names = C._frame("cockpit", "corp_borrower_quarter")
    nm = names[(names["reporting_quarter"] == C.AS_OF_QUARTER) & (names["borrower_id"] == borrower_id)]
    name = str(nm["borrower_name"].iloc[0]) if len(nm) else borrower_id
    sector = str(nm["sector"].iloc[0]) if len(nm) else ""
    h, _ = C.hurdle(sector, lin)

    X = float(f["ead_sar_mn"].sum())
    w = f["ead_sar_mn"] / X if X else f["ead_sar_mn"] * 0
    pd12 = float((f["pd_12m_pct"] / 100 * w).sum())
    pdlt = max(float((f["pd_lifetime_pct"] / 100 * w).sum()), pd12)
    lgd = float((f["lgd_pct"] / 100 * w).sum())
    stage = int(f["stage"].max())
    rating = str(f["rating"].iloc[0])
    utp = bool(f["utp_flag"].fillna(0).max() > 0)
    dpd = float(f["dpd_days"].max())
    ecl_now = float(f["ecl_sar_mn"].sum())
    crm = float(f["crm_sar_mn"].fillna(0).sum())
    rw_now = float((f["risk_weight_pct"].fillna(100) / 100 * w).sum())
    rwa_now = float(f["crwa_sar_mn"].fillna(0).sum())
    ids = set(f["exposure_id"])
    it = d["item"][d["item"]["exposure_id"].isin(ids)]
    cnet = float((it["value_sar_mn"] * (1 - it["haircut_pct"] / 100)).sum())
    cnet_reg = float((it.loc[it["registration_status"] == "Registered", "value_sar_mn"]
                      * (1 - it.loc[it["registration_status"] == "Registered", "haircut_pct"] / 100)).sum())
    gu = d["gua"][d["gua"]["exposure_id"].isin(ids) & (d["gua"]["perfected"] == 1)]
    gnet = float(gu["amount_sar_mn"].sum()) * (1 - float(params.rows("lgd")["guarantor_lgd"]["corporate"]))  # lgd.guarantor_lgd.corporate
    lin.param("lgd", "guarantor_lgd.corporate")
    rs = d["rs"][d["rs"]["exposure_id"].isin(ids)]
    n24 = int(rs["count_24m"].max()) if len(rs) else 0
    deferrals = int(f["deferrals_24m"].fillna(0).max())
    cure3, n3 = _cure_rate()

    def legal_pv(x: float, col: float) -> float:
        sec = min(x, col * (1 - forced))
        return (sec + max(x - sec, 0) * unsec) * (1 - legal_cost) / (1 + r) ** legal_years

    def ecl_for(st: int, x: float, l: float, pv: float | None) -> float:
        if st >= 3:
            return max(x * l, x - pv) if pv is not None else x * l
        return x * (pdlt if st == 2 else pd12) * l

    def cap_for(st: int, x: float, crm_x: float, ecl: float) -> tuple[float, float]:
        rw = rw_now
        if st >= 3:
            rw = 1.0 if x > 0 and ecl / x >= prov_min else 1.5
        rwa = max(x - crm_x, 0) * rw
        return rwa, rwa * k

    p_ok_hold = (1 - pd12) if stage < 3 else cure3
    col = cnet + gnet
    opts = []

    def add(key: str, label: str, pv: float, st: int | None, ecl: float, rwa: float, notes: list[str],
            restructuring: int | None = None) -> None:
        cap = rwa * k
        opts.append({"key": key, "label": label, "recovery_npv_sar_mn": pv, "recovery_rate": pv / X if X else None,
                     "ecl_after_sar_mn": ecl, "ecl_change_sar_mn": ecl - ecl_now, "rwa_after_sar_mn": rwa,
                     "capital_after_sar_mn": cap, "capital_change_sar_mn": cap - rwa_now * k,
                     "stage_after": st, "restructuring_number": restructuring,
                     "net_value_sar_mn": pv - cap * h, "notes": notes})

    def stage3(x: float, crm_x: float, l: float, pv: float) -> tuple[float, float]:
        """ECL and RWA when the whole obligor is Stage 3 (CBUAE: the classification is at obligor level)."""
        ecl = ecl_for(3, x, l, pv)
        return ecl, cap_for(3, x, crm_x, ecl)[0]

    def scaled_rwa(x_after: float, crm_after: float) -> float:
        """Current RWA moved by the change in the unsecured exposure, at the obligor's current weights."""
        base = max(X - crm, 0.0)
        return rwa_now * (max(x_after - crm_after, 0.0) / base) if base > 1e-9 else 0.0

    hold_pv = p_ok_hold * X + (1 - p_ok_hold) * legal_pv(X, col) / (1 + r)
    add("hold", "Hold and monitor (baseline)", hold_pv, stage, ecl_now, rwa_now,
        [f"P(performs or cures in a year) {C.pct(p_ok_hold)}" + (f" (observed Stage 3 cure rate, {n3:,} moves)" if stage >= 3 else " (1 - PD12)")])

    n = n24 + 1
    pc = float(cure["first" if n == 1 else "second" if n == 2 else "third"])
    if n >= 3:
        st_r, why = 3, f"restructuring #{n} in 24 months: Stage 3 is mandatory (CBUAE CRM 9.29)"
    elif utp or stage >= 3 or dpd > 90:
        st_r, why = 3, "UTP met or Stage 3 now: a distressed restructuring stays Stage 3 (CBUAE CRM 9.28), 3 instalments to return (9.35)"
    else:
        st_r, why = 2, "distressed restructuring: at least Stage 2 (CBUAE CRM 9.30), 12 months' probation"
    p_ok_r = p_ok_hold + (1 - p_ok_hold) * pc
    resch_pv = p_ok_r * X * (1 - conc) + (1 - p_ok_r) * legal_pv(X, col) / (1 + r)
    if st_r == 3:
        e_r, rwa_r = stage3(X, crm, lgd, resch_pv)
    else:  # Stage 2 for the restructured facilities: lifetime ECL, never below today's
        e_r, rwa_r = max(ecl_now, X * pdlt * lgd), rwa_now
    add("reschedule", f"Reschedule (restructuring #{n} in 24 months)", resch_pv, st_r, e_r, rwa_r,
        [why, f"rescues {C.pct(pc, 0)} of the cases that would fail on the current schedule (restructuring #{min(n, 3)}"
              f"{'+' if n > 3 else ''}); NPV concession {C.pct(conc, 0)}"], restructuring=n)

    K = extra_cover * X * (1 - re_haircut)
    l_col = max(0.1, lgd * max(0.0, X - cnet - K) / max(X - cnet, 1e-9)) if X > cnet else max(0.1, lgd * 0.5)
    ec_pv = p_ok_hold * X + (1 - p_ok_hold) * legal_pv(X, col + K) / (1 + r)
    add("extra_collateral", f"Ask for extra collateral ({C.pct(extra_cover, 0)} of EAD, real estate)", ec_pv, stage,
        ecl_now * (l_col / lgd if lgd > 0 else 1.0), scaled_rwa(X, min(X, crm + K)), ["no concession, so not a restructuring; stage unchanged",
                                 f"LGD {C.pct(lgd)} to {C.pct(l_col)}"])

    xr = X * (1 - pe_share)
    l_pe = max(0.1, lgd * max(0.0, xr - cnet) / max(X - cnet, 1e-9)) if X > cnet else 0.1
    resid_pv = p_ok_hold * xr + (1 - p_ok_hold) * legal_pv(xr, col) / (1 + r)
    pe_pv = X * pe_share * (1 - pe_cost) + resid_pv
    e_pe = (ecl_for(3, xr, l_pe, resid_pv) if stage >= 3 else ecl_now * (xr / X) * (l_pe / lgd if lgd > 0 else 1.0)) if X else 0.0
    add("partial_exit", f"Partial exit ({C.pct(pe_share, 0)} repaid now)", pe_pv, stage, e_pe, scaled_rwa(xr, min(xr, crm)),
        [f"{C.sar(X * pe_share)} repaid at a {C.pct(pe_cost, 0)} concession; the remaining {C.sar(xr)} keeps all the collateral",
         "needs a repayment source (asset sale, sponsor or refinancing); whether the obligor has one is not in Data Domains"])

    dsc = float(disc["Stage 3"] if stage >= 3 else disc.get(C.bucket(rating), disc["CCC-C"]))
    price = X * (1 - dsc)
    loss_pct = dsc
    sale_notes = [f"price {C.pct(1 - dsc, 0)} of par (expert discount)"]
    if loss_pct > 0.3:
        sale_notes.append("loss over 30%: an unlikeliness-to-pay indicator for the obligor's other exposures (CBUAE CRM 6.8(c))")
    add("sale", "Sell the exposure", price, None, 0.0, 0.0, sale_notes)

    lpv = legal_pv(X, col)
    e_l, rwa_l = stage3(X, crm, lgd, lpv)
    add("legal", "Legal action and enforcement", lpv, 3, e_l, rwa_l,
        [f"{legal_years:.0f} years to realise collateral, {C.pct(legal_cost, 0)} cost, {C.pct(forced, 0)} forced-sale haircut",
         "filing is an unlikeliness-to-pay indicator: Stage 3 (CBUAE CRM 6.8(d))"])

    opts.sort(key=lambda o: -o["net_value_sar_mn"])
    best = opts[0]
    base = next(o for o in opts if o["key"] == "hold")
    profile = {"borrower_id": borrower_id, "borrower_name": name, "sector": sector, "rating": rating, "stage": stage,
               "ead_sar_mn": X, "pd_12m": pd12, "pd_lifetime": pdlt, "lgd": lgd, "ecl_now_sar_mn": ecl_now,
               "rwa_now_sar_mn": rwa_now, "capital_now_sar_mn": rwa_now * k, "collateral_net_sar_mn": cnet,
               "collateral_registered_net_sar_mn": cnet_reg, "guarantees_perfected_sar_mn": float(gu["amount_sar_mn"].sum()),
               "restructurings_24m": n24, "deferrals_24m": deferrals, "utp": utp, "dpd_days": dpd, "facilities": int(len(f)),
               "hurdle": h, "third_restructuring_next": n24 >= 2}
    summary = _write(profile, opts, best, base)
    kpis = [C.kpi("best", "Best option", best["label"], "text"),
            C.kpi("npv", "Recovery NPV (best)", best["recovery_npv_sar_mn"], "SAR m", C.pct(best["recovery_rate"]) + " of EAD"),
            C.kpi("uplift", "vs hold, net of capital cost", best["net_value_sar_mn"] - base["net_value_sar_mn"], "SAR m"),
            C.kpi("restructurings", "Distressed restructurings in 24 months", n24, "count",
                  "next one is the third: Stage 3" if n24 >= 2 else None),
            C.kpi("ecl_now", "ECL now", ecl_now, "SAR m")]
    limits = ["Cure probabilities, sale discounts, legal timelines and costs are expert assumptions (assumptions.json): "
              f"the book holds only {int((d['rs']['status'] == 'Cured').sum())} cured restructurings and no loan-sale or court-recovery history.",
              "Extra collateral is assumed to be real estate at the Deal Desk haircut and recognised as CRM the way col_crwa recognises it.",
              "Recovery NPV values the obligor's exposure on the bank's books; the relationship's other income is not included.",
              "The comparison is one year; a reschedule's longer path (probation, later re-default) is folded into its cure probability."]
    method = ["Each option: recovery NPV at the LGD discount rate, ECL by the stage CBUAE assigns, capital at the target ratio.",
              "Ranking: recovery NPV less one year of the option's capital at the sector hurdle.",
              "CBUAE CRM clauses applied: " + ", ".join(sorted(CLAUSES)) + "."]
    return C.envelope("workout", "Workout optimiser", summary[0], summary, kpis, opts, limits, method, lin,
                      {"profile": profile, "recommended": best["key"], "clauses": CLAUSES})


def _write(p, opts, best, base) -> list[str]:
    out = [f"For {p['borrower_name']} ({p['rating']}, Stage {p['stage']}, EAD {C.sar(p['ead_sar_mn'])}), the best route is: "
           f"{best['label']}. Recovery NPV {C.sar(best['recovery_npv_sar_mn'])} ({C.pct(best['recovery_rate'])} of EAD), " +
           (f"{C.sar(best['net_value_sar_mn'] - base['net_value_sar_mn'])} more than holding, net of capital cost."
            if best["key"] != "hold" else "holding is the best route on recovery net of capital cost.")]
    if p["restructurings_24m"] >= 2:
        out.append(f"It has been restructured {p['restructurings_24m']} times in 24 months in financial difficulty, so a reschedule "
                   "would be the third and force Stage 3 (CBUAE CRM 9.29).")
    elif p["restructurings_24m"] == 1:
        out.append("One distressed restructuring in 24 months: a reschedule would be the second; a third would force Stage 3 (CBUAE CRM 9.29).")
    rs = next(o for o in opts if o["key"] == "reschedule")
    dc = rs["ecl_change_sar_mn"]
    chg = "unchanged" if abs(dc) < 0.05 else f"{'+' if dc > 0 else '-'}{C.sar(abs(dc))}"
    out.append(f"Reschedule: Stage {rs['stage_after']}, ECL {C.sar(rs['ecl_after_sar_mn'])} ({chg}), "
               f"recovery NPV {C.sar(rs['recovery_npv_sar_mn'])}.")
    sale = next(o for o in opts if o["key"] == "sale")
    out.append(f"Sale frees {C.sar(p['capital_now_sar_mn'])} of capital and releases the ECL for {C.sar(sale['recovery_npv_sar_mn'])} cash today; "
               f"legal action recovers {C.sar(next(o for o in opts if o['key'] == 'legal')['recovery_npv_sar_mn'])} in present value.")
    return out[:5]
