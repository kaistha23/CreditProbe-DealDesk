"""The one door Session C's code reads and writes data through (PLAN_R12 §0, N5).

`read(relation, columns=None, **filters)` returns a DataFrame of a relation registered in Data Domains, through
Session E's shared reader `backend.dealdesk.data.store.dd_frame` (contract: docs/v5/R12_DATA_CONTRACT.md). Nothing
else is opened. Every read is recorded (`used()`), so each API response carries its lineage: the domain, relation and
filters (row keys) behind every block.

A relation that is registered but not populated yet reads as an empty frame; one that is not registered at all is
listed in `missing()`. Every caller degrades to "not provided" rather than failing. A filter on a column the relation
does not carry matches no row.

`publish(relation, rows)` writes C's decisions (dd_review_finding, dd_swot) through E's versioned publisher.
"""
from __future__ import annotations

import functools
import threading
from typing import Any

import pandas as pd

_LOCAL = threading.local()


def _log() -> dict[str, dict[str, Any]]:
    if not hasattr(_LOCAL, "log"):
        _LOCAL.log = {}
    return _LOCAL.log


def reset() -> None:
    """Start a fresh lineage log (one per API call)."""
    _LOCAL.log = {}


def used() -> list[dict[str, Any]]:
    return [dict(v, relation=k) for k, v in sorted(_log().items())]


def missing() -> list[str]:
    return sorted(k for k, v in _log().items() if not v.get("available"))


@functools.lru_cache(maxsize=1)
def _registry() -> dict[str, dict[str, Any]]:
    """relation id -> {domain, path} from the Data Builder registry."""
    from backend.data_builder.registry import DOMAINS
    out: dict[str, dict[str, Any]] = {}
    for dom, d in DOMAINS.items():
        for rid, spec in (d.get("relations") or {}).items():
            out[rid] = {"domain": dom, "path": spec["path"], "period_column": spec.get("period_column")}
    return out


def locate(relation: str) -> dict[str, Any] | None:
    """Where a relation is registered: {domain, path}; None when Data Domains does not know it."""
    return _registry().get(relation)


def registered(relation: str) -> bool:
    return relation in _registry()


def _published(relation: str) -> bool:
    try:
        from backend.dealdesk.data import store
        return store.relation_path(relation).exists()
    except Exception:  # noqa: BLE001
        return False


def available(relation: str) -> bool:
    return registered(relation) and _published(relation)


def _record(relation: str, filters: dict[str, Any], n: int, ok: bool, domain: str | None, via: str) -> None:
    log = _log()
    e = log.setdefault(relation, {"domain": domain, "available": ok, "via": via, "rows": 0, "filters": []})
    e["rows"] += n
    e["available"] = e["available"] or ok
    f = {k: (v if not isinstance(v, (list, tuple, set)) else sorted(map(str, v))[:20]) for k, v in filters.items()}
    if f and f not in e["filters"] and len(e["filters"]) < 12:
        e["filters"].append(f)


def read(relation: str, columns: list[str] | None = None, **filters: Any) -> pd.DataFrame:
    """Rows of a registered relation, filtered by equality (scalar) or membership (list) on its columns."""
    from backend.dealdesk.data import store
    dom = (locate(relation) or {}).get("domain")
    via = "backend.dealdesk.data.dd_frame"
    for v in filters.values():
        if isinstance(v, (list, tuple, set)) and not [x for x in v if x is not None]:
            _record(relation, filters, 0, registered(relation), dom, via)
            return pd.DataFrame(columns=columns or [])
    if not registered(relation):
        _record(relation, filters, 0, False, None, "not registered in Data Domains")
        return pd.DataFrame(columns=columns or [])
    try:
        d = store.dd_frame(relation, **filters)
    except KeyError as e:
        if any(f"column {k!r}" in str(e) for k in filters):  # no row can match a filter on a column it lacks
            d = store.dd_frame(relation).iloc[0:0]
        else:
            _record(relation, filters, 0, False, dom, "not published yet")
            return pd.DataFrame(columns=columns or [])
    except FileNotFoundError:
        _record(relation, filters, 0, False, dom, "not published yet")
        return pd.DataFrame(columns=columns or [])
    if columns:
        d = d[[c for c in columns if c in d.columns]]
    _record(relation, filters, len(d), True, dom, via)
    return d.reset_index(drop=True)


def records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    from backend.b360.store import clean
    return [clean(r) for r in frame.astype(object).where(frame.notna(), None).to_dict("records")]


def pick(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    """The first present, non-null column among `names`."""
    for n in names:
        v = row.get(n)
        if v is not None and not (isinstance(v, float) and v != v):
            return v
    return default


def publish(relation: str, rows: list[dict[str, Any]], mode: str = "upsert") -> dict[str, Any]:
    """Publish decisions back to Data Domains through E's publisher (versioned, manifest updated), as actor C."""
    from backend.dealdesk.data import store
    res = store.publish(relation, rows, mode=mode, actor="C")
    out = {"published": True, "relation": relation, "rows": len(rows)}
    if isinstance(res, dict):
        out.update({k: v for k, v in res.items() if k not in out})
    return out
