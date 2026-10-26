"""R12 Session E: the Deal Desk data layer — every fact read from, and every decision published to, Data Domains.

    from backend.dealdesk.data import dd_read, dd_frame, publish, trace, schema

Contract: docs/v5/R12_DATA_CONTRACT.md (generated from schema.py). Imports are lazy so the Data Builder
registry can import `backend.dealdesk.data.schema` without pulling in pandas.
"""
from __future__ import annotations

from typing import Any

__all__ = ["dd_read", "dd_frame", "publish", "trace", "conform", "empty", "relation_path", "SchemaError"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from backend.dealdesk.data import store
        return getattr(store, name)
    raise AttributeError(name)
