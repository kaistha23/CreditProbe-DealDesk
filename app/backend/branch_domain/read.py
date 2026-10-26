"""Read API of the branch domain.

    from backend.branch_domain.read import branches
    branches("corporate", period="2026Q2")   # DataFrame: borrower_id, reporting_quarter, region, branch_id,
                                             #   branch_name, business_unit, rm_id, rm_name
    branches("retail", period="2026-08")     # DataFrame: customer_id, reporting_month, region, branch_id, branch_name
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from backend.branch_domain.paths import CORPORATE_FILE, REFERENCE_FILE, RETAIL_FILE, RM_FILE, release_dir

FILES = {"corporate": CORPORATE_FILE, "retail": RETAIL_FILE}
PERIOD = {"corporate": "reporting_quarter", "retail": "reporting_month"}
KEY = {"corporate": "borrower_id", "retail": "customer_id"}


def path(domain_id: str) -> str:
    """The parquet file of a book's branch relation (for DuckDB / pandas readers)."""
    return str(release_dir() / FILES[domain_id])


@lru_cache(maxsize=4)
def _frame(domain_id: str) -> pd.DataFrame:
    return pd.read_parquet(path(domain_id)).drop(columns=["tenant_id"])


def branches(domain_id: str, period: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    """Branch (and for corporate business unit and RM) per customer and period; filter by period and ids."""
    f = _frame(domain_id)
    if period:
        f = f[f[PERIOD[domain_id]] == period]
    if ids is not None:
        f = f[f[KEY[domain_id]].isin(ids)]
    return f.reset_index(drop=True)


def reference() -> pd.DataFrame:
    return pd.read_parquet(release_dir() / REFERENCE_FILE)


def rm_reference() -> pd.DataFrame:
    return pd.read_parquet(release_dir() / RM_FILE)
