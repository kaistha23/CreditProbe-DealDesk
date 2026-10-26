"""The conversational thread store (forked from the Cockpit's `run_store.py`, generic).

SQLite (WAL). One database per service (`CONVO_STORE` or the path the module
gives). Tables:
  threads    domain, scope (JSON), owner, team, title, state (JSON, the domain's own)
  runs       one per turn: question, mode (ask | execute), forward-only state, answer, error
  events     the run's events, committed before they are streamed
  turns      the settled transcript (question + answer), written before the run settles
  artifacts  every query result and tool output of a run (the evidence its figures come from)
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Any

from backend.convo import events as ev
from backend.convo import states as st

V5 = pathlib.Path(__file__).resolve().parents[2]


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
  thread_id TEXT PRIMARY KEY, domain TEXT, scope TEXT, owner TEXT, team TEXT, title TEXT, origin TEXT,
  created_at REAL, updated_at REAL, state TEXT, archived INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS threads_by_domain ON threads(domain, updated_at);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, thread_id TEXT, owner TEXT, question TEXT, mode TEXT, state TEXT, version INTEGER,
  created_at REAL, updated_at REAL, answer TEXT, error_code TEXT, error TEXT, idem_key TEXT);
CREATE INDEX IF NOT EXISTS runs_by_state ON runs(state, created_at);
CREATE INDEX IF NOT EXISTS runs_by_thread ON runs(thread_id, created_at);
CREATE TABLE IF NOT EXISTS events (run_id TEXT, seq INTEGER, at REAL, payload TEXT, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS turns (
  thread_id TEXT, ordinal INTEGER, run_id TEXT UNIQUE, question TEXT, answer TEXT, created_at REAL,
  PRIMARY KEY (thread_id, ordinal));
CREATE TABLE IF NOT EXISTS artifacts (
  run_id TEXT, artifact_id TEXT, kind TEXT, payload TEXT, created_at REAL, PRIMARY KEY (run_id, artifact_id));
"""


def default_path(name: str = "convo") -> pathlib.Path:
    return pathlib.Path(os.environ.get("CONVO_STORE") or (V5 / "var" / "convo" / f"{name}.sqlite"))


class BusyError(RuntimeError):
    def __init__(self, run_id: str):
        super().__init__(run_id)
        self.run_id = run_id


class Store:
    def __init__(self, path: pathlib.Path | str | None = None, prefix: str = "cv"):
        self.path = pathlib.Path(path or default_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self._lock = threading.RLock()
        with self._con() as con:
            con.executescript(SCHEMA)

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None, factory=_ClosingConnection)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    # ------------------------------------------------------------ threads
    def create_thread(self, *, domain: str, scope: dict, owner: str = "", team: str = "", title: str = "",
                      origin: str = "chat", state: dict | None = None) -> dict[str, Any]:
        tid = f"{self.prefix}t-" + uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock, self._con() as con:
            con.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,0)",
                        (tid, domain, json.dumps(scope or {}), owner, team, title or "New thread", origin, now, now,
                         json.dumps(state or {})))
        return self.thread(tid)

    def thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["scope"] = json.loads(d["scope"] or "{}")
        d["state"] = json.loads(d["state"] or "{}")
        return d

    def save_thread(self, thread_id: str, *, state: dict | None = None, title: str | None = None,
                    scope: dict | None = None) -> None:
        sets, args = ["updated_at=?"], [time.time()]
        if state is not None:
            sets.append("state=?")
            args.append(json.dumps(state))
        if title is not None:
            sets.append("title=?")
            args.append(title)
        if scope is not None:
            sets.append("scope=?")
            args.append(json.dumps(scope))
        with self._lock, self._con() as con:
            con.execute(f"UPDATE threads SET {', '.join(sets)} WHERE thread_id=?", (*args, thread_id))

    def threads(self, domain: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = "SELECT thread_id, domain, scope, owner, team, title, origin, created_at, updated_at FROM threads WHERE archived=0"
        args: list[Any] = []
        if domain:
            q += " AND domain=?"
            args.append(domain)
        q += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._con() as con:
            rows = con.execute(q, args).fetchall()
        return [{**dict(r), "scope": json.loads(r["scope"] or "{}")} for r in rows]

    # ------------------------------------------------------------ runs
    def accept_run(self, thread_id: str, owner: str, question: str, mode: str = "ask", idem_key: str = "") -> dict[str, Any]:
        with self._lock, self._con() as con:
            if idem_key:
                hit = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND idem_key=?", (thread_id, idem_key)).fetchone()
                if hit:
                    return self.run(hit["run_id"]) | {"replayed": True}
            busy = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND state IN (?,?)",
                               (thread_id, st.ACCEPTED, st.RUNNING)).fetchone()
            if busy:
                raise BusyError(busy["run_id"])
            rid = f"{self.prefix}r-" + uuid.uuid4().hex[:12]
            now = time.time()
            con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, thread_id, owner, question, mode, st.ACCEPTED, 0, now, now, None, None, None, idem_key))
        self.append_event(rid, ev.RUN_ACCEPTED, stage="accepted", status="accepted", message="Question received")
        return self.run(rid)

    def run(self, run_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            last = con.execute("SELECT MAX(seq) FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
        if not r:
            return None
        d = dict(r)
        d["answer"] = json.loads(d["answer"]) if d["answer"] else None
        d["terminal"] = d["state"] in st.TERMINAL
        d["last_event_seq"] = int(last or 0)
        return d

    def claim_next(self) -> dict[str, Any] | None:
        with self._lock, self._con() as con:
            r = con.execute("SELECT run_id, version FROM runs WHERE state=? ORDER BY created_at LIMIT 1",
                            (st.ACCEPTED,)).fetchone()
            if not r:
                return None
            n = con.execute("UPDATE runs SET state=?, version=version+1, updated_at=? WHERE run_id=? AND version=?",
                            (st.RUNNING, time.time(), r["run_id"], r["version"])).rowcount
        return self.run(r["run_id"]) if n else None

    def settle(self, run_id: str, state: str, answer: dict | None = None, error_code: str = "", error: str = "") -> bool:
        run = self.run(run_id)
        if run is None or not st.can_move(run["state"], state):
            return False
        with self._lock, self._con() as con:
            n = con.execute("UPDATE runs SET state=?, version=version+1, updated_at=?, answer=?, error_code=?, error=? "
                            "WHERE run_id=? AND version=?",
                            (state, time.time(), json.dumps(answer) if answer is not None else None, error_code or None,
                             error or None, run_id, run["version"])).rowcount
        return bool(n)

    def recover(self) -> int:
        with self._lock, self._con() as con:
            rows = con.execute("SELECT run_id FROM runs WHERE state=?", (st.RUNNING,)).fetchall()
        for r in rows:
            self.append_event(r["run_id"], ev.RUN_FAILED, status="failed",
                              message="The service restarted while this turn was running. Ask again.")
            self.settle(r["run_id"], st.FAILED, error_code="CONVO_INTERNAL", error="Service restarted.")
        return len(rows)

    def active_run(self, thread_id: str) -> str | None:
        with self._con() as con:
            r = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND state IN (?,?) ORDER BY created_at DESC LIMIT 1",
                            (thread_id, st.ACCEPTED, st.RUNNING)).fetchone()
        return r["run_id"] if r else None

    # ------------------------------------------------------------ events
    def append_event(self, run_id: str, event_type: str, *, stage: str = "", status: str = "", message: str = "",
                     elapsed_ms: int = 0, detail: dict | None = None) -> ev.Event:
        with self._lock, self._con() as con:
            seq = int(con.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0])
            e = ev.Event(seq=seq, event_type=event_type, stage=stage, status=status, public_message=message,
                         elapsed_ms=elapsed_ms, detail=detail or {})
            con.execute("INSERT INTO events VALUES (?,?,?,?)", (run_id, seq, time.time(), json.dumps(e.to_dict())))
        return e

    def events_since(self, run_id: str, cursor: int = 0) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT payload FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, cursor)).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ------------------------------------------------------------ turns
    def append_turn(self, thread_id: str, run_id: str, question: str, answer: dict) -> int:
        with self._lock, self._con() as con:
            hit = con.execute("SELECT ordinal FROM turns WHERE run_id=?", (run_id,)).fetchone()
            if hit:
                return int(hit["ordinal"])
            n = int(con.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM turns WHERE thread_id=?", (thread_id,)).fetchone()[0])
            con.execute("INSERT INTO turns VALUES (?,?,?,?,?,?)", (thread_id, n, run_id, question, json.dumps(answer), time.time()))
            con.execute("UPDATE threads SET updated_at=? WHERE thread_id=?", (time.time(), thread_id))
        return n

    def turns(self, thread_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT ordinal, run_id, question, answer, created_at FROM turns WHERE thread_id=? "
                               "ORDER BY ordinal", (thread_id,)).fetchall()
        return [{**dict(r), "answer": json.loads(r["answer"])} for r in rows]

    # ------------------------------------------------------------ artifacts
    def put_artifact(self, run_id: str, artifact_id: str, kind: str, payload: dict) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                        (run_id, artifact_id, kind, json.dumps(payload, default=str), time.time()))

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT artifact_id, kind, payload FROM artifacts WHERE run_id=? ORDER BY created_at",
                               (run_id,)).fetchall()
        return [{"artifact_id": r["artifact_id"], "kind": r["kind"], **json.loads(r["payload"])} for r in rows]
