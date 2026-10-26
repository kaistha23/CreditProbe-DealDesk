"""Where Borrower 360 reads -- in one place, every location movable by env var.

Borrower 360 opens parquet files read-only and never writes. It reads three
families of release:

  books     the v5 Cockpit lake (corporate quarterly, retail monthly);
  ews       the Early Warning releases derived from those books (score, band
            and the rules fired, rule set gw-ews-1.3.0);
  external  the synthetic Bureau and Open Banking domains keyed to the books.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


LAKE = _path("B360_LAKE", V5 / "data" / "cockpit_v4_lake")
EWS = _path("B360_EWS", V5 / "data" / "ews")
EXTERNAL = _path("B360_EXTERNAL", V5 / "data" / "external")

CORP_BOOK = "v4-saudi-corporate-20q-v4"
RET_BOOK = "v4-saudi-retail-20m-v5"
EWS_CORP = "ews-saudi-corporate-20q-v4e2"
EWS_RET = "ews-saudi-retail-20m-v5e1"
BUREAU = "bureau-saudi-v1"
OPEN_BANKING = "open-banking-saudi-v1"
RELATIONSHIPS_DIR = _path("B360_RELATIONSHIPS", V5 / "data" / "relationships")
RELATIONSHIPS = "rel-saudi-v1"

#: Every relation Borrower 360 reads, by the name it is queried under.
RELATIONS: dict[str, pathlib.Path] = {
    "corp_borrower": LAKE / CORP_BOOK / "corp_borrower_quarter.parquet",
    "corp_facility": LAKE / CORP_BOOK / "corp_facility_quarter.parquet",
    "corp_collateral": LAKE / CORP_BOOK / "corp_collateral_quarter.parquet",
    "corp_covenant": LAKE / CORP_BOOK / "corp_covenant_quarter.parquet",
    "ret_customer": LAKE / RET_BOOK / "retail_customer_month.parquet",
    "ret_account": LAKE / RET_BOOK / "retail_account_month.parquet",
    "ret_behaviour": LAKE / RET_BOOK / "retail_behaviour_month.parquet",
    "ret_collateral": LAKE / RET_BOOK / "retail_collateral_month.parquet",
    "ews_corp": EWS / EWS_CORP / "ews_corp_exposure.parquet",
    "ews_ret": EWS / EWS_RET / "ews_retail_exposure.parquet",
    "bureau_corp": EXTERNAL / BUREAU / "bureau_corp_quarter.parquet",
    "bureau_ret": EXTERNAL / BUREAU / "bureau_retail_month.parquet",
    "ob_corp": EXTERNAL / OPEN_BANKING / "openbanking_corp_quarter.parquet",
    "ob_ret": EXTERNAL / OPEN_BANKING / "openbanking_retail_month.parquet",
    "rel_group": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_group_quarter.parquet",
    "rel_edge": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_edge_quarter.parquet",
    "rel_person": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_person_role.parquet",
    "rel_shared": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_shared_collateral.parquet",
    "rel_household": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_household_month.parquet",
    "rel_employer": RELATIONSHIPS_DIR / RELATIONSHIPS / "rel_employer_month.parquet",
}

#: R16 d: fictional demo customers (data/dealdesk/demo_customers/bank_b360/<relation>.parquet, same columns as the book),
#: unioned into Borrower 360's own views by store.conn(); B360_OVERLAY=off hides them. Nothing else reads these files.
OVERLAY = None if os.environ.get("B360_OVERLAY", "").lower() in ("off", "0", "none") else _path(
    "B360_OVERLAY", V5 / "data" / "dealdesk" / "demo_customers" / "bank_b360")

MANIFESTS: dict[str, pathlib.Path] = {
    "bureau": EXTERNAL / BUREAU / "manifest.json",
    "open_banking": EXTERNAL / OPEN_BANKING / "manifest.json",
    "relationships": RELATIONSHIPS_DIR / RELATIONSHIPS / "manifest.json",
}

API_PORT = int(os.environ.get("B360_API_PORT") or 8502)
UI_ORIGINS = [o.strip() for o in (os.environ.get("B360_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",")
              if o.strip()]

__all__ = ["API_PORT", "BUREAU", "CORP_BOOK", "RELATIONSHIPS", "EWS_CORP", "EWS_RET", "MANIFESTS", "OPEN_BANKING",
           "RELATIONS", "RET_BOOK", "UI_ORIGINS", "V5"]
