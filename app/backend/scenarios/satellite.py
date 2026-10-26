"""Satellite models: sector PD and Stage 1 -> 2 migration on the macro drivers, on the bank's own history
(PLAN_R13 §S.3).

Panel: sector s (14) x quarter t, 2021Q3-2026Q2 (`data.sector_quarter`).

    PD model          y_st = Phi^-1(PD_st),           PD_st = EAD-weighted 12-month PIT PD of performing facilities
    migration model   y_st = logit(m_st),             m_st = share of last quarter's Stage 1 facilities now in Stage 2
                                                      (clipped to [0.25/n, 1 - 0.25/n])

    y_st = alpha + a_s + sum_k beta_k x_kt + e_st

x_kt: Brent's year-on-year change of the quarterly average (%), four-quarter-ending real GDP growth (%), non-oil
real GDP growth (%), 3-month SAIBOR (%), each standardised over the sample (mean 0, sd 1). a_s: sector effects,
sum-to-zero by construction of the penalty.

Estimator (regularised, pooled): ridge with separate penalties,

    min_b ||y - X b||^2 + lambda_a sum_s a_s^2 + lambda_b sum_k beta_k^2      (alpha unpenalised)

lambda_a = 1 (sector effects lightly shrunk to the common level); lambda_b chosen on a grid
{0, 0.5, 1, 2, 5, 10, 20, 50} by leave-one-year-out cross-validation (the four quarters of a year held out
together). Standard errors: cluster-robust by quarter, sandwich V = A^-1 (sum_t X_t' e_t e_t' X_t) A^-1 with
A = X'X + Lambda (small-sample factor G/(G-1)). Fit: R^2 overall and within sector. Out-of-sample: the model
refitted on the first 16 quarters predicts the last 4; RMSE (in PD basis points, or migration percentage points)
against a naive forecast (each sector's last in-sample value held flat).

Expected signs (a rise is good for credit): Brent +, real GDP +, non-oil GDP +, SAIBOR -. On y (higher = worse)
the expected coefficient sign is the opposite. A coefficient with the wrong sign, or whose 90% band includes
zero, is not identified: translation sets it to zero and says so.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import logit, ndtri

from backend.scenarios import data

X_KEYS = ("brent_yoy", "gdp_real", "gdp_nonoil", "saibor_3m")
X_LABEL = {"brent_yoy": "Brent, year-on-year %", "gdp_real": "Real GDP growth %", "gdp_nonoil": "Non-oil GDP growth %",
           "saibor_3m": "3-month SAIBOR %"}
#: expected sign of the coefficient on y (y higher = worse credit)
EXPECTED = {"brent_yoy": -1, "gdp_real": -1, "gdp_nonoil": -1, "saibor_3m": +1}
GRID = (0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0)
LAMBDA_SECTOR = 1.0
Z90 = 1.6449
HOLDOUT = 4
MODELS = {"pd": ("Sector 12-month PD", "probit of the EAD-weighted 12-month PD"),
          "migration": ("Stage 1 to 2 migration", "logit of the quarterly Stage 1 to 2 migration rate")}


@functools.lru_cache(maxsize=1)
def panel() -> pd.DataFrame:
    s = data.sector_quarter().copy()
    mac = pd.DataFrame({q: data.macro_at_quarter(q) for q in s["reporting_quarter"].unique()}).T
    s = s.join(mac, on="reporting_quarter")
    s["y_pd"] = ndtri(s["pd"].clip(1e-6, 1 - 1e-6))
    n = s["n_s1"].fillna(0).clip(lower=1)
    m = s["mig12"].clip(lower=0.25 / n, upper=1 - 0.25 / n)
    s["y_migration"] = np.where(s["mig12"].notna(), logit(m), np.nan)
    s["year"] = s["reporting_quarter"].str[:4].astype(int)
    return s


def _design(df: pd.DataFrame, sectors: list[str], mu: pd.Series, sd: pd.Series) -> tuple[np.ndarray, list[str]]:
    zs = ((df[list(X_KEYS)] - mu) / sd).to_numpy()
    d = np.column_stack([(df["sector"] == s).astype(float).to_numpy() for s in sectors])
    names = ["const"] + [f"sector:{s}" for s in sectors] + list(X_KEYS)
    return np.column_stack([np.ones(len(df)), d, zs]), names


def _penalty(k_sec: int, lam_b: float) -> np.ndarray:
    return np.diag([0.0] + [LAMBDA_SECTOR] * k_sec + [lam_b] * len(X_KEYS))


def _solve(x: np.ndarray, y: np.ndarray, pen: np.ndarray) -> np.ndarray:
    return np.linalg.solve(x.T @ x + pen, x.T @ y)


def fit_one(df: pd.DataFrame, ycol: str, lam_b: float | None = None) -> dict[str, Any]:
    df = df.dropna(subset=[ycol] + list(X_KEYS)).reset_index(drop=True)
    sectors = sorted(df["sector"].unique())
    mu, sd = df[list(X_KEYS)].mean(), df[list(X_KEYS)].std(ddof=0).replace(0, 1.0)
    x, names = _design(df, sectors, mu, sd)
    y = df[ycol].to_numpy()
    cv: dict[float, float] = {}
    if lam_b is None:
        for lam in GRID:
            err = []
            for yr in sorted(df["year"].unique()):
                tr, te = (df["year"] != yr).to_numpy(), (df["year"] == yr).to_numpy()
                if te.sum() == 0 or tr.sum() < x.shape[1]:
                    continue
                b = _solve(x[tr], y[tr], _penalty(len(sectors), lam))
                err.append(((y[te] - x[te] @ b) ** 2).mean())
            cv[lam] = float(np.mean(err))
        lam_b = min(cv, key=cv.get)
    pen = _penalty(len(sectors), lam_b)
    b = _solve(x, y, pen)
    e = y - x @ b
    a_inv = np.linalg.inv(x.T @ x + pen)
    meat = np.zeros((x.shape[1], x.shape[1]))
    groups = df["reporting_quarter"].to_numpy()
    g_ids = sorted(set(groups))
    for g in g_ids:
        sel = groups == g
        s = x[sel].T @ e[sel]
        meat += np.outer(s, s)
    g_n = len(g_ids)
    v = a_inv @ meat @ a_inv * (g_n / max(g_n - 1, 1))
    se = np.sqrt(np.clip(np.diag(v), 0, None))
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    within = y - df.groupby("sector")[ycol].transform("mean").to_numpy()
    fit_within = x @ b - pd.Series(x @ b).groupby(df["sector"]).transform("mean").to_numpy()
    r2w = 1 - float(((within - fit_within) ** 2).sum()) / (float((within ** 2).sum()) or 1.0)
    coef = {}
    for k in X_KEYS:
        i = names.index(k)
        beta_z = float(b[i])
        coef[k] = {"label": X_LABEL[k], "beta_per_sd": beta_z, "se_per_sd": float(se[i]), "sd": float(sd[k]), "mean": float(mu[k]),
                   "beta": beta_z / float(sd[k]), "se": float(se[i]) / float(sd[k]),
                   "t": beta_z / float(se[i]) if se[i] > 0 else None,
                   "band90": [(beta_z - Z90 * float(se[i])) / float(sd[k]), (beta_z + Z90 * float(se[i])) / float(sd[k])],
                   "expected_sign": EXPECTED[k]}
        c = coef[k]
        right = np.sign(c["beta"]) == EXPECTED[k] and abs(c["beta"]) > 0
        excl0 = c["band90"][0] > 0 or c["band90"][1] < 0
        c["identified"] = bool(right and excl0)
        c["why"] = ("identified: expected sign, 90% band excludes zero" if c["identified"]
                    else "wrong sign: set to zero in translation" if not right
                    else "90% band includes zero: set to zero in translation")
    sec_eff = {s: float(b[names.index(f"sector:{s}")]) for s in sectors}
    return {"lambda_b": lam_b, "lambda_sector": LAMBDA_SECTOR, "cv_mse": {str(k): v for k, v in cv.items()},
            "const": float(b[0]), "sector_effects": sec_eff, "coef": coef, "n": int(len(df)), "sectors": len(sectors),
            "quarters": int(df["reporting_quarter"].nunique()), "from": df["reporting_quarter"].min(),
            "to": df["reporting_quarter"].max(), "r2": 1 - float((e ** 2).sum()) / ss_tot, "r2_within": r2w,
            "resid_sd": float(e.std(ddof=x.shape[1] - len(sectors))) if len(e) > x.shape[1] else float(e.std()),
            "fitted": (x @ b).tolist(), "actual": y.tolist(), "rows": df[["sector", "reporting_quarter"]].to_dict("records"),
            "_mu": mu.to_dict(), "_sd": sd.to_dict(), "_b": b.tolist(), "_names": names}


def _to_level(model: str, y: np.ndarray) -> np.ndarray:
    from scipy.special import expit, ndtr
    return ndtr(y) if model == "pd" else expit(y)


def oos(df: pd.DataFrame, model: str) -> dict[str, Any]:
    ycol = f"y_{model}"
    d = df.dropna(subset=[ycol]).copy()
    qs = sorted(d["reporting_quarter"].unique(), key=data.quarter_index)
    test_q = qs[-HOLDOUT:]
    train = d[~d["reporting_quarter"].isin(test_q)]
    test = d[d["reporting_quarter"].isin(test_q)]
    f = fit_one(train, ycol)
    sectors = sorted(train["sector"].unique())
    x, _ = _design(test, sectors, pd.Series(f["_mu"]), pd.Series(f["_sd"]))
    pred = _to_level(model, x @ np.array(f["_b"]))
    act = _to_level(model, test[ycol].to_numpy())
    last = train.sort_values("t").groupby("sector")[ycol].last()
    naive = _to_level(model, test["sector"].map(last).to_numpy())
    scale = 10_000 if model == "pd" else 100
    unit = "bps" if model == "pd" else "pp"
    rmse = float(np.sqrt(((pred - act) ** 2).mean()) * scale)
    rn = float(np.sqrt(((naive - act) ** 2).mean()) * scale)
    by_q = (pd.DataFrame({"q": test["reporting_quarter"].to_numpy(), "pred": pred, "act": act, "naive": naive})
            .groupby("q").mean() * scale)
    return {"train": [qs[0], qs[-HOLDOUT - 1]], "test": [test_q[0], test_q[-1]], "rmse": rmse, "rmse_naive": rn, "unit": unit,
            "beats_naive": rmse < rn, "by_quarter": {q: {k: float(v) for k, v in r.items()} for q, r in by_q.iterrows()}}


@functools.lru_cache(maxsize=1)
def fit_all() -> dict[str, Any]:
    p = panel()
    out = {}
    for m, (label, ydesc) in MODELS.items():
        f = fit_one(p, f"y_{m}")
        f["oos"] = oos(p, m)
        f["label"], f["y"] = label, ydesc
        out[m] = f
    out["backtest"] = backtest(p, out["pd"])
    return out


def backtest(p: pd.DataFrame, f: dict[str, Any]) -> dict[str, Any]:
    """Book level, each quarter: the PD model's fitted PD (EAD-weighted over sectors) against the reported PD and
    the observed quarterly default rate annualised (1 - (1 - dr)^4)."""
    d = p.dropna(subset=["y_pd"]).reset_index(drop=True)
    fitted = _to_level("pd", np.array(f["fitted"]))
    d = d.assign(fit=fitted)
    w = d["w"]
    g = d.assign(fw=d["fit"] * w, aw=d["pd"] * w, nd=d["n_nd"].fillna(0), de=d["new_def"].fillna(0)).groupby("reporting_quarter")
    out = pd.DataFrame({"fitted_pd": g["fw"].sum() / g["w"].sum(), "reported_pd": g["aw"].sum() / g["w"].sum(),
                        "default_rate": 1 - (1 - g["de"].sum() / g["nd"].sum().replace(0, np.nan)) ** 4})
    out = out.loc[sorted(out.index, key=data.quarter_index)]
    rows = [{"quarter": q, **{k: (float(v) if v == v else None) for k, v in r.items()}} for q, r in out.iterrows()]
    ok = out.dropna()
    return {"rows": rows, "mean_fitted": float(ok["fitted_pd"].mean()), "mean_reported": float(ok["reported_pd"].mean()),
            "mean_default_rate": float(ok["default_rate"].mean()),
            "corr_fit_dr": float(np.corrcoef(ok["fitted_pd"], ok["default_rate"])[0, 1]) if len(ok) > 2 else None}


def delta_y(model: dict[str, Any], dx: dict[str, float], sector: str | None = None, *, band: str = "mid",
            identified_only: bool = True) -> float:
    """The change in y for a change dx in the raw drivers (units of X_KEYS). band: mid | low | high (90%)."""
    tot = 0.0
    for k, c in model["coef"].items():
        if identified_only and not c["identified"]:
            continue
        b = c["beta"] if band == "mid" else (c["band90"][0] if band == "low" else c["band90"][1])
        tot += b * float(dx.get(k, 0.0))
    return tot


def dx_for(values: dict[str, float]) -> dict[str, float]:
    """Joint-scenario adverse moves (brent fall %, GDP slowdowns pp, SAIBOR rise bps) -> changes in the regressors
    against a flat base: Brent's year-on-year change -F, growth down by the slowdown, SAIBOR up by the rise."""
    return {"brent_yoy": -float(values.get("brent", 0.0)), "gdp_real": -float(values.get("gdp_real", 0.0)),
            "gdp_nonoil": -float(values.get("gdp_nonoil", 0.0)), "saibor_3m": float(values.get("saibor", 0.0)) / 100.0}
