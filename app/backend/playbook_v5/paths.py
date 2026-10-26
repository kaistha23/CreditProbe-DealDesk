"""Where the Playbook and Policy Docs service reads and writes, in one place, movable by env var.

Writes: one sqlite file (PLAYBOOK_STORE, default var/playbook/playbook.sqlite), its files beside it, and the
active policy pack the Cockpit reads (POLICY_ACTIVE_PACK, default var/policy/active_pack.json; FX-7).
Reads (read-only): the Cockpit books and the Early Warning release, to quote figures; the Cockpit's default
policy pack (backend/cockpit_v4/credit_policy.json), which is the first version of the pack.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


def store_path() -> pathlib.Path:
    """Read on every call, so a test can point the service at a temporary store."""
    return _path("PLAYBOOK_STORE", V5 / "var" / "playbook" / "playbook.sqlite")


def files_dir() -> pathlib.Path:
    return store_path().parent / (store_path().stem + "_files")


def active_pack_path() -> pathlib.Path:
    """The active versioned policy pack, written on every pack change. ops/v5.sh points the Cockpit at it."""
    return _path("POLICY_ACTIVE_PACK", V5 / "var" / "policy" / "active_pack.json")


DEFAULT_PACK = V5 / "backend" / "cockpit_v4" / "credit_policy.json"
LAKE = _path("PLAYBOOK_LAKE", V5 / "data" / "cockpit_v4_lake")
EWS = _path("PLAYBOOK_EWS", V5 / "data" / "ews")
CORP_BOOK = "v4-saudi-corporate-20q-v4"
RETAIL_BOOK = "v4-saudi-retail-20m-v5"
EWS_CORP = "ews-saudi-corporate-20q-v4e2"

API_PORT = int(os.environ.get("PLAYBOOK_API_PORT") or 8506)
UI_ORIGINS = [o.strip() for o in (os.environ.get("PLAYBOOK_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]

#: The other v5 services Playbook imports from (server side, forwarding the caller's cookie).
SERVICES = {
    "core": os.environ.get("CORE_API_ORIGIN") or "http://127.0.0.1:8505",
    "cockpit": os.environ.get("COCKPIT_API_ORIGIN") or "http://127.0.0.1:8500",
    "ews": os.environ.get("EWS_API_ORIGIN") or "http://127.0.0.1:8501",
    "b360": os.environ.get("B360_API_ORIGIN") or "http://127.0.0.1:8502",
    "whatif": os.environ.get("WHATIF_API_ORIGIN") or "http://127.0.0.1:8503",
    "data": os.environ.get("DATA_BUILDER_API_ORIGIN") or "http://127.0.0.1:8504",
    "scorecard": os.environ.get("SCORECARD_API_ORIGIN") or "http://127.0.0.1:8507",
    "dealdesk": os.environ.get("DEALDESK_API_ORIGIN") or "http://127.0.0.1:8508",
    "lenses": os.environ.get("LENSES_API_ORIGIN") or "http://127.0.0.1:8509",
}
