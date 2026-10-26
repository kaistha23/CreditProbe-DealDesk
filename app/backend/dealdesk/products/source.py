"""PLAN_R12 Session P: where the product analytics read their facts and publish their results.

Every fact comes from a relation registered in Data Domains, read through Session E's shared reader
`backend.dealdesk.data` (`dd_read`, `trace`, `publish`; contract `docs/v5/R12_DATA_CONTRACT.md`). This module is
the only place in `products/**` that touches the reader, so the analytics stay pure functions over rows, and each
row keeps its lineage (domain, relation, row key, period, version) all the way to the screen.

Tests serve their own rows with `override()` (nothing is read from a private file: no side door).
"""
from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Iterator
from typing import Any

#: the relations P reads (all registered by Session E)
RELATIONS = ("dd_project", "dd_project_cashflow", "dd_escrow_account", "dd_escrow", "dd_syndication", "dd_sme_application",
             "dd_facility_limit", "bureau_entity_report", "dd_deal", "dd_parameter")

#: row keys for lineage when the reader is not in play (tests); the reader's own keys win otherwise
KEYS: dict[str, tuple[str, ...]] = {
    "dd_project": ("project_id",), "dd_project_cashflow": ("project_id", "scenario", "month_no"),
    "dd_escrow_account": ("escrow_id",), "dd_escrow": ("escrow_id", "month"), "dd_syndication": ("proposal_id",),
    "dd_sme_application": ("proposal_id",), "dd_facility_limit": ("proposal_id", "limit_id"),
    "bureau_entity_report": ("report_id",), "dd_deal": ("proposal_id",), "dd_parameter": ("table_name", "param_key"),
}
DOMAINS = {"bureau_entity_report": "Bureau"}

_override: dict[str, list[dict[str, Any]]] | None = None


@contextlib.contextmanager
def override(rows: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
    """Tests: serve these rows instead of the reader (relations not given read as empty)."""
    global _override
    prev, _override = _override, rows
    try:
        yield
    finally:
        _override = prev


def _data() -> Any:
    try:
        from backend.dealdesk import data as dd_data  # Session E
        return dd_data
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    return _override is not None or _data() is not None


def _clean(v: Any) -> Any:
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return _clean(v.item())
        except (ValueError, AttributeError):
            return v
    return v


def read(relation: str, **filters: Any) -> list[dict[str, Any]]:
    """Rows of a registered relation, filtered by equality (None filters are dropped), NaN as None."""
    filters = {k: v for k, v in filters.items() if v is not None}
    if _override is not None:
        rows = [dict(r) for r in _override.get(relation, [])]
        return [{k: _clean(v) for k, v in r.items()} for r in rows
                if all(str(r.get(k)) == str(v) for k, v in filters.items())]
    d = _data()
    if d is None:
        return []
    try:
        return [{k: _clean(v) for k, v in r.items()} for r in d.dd_read(relation, **filters)]
    except (KeyError, FileNotFoundError, ValueError):
        return []


def src(relation: str, row: dict[str, Any], column: str | None = None) -> dict[str, Any]:
    """Lineage of one figure: domain, relation, row key, period, version and column (PLAN_R12 §0 rule 3)."""
    out: dict[str, Any] | None = None
    if _override is None and (d := _data()) is not None:
        try:
            out = dict(d.trace(relation, row))
        except Exception:  # noqa: BLE001
            out = None
    if out is None:
        out = {"domain": DOMAINS.get(relation, "Deal Desk"), "relation": relation,
               "key": {k: row.get(k) for k in KEYS.get(relation, ()) if row.get(k) is not None},
               "period": row.get("reporting_quarter") or row.get("month"), "version": row.get("rel_version")}
    if column:
        out["column"] = column
    return out


def derived(*sources: dict[str, Any], method: str) -> dict[str, Any]:
    """Lineage of a computed figure: the relations it is computed from and how."""
    rels = sorted({r for s in sources for r in ([s["relation"]] if isinstance(s.get("relation"), str) else s.get("relation") or [])})
    return {"domain": "Deal Desk", "relation": rels[0] if len(rels) == 1 else rels, "derived": method,
            "inputs": [{k: s[k] for k in ("relation", "key", "column") if k in s} for s in sources[:12]]}


def publish(relation: str, rows: list[dict[str, Any]], actor: str = "P") -> dict[str, Any]:
    """Publish result rows (upsert) through E's publisher; never raises (an answer is not lost to a failed write)."""
    if _override is not None:
        return {"published": False, "relation": relation, "reason": "test rows are not published"}
    d = _data()
    fn: Callable[..., Any] | None = getattr(d, "publish", None) if d is not None else None
    if fn is None:
        return {"published": False, "relation": relation, "reason": "publisher not available"}
    try:
        res = fn(relation, rows, mode="upsert", actor=actor)
    except Exception as e:  # noqa: BLE001
        return {"published": False, "relation": relation, "reason": f"publisher refused: {type(e).__name__}: {e}"[:200]}
    return {"published": True, "relation": relation, "rows": len(rows), "version": (res or {}).get("version")}
