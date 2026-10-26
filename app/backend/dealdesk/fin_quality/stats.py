"""Statistical screens of the financial-quality detector (PLAN_R13 §Q): Beneish M-score and the Benford first-digit test.

Both are screens, not proofs. Each returns its number, the threshold it is read against, the inputs it used and a
reliability note that the panel and the papers print next to the number.

    beneish(cur, prev)      8-variable M-score (Beneish 1999); None components name the missing inputs
    benford(values)         first-digit test: MAD (Nigrini 2012 bands), chi-square (8 df), n and the conformity band
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

#: Beneish (1999) 8-variable model; a score above -1.78 is the published cut-off for a likely manipulator.
M_COEF = {"const": -4.84, "DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892, "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327}
M_THRESHOLD = -1.78
M_NOTE = ("Beneish (1999) 8-variable model estimated on US listed manufacturers (1982-1992); PP&E is approximated as non-current assets "
          "less intangibles and non-core investments, SG&A as gross profit less operating profit, depreciation as EBITDA less operating "
          "profit. A screen for earnings manipulation, not evidence of it; read with the audit opinion.")

#: Benford first-digit expectations and Nigrini's (2012) MAD conformity bands for the first digit.
BENFORD = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
MAD_BANDS = ((0.006, "close conformity"), (0.012, "acceptable conformity"), (0.015, "marginally acceptable conformity"), (math.inf, "nonconformity"))
MAD_THRESHOLD = 0.015
CHI2_CRIT_8DF_5PCT = 15.507
BENFORD_MIN_N = 30
BENFORD_RELIABLE_N = 100


def _n(x: Any) -> float | None:
    try:
        if x is None or x == "" or isinstance(x, bool):
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _div(a: float | None, b: float | None) -> float | None:
    return None if a is None or b in (None, 0) else a / b


def _ppe(y: dict[str, Any]) -> float | None:
    ta, ca = _n(y.get("total_assets")), _n(y.get("current_assets"))
    if ta is None or ca is None:
        return None
    return max(ta - ca - (_n(y.get("intangibles")) or 0.0) - (_n(y.get("noncore_investments")) or 0.0), 0.0)


def beneish(cur: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
    """The M-score of `cur` against `prev` (two consecutive audited years, fields as in inputs.YEAR_FIELDS)."""
    def g(y: dict[str, Any], k: str) -> float | None:
        return _n(y.get(k))

    def gm(y: dict[str, Any]) -> float | None:
        return _div(g(y, "gross_profit"), g(y, "revenue"))

    def dep(y: dict[str, Any]) -> float | None:
        e, o = g(y, "ebitda"), g(y, "operating_profit")
        return None if e is None or o is None else max(e - o, 0.0)

    def sga(y: dict[str, Any]) -> float | None:
        a, o = g(y, "gross_profit"), g(y, "operating_profit")
        return None if a is None or o is None else a - o

    def aq(y: dict[str, Any]) -> float | None:
        ta, ca, ppe = g(y, "total_assets"), g(y, "current_assets"), _ppe(y)
        if ta in (None, 0) or ca is None or ppe is None:
            return None
        return 1 - (ca + ppe + (g(y, "noncore_investments") or 0.0)) / ta

    def lv(y: dict[str, Any]) -> float | None:
        ta, cl = g(y, "total_assets"), g(y, "current_liabilities")
        return None if ta in (None, 0) or cl is None else (cl + (g(y, "bank_debt_lt") or 0.0)) / ta

    def depr(y: dict[str, Any]) -> float | None:
        d, p = dep(y), _ppe(y)
        return None if d is None or p is None or (d + p) == 0 else d / (d + p)

    comp: dict[str, float | None] = {}
    comp["DSRI"] = _div(_div(g(cur, "receivables"), g(cur, "revenue")), _div(g(prev, "receivables"), g(prev, "revenue")))
    comp["GMI"] = _div(gm(prev), gm(cur))
    a1, a0 = aq(cur), aq(prev)
    comp["AQI"] = (a1 / a0) if a1 is not None and a0 not in (None, 0) else (1.0 if a1 is not None and a0 == 0 and a1 == 0 else None)
    comp["SGI"] = _div(g(cur, "revenue"), g(prev, "revenue"))
    comp["DEPI"] = _div(depr(prev), depr(cur))
    comp["SGAI"] = _div(_div(sga(cur), g(cur, "revenue")), _div(sga(prev), g(prev, "revenue")))
    comp["LVGI"] = _div(lv(cur), lv(prev))
    ni, ocf, ta = g(cur, "net_profit"), g(cur, "operating_cash_flow"), g(cur, "total_assets")
    comp["TATA"] = None if ni is None or ocf is None or not ta else (ni - ocf) / ta
    missing = [k for k, v in comp.items() if v is None]
    score = None
    if not missing:
        score = M_COEF["const"] + sum(M_COEF[k] * float(v) for k, v in comp.items())  # type: ignore[arg-type]
    return {"score": None if score is None else round(score, 3), "threshold": M_THRESHOLD,
            "components": {k: None if v is None else round(float(v), 4) for k, v in comp.items()},
            "missing": missing, "note": M_NOTE}


def first_digit(x: float) -> int | None:
    v = abs(float(x))
    if v == 0 or v != v or math.isinf(v):
        return None
    while v < 1:
        v *= 10
    while v >= 10:
        v /= 10
    return int(v)


BENFORD_MIN_LINES = 20


def benford(values: Iterable[Any], lines: int | None = None) -> dict[str, Any]:
    """First-digit test on reported amounts (zeros, blanks and amounts below 0.1m are left out). `lines` is the number of
    distinct line items behind the amounts: the same few lines repeated period after period are not independent draws,
    so the test counts as reliable only with 100+ amounts over 20+ line items."""
    digits = []
    for x in values:
        v = _n(x)
        if v is None or abs(v) < 0.1:
            continue
        d = first_digit(v)
        if d:
            digits.append(d)
    n = len(digits)
    obs = {d: digits.count(d) for d in range(1, 10)}
    out: dict[str, Any] = {"n": n, "observed": obs, "expected": {d: round(p, 4) for d, p in BENFORD.items()},
                           "mad": None, "chi2": None, "band": None, "threshold": MAD_THRESHOLD, "lines": lines,
                           "reliable": n >= BENFORD_RELIABLE_N and (lines is None or lines >= BENFORD_MIN_LINES)}
    if n < BENFORD_MIN_N:
        out["note"] = (f"{n} reported amounts: too few for a first-digit test (at least {BENFORD_MIN_N}, reliable from {BENFORD_RELIABLE_N}).")
        return out
    mad = sum(abs(obs[d] / n - BENFORD[d]) for d in range(1, 10)) / 9
    chi2 = sum((obs[d] - n * BENFORD[d]) ** 2 / (n * BENFORD[d]) for d in range(1, 10))
    out["mad"], out["chi2"] = round(mad, 4), round(chi2, 2)
    out["band"] = next(lbl for lim, lbl in MAD_BANDS if mad <= lim)
    out["note"] = (f"{n} reported amounts across the statements on file; financial-statement lines are partly sums of one another and "
                   f"cover a narrow range, so the test is indicative only" + ("" if n >= BENFORD_RELIABLE_N else
                                                                              f" and below the {BENFORD_RELIABLE_N} amounts a reliable test needs")
                   + ("" if lines is None or lines >= BENFORD_MIN_LINES else
                      f"; the amounts repeat {lines} line items period after period, fewer than the {BENFORD_MIN_LINES} independent lines a reliable test needs")
                   + f". MAD bands (Nigrini 2012): up to 0.006 close, 0.012 acceptable, 0.015 marginal, above 0.015 nonconformity; "
                     f"chi-square critical value {CHI2_CRIT_8DF_5PCT} at 5% (8 df).")
    return out
