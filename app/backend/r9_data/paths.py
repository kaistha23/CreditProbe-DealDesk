"""Where the R9 shared data domains live (PLAN_R9 Session A)."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]
ROOT = pathlib.Path(os.environ.get("R9_DATASETS") or V5 / "data" / "r9_data").resolve()
RELEASE = "r9-saudi-v1"
SEED = 20261013
REL_DIR = V5 / "data" / "relationships" / "rel-saudi-v1"
EWS_CORP = V5 / "data" / "ews" / "ews-saudi-corporate-20q-v4e2" / "ews_corp_exposure.parquet"
EWS_RET = V5 / "data" / "ews" / "ews-saudi-retail-20m-v5e1" / "ews_retail_exposure.parquet"
CRM_JSON = V5 / "backend" / "playbook_v5" / "data" / "cbuae_crm.json"

#: domain id -> its tables (one parquet file each)
DOMAIN_TABLES: dict[str, list[str]] = {
    "deposits": ["dep_account", "dep_month", "dep_counterparty", "dep_derived"],
    "origination": ["orig_facility"],
    "classification": ["cls_exposure", "cls_reason"],
    "collateral": ["col_item", "col_guarantee", "col_restructured", "col_related_party", "col_large_exposure",
                   "col_crwa"],
    "relationships": ["rel_node", "rel_link"],
    "ecl_runs": ["ecl_facility", "ecl_anomaly"],
}

#: The two ECL runs: the current (Q3 cycle) run is the books at their as-of; the prior run the period before.
RUN_CURRENT = "2026Q3"
RUN_PRIOR = "2026Q2"


def release_dir() -> pathlib.Path:
    return ROOT / RELEASE
