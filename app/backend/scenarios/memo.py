"""The scenario methodology memo (PLAN_R13 §S.5): Word, house style, the full mathematical workup. Every equation is
the one the engine ran (the code path is printed in section 12) and every number is read from `engine.build()`.

    from backend.scenarios import memo
    body = memo.build(generated_by="Anne (Administrator)")    # bytes; check.docx(body) == []
"""
from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from backend.house_style import ACCENT, Meta  # noqa: E402
from backend.house_style import docx as hd  # noqa: E402
from backend.scenarios import calibrate, engine, joint, translate  # noqa: E402

SEVS = ("mild", "moderate", "severe")
SEV_COL = {"mild": "#7FA7C9", "moderate": "#A16207", "severe": "#A92A25"}
hd.chart_style()


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _eq(doc, text: str) -> None:
    hd.para(doc, text, size=9.5, italic=True)


def _m(x: float | None) -> str:
    return "—" if x is None else f"{x:,.0f}"


def _p(x: float | None, dp: int = 2) -> str:
    return "—" if x is None else f"{x * 100:.{dp}f}%"


# ------------------------------------------------------------------ charts

def chart_distributions(cal: dict[str, Any]) -> io.BytesIO:
    keys = ["brent", "gdp_nonoil", "saibor", "sector_cycle"]
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 4.8))
    for ax, k in zip(axes.flat, keys):
        d = calibrate.drivers_by_key()[k]
        o = d.observe()
        ax.hist(o.values, bins=min(18, max(6, len(o.values) // 3)), color="#" + ACCENT, alpha=0.75)
        for s in SEVS:
            ax.axvline(cal[k]["values"][s], color=SEV_COL[s], lw=1.6, label=f"{s} {cal[k]['display'][s]}")
        ax.set_title(f"{d.label.split(',')[0]} ({d.window.split(' ')[0]})", fontsize=8)
        ax.set_xlabel(f"adverse one-year move ({d.unit})")
        ax.legend(fontsize=6.5)
    fig.tight_layout()
    return _png(fig)


def chart_joint(j: dict[str, Any]) -> io.BytesIO:
    h = joint.history()
    margins = [h[k].dropna().to_numpy() for k in joint.KEYS]
    _, x = joint.draws(np.array(j["copula"]), margins, n=3000)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.scatter(x[:, 0], x[:, 1], s=4, alpha=0.18, color="#7FA7C9", label="copula draws")
    ok = h[["brent", "gdp_real"]].dropna()
    ax.scatter(ok["brent"], ok["gdp_real"], s=16, color="#" + ACCENT, label="observed years")
    for y in joint.ANALOGUES:
        if y in ok.index:
            ax.annotate(str(y), (ok.loc[y, "brent"], ok.loc[y, "gdp_real"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    for s in SEVS:
        v = j["joint"][s]["values"]
        ax.scatter([v["brent"]], [v["gdp_real"]], s=60, marker="D", color=SEV_COL[s], label=f"joint {s}")
    ax.set_xlabel("Brent one-year fall (%)")
    ax.set_ylabel("Real GDP slowdown (pp)")
    ax.legend(fontsize=6.5, loc="upper left")
    return _png(fig)


def chart_backtest(bt: dict[str, Any]) -> io.BytesIO:
    rows = bt["rows"]
    q = [r["quarter"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(q, [r["reported_pd"] * 100 for r in rows], label="reported 12-month PD", color="#" + ACCENT, lw=1.8)
    ax.plot(q, [r["fitted_pd"] * 100 for r in rows], label="PD model, fitted", color="#A16207", lw=1.4, ls="--")
    ax.plot(q, [(r["default_rate"] or np.nan) * 100 for r in rows], label="observed default rate (annualised)", color="#A92A25", lw=1.2)
    ax.set_ylabel("% of performing EAD / facilities")
    ax.tick_params(axis="x", rotation=60, labelsize=6.5)
    ax.legend(fontsize=6.5)
    return _png(fig)


def chart_results(tr: dict[str, Any]) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(6.0, 2.8))
    vals = [tr[s]["ecl_change"] for s in SEVS]
    lo = [tr[s]["ecl_change"] - tr[s]["ecl_band"][0] for s in SEVS]
    hi = [tr[s]["ecl_band"][1] - tr[s]["ecl_change"] for s in SEVS]
    ax.bar(SEVS, vals, color=[SEV_COL[s] for s in SEVS], yerr=[lo, hi], capsize=4)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=7.5)
    ax.set_ylabel("ECL change (SAR million)")
    return _png(fig)


# ------------------------------------------------------------------ the memo

def build(generated_by: str = "", res: dict[str, Any] | None = None) -> bytes:  # noqa: C901 - one linear document
    res = res or engine.build()
    cal, j, sat, tr, w, lim = res["calibration"], res["joint"], res["satellite"], res["translation"], res["window"], res["limits"]
    rep = res["reproducibility"]
    meta = Meta("Scenario methodology memo", book="corporate", period=w["bank_to"],
                subject="Mild, moderate and severe from the historical distribution", generated_by=generated_by,
                reference=f"SCN-{rep['fingerprint']}")
    doc = hd.document(meta, kind="Methodology memo", subtitle="Data-driven stress scenarios, satellite models and translation",
                      details=[("Engine", f"{res['version']} (fingerprint {rep['fingerprint']})"),
                               ("Data", f"bank {w['bank_from']}–{w['bank_to']}; macro {w['macro_from']}–{w['macro_to']}")])

    # 1 ------------------------------------------------------------
    hd.heading(doc, "1. Purpose and scope")
    hd.para(doc, "This memo sets out how CreditProbe defines the **mild, moderate and severe** stress scenarios used by What-If and "
                 "the Deal Desk Stress Lab, how the drivers are combined, how they are translated into PD, LGD, EAD, ECL, stage and "
                 "capital, and what the data can and cannot support. It replaces the hand-set ladder of R12 (R12-L1) with "
                 f"severities read from history (set {res['calibration'] and 'R13-S1'}).")
    hd.key_figures(doc, [(f"ECL change, {s}", f"SAR {tr[s]['ecl_change']:,.0f}m") for s in SEVS]
                   + [(f"Stage 2 share, {s}", _p(tr[s]["stage2_share_stressed"], 1)) for s in SEVS])
    hd.para(doc, f"**What the data supports.** {lim['supports']}")
    hd.para(doc, f"**What it does not.** {lim['cannot']}")
    from backend.scenarios import conditioned, regime as _rg
    _r = _rg.current()
    hd.para(doc, "**Current regime (R14).** " + " ".join(_r["lines"]).replace("**", "") + " " + _r["vintage_line"])
    hd.para(doc, "**Conditional on today's level.** " + conditioned.conditional_brent()["text"])

    # 2 ------------------------------------------------------------
    hd.heading(doc, "2. Data and its limits")
    rows = [[rel["relation"], rel["file"], rel["sha256_16"]] for rel in rep["relations"]]
    hd.table(doc, ["Relation", "File", "SHA-256 (16)"], rows, widths=[5.0, 8.5, 3.0])
    rd = res["resolved_defaults"]
    hd.bullets(doc, [
        f"Bank history: {w['bank_quarters']} quarters ({w['bank_from']}–{w['bank_to']}), 14 sectors; four-quarter moves overlap, so "
        "independent one-year observations are counted as non-overlapping years per unit.",
        f"Macro: annual since {w['macro_from']} (Brent, real GDP: {w['macro_years']} years, {w['macro_years'] - 1} one-year moves), non-oil GDP since {w['nonoil_from']}, "
        f"3-month SAIBOR since {w['saibor_from']}, real-estate prices since {w['re_price_from']}.",
        f"Defaults: {rd['defaulted_facilities']:,} facilities defaulted in the window; {rd['resolved_facilities']:,} have a booked "
        f"recovery or write-off, all since {rd['first_resolution']}: too few finished workouts for a downturn LGD.",
        "No long property price index and no customer-level revenue, receivable-day or project-milestone history.",
    ])

    # 3 ------------------------------------------------------------
    hd.heading(doc, "3. Driver distributions")
    hd.para(doc, "For each driver, the one-year move in the adverse direction (a fall that hurts is written positive). The table "
                 "gives the severities in force, the method and the evidence.")
    rows = []
    for k, r in cal.items():
        e = r["estimate"] or {}
        f = (e.get("freq") or {}).get("moderate") or {}
        rows.append([r["label"], r["method"], r["display"]["mild"], r["display"]["moderate"], r["display"]["severe"],
                     f"{e['n']:,} / {e['n_independent']:,}" if e else "—",
                     (f"{e['worst_episode_label']}" if e else "—"),
                     (f"{f.get('count', 0):,} of {f.get('of', 0):,}" if f else "—")])
    hd.table(doc, ["Driver", "Method", "Mild", "Moderate", "Severe", "n / independent", "Worst episode", "At least moderate"], rows,
             widths=[4.2, 1.6, 1.4, 1.5, 1.4, 2.0, 2.6, 1.9], size=7.5)
    hd.figure(doc, chart_distributions(cal), width_cm=16, caption="Figure 1. Distributions of the one-year adverse move, with the three severities.")
    for k in ("brent", "gdp_nonoil", "saibor", "sector_cycle", "rating"):
        hd.para(doc, cal[k]["text"], size=9)

    # 4 ------------------------------------------------------------
    hd.heading(doc, "4. Percentile choices")
    _eq(doc, "Q(p) = x(⌊h⌋) + (h − ⌊h⌋)(x(⌊h⌋+1) − x(⌊h⌋)),  h = (n − 1)p   (empirical quantile, linear interpolation)")
    _eq(doc, "mild = Q(0.75);   moderate = Q(0.92) within [Q(0.90), Q(0.93)];   severe = max(Q(0.96), worst observed episode)")
    _eq(doc, "whole notches: severity = min{ n ≥ 1 : P(a ≥ n) ≤ 25% / 8% / 4% };  severe one notch beyond moderate when history holds it")
    hd.para(doc, f"A driver with fewer than {calibrate.MIN_OBS} independent one-year observations, a history with no adverse tail at "
                 "the moderate percentile, or a series that does not measure the shock (appraisal marks, unfinished workouts) keeps "
                 "a labelled expert value; the rejected estimate is shown beside it.")
    rows = []
    for k, r in cal.items():
        e = r["estimate"]
        if not e:
            continue
        band = e["moderate_band"]
        ratio = e.get("rule_ratio")
        lo, hi = calibrate.RULE_BAND
        rule = "—" if ratio is None else (f"{(ratio - 1) * 100:+.0f}%: " + ("within" if lo <= ratio <= hi else "outside"))
        rows.append([r["label"], f"{e['mean_adverse']:.3g}", f"{e['mild']:.3g}", f"{band[0]:.3g} – {band[1]:.3g}", rule,
                     "in force" if r["method"] == "empirical" else "fallback"])
    hd.table(doc, ["Driver", "Average adverse move", "P75", "P90–P93", "Mild vs average (rule +10% to +20%)", "Used"],
             rows, widths=[5.2, 2.2, 1.6, 2.6, 3.4, 1.6], size=7.5)
    hd.para(doc, "Where mild sits outside the rule of thumb the percentile rule is kept: the rule is a cross-check, and a "
                 "distribution with many small moves and a few large ones (oil, rates) puts P75 below the average adverse move.")
    fb = [r for k, r in cal.items() if r["method"] == "fallback" and k not in calibrate.SENSITIVITY_ONLY]
    hd.para(doc, "**Fallbacks (labelled in every output):**")
    hd.bullets(doc, [f"{r['label']}: {r['display']['mild']} / {r['display']['moderate']} / {r['display']['severe']}, "
                     f"{r['fallback_label']}; {r['fallback_reason']}." for r in fb])

    # 5 ------------------------------------------------------------
    hd.heading(doc, "5. Joint dependence")
    _eq(doc, "ρs(i, j) = Spearman rank correlation on the years both drivers are observed;   r(i, j) = 2 sin(π ρs / 6)")
    _eq(doc, f"z ~ N(0, R),  u = Φ(z),  a_j = F_j⁻¹(u_j);  N = {j['n_draws']:,} draws, seed {j['seed']};  composite c = w′z, w = first principal component of R (sum 1)")
    lab = [j["labels"][k] for k in j["keys"]]
    rows = []
    for i, k in enumerate(j["keys"]):
        rows.append([lab[i]] + [f"{j['spearman'][i][m]:+.2f} (n {j['n_pairs'][i][m]})" for m in range(len(j["keys"]))])
    hd.table(doc, ["Spearman ρ"] + [k for k in j["keys"]], rows, widths=[4.6, 2.8, 2.8, 2.8, 2.8], size=7.5)
    hd.note(doc, "Simulated draws reproduce the rank correlations: largest gap "
                 f"{np.abs(np.array(j['simulated_spearman']) - np.array(j['spearman'])).max():.3f}. "
                 f"Standard error of ρ on the Fisher-z scale 1/√(n − 3): {min(x for r in j['se_fisher_z'] for x in r if x > 0):.2f} to "
                 f"{max(x for r in j['se_fisher_z'] for x in r):.2f}." + (" The matrix was projected on the nearest positive semi-definite matrix." if j["psd_adjusted"] else ""))
    rows = []
    for s in SEVS:
        v = j["joint"][s]["values"]
        iv = j["independent_tails"][s]
        rows.append([s, f"{v['brent']:.1f}% ({iv['brent']:.1f}%)", f"{v['gdp_real']:.2f} ({iv['gdp_real']:.2f})",
                     f"{v['gdp_nonoil']:.2f} ({iv['gdp_nonoil']:.2f})", f"{v['saibor']:.0f} ({iv['saibor']:.0f})", j["joint"][s]["basis"]])
    for a in j["analogues"]:
        v = a["values"]
        rows.append([str(a["year"]), f"{v['brent']:.1f}%", f"{v['gdp_real']:.2f}", f"{(v['gdp_nonoil'] if v['gdp_nonoil'] is not None else 0):.2f}",
                     f"{v['saibor']:.0f}" if v["saibor"] is not None else "—", f"analogue, composite P{a['percentile'] * 100:.0f}"])
    hd.table(doc, ["Scenario", "Brent fall (independent)", "Real GDP slowdown pp", "Non-oil slowdown pp", "SAIBOR rise bps", "Basis"],
             rows, widths=[1.8, 2.8, 2.4, 2.4, 2.2, 5.0], size=7.5)
    hd.para(doc, joint.corr_text(j) + " The figures in brackets are each driver at its own severity: stacking them would describe a "
                 "year that never happened.")
    hd.figure(doc, chart_joint(j), width_cm=14, caption="Figure 2. Brent fall and real GDP slowdown: observed years, copula draws and the joint severities.")

    # 6 ------------------------------------------------------------
    hd.heading(doc, "6. Satellite models")
    _eq(doc, "PD model:          Φ⁻¹(PD_st) = α + a_s + Σk βk x_kt + e_st")
    _eq(doc, "Migration model:   logit(m_st) = α + a_s + Σk βk x_kt + e_st,   m_st = Stage 1 → 2 share in the quarter")
    _eq(doc, "b̂ = argmin ‖y − Xb‖² + λa Σ a_s² + λb Σ βk²;   V = A⁻¹ (Σt X_t′ e_t e_t′ X_t) A⁻¹ · G/(G − 1),  A = X′X + Λ")
    for m in ("pd", "migration"):
        f = sat[m]
        hd.heading(doc, f"6.{1 if m == 'pd' else 2} {f['label']}", level=2)
        hd.para(doc, f"n {f['n']} sector-quarters ({f['from']}–{f['to']}, {f['sectors']} sectors); R² {f['r2']:.3f}, within sector "
                     f"{f['r2_within']:.3f}; λb {f['lambda_b']:g} (leave-one-year-out), λa {f['lambda_sector']:g}; residual s.d. "
                     f"{f['resid_sd']:.4f}.")
        rows = [[c["label"], f"{c['beta']:+.5f}", f"{c['se']:.5f}", f"{c['t']:+.2f}" if c["t"] is not None else "—",
                 f"[{c['band90'][0]:+.5f}, {c['band90'][1]:+.5f}]", "yes" if c["identified"] else "no", c["why"]] for c in f["coef"].values()]
        hd.table(doc, ["Driver", "β (per unit)", "s.e.", "t", "90% band", "Used", "Why"], rows,
                 widths=[3.2, 1.8, 1.6, 1.1, 3.2, 1.0, 4.6], size=7.5)
        o = f["oos"]
        hd.para(doc, f"Out of sample: fitted on {o['train'][0]}–{o['train'][1]}, predicting {o['test'][0]}–{o['test'][1]}: RMSE "
                     f"{o['rmse']:.1f} {o['unit']} against {o['rmse_naive']:.1f} {o['unit']} for the last value held "
                     + ("(the model beats the naive forecast)." if o["beats_naive"] else
                        "(the model does not beat the naive forecast: its coefficients give direction and an order of size, not a forecast)."))
    bt = sat["backtest"]
    hd.heading(doc, "6.3 Back-test", level=2)
    hd.para(doc, f"Book level, each quarter: fitted PD averages {_p(bt['mean_fitted'])} against the reported {_p(bt['mean_reported'])}; "
                 f"the observed annualised default rate averages {_p(bt['mean_default_rate'])}; correlation of the fitted PD with the "
                 f"default rate {bt['corr_fit_dr']:+.2f}.")
    hd.figure(doc, chart_backtest(bt), width_cm=16, caption="Figure 3. Back-test: reported and fitted PD, and the observed default rate.")

    # 7 ------------------------------------------------------------
    hd.heading(doc, "7. Translation to PD, LGD, EAD, ECL, stage and capital")
    for e in ("Δx = (−Brent fall, −real GDP slowdown, −non-oil slowdown, +SAIBOR rise/100) against a flat base",
              "PD12′ = Φ(Φ⁻¹(PD12) + Σk βk Δxk)   (identified terms only)",
              "PDlt′ = 1 − (1 − PDlt)^(h′/h),  h = −ln(1 − PD12)",
              "extra Stage 2 share = [1 − (1 − m′)⁴] − [1 − (1 − m)⁴],  m′ = expit(logit(m) + Σk γk Δxk); highest stressed PD first",
              "LGD′ = min(LGD + add-on, 1);   EAD′ = min(max(limit, EAD), EAD + Δu × limit)",
              "ECL′ = ECL_reported + [f(PD′, LGD′, EAD′, stage′) − f(PD, LGD, EAD, stage)],  f = PD12·LGD·EAD (Stage 1), PDlt·LGD·EAD (Stage 2)",
              "K = LGD [Φ((Φ⁻¹(PD) + √R Φ⁻¹(0.999)) / √(1 − R)) − PD] · MA;  RWA = 12.5 K EAD;  capital = ΔECL + 15% ΔRWA"):
        _eq(doc, e)
    rows = [[s, f"{tr[s]['dy_pd']:+.4f}", f"{tr[s]['dy_migration']:+.3f}", f"{tr[s]['lgd_add_pp']:.0f} pp", f"{tr[s]['utilisation_pp']:.1f} pp",
             _p(tr[s]["pd_start"]), _p(tr[s]["pd_stressed"])] for s in SEVS]
    hd.table(doc, ["Severity", "Δ probit PD", "Δ logit migration", "LGD add-on (expert)", "Utilisation rise", "PD start", "PD stressed"], rows,
             widths=[2.0, 2.0, 2.4, 2.6, 2.2, 2.0, 2.0], size=7.5)
    hd.para(doc, "RAROC: the deal-level RAROC under the same severities is computed by the Deal Desk Stress Lab, which reprices PD, "
                 "capital, ECL and the margin ratchet for each deal (section 10).")

    # 8 ------------------------------------------------------------
    hd.heading(doc, "8. Results by severity")
    rows = [[s, tr[s]["ecl_start"], tr[s]["ecl_stressed"], tr[s]["ecl_change"], f"{tr[s]['ecl_band'][0]:,.0f} – {tr[s]['ecl_band'][1]:,.0f}",
             _p(tr[s]["stage2_share_start"], 1), _p(tr[s]["stage2_share_stressed"], 1), tr[s]["rwa_change"], tr[s]["capital_impact"]] for s in SEVS]
    hd.table(doc, ["Severity", "ECL start", "ECL stressed", "ECL change", "90% band", "Stage 2 start", "Stage 2 stressed", "RWA change", "Capital"],
             rows, kinds=["", "sar_mn", "sar_mn", "sar_mn", "", "", "", "sar_mn", "sar_mn"], size=7.5)
    hd.figure(doc, chart_results(tr), width_cm=12, caption="Figure 4. ECL change by severity, with the 90% band from the satellite coefficients.")
    rows = [[s["sector"], s["ead"], s["ecl_start"], s["ecl_change"], _p(s["pd_start"]), _p(s["pd_stressed"]),
             _p(s["stage2_share_start"], 1), _p(s["stage2_share_stressed"], 1)] for s in tr["severe"]["sectors"]]
    hd.table(doc, ["Sector (severe)", "EAD", "ECL start", "ECL change", "PD start", "PD stressed", "Stage 2 start", "Stage 2 stressed"], rows,
             kinds=["", "sar_mn", "sar_mn", "sar_mn", "", "", "", ""], size=7.5)

    # 9 ------------------------------------------------------------
    hd.heading(doc, "9. Sensitivity")
    rows = []
    for s in SEVS:
        ind = translate.run(j["independent_tails"][s], s)
        rows.append([s, f"{tr[s]['ecl_change']:,.0f}", f"{ind['ecl_change']:,.0f}", f"{tr[s]['ecl_band'][0]:,.0f} – {tr[s]['ecl_band'][1]:,.0f}"])
    hd.table(doc, ["Severity", "Joint (in force)", "Independent tails stacked", "Satellite 90% band"], rows, widths=[2.4, 3.2, 4.0, 4.0])
    noad = {s: translate.run(j["joint"][s]["values"], "none") for s in ("severe",)}
    hd.bullets(doc, [
        f"LGD overlay: without the expert add-on the severe ECL change is SAR {noad['severe']['ecl_change']:,.0f}m, against "
        f"SAR {tr['severe']['ecl_change']:,.0f}m with it: the overlay is {(1 - noad['severe']['ecl_change'] / tr['severe']['ecl_change']) * 100:.0f}% of the severe result.",
        f"Moderate percentile: Brent's moderate fall is {cal['brent']['estimate']['moderate_band'][0]:.0f}% at P90 and "
        f"{cal['brent']['estimate']['moderate_band'][1]:.0f}% at P93 (P92 in force: {cal['brent']['values']['moderate']:.0f}%).",
        "Bank-history drivers (sector index, PD multiplier, margin, rating, utilisation) come from one partial cycle: their severe values "
        "are lower bounds of what a full cycle would show.",
    ])

    # 10 -----------------------------------------------------------
    hd.heading(doc, "10. Deal Desk Stress Lab: the calibrated ladder and the tiers")
    from backend.scenarios import ladder, tiers
    from backend.dealdesk.stress2 import catalogue as cat
    seed = {r["scenario_id"]: r for r in cat.seed_ladder()}
    rows = []
    for r in ladder.calibrated_rows():
        old = seed.get(r["scenario_id"], {})
        rows.append([r["scenario_id"], r["severity"], old.get("label", "—"), r["label"], "data" if r["source"].startswith("calibrated") else "regime" if r["source"].startswith("regime") else "fallback"])
    hd.table(doc, ["Scenario", "Severity", "R12 ladder (hand-set)", "R13-S1 (calibrated)", "Basis"], rows, widths=[3.0, 1.8, 4.2, 5.4, 1.8], size=7.5)
    rep_t = tiers.load()
    if rep_t:
        b, a = rep_t["before"]["counts"], rep_t["after"]["counts"]
        order = ("High", "Medium", "Standard")
        hd.table(doc, ["Tier", "R12 ladder", "R13-S1"], [[t, b.get(t, 0), a.get(t, 0)] for t in order], kinds=["", "int", "int"], widths=[4, 3, 3])
        hd.para(doc, tier_explanation(rep_t))
    else:
        hd.para(doc, "The tier distribution is computed by python -m backend.scenarios.tiers.")

    # 11 -----------------------------------------------------------
    hd.heading(doc, "11. Limitations and expert overlays")
    hd.bullets(doc, [
        lim["cannot"],
        "The satellite coefficients rest on one partial cycle; oil is not identified in the bank's PD history (consistent with the R12 "
        "revenue calibration), so the oil channel reaches PD only through its co-movement with non-oil GDP in the joint scenario.",
        "Expert overlays in force: " + "; ".join(f"{r['label']} ({r['display']['mild']} / {r['display']['moderate']} / {r['display']['severe']})" for r in fb) + ".",
        "Risk Models can replace any fallback with the bank's ICAAP or the regulator's set through the Stress Lab editor (maker-checker); "
        "the calibration rows keep the estimate beside the value in force.",
        "The retail book (20 months) is not yet modelled by satellite; the macro severities apply to it, the translation does not.",
    ])

    # 12 -----------------------------------------------------------
    hd.heading(doc, "12. Reproducibility")
    hd.para(doc, f"Engine {rep['engine_version']}, commit {rep['commit'] or 'working tree'}, Python {rep['python']}, fingerprint "
                 f"{rep['fingerprint']} (hash of the input files and the code below). Command: {rep['command']}.")
    hd.table(doc, ["Package", "Version"], [[k, v] for k, v in rep["packages"].items()], widths=[5, 4])
    hd.table(doc, ["Code path", "SHA-256 (16)"], [[c["file"], c["sha256_16"]] for c in rep["code"]], widths=[9, 4])
    hd.para(doc, "Published relations (Data Domains, deal_desk): dd_scenario_calibration, dd_scenario_joint, dd_satellite_model, "
                 "dd_scenario_result, and dd_stress_scenario set R13-S1.")
    return hd.to_bytes(doc)


def tier_explanation(rep: dict[str, Any]) -> str:
    """Why the tiers are what they are (deterministic writer over tiers.json and the diagnosis)."""
    from backend.scenarios import tiers
    b, a = rep["before"], rep["after"]
    n = rep["n_deals"]
    dg = tiers.diagnose(rep)["after"]
    hb, ha = b["counts"].get("High", 0), a["counts"].get("High", 0)
    others = ", ".join(f"{a['counts'].get(t, 0)} {t}" for t in ("Medium", "Standard"))
    passing = n - dg["base_fail"]
    mild = dg["mild_data"] + dg["mild_expert"]
    top = sorted(dg["mild_by"].items(), key=lambda kv: -kv[1])[:5]
    rr = rep.get("revenue_relative", {}).get("counts", {}).get("High")
    one = (calibrate.calibrate_all()["rating"]["estimate"] or {}).get("discrete_share", {}).get(1, 0.0)
    txt = (f"Across the {n} deals in the Deal Desk register (dd_deal), tier High goes from {hb} under the R12 ladder to {ha} under "
           f"R13-S1 ({others}). High is not universal, and where it remains the data and the R12 rule put it there: "
           f"{dg['base_fail']} deals fail a test before any stress ({dg['base_fail_pricing']} price below the RAROC hurdle), and the "
           f"rule makes those High whatever the severities. Of the other {passing}, {mild} break at mild — {dg['mild_expert']} only on "
           f"shocks the bank data cannot size (labelled expert: project delay, customer loss, collateral, real estate, revenue, the "
           f"size of the own-sector downturn) and {dg['mild_data']} on calibrated shocks (a one-notch downgrade happened in {one * 100:.1f}% of "
           f"borrower-years, so it is a mild event) — and {dg['moderate']} break at moderate. Mildest breaking scenarios: "
           + ", ".join(f"{k} {v}" for k, v in top) + ".")
    if rr is not None:
        txt += (f" Sensitivity: with the revenue rows at the bank's own relative-shortfall percentiles instead of the expert "
                f"values, High would be {rr}: the revenue fallback is not what keeps the deals High.")
    return txt
