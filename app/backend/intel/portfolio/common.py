"""Shared plumbing for the portfolio steering engines (PLAN_R13 §I, session ID).

* Every business figure is read from a registered Data Domains relation (backend/data_builder/registry.py),
  read-only, and each read is recorded on a `Lineage` so a response lists the relations, periods and rows it used.
* Parameters come from the Deal Desk parameter tables (data/dealdesk/params/v1) and are cited by table and key.
* Every response has the same envelope: headline, 3-5 summary lines from a deterministic writer, KPIs, rows,
  data limits (what the data cannot tell us, N5), method and lineage.
"""
from __future__ import annotations

import functools
import hashlib
import json
import math
import pathlib
from typing import Any

import numpy as np
import pandas as pd

from backend.data_builder.registry import DOMAINS
from backend.dealdesk import params

V5 = pathlib.Path(__file__).resolve().parents[3]
VERSION = "r13-id-1"
AS_OF_QUARTER = "2026Q2"          # the corporate book's as-of (cockpit release v4-saudi-corporate-20q-v4)
RUN_CURRENT = "2026Q3"            # the ECL run that values the 2026Q2 book (r9 ecl_runs)
RUN_PRIOR = "2026Q2"
NEXT_RUN = "2026Q4"

# Rating order and the risk weights the collateral domain's col_crwa applies (backend/r9_data/build.py `_RW`):
RATING_ORDER = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
CRWA_RW = {**{r: 20 for r in RATING_ORDER[:4]}, **{r: 50 for r in RATING_ORDER[4:7]},
           **{r: 100 for r in RATING_ORDER[7:13]}, **{r: 150 for r in RATING_ORDER[13:]}}


def bucket(rating: Any) -> str:
    r = str(rating)
    if r not in RATING_ORDER:
        return "CCC-C"
    i = RATING_ORDER.index(r)
    return "IG" if i <= 9 else "BB" if i <= 12 else "B" if i <= 15 else "CCC-C"


BUCKETS = ["IG", "BB", "B", "CCC-C"]


class Lineage:
    """The relations a response read: domain, relation, path, period, rows, columns used."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def add(self, domain: str, relation: str, period: Any = None, rows: int | None = None,
            columns: list[str] | None = None, note: str | None = None) -> None:
        key = f"{domain}.{relation}"
        cur = self.items.get(key) or {"domain": domain, "relation": relation,
                                      "path": DOMAINS[domain]["relations"][relation]["path"] if domain in DOMAINS else None,
                                      "period": period, "rows": rows, "columns": []}
        if rows is not None:
            cur["rows"] = rows
        if period is not None:
            cur["period"] = period
        for c in columns or []:
            if c not in cur["columns"]:
                cur["columns"].append(c)
        if note:
            cur["note"] = note
        self.items[key] = cur

    def param(self, table: str, key: str) -> None:
        k = f"params.{table}"
        cur = self.items.get(k) or {"domain": "deal_desk_parameters", "relation": table,
                                    "path": f"data/dealdesk/params/v1/{table}.json", "period": params.table(table).get("version"),
                                    "rows": None, "columns": []}
        if key not in cur["columns"]:
            cur["columns"].append(key)
        self.items[k] = cur

    def list(self) -> list[dict[str, Any]]:
        return list(self.items.values())


def registered_path(domain: str, relation: str) -> pathlib.Path:
    rel = DOMAINS[domain]["relations"][relation]
    p = (V5 / rel["path"]).resolve()
    if (V5 / "data").resolve() not in p.parents:
        raise PermissionError(f"{domain}.{relation} is not under data/")
    return p


@functools.lru_cache(maxsize=32)
def _frame(domain: str, relation: str) -> pd.DataFrame:
    return pd.read_parquet(registered_path(domain, relation))


def read(lin: Lineage | None, domain: str, relation: str, columns: list[str] | None = None,
         period: tuple[str, Any] | None = None) -> pd.DataFrame:
    """A registered relation (read-only, cached), optionally filtered on one period column."""
    f = _frame(domain, relation)
    if period is not None:
        col, val = period
        f = f[f[col] == val]
    if columns:
        f = f[[c for c in columns if c in f.columns]]
    if lin is not None:
        lin.add(domain, relation, period=period[1] if period else None, rows=int(len(f)), columns=list(f.columns))
    return f.reset_index(drop=True)


def capital_ratio(lin: Lineage | None = None) -> float:
    if lin is not None:
        lin.param("capital", "capital_ratio_target")
    return float(params.rows("capital")["capital_ratio_target"])


def tier1(lin: Lineage | None = None) -> float:
    if lin is not None:
        lin.param("capital", "tier1_sar_mn")
    return float(params.rows("capital")["tier1_sar_mn"])


def appetite_rows() -> dict[str, dict[str, Any]]:
    return {x["name"]: x for x in params.rows("risk_appetite")}


def hurdle(sector: str, lin: Lineage | None = None) -> tuple[float, str]:
    r = params.rows("returns")
    if lin is not None:
        lin.param("returns", "hurdle")
    if sector in r.get("hurdle_sector", {}):
        return float(r["hurdle_sector"][sector]), f"returns.hurdle_sector[{sector}]"
    return float(r["hurdle"]["Corporate Banking"]), "returns.hurdle[Corporate Banking]"


# ------------------------------------------------------------------ formatting (the deterministic writers' vocabulary)

def sar(v: float | None, dp: int = 1) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/a"
    a = abs(v)
    if a >= 1000:
        return f"SAR {v / 1000:,.{max(dp, 1)}f}bn"
    return f"SAR {v:,.{dp}f}m"


def pct(v: float | None, dp: int = 1) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/a"
    return f"{100 * v:.{dp}f}%"


def bps(v: float | None) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/a"
    return f"{v:,.0f} bps"


def clean(x: Any) -> Any:
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python numbers, floats rounded to 6 dp."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return None if not math.isfinite(f) else round(f, 6)
    if isinstance(x, np.bool_):
        return bool(x)
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def envelope(engine: str, title: str, headline: str, summary: list[str], kpis: list[dict[str, Any]],
             rows: list[dict[str, Any]], data_limits: list[str], method: list[str], lin: Lineage,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"engine": f"intel.portfolio.{engine}", "version": VERSION, "title": title,
            "as_of": AS_OF_QUARTER, "ecl_run": RUN_CURRENT, "headline": headline, "summary": summary[:5],
            "kpis": kpis, "rows": rows, "data_limits": data_limits, "method": method, "lineage": lin.list(),
            "writer": "deterministic", **(extra or {})}
    body = clean(body)
    body["digest"] = hashlib.sha256(json.dumps({k: body[k] for k in ("kpis", "rows")}, sort_keys=True,
                                               default=str).encode()).hexdigest()[:16]
    return body


def kpi(key: str, label: str, value: Any, unit: str, text: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "unit": unit, "text": text}


# ------------------------------------------------------------------ the corporate book at its as-of

@functools.lru_cache(maxsize=1)
def book(lin_key: str = "default") -> pd.DataFrame:
    """Facility rows of the 2026Q2 corporate book joined to obligor rating, connected group, CRWA and classification."""
    from backend.dealdesk import portfolio
    fr = portfolio.frames()
    f, b = fr["facility"], fr["borrower"]
    m = f.merge(b[["borrower_id", "rating_current", "connected_group_id", "connected_group_name", "revenue_sar_mn",
                   "watchlist_flag", "restructured_flag"]], on="borrower_id", how="left")
    m["bucket"] = m["rating_current"].map(bucket)
    cr = _frame("collateral", "col_crwa")
    cr = cr[cr["book"] == "corporate"][["exposure_id", "crm_sar_mn", "risk_weight_pct", "crwa_sar_mn"]]
    m = m.merge(cr.rename(columns={"exposure_id": "facility_id"}), on="facility_id", how="left")
    return m


def book_lineage(lin: Lineage) -> None:
    lin.add("cockpit", "corp_facility_quarter", period=AS_OF_QUARTER, columns=["ead_sar_mn", "stage", "pd_pit_12m", "lgd_pct", "sector"])
    lin.add("cockpit", "corp_borrower_quarter", period=AS_OF_QUARTER, columns=["rating_current", "revenue_sar_mn"])
    lin.add("borrower_360", "rel_group_quarter", period=AS_OF_QUARTER, columns=["group_id", "group_name"])
    lin.add("collateral", "col_crwa", period="2026-06-30", columns=["crm_sar_mn", "risk_weight_pct", "crwa_sar_mn"])


# ------------------------------------------------------------------ expert assumptions (labelled, N5)

@functools.lru_cache(maxsize=1)
def _assumptions() -> dict[str, Any]:
    return json.loads((pathlib.Path(__file__).with_name("assumptions.json")).read_text())


def A(key: str, lin: Lineage | None = None) -> Any:
    """An expert assumption (backend/intel/portfolio/assumptions.json), recorded on the lineage as such."""
    row = _assumptions()["rows"][key]
    if lin is not None:
        k = "assumptions.intel_portfolio"
        cur = lin.items.get(k) or {"domain": "expert_assumptions", "relation": "intel_portfolio_assumptions",
                                   "path": "backend/intel/portfolio/assumptions.json", "period": _assumptions()["version"],
                                   "rows": None, "columns": [], "note": _assumptions()["status"]}
        if key not in cur["columns"]:
            cur["columns"].append(key)
        lin.items[k] = cur
    return row["value"]


def assumption_basis(key: str) -> str:
    return _assumptions()["rows"][key]["basis"]
