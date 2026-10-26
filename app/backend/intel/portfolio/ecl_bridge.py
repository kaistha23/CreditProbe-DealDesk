"""ECL bridge forecast (R14 backlog #17): next quarter's corporate ECL before the run, the stage movers, the PD / LGD / EAD
drivers, the bridge from the current run, and a drafted overlay justification.

Opening: ecl_runs.ecl_facility, run 2026Q3 (the 2026Q2 book). Per facility the run's ECL is the stage formula
    Stage 1: EAD x PD12 x LGD     Stage 2: EAD x PDlifetime x LGD     Stage 3: EAD x LGD
(it reproduces the run to the cent; the run's management overlay is inside it and shown separately).

1. Stage movers (EWS model). From Early Warning ews.corp_exposure (20 quarters) the engine counts every facility's move
   from quarter t to t+1 by (stage_t, EWS band_t) into {Stage 1, 2, 3, exit} over the last `window` transitions (exit =
   repaid or written off: the facility is not in the book at t+1). Each facility's next-quarter stage distribution is the
   row for its stage and current band (pooled by stage when a cell has fewer than `min_n` moves). Expected ECL after
   moves = sum over stages of P(stage) x the stage formula at today's EAD, PD and LGD. Cross-check: the Deal Desk
   forward-risk chain (backend/dealdesk/transition_model, cure and Stage 2 to 3 rates).
2. PD and LGD drivers. Sector trend of the EAD-weighted performing PD12 and LGD over the last 4 quarters of the
   corporate book (cockpit.corp_facility_quarter), as a quarterly geometric rate, applied to every surviving facility.
3. EAD driver. Average quarterly EAD change of facilities present in consecutive quarters, by product, last 4 quarters.
4. Bridge (sequential, adds up exactly): opening -> stage moves and exits -> PD -> LGD -> EAD -> closing.
5. Back-test. The same method estimated on transitions up to 2026Q1 and run from the 2026Q1 book predicts 2026Q2 Stage
   2 and Stage 3 EAD and the inflows into Stage 2 and Stage 3; an under-predicted inflow drives the drafted overlay.
6. Macro (R14 G, ID gap 4): the §S calibrated scenarios (deal_desk.dd_scenario_result, the corporate book under the joint
   scenarios by severity and sector, latest version; severities from dd_scenario_calibration) are applied on top of the
   base forecast: each sector's stressed / start ECL ratio over §S's one-year horizon, a quarter carrying a quarter of its
   log change, scales that sector's closing ECL. The base bridge is the no-new-shock path; the §S paths are shown beside it,
   each with its data window and calibration fingerprint.
New business, write-off policy changes, scenario weights and model recalibrations are not forecast (data limits).
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.intel.portfolio import common as C

STATES = ("1", "2", "3", "exit")


@functools.lru_cache(maxsize=1)
def _ews() -> pd.DataFrame:
    e = C._frame("ews", "corp_exposure")
    return e[["facility_id", "borrower_id", "reporting_quarter", "stage", "ews_band", "ead_sar_mn", "pd_pit_12m", "lgd_pct",
              "sector", "product_type", "ews_reasons"]].copy()


def _transitions(e: pd.DataFrame, upto: str, window: int) -> pd.DataFrame:
    qs = sorted(e["reporting_quarter"].unique())
    qs = [q for q in qs if q <= upto]
    pairs = list(zip(qs[:-1], qs[1:]))[-window:]
    out = []
    for a, b in pairs:
        x = e[e["reporting_quarter"] == a][["facility_id", "stage", "ews_band"]]
        y = e[e["reporting_quarter"] == b].set_index("facility_id")["stage"]
        nxt = x["facility_id"].map(y)
        out.append(x.assign(next=np.where(nxt.isna(), "exit", nxt.fillna(0).astype(int).astype(str))))
    return pd.concat(out, ignore_index=True)


def _matrix(tr: pd.DataFrame, min_n: int) -> tuple[dict[tuple[int, str], dict[str, float]], list[dict[str, Any]]]:
    pooled = {s: (g["next"].value_counts(normalize=True).reindex(STATES).fillna(0).to_dict(), len(g))
              for s, g in tr.groupby("stage")}
    mat, table = {}, []
    for (s, band), g in tr.groupby(["stage", "ews_band"]):
        n = len(g)
        row = g["next"].value_counts(normalize=True).reindex(STATES).fillna(0).to_dict() if n >= min_n else pooled[s][0]
        mat[(int(s), str(band))] = row
        table.append({"stage": int(s), "ews_band": str(band), "n": n, "pooled": n < min_n,
                      **{f"p_{k}": float(v) for k, v in row.items()}})
    for s, (row, n) in pooled.items():
        mat[(int(s), "*")] = row
    return mat, table


def _probs(cur: pd.DataFrame, mat) -> np.ndarray:
    P = np.zeros((len(cur), 4))
    for i, (s, b) in enumerate(zip(cur["stage"].astype(int), cur["ews_band"].astype(str))):
        row = mat.get((s, b)) or mat.get((s, "*")) or {"1": 0, "2": 0, "3": 0, "exit": 0, str(s): 1}
        P[i] = [row.get(k, 0.0) for k in STATES]
    return P


def _stage_ecl(ead, pd12, pdlt, lgd) -> np.ndarray:
    return np.vstack([ead * pd12 * lgd, ead * pdlt * lgd, ead * lgd, np.zeros_like(ead)]).T


def _trend(h: pd.DataFrame, col: str, by: str, quarters: int = 4) -> dict[str, float]:
    qs = sorted(h["reporting_quarter"].unique())[-(quarters + 1):]
    p = h[(h["reporting_quarter"].isin(qs)) & (h["stage"] < 3)]
    w = p.assign(x=p[col] * p["ead_sar_mn"]).groupby([by, "reporting_quarter"])[["x", "ead_sar_mn"]].sum()
    lvl = (w["x"] / w["ead_sar_mn"]).unstack()
    rate = (lvl[qs[-1]] / lvl[qs[0]]) ** (1 / quarters)
    return rate.replace([np.inf, -np.inf], np.nan).fillna(1.0).clip(0.8, 1.25).to_dict()


def _ead_trend(h: pd.DataFrame, quarters: int = 4) -> dict[str, float]:
    qs = sorted(h["reporting_quarter"].unique())[-(quarters + 1):]
    rates = []
    for a, b in zip(qs[:-1], qs[1:]):
        x = h[h["reporting_quarter"] == a].set_index("facility_id")[["ead_sar_mn", "product_type"]]
        y = h[h["reporting_quarter"] == b].set_index("facility_id")["ead_sar_mn"]
        j = x.join(y.rename("next"), how="inner")
        rates.append(j.groupby("product_type")["next"].sum() / j.groupby("product_type")["ead_sar_mn"].sum())
    return pd.concat(rates, axis=1).mean(axis=1).clip(0.8, 1.2).to_dict()


BACKTEST_QUARTERS = 4


def _backtest(e: pd.DataFrame, window: int, min_n: int) -> dict[str, Any]:
    """The latest quarter's back-test in detail, plus inflows pooled over the last BACKTEST_QUARTERS quarters."""
    qs = sorted(e["reporting_quarter"].unique())
    last = _backtest_one(e, qs[-2], qs[-1], window, min_n)
    runs = [last] + [_backtest_one(e, a, b, window, min_n) for a, b in list(zip(qs[:-1], qs[1:]))[-BACKTEST_QUARTERS:-1]]
    pp = {k: sum(r["inflow_predicted_ead"][k] for r in runs) for k in ("2", "3")}
    pa = {k: sum(r["inflow_actual_ead"][k] for r in runs) for k in ("2", "3")}
    last["pooled"] = {"quarters": [f"{r['from']}->{r['to']}" for r in runs], "inflow_predicted_ead": pp, "inflow_actual_ead": pa,
                      "inflow_error": {k: (pp[k] - pa[k]) / pa[k] if pa[k] else None for k in ("2", "3")},
                      "by_quarter": [{"from": r["from"], "to": r["to"], "inflow_error": r["inflow_error"]} for r in runs]}
    return last


def _backtest_one(e: pd.DataFrame, q_from: str, q_to: str, window: int, min_n: int) -> dict[str, Any]:
    mat, _ = _matrix(_transitions(e, q_from, window), min_n)
    cur = e[e["reporting_quarter"] == q_from]
    P = _probs(cur, mat)
    ead = cur["ead_sar_mn"].to_numpy(float)
    pred = {s: float((P[:, i] * ead).sum()) for i, s in enumerate(("1", "2", "3"))}
    act_df = e[(e["reporting_quarter"] == q_to) & e["facility_id"].isin(cur["facility_id"])]
    act = {s: float(act_df.loc[act_df["stage"] == int(s), "ead_sar_mn"].sum()) for s in ("1", "2", "3")}
    # compare on the same EAD base (survivors at today's EAD) to isolate the stage error
    surv = cur.set_index("facility_id")["ead_sar_mn"]
    act_same = {s: float(surv.reindex(act_df.loc[act_df["stage"] == int(s), "facility_id"]).sum()) for s in ("1", "2", "3")}
    err = {s: (pred[s] - act_same[s]) / act_same[s] if act_same[s] else None for s in ("2", "3")}
    # inflows: Stage 1 -> 2 and Stage 1/2 -> 3, predicted vs actual on the same EAD base
    st0 = cur["stage"].to_numpy()
    nxt = cur["facility_id"].map(act_df.set_index("facility_id")["stage"]).to_numpy()
    in_pred = {"2": float((P[st0 == 1, 1] * ead[st0 == 1]).sum()), "3": float((P[st0 < 3, 2] * ead[st0 < 3]).sum())}
    in_act = {"2": float(ead[(st0 == 1) & (nxt == 2)].sum()), "3": float(ead[(st0 < 3) & (nxt == 3)].sum())}
    in_err = {s: (in_pred[s] - in_act[s]) / in_act[s] if in_act[s] else None for s in ("2", "3")}
    return {"from": q_from, "to": q_to, "inflow_predicted_ead": in_pred, "inflow_actual_ead": in_act, "inflow_error": in_err, "predicted_ead": pred, "actual_ead_same_base": act_same, "actual_ead": act,
            "error": err, "facilities": int(len(cur))}


def compute(window: int = 8, min_n: int = 200, movers: int = 25) -> dict[str, Any]:
    lin = C.Lineage()
    run = C.read(lin, "ecl_runs", "ecl_facility", ["exposure_id", "obligor_id", "book", "ead_sar_mn", "pd_12m_pct",
                                                   "pd_lifetime_pct", "lgd_pct", "stage", "rating", "overlay_sar_mn", "ecl_sar_mn"],
                 period=("run_id", C.RUN_CURRENT))
    run = run[run["book"] == "corporate"].reset_index(drop=True)
    e = _ews()
    lin.add("ews", "corp_exposure", period="2021Q3-2026Q2", rows=int(len(e)),
            columns=["facility_id", "reporting_quarter", "stage", "ews_band", "ead_sar_mn"])
    last = e["reporting_quarter"].max()
    now = e[e["reporting_quarter"] == last].set_index("facility_id")
    cur = run.assign(ews_band=run["exposure_id"].map(now["ews_band"]).fillna("none"),
                     sector=run["exposure_id"].map(now["sector"]), product_type=run["exposure_id"].map(now["product_type"]),
                     borrower_name=run["exposure_id"].map(now["borrower_id"]),
                     ews_reasons=run["exposure_id"].map(now["ews_reasons"]))
    names = C._frame("cockpit", "corp_borrower_quarter")
    names = names[names["reporting_quarter"] == C.AS_OF_QUARTER].set_index("borrower_id")["borrower_name"]
    cur["borrower_name"] = cur["obligor_id"].map(names)

    tr = _transitions(e, last, window)
    mat, table = _matrix(tr, min_n)
    P = _probs(cur, mat)
    ead = cur["ead_sar_mn"].to_numpy(float)
    pd12 = cur["pd_12m_pct"].to_numpy(float) / 100
    pdlt = np.maximum(cur["pd_lifetime_pct"].to_numpy(float) / 100, pd12)
    lgd = cur["lgd_pct"].to_numpy(float) / 100
    st = cur["stage"].astype(int).to_numpy()
    E = _stage_ecl(ead, pd12, pdlt, lgd)
    opening = float(cur["ecl_sar_mn"].sum())
    e_now = E[np.arange(len(cur)), st - 1]
    cal = float(opening / e_now.sum()) if e_now.sum() else 1.0
    after_stage = (P * E).sum(axis=1)

    hist = C.read(lin, "cockpit", "corp_facility_quarter", ["facility_id", "reporting_quarter", "stage", "ead_sar_mn",
                                                            "pd_pit_12m", "lgd_pct", "sector", "product_type"])
    pd_rate = _trend(hist, "pd_pit_12m", "sector")
    lgd_rate = _trend(hist, "lgd_pct", "sector")
    ead_rate = _ead_trend(hist)
    fp = cur["sector"].map(pd_rate).fillna(1.0).to_numpy(float)
    fl = cur["sector"].map(lgd_rate).fillna(1.0).to_numpy(float)
    fe = cur["product_type"].map(ead_rate).fillna(1.0).to_numpy(float)
    E_pd = _stage_ecl(ead, np.minimum(pd12 * fp, 1), np.minimum(pdlt * fp, 1), lgd)
    E_pd[:, 2] = E[:, 2]
    after_pd = (P * E_pd).sum(axis=1)
    E_lgd = _stage_ecl(ead, np.minimum(pd12 * fp, 1), np.minimum(pdlt * fp, 1), np.minimum(lgd * fl, 1))
    after_lgd = (P * E_lgd).sum(axis=1)
    after_ead = after_lgd * fe
    steps = [("opening", "ECL run " + C.RUN_CURRENT, opening),
             ("stage", "Stage moves and exits (EWS model)", float(after_stage.sum() - e_now.sum())),
             ("pd", "PD drift (sector trend)", float(after_pd.sum() - after_stage.sum())),
             ("lgd", "LGD drift (sector trend)", float(after_lgd.sum() - after_pd.sum())),
             ("ead", "EAD change (product trend)", float(after_ead.sum() - after_lgd.sum()))]
    closing = opening + sum(s[2] for s in steps[1:])
    bridge = [{"key": k, "label": lab, "value_sar_mn": v} for k, lab, v in steps]
    bridge.append({"key": "closing", "label": f"Forecast {C.NEXT_RUN} before overlay review", "value_sar_mn": closing})
    del cal

    # stage movers: expected ECL increase from stage moves alone, by facility
    d_stage = after_stage - e_now
    p_worse = np.where(st == 1, P[:, 1] + P[:, 2], np.where(st == 2, P[:, 2], 0.0))
    # stage movers by obligor (CBUAE stages at obligor level): the facility with the largest expected rise leads the row
    obl = cur["obligor_id"].to_numpy()
    by_obl = pd.Series(d_stage).groupby(obl).sum()
    by_obl = by_obl[by_obl > 0].sort_values(ascending=False).head(movers)
    lead = pd.Series(d_stage).groupby(obl).idxmax()
    nfac = pd.Series(d_stage > 0).groupby(obl).sum()
    mv = []
    for oid, inc in by_obl.items():
        i = int(lead[oid])
        mv.append({"facility_id": cur["exposure_id"].iloc[i], "borrower_id": oid, "facilities": int(nfac[oid]),
                   "borrower_name": cur["borrower_name"].iloc[i], "sector": cur["sector"].iloc[i], "rating": cur["rating"].iloc[i],
                   "stage": int(st[i]), "ews_band": cur["ews_band"].iloc[i], "ews_reasons": cur["ews_reasons"].iloc[i],
                   "ead_sar_mn": float(ead[obl == oid].sum()), "p_stage2": float(P[i, 1]), "p_stage3": float(P[i, 2]),
                   "p_worse": float(p_worse[i]), "ecl_now_sar_mn": float(e_now[obl == oid].sum()),
                   "ecl_if_moves_sar_mn": float(E[i, 2] if st[i] == 2 else E[i, 1]),
                   "expected_increase_sar_mn": float(inc)})
    exp_ead = {s: float((P[:, i] * ead).sum()) for i, s in enumerate(("1", "2", "3"))}
    now_ead = {s: float(ead[st == int(s)].sum()) for s in ("1", "2", "3")}

    bt = _backtest(e, window, min_n)
    anom = C.read(lin, "ecl_runs", "ecl_anomaly", ["anomaly_id", "run_id", "exposure_id", "kind", "rerun_required"])
    anom = anom[(anom["run_id"] == C.RUN_CURRENT) & (anom["rerun_required"] == 1)]
    ov_now = float(cur["overlay_sar_mn"].sum())
    overlay = _overlay(closing, bt, cur, P, E, st, anom, ov_now)

    try:
        from backend.dealdesk import transition_model as tm
        chain = tm.meta()["chain"]
        lin.add("cockpit", "corp_facility_quarter", note="forward-risk chain (backend/dealdesk/transition_model)")
        s2 = [t for t in table if t["stage"] == 2]
        cross = {"forward_risk_s2_to_s1": chain["s2_to_s1"], "forward_risk_s2_to_s3": chain["s2_to_s3"],
                 "ews_model_s2_to_s1": float(np.average([t["p_1"] for t in s2], weights=[t["n"] for t in s2])) if s2 else None,
                 "ews_model_s2_to_s3": float(np.average([t["p_3"] for t in s2], weights=[t["n"] for t in s2])) if s2 else None,
                 "basis": chain.get("basis")}
    except Exception:  # noqa: BLE001 - cross-check only
        cross = None

    macro = _macro(lin, cur["sector"].to_numpy(), after_ead, closing)
    summary = _write(opening, closing, bridge, mv, exp_ead, now_ead, bt, overlay)
    if macro["scenarios"]:
        mod = next((x for x in macro["scenarios"] if x["severity"] == "moderate"), macro["scenarios"][0])
        summary.insert(1, f"Under the §S {mod['severity']} scenario the forecast is {C.sar(mod['closing_sar_mn'])} "
                          f"({mod['delta_sar_mn']:+,.0f}m on the base path; §S window {macro['window']}, calibration {macro['fingerprint']}).")
    kpis = [C.kpi("opening", f"ECL run {C.RUN_CURRENT}", opening, "SAR m"),
            C.kpi("forecast", f"Forecast {C.NEXT_RUN}", closing, "SAR m", f"{(closing / opening - 1) * 100:+.1f}%"),
            C.kpi("stage2_ead", "Stage 2 EAD next quarter", exp_ead["2"], "SAR m", f"now {C.sar(now_ead['2'], 0)}"),
            C.kpi("stage3_ead", "Stage 3 EAD next quarter", exp_ead["3"], "SAR m", f"now {C.sar(now_ead['3'], 0)}"),
            C.kpi("overlay", "Drafted overlay", overlay["amount_sar_mn"], "SAR m", f"current {C.sar(ov_now)}")]
    for x in macro["scenarios"]:
        if x["severity"] == "moderate":
            kpis.append(C.kpi("forecast_s_moderate", f"Forecast {C.NEXT_RUN}, §S moderate", x["closing_sar_mn"], "SAR m",
                              f"{x['delta_sar_mn']:+,.0f}m on the base path"))
    limits = [
        f"The EWS model is estimated on {len(tr):,} facility-quarter moves ({window} quarters, one partial credit cycle); "
        f"cells with fewer than {min_n} moves use the stage's pooled row.",
        "New business, repayments other than full exits, write-off policy changes, scenario-weight changes and model "
        "recalibration are not forecast. Macro comes from the §S calibrated scenarios (dd_scenario_result), shown beside the "
        "base path: a quarter carries a quarter of §S's one-year log change by sector (a pro-rata assumption, not a quarterly model).",
        "PD and LGD drift extrapolate the last 4 quarters' sector trend (clipped to +/-25% a quarter); a turn in the cycle "
        "will not show until it is in the data.",
        "The run's ECL includes its management overlay; the drafted overlay is an addition proposed for review, not booked.",
    ]
    method = ["Stage distribution next quarter: empirical P(stage', exit | stage, EWS band) from ews.corp_exposure.",
              "ECL per stage from the run's own EAD, PD and LGD; drivers applied in sequence so the bridge adds up exactly.",
              f"Back-test {bt['from']} -> {bt['to']} on the same method; error drives the drafted overlay."]
    return C.envelope("ecl_bridge", "ECL bridge forecast", summary[0], summary, kpis, mv, limits, method, lin,
                      {"bridge": bridge, "stage_ead_now": now_ead, "stage_ead_next": exp_ead, "transition_table": table,
                       "drivers": {"pd_rate_by_sector": pd_rate, "lgd_rate_by_sector": lgd_rate, "ead_rate_by_product": ead_rate},
                       "backtest": bt, "overlay": overlay, "cross_check": cross, "next_run": C.NEXT_RUN, "macro": macro})


def _macro(lin: C.Lineage, sector: np.ndarray, closing_fac: np.ndarray, closing: float) -> dict[str, Any]:
    """R14 G: the base forecast under each §S calibrated scenario (latest version of dd_scenario_result)."""
    out: dict[str, Any] = {"source": "deal_desk.dd_scenario_result", "scenarios": [], "window": "", "fingerprint": "", "engine_version": ""}
    try:
        r = C.read(lin, "deal_desk", "dd_scenario_result", ["severity", "sector", "version", "ecl_start_mn", "ecl_stressed_mn",
                                                             "stage2_share_start", "stage2_share_stressed", "as_of", "engine_version", "rel_version"])
        c = C.read(lin, "deal_desk", "dd_scenario_calibration", ["driver", "severity", "window", "fingerprint", "source", "value", "unit", "label"])
    except Exception as e:  # noqa: BLE001 - §S not published on this branch: the base path stands alone, said so
        out["note"] = f"§S scenarios not available ({type(e).__name__}): base path only."
        return out
    if not len(r):
        out["note"] = "§S scenarios not published: base path only."
        return out
    r = r[r["version"] == r["version"].max()]
    out["engine_version"] = str(r["engine_version"].iloc[0])
    out["as_of"] = str(r["as_of"].iloc[0])
    if len(c):
        out["fingerprint"] = str(c["fingerprint"].iloc[0])
        w = sorted({str(x) for x in c["window"].dropna().unique()})
        out["window"] = ", ".join(w[:3])
        brent = c[c["driver"] == "brent"].set_index("severity")
    else:
        brent = pd.DataFrame()
    sec = pd.Series(closing_fac).groupby(sector).sum()
    for sev in ("mild", "moderate", "severe"):
        x = r[r["severity"] == sev]
        if not len(x):
            continue
        book = x[x["sector"] == "*"]
        ratio = (x.set_index("sector")["ecl_stressed_mn"] / x.set_index("sector")["ecl_start_mn"]).replace([np.inf, -np.inf], np.nan)
        book_ratio = float(book["ecl_stressed_mn"].iloc[0] / book["ecl_start_mn"].iloc[0]) if len(book) and book["ecl_start_mn"].iloc[0] else 1.0
        q_factor = {k: float(v) ** 0.25 for k, v in ratio.dropna().items() if k != "*" and v > 0}
        stressed = float(sum(v * q_factor.get(k, book_ratio ** 0.25) for k, v in sec.items()))
        row = {"severity": sev, "closing_sar_mn": stressed, "delta_sar_mn": stressed - closing,
               "book_ratio_one_year": book_ratio,
               "stage2_share_start": float(book["stage2_share_start"].iloc[0]) if len(book) else None,
               "stage2_share_stressed": float(book["stage2_share_stressed"].iloc[0]) if len(book) else None,
               "source": {"domain": "deal_desk", "relation": "dd_scenario_result",
                          "key": {"severity": sev, "sector": "*", "version": int(x["version"].iloc[0]), "reporting_quarter": out["as_of"]},
                          "column": "ecl_stressed_mn", "period": out["as_of"]}}
        if sev in brent.index:
            b = brent.loc[sev]
            row["brent_fall_pct"] = float(b["value"])
            row["label"] = f"§S {sev}: {b['label']} {float(b['value']):.0f}%, with the joint drivers"
        else:
            row["label"] = f"§S {sev}"
        out["scenarios"].append(row)
    return out


def _overlay(closing, bt, cur, P, E, st, anom, ov_now) -> dict[str, Any]:
    parts = []
    def short(key: str) -> tuple[float, float] | None:
        p_, a_ = bt["pooled"]["inflow_predicted_ead"][key], bt["pooled"]["inflow_actual_ead"][key]
        return (a_ / p_ - 1.0, (p_ - a_) / a_) if p_ > 0 and a_ > p_ else None
    s2 = short("2")
    if s2:
        # the method under-predicted Stage 1 -> 2 inflow: scale the expected Stage 1 -> 2 increase up to the observed inflow
        inc12 = float((P[st == 1, 1] * (E[st == 1, 1] - E[st == 1, 0])).sum())
        parts.append({"key": "stage2_inflow_underprediction", "amount_sar_mn": inc12 * s2[0],
                      "why": f"Stage 1 to 2 inflow was under-predicted by {C.pct(-s2[1])} over the last {len(bt['pooled']['quarters'])} back-tested quarters"})
    s3 = short("3")
    if s3:
        inc3 = float((P[st < 3, 2] * (E[st < 3, 2] - E[st < 3, np.minimum(st[st < 3], 2) - 1])).sum())
        parts.append({"key": "stage3_inflow_underprediction", "amount_sar_mn": inc3 * s3[0],
                      "why": f"inflow into Stage 3 was under-predicted by {C.pct(-s3[1])} over the last {len(bt['pooled']['quarters'])} back-tested "
                             f"quarters (predicted {C.sar(bt['pooled']['inflow_predicted_ead']['3'], 0)} of EAD, observed "
                             f"{C.sar(bt['pooled']['inflow_actual_ead']['3'], 0)}); "
                             "the expected Stage 3 ECL increase is scaled up to the observed inflow"})
    hi = (cur["ews_band"].isin(["high", "critical"]).to_numpy()) & (st == 1)
    if hi.any():
        gap = float((E[hi, 1] - E[hi, 0]).sum() - (P[hi, 1] * (E[hi, 1] - E[hi, 0])).sum())
        parts.append({"key": "ews_high_stage1", "amount_sar_mn": 0.5 * max(gap, 0.0),
                      "why": f"{int(hi.sum())} Stage 1 facilities are Early Warning high or critical; half the lifetime uplift the "
                             "model does not already expect is held against a SICR the model has not seen"})
    if len(anom):
        ids = set(anom["exposure_id"])
        m = cur["exposure_id"].isin(ids).to_numpy()
        parts.append({"key": "run_anomalies", "amount_sar_mn": float(0.1 * cur.loc[m, "ecl_sar_mn"].sum()),
                      "why": f"{len(ids)} exposures carry ECL input anomalies needing a rerun (ecl_anomaly); 10% of their ECL "
                             "is held until the rerun"})
    amt = float(sum(p["amount_sar_mn"] for p in parts))
    text = _overlay_text(closing, amt, parts, ov_now)
    return {"amount_sar_mn": amt, "components": parts, "current_overlay_sar_mn": ov_now, "text": text,
            "status": "draft for the ECL committee; not booked"}


def _overlay_text(closing, amt, parts, ov_now) -> str:
    if amt <= 0:
        return (f"No additional overlay is proposed for {C.NEXT_RUN}: the method did not under-predict stage moves in the "
                f"back-test and no Stage 1 name is Early Warning high or critical. The current overlay of {C.sar(ov_now)} is kept.")
    lines = [f"Proposed post-model adjustment for {C.NEXT_RUN}: {C.sar(amt)} on a modelled forecast of {C.sar(closing)} "
             f"({C.pct(amt / closing)}), in addition to the current overlay of {C.sar(ov_now)}."]
    for p in parts:
        lines.append(f"- {C.sar(p['amount_sar_mn'])}: {p['why']}.")
    lines.append("Each component is released when the run captures the risk it covers (the facility moves stage, the "
                 "anomaly is rerun) or when the next back-test shows no under-prediction.")
    return "\n".join(lines)


def _write(opening, closing, bridge, mv, exp_ead, now_ead, bt, overlay) -> list[str]:
    d = closing - opening
    big = max(bridge[1:-1], key=lambda b: abs(b["value_sar_mn"]))
    out = [f"Next quarter's corporate ECL is forecast at {C.sar(closing)} before the {C.NEXT_RUN} run, "
           f"{'up' if d >= 0 else 'down'} {C.sar(abs(d))} ({d / opening * 100:+.1f}%) on the {C.RUN_CURRENT} run; "
           f"the largest driver is {big['label']} ({'+' if big['value_sar_mn'] >= 0 else '-'}{C.sar(abs(big['value_sar_mn']))})."]
    out.append(f"Stage 2 EAD is expected at {C.sar(exp_ead['2'], 0)} (now {C.sar(now_ead['2'], 0)}) and Stage 3 at "
               f"{C.sar(exp_ead['3'], 0)} (now {C.sar(now_ead['3'], 0)}).")
    if mv:
        top = mv[:3]
        out.append("Top stage movers: " + "; ".join(f"{m['borrower_name']} ({m['ews_band']}, +{C.sar(m['expected_increase_sar_mn'], 2)})"
                                                     for m in top) + ".")
    ie = bt["pooled"]["inflow_error"]
    if ie.get("2") is not None and ie.get("3") is not None:
        out.append(f"Back-test over {len(bt['pooled']['quarters'])} quarters to {bt['to']}: Stage 2 inflow {'over' if ie['2'] > 0 else 'under'}-predicted by {C.pct(abs(ie['2']))}, "
                   f"Stage 3 inflow {'over' if ie['3'] > 0 else 'under'}-predicted by {C.pct(abs(ie['3']))}.")
    out.append(f"Drafted overlay: {C.sar(overlay['amount_sar_mn'])} for committee review.")
    return out[:5]
