"""Saudi macroeconomic variables (MEVs): the history and the 5-year scenario paths.

The store is `data/whatif_v5/mev/`:
  mev_annual.csv            series,year,value,unit,kind,source,source_url,vintage,note
                            (real published figures; kind = history | projection)
  brent_monthly_eia.csv     EIA Europe Brent spot, monthly average (datasets/oil-prices mirror)
  manifest.json             every series with its source, vintage and retrieval date

Each series has a *feature* the credit-cycle model reads (a growth rate, a
level, or the % deviation of a price from its 2010-2025 average level), and a
direction: +1 when a rise in the feature is good for credit, -1 when it is bad.

Scenario paths (annual, 5 years from the as-of year):
  base      the realised values where the year has happened, else the IMF
            projection, else the last observed value held flat (said per series)
  upturn    base + 1.0 historical standard deviation of the feature in the good
            direction in year 1, fading 1.0, 0.75, 0.5, 0.25, 0
  downturn  base - 1.5 historical standard deviations in year 1, profile
            1.0, 1.0, 0.6, 0.3, 0.1 (shaped on 2015-16 and 2020)
For price series (Brent, real-estate prices) the shock is applied to the
level, so the feature (deviation from the 2010-2025 average) moves with it.
"""
from __future__ import annotations

import csv
import functools
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5 import paths

MEV_DIR = paths.V5 / "data" / "whatif_v5" / "mev"
HORIZON = 5
SCENARIOS = ("base", "upturn", "downturn")
WEIGHTS = {"base": 0.50, "upturn": 0.20, "downturn": 0.30}
UP_PROFILE = (1.0, 1.0, 0.75, 0.5, 0.25)
DOWN_PROFILE = (1.0, 1.0, 0.6, 0.3, 0.1)
UP_SD = 1.0
DOWN_SD = 1.5
HISTORY_FROM = 1990


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    unit: str            # unit of the published value
    feature: str         # "level" | "price"  (price: % deviation from the 2010-2025 average level)
    direction: int       # +1: a rise is good for credit; -1: a rise is bad
    shock_unit: str      # how a user's shock is read: "pp" | "bps" | "pct"
    prior_z_per_sd: float  # reference sensitivity: credit-cycle units per 1 sd of the feature

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "unit": self.unit, "feature": self.feature,
                "direction": "a rise is good for credit" if self.direction > 0 else "a rise is bad for credit",
                "shock_unit": self.shock_unit}


SERIES: tuple[Series, ...] = (
    Series("gdp_real", "Real GDP growth", "% y/y", "level", +1, "pp", 0.20),
    Series("gdp_nonoil", "Non-oil real GDP growth", "% y/y", "level", +1, "pp", 0.25),
    Series("brent", "Oil price (Brent)", "USD/bbl", "price", +1, "pct", 0.15),
    Series("cpi", "CPI inflation", "% y/y", "level", -1, "pp", 0.05),
    Series("unemployment", "Unemployment rate", "%", "level", -1, "pp", 0.15),
    Series("repo", "SAMA repo (policy) rate", "%", "level", -1, "bps", 0.10),
    Series("saibor_3m", "3-month SAIBOR", "%", "level", -1, "bps", 0.10),
    Series("gov_spend", "Government expenditure", "% of GDP", "level", +1, "pp", 0.10),
    Series("re_price", "Real estate price index", "index", "price", +1, "pct", 0.10),
    Series("current_account", "Current account balance", "% of GDP", "level", +1, "pp", 0.05),
    Series("credit_growth", "Bank credit to the private sector", "% y/y", "level", +1, "pp", 0.10),
)
BY_KEY = {s.key: s for s in SERIES}


class MevError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def annual_table() -> pd.DataFrame:
    """The published annual values: one row per series and year (history and projection)."""
    path = MEV_DIR / "mev_annual.csv"
    if not path.exists():
        raise MevError("The macroeconomic scenarios are not available yet. Please try again in a moment.")
    frame = pd.read_csv(path, dtype={"series": str, "kind": str})
    frame = frame[frame["series"].isin(BY_KEY)].copy()
    frame["year"] = frame["year"].astype(int)
    frame["value"] = frame["value"].astype(float)
    return frame.sort_values(["series", "year"]).reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def brent_monthly() -> pd.Series:
    path = MEV_DIR / "brent_monthly_eia.csv"
    with path.open() as fh:
        rows = [(r["Date"][:7], float(r["Price"])) for r in csv.DictReader(fh)]
    return pd.Series({m: v for m, v in rows}).sort_index()


@functools.lru_cache(maxsize=1)
def annual() -> pd.DataFrame:
    """year x series: realised values where published, IMF projections after; Brent from EIA monthly."""
    t = annual_table()
    hist = t[t["kind"] == "history"].pivot_table(index="year", columns="series", values="value", aggfunc="first")
    proj = t[t["kind"] == "projection"].pivot_table(index="year", columns="series", values="value", aggfunc="first")
    years = range(HISTORY_FROM, max(int(t["year"].max()), 2031) + 1)
    out = pd.DataFrame(index=pd.Index(list(years), name="year"), columns=[s.key for s in SERIES], dtype=float)
    for key in out.columns:
        if key in hist:
            out.loc[hist.index.intersection(out.index), key] = hist[key]
        if key in proj:
            missing = out[key].isna()
            idx = proj.index.intersection(out.index[missing])
            out.loc[idx, key] = proj.loc[idx, key]
    # Brent: the EIA monthly averages give the calendar-year average for every complete year.
    bm = brent_monthly()
    by_year = pd.Series(bm.values, index=[int(m[:4]) for m in bm.index]).groupby(level=0)
    counts, means = by_year.size(), by_year.mean()
    for y in means.index:
        if y in out.index and counts[y] == 12:
            out.loc[y, "brent"] = float(means[y])
    return out


@functools.lru_cache(maxsize=1)
def fill_notes() -> dict[str, str]:
    """How each series' gaps (if any) were filled, said plainly for the model card."""
    a = annual()
    notes: dict[str, str] = {}
    for s in SERIES:
        col = a[s.key]
        known = col.dropna()
        if known.empty:
            notes[s.key] = "no published values: series not used"
            continue
        first, last = int(known.index.min()), int(known.index.max())
        gaps = [int(y) for y in col.loc[first:last].index[col.loc[first:last].isna()]]
        parts = [f"published {first}-{last}"]
        if gaps:
            parts.append(f"{len(gaps)} interior gap year(s) {gaps[:6]} filled by linear interpolation")
        if first > HISTORY_FROM:
            parts.append(f"before {first} held at the first published value for the feature only")
        if last < 2031:
            parts.append(f"after {last} held flat at the last value")
        notes[s.key] = "; ".join(parts)
    return notes


@functools.lru_cache(maxsize=1)
def filled() -> pd.DataFrame:
    """The annual table with interior gaps interpolated and the ends held (for the features only)."""
    a = annual().copy()
    for key in a.columns:
        col = a[key]
        if col.notna().any():
            a[key] = col.interpolate(limit_area="inside").ffill().bfill()
    return a


REFERENCE_YEARS = (2010, 2025)


@functools.lru_cache(maxsize=16)
def price_reference(key: str) -> float:
    """The reference level of a price series: its average over 2010-2025 (the feature is the % deviation from it)."""
    return float(filled()[key].loc[REFERENCE_YEARS[0]:REFERENCE_YEARS[1]].mean())


def _features_from_levels(levels: pd.DataFrame) -> pd.DataFrame:
    feats = pd.DataFrame(index=levels.index)
    for s in SERIES:
        col = levels[s.key].astype(float)
        if s.feature == "price":
            feats[s.key] = (col / price_reference(s.key) - 1.0) * 100.0
        else:
            feats[s.key] = col
    return feats


@functools.lru_cache(maxsize=1)
def annual_features() -> pd.DataFrame:
    return _features_from_levels(filled())


@functools.lru_cache(maxsize=1)
def feature_stats() -> dict[str, dict[str, float]]:
    """Mean and standard deviation of each feature over the realised history (1990 to the last full year)."""
    f = annual_features().loc[HISTORY_FROM:2025]
    return {k: {"mean": float(f[k].mean()), "sd": float(f[k].std(ddof=1)) or 1.0} for k in f.columns}


def standardise(feats: pd.DataFrame) -> pd.DataFrame:
    st = feature_stats()
    out = pd.DataFrame(index=feats.index)
    for s in SERIES:
        out[s.key] = (feats[s.key] - st[s.key]["mean"]) / st[s.key]["sd"] * s.direction
    return out


# ------------------------------------------------------------------ periods

def period_year_fraction(period: str) -> float:
    """2026Q2 -> 2026.375 (mid-quarter); 2026-08 -> 2026.625 (mid-month)."""
    if "Q" in period:
        y, q = period.split("Q")
        return int(y) + (int(q) - 0.5) / 4.0
    y, m = period.split("-")
    return int(y) + (int(m) - 0.5) / 12.0


def at_period(period: str) -> dict[str, float]:
    """The feature values at a quarter or month: the annual series interpolated between mid-years.

    Brent uses the real EIA monthly average price.
    """
    f = annual_features()
    x = period_year_fraction(period) - 0.5
    lo = int(math.floor(x))
    w = x - lo
    out = {}
    for s in SERIES:
        a, b = f[s.key].get(lo, np.nan), f[s.key].get(lo + 1, np.nan)
        out[s.key] = float(a * (1 - w) + b * w) if not (np.isnan(a) or np.isnan(b)) else float(a if not np.isnan(a) else b)
    bm = brent_monthly()
    month = _month_of(period)
    if month in bm.index:
        out["brent"] = float((bm[month] / price_reference("brent") - 1.0) * 100.0)
    return out


def levels_at_period(period: str) -> dict[str, float]:
    a = filled()
    x = period_year_fraction(period) - 0.5
    lo = int(math.floor(x))
    w = x - lo
    out = {}
    for s in SERIES:
        va, vb = a[s.key].get(lo, np.nan), a[s.key].get(lo + 1, np.nan)
        out[s.key] = float(va * (1 - w) + vb * w)
    bm = brent_monthly()
    month = _month_of(period)
    if month in bm.index:
        out["brent"] = float(bm[month])
    return out


def _month_of(period: str) -> str:
    if "Q" in period:
        y, q = period.split("Q")
        return f"{y}-{int(q) * 3:02d}"
    return period


# ------------------------------------------------------------------ scenario paths

def _shocked_levels(levels: pd.DataFrame, start_year: int, scenario: str) -> pd.DataFrame:
    if scenario == "base":
        return levels
    st = feature_stats()
    sign = 1.0 if scenario == "upturn" else -1.0
    size = UP_SD if scenario == "upturn" else DOWN_SD
    profile = UP_PROFILE if scenario == "upturn" else DOWN_PROFILE
    out = levels.copy()
    for i in range(HORIZON):
        y = start_year + i
        for s in SERIES:
            move = sign * size * profile[i] * st[s.key]["sd"] * s.direction
            if s.feature == "price":
                # A move of `move` % in the deviation-from-trend feature, applied to the level.
                out.loc[y, s.key] = levels.loc[y, s.key] * (1.0 + move / 100.0)
            else:
                out.loc[y, s.key] = levels.loc[y, s.key] + move
    return out


@functools.lru_cache(maxsize=64)
def paths_from(start_year: int) -> dict[str, pd.DataFrame]:
    """scenario -> DataFrame(year x series) of LEVELS for start_year .. start_year+4, plus features."""
    base = filled()
    out = {}
    for sc in SCENARIOS:
        lv = _shocked_levels(base, start_year, sc)
        feats = _features_from_levels(lv)
        out[sc] = lv.loc[start_year:start_year + HORIZON - 1].copy()
        out[sc + "_features"] = feats.loc[start_year:start_year + HORIZON - 1].copy()
    return out


def shocked_features(start_year: int, scenario: str, shocks: dict[str, float]) -> pd.DataFrame:
    """The scenario's feature path with user MEV shocks applied to the levels in every year.

    shocks: series key -> move in the series' shock unit (pp, bps, or % of the level for prices).
    """
    base = filled()
    lv = _shocked_levels(base, start_year, scenario).copy()
    yrs = list(range(start_year, start_year + HORIZON))
    for key, move in shocks.items():
        s = BY_KEY[key]
        if s.shock_unit == "pct":
            lv.loc[yrs, key] = lv.loc[yrs, key] * (1.0 + move / 100.0)
        elif s.shock_unit == "bps":
            lv.loc[yrs, key] = lv.loc[yrs, key] + move / 100.0
        else:
            lv.loc[yrs, key] = lv.loc[yrs, key] + move
    return _features_from_levels(lv).loc[start_year:start_year + HORIZON - 1]


def manifest() -> dict[str, Any]:
    path = MEV_DIR / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def describe() -> list[dict[str, Any]]:
    a = annual()
    notes = fill_notes()
    man = {m["key"]: m for m in manifest().get("series", [])}
    out = []
    for s in SERIES:
        col = a[s.key].dropna()
        d = s.to_dict()
        d.update({"first_year": int(col.index.min()) if len(col) else None,
                  "last_year": int(col.index.max()) if len(col) else None,
                  "coverage": notes.get(s.key, ""), "source": man.get(s.key, {}).get("source", ""),
                  "vintage": man.get(s.key, {}).get("vintage", ""),
                  "retrieved": man.get(s.key, {}).get("retrieved", "")})
        out.append(d)
    return out
