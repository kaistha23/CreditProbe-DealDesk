"""Joint scenarios: the macro drivers drawn together as they moved in history (PLAN_R13 §S.2).

Margins. Each driver's one-year adverse move a_j (Brent fall %, real GDP slowdown pp, non-oil GDP slowdown pp,
SAIBOR rise bps) has the empirical distribution F_j of `calibrate` (annual, since the series starts).

Dependence. Spearman's rank correlation rho_s is estimated pairwise on the years both drivers are observed, turned
into the Gaussian-copula correlation r = 2 sin(pi rho_s / 6) and, if needed, projected on the nearest positive
semi-definite matrix (eigenvalues clipped at 1e-6, unit diagonal restored). Standard error of each rho_s:
1/sqrt(n - 3) on the Fisher-z scale.

Draws. z ~ N(0, R) (N = 20,000, seed 13), u = Phi(z), a_j = F_j^-1(u_j) with linear interpolation between the
order statistics, held at the observed min and max (the copula never extrapolates beyond history).

Joint severity. The composite stress index is the first principal component of R applied to z (loadings scaled
to sum to one). The mild / moderate / severe joint scenario is the median of each driver over the draws whose
composite lies in the percentile band [0.73, 0.77], [0.90, 0.93] and [0.96, 0.98]; severe is replaced by the worst
historical analogue (2009, 2015, 2016, 2020) when that year's composite is harsher. Independent tails are never
combined: each joint scenario is one coherent year.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri
from scipy.stats import spearmanr

from backend.scenarios import calibrate, data

KEYS = ("brent", "gdp_real", "gdp_nonoil", "saibor")
N_DRAWS = 20_000
SEED = 13
BANDS = {"mild": (0.73, 0.77), "moderate": (0.90, 0.93), "severe": (0.96, 0.98)}
ANALOGUES = (2009, 2015, 2016, 2020)


@functools.lru_cache(maxsize=1)
def history() -> pd.DataFrame:
    """year x driver: the adverse one-year move of each macro driver (NaN before the series starts)."""
    cols = {}
    for k in KEYS:
        o = calibrate.drivers_by_key()[k].observe()
        cols[k] = pd.Series(o.values, index=[int(x) for x in o.labels])
    return pd.DataFrame(cols).sort_index()


def nearest_psd(r: np.ndarray) -> np.ndarray:
    w, v = np.linalg.eigh((r + r.T) / 2)
    w = np.clip(w, 1e-6, None)
    out = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(out))
    out = out / np.outer(d, d)
    np.fill_diagonal(out, 1.0)
    return out


def correlation(h: pd.DataFrame) -> dict[str, Any]:
    k = len(h.columns)
    rho = np.eye(k)
    n = np.zeros((k, k), dtype=int)
    for i in range(k):
        for j in range(k):
            ok = h.iloc[:, [i, j]].dropna()
            n[i, j] = len(ok)
            if i < j and len(ok) >= 4:
                rho[i, j] = rho[j, i] = float(spearmanr(ok.iloc[:, 0], ok.iloc[:, 1]).statistic)
    gauss = 2 * np.sin(np.pi * rho / 6)
    np.fill_diagonal(gauss, 1.0)
    psd = nearest_psd(gauss)
    se = np.where(n > 3, 1 / np.sqrt(np.clip(n - 3, 1, None)), np.nan)
    return {"spearman": rho, "gaussian": gauss, "copula": psd, "n": n, "se_fisher_z": se,
            "psd_adjusted": bool(np.abs(psd - gauss).max() > 1e-9)}


def margin_quantile(values: np.ndarray, u: np.ndarray) -> np.ndarray:
    v = np.sort(np.asarray(values, float))
    return np.quantile(v, np.clip(u, 0, 1))


def draws(corr: np.ndarray, margins: list[np.ndarray], n: int = N_DRAWS, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    z = rng.multivariate_normal(np.zeros(len(margins)), corr, size=n, method="cholesky")
    u = ndtr(z)
    x = np.column_stack([margin_quantile(m, u[:, j]) for j, m in enumerate(margins)])
    return z, x


def composite_weights(corr: np.ndarray) -> np.ndarray:
    w, v = np.linalg.eigh(corr)
    pc = v[:, int(np.argmax(w))]
    pc = pc if pc.sum() >= 0 else -pc
    pc = np.clip(pc, 0, None)
    return pc / pc.sum()


def _empirical_u(values: np.ndarray, x: float) -> float:
    v = np.sort(values)
    return float(np.clip((np.searchsorted(v, x, side="right") - 0.5) / len(v), 0.5 / len(v), 1 - 0.5 / len(v)))


@functools.lru_cache(maxsize=1)
def build() -> dict[str, Any]:
    h = history()
    margins = [h[k].dropna().to_numpy() for k in KEYS]
    c = correlation(h)
    z, x = draws(c["copula"], margins)
    w = composite_weights(c["copula"])
    comp = z @ w
    rank = comp.argsort().argsort() / (len(comp) - 1)
    joint: dict[str, dict[str, Any]] = {}
    for sev, (lo, hi) in BANDS.items():
        sel = (rank >= lo) & (rank <= hi)
        joint[sev] = {"values": {k: float(np.median(x[sel, j])) for j, k in enumerate(KEYS)}, "band": [lo, hi],
                      "draws": int(sel.sum()), "basis": f"Gaussian copula, composite P{int(lo * 100)}–P{int(hi * 100)}"}
    # historical analogues: their composite on the same scale (normal scores of the empirical margins)
    analog = []
    for y in ANALOGUES:
        if y not in h.index:
            continue
        row = h.loc[y]
        zs = np.array([ndtri(_empirical_u(margins[j], row[k])) if row[k] == row[k] else 0.0 for j, k in enumerate(KEYS)])
        score = float(zs @ w)
        pct = float((comp <= score).mean())
        analog.append({"year": int(y), "values": {k: (float(row[k]) if row[k] == row[k] else None) for k in KEYS},
                       "composite": score, "percentile": pct})
    worst = max(analog, key=lambda a: a["composite"]) if analog else None
    sev_score = float(np.quantile(comp, BANDS["severe"][0]))
    if worst and worst["composite"] > sev_score:
        joint["severe"] = {"values": {k: (v if v is not None else joint["severe"]["values"][k]) for k, v in worst["values"].items()},
                           "band": None, "draws": 0,
                           "basis": f"historical analogue {worst['year']} (composite P{worst['percentile'] * 100:.1f}, harsher than the copula's P96)"}
    sim_spear = np.array([[float(spearmanr(x[:, i], x[:, j]).statistic) if i != j else 1.0 for j in range(len(KEYS))]
                          for i in range(len(KEYS))])
    return {"keys": list(KEYS), "labels": {k: calibrate.drivers_by_key()[k].label for k in KEYS},
            "units": {k: calibrate.drivers_by_key()[k].unit for k in KEYS},
            "years": {k: [int(h[k].dropna().index.min()), int(h[k].dropna().index.max())] for k in KEYS},
            "spearman": c["spearman"].tolist(), "copula": c["copula"].tolist(), "gaussian": c["gaussian"].tolist(),
            "n_pairs": c["n"].tolist(), "se_fisher_z": np.nan_to_num(c["se_fisher_z"], nan=0.0).tolist(),
            "psd_adjusted": c["psd_adjusted"], "simulated_spearman": sim_spear.tolist(), "weights": w.tolist(),
            "n_draws": N_DRAWS, "seed": SEED, "joint": joint, "analogues": analog,
            "independent_tails": {s: {k: calibrate.calibrate_all()[k]["values"][s] for k in KEYS} for s in BANDS}}


def corr_text(j: dict[str, Any]) -> str:
    k = j["keys"]
    i, g = k.index("brent"), k.index("gdp_real")
    r = j["spearman"][i][g]
    n = j["n_pairs"][i][g]
    return (f"Oil falls and real GDP slowdowns moved together (Spearman {r:+.2f} over {n} years); the joint scenarios keep "
            f"that co-movement instead of stacking independent tails.")
