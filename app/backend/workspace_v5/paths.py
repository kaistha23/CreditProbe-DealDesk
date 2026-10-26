"""Where the Workspace service reads and writes -- in one place, movable by env var.

Writes: one sqlite file (WORKSPACE_STORE, default var/workspace/workspace.sqlite).
Reads (read-only, pandas, only to quote figures in the Demo seed): the v5
corporate Early Warning release and the Cockpit corporate book it derives from.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


def store_path() -> pathlib.Path:
    """Read on every call, so a test can point the service at a temporary store."""
    return _path("WORKSPACE_STORE", V5 / "var" / "workspace" / "workspace.sqlite")


LAKE = _path("WORKSPACE_LAKE", V5 / "data" / "cockpit_v4_lake")
EWS = _path("WORKSPACE_EWS", V5 / "data" / "ews")

CORP_BOOK = "v4-saudi-corporate-20q-v4"
RETAIL_BOOK = "v4-saudi-retail-20m-v5"
EWS_RETAIL = "ews-saudi-retail-20m-v5e1"
EWS_CORP = "ews-saudi-corporate-20q-v4e2"

#: The corporate Early Warning release: one row per facility and quarter, with
#: the book's EAD/ECL and the Early Warning score, band and rule set.
EWS_CORP_EXPOSURE = EWS / EWS_CORP / "ews_corp_exposure.parquet"
#: The Cockpit corporate book's borrower table: ratings, outlook, financials.
CORP_BORROWER = LAKE / CORP_BOOK / "corp_borrower_quarter.parquet"

API_PORT = int(os.environ.get("WORKSPACE_API_PORT") or 8505)
UI_ORIGINS = [o.strip() for o in (os.environ.get("WORKSPACE_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",")
              if o.strip()]

#: Project documents (uploaded files) live beside the store.
def files_dir() -> pathlib.Path:
    return store_path().parent / "workspace_files"


__all__ = ["API_PORT", "CORP_BOOK", "RETAIL_BOOK", "EWS_RETAIL", "LAKE", "EWS", "files_dir", "CORP_BORROWER", "EWS_CORP", "EWS_CORP_EXPOSURE", "UI_ORIGINS", "V5",
           "store_path"]
