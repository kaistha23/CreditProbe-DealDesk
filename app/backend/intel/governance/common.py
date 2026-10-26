"""R13 IE shared helpers: reads through Data Domains only, lineage figures, statistics.

Every number an engine returns is a figure {"value", "unit", "source"} whose source resolves to a registered relation
and row (backend.dealdesk.data.lineage), or a computed figure whose "basis" lists the relation, the rows (count and
filter) and the method. No file is opened outside the registry.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Iterable

import pandas as pd

from backend.dealdesk.data import store
from backend.dealdesk.data.store import dd_frame
from backend.v5common.ratings import rank as rating_rank

AS_OF_QUARTER = "2026Q2"
OUTCOME_QUARTERS = 4  # outcomes measured over the four quarters after a decision (12 months)
SEED_NOTE = ("Decision history is a fictional seed published to Data Domains (domain governance, gov_* relations, "
             "ops/r13_seed_governance.py); outcomes (stage, DPD, default, rating drift) are the corporate book's own.")


# ------------------------------------------------------------------ quarters

def q_index(q: str) -> int:
    y, n = str(q).split("Q")
    return int(y) * 4 + int(n) - 1


def q_label(i: int) -> str:
    return f"{i // 4}Q{i % 4 + 1}"


def q_add(q: str, n: int) -> str:
    return q_label(q_index(q) + n)


# ------------------------------------------------------------------ reads (cached by relation version / file mtime)

def _ver(rel: str) -> str:
    try:
        p = store.relation_path(rel)
        return f"{p.stat().st_mtime_ns}" if p.exists() else "0"
    except KeyError:
        return "0"


@lru_cache(maxsize=32)
def _frame(rel: str, ver: str, cols: tuple[str, ...] | None) -> pd.DataFrame:
    return dd_frame(rel, columns=list(cols) if cols else None)


def frame(rel: str, columns: Iterable[str] | None = None) -> pd.DataFrame:
    return _frame(rel, _ver(rel) + str(store.root()), tuple(columns) if columns else None)


def decisions() -> pd.DataFrame:
    return frame("gov_decision")


def steps() -> pd.DataFrame:
    return frame("gov_approval_step")


def exceptions() -> pd.DataFrame:
    return frame("gov_policy_exception")


FAC_COLS = ("facility_id", "borrower_id", "reporting_quarter", "limit_sar_mn", "ead_sar_mn", "stage", "default_flag",
            "dpd_days", "ecl_sar_mn", "pd_pit_12m")
BOR_COLS = ("borrower_id", "borrower_name", "reporting_quarter", "sector", "rating_current", "dscr_x", "leverage_x",
            "current_ratio_x", "pd_ttc_12m", "watchlist_flag", "restructured_flag")


def facilities() -> pd.DataFrame:
    return frame("corp_facility_quarter", FAC_COLS)


def borrowers() -> pd.DataFrame:
    return frame("corp_borrower_quarter", BOR_COLS)


# ------------------------------------------------------------------ outcomes (read live from the book)

@lru_cache(maxsize=4)
def _outcomes(dver: str, fver: str) -> pd.DataFrame:
    d = decisions()
    if d.empty:
        return pd.DataFrame()
    f = facilities()
    agg = (f.assign(qi=f["reporting_quarter"].map(q_index))
           .groupby(["borrower_id", "qi"]).agg(stage=("stage", "max"), default=("default_flag", "max"),
                                                dpd=("dpd_days", "max"), ead=("ead_sar_mn", "sum")).reset_index())
    b = borrowers()
    rat = b.assign(qi=b["reporting_quarter"].map(q_index))[["borrower_id", "qi", "rating_current"]]
    base = d[["decision_id", "borrower_id", "decision_quarter", "rating_at_decision"]].copy()
    base["q0"] = base["decision_quarter"].map(q_index)
    s0 = base.merge(agg.rename(columns={"qi": "q0"})[["borrower_id", "q0", "stage"]], on=["borrower_id", "q0"], how="left")
    s0 = s0.set_index("decision_id")["stage"].fillna(1).astype(int)
    exp = pd.concat([base.assign(qi=base["q0"] + k) for k in range(1, OUTCOME_QUARTERS + 1)], ignore_index=True)
    w = exp.merge(agg, on=["borrower_id", "qi"], how="inner")
    if w.empty:
        return pd.DataFrame()
    g = w.groupby("decision_id")
    o = pd.DataFrame({"worst_stage": g["stage"].max().astype(int), "default_12m": g["default"].max().astype(int),
                      "max_dpd": g["dpd"].max().astype(int), "last_qi": g["qi"].max(), "quarters_observed": g["qi"].size()})
    o["stage_at_decision"] = s0.reindex(o.index).fillna(1).astype(int)
    o["migrated_12m"] = (o["worst_stage"] > o["stage_at_decision"]).astype(int)
    o["stage3_12m"] = (o["worst_stage"] >= 3).astype(int)
    o = o.reset_index()
    last = w.merge(o[["decision_id", "last_qi"]], left_on=["decision_id", "qi"], right_on=["decision_id", "last_qi"])
    o = o.merge(last[["decision_id", "ead"]].rename(columns={"ead": "ead_end"}), on="decision_id", how="left")
    o = o.merge(base[["decision_id", "borrower_id", "rating_at_decision"]], on="decision_id")
    o = o.merge(rat.rename(columns={"qi": "last_qi"}), on=["borrower_id", "last_qi"], how="left")
    from backend.v5common.ratings import RATING_ORDER
    rk = {r: i for i, r in enumerate(RATING_ORDER)}
    o["notches_12m"] = (o["rating_current"].map(rk) - o["rating_at_decision"].map(rk)).fillna(0).astype(int)
    o["outcome_quarter"] = o["last_qi"].map(q_label)
    return o.drop(columns=["borrower_id", "rating_at_decision", "rating_current", "last_qi"])


def outcomes() -> pd.DataFrame:
    """One row per decision: what happened in the four quarters after it (corp_facility_quarter, corp_borrower_quarter)."""
    return _outcomes(_ver("gov_decision") + str(store.root()), _ver("corp_facility_quarter"))


def decisions_with_outcomes() -> pd.DataFrame:
    d = decisions()
    o = outcomes()
    if d.empty or o.empty:
        return d
    return d.merge(o, on="decision_id", how="left")


# ------------------------------------------------------------------ figures

def fig(relation: str, row: dict[str, Any], column: str, unit: str = "") -> dict[str, Any]:
    """A traced figure: value from one row of a registered relation."""
    src = store.trace(relation, row)
    src["column"] = column
    v = row.get(column)
    try:
        v = None if v is None or (isinstance(v, float) and math.isnan(v)) else v
    except TypeError:
        pass
    if hasattr(v, "item"):
        v = v.item()
    return {"value": v, "unit": unit, "source": src}


def computed(value: float | int | None, unit: str, relations: list[str], rows: int, method: str,
             filt: dict[str, Any] | None = None) -> dict[str, Any]:
    """A computed figure with its basis: which relations, how many rows, which filter and the method."""
    if value is not None and not isinstance(value, (int, str)):
        value = None if (isinstance(value, float) and math.isnan(value)) else round(float(value), 4)
    return {"value": value, "unit": unit,
            "basis": {"relations": relations, "rows": int(rows), "filter": filt or {}, "method": method,
                      "period": AS_OF_QUARTER}}


# ------------------------------------------------------------------ statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n (rate in 0-1)."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def poisson_ratio_ci(obs: int, exp: float, z: float = 1.96) -> tuple[float, float]:
    """Approximate 95% interval for observed/expected (Byar's approximation)."""
    if exp <= 0:
        return (0.0, 0.0)
    o = obs
    lo = 0.0 if o == 0 else o * (1 - 1 / (9 * o) - z / (3 * math.sqrt(o))) ** 3 / exp
    o1 = o + 1
    hi = o1 * (1 - 1 / (9 * o1) + z / (3 * math.sqrt(o1))) ** 3 / exp
    return (max(0.0, lo), hi)


def rate(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(k, n)
    return {"pct": round(100 * k / n, 2) if n else None, "k": int(k), "n": int(n),
            "ci_low_pct": round(100 * lo, 2), "ci_high_pct": round(100 * hi, 2)}


def thin(n: int, floor: int = 30) -> bool:
    return n < floor


def pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}%"
