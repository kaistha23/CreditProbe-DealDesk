"""The monitoring agent's own store (SQLite, WAL) at var/agents_v5/lenses/monitoring.sqlite.

  sets        a monitoring set per scope: proposed -> active -> retired; its metrics (definition, threshold, back-test),
              the lens it created or updated, and its schedule
  proposals   every state change the agent wants (a set to approve, a retire or re-threshold): pending -> approved |
              rejected | expired; maker (the agent, on behalf of the requester), approver role, expiry; per-metric
              accept / edit / reject marks made before the decision
  alerts      what each scheduled or on-demand run found: metric, period, severity, the two-line explanation, evidence
  runs        each run (A3): goal, plan, steps, findings, narrative; mirrored into the shared runtime once it is merged
  schedules   when the set runs (cron) and what it runs (the goal); mirrored into the runtime's schedule

The lens itself lives in the Lenses store (backend.lenses_v5.store); this store only records its id.
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

V5 = pathlib.Path(__file__).resolve().parents[3]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (
  set_id TEXT PRIMARY KEY, scope_key TEXT, book TEXT, filters TEXT, label TEXT, status TEXT, lens_id TEXT, schedule TEXT,
  metrics TEXT, version INTEGER, created_by TEXT, approved_by TEXT, created_at REAL, approved_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY, kind TEXT, set_id TEXT, scope_key TEXT, run_id TEXT, payload TEXT, status TEXT, maker TEXT,
  requested_by TEXT, approver_role TEXT, decided_by TEXT, decided_at REAL, note TEXT, created_at REAL, expires_at REAL, runtime_ref TEXT);
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY, set_id TEXT, run_id TEXT, metric_key TEXT, label TEXT, period TEXT, severity TEXT, status TEXT,
  value REAL, display TEXT, headline TEXT, explanation TEXT, detail TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, agent TEXT, goal TEXT, goal_type TEXT, scope_key TEXT, trigger TEXT, user TEXT, status TEXT,
  started_at REAL, finished_at REAL, body TEXT);
CREATE TABLE IF NOT EXISTS schedules (
  set_id TEXT PRIMARY KEY, cron TEXT, goal TEXT, next_at REAL, last_run_at REAL, last_period TEXT, enabled INTEGER, runtime_ref TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS notified (run_id TEXT PRIMARY KEY, at REAL);
CREATE INDEX IF NOT EXISTS alerts_set ON alerts(set_id, created_at);
CREATE INDEX IF NOT EXISTS runs_scope ON runs(scope_key, started_at);
"""

PROPOSAL_DAYS = 7


def store_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AGENTS_LENSES_STORE") or V5 / "var" / "agents_v5" / "lenses" / "monitoring.sqlite").expanduser().resolve()


class _Con(sqlite3.Connection):
    def __exit__(self, *exc):  # commit (sqlite3's behaviour) and close
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def _j(v: Any) -> str:
    return json.dumps(v, default=str)


class MStore:
    def __init__(self, path: pathlib.Path | None = None):
        self.path = pathlib.Path(path or store_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._con() as con:
            con.executescript(SCHEMA)

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None, factory=_Con)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    # ------------------------------------------------------------------ sets
    @staticmethod
    def _set(r: sqlite3.Row | None) -> dict[str, Any] | None:
        if r is None:
            return None
        d = dict(r)
        for k in ("filters", "metrics", "schedule"):
            d[k] = json.loads(d[k] or "null")
        return d

    def active_set(self, scope_key: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._set(con.execute("SELECT * FROM sets WHERE scope_key=? AND status='active' ORDER BY updated_at DESC LIMIT 1", (scope_key,)).fetchone())

    def get_set(self, set_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._set(con.execute("SELECT * FROM sets WHERE set_id=?", (set_id,)).fetchone())

    def sets(self, status: str = "") -> list[dict[str, Any]]:
        with self._con() as con:
            q = "SELECT * FROM sets" + (" WHERE status=?" if status else "") + " ORDER BY updated_at DESC"
            return [self._set(r) for r in con.execute(q, (status,) if status else ()).fetchall()]  # type: ignore[misc]

    def save_set(self, *, scope_key: str, book: str, filters: list[dict[str, Any]], label: str, metrics: list[dict[str, Any]],
                 lens_id: str, schedule: dict[str, Any] | None, created_by: str, approved_by: str) -> dict[str, Any]:
        """Activate a set for the scope: the previous active set (if any) is retired and its version carried on."""
        now = time.time()
        with self._lock, self._con() as con:
            prev = con.execute("SELECT set_id, version FROM sets WHERE scope_key=? AND status='active'", (scope_key,)).fetchone()
            ver = (prev["version"] + 1) if prev else 1
            if prev:
                con.execute("UPDATE sets SET status='retired', updated_at=? WHERE set_id=?", (now, prev["set_id"]))
            sid = "ms-" + uuid.uuid4().hex[:10]
            con.execute("INSERT INTO sets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, scope_key, book, _j(filters), label, "active", lens_id, _j(schedule), _j(metrics), ver, created_by, approved_by,
                         now, now, now))
        return self.get_set(sid)  # type: ignore[return-value]

    def update_set(self, set_id: str, **fields: Any) -> None:
        sets, args = ["updated_at=?"], [time.time()]
        for k, v in fields.items():
            if k in ("metrics", "schedule", "filters"):
                v = _j(v)
            sets.append(f"{k}=?")
            args.append(v)
        with self._lock, self._con() as con:
            con.execute(f"UPDATE sets SET {', '.join(sets)} WHERE set_id=?", (*args, set_id))

    # ------------------------------------------------------------------ proposals
    @staticmethod
    def _prop(r: sqlite3.Row | None) -> dict[str, Any] | None:
        if r is None:
            return None
        d = dict(r)
        d["payload"] = json.loads(d["payload"] or "{}")
        if d["status"] == "pending" and d["expires_at"] and d["expires_at"] < time.time():
            d["status"] = "expired"
        return d

    def add_proposal(self, *, kind: str, scope_key: str, payload: dict[str, Any], run_id: str, requested_by: str, approver_role: str,
                     set_id: str = "", maker: str = "agent:lenses-monitor", runtime_ref: str = "") -> dict[str, Any]:
        now = time.time()
        pid = "mp-" + uuid.uuid4().hex[:10]
        with self._lock, self._con() as con:
            # one pending proposal of a kind per scope: a newer plan supersedes the older one
            con.execute("UPDATE proposals SET status='superseded', note='A newer proposal replaced it.' WHERE scope_key=? AND kind=? AND status='pending'",
                        (scope_key, kind))
            con.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (pid, kind, set_id, scope_key, run_id, _j(payload), "pending", maker, requested_by, approver_role, "", None, "",
                         now, now + PROPOSAL_DAYS * 86400, runtime_ref))
        return self.proposal(pid)  # type: ignore[return-value]

    def proposal(self, pid: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._prop(con.execute("SELECT * FROM proposals WHERE proposal_id=?", (pid,)).fetchone())

    def proposals(self, scope_key: str = "", status: str = "") -> list[dict[str, Any]]:
        q, a = "SELECT * FROM proposals WHERE 1=1", []
        if scope_key:
            q += " AND scope_key=?"
            a.append(scope_key)
        q += " ORDER BY created_at DESC LIMIT 100"
        with self._con() as con:
            rows = [self._prop(r) for r in con.execute(q, a).fetchall()]
        return [r for r in rows if r and (not status or r["status"] == status)]

    def update_proposal(self, pid: str, **fields: Any) -> None:
        sets, args = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            args.append(_j(v) if k == "payload" else v)
        with self._lock, self._con() as con:
            con.execute(f"UPDATE proposals SET {', '.join(sets)} WHERE proposal_id=?", (*args, pid))

    # ------------------------------------------------------------------ alerts
    def add_alert(self, *, set_id: str, run_id: str, metric_key: str, label: str, period: str, severity: str, status: str, value: float | None,
                  display: str, headline: str, explanation: list[str], detail: dict[str, Any]) -> dict[str, Any]:
        aid = "ma-" + uuid.uuid4().hex[:10]
        with self._lock, self._con() as con:
            con.execute("INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, set_id, run_id, metric_key, label, period, severity, status, value, display, headline, _j(explanation), _j(detail),
                         time.time()))
        return {"alert_id": aid}

    def alerts(self, set_id: str = "", limit: int = 50, run_id: str = "") -> list[dict[str, Any]]:
        q, a = "SELECT * FROM alerts WHERE 1=1", []
        if set_id:
            q += " AND set_id=?"
            a.append(set_id)
        if run_id:
            q += " AND run_id=?"
            a.append(run_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        a.append(limit)
        with self._con() as con:
            out = []
            for r in con.execute(q, a).fetchall():
                d = dict(r)
                d["explanation"] = json.loads(d["explanation"] or "[]")
                d["detail"] = json.loads(d["detail"] or "{}")
                out.append(d)
        return out

    def delete_run_alerts(self, run_id: str) -> None:
        with self._lock, self._con() as con:
            con.execute("DELETE FROM alerts WHERE run_id=?", (run_id,))

    def notified(self, run_id: str) -> bool:
        with self._con() as con:
            return con.execute("SELECT 1 FROM notified WHERE run_id=?", (run_id,)).fetchone() is not None

    def mark_notified(self, run_id: str) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO notified VALUES (?,?)", (run_id, time.time()))

    def alert_history(self, set_id: str, metric_key: str) -> list[dict[str, Any]]:
        with self._con() as con:
            return [dict(r) for r in con.execute("SELECT period, severity, status, value FROM alerts WHERE set_id=? AND metric_key=? ORDER BY created_at",
                                                  (set_id, metric_key)).fetchall()]

    # ------------------------------------------------------------------ runs
    def save_run(self, run: dict[str, Any], scope_key: str) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (run["run_id"], run["agent"], run["goal"], run["goal_type"], scope_key, run.get("trigger", "on_demand"), run.get("user", ""),
                         run["status"], run["started_at"], run.get("finished_at") or 0, _j(run)))

    def run(self, run_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT body FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r["body"]) if r else None

    def runs(self, scope_key: str = "", limit: int = 20) -> list[dict[str, Any]]:
        q, a = "SELECT run_id, agent, goal, goal_type, scope_key, trigger, user, status, started_at, finished_at FROM runs", []
        if scope_key:
            q += " WHERE scope_key=?"
            a.append(scope_key)
        q += " ORDER BY started_at DESC LIMIT ?"
        a.append(limit)
        with self._con() as con:
            return [dict(r) for r in con.execute(q, a).fetchall()]

    # ------------------------------------------------------------------ schedules
    def set_schedule(self, set_id: str, cron: str, goal: str, next_at: float, runtime_ref: str = "") -> dict[str, Any]:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO schedules VALUES (?,?,?,?,?,?,?,?,?)",
                        (set_id, cron, goal, next_at, None, None, 1, runtime_ref, time.time()))
        return self.schedule(set_id)  # type: ignore[return-value]

    def schedule(self, set_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM schedules WHERE set_id=?", (set_id,)).fetchone()
        return dict(r) if r else None

    def schedules(self) -> list[dict[str, Any]]:
        with self._con() as con:
            return [dict(r) for r in con.execute("SELECT * FROM schedules WHERE enabled=1").fetchall()]

    def mark_ran(self, set_id: str, period: str, next_at: float) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE schedules SET last_run_at=?, last_period=?, next_at=? WHERE set_id=?", (time.time(), period, next_at, set_id))

    def disable_schedule(self, set_id: str) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE schedules SET enabled=0 WHERE set_id=?", (set_id,))


_STORE: MStore | None = None
_LOCK = threading.Lock()


def get() -> MStore:
    global _STORE
    with _LOCK:
        if _STORE is None or _STORE.path != store_path():
            _STORE = MStore()
        return _STORE
