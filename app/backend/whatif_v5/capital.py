"""Capital impact: an IRB-like risk-weight formula and a stated CET1 ratio (new in v5).

5318 priced ECL only; the capital view is a v5 addition. Every number here is
an ILLUSTRATIVE assumption over the books -- not the bank's
capital, not a regulatory return.

Method
------
Risk-weighted assets per exposure, Basel IRB foundation-style (ASRF):

    K   = LGD x [ N( (G(PD) + sqrt(R) G(0.999)) / sqrt(1 - R) ) - PD ] x MA
    RWA = 12.5 x K x EAD

  * PD  = the 12-month PD (baseline or stressed), floored at 0.05%.
  * LGD = the book's IFRS 9 LGD (baseline or stressed), used as a downturn-LGD proxy.
  * Corporate: R = 0.12 w + 0.24 (1 - w), w = (1 - e^-50PD)/(1 - e^-50);
    maturity adjustment MA = (1 + (M - 2.5) b)/(1 - 1.5 b), b = (0.11852 - 0.05478 ln PD)^2, M = 2.5 years.
  * Retail: Mortgage R = 0.15; Credit Card (qualifying revolving) R = 0.04; other retail
    R = 0.03 w + 0.16 (1 - w), w = (1 - e^-35PD)/(1 - e^-35); no maturity adjustment.
  * Stage 3 (defaulted): RWA = 100% x max(EAD - ECL, 0) -- the standardised treatment of a
    defaulted exposure net of its specific provision.

CET1
----
  * CET1 capital held against the book is ASSUMED to be 15.0% of the whole book's
    baseline RWA at the period (one figure per book and period).
  * Scenario CET1 capital = that capital - the ECL increase (charged through P&L, pre-tax,
    no tax shield, no expected-loss shortfall adjustment).
  * Scenario RWA = whole-book baseline RWA + the RWA change in scope.
  * Capital impact = the ECL increase + 15.0% x the RWA increase: the CET1 needed to
    restore the 15.0% ratio.
"""
from __future__ import annotations

import functools
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

CET1_RATIO = 0.15
PD_FLOOR = 0.0005
MATURITY_YEARS = 2.5
CONFIDENCE = 0.999
DEFAULTED_RW = 1.0

_N = NormalDist()
_G999 = _N.inv_cdf(CONFIDENCE)
_inv = np.vectorize(_N.inv_cdf, otypes=[float])
_erf = np.vectorize(math.erf, otypes=[float])


def _cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + _erf(x / math.sqrt(2.0)))


def _correlation(domain: str, products: pd.Series, pd_: np.ndarray) -> np.ndarray:
    if domain == "corporate":
        w = (1 - np.exp(-50 * pd_)) / (1 - math.exp(-50))
        return 0.12 * w + 0.24 * (1 - w)
    w = (1 - np.exp(-35 * pd_)) / (1 - math.exp(-35))
    other = 0.03 * w + 0.16 * (1 - w)
    prod = products.astype(str).to_numpy()
    return np.where(prod == "Mortgage", 0.15, np.where(prod == "Credit Card", 0.04, other))


def rwa(domain: str, products: pd.Series, stage: np.ndarray, pd12: np.ndarray, lgd_pct: np.ndarray,
        ead: np.ndarray, ecl: np.ndarray) -> np.ndarray:
    """Risk-weighted assets per exposure, SAR million."""
    pd_ = np.clip(np.asarray(pd12, dtype=float), PD_FLOOR, 0.9999)
    lgd = np.clip(np.asarray(lgd_pct, dtype=float) / 100.0, 0.0, 1.0)
    ead = np.asarray(ead, dtype=float)
    r = _correlation(domain, products, pd_)
    k = lgd * (_cdf((_inv(pd_) + np.sqrt(r) * _G999) / np.sqrt(1 - r)) - pd_)
    if domain == "corporate":
        b = (0.11852 - 0.05478 * np.log(pd_)) ** 2
        k = k * (1 + (MATURITY_YEARS - 2.5) * b) / (1 - 1.5 * b)
    performing = 12.5 * np.clip(k, 0.0, None) * ead
    defaulted = DEFAULTED_RW * np.clip(ead - np.asarray(ecl, dtype=float), 0.0, None)
    return np.where(np.asarray(stage) >= 3, defaulted, performing)


def assumptions() -> list[str]:
    return [
        "Capital is illustrative: an IRB foundation-style (ASRF) risk weight over the book, "
        "not the bank's capital and not a regulatory return.",
        "RWA = 12.5 x K x EAD, K = LGD x [N((G(PD) + sqrt(R) G(0.999)) / sqrt(1-R)) - PD] x maturity adjustment.",
        f"PD = 12-month PD floored at {PD_FLOOR * 100:.2f}%; LGD = the book's IFRS 9 LGD as a downturn proxy.",
        "Corporate correlation 0.12-0.24 (Basel corporate), maturity 2.5 years. Retail: Mortgage R = 0.15, "
        "Credit Card R = 0.04 (qualifying revolving), other retail R = 0.03-0.16; no maturity adjustment.",
        "Stage 3: RWA = 100% x (EAD - ECL), the standardised treatment of a defaulted exposure net of provisions.",
        f"CET1 capital is assumed to be {CET1_RATIO * 100:.1f}% of the whole book's baseline RWA at the period.",
        "Scenario CET1 = that capital - the ECL increase (pre-tax, no tax shield); scenario RWA = whole-book RWA + "
        "the change in scope.",
        f"Capital impact = ECL increase + {CET1_RATIO * 100:.1f}% x RWA increase (the CET1 needed to restore the ratio).",
    ]


__all__ = ["CET1_RATIO", "assumptions", "rwa"]
