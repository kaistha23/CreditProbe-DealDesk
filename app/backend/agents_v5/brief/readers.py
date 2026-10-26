"""Noor's readers: every business fact the brief uses comes from a relation registered in Data Domains (PLAN_R12 §0).

`read(domain, relation, where=..., columns=...)` returns a `Read`: the rows plus the source stamp (domain, relation,
period column, row count) that every brief line carries as its trace. The order of preference:

1. Session E's shared reader `backend.dealdesk.data.dd_read(relation, **filters)` for Deal Desk relations, once it is
   on the build (SCHEMA READY);
2. otherwise the Data Builder store (`backend.data_builder.store`): the registered parquet, read with DuckDB.

A relation that is not registered (yet) is never read from a side door: the Read is empty with
`status="not_registered"`, and the brief says that source has nothing to report on this build.

The agents' own working memory (the EWS triage store, the Lenses monitoring store, the approvals table) is not a Data
Domains relation; those are read through the owning agent's store module, read-only, and stamped `agent_store`.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Read:
    domain: str
    relation: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok | not_registered | unavailable | agent_store
    period_column: str | None = None
    note: str = ""

    def stamp(self, keys: dict[str, Any] | None = None, period: str = "") -> dict[str, Any]:
        """The trace of one figure: domain, relation, row keys and period."""
        return {"domain": self.domain, "relation": self.relation, "keys": dict(keys or {}), "period": period,
                "status": self.status}


def _dd_reader():
    try:
        mod = importlib.import_module("backend.dealdesk.data")
    except Exception:  # noqa: BLE001 - E's reader not on this build yet
        return None
    return getattr(mod, "dd_read", None)


def registered(domain: str, relation: str) -> dict[str, Any] | None:
    try:
        from backend.data_builder.registry import DOMAINS
    except Exception:  # noqa: BLE001
        return None
    return ((DOMAINS.get(domain) or {}).get("relations") or {}).get(relation)


def domain_of(relation: str) -> str | None:
    try:
        from backend.data_builder.registry import DOMAINS
    except Exception:  # noqa: BLE001
        return None
    for d, spec in DOMAINS.items():
        if relation in (spec.get("relations") or {}):
            return d
    return None


def _clean(v: Any) -> Any:
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:  # noqa: BLE001
        pass
    if hasattr(v, "isoformat") and not isinstance(v, str):
        try:
            return v.isoformat()
        except Exception:  # noqa: BLE001
            return str(v)
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            return v
    return v


def read(domain: str, relation: str, *, where: str = "", args: list[Any] | None = None,
         columns: str = "*", group: str = "", order: str = "", limit: int | None = None,
         filters: dict[str, Any] | None = None) -> Read:
    """Rows of one registered relation. `where` is a SQL predicate with `?` placeholders bound from `args`."""
    domain = domain or domain_of(relation) or ""
    spec = registered(domain, relation)
    if spec is None:
        return Read(domain, relation, status="not_registered",
                    note=f"{relation} is not registered in Data Domains on this build.")
    period = spec.get("period_column")
    if domain == "deal_desk" and filters is not None and not where:
        fn = _dd_reader()
        if fn is not None:
            try:
                rows = fn(relation, **filters)
                rows = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows or [])
                return Read(domain, relation, [{k: _clean(v) for k, v in r.items()} for r in rows],
                            period_column=period)
            except Exception as e:  # noqa: BLE001 - fall through to the store
                logger.info("dd_read(%s) failed, reading through the store: %s", relation, e)
    try:
        from backend.data_builder import store
        src = store.source(domain, relation)
    except Exception as e:  # noqa: BLE001
        return Read(domain, relation, status="unavailable", period_column=period, note=str(e)[:200])
    preds, bind = [], list(args or [])
    if where:
        preds.append(f"({where})")
    for k, v in (filters or {}).items():
        preds.append(f'"{k}" = ?')
        bind.append(v)
    sql = f"SELECT {columns} FROM {src}" + (f" WHERE {' AND '.join(preds)}" if preds else "")
    if group:
        sql += f" GROUP BY {group}"
    if order:
        sql += f" ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    try:
        rows = store.q(sql, bind)
    except Exception as e:  # noqa: BLE001 - an empty or schema-only parquet, or a column E has not filled yet
        return Read(domain, relation, status="unavailable", period_column=period, note=str(e)[:200])
    return Read(domain, relation, [{k: _clean(v) for k, v in r.items()} for r in rows], period_column=period)


def latest_period(domain: str, relation: str, column: str = "") -> str:
    spec = registered(domain, relation)
    col = column or (spec or {}).get("period_column") or ""
    if not col:
        return ""
    r = read(domain, relation, columns=f'max("{col}") AS p')
    return str((r.rows[0] or {}).get("p") or "") if r.rows else ""
