"""The credit-cycle model: how the MEVs move every PD in the What-If domain.

1. Implied cycle index. For every performing exposure the one-factor (Vasicek)
   model links its point-in-time PD to its through-the-cycle PD:
       PIT = Phi((Phi^-1(TTC) - sqrt(rho) * Z) / sqrt(1 - rho))
   so Z = (Phi^-1(TTC) - sqrt(1 - rho) * Phi^-1(PIT)) / sqrt(rho).
   Positive Z is a good year. Each segment's Z per period is the EAD-weighted
   mean over its performing exposures; the book's Z is the EAD-weighted mean
   over segments. TTC is the borrower's `pd_ttc_12m` (corporate) or the
   20-month average PD of its product and score band (retail).
2. MEV elasticities. Z(book, t) is regressed on the standardised,
   direction-adjusted MEV features at t (section `mev`), by ridge regression
   shrunk toward reference sensitivities and constrained to the expected sign
   (non-negative on direction-adjusted features). Fit, prior and posterior are
   on the model card.
3. Segment elasticities. Each segment's Z is regressed on the book's Z
   (slope shrunk toward 1 with equal weight, clipped to [0.3, 3]): a sector
   whose PDs swing more than the book has beta > 1.

rho is the Basel asset correlation (corporate: 0.12-0.24 by PD; retail
mortgage 0.15, revolving 0.04, other retail 0.03-0.16).
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.special import ndtr, ndtri

from backend.whatif_v5.domain import mev

PD_FLOOR = 1e-5
PD_CAP = 0.9999
PRIOR_WEIGHT = 1.0      # lambda as a multiple of the number of periods
BETA_RANGE = (0.3, 3.0)


def rho(domain: str, pd_ttc: np.ndarray, product: np.ndarray | None = None) -> np.ndarray:
    p = np.clip(np.asarray(pd_ttc, dtype=float), PD_FLOOR, 0.999)
    if domain == "corporate":
        w = (1 - np.exp(-50 * p)) / (1 - np.exp(-50))
        return 0.12 * w + 0.24 * (1 - w)
    w = (1 - np.exp(-35 * p)) / (1 - np.exp(-35))
    other = 0.03 * w + 0.16 * (1 - w)
    prod = np.asarray(product if product is not None else [""] * len(p)).astype(str)
    out = np.where(prod == "Mortgage", 0.15, np.where(prod == "Credit Card", 0.04, other))
    return out.astype(float)


def implied_z(pd_ttc: np.ndarray, pd_pit: np.ndarray, r: np.ndarray) -> np.ndarray:
    t = ndtri(np.clip(pd_ttc, PD_FLOOR, PD_CAP))
    p = ndtri(np.clip(pd_pit, PD_FLOOR, PD_CAP))
    return (t - np.sqrt(1 - r) * p) / np.sqrt(r)


def shift_pd(pd: np.ndarray, r: np.ndarray, dz: np.ndarray | float) -> np.ndarray:
    """Move PDs along the one-factor model by a change dz in the cycle index (dz < 0 is worse)."""
    p = np.clip(pd, PD_FLOOR, PD_CAP)
    return ndtr(ndtri(p) - np.sqrt(r / (1 - r)) * dz)


def fit(domain: str, history: pd.DataFrame) -> dict[str, Any]:
    """history: columns period, segment, z, ead (one row per segment and period)."""
    hist = history.copy()
    periods = sorted(hist["period"].unique())
    book = (hist.assign(zw=hist["z"] * hist["ead"]).groupby("period")
            .agg(zw=("zw", "sum"), ead=("ead", "sum")))
    book_z = (book["zw"] / book["ead"]).reindex(periods)
    x_raw = pd.DataFrame([mev.at_period(p) for p in periods], index=periods)
    x = mev.standardise(x_raw)
    keys = [s.key for s in mev.SERIES]
    xc = x[keys] - x[keys].mean()
    zc = book_z - book_z.mean()
    n = len(periods)
    lam = PRIOR_WEIGHT * n
    prior = np.array([mev.BY_KEY[k].prior_z_per_sd for k in keys])
    a = np.vstack([xc.to_numpy(), np.sqrt(lam) * np.eye(len(keys))])
    b = np.concatenate([zc.to_numpy(), np.sqrt(lam) * prior])
    gamma, _ = nnls(a, b)
    fitted = xc.to_numpy() @ gamma
    ss_res = float(((zc.to_numpy() - fitted) ** 2).sum())
    ss_tot = float((zc.to_numpy() ** 2).sum()) or 1.0
    # data-only (sign-constrained, no prior) for the card, to show what the history alone says
    g_data, _ = nnls(xc.to_numpy(), zc.to_numpy())
    betas: dict[str, dict[str, float]] = {}
    zb = zc.to_numpy()
    kappa = float((zb ** 2).sum()) or 1.0
    for seg, g in hist.groupby("segment"):
        zs = g.set_index("period")["z"].reindex(periods)
        ok = zs.notna().to_numpy()
        zs_c = (zs - zs[ok].mean()).to_numpy()
        slope_data = float((zs_c[ok] * zb[ok]).sum() / ((zb[ok] ** 2).sum() or 1.0))
        beta = float(np.clip(((zs_c[ok] * zb[ok]).sum() + kappa) / ((zb[ok] ** 2).sum() + kappa), *BETA_RANGE))
        betas[str(seg)] = {"beta": beta, "beta_data": slope_data, "periods": int(ok.sum())}
    return {
        "domain": domain, "periods": periods, "lambda": lam,
        "gamma": {k: float(v) for k, v in zip(keys, gamma)},
        "gamma_prior": {k: float(v) for k, v in zip(keys, prior)},
        "gamma_data_only": {k: float(v) for k, v in zip(keys, g_data)},
        "r2": 1.0 - ss_res / ss_tot,
        "book_z": {p: float(v) for p, v in book_z.items()},
        "fitted_z": {p: float(v + book_z.mean()) for p, v in zip(periods, fitted)},
        "features": {p: {k: float(x_raw.loc[p, k]) for k in keys} for p in periods},
        "betas": betas,
        "segment_z": {str(seg): {p: float(z) for p, z in g.set_index("period")["z"].items()}
                      for seg, g in hist.groupby("segment")},
    }


def z_path(model: dict[str, Any], segment: str, feats: pd.DataFrame) -> np.ndarray:
    """Cycle index over the path years for a segment (relative level; only differences matter)."""
    x = mev.standardise(feats)
    keys = [s.key for s in mev.SERIES]
    g = np.array([model["gamma"][k] for k in keys])
    beta = model["betas"].get(segment, {"beta": 1.0})["beta"]
    return beta * (x[keys].to_numpy() @ g)


def mev_dz(model: dict[str, Any], segment: str, base_feats: pd.DataFrame, shocked_feats: pd.DataFrame) -> np.ndarray:
    """The change in the cycle index, year by year, that an MEV shock causes for a segment."""
    return z_path(model, segment, shocked_feats) - z_path(model, segment, base_feats)


@functools.lru_cache(maxsize=4)
def load(domain: str) -> dict[str, Any]:
    import json

    from backend.whatif_v5.domain import store
    return json.loads((store.ROOT / domain / "cycle_model.json").read_text())
