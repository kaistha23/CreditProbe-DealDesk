"""Figures from the v5 corporate book, read-only, for the Demo seed.

Every number the seed quotes comes from here, and the tests recompute each one
with pandas straight from the parquet files. Amounts are SAR million, as the
books publish them.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from backend.workspace_v5 import paths

EXPOSURE_COLS = ["borrower_id", "borrower_name", "facility_id", "reporting_quarter", "sector", "sub_sector",
                 "ead_sar_mn", "ecl_sar_mn", "stage", "ews_score", "ews_band", "ews_ruleset_version"]


@lru_cache(maxsize=1)
def exposure() -> pd.DataFrame:
    return pd.read_parquet(paths.EWS_CORP_EXPOSURE, columns=EXPOSURE_COLS)


@lru_cache(maxsize=1)
def borrowers() -> pd.DataFrame:
    return pd.read_parquet(paths.CORP_BORROWER)


def _f(v: Any) -> float:
    return float(v)


def portfolio(period: str) -> dict[str, Any]:
    e = exposure()
    q = e[e.reporting_quarter == period]
    return {"period": period, "ead": _f(q.ead_sar_mn.sum()), "ecl": _f(q.ecl_sar_mn.sum()),
            "borrowers": int(q.borrower_id.nunique()), "facilities": int(len(q))}


def sector(name: str, period: str) -> dict[str, Any]:
    e = exposure()
    q = e[(e.reporting_quarter == period) & (e.sector == name)]
    ead, ecl = _f(q.ead_sar_mn.sum()), _f(q.ecl_sar_mn.sum())
    return {"sector": name, "period": period, "ead": ead, "ecl": ecl, "coverage_pct": 100 * ecl / ead if ead else 0.0,
            "borrowers": int(q.borrower_id.nunique()), "facilities": int(len(q))}


def sectors(period: str) -> list[dict[str, Any]]:
    e = exposure()
    q = e[e.reporting_quarter == period]
    g = q.groupby("sector").agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"),
                                borrowers=("borrower_id", "nunique"), facilities=("facility_id", "count"))
    g = g.sort_values("ead", ascending=False)
    total = float(g.ead.sum())
    return [{"sector": str(k), "ead": _f(r.ead), "ecl": _f(r.ecl), "coverage_pct": 100 * r.ecl / r.ead,
             "share_pct": 100 * r.ead / total, "borrowers": int(r.borrowers), "facilities": int(r.facilities)}
            for k, r in g.iterrows()]


def sub_sectors(name: str, before: str, after: str) -> list[dict[str, Any]]:
    e = exposure()
    s = e[(e.sector == name) & e.reporting_quarter.isin([before, after])]
    p = s.pivot_table(index="sub_sector", columns="reporting_quarter", values=["ead_sar_mn", "ecl_sar_mn"],
                      aggfunc="sum")
    rows = []
    for sub in p.index:
        e0, e1 = _f(p.loc[sub, ("ead_sar_mn", before)]), _f(p.loc[sub, ("ead_sar_mn", after)])
        c0, c1 = _f(p.loc[sub, ("ecl_sar_mn", before)]), _f(p.loc[sub, ("ecl_sar_mn", after)])
        rows.append({"sub_sector": str(sub), "ead_before": e0, "ead_after": e1, "ecl_before": c0, "ecl_after": c1,
                     "ecl_change": c1 - c0})
    return sorted(rows, key=lambda r: -r["ecl_change"])


def stage_mix(name: str, before: str, after: str) -> list[dict[str, Any]]:
    e = exposure()
    s = e[(e.sector == name) & e.reporting_quarter.isin([before, after])]
    p = s.pivot_table(index="stage", columns="reporting_quarter", values=["ead_sar_mn", "ecl_sar_mn"], aggfunc="sum")
    return [{"stage": int(st), "ead_before": _f(p.loc[st, ("ead_sar_mn", before)]),
             "ead_after": _f(p.loc[st, ("ead_sar_mn", after)]),
             "ecl_before": _f(p.loc[st, ("ecl_sar_mn", before)]),
             "ecl_after": _f(p.loc[st, ("ecl_sar_mn", after)])} for st in sorted(p.index)]


def borrower(borrower_id: str, period: str) -> dict[str, Any]:
    """One borrower at one quarter: exposure (EAD) and ECL summed over its facilities,
    the customer Early Warning score (the highest facility score) and its band,
    and the rating, outlook and ratios from the book's borrower table."""
    e = exposure()
    x = e[(e.borrower_id == borrower_id) & (e.reporting_quarter == period)]
    if x.empty:
        raise LookupError(f"{borrower_id} has no exposure at {period}")
    top = x.sort_values(["ews_score", "facility_id"], ascending=[False, True]).iloc[0]
    b = borrowers()
    r = b[(b.borrower_id == borrower_id) & (b.reporting_quarter == period)].iloc[0]
    return {
        "borrower_id": borrower_id, "period": period, "name": str(x.borrower_name.iloc[0]),
        "sector": str(x.sector.iloc[0]), "sub_sector": str(x.sub_sector.iloc[0]),
        "exposure": _f(x.ead_sar_mn.sum()), "ecl": _f(x.ecl_sar_mn.sum()), "facilities": int(len(x)),
        "facility_ids": sorted(str(v) for v in x.facility_id),
        "ews_score": int(top.ews_score), "ews_band": str(top.ews_band), "ews_ruleset": str(top.ews_ruleset_version),
        "rating": str(r.rating_current), "rating_previous": str(r.rating_previous),
        "rating_migration": str(r.rating_migration), "rating_outlook": str(r.rating_outlook),
        "group_name": str(r.group_name), "leverage_x": _f(r.leverage_x), "dscr_x": _f(r.dscr_x),
        "watchlist": bool(r.watchlist_flag), "quarters_on_watchlist": int(r.quarters_on_watchlist),
    }


# ----------------------------------------------------------------- words


def mn(v: float, places: int = 1) -> str:
    """'SAR 18,695.2m' -- SAR million, as the books publish them."""
    return f"SAR {v:,.{places}f}m"


def bn(v: float) -> str:
    """'SAR 18.7bn' for an amount given in SAR million."""
    return f"SAR {v / 1000:,.1f}bn"


def pct(v: float, places: int = 1) -> str:
    return f"{v:.{places}f}%"
