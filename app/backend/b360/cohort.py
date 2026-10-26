"""PLAN_R9 B5: "Send to What-If" — a Borrower 360 selection frozen as a What-If population.

The filtered list (or the ids given) is resolved to its exposures (facilities or accounts) at the
period, and stored with a membership hash in Borrower 360's own store (`var/b360/b360_cohorts.sqlite`,
table `cohort`, JSON `body`), in the same shape as an Early Warning cohort. What-If opens it read-only
by id (`backend/whatif_v5/cohorts.py`, prefix `b360-cohort-`) and runs current against stressed ECL on it.
This is the only thing Borrower 360 writes, and it writes only to its own store.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import time
from typing import Any

from backend.b360 import booklist, paths
from backend.b360.store import clean, rows
from backend.ews_domain import ews_rules as ews

PREFIX = "b360-cohort-"


def store_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("B360_COHORT_STORE") or (paths.V5 / "var" / "b360" / "b360_cohorts.sqlite"))


def _con() -> sqlite3.Connection:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=5)
    c.execute("CREATE TABLE IF NOT EXISTS cohort (object_id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at REAL)")
    return c


def _title(domain_id: str, filters: dict[str, str], n: int) -> str:
    from backend.b360 import intel
    bits = [dict(intel.CARDS).get(filters["card"], filters["card"])] if filters.get("card") else []
    bits += [v for k, v in filters.items() if v and k not in ("card", "ead_min", "ead_max")]
    who = "borrowers" if domain_id == "corporate" else "customers"
    return f"Borrower 360: {n:,} {who}" + (f" · {' · '.join(bits)}" if bits else "")


def freeze(domain_id: str, period: str, ids: list[str] | None = None, query: dict[str, Any] | None = None) -> dict[str, Any]:
    period = booklist.resolve_period(domain_id, period)
    q = {k: str(v) for k, v in (query or {}).items() if v not in (None, "")}
    filters = {k: q[k] for k in booklist.FILTERS if k in q}
    if ids:
        owners = sorted({str(x) for x in ids})
    else:
        v = booklist.View(domain_id, period, q.get("q", ""), filters,
                          float(q["ead_min"]) if "ead_min" in q else None, float(q["ead_max"]) if "ead_max" in q else None)
        owners = sorted(str(r["id"]) for r in booklist.all_rows(v)[0])
    if not owners:
        raise ValueError("The selection is empty; nothing to send to What-If.")
    if len(owners) > 20000:
        raise ValueError("The selection is larger than 20,000 names; narrow it first.")
    rel, key, okey, pcol = (("corp_facility", "facility_id", "borrower_id", "reporting_quarter") if domain_id == "corporate"
                            else ("ret_account", "account_id", "customer_id", "reporting_month"))
    ex = rows(f"""SELECT {key} AS id, stage, ead_sar_mn AS ead, ecl_sar_mn AS ecl FROM {rel}
                  WHERE {pcol} = ? AND {okey} IN (SELECT unnest(?::VARCHAR[])) ORDER BY 1""", [period, owners])
    exposure_ids = [str(r["id"]) for r in ex]
    digest = hashlib.sha256("\n".join(exposure_ids).encode()).hexdigest()
    object_id = PREFIX + hashlib.sha256(f"{domain_id}|{period}|{digest}".encode()).hexdigest()[:16]
    stage_mix = {str(s): sum(1 for r in ex if r["stage"] == s) for s in (1, 2, 3)}
    body = clean({
        "object_id": object_id, "kind": "b360_selection", "status": "frozen",
        "title": _title(domain_id, filters if not ids else {}, len(owners)) if not ids or len(owners) > 1
        else f"Borrower 360: {owners[0]}",
        "domain_id": domain_id, "release_id": "", "period": period, "ruleset": ews.RULESET_VERSION,
        "membership_hash": digest, "counts": {"owners": len(owners), "exposures": len(exposure_ids)},
        "exposure": sum(r["ead"] or 0 for r in ex), "ecl": sum(r["ecl"] or 0 for r in ex), "stage_mix": stage_mix,
        "customer_ids": owners[:200], "request": {"ids": ids or [], "query": q}, "created_at": time.time(),
        "exposure_ids": exposure_ids, "source": "Borrower 360",
    })
    with _con() as c:
        c.execute("INSERT OR REPLACE INTO cohort (object_id, body, created_at) VALUES (?, ?, ?)",
                  (object_id, json.dumps(body), body["created_at"]))
    return {k: v for k, v in body.items() if k != "exposure_ids"}
