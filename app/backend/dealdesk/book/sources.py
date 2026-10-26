"""Where the Book reads and writes (PLAN_R12 §0): registered Data Domains relations only.

* Registered relations of the live domains (Early Warning, origination, ECL runs, classification, deposits)
  are resolved through the Data Builder registry (`backend/data_builder/registry.py`) and read from the file
  the registry names -- never from a path of our own.
* The Deal Desk relations (dd_monitoring_plan, dd_condition, dd_promise, dd_raroc_drift, dd_proposal, ...) are
  read and published only through Session E's readers in `backend.dealdesk.data` (`dd_read`, `publish`).
  Until E's SCHEMA READY lands those readers do not exist: `dd()` then raises `DataPending`, and the Book
  says which relations are pending. There is no fixture fallback for business data.

Every read is recorded in `LINEAGE` (domain, relation, file, period) so a response can carry its sources and
the lineage test can check every figure maps to a registered relation.
"""
from __future__ import annotations

import functools
import importlib
import pathlib
import threading
from typing import Any

import pandas as pd

from backend.data_builder.registry import DOMAINS

V5 = pathlib.Path(__file__).resolve().parents[3]

#: (domain, relation) pairs the Book reads from the live domains
LIVE: dict[str, tuple[str, str]] = {
    "ews_exposure": ("ews", "corp_exposure"),
    "ews_covenant": ("ews", "corp_covenant"),
    "orig_facility": ("origination", "orig_facility"),
    "ecl_facility": ("ecl_runs", "ecl_facility"),
    "cls_exposure": ("classification", "cls_exposure"),
    "dep_month": ("deposits", "dep_month"),
    "dep_derived": ("deposits", "dep_derived"),
}

#: Deal Desk relations (Session E's contract) the Book reads or publishes
DD_READS = ("dd_monitoring_plan", "dd_condition", "dd_promise", "dd_proposal", "dd_proposal_facility",
            "dd_workflow_event", "dd_raroc_drift")
DD_PUBLISHES = ("dd_raroc_drift", "dd_promise", "dd_monitoring_plan", "dd_workflow_event", "dd_review_finding")

_LOCK = threading.Lock()
LINEAGE: dict[str, dict[str, Any]] = {}


class DataPending(RuntimeError):
    """A Deal Desk relation is not available yet (Session E's readers or data not merged)."""

    def __init__(self, relation: str, why: str):
        super().__init__(f"{relation}: {why}")
        self.relation = relation
        self.why = why


def registered_path(domain: str, relation: str) -> pathlib.Path:
    rel = DOMAINS[domain]["relations"][relation]
    p = (V5 / rel["path"]).resolve()
    if (V5 / "data").resolve() not in p.parents:
        raise PermissionError(f"{domain}.{relation} is not under data/")
    return p


def _note(key: str, domain: str, relation: str, path: str, period: Any = None, rows: int | None = None) -> None:
    with _LOCK:
        LINEAGE[key] = {"domain": domain, "relation": relation, "path": path, "period": period, "rows": rows}


@functools.lru_cache(maxsize=16)
def _live_frame(key: str, columns: tuple[str, ...] | None) -> pd.DataFrame:
    domain, relation = LIVE[key]
    p = registered_path(domain, relation)
    f = pd.read_parquet(p, columns=list(columns) if columns else None)
    return f


def live(key: str, columns: list[str] | None = None) -> pd.DataFrame:
    """One registered live relation (read-only, cached)."""
    domain, relation = LIVE[key]
    f = _live_frame(key, tuple(columns) if columns else None)
    _note(key, domain, relation, str(registered_path(domain, relation).relative_to(V5)), rows=len(f))
    return f


# ------------------------------------------------------------------ Session E's Deal Desk readers

def _dd_module():
    try:
        return importlib.import_module("backend.dealdesk.data")
    except ImportError as e:  # SCHEMA READY not merged yet
        raise DataPending("backend.dealdesk.data", f"Deal Desk data readers not merged yet ({e.name})") from None


def _fn(name: str):
    m = _dd_module()
    f = getattr(m, name, None)
    if f is None:
        for sub in ("read", "readers", "publish", "publisher"):
            try:
                s = importlib.import_module(f"backend.dealdesk.data.{sub}")
            except ImportError:
                continue
            f = getattr(s, name, None)
            if f is not None:
                break
    if f is None:
        raise DataPending("backend.dealdesk.data", f"no {name}() in the Deal Desk data readers")
    return f


def dd(relation: str, **filters: Any) -> pd.DataFrame:
    """A Deal Desk relation through E's reader. Raises DataPending when it is not registered yet."""
    try:
        m = _dd_module()
        fn = getattr(m, "dd_frame", None) or _fn("dd_read")
        f = fn(relation, **filters)
    except DataPending:
        raise
    except (KeyError, FileNotFoundError, LookupError) as e:
        raise DataPending(relation, f"not registered or not written yet ({e})") from None
    if not isinstance(f, pd.DataFrame):
        f = pd.DataFrame(list(f))
    _note(relation, "deal_desk", relation, f"data/dealdesk/dd-saudi-v1/{relation}.parquet", rows=len(f))
    return f


def dd_or_empty(relation: str, pending: list[str], **filters: Any) -> pd.DataFrame:
    """A Deal Desk relation, or an empty frame with the relation added to `pending` (said on screen)."""
    try:
        return dd(relation, **filters)
    except DataPending:
        if relation not in pending:
            pending.append(relation)
        return pd.DataFrame()


def publish(relation: str, rows: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    """Publish rows through E's versioned publisher (manifest updated, period stamped)."""
    if relation not in DD_PUBLISHES:
        raise PermissionError(f"the Book does not publish {relation}")
    kw.setdefault("mode", "upsert")
    kw.setdefault("actor", "I:book")
    try:
        res = _fn("publish")(relation, rows, **kw)
    except TypeError:  # a publisher without mode / actor
        res = _fn("publish")(relation, rows)
    return res if isinstance(res, dict) else {"relation": relation, "rows": len(rows), "result": res}


def version(relation: str) -> str:
    """The published version of a Deal Desk relation (changes on every publish), or "" when unknown."""
    try:
        from backend.dealdesk.data import store
        return str(store.version_of(relation))
    except Exception:  # noqa: BLE001
        return ""


def lineage() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(v, key=k) for k, v in sorted(LINEAGE.items())]


def clear_cache() -> None:
    _live_frame.cache_clear()
