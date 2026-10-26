"""Where the branch domain lives."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]
SOURCE_LAKE = pathlib.Path(os.environ.get("BRANCH_SOURCE_LAKE") or V5 / "data" / "cockpit_v4_lake").resolve()
BRANCHES = pathlib.Path(os.environ.get("BRANCH_DATASETS") or V5 / "data" / "branches").resolve()
RELEASE = "branch-saudi-v1"
CORP_SRC = "v4-saudi-corporate-20q-v4"
RET_SRC = "v4-saudi-retail-20m-v5"
SEED = 20261011

CORPORATE_FILE = "branch_corporate_quarter.parquet"
RETAIL_FILE = "branch_retail_month.parquet"
REFERENCE_FILE = "branch_reference.parquet"
RM_FILE = "branch_rm_reference.parquet"


def release_dir() -> pathlib.Path:
    return BRANCHES / RELEASE
