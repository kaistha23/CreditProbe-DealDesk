"""The Scorecard Validation store (SQLite, WAL) at var/scorecard_v5/scorecard.sqlite.

  threads      one per conversation: owner, team, scorecard, title, state (JSON: stage, plan, validation)
  turns        the settled transcript: question + answer per ordinal
  validations  one per completed run: plan, result (JSON, with figures), verdict counts, the review
  findings     R16 M8: the findings register at run time (new findings from validations, and status / owner / due changes
               to the seeded register rows in data/scorecard_v5/monitoring-saudi-v1/sc_findings_register)
  conclusions  R16 M8: maker-checker on a validation's conclusion (proposed by a maker, approved or returned by a checker)
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Any

from backend.scorecard_v5 import charts, paths


class _ClosingConnection(sqlite3.Connection):
    """`with self._con() as con:` commits (sqlite3's own behaviour) and then closes.

    sqlite3.Connection's context manager does not close the connection; the polling
    workers open one per loop, so without this a long-running service exhausts its
    file descriptors (macOS default 256 per process) and fails with "unable to open
    database file"."""

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY, owner TEXT, team TEXT, scorecard_id TEXT, title TEXT, state TEXT,
  created_at REAL, updated_at REAL, archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS turns (
  thread_id TEXT, ordinal INTEGER, question TEXT, answer TEXT, created_at REAL, PRIMARY KEY (thread_id, ordinal));
CREATE TABLE IF NOT EXISTS validations (
  validation_id TEXT PRIMARY KEY, thread_id TEXT, scorecard_id TEXT, owner TEXT, team TEXT, title TEXT, as_of TEXT,
  plan TEXT, result TEXT, overall TEXT, counts TEXT, created_at REAL, review TEXT, seed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY, scorecard_id TEXT, record TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS conclusions (
  validation_id TEXT PRIMARY KEY, record TEXT, updated_at REAL);
"""


class Store:
    def __init__(self, path: pathlib.Path | None = None):
        self.path = pathlib.Path(path or paths.store_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._con() as con:
            con.executescript(SCHEMA)

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None, factory=_ClosingConnection)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    # ---------------------------------------------------------------- threads
    def create_thread(self, *, owner: str, team: str, title: str = "New validation", scorecard_id: str = "", state: dict | None = None,
                      created_at: float | None = None) -> dict[str, Any]:
        tid = "sv-" + uuid.uuid4().hex[:12]
        now = created_at or time.time()
        with self._lock, self._con() as con:
            con.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,0)", (tid, owner, team, scorecard_id, title, json.dumps(state or {"stage": "choose"}), now, now))
        return self.thread(tid)

    def thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["state"] = json.loads(d["state"] or "{}")
        return d

    def save_thread(self, thread_id: str, state: dict, title: str | None = None, scorecard_id: str | None = None, at: float | None = None) -> None:
        sets, args = ["state=?", "updated_at=?"], [json.dumps(state), at or time.time()]
        if title is not None:
            sets.append("title=?")
            args.append(title)
        if scorecard_id is not None:
            sets.append("scorecard_id=?")
            args.append(scorecard_id)
        with self._lock, self._con() as con:
            con.execute(f"UPDATE threads SET {', '.join(sets)} WHERE thread_id=?", (*args, thread_id))

    def threads(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT thread_id, owner, team, scorecard_id, title, created_at, updated_at, state FROM threads WHERE archived=0 "
                               "ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["stage"] = json.loads(d.pop("state") or "{}").get("stage", "choose")
            out.append(d)
        return out

    def add_turn(self, thread_id: str, question: str, answer: dict, at: float | None = None) -> int:
        with self._lock, self._con() as con:
            n = con.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM turns WHERE thread_id=?", (thread_id,)).fetchone()[0]
            con.execute("INSERT INTO turns VALUES (?,?,?,?,?)", (thread_id, n, question, json.dumps(answer), at or time.time()))
        return int(n)

    def turns(self, thread_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT * FROM turns WHERE thread_id=? ORDER BY ordinal", (thread_id,)).fetchall()
        return [{"ordinal": r["ordinal"], "question": r["question"], "answer": json.loads(r["answer"]), "created_at": r["created_at"]} for r in rows]

    def rename(self, thread_id: str, title: str) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE threads SET title=?, updated_at=? WHERE thread_id=?", (title, time.time(), thread_id))

    # ---------------------------------------------------------------- validations
    def add_validation(self, *, thread_id: str, scorecard_id: str, owner: str, team: str, title: str, plan: dict, result: dict,
                       seed: bool = False, at: float | None = None) -> dict[str, Any]:
        vid = f"val-{scorecard_id.lower()}-{plan['as_of'].lower()}-{uuid.uuid4().hex[:6]}"
        review = {"status": "pending", "conclusion": "", "note": "", "reviewer": "", "at": None}
        with self._lock, self._con() as con:
            con.execute("INSERT INTO validations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (vid, thread_id, scorecard_id, owner, team, title, plan["as_of"], json.dumps(plan), json.dumps(result),
                         result["summary"]["overall"], json.dumps(result["summary"]["counts"]), at or time.time(), json.dumps(review), int(seed)))
        return self.validation(vid, full=False)

    def validation(self, validation_id: str, full: bool = True) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM validations WHERE validation_id=?", (validation_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("plan", "counts", "review"):
            d[k] = json.loads(d[k])
        # Stored figures are put in the current chart style when read (idempotent; PLAN_R4 B3).
        d["result"] = charts.style_result(json.loads(d["result"])) if full else None
        if not full:
            d.pop("result")
        d["seed"] = bool(d["seed"])
        return d

    def validations(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT validation_id FROM validations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [v for v in (self.validation(r["validation_id"], full=False) for r in rows) if v]

    def validation_for_thread(self, thread_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT validation_id FROM validations WHERE thread_id=? ORDER BY created_at", (thread_id,)).fetchall()
        return [v for v in (self.validation(r["validation_id"], full=False) for r in rows) if v]

    def set_review(self, validation_id: str, review: dict) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE validations SET review=? WHERE validation_id=?", (json.dumps(review), validation_id))

    def has_seed(self) -> bool:
        with self._con() as con:
            return con.execute("SELECT COUNT(*) FROM validations WHERE seed=1").fetchone()[0] > 0

    def delete_thread(self, thread_id: str) -> None:
        """Remove a conversation with its turns and its validations (the caller has checked it is not a seed)."""
        with self._lock, self._con() as con:
            con.execute("DELETE FROM turns WHERE thread_id=?", (thread_id,))
            con.execute("DELETE FROM validations WHERE thread_id=?", (thread_id,))
            con.execute("DELETE FROM threads WHERE thread_id=?", (thread_id,))

    # ------------------------------------------------------------------ R16 M8: findings register and maker-checker

    def findings(self) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT record FROM findings ORDER BY updated_at").fetchall()
        return [json.loads(r["record"]) for r in rows]

    def put_finding(self, record: dict[str, Any]) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO findings VALUES (?,?,?,?)", (record["finding_id"], record["scorecard_id"], json.dumps(record), time.time()))

    def conclusion(self, validation_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT record FROM conclusions WHERE validation_id=?", (validation_id,)).fetchone()
        return json.loads(r["record"]) if r else None

    def conclusions(self) -> dict[str, dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT validation_id, record FROM conclusions").fetchall()
        return {r["validation_id"]: json.loads(r["record"]) for r in rows}

    def put_conclusion(self, validation_id: str, record: dict[str, Any]) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO conclusions VALUES (?,?,?)", (validation_id, json.dumps(record), time.time()))
