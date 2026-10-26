"""The paper workspace store (SQLite). Writes only its own file; never a book, the engine's domain or Data Domains.

    workspaces  ws_id, kind (request | proposal), proposal_id, ref (request id / structure / given), title, customer, owner,
                owner_name, created, updated, status (draft | final), final_version, current_version
    versions    ws_id, n, paper (JSON), author, at, action (created | edit | structure | undo | refresh), instruction, section,
                change (JSON: {sections: [{key, heading, before, after}], status: pending | accepted | undone, fields?}), note
    turns       ws_id, turn_id, role (user | noor), text, author, at, version, section, meta (JSON)
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
CREATE TABLE IF NOT EXISTS workspaces (ws_id TEXT PRIMARY KEY, kind TEXT, proposal_id TEXT, ref TEXT, title TEXT, customer TEXT,
    owner TEXT, owner_name TEXT, created REAL, updated REAL, status TEXT, final_version INTEGER, current_version INTEGER, meta TEXT);
CREATE TABLE IF NOT EXISTS versions (ws_id TEXT, n INTEGER, paper TEXT, author TEXT, at REAL, action TEXT, instruction TEXT,
    section TEXT, change TEXT, note TEXT, PRIMARY KEY (ws_id, n));
CREATE TABLE IF NOT EXISTS turns (turn_id TEXT PRIMARY KEY, ws_id TEXT, role TEXT, text TEXT, author TEXT, at REAL, version INTEGER,
    section TEXT, meta TEXT);
CREATE INDEX IF NOT EXISTS turns_ws ON turns (ws_id, at);
"""


def path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("PAPERWS_STORE") or V5 / "var" / "paperws" / "paperws.sqlite").expanduser()


class Store:
    def __init__(self, p: str | pathlib.Path | None = None) -> None:
        p = str(p or path())
        if p != ":memory:":
            pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
        self.path = p
        self._db = sqlite3.connect(p, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.fetchall()

    # ------------------------------------------------------------ workspaces
    def create(self, kind: str, proposal_id: str, ref: str, title: str, customer: str, owner: str, owner_name: str,
               meta: dict[str, Any] | None = None) -> str:
        ws_id = "PW-" + uuid.uuid4().hex[:10].upper()
        now = time.time()
        self._q("INSERT INTO workspaces VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ws_id, kind, proposal_id, ref, title, customer, owner, owner_name, now, now, "draft", None, 0, json.dumps(meta or {})))
        return ws_id

    def get(self, ws_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM workspaces WHERE ws_id=?", (ws_id,))
        return _ws(rows[0]) if rows else None

    def update(self, ws_id: str, **cols: Any) -> None:
        cols["updated"] = time.time()
        sets = ", ".join(f"{k}=?" for k in cols)
        self._q(f"UPDATE workspaces SET {sets} WHERE ws_id=?", (*[json.dumps(v) if k == "meta" else v for k, v in cols.items()], ws_id))

    def listing(self, proposal_id: str | None = None, kind: str | None = None, owner: str | None = None, ref: str | None = None,
                limit: int = 50) -> list[dict[str, Any]]:
        where, args = [], []
        for col, v in (("proposal_id", proposal_id), ("kind", kind), ("owner", owner), ("ref", ref)):
            if v:
                where.append(f"{col}=?")
                args.append(v)
        sql = "SELECT * FROM workspaces" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated DESC LIMIT ?"
        return [_ws(r) for r in self._q(sql, (*args, limit))]

    # ------------------------------------------------------------ versions
    def add_version(self, ws_id: str, paper: dict[str, Any], author: str, action: str, instruction: str = "", section: str = "",
                    change: dict[str, Any] | None = None, note: str = "") -> int:
        with self._lock:
            cur = self._db.execute("SELECT COALESCE(MAX(n), 0) FROM versions WHERE ws_id=?", (ws_id,))
            n = int(cur.fetchone()[0]) + 1
            self._db.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (ws_id, n, json.dumps(paper, ensure_ascii=False, default=str), author, time.time(), action, instruction, section,
                              json.dumps(change) if change is not None else None, note))
            self._db.execute("UPDATE workspaces SET current_version=?, updated=? WHERE ws_id=?", (n, time.time(), ws_id))
            self._db.commit()
        return n

    def version(self, ws_id: str, n: int | None = None) -> dict[str, Any] | None:
        if n is None:
            rows = self._q("SELECT * FROM versions WHERE ws_id=? ORDER BY n DESC LIMIT 1", (ws_id,))
        else:
            rows = self._q("SELECT * FROM versions WHERE ws_id=? AND n=?", (ws_id, n))
        return _ver(rows[0], with_paper=True) if rows else None

    def versions(self, ws_id: str) -> list[dict[str, Any]]:
        return [_ver(r) for r in self._q("SELECT * FROM versions WHERE ws_id=? ORDER BY n", (ws_id,))]

    def set_change(self, ws_id: str, n: int, change: dict[str, Any]) -> None:
        self._q("UPDATE versions SET change=? WHERE ws_id=? AND n=?", (json.dumps(change), ws_id, n))

    # ------------------------------------------------------------ turns
    def add_turn(self, ws_id: str, role: str, text: str, author: str = "", version: int | None = None, section: str = "",
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
        tid = "PT-" + uuid.uuid4().hex[:10]
        at = time.time()
        self._q("INSERT INTO turns VALUES (?,?,?,?,?,?,?,?,?)", (tid, ws_id, role, text, author, at, version, section, json.dumps(meta or {}, default=str)))
        self._q("UPDATE workspaces SET updated=? WHERE ws_id=?", (at, ws_id))
        return {"turn_id": tid, "role": role, "text": text, "author": author, "at": at, "version": version, "section": section, "meta": meta or {}}

    def turns(self, ws_id: str) -> list[dict[str, Any]]:
        return [{"turn_id": r["turn_id"], "role": r["role"], "text": r["text"], "author": r["author"], "at": r["at"], "version": r["version"],
                 "section": r["section"], "meta": json.loads(r["meta"] or "{}")}
                for r in self._q("SELECT * FROM turns WHERE ws_id=? ORDER BY at, rowid", (ws_id,))]


def _ws(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["meta"] = json.loads(d.get("meta") or "{}")
    return d


def _ver(r: sqlite3.Row, with_paper: bool = False) -> dict[str, Any]:
    d = {k: r[k] for k in ("ws_id", "n", "author", "at", "action", "instruction", "section", "note")}
    d["change"] = json.loads(r["change"]) if r["change"] else None
    if with_paper:
        d["paper"] = json.loads(r["paper"])
    return d


_STORE: Store | None = None
_SLOCK = threading.Lock()


def default() -> Store:
    """One store per process (tests: reset() after pointing PAPERWS_STORE elsewhere)."""
    global _STORE
    with _SLOCK:
        if _STORE is None or _STORE.path != str(path()):
            _STORE = Store()
        return _STORE


def reset() -> None:
    global _STORE
    with _SLOCK:
        _STORE = None
