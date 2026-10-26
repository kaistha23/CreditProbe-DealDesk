"""The ECL runs P6 reads, through Session A's `ecl_runs` contract (docs/STATUS_R9_DATA.md).

`ecl_run(run_id, book)` and `anomalies()` come from `backend.r9_data.read` once that domain is merged. Until then a
local fixture with the same columns is built from the books (current run 2026Q3 = the books at their as-of, prior
run 2026Q2 = the books one period earlier; a handful of planted input anomalies on the current run). The fixture
never leaves this process.
"""
from __future__ import annotations

import functools
from typing import Any

import pandas as pd

from backend.spine.books import book as _book

CURRENT, PRIOR = "2026Q3", "2026Q2"


def _a():
    try:
        from backend.r9_data import read as r9  # type: ignore
        r9.ecl_run  # noqa: B018
        return r9
    except Exception:  # noqa: BLE001 - the domain is not merged yet
        return None


def source() -> str:
    return "ecl_runs (Data Domains)" if _a() is not None else "books (ecl_runs pending)"


@functools.lru_cache(maxsize=4)
def _fixture_run(run_id: str, bk: str) -> pd.DataFrame:
    b = _book(bk)
    period = b.as_of if run_id == CURRENT else b.comparison
    key, own, pc = b.exposure_key, b.customer_key, b.period_column
    cols = [key, own, pc, "ead_sar_mn", "limit_sar_mn", "pd_pit_12m", "pd_lifetime", "lgd_pct", "stage", "dpd_days",
            "ecl_sar_mn"]
    f = pd.read_parquet(b.path(b.exposure_relation), columns=cols, filters=[(pc, "=", period)])
    out = pd.DataFrame({
        "run_id": run_id, "book": bk, "exposure_id": f[key], "obligor_id": f[own], "book_period": period,
        "ead_sar_mn": f["ead_sar_mn"], "limit_sar_mn": f["limit_sar_mn"],
        "pd_12m_pct": f["pd_pit_12m"] * 100, "pd_lifetime_pct": f["pd_lifetime"] * 100, "lgd_pct": f["lgd_pct"],
        "stage": f["stage"], "dpd_days": f["dpd_days"], "overlay_sar_mn": 0.0, "ecl_sar_mn": f["ecl_sar_mn"],
    })
    if bk == "corporate":
        bq = pd.read_parquet(b.path(b.customer_relation), columns=[own, pc, "rating_current", "sector"],
                             filters=[(pc, "=", period)])
        out = out.merge(bq.rename(columns={own: "obligor_id", "rating_current": "rating"})[["obligor_id", "rating", "sector"]],
                        on="obligor_id", how="left")
        col = pd.read_parquet(b.path("corp_collateral_quarter"), columns=["facility_id", pc, "allocated_value_sar_mn"],
                              filters=[(pc, "=", period)]).groupby("facility_id")["allocated_value_sar_mn"].sum()
        out["collateral_sar_mn"] = out["exposure_id"].map(col).fillna(0.0)
        if run_id == CURRENT:
            out = out.reset_index(drop=True)
            for a in _FIXTURE_PLANTS:
                i = out.index[out["exposure_id"] == a["exposure_id"]]
                if len(i):
                    out.loc[i, a["field"]] = a["current_value"]
    return out.reset_index(drop=True)


def _plants() -> list[dict[str, Any]]:
    """Seven deterministic input errors on the fixture's current run (ECL untouched, so it still equals the books)."""
    b = _book("corporate")
    f = pd.read_parquet(b.path(b.exposure_relation), columns=["facility_id", "reporting_quarter", "stage", "pd_pit_12m",
                                                               "lgd_pct", "limit_sar_mn", "ead_sar_mn"],
                        filters=[("reporting_quarter", "in", [b.as_of, b.comparison])])
    now = f[f.reporting_quarter == b.as_of].set_index("facility_id")
    pri = f[f.reporting_quarter == b.comparison].set_index("facility_id")
    ids = sorted(set(now.index) & set(pri.index))
    s1 = [i for i in ids if now.at[i, "stage"] == 1 and pri.at[i, "stage"] == 1 and now.at[i, "ead_sar_mn"] > 5][::400][:7]
    plan = [("pd_12m_pct", lambda i: float(pri.at[i, "pd_pit_12m"] * 100 * 4 + 2), "PD changed with no rating change"),
            ("pd_12m_pct", lambda i: float(pri.at[i, "pd_pit_12m"] * 100 * 5 + 3), "PD changed with no rating change"),
            ("lgd_pct", lambda i: float(min(100.0, pri.at[i, "lgd_pct"] + 25)), "LGD changed with no collateral change"),
            ("lgd_pct", lambda i: float(min(100.0, pri.at[i, "lgd_pct"] + 30)), "LGD changed with no collateral change"),
            ("limit_sar_mn", lambda i: float(now.at[i, "ead_sar_mn"] * 0.8), "EAD above the limit"),
            ("collateral_sar_mn", lambda i: float("nan"), "Missing collateral value"),
            ("limit_sar_mn", lambda i: float(now.at[i, "ead_sar_mn"] * 0.7), "EAD above the limit")]
    out = []
    for n, (i, (fld, val, kind)) in enumerate(zip(s1, plan), 1):
        out.append({"anomaly_id": f"FX-{n:02d}", "run_id": CURRENT, "book": "corporate", "exposure_id": i, "kind": kind,
                    "field": fld, "current_value": val(i), "rerun_required": True})
    return out


try:
    _FIXTURE_PLANTS = _plants()
except Exception:  # noqa: BLE001 - no books, no plants
    _FIXTURE_PLANTS = []


def ecl_run(run_id: str, bk: str = "corporate") -> pd.DataFrame:
    r9 = _a()
    if r9 is not None:
        f = r9.ecl_run(run_id, bk)
        if "sector" not in f.columns and bk == "corporate":
            fx = _fixture_run(run_id, bk)[["exposure_id", "sector"]]
            f = f.merge(fx, on="exposure_id", how="left")
        return f
    return _fixture_run(run_id, bk).copy()


def anomalies() -> list[dict[str, Any]]:
    """The planted input anomalies on the current run (A's `ecl_anomaly`), else the fixture's own plants."""
    r9 = _a()
    if r9 is not None:
        a = r9.anomalies()
        return a.to_dict("records") if isinstance(a, pd.DataFrame) else list(a)
    return list(_FIXTURE_PLANTS)


def crwa(bk: str = "corporate") -> pd.DataFrame:
    """Credit RWA per exposure: A's `col_crwa` when merged, else EAD x a standardised corporate risk weight by rating
    (AAA–AA- 20%, A 50%, BBB–BB 100%, below BB- 150%) -- recorded as an assumption in STATUS."""
    r9 = _a()
    if r9 is not None and hasattr(r9, "crwa"):
        try:
            return r9.crwa(bk)
        except Exception:  # noqa: BLE001
            pass
    f = ecl_run(CURRENT, bk)
    if bk == "corporate":
        def rw(r: Any) -> float:
            s = str(r or "")
            if s.startswith(("AAA", "AA")):
                return 20.0
            if s.startswith("A"):
                return 50.0
            if s.startswith(("BBB", "BB")):
                return 100.0
            return 150.0 if s else 100.0
        w = f["rating"].map(rw)
    else:
        w = pd.Series(75.0, index=f.index)
    return pd.DataFrame({"exposure_id": f["exposure_id"], "obligor_id": f["obligor_id"], "ead_sar_mn": f["ead_sar_mn"],
                         "risk_weight_pct": w, "crwa_sar_mn": f["ead_sar_mn"] * w / 100.0})
