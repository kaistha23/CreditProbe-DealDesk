"""The one door through which the bank-form papers read data (PLAN_R12 §0, N5).

    rows = read("dd_project", proposal_id="DD-31")      # list of dicts, each with "_src" (lineage), [] when empty
    status("dd_project")                                  # "live" | "empty" | "missing"

Order of reading:
  1. a test or preview override (`use({...})`), relation -> rows;
  2. Session E's shared reader `backend.dealdesk.data.dd_read(relation, **filters)` (every registered relation, the R11 seven included).

Nothing else is ever opened (no side door): a relation that is not registered is "missing" and its section says "not available".
Every row carries `_src` = {"domain", "relation", "row", "period"} so each figure in a paper traces to its relation and row.
"""
from __future__ import annotations

import contextlib
import types
from typing import Any, Iterator


_LOCAL = types.SimpleNamespace(override=None)  # process-wide: the API's worker threads see a test override too
PERIOD_COLS = ("reporting_quarter", "period", "as_of", "month", "year")
KEY_COLS = ("proposal_id", "line_id", "limit_id", "item_id", "condition_id", "finding_id", "project_id", "entity_id", "bank",
            "holder", "person", "month", "year", "kind", "view")

#: the domain each relation family belongs to (for the lineage label)
DOMAINS = (("b360_", "Borrower 360"), ("rel_", "Borrower 360"), ("bureau_", "Bureau"), ("other_bank", "Bureau"),
           ("dep_", "Deposits"), ("col_", "Collateral and registers"), ("dd_", "Deal Desk"))


def domain_of(relation: str) -> str:
    return next((d for p, d in DOMAINS if relation.startswith(p)), "Data Domains")


@contextlib.contextmanager
def use(tables: dict[str, list[dict[str, Any]]]) -> Iterator[None]:
    """Read from these rows instead of Data Domains (tests and the preview of an unsaved deal)."""
    prev = getattr(_LOCAL, "override", None)
    _LOCAL.override = tables
    try:
        yield
    finally:
        _LOCAL.override = prev


def _shared_reader():
    try:
        from backend.dealdesk import data as ddata  # Session E (R12 SCHEMA READY)
    except Exception:  # noqa: BLE001 - before E's merge the shared reader does not exist yet
        return None
    return getattr(ddata, "dd_read", None)


def _records(obj: Any) -> list[dict[str, Any]] | None:
    if obj is None:
        return None
    if hasattr(obj, "to_dict"):
        try:
            return [dict(r) for r in obj.to_dict(orient="records")]
        except TypeError:
            pass
    if isinstance(obj, dict) and "rows" in obj:
        return list(obj["rows"])
    return [dict(r) for r in obj]


def _clean(v: Any) -> Any:
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:  # noqa: BLE001
        pass
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            return v
    if hasattr(v, "isoformat") and not isinstance(v, str):
        return v.isoformat()[:10]
    return v


def _tag(relation: str, rows: list[dict[str, Any]], via: str) -> list[dict[str, Any]]:
    out = []
    for i, r in enumerate(rows):
        r = {k: _clean(v) for k, v in r.items()}
        key = " · ".join(f"{k}={r[k]}" for k in KEY_COLS if r.get(k) not in (None, ""))[:120] or f"row {i + 1}"
        period = next((str(r[c]) for c in PERIOD_COLS if r.get(c) not in (None, "")), "")
        r["_src"] = {"domain": domain_of(relation), "relation": relation, "row": key, "period": period, "via": via}
        out.append(r)
    return out


def _match(r: dict[str, Any], filters: dict[str, Any]) -> bool:
    for k, v in filters.items():
        if v is None:
            continue
        rv = r.get(k)
        if isinstance(v, (list, tuple, set)):
            if rv not in v:
                return False
        elif rv != v:
            return False
    return True


def read(relation: str, **filters: Any) -> list[dict[str, Any]]:
    """Rows of a registered relation matching the filters (equality; a list means 'one of'); [] when missing or empty."""
    rows, _ = _read(relation, filters)
    return rows


_COLS: dict[str, set[str] | None] = {}


def _columns(relation: str) -> set[str] | None:
    """The relation's column names from its parquet schema (cheap), None when unknown."""
    if relation not in _COLS:
        try:
            import pyarrow.parquet as pq

            from backend.dealdesk.data import store
            _COLS[relation] = set(pq.read_schema(store.relation_path(relation)).names)
        except Exception:  # noqa: BLE001
            _COLS[relation] = None
    return _COLS[relation]


def _read(relation: str, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    ov = getattr(_LOCAL, "override", None)
    if ov is not None:
        if relation not in ov:
            return [], "missing"
        rows = [r for r in ov[relation] if _match(r, filters)]
        return _tag(relation, rows, "override"), ("live" if ov[relation] else "empty")
    fn = _shared_reader()
    if fn is not None:
        cols = _columns(relation)
        if cols is not None and any(k not in cols for k, v in filters.items() if v is not None):
            return [], "empty"  # the relation has no such key: nothing of this deal in it (never read it whole)
        got = None
        simple = {k: (list(v) if isinstance(v, (tuple, set)) else v) for k, v in filters.items() if v is not None}
        for call in ((lambda: fn(relation, **simple)), (lambda: fn(relation))):
            try:
                got = _records(call())
                break
            except Exception:  # noqa: BLE001 - a filter column the relation lacks, or not registered: try unfiltered, then fall through
                got = None
        if got is not None:
            got = [r for r in got if _match(r, filters)]
            return _tag(relation, got, "dd_read"), ("live" if got else "empty")
    return [], "missing"


def status(relation: str, **filters: Any) -> str:
    return _read(relation, filters)[1]


def label(src: dict[str, Any] | None) -> str:
    """'Deal Desk · dd_project · project_id=P1 · 2026Q3' — the lineage line under a table or in the sources annex."""
    if not src:
        return ""
    return " · ".join(x for x in (src.get("domain"), src.get("relation"), src.get("row"), src.get("period")) if x)


def first(r: dict[str, Any] | None, *cols: str, default: Any = None) -> Any:
    """The first non-empty of several column names (the contract's name first, then the plan's)."""
    if not r:
        return default
    for c in cols:
        v = r.get(c)
        if v not in (None, ""):
            return v
    return default
