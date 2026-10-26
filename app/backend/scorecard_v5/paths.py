"""Where the Scorecard Validation service reads, writes and listens -- in one place.

The domain (data/scorecard_v5) is read-only at run time; the books and the Bureau and Open Banking
domains are opened read-only when the domain is built. The only file the service writes is its own
store (var/scorecard_v5/scorecard.sqlite).
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


RELEASE = "scorecard-saudi-v1"
DOMAIN = _path("SCORECARD_DOMAIN", V5 / "data" / "scorecard_v5" / RELEASE)
LAKE = _path("SCORECARD_LAKE", V5 / "data" / "cockpit_v4_lake")
EXTERNAL = _path("SCORECARD_EXTERNAL", V5 / "data" / "external")
CORP_RELEASE = "v4-saudi-corporate-20q-v4"
RETAIL_RELEASE = "v4-saudi-retail-20m-v5"
BUREAU = "bureau-saudi-v1"
OPEN_BANKING = "open-banking-saudi-v1"


def store_path() -> pathlib.Path:
    return _path("SCORECARD_STORE", V5 / "var" / "scorecard_v5" / "scorecard.sqlite")


API_PORT = int(os.environ.get("SCORECARD_API_PORT") or 8507)
UI_ORIGINS = [o.strip() for o in (os.environ.get("SCORECARD_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
