"""The Deal Desk thread store (SQLite): the conversation per proposal, its state
(current and recommended terms, the last optimisation), and saved analyses.
Writes only its own file; the books and the engine's domain are never written."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from backend.dealdesk_thread import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (turn_id TEXT PRIMARY KEY, proposal_id TEXT, owner TEXT, question TEXT,
                                  answer TEXT, created REAL);
CREATE TABLE IF NOT EXISTS state (proposal_id TEXT PRIMARY KEY, body TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS analyses (analysis_id TEXT PRIMARY KEY, proposal_id TEXT, owner TEXT, team TEXT, name TEXT,
                                     body TEXT, created REAL);
CREATE TABLE IF NOT EXISTS proposals (proposal_id TEXT PRIMARY KEY, body TEXT, created REAL);
CREATE TABLE IF NOT EXISTS desk_threads (thread_id TEXT PRIMARY KEY, owner TEXT, title TEXT, created REAL, updated REAL);
"""

#: R14 n (K16): one desk thread per new question. Its turns are kept under `desk:<thread_id>`; the old fixed id
#: "desk" is gone (its turns stay readable as history, never appended to).
DESK_PREFIX = "desk:"


def desk_key(thread_id: str) -> str:
    return DESK_PREFIX + thread_id


def title_of(question: str, limit: int = 80) -> str:
    """A thread title from its first question: one line, at most `limit` characters, cut at a word."""
    t = " ".join(str(question or "").split())
    if len(t) <= limit:
        return t or "Deal Desk thread"
    cut = t[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"



class Store:
    def __init__(self, path: str | None = None) -> None:
        p = path or str(paths.store())
        if p != ":memory:":
            import pathlib
            pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
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

    # turns
    def add_turn(self, proposal_id: str, owner: str, question: str, answer: dict) -> str:
        tid = "DT-" + uuid.uuid4().hex[:10]
        self._q("INSERT INTO turns VALUES (?,?,?,?,?,?)", (tid, proposal_id, owner, question, json.dumps(answer, default=str), time.time()))
        return tid

    def turns(self, proposal_id: str) -> list[dict]:
        rows = self._q("SELECT * FROM turns WHERE proposal_id=? ORDER BY created", (proposal_id,))
        return [{"turn_id": r["turn_id"], "question": r["question"], "owner": r["owner"], "created": r["created"],
                 "answer": json.loads(r["answer"])} for r in rows]

    def recent_turns(self, limit: int = 50, owner: str | None = None) -> list[dict]:
        """The latest turns across every proposal (newest first), optionally one user's."""
        if owner:
            rows = self._q("SELECT * FROM turns WHERE owner=? ORDER BY created DESC LIMIT ?", (owner, limit))
        else:
            rows = self._q("SELECT * FROM turns ORDER BY created DESC LIMIT ?", (limit,))
        return [{"turn_id": r["turn_id"], "proposal_id": r["proposal_id"], "question": r["question"], "owner": r["owner"],
                 "created": r["created"], "answer": json.loads(r["answer"])} for r in rows]

    # desk threads (R14 n, K16): one per new question asked on the landing, the Noor panel or the Cockpit Ask
    def create_desk_thread(self, owner: str, question: str) -> dict:
        tid = "DK-" + uuid.uuid4().hex[:10]
        now = time.time()
        self._q("INSERT INTO desk_threads VALUES (?,?,?,?,?)", (tid, owner, title_of(question), now, now))
        return self.desk_thread(tid) or {}

    def desk_thread(self, thread_id: str) -> dict | None:
        rows = self._q("SELECT * FROM desk_threads WHERE thread_id=?", (thread_id,))
        if not rows:
            return None
        r = rows[0]
        n = self._q("SELECT COUNT(*) AS n FROM turns WHERE proposal_id=?", (desk_key(thread_id),))[0]["n"]
        return {"thread_id": r["thread_id"], "owner": r["owner"], "title": r["title"], "created": r["created"],
                "updated": r["updated"], "turns": int(n), "href": f"/deal-desk/thread/{r['thread_id']}"}

    def touch_desk_thread(self, thread_id: str) -> None:
        self._q("UPDATE desk_threads SET updated=? WHERE thread_id=?", (time.time(), thread_id))

    def desk_threads(self, owner: str | None = None, limit: int = 20) -> list[dict]:
        """Newest first (the top of Recent work is the latest thread)."""
        if owner:
            rows = self._q("SELECT thread_id FROM desk_threads WHERE owner=? ORDER BY updated DESC, created DESC LIMIT ?",
                           (owner, limit))
        else:
            rows = self._q("SELECT thread_id FROM desk_threads ORDER BY updated DESC, created DESC LIMIT ?", (limit,))
        return [t for t in (self.desk_thread(r["thread_id"]) for r in rows) if t]

    def clear_turns(self, proposal_id: str) -> None:
        self._q("DELETE FROM turns WHERE proposal_id=?", (proposal_id,))

    # state
    def state(self, proposal_id: str) -> dict:
        rows = self._q("SELECT body FROM state WHERE proposal_id=?", (proposal_id,))
        return json.loads(rows[0]["body"]) if rows else {}

    def set_state(self, proposal_id: str, body: dict) -> None:
        self._q("INSERT OR REPLACE INTO state VALUES (?,?,?)", (proposal_id, json.dumps(body, default=str), time.time()))

    # saved analyses
    def save_analysis(self, proposal_id: str, owner: str, team: str, name: str, body: dict) -> dict:
        aid = "DA-" + uuid.uuid4().hex[:8].upper()
        self._q("INSERT INTO analyses VALUES (?,?,?,?,?,?,?)", (aid, proposal_id, owner, team, name, json.dumps(body, default=str), time.time()))
        return self.analysis(aid) or {}

    def analysis(self, aid: str) -> dict | None:
        rows = self._q("SELECT * FROM analyses WHERE analysis_id=?", (aid,))
        return self._row(rows[0]) if rows else None

    def analyses(self) -> list[dict]:
        return [self._row(r) for r in self._q("SELECT * FROM analyses ORDER BY created DESC")]

    def remove_analysis(self, aid: str) -> None:
        self._q("DELETE FROM analyses WHERE analysis_id=?", (aid,))

    @staticmethod
    def _row(r: sqlite3.Row) -> dict[str, Any]:
        return {"analysis_id": r["analysis_id"], "proposal_id": r["proposal_id"], "owner": r["owner"], "team": r["team"],
                "name": r["name"], "created": r["created"], **json.loads(r["body"])}

    # proposals entered through the form or a memo (kept so a restart keeps them)
    def add_proposal(self, body: dict) -> None:
        self._q("INSERT OR REPLACE INTO proposals VALUES (?,?,?)", (body["proposal_id"], json.dumps(body, default=str), time.time()))

    def proposals(self) -> list[dict]:
        return [json.loads(r["body"]) for r in self._q("SELECT body FROM proposals ORDER BY created")]
