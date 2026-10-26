"""Sector revenue sensitivities to oil (Brent) and real non-oil GDP, estimated from the bank's borrower history.

Data (PLAN_R12 §0: read through Data Domains; only public macro series already in the repo):
  * the bank's borrower financials history: `corp_borrower_quarter` (Data Domains, domain "cockpit"), revenue by
    borrower and quarter, 2021Q3-2026Q2 (20 quarters), with the borrower's sector;
  * Brent: U.S. EIA Europe Brent spot, monthly averages (`data/whatif_v5/mev/brent_monthly_eia.csv`, public);
  * real non-oil GDP growth: IMF via FRED SAUNGDPXORPCHPT, annual (`data/whatif_v5/mev/mev_annual.csv`, public).

Method (the model card, docs/v5/R12_STRESS_CALIBRATION.md, says the same in words):
  * for each sector, a balanced panel: borrowers with revenue in both quarter t and t-4; the sector's
    year-on-year revenue growth g_t = 100 * ln(sum revenue_t / sum revenue_t-4)  (16 quarters, 2022Q3-2026Q2);
  * drivers on the same four-quarter window: oil_t = 100 * ln(Brent_t / Brent_t-4) (quarterly average of the
    monthly series); gdp_t = the four-quarter-ending real non-oil GDP growth (the annual rates weighted by the
    quarters of each calendar year in the window);
  * OLS g_t = a + b_oil * oil_t + b_gdp * gdp_t; Newey-West (HAC, 4 lags: the year-on-year windows overlap)
    standard errors; 90% bands with Student t (n - 3 degrees of freedom); R²; n quarters and n borrowers;
  * robustness: the same regression on borrower-level growth (pooled within the sector), standard errors
    clustered by quarter;
  * the stress value of a sensitivity is the revenue change at the scenario's shock: oil_30 (Brent -30%:
    ln 0.7) and gdp_3 (non-oil GDP 3 points below plan).

Thin data -> the expert value stays (flagged): a calibrated value replaces the expert one only when
  n >= MIN_N quarters, the 90% band excludes zero, the sign is the adverse one (revenue falls with the driver)
  and R² >= MIN_R2, the driver's own partial R² >= MIN_PARTIAL_R2 and the scenario shock is at most MAX_REACH times
  the largest adverse move of the driver in the sample. Otherwise the row keeps the expert value from stress_scenarios.json with `fallback: true`
  and the reason. Every row carries both values, so the expert override (maker-checker) stays possible.

Deterministic: the same files give the same numbers; no model, no network, numpy only (N3).
"""
from __future__ import annotations

import csv
import functools
import json
import math
import pathlib
from datetime import date
from typing import Any

import numpy as np

from backend.dealdesk import paths

V5 = paths.V5
VERSION = "calibrated-v1"
SOURCE = "calibrated v1"
METHOD = "OLS of sector YoY revenue growth on Brent YoY and non-oil GDP growth; Newey-West (4 lags) 90% bands"
MIN_N = 12
MIN_R2 = 0.30
#: a calibrated value is used up to this multiple of the largest adverse driver move seen in the sample
MAX_REACH = 1.5
#: and only when the driver itself explains part of the variation (partial R²)
MIN_PARTIAL_R2 = 0.05
HAC_LAGS = 4
LEVEL = 0.90
DRIVERS = {
    "oil": {"label": "Oil (Brent)", "scenario": "oil_30", "shock": 100 * math.log(0.70), "shock_label": "Brent -30%",
            "unit": "% revenue per 1% Brent (log-log elasticity)"},
    "gdp_nonoil": {"label": "Real non-oil GDP", "scenario": "gdp_3", "shock": -3.0, "shock_label": "non-oil GDP 3 pts below plan",
                   "unit": "% revenue per 1 pt non-oil GDP growth (beta)"},
}
BOOK_RELATION = ("cockpit", "corp_borrower_quarter")
MEV_DIR = V5 / "data" / "whatif_v5" / "mev"
BRENT_FILE = MEV_DIR / "brent_monthly_eia.csv"
MEV_FILE = MEV_DIR / "mev_annual.csv"
OUT = pathlib.Path(__file__).resolve().parent / "calibrated_v1.json"

#: Student t 95th percentile (two-sided 90%) by degrees of freedom; above 30 the normal value.
_T95 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796,
        12: 1.782, 13: 1.771, 14: 1.761, 15: 1.753, 16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729, 20: 1.725, 21: 1.721,
        22: 1.717, 23: 1.714, 24: 1.711, 25: 1.708, 26: 1.706, 27: 1.703, 28: 1.701, 29: 1.699, 30: 1.697}


def t95(df: int) -> float:
    return _T95.get(max(1, df), 1.645) if df <= 30 else 1.645


# ------------------------------------------------------------------ data (Data Domains + public macro)

def book_path() -> pathlib.Path:
    """The registered file of corp_borrower_quarter (Data Domains registry: the relation, never a side door)."""
    from backend.data_builder import registry
    rel = registry.DOMAINS[BOOK_RELATION[0]]["relations"][BOOK_RELATION[1]]
    return V5 / rel["path"]


@functools.lru_cache(maxsize=1)
def book_history() -> Any:
    import pandas as pd
    df = pd.read_parquet(book_path(), columns=["borrower_id", "reporting_quarter", "sector", "revenue_sar_mn"])
    return df


def _q_of(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


@functools.lru_cache(maxsize=1)
def macro() -> dict[str, Any]:
    """Brent by quarter (average of the monthly averages) and non-oil real GDP growth by year (history only)."""
    months: dict[str, list[float]] = {}
    with open(BRENT_FILE) as f:
        for r in csv.DictReader(f):
            months.setdefault(_q_of(r["Date"]), []).append(float(r["Price"]))
    brent_q = {q: sum(v) / len(v) for q, v in months.items() if len(v) == 3}
    gdp: dict[int, float] = {}
    kinds: dict[int, str] = {}
    with open(MEV_FILE) as f:
        for r in csv.DictReader(f):
            if r["series"] == "gdp_nonoil":
                gdp[int(r["year"])] = float(r["value"])
                kinds[int(r["year"])] = r["kind"]
    return {"brent_q": brent_q, "gdp_nonoil": gdp, "gdp_kind": kinds,
            "sources": {"brent": "U.S. EIA Europe Brent spot (RBRTE), monthly averages; data/whatif_v5/mev/brent_monthly_eia.csv",
                        "gdp_nonoil": "IMF real non-oil GDP growth via FRED SAUNGDPXORPCHPT, annual; data/whatif_v5/mev/mev_annual.csv"}}


def _prev4(q: str) -> str:
    return f"{int(q[:4]) - 1}Q{q[-1]}"


def drivers_for(quarters: list[str]) -> dict[str, dict[str, float]]:
    """oil_t = 100 ln(Brent_t / Brent_t-4); gdp_t = the four-quarter-ending non-oil growth (annual rates by quarter weight)."""
    m = macro()
    out: dict[str, dict[str, float]] = {}
    for q in quarters:
        y, k = int(q[:4]), int(q[-1])
        b0, b1 = m["brent_q"].get(_prev4(q)), m["brent_q"].get(q)
        g0, g1 = m["gdp_nonoil"].get(y - 1), m["gdp_nonoil"].get(y)
        if None in (b0, b1, g0, g1) or m["gdp_kind"].get(y) != "history" or m["gdp_kind"].get(y - 1) != "history":
            continue  # history only: a window that needs a projected GDP year is left out
        out[q] = {"oil": 100 * math.log(b1 / b0), "gdp_nonoil": (g1 * k + g0 * (4 - k)) / 4}
    return out


def sector_growth() -> dict[str, Any]:
    """Sector YoY revenue growth on a balanced panel, and the borrower-level growth for the robustness check."""
    df = book_history()
    w = df.pivot_table(index="borrower_id", columns="reporting_quarter", values="revenue_sar_mn", aggfunc="sum")
    sec = df.drop_duplicates("borrower_id").set_index("borrower_id")["sector"]
    qs = sorted(w.columns)
    pairs = [(q, _prev4(q)) for q in qs if _prev4(q) in w.columns]
    out: dict[str, Any] = {"quarters": [q for q, _ in pairs], "sectors": {}}
    for s in sorted(sec.dropna().unique()):
        ids = sec[sec == s].index
        sub = w.loc[w.index.isin(ids)]
        g, n_bor, bor = [], [], []
        for q, p in pairs:
            ok = (sub[q] > 0) & (sub[p] > 0)
            g.append(100 * math.log(float(sub.loc[ok, q].sum()) / float(sub.loc[ok, p].sum())))
            n_bor.append(int(ok.sum()))
            bor.append(100 * np.log(sub.loc[ok, q].to_numpy() / sub.loc[ok, p].to_numpy()))
        out["sectors"][s] = {"growth": g, "borrowers": n_bor, "borrower_growth": bor}
    return out


# ------------------------------------------------------------------ statistics

def ols_hac(y: np.ndarray, X: np.ndarray, lags: int = HAC_LAGS) -> dict[str, Any]:
    """OLS with Newey-West (Bartlett) standard errors."""
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    b = xtx_inv @ X.T @ y
    e = y - X @ b
    u = X * e[:, None]
    S = u.T @ u
    for L in range(1, min(lags, n - 1) + 1):
        w = 1 - L / (lags + 1)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    V = xtx_inv @ S @ xtx_inv * (n / max(n - k, 1))
    se = np.sqrt(np.maximum(np.diag(V), 0))
    tss = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float((e ** 2).sum()) / tss if tss > 0 else 0.0
    return {"b": b, "se": se, "r2": r2, "n": n, "df": n - k, "resid_sd": float(np.sqrt((e ** 2).sum() / max(n - k, 1)))}


def ols_cluster(y: np.ndarray, X: np.ndarray, groups: np.ndarray) -> dict[str, Any]:
    """Pooled OLS with standard errors clustered by group (the quarter)."""
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    b = xtx_inv @ X.T @ y
    e = y - X @ b
    S = np.zeros((k, k))
    G = np.unique(groups)
    for g in G:
        m = groups == g
        s = X[m].T @ e[m]
        S += np.outer(s, s)
    c = len(G) / max(len(G) - 1, 1) * (n - 1) / max(n - k, 1)
    V = c * xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(V), 0))
    tss = float(((y - y.mean()) ** 2).sum())
    return {"b": b, "se": se, "r2": 1 - float((e ** 2).sum()) / tss if tss > 0 else 0.0, "n": n, "clusters": len(G)}


# ------------------------------------------------------------------ expert values

def _stress_table() -> dict[str, Any]:
    return json.loads((paths.params_dir() / "v1" / "stress_scenarios.json").read_text())


def expert_value(sector: str, driver: str) -> dict[str, Any]:
    """The Risk Models assumption in stress_scenarios.json, as a revenue change at the scenario shock and as a sensitivity."""
    t = _stress_table()
    sid = DRIVERS[driver]["scenario"]
    sc = next(s for s in t["scenarios"] if s["id"] == sid)
    rp = sc["shocks"]["revenue_pct"]
    v = rp.get("by_sector", {}).get(sector, rp.get("default"))
    in_table = sector in rp.get("by_sector", {})
    shock = -30.0 if driver == "oil" else DRIVERS[driver]["shock"]  # the expert table is quoted per 30% oil fall
    return {"stress_revenue_pct": float(v), "sensitivity": round(100 * float(v) / shock, 4), "in_table": in_table,
            "version": f"stress_scenarios.json {t['version']} ({t['owner']}, effective {t['effective_from']})",
            "scenario": sid, "basis": sc.get("basis", "")}


# ------------------------------------------------------------------ estimation

def _verdict(n: int, b: float, lo: float, hi: float, r2: float, reach: float, partial: float = 1.0) -> tuple[bool, str]:
    if n < MIN_N:
        return False, f"only {n} quarters (fewer than {MIN_N})"
    if b <= 0:
        return False, "the estimate has the wrong sign (revenue does not fall with the driver in this history)"
    if lo <= 0 <= hi:
        return False, f"the 90% band ({lo:.3f} to {hi:.3f}) includes zero: the effect is not identified"
    if r2 < MIN_R2:
        return False, f"R² {r2:.2f} is below {MIN_R2:.2f}"
    if partial < MIN_PARTIAL_R2:
        return False, f"the driver adds only {partial:.3f} to R² (below {MIN_PARTIAL_R2:.2f}): the fit comes from the other driver"
    if reach > MAX_REACH:
        return False, f"the scenario shock is {reach:.1f}x the largest move in the sample (above {MAX_REACH:.1f}x)"
    return True, "estimated: band excludes zero, adverse sign, R² and n sufficient"


def _pct(log_change: float) -> float:
    return math.exp(log_change / 100) - 1


def estimate() -> dict[str, Any]:
    sg = sector_growth()
    quarters = sg["quarters"]
    drv = drivers_for(quarters)
    qs = [q for q in quarters if q in drv]
    idx = [quarters.index(q) for q in qs]
    oil = np.array([drv[q]["oil"] for q in qs])
    gdp = np.array([drv[q]["gdp_nonoil"] for q in qs])
    X = np.c_[np.ones(len(qs)), oil, gdp]
    obs = {"oil": {"min": round(float(oil.min()), 2), "max": round(float(oil.max()), 2), "mean": round(float(oil.mean()), 2)},
           "gdp_nonoil": {"min": round(float(gdp.min()), 2), "max": round(float(gdp.max()), 2), "mean": round(float(gdp.mean()), 2)}}
    years = sorted({int(q[:4]) for q in qs} | {int(q[:4]) - 1 for q in qs})
    rows: list[dict[str, Any]] = []
    fits: dict[str, Any] = {}
    sectors = dict(sg["sectors"])
    # the book-wide row (sectors without their own expert value use the default)
    allg = []
    for j in idx:
        tot_q = sum(sectors[s]["growth"][j] * sectors[s]["borrowers"][j] for s in sectors)
        allg.append(tot_q / max(sum(sectors[s]["borrowers"][j] for s in sectors), 1))
    for s, d in list(sectors.items()) + [("default", {"growth": allg, "borrowers": [sum(sectors[x]["borrowers"][j] for x in sectors) for j in range(len(quarters))],
                                                       "borrower_growth": None})]:
        y = np.array([d["growth"][j] for j in idx])
        f = ols_hac(y, X)
        tc = t95(f["df"])
        # partial R²: what each driver adds over the other one alone
        part = {key: max(0.0, f["r2"] - ols_hac(y, np.delete(X, i, axis=1))["r2"]) for i, key in ((1, "oil"), (2, "gdp_nonoil"))}
        rob = None
        if d.get("borrower_growth") is not None:
            ys, xs, gs = [], [], []
            for k, j in enumerate(idx):
                bg = d["borrower_growth"][j]
                ys.append(bg)
                xs.append(np.repeat(X[k:k + 1], len(bg), axis=0))
                gs.append(np.full(len(bg), k))
            rob = ols_cluster(np.concatenate(ys), np.vstack(xs), np.concatenate(gs))
        fits[s] = {"r2": round(f["r2"], 4), "n": f["n"], "intercept": round(float(f["b"][0]), 4), "resid_sd": round(f["resid_sd"], 4),
                   "borrowers_min": int(min(d["borrowers"][j] for j in idx)), "borrowers_max": int(max(d["borrowers"][j] for j in idx)),
                   "growth": [round(float(v), 4) for v in y]}
        for i, key in ((1, "oil"), (2, "gdp_nonoil")):
            b, se = float(f["b"][i]), float(f["se"][i])
            lo, hi = b - tc * se, b + tc * se
            shock = DRIVERS[key]["shock"]
            move = abs(obs[key]["min"] - obs[key]["mean"])  # the largest adverse move from the sample mean
            reach = abs(shock) / move if move else float("inf")
            ok, why = _verdict(f["n"], b, lo, hi, f["r2"], reach, part[key])
            ex = expert_value(s if s != "default" else "__default__", key)
            cal_stress = _pct(b * shock)
            band_stress = sorted([_pct(lo * shock), _pct(hi * shock)])
            # the shock is a move from plan: extrapolated when it is larger than the largest adverse move observed
            extrap = reach > 1.0
            row = {
                "version": VERSION, "source": SOURCE if ok else "expert (fallback)", "sector": s, "driver": key,
                "driver_label": DRIVERS[key]["label"], "unit": DRIVERS[key]["unit"], "scenario_id": DRIVERS[key]["scenario"],
                "shock": round(shock, 4), "shock_label": DRIVERS[key]["shock_label"],
                "sensitivity": round(b, 5) if ok else ex["sensitivity"],
                "stress_revenue_pct": round(cal_stress, 5) if ok else ex["stress_revenue_pct"],
                "estimate": round(b, 5), "std_error": round(se, 5), "ci_level": LEVEL, "ci_low": round(lo, 5), "ci_high": round(hi, 5),
                "stress_revenue_pct_estimate": round(cal_stress, 5),
                "stress_revenue_pct_ci_low": round(band_stress[0], 5), "stress_revenue_pct_ci_high": round(band_stress[1], 5),
                "r2": round(f["r2"], 4), "partial_r2": round(part[key], 4), "n": f["n"], "n_borrowers": fits[s]["borrowers_max"],
                "panel_estimate": round(float(rob["b"][i]), 5) if rob else None,
                "panel_std_error": round(float(rob["se"][i]), 5) if rob else None,
                "panel_n": rob["n"] if rob else None,
                "expert_sensitivity": ex["sensitivity"], "expert_stress_revenue_pct": ex["stress_revenue_pct"],
                "expert_in_table": ex["in_table"], "expert_version": ex["version"],
                "fallback": not ok, "flag": "" if ok else f"Expert value kept: {why}.", "reason": why,
                "extrapolated": bool(extrap), "shock_reach": round(reach, 3),
                "observed_min": obs[key]["min"], "observed_max": obs[key]["max"],
                "sample_from": qs[0], "sample_to": qs[-1], "method": METHOD,
                "data_relation": "cockpit.corp_borrower_quarter (revenue_sar_mn, sector)",
                "macro_source": macro()["sources"]["brent" if key == "oil" else "gdp_nonoil"],
            }
            rows.append(row)
    n_cal = sum(1 for r in rows if not r["fallback"])
    return {"version": VERSION, "source": SOURCE, "method": METHOD, "estimated_on": date.today().isoformat(),
            "sample": {"quarters": qs, "from": qs[0], "to": qs[-1], "n": len(qs), "macro_years": years,
                       "left_out": [q for q in quarters if q not in drv],
                       "drivers": {q: {"oil": round(drv[q]["oil"], 3), "gdp_nonoil": round(drv[q]["gdp_nonoil"], 3)} for q in qs},
                       "observed": obs},
            "rules": {"min_n": MIN_N, "min_r2": MIN_R2, "ci_level": LEVEL, "hac_lags": HAC_LAGS, "max_reach": MAX_REACH, "min_partial_r2": MIN_PARTIAL_R2},
            "fits": fits, "rows": rows,
            "summary": {"rows": len(rows), "calibrated": n_cal, "fallback": len(rows) - n_cal,
                        "calibrated_by_driver": {k: sum(1 for r in rows if r["driver"] == k and not r["fallback"]) for k in DRIVERS}},
            "sources": macro()["sources"] | {"book": "Data Domains cockpit.corp_borrower_quarter (" + str(book_path().relative_to(V5)) + ")"}}


def write(est: dict[str, Any] | None = None) -> pathlib.Path:
    """The coefficients as JSON (N3: models exported as coefficients), committed beside this module."""
    est = est or estimate()
    OUT.write_text(json.dumps({k: v for k, v in est.items() if k != "estimated_on"}, indent=1, ensure_ascii=False) + "\n")
    return OUT


def load() -> dict[str, Any]:
    return json.loads(OUT.read_text()) if OUT.exists() else estimate()


# ------------------------------------------------------------------ publishing (Session E's publisher)

RELATION = "dd_stress_sensitivity"


def relation_rows(est: dict[str, Any]) -> list[dict[str, Any]]:
    """The rows for dd_stress_sensitivity: one per sector and driver (the plan's columns; see publish_version)."""
    return [dict(r) for r in est["rows"]]


def publish_version(est: dict[str, Any] | None = None, by: str = "Session T (calibration)") -> dict[str, Any]:
    """Publish the estimate as a new dd_stress_sensitivity version through Session E's publisher.

    Until E's publisher lands (SCHEMA READY), the rows are written to var/dealdesk/calibration and the result says so.
    """
    from backend.dealdesk.calibration import publish as P
    est = est or load()
    return P.publish_sensitivity(relation_rows(est), version=est["version"], source=est["source"], by=by)
