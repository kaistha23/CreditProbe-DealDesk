"""The What-If thread store (forked from the Cockpit's `run_store.py`, re-keyed and slimmed).

SQLite (WAL) at var/whatif/whatif_chat.sqlite. Tables:
  threads    one per conversation: owner, team, book, period, Early Warning cohort, title, state (JSON:
             the current scenario's steps, the chosen method, a pending scenario, the undo history)
  runs       one per turn being answered: question, state (forward-only, compare-and-swap on version),
             answer (JSON), error
  events     the run's event sequence (committed before it is streamed)
  turns      the settled transcript: question + answer per ordinal (written before the run settles)
  scenarios  the scenario repository: saved scenarios with owner, date, method, ECL impact and tags,
             plus the standard library
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

from backend.whatif_v5 import paths
from backend.whatif_v5.chat import events as ev
from backend.whatif_v5.chat import states as st


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
  thread_id TEXT PRIMARY KEY, owner TEXT, team TEXT, domain TEXT, period TEXT, cohort_id TEXT,
  title TEXT, origin TEXT, created_at REAL, updated_at REAL, state TEXT, archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, thread_id TEXT, owner TEXT, question TEXT, state TEXT, version INTEGER,
  created_at REAL, updated_at REAL, answer TEXT, error_code TEXT, error TEXT, idem_key TEXT);
CREATE INDEX IF NOT EXISTS runs_by_state ON runs(state, created_at);
CREATE INDEX IF NOT EXISTS runs_by_thread ON runs(thread_id, created_at);
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT, seq INTEGER, at REAL, payload TEXT, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS turns (
  thread_id TEXT, ordinal INTEGER, run_id TEXT UNIQUE, question TEXT, answer TEXT, created_at REAL,
  PRIMARY KEY (thread_id, ordinal));
CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id TEXT PRIMARY KEY, owner TEXT, team TEXT, name TEXT, description TEXT, domain TEXT, period TEXT,
  method TEXT, scenario TEXT, summary TEXT, ecl_before REAL, ecl_after REAL, change REAL, change_pct REAL,
  tags TEXT, created_at REAL, standard INTEGER DEFAULT 0, thread_id TEXT, cohort_id TEXT);
CREATE TABLE IF NOT EXISTS report_items (
  item_id TEXT PRIMARY KEY, owner TEXT, kind TEXT, ref TEXT, name TEXT, domain TEXT, method TEXT,
  scenario TEXT, change REAL, added_at REAL);
"""


def db_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("WHATIF_CHAT_STORE") or (paths.V5 / "var" / "whatif" / "whatif_chat.sqlite"))


class Store:
    def __init__(self, path: pathlib.Path | None = None):
        self.path = pathlib.Path(path or db_path())
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

    # ------------------------------------------------------------ threads
    def create_thread(self, *, owner: str, team: str, domain: str, period: str, cohort_id: str = "",
                      title: str = "", origin: str = "chat", state: dict | None = None) -> dict[str, Any]:
        tid = "wt-" + uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock, self._con() as con:
            con.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,0)",
                        (tid, owner, team, domain, period, cohort_id, title or "New What-If thread", origin, now, now,
                         json.dumps(state or {})))
        return self.thread(tid)

    def thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["state"] = json.loads(d["state"] or "{}")
        return d

    def save_thread_state(self, thread_id: str, state: dict, title: str | None = None, period: str | None = None) -> None:
        with self._lock, self._con() as con:
            sets, args = ["state=?", "updated_at=?"], [json.dumps(state), time.time()]
            if title is not None:
                sets.append("title=?")
                args.append(title)
            if period is not None:
                sets.append("period=?")
                args.append(period)
            con.execute(f"UPDATE threads SET {', '.join(sets)} WHERE thread_id=?", (*args, thread_id))

    def rename(self, thread_id: str, title: str) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE threads SET title=?, updated_at=? WHERE thread_id=?", (title, time.time(), thread_id))

    def threads(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT thread_id, owner, team, domain, period, cohort_id, title, origin, created_at, "
                               "updated_at FROM threads WHERE archived=0 ORDER BY updated_at DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ runs
    def accept_run(self, thread_id: str, owner: str, question: str, idem_key: str = "") -> dict[str, Any]:
        with self._lock, self._con() as con:
            if idem_key:
                hit = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND idem_key=?", (thread_id, idem_key)).fetchone()
                if hit:
                    return self.run(hit["run_id"]) | {"replayed": True}
            busy = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND state IN (?,?)",
                               (thread_id, st.ACCEPTED, st.RUNNING)).fetchone()
            if busy:
                raise BusyError(busy["run_id"])
            rid = "wq-" + uuid.uuid4().hex[:12]
            now = time.time()
            con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, thread_id, owner, question, st.ACCEPTED, 0, now, now, None, None, None, idem_key))
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

    def settle(self, run_id: str, state: str, answer: dict | None = None, error_code: str = "", error: str = "") -> None:
        run = self.run(run_id)
        if run is None or not st.can_move(run["state"], state):
            return
        with self._lock, self._con() as con:
            con.execute("UPDATE runs SET state=?, version=version+1, updated_at=?, answer=?, error_code=?, error=? "
                        "WHERE run_id=? AND version=?",
                        (state, time.time(), json.dumps(answer) if answer is not None else None, error_code or None,
                         error or None, run_id, run["version"]))

    def recover(self) -> int:
        """Runs left RUNNING by a stopped service are failed (stated), never left hanging."""
        with self._lock, self._con() as con:
            rows = con.execute("SELECT run_id FROM runs WHERE state=?", (st.RUNNING,)).fetchall()
        for r in rows:
            self.append_event(r["run_id"], ev.RUN_FAILED, status="failed",
                              message="The service restarted while this turn was running. Ask again.")
            self.settle(r["run_id"], st.FAILED, error_code="WHATIF_INTERNAL", error="Service restarted.")
        return len(rows)

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
            con.execute("INSERT INTO turns VALUES (?,?,?,?,?,?)",
                        (thread_id, n, run_id, question, json.dumps(answer), time.time()))
            con.execute("UPDATE threads SET updated_at=? WHERE thread_id=?", (time.time(), thread_id))
        return n

    def turns(self, thread_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT ordinal, run_id, question, answer, created_at FROM turns WHERE thread_id=? "
                               "ORDER BY ordinal", (thread_id,)).fetchall()
        return [{**dict(r), "answer": json.loads(r["answer"])} for r in rows]

    def active_run(self, thread_id: str) -> str | None:
        with self._con() as con:
            r = con.execute("SELECT run_id FROM runs WHERE thread_id=? AND state IN (?,?) ORDER BY created_at DESC LIMIT 1",
                            (thread_id, st.ACCEPTED, st.RUNNING)).fetchone()
        return r["run_id"] if r else None

    # ------------------------------------------------------------ scenario repository
    def save_scenario(self, row: dict[str, Any]) -> dict[str, Any]:
        sid = row.get("scenario_id") or ("sc-" + uuid.uuid4().hex[:10])
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, row.get("owner", ""), row.get("team", ""), row["name"], row.get("description", ""),
                         row["domain"], row["period"], row.get("method", ""), json.dumps(row["scenario"]),
                         json.dumps(row.get("summary") or {}), row.get("ecl_before"), row.get("ecl_after"),
                         row.get("change"), row.get("change_pct"), json.dumps(row.get("tags") or []),
                         row.get("created_at") or time.time(), int(bool(row.get("standard"))), row.get("thread_id", ""),
                         row.get("cohort_id", "")))
        return self.scenario(sid)

    def scenario(self, sid: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM scenarios WHERE scenario_id=?", (sid,)).fetchone()
        return _scn(r) if r else None

    def scenarios(self, standard: bool | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM scenarios"
        args: tuple = ()
        if standard is not None:
            q += " WHERE standard=?"
            args = (int(standard),)
        q += " ORDER BY standard DESC, CASE WHEN standard=1 THEN rowid END ASC, created_at DESC"
        with self._con() as con:
            return [_scn(r) for r in con.execute(q, args).fetchall()]

    # ------------------------------------------------------------ report pack
    def add_report_item(self, row: dict[str, Any]) -> dict[str, Any]:
        iid = "ri-" + uuid.uuid4().hex[:10]
        with self._lock, self._con() as con:
            con.execute("INSERT INTO report_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (iid, row.get("owner", ""), row["kind"], row["ref"], row["name"], row["domain"], row["method"],
                         json.dumps(row["scenario"]), row.get("change"), time.time()))
        return next(i for i in self.report_items(row.get("owner", ""), all_=True) if i["item_id"] == iid)

    def report_items(self, owner: str, all_: bool = False) -> list[dict[str, Any]]:
        with self._con() as con:
            if all_:
                rows = con.execute("SELECT * FROM report_items ORDER BY added_at").fetchall()
            else:
                rows = con.execute("SELECT * FROM report_items WHERE owner=? ORDER BY added_at", (owner,)).fetchall()
        return [{**dict(r), "scenario": json.loads(r["scenario"])} for r in rows]

    def remove_report_item(self, item_id: str, owner: str) -> None:
        with self._lock, self._con() as con:
            con.execute("DELETE FROM report_items WHERE item_id=? AND owner=?", (item_id, owner))

    def delete_scenario(self, sid: str) -> None:
        with self._lock, self._con() as con:
            con.execute("DELETE FROM scenarios WHERE scenario_id=? AND standard=0", (sid,))


def _scn(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["scenario"] = json.loads(d["scenario"])
    d["summary"] = json.loads(d["summary"] or "{}")
    d["tags"] = json.loads(d["tags"] or "[]")
    d["standard"] = bool(d["standard"])
    return d


class BusyError(RuntimeError):
    def __init__(self, run_id: str):
        super().__init__(run_id)
        self.run_id = run_id
