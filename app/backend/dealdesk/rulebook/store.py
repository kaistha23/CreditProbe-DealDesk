"""The rulebook store: one SQLite file under var/dealdesk/rulebook/ (DEALDESK_VAR moves it; DEALDESK_RULEBOOK_DB overrides it).

    assessments  an uploaded regulation or policy read for Deal Desk: summary, the thresholds it sets, the pipeline impact,
                 status (pending | approved | rejected), who uploaded, who decided, when, the Policy Docs document it belongs to
    thresholds   every threshold an approved policy put in force: param, segment, value, clause, quote, approved by and when
                 (the provenance of each value; the latest per param and segment is in force)
    flags        a pending deal flagged by an approved policy: the check it fails, the clause cited, open | cleared
    gold         a gold-standard proposal compared with how the system writes today, and what was applied from it
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.dealdesk import paths

_LOCK = threading.RLock()
_READY: set[str] = set()


class NotFound(KeyError):
    pass


class Invalid(ValueError):
    pass


def db_path() -> pathlib.Path:
    p = os.environ.get("DEALDESK_RULEBOOK_DB")
    return pathlib.Path(p) if p else paths.VAR / "rulebook" / "rulebook.sqlite"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    if str(path) not in _READY or con.execute("SELECT 1 FROM sqlite_master WHERE name='assessments'").fetchone() is None:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS assessments (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
              policy_doc_id TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL DEFAULT '', text TEXT NOT NULL,
              summary TEXT NOT NULL DEFAULT '', reading TEXT NOT NULL, impact TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              uploaded_by TEXT NOT NULL DEFAULT '', uploaded_at TEXT NOT NULL, decided_by TEXT NOT NULL DEFAULT '',
              decided_at TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', flagged INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS thresholds (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id TEXT NOT NULL, param TEXT NOT NULL, segment TEXT NOT NULL,
              value TEXT NOT NULL, display TEXT NOT NULL DEFAULT '', clause TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL DEFAULT '',
              reference TEXT NOT NULL DEFAULT '', approved_by TEXT NOT NULL DEFAULT '', approved_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active');
            CREATE TABLE IF NOT EXISTS flags (
              n INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, assessment_id TEXT NOT NULL, check_id TEXT NOT NULL,
              label TEXT NOT NULL, why TEXT NOT NULL DEFAULT '', clause TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL DEFAULT '',
              reference TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', at TEXT NOT NULL, by TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS gold (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, file_name TEXT NOT NULL DEFAULT '', text TEXT NOT NULL,
              comparison TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', uploaded_by TEXT NOT NULL DEFAULT '',
              uploaded_at TEXT NOT NULL, applied_by TEXT NOT NULL DEFAULT '', applied_at TEXT NOT NULL DEFAULT '',
              applied TEXT NOT NULL DEFAULT '[]');
        """)
        con.commit()
        _READY.add(str(path))
    return con


def _j(v: Any, default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ assessments

def assessment_row(r: sqlite3.Row, full: bool = True) -> dict[str, Any]:
    d = dict(r)
    d["reading"] = _j(d["reading"], {})
    d["impact"] = _j(d["impact"], {})
    if not full:
        d.pop("text", None)
        d["impact"] = {k: d["impact"].get(k) for k in ("pipeline", "parameters", "checks", "deal_types")}
    return d


def add_assessment(a: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            con.execute("INSERT INTO assessments(id, kind, title, reference, policy_doc_id, file_name, text, summary, reading, impact, status,"
                        " uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', ?, ?)",
                        (a["id"], a["kind"], a["title"], a.get("reference", ""), a.get("policy_doc_id", ""), a.get("file_name", ""), a["text"],
                         a.get("summary", ""), json.dumps(a["reading"]), json.dumps(a["impact"], default=str), a.get("uploaded_by", ""), now()))
            con.commit()
        finally:
            con.close()
    return get_assessment(a["id"])


def get_assessment(aid: str) -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            r = con.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
            if r is None:
                raise NotFound(f"No assessment {aid}.")
            return assessment_row(r)
        finally:
            con.close()


def assessments(kind: str = "", policy_doc_id: str = "", status: str = "") -> list[dict[str, Any]]:
    q, a = "SELECT * FROM assessments WHERE 1=1", []
    for col, v in (("kind", kind), ("policy_doc_id", policy_doc_id), ("status", status)):
        if v:
            q += f" AND {col}=?"
            a.append(v)
    with _LOCK:
        con = connect()
        try:
            return [assessment_row(r, full=False) for r in con.execute(q + " ORDER BY uploaded_at DESC, id", a)]
        finally:
            con.close()


def update_assessment(aid: str, **cols: Any) -> dict[str, Any]:
    allowed = {"status", "decided_by", "decided_at", "note", "impact", "flagged", "policy_doc_id"}
    cols = {k: (json.dumps(v, default=str) if k == "impact" else v) for k, v in cols.items() if k in allowed}
    with _LOCK:
        con = connect()
        try:
            con.execute(f"UPDATE assessments SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", [*cols.values(), aid])  # noqa: S608
            con.commit()
        finally:
            con.close()
    return get_assessment(aid)


# ------------------------------------------------------------------ thresholds in force

def add_thresholds(aid: str, reference: str, changes: list[dict[str, Any]], by: str) -> list[int]:
    out = []
    with _LOCK:
        con = connect()
        try:
            at = now()
            for c in changes:
                cur = con.execute("INSERT INTO thresholds(assessment_id, param, segment, value, display, clause, quote, reference, approved_by, approved_at)"
                                  " VALUES (?,?,?,?,?,?,?,?,?,?)", (aid, c["param"], c["segment"], json.dumps(c["value"]), c.get("display", ""),
                                                                    c.get("clause", ""), c.get("quote", ""), reference, by, at))
                out.append(int(cur.lastrowid or 0))
            con.commit()
        finally:
            con.close()
    return out


def thresholds(status: str = "active") -> list[dict[str, Any]]:
    with _LOCK:
        con = connect()
        try:
            rows = con.execute("SELECT * FROM thresholds" + (" WHERE status=?" if status else "") + " ORDER BY seq", (status,) if status else ())
            return [{**dict(r), "value": _j(r["value"], None)} for r in rows]
        finally:
            con.close()


def overlay() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for t in thresholds():
        out.setdefault(t["param"], []).append(t)
    return out


def next_seq() -> int:
    with _LOCK:
        con = connect()
        try:
            r = con.execute("SELECT COALESCE(MAX(seq), 0) FROM thresholds").fetchone()
            return int(r[0]) + 1
        finally:
            con.close()


# ------------------------------------------------------------------ flags

def add_flags(rows: list[dict[str, Any]], by: str) -> int:
    with _LOCK:
        con = connect()
        try:
            at = now()
            for f in rows:
                con.execute("INSERT INTO flags(proposal_id, assessment_id, check_id, label, why, clause, quote, reference, status, at, by)"
                            " VALUES (?,?,?,?,?,?,?,?, 'open', ?, ?)", (f["proposal_id"], f["assessment_id"], f["check"], f["label"], f.get("why", ""),
                                                                      f.get("clause", ""), f.get("quote", ""), f.get("reference", ""), at, by))
            con.commit()
            return len(rows)
        finally:
            con.close()


def flags(proposal_id: str = "", assessment_id: str = "", status: str = "open") -> list[dict[str, Any]]:
    q, a = "SELECT * FROM flags WHERE 1=1", []
    for col, v in (("proposal_id", proposal_id), ("assessment_id", assessment_id), ("status", status)):
        if v:
            q += f" AND {col}=?"
            a.append(v)
    with _LOCK:
        con = connect()
        try:
            return [dict(r) for r in con.execute(q + " ORDER BY n", a)]
        finally:
            con.close()


def clear_flag(n: int, by: str) -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            r = con.execute("SELECT * FROM flags WHERE n=?", (n,)).fetchone()
            if r is None:
                raise NotFound(f"No flag {n}.")
            con.execute("UPDATE flags SET status='cleared', by=? WHERE n=?", (by, n))
            con.commit()
            return dict(con.execute("SELECT * FROM flags WHERE n=?", (n,)).fetchone())
        finally:
            con.close()


# ------------------------------------------------------------------ gold standards

def gold_row(r: sqlite3.Row, full: bool = True) -> dict[str, Any]:
    d = dict(r)
    d["comparison"] = _j(d["comparison"], {})
    d["applied"] = _j(d["applied"], [])
    if not full:
        d.pop("text", None)
    return d


def add_gold(g: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            con.execute("INSERT INTO gold(id, title, file_name, text, comparison, status, uploaded_by, uploaded_at) VALUES (?,?,?,?,?, 'pending', ?, ?)",
                        (g["id"], g["title"], g.get("file_name", ""), g["text"], json.dumps(g["comparison"]), g.get("uploaded_by", ""), now()))
            con.commit()
        finally:
            con.close()
    return get_gold(g["id"])


def get_gold(gid: str) -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            r = con.execute("SELECT * FROM gold WHERE id=?", (gid,)).fetchone()
            if r is None:
                raise NotFound(f"No gold-standard document {gid}.")
            return gold_row(r)
        finally:
            con.close()


def golds() -> list[dict[str, Any]]:
    with _LOCK:
        con = connect()
        try:
            return [gold_row(r, full=False) for r in con.execute("SELECT * FROM gold ORDER BY uploaded_at DESC, id")]
        finally:
            con.close()


def update_gold(gid: str, **cols: Any) -> dict[str, Any]:
    allowed = {"status", "applied_by", "applied_at", "applied"}
    cols = {k: (json.dumps(v) if k == "applied" else v) for k, v in cols.items() if k in allowed}
    with _LOCK:
        con = connect()
        try:
            con.execute(f"UPDATE gold SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", [*cols.values(), gid])  # noqa: S608
            con.commit()
        finally:
            con.close()
    return get_gold(gid)
