"""The Lenses store (SQLite, WAL) at var/lenses_v5/lenses.sqlite -- the `lenses` data domain (PLAN_R5 L2).

  lenses     one per lens: owner, team, name, description, tags, book, kind (lens | template), current version,
             undo/redo cursor, convo thread, saved flag, thumbnail (KPI digest), schedule
  versions   every spec the lens has had (spec JSON, what changed, who, when); undo/redo moves the cursor
  shares     who a lens was shared with (users or teams; the share itself travels through Mail)
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Any

from backend.lenses_v5 import paths


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
CREATE TABLE IF NOT EXISTS lenses (
  lens_id TEXT PRIMARY KEY, owner TEXT, team TEXT, name TEXT, description TEXT, tags TEXT, book TEXT, kind TEXT,
  version INTEGER, head INTEGER, thread_id TEXT, saved INTEGER DEFAULT 0, thumb TEXT, schedule TEXT,
  created_at REAL, updated_at REAL, archived INTEGER DEFAULT 0, template_key TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS versions (
  lens_id TEXT, version INTEGER, spec TEXT, change TEXT, author TEXT, created_at REAL, PRIMARY KEY (lens_id, version));
CREATE TABLE IF NOT EXISTS shares (
  lens_id TEXT, kind TEXT, target TEXT, by_user TEXT, created_at REAL, PRIMARY KEY (lens_id, kind, target));
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

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
        if r is None:
            return None
        d = dict(r)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["thumb"] = json.loads(d.get("thumb") or "null")
        d["schedule"] = json.loads(d.get("schedule") or "null")
        d["saved"] = bool(d["saved"])
        return d

    # ------------------------------------------------------------------ lenses
    def create(self, *, owner: str, team: str, spec: dict[str, Any], kind: str = "lens", name: str = "", description: str = "",
               tags: list[str] | None = None, thread_id: str = "", saved: bool = False, template_key: str = "",
               change: str = "Built from the request", at: float | None = None) -> dict[str, Any]:
        lid = ("tpl-" if kind == "template" else "lens-") + uuid.uuid4().hex[:10]
        now = at or time.time()
        with self._lock, self._con() as con:
            con.execute("INSERT INTO lenses (lens_id, owner, team, name, description, tags, book, kind, version, head, thread_id, saved, thumb,"
                        " schedule, created_at, updated_at, archived, template_key) VALUES (?,?,?,?,?,?,?,?,1,1,?,?,NULL,NULL,?,?,0,?)",
                        (lid, owner, team, name or spec.get("title", "Lens"), description, json.dumps(tags or []), spec["book"], kind,
                         thread_id, int(saved), now, now, template_key))
            con.execute("INSERT INTO versions VALUES (?,?,?,?,?,?)", (lid, 1, json.dumps(spec), change, owner, now))
        return self.lens(lid)  # type: ignore[return-value]

    def lens(self, lens_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._row(con.execute("SELECT * FROM lenses WHERE lens_id=? AND archived=0", (lens_id,)).fetchone())

    def lenses(self, kind: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
        with self._con() as con:
            if kind:
                rows = con.execute("SELECT * FROM lenses WHERE archived=0 AND kind=? ORDER BY updated_at DESC LIMIT ?", (kind, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM lenses WHERE archived=0 ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def template(self, key: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._row(con.execute("SELECT * FROM lenses WHERE kind='template' AND template_key=? AND archived=0", (key,)).fetchone())

    def keyed(self, kind: str, key: str) -> dict[str, Any] | None:
        with self._con() as con:
            return self._row(con.execute("SELECT * FROM lenses WHERE kind=? AND template_key=? AND archived=0", (kind, key)).fetchone())

    def update(self, lens_id: str, **fields: Any) -> None:
        allowed = {"name", "description", "tags", "thread_id", "saved", "thumb", "schedule", "book"}
        sets, args = ["updated_at=?"], [time.time()]
        for k, v in fields.items():
            if k not in allowed:
                continue
            sets.append(f"{k}=?")
            args.append(json.dumps(v) if k in ("tags", "thumb", "schedule") else int(v) if k == "saved" else v)
        with self._lock, self._con() as con:
            con.execute(f"UPDATE lenses SET {', '.join(sets)} WHERE lens_id=?", (*args, lens_id))

    def archive(self, lens_id: str) -> None:
        with self._lock, self._con() as con:
            con.execute("UPDATE lenses SET archived=1, updated_at=? WHERE lens_id=?", (time.time(), lens_id))

    # ------------------------------------------------------------------ versions, undo, redo
    def spec(self, lens_id: str, version: int | None = None) -> dict[str, Any]:
        lens = self.lens(lens_id)
        if lens is None:
            raise KeyError(lens_id)
        v = version or lens["head"]
        with self._con() as con:
            r = con.execute("SELECT spec FROM versions WHERE lens_id=? AND version=?", (lens_id, v)).fetchone()
        return json.loads(r["spec"])

    def commit(self, lens_id: str, spec: dict[str, Any], change: str, author: str) -> int:
        """A new version after the head; anything beyond the head (undone versions) is dropped, as editors do."""
        with self._lock, self._con() as con:
            head = con.execute("SELECT head FROM lenses WHERE lens_id=?", (lens_id,)).fetchone()["head"]
            con.execute("DELETE FROM versions WHERE lens_id=? AND version>?", (lens_id, head))
            v = head + 1
            con.execute("INSERT INTO versions VALUES (?,?,?,?,?,?)", (lens_id, v, json.dumps(spec), change, author, time.time()))
            con.execute("UPDATE lenses SET version=?, head=?, book=?, updated_at=? WHERE lens_id=?", (v, v, spec["book"], time.time(), lens_id))
        return v

    def move_head(self, lens_id: str, step: int) -> int:
        with self._lock, self._con() as con:
            r = con.execute("SELECT head, version FROM lenses WHERE lens_id=?", (lens_id,)).fetchone()
            nv = r["head"] + step
            if nv < 1 or nv > r["version"]:
                return r["head"]
            book = json.loads(con.execute("SELECT spec FROM versions WHERE lens_id=? AND version=?", (lens_id, nv)).fetchone()["spec"])["book"]
            con.execute("UPDATE lenses SET head=?, book=?, updated_at=? WHERE lens_id=?", (nv, book, time.time(), lens_id))
            return nv

    def restore(self, lens_id: str, version: int, author: str) -> int:
        spec = self.spec(lens_id, version)
        return self.commit(lens_id, spec, f"Restored version {version}", author)

    def versions(self, lens_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT version, change, author, created_at FROM versions WHERE lens_id=? ORDER BY version", (lens_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ shares
    def share(self, lens_id: str, kind: str, target: str, by: str) -> None:
        with self._lock, self._con() as con:
            con.execute("INSERT OR REPLACE INTO shares VALUES (?,?,?,?,?)", (lens_id, kind, target, by, time.time()))

    def shares(self, lens_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            return [dict(r) for r in con.execute("SELECT kind, target, by_user, created_at FROM shares WHERE lens_id=?", (lens_id,)).fetchall()]

    def shared_with(self, username: str, team: str) -> set[str]:
        with self._con() as con:
            rows = con.execute("SELECT lens_id FROM shares WHERE (kind='user' AND target=?) OR (kind='team' AND target=?)", (username, team)).fetchall()
        return {r["lens_id"] for r in rows}
