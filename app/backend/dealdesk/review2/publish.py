"""The bridge to Session E's Data Domains readers and publisher (PLAN §0, R12_DATA_CONTRACT).

`read(relation, **filters)` returns a list of row dicts through `backend.dealdesk.data` (E's `dd_read`), or [] when the
reader or the relation is not there yet. `publish(relation, rows, key)` writes rows through E's `publish`; until it exists,
rows are staged in var/dealdesk/r12_publish/<relation>.jsonl (latest row per key wins) so nothing is lost and the
lineage of every decision stays explicit.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
from typing import Any, Iterable

from backend.dealdesk import paths

_log = logging.getLogger(__name__)
_LOCK = threading.Lock()


def _readers():
    try:
        from backend.dealdesk import data as D  # E's package: dd_read(relation, **filters), publish(relation, rows)
        return D
    except Exception:  # noqa: BLE001 - before SCHEMA READY the package does not exist
        return None


def available() -> bool:
    D = _readers()
    return bool(D and hasattr(D, "dd_read"))


def _rows(x: Any) -> list[dict[str, Any]]:
    if x is None:
        return []
    if hasattr(x, "to_dict"):
        try:
            import pandas as pd
            df = x.astype(object).where(pd.notna(x), None)
            return df.to_dict("records")
        except Exception:  # noqa: BLE001
            return x.to_dict("records")
    return [dict(r) for r in x]


def read(relation: str, **filters: Any) -> list[dict[str, Any]]:
    D = _readers()
    if not D or not hasattr(D, "dd_read"):
        return []
    try:
        return _rows(D.dd_read(relation, **filters))
    except Exception as e:  # noqa: BLE001 - an unknown or empty relation reads as no rows
        _log.debug("dd_read(%s) failed: %s", relation, e)
        return []


def _stage_dir():
    d = paths.VAR / "r12_publish"
    d.mkdir(parents=True, exist_ok=True)
    return d


def staged(relation: str) -> list[dict[str, Any]]:
    f = _stage_dir() / f"{relation}.jsonl"
    if not f.exists():
        return []
    out: dict[str, dict[str, Any]] = {}
    for line in f.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r.get("_key") or json.dumps(r, sort_keys=True)] = r
    return [{k: v for k, v in r.items() if k != "_key"} for r in out.values() if not r.get("_deleted")]


def publish(relation: str, rows: Iterable[dict[str, Any]], key: Iterable[str] = ()) -> dict[str, Any]:
    rows = [dict(r) for r in rows]
    key = list(key)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    D = _readers()
    if D and hasattr(D, "publish") and not os.environ.get("DD_REVIEW2_STAGE_ONLY"):
        if key and not _changed(relation, rows, key):
            return {"relation": relation, "rows": len(rows), "via": "data-domains", "result": "unchanged"}
        try:
            res = D.publish(relation, rows, mode="upsert", actor="B")
            return {"relation": relation, "rows": len(rows), "via": "data-domains", "result": res if isinstance(res, (dict, str, int)) else None}
        except Exception as e:  # noqa: BLE001 - never lose a decision: stage it and say so
            _log.warning("publish(%s) failed, staged instead: %s", relation, e)
    with _LOCK:
        with open(_stage_dir() / f"{relation}.jsonl", "a") as f:
            for r in rows:
                r.setdefault("published_at", stamp)
                f.write(json.dumps({**r, "_key": "|".join(str(r.get(k)) for k in key) if key else None}, default=str) + "\n")
    return {"relation": relation, "rows": len(rows), "via": "staged"}


_IGNORE = {"published_at", "rel_version", "raised_at", "reporting_quarter"}


def _norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return round(float(v), 9)
    return str(v)


def _changed(relation: str, rows: list[dict[str, Any]], key: list[str]) -> bool:
    """False when every row is already published with the same values (no new version for an unchanged decision)."""
    try:
        cur = {tuple(str(r.get(k)) for k in key): r for r in read(relation, **({key[0]: sorted({str(x.get(key[0])) for x in rows})} if rows else {}))}
    except Exception:  # noqa: BLE001
        return True
    for r in rows:
        old = cur.get(tuple(str(r.get(k)) for k in key))
        if old is None:
            return True
        for c, v in r.items():
            if c in _IGNORE:
                continue
            if _norm(v) != _norm(old.get(c)):
                return True
    return False


def src(relation: str, key: dict[str, Any] | None = None, period: str | None = None, via: str | None = None) -> dict[str, Any]:
    """The lineage tag on a figure: the domain relation, the row key and the period it is read from."""
    out: dict[str, Any] = {"relation": relation, "key": key or {}, "period": period}
    if via:
        out["via"] = via
    return out
