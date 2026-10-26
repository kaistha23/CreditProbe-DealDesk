"""Where the relationship domain lives."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]
SOURCE_LAKE = pathlib.Path(os.environ.get("REL_SOURCE_LAKE") or V5 / "data" / "cockpit_v4_lake").resolve()
RELATIONSHIPS = pathlib.Path(os.environ.get("REL_DATASETS") or V5 / "data" / "relationships").resolve()
RELEASE = "rel-saudi-v1"
CORP_SRC = "v4-saudi-corporate-20q-v4"
RET_SRC = "v4-saudi-retail-20m-v5"
SEED = 20261011
CP_LIMIT_FILE = V5 / "backend" / "cockpit_v4" / "credit_policy.json"
