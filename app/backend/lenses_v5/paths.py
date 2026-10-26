"""Where the Lenses service reads, writes and listens -- in one place.

Reads (read-only): the Early Warning releases (data/ews), the Cockpit lake (data/cockpit_v4_lake) for the
borrower financials, the Scorecard domain and the Deal Desk domain. Writes only its own store
(var/lenses_v5/lenses.sqlite) and the convo store (var/convo/lenses.sqlite).
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


SCORECARD_DOMAIN = _path("LENSES_SCORECARD_DOMAIN", V5 / "data" / "scorecard_v5" / "scorecard-saudi-v1")
DEALDESK_DOMAIN = _path("LENSES_DEALDESK_DOMAIN", V5 / "data" / "dealdesk" / "dd-saudi-v1")


def store_path() -> pathlib.Path:
    return _path("LENSES_STORE", V5 / "var" / "lenses_v5" / "lenses.sqlite")


def engine_path() -> pathlib.Path:
    return _path("LENSES_ENGINE_DB", V5 / "var" / "lenses_v5" / "engine.duckdb")


def convo_store_path() -> pathlib.Path:
    return _path("LENSES_CONVO_STORE", V5 / "var" / "convo" / "lenses.sqlite")


API_PORT = int(os.environ.get("LENSES_API_PORT") or 8509)
UI_ORIGINS = [o.strip() for o in (os.environ.get("LENSES_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
