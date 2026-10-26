"""Where the Early Warning service reads, writes and listens -- in one place.

Every location is under the v5 checkout by default and can be moved with an
environment variable; nothing points at /tmp. The builder is the ONLY module
that opens the Cockpit lake (read-only, to derive the EWS releases); the
reader and the API only ever open the EWS releases under DATASETS.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


#: The Cockpit books the EWS releases are derived from (opened read-only).
SOURCE_LAKE = _path("EWS_SOURCE_LAKE", V5 / "data" / "cockpit_v4_lake")
#: The EWS service's own releases.
DATASETS = _path("EWS_DATASETS", V5 / "data" / "ews")
#: Build and test evidence.
EVIDENCE = _path("EWS_EVIDENCE", V5 / "evidence" / "v5" / "ews")
EVIDENCE.mkdir(parents=True, exist_ok=True)
#: Saved cohorts (the population handed to Borrower 360 / What-If).
STORE = _path("EWS_STORE", V5 / "var" / "ews" / "ews_store.sqlite")

CORP_SRC = "v4-saudi-corporate-20q-v4"
RET_SRC = "v4-saudi-retail-20m-v5"
#: v4e2: rebuilt from the v5 corporate book (amounts x0.01; see
#: docs/v5/RESCALE.md). v4e1 was built from the unscaled Round H book.
EWS_CORP = "ews-saudi-corporate-20q-v4e2"
#: Retail is unchanged by v5, so its EWS release keeps its id.
EWS_RET = "ews-saudi-retail-20m-v5e1"

API_PORT = int(os.environ.get("EWS_API_PORT") or 8501)
UI_ORIGINS = [o.strip() for o in (os.environ.get("EWS_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",")
              if o.strip()]

__all__ = ["API_PORT", "CORP_SRC", "DATASETS", "EVIDENCE", "EWS_CORP", "EWS_RET",
           "RET_SRC", "SOURCE_LAKE", "STORE", "UI_ORIGINS", "V5"]
