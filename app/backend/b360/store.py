"""Read-only DuckDB over the parquet releases Borrower 360 reads.

One in-memory connection; every relation is a `read_parquet` view, so nothing
is copied and nothing can be written back. Queries are parameterised; the only
names interpolated into SQL are this module's own view names and columns.
"""
from __future__ import annotations

import json
import math
import threading
from functools import lru_cache
from typing import Any

import duckdb
import pandas as pd

from backend.b360 import paths

_LOCK = threading.RLock()
_CONN: duckdb.DuckDBPyConnection | None = None


class NotFound(LookupError):
    """A customer, period or tab Borrower 360 does not have."""


def conn() -> duckdb.DuckDBPyConnection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            c = duckdb.connect(":memory:")
            for name, path in paths.RELATIONS.items():
                if not path.is_file():
                    raise FileNotFoundError(f"Borrower 360 needs {path}, which is missing.")
                extra = (paths.OVERLAY / f"{name}.parquet") if paths.OVERLAY else None
                if extra is not None and extra.is_file():   # R16 d: demo customers beside the book (paths.OVERLAY)
                    c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path.as_posix()}') "
                              f"UNION ALL BY NAME SELECT * FROM read_parquet('{extra.as_posix()}')")
                else:
                    c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path.as_posix()}')")
            _CONN = c
        return _CONN


@lru_cache(maxsize=1)
def overlay_ids() -> tuple[str, ...]:
    """R16 d: borrower ids of the demo-customer overlay (paths.OVERLAY): searchable and openable, but kept out of the
    book list, its cards and totals so every book-level number stays the book's."""
    f = (paths.OVERLAY / "corp_borrower.parquet") if paths.OVERLAY else None
    if f is None or not f.is_file():
        return ()
    with _LOCK:
        return tuple(r[0] for r in conn().execute(f"SELECT DISTINCT borrower_id FROM read_parquet('{f.as_posix()}')").fetchall())


def df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with _LOCK:
        return conn().execute(sql, params or []).df()


def rows(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        cur = conn().execute(sql, params or [])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def clean(value: Any) -> Any:
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python, recursively."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [clean(r) for r in frame.astype(object).where(frame.notna(), None).to_dict("records")]


@lru_cache(maxsize=4)
def book_periods(domain_id: str) -> tuple[str, ...]:
    rel, col = ("corp_facility", "reporting_quarter") if domain_id == "corporate" else ("ret_account", "reporting_month")
    return tuple(r["p"] for r in rows(f"SELECT DISTINCT {col} AS p FROM {rel} ORDER BY 1"))


@lru_cache(maxsize=4)
def manifest(key: str) -> dict[str, Any]:
    return json.loads(paths.MANIFESTS[key].read_text())
