"""The inputs of the scenario engine, and what they can and cannot support.

Bank history (Data Domains `cockpit`, the corporate book release v4-saudi-corporate-20q-v4, read-only):
  corp_facility_quarter   facility x quarter, 2021Q3-2026Q2 (20 quarters): EAD, stage, default flag, PD, LGD, ECL,
                          utilisation, write-offs and recoveries
  corp_borrower_quarter   borrower x quarter: sector, rating, revenue, EBITDA margin
  What-If cycle model     data/whatif_v5/corporate/cycle_model.json: the sector credit-cycle index (Vasicek-implied Z)
                          per sector and quarter, 2021Q4-2026Q2
Macro (data/whatif_v5/mev, public, annual): Brent (EIA, since 1987), real GDP growth (IMF WEO, since 1990),
non-oil real GDP growth (IMF via FRED, since 2005), 3-month SAIBOR (SAMA, since 2007), real-estate price index
(GASTAT, since 2014).

`LIMITS` is the statement every output carries (PLAN_R13 §S "state it in every answer").
"""
from __future__ import annotations

import functools
import json
from typing import Any

import numpy as np
import pandas as pd

from backend.v5common import ratings
from backend.whatif_v5 import paths as wpaths
from backend.whatif_v5.domain import mev

CORP = wpaths.LAKE / wpaths.CORP_RELEASE
CYCLE_FILE = wpaths.V5 / "data" / "whatif_v5" / "corporate" / "cycle_model.json"
LAST_FULL_YEAR = 2025
LAG = 4  # quarters in the one-year horizon

RELATIONS = {
    "facility": ("cockpit.corp_facility_quarter", f"data/cockpit_v4_lake/{wpaths.CORP_RELEASE}/corp_facility_quarter.parquet"),
    "borrower": ("cockpit.corp_borrower_quarter", f"data/cockpit_v4_lake/{wpaths.CORP_RELEASE}/corp_borrower_quarter.parquet"),
    "collateral": ("cockpit.corp_collateral_quarter", f"data/cockpit_v4_lake/{wpaths.CORP_RELEASE}/corp_collateral_quarter.parquet"),
    "cycle": ("whatif.cycle_model (corporate)", "data/whatif_v5/corporate/cycle_model.json"),
    "mev": ("whatif.mev_annual", "data/whatif_v5/mev/mev_annual.csv"),
    "brent": ("whatif.brent_monthly_eia", "data/whatif_v5/mev/brent_monthly_eia.csv"),
}


def quarter_index(q: str) -> int:
    y, n = q.split("Q")
    return int(y) * 4 + int(n) - 1


@functools.lru_cache(maxsize=1)
def facility() -> pd.DataFrame:
    cols = ["facility_id", "borrower_id", "reporting_quarter", "sector", "ead_sar_mn", "limit_sar_mn", "drawn_sar_mn",
            "undrawn_sar_mn", "utilisation_pct", "stage", "default_flag", "pd_pit_12m", "pd_lifetime", "lgd_pct",
            "ecl_sar_mn", "ecl_12m_sar_mn", "ecl_lifetime_sar_mn", "write_off_sar_mn", "recovery_sar_mn"]
    f = pd.read_parquet(CORP / "corp_facility_quarter.parquet", columns=cols)
    f["t"] = f["reporting_quarter"].map(quarter_index)
    return f


@functools.lru_cache(maxsize=1)
def borrower() -> pd.DataFrame:
    cols = ["borrower_id", "reporting_quarter", "sector", "rating_current", "revenue_sar_mn", "ebitda_margin_pct"]
    b = pd.read_parquet(CORP / "corp_borrower_quarter.parquet", columns=cols)
    b["t"] = b["reporting_quarter"].map(quarter_index)
    b["rank"] = b["rating_current"].map(ratings.rank)
    return b


@functools.lru_cache(maxsize=1)
def quarters() -> list[str]:
    return sorted(facility()["reporting_quarter"].unique(), key=quarter_index)


@functools.lru_cache(maxsize=1)
def cycle_model() -> dict[str, Any]:
    return json.loads(CYCLE_FILE.read_text())


@functools.lru_cache(maxsize=1)
def sector_quarter() -> pd.DataFrame:
    """Sector x quarter panel: EAD-weighted 12-month PD of performing facilities, the observed default rate, the
    Stage 1 -> 2 migration rate (share of last quarter's Stage 1 facilities in Stage 2 now) and utilisation."""
    f = facility()
    perf = f[f["stage"] < 3]
    w = perf["ead_sar_mn"].clip(lower=1e-9)
    g = perf.assign(pw=perf["pd_pit_12m"] * w, w=w, uw=perf["utilisation_pct"] * w)
    pdw = g.groupby(["sector", "reporting_quarter"]).agg(pw=("pw", "sum"), w=("w", "sum"), uw=("uw", "sum"),
                                                          n_perf=("facility_id", "size"))
    pdw["pd"] = pdw["pw"] / pdw["w"]
    pdw["util"] = pdw["uw"] / pdw["w"]
    prev = f[["facility_id", "t", "stage", "default_flag"]].assign(t=lambda d: d["t"] + 1)
    m = f.merge(prev, on=["facility_id", "t"], suffixes=("", "_prev"))
    s1 = m[m["stage_prev"] == 1]
    mig = s1.groupby(["sector", "reporting_quarter"]).agg(n_s1=("facility_id", "size"),
                                                           to_s2=("stage", lambda s: int((s == 2).sum())))
    nd = m[m["default_flag_prev"] == 0].groupby(["sector", "reporting_quarter"]).agg(
        n_nd=("facility_id", "size"), new_def=("default_flag", "sum"))
    out = pdw.join(mig, how="left").join(nd, how="left").reset_index()
    out["mig12"] = out["to_s2"] / out["n_s1"]
    out["dr"] = out["new_def"] / out["n_nd"]
    out["t"] = out["reporting_quarter"].map(quarter_index)
    return out.sort_values(["sector", "t"]).reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def macro_annual() -> pd.DataFrame:
    """year x series, published history only (1990..2025): the MEV store's realised values."""
    a = mev.annual().loc[:LAST_FULL_YEAR]
    return a[["brent", "gdp_real", "gdp_nonoil", "saibor_3m", "repo", "re_price"]].copy()


def macro_at_quarter(q: str) -> dict[str, float]:
    """The macro drivers at a quarter as the satellite models read them: Brent's year-on-year % change of the quarterly
    average (EIA monthly), and the four-quarter-ending real and non-oil GDP growth (annual rates weighted by quarter)."""
    bm = mev.brent_monthly()
    y, n = (int(x) for x in q.split("Q"))
    months = [f"{y}-{m:02d}" for m in range(3 * n - 2, 3 * n + 1)]
    months_prev = [f"{y - 1}-{m:02d}" for m in range(3 * n - 2, 3 * n + 1)]
    cur = float(np.mean([bm[m] for m in months if m in bm.index])) if any(m in bm.index for m in months) else np.nan
    prv = float(np.mean([bm[m] for m in months_prev if m in bm.index])) if any(m in bm.index for m in months_prev) else np.nan
    a = mev.filled()
    out = {"brent_yoy": (cur / prv - 1) * 100 if prv == prv and cur == cur else np.nan}
    for key in ("gdp_real", "gdp_nonoil"):
        out[key] = float((a.loc[y, key] * n + a.loc[y - 1, key] * (4 - n)) / 4)
    out["saibor_3m"] = float((a.loc[y, "saibor_3m"] * n + a.loc[y - 1, "saibor_3m"] * (4 - n)) / 4)
    return out


@functools.lru_cache(maxsize=1)
def resolved_defaults() -> dict[str, Any]:
    """How many defaults have been worked out (a write-off or a recovery booked), the basis for any LGD estimate."""
    f = facility()
    d = f[f["default_flag"] == 1]
    res = d[(d["write_off_sar_mn"] > 0) | (d["recovery_sar_mn"] > 0)]
    first = res["reporting_quarter"].min() if len(res) else None
    return {"defaulted_facilities": int(d["facility_id"].nunique()), "resolved_facilities": int(res["facility_id"].nunique()),
            "first_resolution": first, "quarters_with_resolutions": int(res["reporting_quarter"].nunique())}


def window() -> dict[str, Any]:
    q = quarters()
    a = macro_annual()
    return {"bank_from": q[0], "bank_to": q[-1], "bank_quarters": len(q),
            "macro_from": int(a.index.min()), "macro_to": LAST_FULL_YEAR,
            "macro_years": int(a["brent"].dropna().shape[0]),
            "nonoil_from": int(a["gdp_nonoil"].dropna().index.min()),
            "saibor_from": int(a["saibor_3m"].dropna().index.min()),
            "re_price_from": int(a["re_price"].dropna().index.min())}


def limits() -> dict[str, str]:
    """What the available data supports and what it does not (every answer and the memo carry this)."""
    w = window()
    rd = resolved_defaults()
    return {
        "supports": (f"Macro tails from {w['macro_years'] - 1} one-year moves of annual data ({w['macro_from']}–{w['macro_to']}: Brent, real GDP; "
                     f"non-oil GDP since {w['nonoil_from']}, SAIBOR since {w['saibor_from']}); the bank's own moves in sector PD, "
                     f"stage, rating, revenue and margin over {w['bank_quarters']} quarters ({w['bank_from']}–{w['bank_to']})."),
        "cannot": (f"The link from macro to PD and stage rests on {w['bank_quarters']} quarters, one partial cycle, so its "
                   f"coefficients carry wide bands; there is no long property index (the real-estate index starts {w['re_price_from']}, "
                   f"{2025 - w['re_price_from']} annual changes) and the bank's collateral marks are appraisals, not prices, so "
                   f"collateral shocks are labelled expert; downturn LGD cannot be estimated ({rd['resolved_facilities']:,} of "
                   f"{rd['defaulted_facilities']:,} defaulted facilities have a booked recovery or write-off, all since "
                   f"{rd['first_resolution']}, with workouts unfinished), so LGD stress is an expert add-on."),
        "short": (f"Data: {w['bank_quarters']} quarters of bank history ({w['bank_from']}–{w['bank_to']}); MEVs annual since "
                  f"{w['macro_from']}; no property index; few resolved defaults for downturn LGD."),
    }
