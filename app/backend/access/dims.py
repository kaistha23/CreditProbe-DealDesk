"""The attributes a data-access policy filters on, per book customer (PLAN_R5 A1).

Corporate: borrower_id -> sector, sub_sector, region, segment (relationship tier), branch_id, rm_id, business unit.
Retail:    customer_id -> region, segment (customer segment), branch_id.

Read once (lru_cache) from the books and the Branches and RMs domain, read-only. Attributes are the customer's
latest period (they do not move between periods in the books).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

V5 = Path(__file__).resolve().parents[2]
LAKE = Path(os.environ.get("ACCESS_LAKE") or V5 / "data" / "cockpit_v4_lake")
BRANCHES = Path(os.environ.get("BRANCH_DATASETS") or V5 / "data" / "branches") / "branch-saudi-v1"
CORP = "v4-saudi-corporate-20q-v4"
RET = "v4-saudi-retail-20m-v5"

#: The columns a policy can restrict, per book (policy field -> dimension column).
FIELDS = {
    "corporate": {"sectors": "sector", "sub_sectors": "sub_sector", "regions": "region", "branches": "branch_id",
                  "rm_ids": "rm_id", "segments": "segment", "business_units": "business_unit"},
    "retail": {"regions": "region", "branches": "branch_id", "segments": "segment"},
}
KEY = {"corporate": "borrower_id", "retail": "customer_id"}


@lru_cache(maxsize=1)
def corporate() -> pd.DataFrame:
    b = pd.read_parquet(LAKE / CORP / "corp_borrower_quarter.parquet",
                        columns=["borrower_id", "borrower_name", "reporting_quarter", "sector", "sub_sector", "region",
                                 "relationship_tier"])
    b = b.sort_values("reporting_quarter").drop_duplicates("borrower_id", keep="last")
    br = pd.read_parquet(BRANCHES / "branch_corporate_quarter.parquet",
                         columns=["borrower_id", "reporting_quarter", "branch_id", "branch_name", "business_unit",
                                  "rm_id", "rm_name"])
    br = br.sort_values("reporting_quarter").drop_duplicates("borrower_id", keep="last").drop(columns="reporting_quarter")
    out = b.drop(columns="reporting_quarter").merge(br, on="borrower_id", how="left")
    out = out.rename(columns={"relationship_tier": "segment"})
    return out.set_index("borrower_id", drop=False)


@lru_cache(maxsize=1)
def retail() -> pd.DataFrame:
    c = pd.read_parquet(LAKE / RET / "retail_customer_month.parquet",
                        columns=["customer_id", "reporting_month", "customer_segment", "region"])
    c = c.sort_values("reporting_month").drop_duplicates("customer_id", keep="last")
    br = pd.read_parquet(BRANCHES / "branch_retail_month.parquet",
                         columns=["customer_id", "reporting_month", "branch_id", "branch_name"])
    br = br.sort_values("reporting_month").drop_duplicates("customer_id", keep="last").drop(columns="reporting_month")
    out = c.drop(columns="reporting_month").merge(br, on="customer_id", how="left")
    out = out.rename(columns={"customer_segment": "segment"})
    return out.set_index("customer_id", drop=False)


def frame(book: str) -> pd.DataFrame:
    return corporate() if book == "corporate" else retail()


def book_of(owner_id: str) -> str | None:
    s = str(owner_id or "")
    if s.startswith("CB") or s.startswith("CF") or s.startswith("CG"):
        return "corporate"
    if s.startswith("RC") or s.startswith("RA"):
        return "retail"
    return None


@lru_cache(maxsize=1)
def facility_owner() -> dict[str, str]:
    """facility_id -> borrower_id (a facility row is allowed when its borrower is)."""
    f = pd.read_parquet(LAKE / CORP / "corp_facility_quarter.parquet", columns=["facility_id", "borrower_id"])
    return dict(zip(f["facility_id"], f["borrower_id"]))


@lru_cache(maxsize=1)
def group_members() -> dict[str, set[str]]:
    g = pd.read_parquet(LAKE / CORP / "corp_borrower_quarter.parquet", columns=["borrower_id", "group_id"]).dropna()
    out: dict[str, set[str]] = {}
    for gid, bid in zip(g["group_id"], g["borrower_id"]):
        out.setdefault(str(gid), set()).add(str(bid))
    return out


def options() -> dict[str, dict[str, list[str]]]:
    """Every value a policy can pick, per book and field (for the policy editor)."""
    out: dict[str, dict[str, list[str]]] = {}
    for book, fields in FIELDS.items():
        df = frame(book)
        out[book] = {f: sorted(str(v) for v in df[col].dropna().unique()) for f, col in fields.items()}
    return out
