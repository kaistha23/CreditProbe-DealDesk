"""The triage agent's memory: verdicts per run and name, RM action notes, and proposal references.

This is the agent's own working memory (for follow-up on later runs), not the books: it never holds a stage, a
watchlist flag or any figure of record. Location: `AGENTS_V5_EWS_STORE`, default `var/agents_v5/ews_triage.sqlite`.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

V5 = pathlib.Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
  run_id TEXT NOT NULL, domain TEXT NOT NULL, period TEXT NOT NULL, borrower_id TEXT NOT NULL,
  borrower_name TEXT, verdict TEXT NOT NULL, reason TEXT, detail TEXT, created TEXT NOT NULL,
  PRIMARY KEY (run_id, borrower_id));
CREATE INDEX IF NOT EXISTS verdicts_name ON verdicts(borrower_id, created);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, domain TEXT NOT NULL, borrower_id TEXT NOT NULL,
  borrower_name TEXT, verdict TEXT NOT NULL, owner TEXT, owner_role TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 0,
  due TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', closed TEXT, note TEXT,
  history TEXT NOT NULL DEFAULT '[]');
CREATE INDEX IF NOT EXISTS actions_name ON actions(borrower_id, status);
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, borrower_id TEXT NOT NULL, kind TEXT NOT NULL,
  approval_ref TEXT, status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL, detail TEXT);
CREATE INDEX IF NOT EXISTS proposals_name ON proposals(borrower_id, kind);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, domain TEXT, period TEXT, goal TEXT, goal_type TEXT, scope TEXT, created TEXT, body TEXT);
"""


def path() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("AGENTS_V5_EWS_STORE") or V5 / "var" / "agents_v5" / "ews_triage.sqlite")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        con = sqlite3.connect(path())
        con.row_factory = sqlite3.Row
        try:
            con.executescript(SCHEMA)
            yield con
            con.commit()
        finally:
            con.close()


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------- reads

def last_verdicts(owners: list[str] | None = None, *, domain: str = "corporate",
                  before_run: str = "") -> dict[str, dict[str, Any]]:
    """The latest verdict per name from earlier runs (excluding `before_run`)."""
    with db() as con:
        rows = _rows(con.execute(
            """SELECT v.* FROM verdicts v JOIN (SELECT borrower_id, MAX(created) AS c FROM verdicts
                                               WHERE domain = ? AND run_id <> ? GROUP BY borrower_id) m
               ON m.borrower_id = v.borrower_id AND m.c = v.created WHERE v.run_id <> ?""",
            [domain, before_run, before_run]))
    out = {r["borrower_id"]: {**r, "detail": json.loads(r["detail"] or "{}")} for r in rows}
    return {k: v for k, v in out.items() if owners is None or k in owners}


def followed(domain: str = "corporate") -> list[str]:
    """Names this agent follows up: an open action, or a latest verdict of watchlist, SICR or UTP."""
    with db() as con:
        acts = {r["borrower_id"] for r in con.execute(
            "SELECT DISTINCT borrower_id FROM actions WHERE domain = ? AND status = 'open'", [domain])}
    lv = last_verdicts(domain=domain)
    return sorted(acts | {k for k, v in lv.items() if v["verdict"] in ("watchlist", "sicr", "utp")})


def open_actions(owners: list[str] | None = None, domain: str = "corporate") -> list[dict[str, Any]]:
    with db() as con:
        rows = _rows(con.execute("SELECT * FROM actions WHERE domain = ? AND status = 'open' ORDER BY id", [domain]))
    for r in rows:
        r["history"] = json.loads(r["history"] or "[]")
    return [r for r in rows if owners is None or r["borrower_id"] in owners]


def proposals_for(owners: list[str]) -> list[dict[str, Any]]:
    with db() as con:
        rows = _rows(con.execute("SELECT * FROM proposals ORDER BY id"))
    return [r for r in rows if r["borrower_id"] in owners]


def run_verdicts(run_id: str) -> list[dict[str, Any]]:
    with db() as con:
        return _rows(con.execute("SELECT borrower_id, borrower_name, verdict, reason, period FROM verdicts "
                                 "WHERE run_id = ?", [run_id]))


def latest_run(domain: str = "corporate", period: str = "", goal_type: str = "") -> dict[str, Any] | None:
    q, p = "SELECT * FROM runs WHERE domain = ?", [domain]
    if period:
        q += " AND period = ?"
        p.append(period)
    if goal_type:
        q += " AND goal_type = ?"
        p.append(goal_type)
    with db() as con:
        r = con.execute(q + " ORDER BY created DESC LIMIT 1", p).fetchone()
    return dict(r) if r else None


def runs(domain: str = "corporate", limit: int = 20) -> list[dict[str, Any]]:
    with db() as con:
        return _rows(con.execute("SELECT run_id, domain, period, goal, goal_type, scope, created FROM runs "
                                 "WHERE domain = ? ORDER BY created DESC LIMIT ?", [domain, limit]))


def get_run(run_id: str) -> dict[str, Any] | None:
    with db() as con:
        r = con.execute("SELECT body FROM runs WHERE run_id = ?", [run_id]).fetchone()
    return json.loads(r["body"]) if r else None


# ---------------------------------------------------------------- writes (agent memory only)

def record_verdicts(run_id: str, domain: str, period: str, created: str, rows: list[dict[str, Any]]) -> int:
    with db() as con:
        con.executemany(
            "INSERT OR REPLACE INTO verdicts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, domain, period, r["borrower_id"], r.get("borrower_name"), r["verdict"], r.get("reason", ""),
              json.dumps(r.get("detail") or {}, default=str), created) for r in rows])
    return len(rows)


def add_action(run_id: str, domain: str, note: dict[str, Any]) -> int:
    with db() as con:
        cur = con.execute(
            "INSERT INTO actions (run_id, domain, borrower_id, borrower_name, verdict, owner, owner_role, level, due, "
            "created, note, history) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, domain, note["borrower_id"], note.get("borrower_name"), note["verdict"], note.get("owner"),
             note.get("owner_role", "RM"), int(note.get("level", 0)), note["due"], note["created"],
             json.dumps(note, default=str), json.dumps([{"at": note["created"], "event": "created",
                                                          "owner_role": note.get("owner_role", "RM")}])])
        return int(cur.lastrowid)


def escalate_action(action_id: int, *, level: int, owner_role: str, owner: str, due: str, at: str, why: str) -> None:
    with db() as con:
        r = con.execute("SELECT history FROM actions WHERE id = ?", [action_id]).fetchone()
        hist = json.loads(r["history"] or "[]") if r else []
        hist.append({"at": at, "event": "escalated", "owner_role": owner_role, "why": why})
        con.execute("UPDATE actions SET level = ?, owner_role = ?, owner = ?, due = ?, history = ? WHERE id = ?",
                    [level, owner_role, owner, due, json.dumps(hist), action_id])


def close_action(action_id: int, *, at: str, why: str, status: str = "closed") -> None:
    with db() as con:
        r = con.execute("SELECT history FROM actions WHERE id = ?", [action_id]).fetchone()
        hist = json.loads(r["history"] or "[]") if r else []
        hist.append({"at": at, "event": status, "why": why})
        con.execute("UPDATE actions SET status = ?, closed = ?, history = ? WHERE id = ?",
                    [status, at, json.dumps(hist), action_id])


def add_proposal(run_id: str, borrower_id: str, kind: str, approval_ref: str, created: str,
                 detail: dict[str, Any]) -> int:
    with db() as con:
        cur = con.execute("INSERT INTO proposals (run_id, borrower_id, kind, approval_ref, created, detail) "
                          "VALUES (?, ?, ?, ?, ?, ?)",
                          [run_id, borrower_id, kind, approval_ref, created, json.dumps(detail, default=str)])
        return int(cur.lastrowid)


def save_run(run_id: str, domain: str, period: str, goal: str, goal_type: str, scope: str, created: str,
             body: dict[str, Any]) -> None:
    with db() as con:
        con.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [run_id, domain, period, goal, goal_type, scope, created, json.dumps(body, default=str)])


__all__ = ["add_action", "add_proposal", "close_action", "db", "escalate_action", "followed", "get_run",
           "last_verdicts", "latest_run", "open_actions", "path", "proposals_for", "record_verdicts", "run_verdicts",
           "runs", "save_run"]
