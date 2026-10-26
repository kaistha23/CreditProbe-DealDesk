"""The calibrated Deal Desk Stress Lab ladder (PLAN_R13 §S.6): the same scenario ids, families and severities as the
R12 ladder (R12-L1), with each shock read from the engine's calibration, so the R12 tier rule
(`backend/dealdesk/stress2/verdict.py`) reads data-driven severities.

| Family / rows                 | Driver (calibrate)          | Shock in the ladder                                      |
|---|---|---|
| macro oil_15 / 30 / 45        | brent                       | oil_pct = -(Brent one-year fall at P75 / P92 / severe)   |
| macro gdp_1_5 / 3 / 4_5       | gdp_nonoil                  | gdp_pct = -(non-oil GDP slowdown, pp)                    |
| macro rates_100 / 200 / 300   | saibor                      | rate_bps = SAIBOR one-year rise, rounded to 5 bps        |
| sector_mild / moderate / severe | sector_cycle              | sector_downturn = fall at the severity / fall at moderate (moderate = the expert downturn, 1.0) |
| borrower margin_*             | margin                      | ebitda_margin_bps = -(margin fall, rounded to 5 bps)     |
| borrower rev_*, cust_*, paydelay_*, delay_* | revenue, customer, payment_delay, project_delay | labelled fallback (no adverse tail / no data) |
| collateral coll_*, re_*       | collateral, re_price        | labelled fallback (appraisal marks; 11 annual index moves) |
| rating notch_*                | rating                      | notches (whole, at least as rare as 1 in 4 / 12 / 25)    |
| combined moderate / severe    | joint (copula / analogue)   | the joint macro year (oil, non-oil GDP, rates together) plus revenue -10% / -20% and collateral -20% / -30% |

R14 m (K12, K20 (b)): in a high-oil regime (`regime.is_high`) the oil rows are the **oil reversal from today's level**
(mild half-way back to the pre-shock level, moderate back to it, severe the median post-spike reversal of 2008–09,
2014–15, 2022–23), never a fall from the long-run average, and the combined rows are the **conflict and trade
disruption** (the joint year's non-oil slowdown and rate rise with no oil fall, revenue, freight and input cost through
the margin, and payment delays). In any other regime the R13 rows apply unchanged.

Ids are kept so every R12 reader (verdict drivers, chain, papers) works unchanged; labels say the new size. Rows are
published as the next version of each scenario in `dd_stress_scenario` (set R13-S1, bank scope, approved by the
Risk Models checker), through Session D's door to Data Domains (`backend.dealdesk.stress2.store`).
"""
from __future__ import annotations

from typing import Any

from backend.scenarios import calibrate, joint

SET_ID = "R13-S1"
MAKER = "Risk Models (scenario engine r13-s1)"
CHECKER = "Head of Risk Models (calibration approval)"
MADE_AT = "2026-10-19T12:00:00+00:00"
REGIME_MADE_AT = "2026-10-19T20:00:00+00:00"   # R14 m: the regime-conditioned versions

ROWS = {
    "brent": (("oil_15", "oil_30", "oil_45"), "macro"),
    "gdp_nonoil": (("gdp_1_5", "gdp_3", "gdp_4_5"), "macro"),
    "saibor": (("rates_100", "rates_200", "rates_300"), "macro"),
    "sector_cycle": (("sector_mild", "sector_moderate", "sector_severe"), "sector"),
    "revenue": (("rev_10", "rev_20", "rev_30"), "borrower"),
    "margin": (("margin_150", "margin_300", "margin_450"), "borrower"),
    "customer": (("cust_33", "cust_67", "cust_100"), "borrower"),
    "payment_delay": (("paydelay_30", "paydelay_60", "paydelay_90"), "borrower"),
    "project_delay": (("delay_3", "delay_6", "delay_12"), "borrower"),
    "collateral": (("coll_20", "coll_30", "coll_40"), "collateral"),
    "re_price": (("re_10", "re_20", "re_30"), "collateral"),
    "rating": (("notch_1", "notch_2", "notch_3"), "rating"),
}
SEV = calibrate.SEVERITIES


def _r5(x: float) -> float:
    return float(round(x / 5.0) * 5.0)


def _freq_text(row: dict[str, Any], sev: str) -> str:
    est = row["estimate"]
    if row["method"] == "fallback":
        return f"{row['fallback_label']}: {row['fallback_reason']}"
    f = est["freq"][sev]
    pct = {"mild": "P75", "moderate": "P92", "severe": "severe = max(P96, worst episode)"}[sev]
    one = f" (about 1 in {f['one_in']:.0f})" if f.get("one_in") else ""
    if est["n"] == est["n_independent"]:
        yrs = ", ".join(f["labels"][-5:])
        return (f"{pct} of {est['n']} one-year moves, {row['window']}: at least this large in {f['count']} of {f['of']} years"
                f"{one}" + (f" ({yrs})" if yrs else ""))
    return (f"{pct} of {est['n']:,} four-quarter moves ({est['n_independent']:,} independent), {row['window']}: at least this "
            f"large in {f['share'] * 100:.1f}% of them{one}")


def shocks_for(key: str, sev: str, cal: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    row = cal[key]
    v = float(row["values"][sev])
    if key == "brent":
        return {"oil_pct": -round(v, 1)}, f"Oil −{v:.0f}%"
    if key == "gdp_nonoil":
        return {"gdp_pct": -round(v, 2)}, f"Non-oil GDP −{v:.1f} pp"
    if key == "saibor":
        b = max(5.0, _r5(v))
        return {"rate_bps": b}, f"Rates +{b:.0f} bps"
    if key == "sector_cycle":
        k = v / float(row["values"]["moderate"])
        lab = {"mild": "Own-sector slowdown", "moderate": "Own-sector downturn", "severe": "Own-sector crisis"}[sev]
        return {"sector_downturn": round(k, 2)}, f"{lab} (×{k:.2f})"
    if key == "revenue":
        return {"revenue_pct": -round(v / 100.0, 4)}, f"Revenue −{v:.0f}%"
    if key == "margin":
        b = max(5.0, _r5(v))
        return {"ebitda_margin_bps": -b}, f"EBITDA margin −{b:.0f} bps"
    if key == "customer":
        lab = {"mild": "Largest customer cuts a third", "moderate": "Largest customer cuts two thirds", "severe": "Largest customer lost"}[sev]
        return {"customer_loss_share": v}, lab
    if key == "payment_delay":
        return {"receivable_days": v}, f"Payments {v:.0f} days slower"
    if key == "project_delay":
        return {"delay_months": v}, f"Project delay {v:.0f} months"
    if key == "collateral":
        return {"collateral_pct": -round(v / 100.0, 4)}, f"Collateral −{v:.0f}%"
    if key == "re_price":
        return {"real_estate_pct": -round(v, 1)}, f"Real-estate prices −{v:.0f}%"
    if key == "rating":
        n = int(v)
        return {"notches": n}, f"Rating −{n} notch{'es' if n > 1 else ''}"
    raise KeyError(key)


def combined(sev: str, cal: dict[str, dict[str, Any]], j: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    jv = j["joint"][sev]["values"]
    idi = "mild" if sev == "moderate" else "moderate"
    rev = float(cal["revenue"]["values"][idi])
    col = float(cal["collateral"]["values"][idi])
    rate = max(0.0, _r5(jv["saibor"]))
    sh = {"oil_pct": -round(jv["brent"], 1), "gdp_pct": -round(jv["gdp_nonoil"], 2), "revenue_pct": -round(rev / 100.0, 4),
          "collateral_pct": -round(col / 100.0, 4)}
    if rate > 0:
        sh["rate_bps"] = rate
    basis = (f"One coherent macro year from the joint model ({j['joint'][sev]['basis']}): oil −{jv['brent']:.0f}%, non-oil GDP "
             f"−{jv['gdp_nonoil']:.1f} pp" + (f", rates +{rate:.0f} bps" if rate > 0 else ", rates unchanged (they did not rise with "
                                                                                    "oil falls in history)")
             + f"; with the {idi} borrower revenue shock (revenue −{rev:.0f}%, expert) and collateral −{col:.0f}% (expert); the "
               f"oil and GDP moves are drawn together as they moved in history, never as independent tails.")
    label = "Combined moderate" if sev == "moderate" else "Combined severe"
    return sh, label, basis


def reversal_shocks(sev: str, r: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    rv = r["reversal"][sev]
    today = r["brent"]["latest"]["value"]
    hist = ", ".join(f"{h['label']} {h['fall_pct']:.0f}%" for h in r["reversal"]["history"])
    basis = (f"Oil reversal from today's level ({r['label']}, Brent USD {today:.0f} on {r['brent']['latest']['date']}): "
             f"USD {today:.0f} → {rv['to_usd']:.0f}, {rv['fall_pct']:.0f}% ({rv['basis']}); post-spike reversals in "
             f"{regime_mod().YEARS} years: {hist}. Conditional calibration: {conditional_mod().conditional_brent()['text']}")
    return {"oil_pct": round(rv["fall_pct"], 1)}, f"Oil reversal {rv['fall_pct']:.0f}% (USD {today:.0f} → {rv['to_usd']:.0f})", basis


def disruption_combined(sev: str, cal: dict[str, dict[str, Any]], j: dict[str, Any], r: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    jv = j["joint"][sev]["values"]
    idi = "mild" if sev == "moderate" else "moderate"
    rev = float(cal["revenue"]["values"][idi])
    mar = max(5.0, _r5(float(cal["margin"]["values"][idi])))
    days = float(cal["payment_delay"]["values"][idi])
    rate = max(0.0, _r5(max(jv["saibor"], float(cal["saibor"]["values"]["mild"]))))
    # oil_pct 0: oil stays at today's (high) level in a disruption; kept explicit so every reader names the oil leg
    sh = {"oil_pct": 0.0, "gdp_pct": -round(jv["gdp_nonoil"], 2), "revenue_pct": -round(rev / 100.0, 4),
          "ebitda_margin_bps": -mar, "receivable_days": days}
    if rate > 0:
        sh["rate_bps"] = rate
    basis = (f"Conflict and trade disruption in the {r['label']} (Brent USD {r['brent']['latest']['value']:.0f}, "
             f"{r['brent']['change_12m_pct']:+.0f}% in 12 months): non-oil GDP −{jv['gdp_nonoil']:.1f} pp (the joint {sev} year, "
             f"{j['joint'][sev]['basis']}) with no oil fall; revenue −{rev:.0f}% (expert {idi}); freight and input cost through "
             f"the EBITDA margin −{mar:.0f} bps (calibrated {idi}); payments {days:.0f} days slower from government and "
             f"contractors (expert {idi}); funding cost +{rate:.0f} bps (FX / liquidity).")
    label = "Combined moderate (trade disruption)" if sev == "moderate" else "Combined severe (trade disruption)"
    return sh, label, basis


def regime_mod():
    from backend.scenarios import regime
    return regime


def conditional_mod():
    from backend.scenarios import conditioned
    return conditioned


def calibrated_rows(prior_versions: dict[str, int] | None = None, conditioned: bool | None = None) -> list[dict[str, Any]]:
    """The R13-S1 ladder in Session D's internal row shape (`catalogue.seed_ladder`), one row per scenario id."""
    cal = calibrate.calibrate_all()
    j = joint.build()
    prior = prior_versions or {}
    rows = []

    def add(sid: str, fam: str, sev: str, label: str, shocks: dict[str, Any], basis: str, source: str) -> None:
        rows.append({"scenario_id": sid, "version": int(prior.get(sid, 0)) + 1, "set_id": SET_ID, "scope": "bank",
                     "proposal_id": None, "family": fam, "severity": sev, "label": label, "shocks": shocks, "basis": basis,
                     "source": source, "status": "approved", "maker": MAKER, "made_at": MADE_AT, "checker": CHECKER,
                     "checked_at": MADE_AT, "reason": "R13 §S: severities calibrated on the historical distribution (J5)"})

    r = regime_mod().current()
    high = regime_mod().is_high(r) if conditioned is None else conditioned
    for key, (ids, fam) in ROWS.items():
        row = cal[key]
        for sid, sev in zip(ids, SEV):
            if key == "brent" and high:
                sh, label, basis = reversal_shocks(sev, r)
                add(sid, fam, sev, label, sh, basis, f"regime {SET_ID}: oil reversal from today's level (whatif.mev_latest, "
                                                      "whatif.brent_monthly_eia)")
                continue
            sh, label = shocks_for(key, sev, cal)
            how = _freq_text(row, sev)
            basis = f"{row['label']}: {row['display'][sev]}; {how}."
            src = (f"calibrated {SET_ID} ({row['source']})" if row["method"] == "empirical"
                   else f"fallback {SET_ID}: {row['fallback_label']}")
            add(sid, fam, sev, label, sh, basis, src)
    add("guarantee_void", "collateral", "severe", "Guarantee unenforceable", {"guarantee_unenforceable": True},
        "The guarantee or credit insurance cannot be called: expert severe case (no enforcement history in the bank data).",
        f"fallback {SET_ID}: expert (no enforcement history)")
    for sev, sid in (("moderate", "combined_moderate"), ("severe", "combined_severe")):
        if high:
            sh, label, basis = disruption_combined(sev, cal, j, r)
            add(sid, "combined", sev, label, sh, basis, f"regime {SET_ID} (joint macro growth and rates; expert revenue and delay)")
            continue
        sh, label, basis = combined(sev, cal, j)
        add(sid, "combined", sev, label, sh, basis, f"calibrated {SET_ID} (joint macro: Gaussian copula and analogues)")
    return rows


def publish() -> dict[str, Any]:
    """Publish the R13-S1 ladder as the next version of every scenario (idempotent: skipped when already in force)."""
    from backend.dealdesk.stress2 import catalogue as cat
    from backend.dealdesk.stress2 import store
    cat.ensure_seeded()
    have = store.read("dd_stress_scenario")
    prior: dict[str, int] = {}
    mine: dict[str, dict[str, Any]] = {}
    for r in have:
        if r.get("set_id") == SET_ID:
            if int(r.get("version") or 1) >= int((mine.get(r["scenario_id"]) or {}).get("version") or 0):
                mine[r["scenario_id"]] = r
        else:
            prior[r["scenario_id"]] = max(prior.get(r["scenario_id"], 0), int(r.get("version") or 1))
    rows = []
    for r in calibrated_rows(prior):
        cur = mine.get(r["scenario_id"])
        if cur is not None:
            # the set is already in force: republish only when the content changed, as the next version (R14 m: the
            # regime-conditioned rows keep the R13 version beside them, so the history shows both)
            same = (store.decode(cur.get("shocks")) or {}) == r["shocks"] and cur.get("basis") == r["basis"] and \
                cur.get("label") == r["label"]
            if same:
                continue
            r = {**r, "version": int(cur.get("version") or 1) + 1, "made_at": REGIME_MADE_AT, "checked_at": REGIME_MADE_AT,
                 "reason": "R14 m (K12): severities conditioned on the current regime" if r["source"].startswith("regime")
                 else r["reason"]}
        rows.append(r)
    res = store.publish("dd_stress_scenario", rows, actor="S") if rows else {"rows": 0}
    return {"relation": "dd_stress_scenario", "set_id": SET_ID, "published": len(rows), "already": len(mine),
            "backend": store.backend("dd_stress_scenario"), "result": res}
