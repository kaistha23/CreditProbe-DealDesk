"""R13 IB: registered Data Domains reads with lineage (PLAN_R12 §0, PLAN_R13 N5).

Every relation is resolved through the Data Builder registry (`backend/data_builder/registry.py`) and read from the file the
registry names, read-only. Every figure an IB engine returns is wrapped by `num()` so it carries its source: domain, relation,
key, column and period. Shared by the renewal autopilot, the covenant designer and "who to call today".
"""
from __future__ import annotations

import functools
import glob
import pathlib
import threading
from typing import Any

import numpy as np
import pandas as pd

from backend.data_builder.registry import DOMAINS

V5 = pathlib.Path(__file__).resolve().parents[3]
_LOCK = threading.Lock()
_SEEN: dict[str, dict[str, Any]] = {}


class Missing(RuntimeError):
    """A registered relation's file is not on disk (stated as a data limit, never filled in)."""

    def __init__(self, domain: str, relation: str, why: str):
        super().__init__(f"{domain}.{relation}: {why}")
        self.domain, self.relation, self.why = domain, relation, why


def path_of(domain: str, relation: str) -> pathlib.Path:
    rel = DOMAINS[domain]["relations"][relation]
    p = rel["path"]
    if "*" in p:
        hits = sorted(glob.glob(str(V5 / p)))
        if not hits:
            raise Missing(domain, relation, "no file matches the registered path")
        p = hits[-1]
    full = (V5 / p).resolve()
    if (V5 / "data").resolve() not in full.parents:
        raise PermissionError(f"{domain}.{relation} is not under data/")
    return full


@functools.lru_cache(maxsize=32)
def _frame(domain: str, relation: str, columns: tuple[str, ...] | None) -> pd.DataFrame:
    p = path_of(domain, relation)
    if not p.exists():
        raise Missing(domain, relation, "file not built")
    f = pd.read_parquet(p, columns=list(columns) if columns else None)
    for c in f.columns:  # pyarrow-backed strings and numbers -> plain numpy, so arithmetic and comparisons behave
        if str(f[c].dtype).endswith("[pyarrow]"):
            try:
                f[c] = f[c].astype("float64") if pd.api.types.is_numeric_dtype(f[c]) else f[c].astype(object)
            except (TypeError, ValueError):
                f[c] = f[c].astype(object)
    return f


def read(domain: str, relation: str, columns: list[str] | None = None) -> pd.DataFrame:
    """One registered relation (cached, read-only). Records the read for `lineage()`."""
    f = _frame(domain, relation, tuple(columns) if columns else None)
    rel = DOMAINS[domain]["relations"][relation]
    with _LOCK:
        _SEEN[f"{domain}.{relation}"] = {"domain": domain, "relation": relation, "path": str(path_of(domain, relation).relative_to(V5)),
                                         "period_column": rel.get("period_column"), "rows": int(len(f))}
    return f


def try_read(domain: str, relation: str, limits: list[str], columns: list[str] | None = None) -> pd.DataFrame:
    """A relation, or an empty frame with the gap stated in `limits`."""
    try:
        return read(domain, relation, columns)
    except (Missing, FileNotFoundError, KeyError) as e:
        limits.append(f"{domain}.{relation} is not available ({e}); signals from it are not shown.")
        return pd.DataFrame(columns=columns or [])


def lineage() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(v) for _, v in sorted(_SEEN.items())]


def clear() -> None:
    _frame.cache_clear()


def py(x: Any) -> Any:
    """JSON-safe scalar."""
    if x is None or x is pd.NA:
        return None
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    return x


def clean(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return py(x)


def src(domain: str, relation: str, key: dict[str, Any], column: str, period: Any = None, method: str | None = None) -> dict[str, Any]:
    out = {"domain": domain, "relation": relation, "key": {k: py(v) for k, v in key.items()}, "column": column, "period": py(period)}
    if method:
        out["method"] = method
    return out


def num(value: Any, source: dict[str, Any], unit: str = "", label: str = "") -> dict[str, Any]:
    """A number with its lineage (every number an IB engine returns goes through here)."""
    v = py(value)
    if isinstance(v, float):
        v = round(v, 6)
    out: dict[str, Any] = {"value": v, "source": source}
    if unit:
        out["unit"] = unit
    if label:
        out["label"] = label
    return out


def computed(value: Any, method: str, inputs: list[dict[str, Any]], unit: str = "", label: str = "") -> dict[str, Any]:
    """A number this service computed: its method and the sourced inputs it was computed from."""
    return num(value, {"domain": "computed", "relation": "r13_ib", "method": method, "inputs": [i.get("source", i) for i in inputs]},
               unit, label)


def quarter_index(q: pd.Series) -> pd.Series:
    """'2024Q3' -> 2024*4+2 (consecutive quarters differ by 1)."""
    s = q.astype(str)
    return s.str[:4].astype(int) * 4 + s.str[-1].astype(int) - 1
