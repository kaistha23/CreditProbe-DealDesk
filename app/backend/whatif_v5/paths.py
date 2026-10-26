"""Where the What-If service reads, writes and listens -- in one place.

Every location is under the v5 checkout by default and can be moved with an
environment variable. The books and the Early Warning store are opened
read-only; the only file this service writes is its own run register.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


#: The v5 books (opened read-only).
LAKE = _path("WHATIF_LAKE", V5 / "data" / "cockpit_v4_lake")
CORP_RELEASE = "v4-saudi-corporate-20q-v4"
RETAIL_RELEASE = "v4-saudi-retail-20m-v5"

#: The Early Warning store, where exported cohorts are frozen (read-only here).
def ews_store() -> pathlib.Path:
    return _path("EWS_STORE", V5 / "var" / "ews" / "ews_store.sqlite")


#: What-If's own register of runs, so an export link survives a restart.
def run_store() -> pathlib.Path:
    return _path("WHATIF_STORE", V5 / "var" / "whatif" / "whatif_runs.sqlite")


#: The Early Warning API, used only as a fallback when the store is unreadable.
EWS_API = (os.environ.get("NEXT_PUBLIC_EWS_API") or os.environ.get("EWS_API")
           or "http://127.0.0.1:8501").rstrip("/")

API_PORT = int(os.environ.get("WHATIF_API_PORT") or 8503)
UI_ORIGINS = [o.strip() for o in (os.environ.get("WHATIF_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",")
              if o.strip()]

__all__ = ["API_PORT", "CORP_RELEASE", "EWS_API", "LAKE", "RETAIL_RELEASE", "UI_ORIGINS", "V5",
           "ews_store", "run_store"]
