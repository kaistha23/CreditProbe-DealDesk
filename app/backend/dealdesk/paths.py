"""Where Deal Desk reads, writes and listens -- in one place.

The corporate book and the What-If model are opened read-only. The only files this
service writes are under var/dealdesk (traces, parameter edits, user proposals).
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


#: The committed domain: proposals, memos, seeded parameter tables, manifest.
DATA = _path("DEALDESK_DATA", V5 / "data" / "dealdesk")
#: Runtime store (git-ignored).
VAR = _path("DEALDESK_VAR", V5 / "var" / "dealdesk")
#: The v5 corporate book (read-only).
LAKE = _path("DEALDESK_LAKE", V5 / "data" / "cockpit_v4_lake")
CORP_RELEASE = "v4-saudi-corporate-20q-v4"
AS_OF = "2026Q2"

API_PORT = int(os.environ.get("DEALDESK_API_PORT") or 8508)
UI_ORIGINS = [o.strip() for o in (os.environ.get("DEALDESK_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]


def params_dir() -> pathlib.Path:
    return DATA / "params"


def store_path() -> pathlib.Path:
    VAR.mkdir(parents=True, exist_ok=True)
    return VAR / "dealdesk.sqlite"


def book_relation(name: str) -> pathlib.Path:
    return LAKE / CORP_RELEASE / f"{name}.parquet"
