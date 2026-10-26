"""The rules store: one SQLite file under var/dealdesk/rules/ (DEALDESK_VAR moves it; DEALDESK_RULES_DB overrides it).

    rules        id, text, kind, params (JSON), scope (me | team | bank), team, document (request | proposal | both), section,
                 section_label, author, author_name, created_at, updated_at, updated_by, source_instruction, source (JSON),
                 status (active | paused | removed), origin (analyst | seed | gold:<id> | policy), version
    rule_events  every change: rule id, at, by, action (created | edited | paused | resumed | removed), before/after (JSON)

Nothing is ever deleted: "remove" sets the status and keeps the rule and its history on record.
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
SCOPES = ("me", "team", "bank")
DOCUMENTS = ("request", "proposal", "both")
STATUSES = ("active", "paused", "removed")
SCOPE_LABEL = {"me": "Me", "team": "My team", "bank": "The bank"}
DOCUMENT_LABEL = {"request": "Credit request", "proposal": "Credit proposal", "both": "Both documents"}
EDITABLE = ("text", "scope", "document", "section", "section_label", "status", "kind", "params")


class NotFound(KeyError):
    pass


class Forbidden(PermissionError):
    pass


class Invalid(ValueError):
    pass


def db_path() -> pathlib.Path:
    p = os.environ.get("DEALDESK_RULES_DB")
    if p:
        return pathlib.Path(p)
    return paths.VAR / "rules" / "rules.sqlite"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


_READY: set[str] = set()


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    key = str(path)
    if key not in _READY or not _has_tables(con):
        con.executescript("""
            CREATE TABLE IF NOT EXISTS rules (
              id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL DEFAULT '{}',
              scope TEXT NOT NULL, team TEXT NOT NULL DEFAULT '', document TEXT NOT NULL, section TEXT NOT NULL DEFAULT '',
              section_label TEXT NOT NULL DEFAULT '', author TEXT NOT NULL, author_name TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '',
              source_instruction TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active',
              origin TEXT NOT NULL DEFAULT 'analyst', version INTEGER NOT NULL DEFAULT 1, method TEXT NOT NULL DEFAULT 'rules');
            CREATE TABLE IF NOT EXISTS rule_events (
              n INTEGER PRIMARY KEY AUTOINCREMENT, rule_id TEXT NOT NULL, at TEXT NOT NULL, by TEXT NOT NULL, action TEXT NOT NULL,
              before TEXT, after TEXT);
            CREATE INDEX IF NOT EXISTS ix_rules_scope ON rules(scope, status);
        """)
        con.commit()
        _READY.add(key)
        from backend.dealdesk.rules import seed
        seed.ensure(con)
    return con


def _has_tables(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rules'").fetchone() is not None


def row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["params"] = json.loads(d.get("params") or "{}")
    d["source"] = json.loads(d.get("source") or "{}")
    d["scope_label"] = SCOPE_LABEL.get(d["scope"], d["scope"])
    d["document_label"] = DOCUMENT_LABEL.get(d["document"], d["document"])
    return d


# ------------------------------------------------------------------ people

def person(username: str) -> dict[str, Any]:
    """Name and team of a user, from the seeded directory (no call to the Core service)."""
    try:
        from backend.identity_v5 import directory
        for u in directory.seed_users():
            if u["username"] == username:
                return {"username": username, "name": u["name"], "team": u["team"], "is_admin": u["is_admin"]}
    except Exception:  # noqa: BLE001 - the directory is optional for the store
        pass
    return {"username": username, "name": username or "Unknown", "team": "", "is_admin": username == "anne"}


# ------------------------------------------------------------------ reads

def get(rule_id: str, con: sqlite3.Connection | None = None) -> dict[str, Any]:
    own = con is None
    con = con or connect()
    try:
        r = con.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        if r is None:
            raise NotFound(f"No rule {rule_id}.")
        return row(r)
    finally:
        if own:
            con.close()


def listing(*, scope: str = "", document: str = "", author: str = "", status: str = "active", visible_to: str = "",
            origin: str = "") -> list[dict[str, Any]]:
    """Rules, newest first. `visible_to` keeps what that user sees: their own, their team's and the bank's."""
    q, a = "SELECT * FROM rules WHERE 1=1", []
    if scope:
        q += " AND scope=?"
        a.append(scope)
    if status == "all":
        pass
    elif status:
        q += " AND status=?"
        a.append(status)
    else:
        q += " AND status!='removed'"
    if document:
        q += " AND document IN (?, 'both')"
        a.append(document)
    if author:
        q += " AND author=?"
        a.append(author)
    if origin:
        q += " AND origin LIKE ?"
        a.append(origin + "%")
    q += " ORDER BY scope='bank', created_at DESC, id"
    with _LOCK:
        con = connect()
        try:
            rows = [row(r) for r in con.execute(q, a)]
        finally:
            con.close()
    if visible_to:
        me = person(visible_to)
        rows = [r for r in rows if r["scope"] == "bank" or (r["scope"] == "me" and r["author"] == visible_to)
                or (r["scope"] == "team" and (r["team"] == me["team"] or r["author"] == visible_to))]
    return rows


def for_document(username: str, document: str) -> list[dict[str, Any]]:
    """The active rules that apply when `username` writes `document` (request | proposal): theirs, their team's, the bank's.
    Order: the bank's first, then the team's, then the analyst's own, so a personal rule is applied last (and wins)."""
    rows = listing(document=document, status="active", visible_to=username or "-")
    rank = {"bank": 0, "team": 1, "me": 2}
    return sorted(rows, key=lambda r: (rank.get(r["scope"], 3), r["created_at"], r["id"]))


def history(rule_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        con = connect()
        try:
            get(rule_id, con)
            out = []
            for r in con.execute("SELECT * FROM rule_events WHERE rule_id=? ORDER BY n", (rule_id,)):
                d = dict(r)
                d["before"] = json.loads(d["before"]) if d["before"] else None
                d["after"] = json.loads(d["after"]) if d["after"] else None
                d["by_name"] = person(d["by"])["name"]
                out.append(d)
            return out
        finally:
            con.close()


# ------------------------------------------------------------------ writes

def _check(scope: str, document: str) -> None:
    if scope not in SCOPES:
        raise Invalid("scope must be one of me, team, bank.")
    if document not in DOCUMENTS:
        raise Invalid("document must be one of request, proposal, both.")


def _event(con: sqlite3.Connection, rule_id: str, by: str, action: str, before: Any, after: Any) -> None:
    con.execute("INSERT INTO rule_events(rule_id, at, by, action, before, after) VALUES (?,?,?,?,?,?)",
                (rule_id, now(), by, action, json.dumps(before) if before is not None else None,
                 json.dumps(after) if after is not None else None))


def create(*, text: str, kind: str, params: dict[str, Any], scope: str, document: str, section: str = "", section_label: str = "",
           author: str, source_instruction: str = "", source: dict[str, Any] | None = None, origin: str = "analyst",
           method: str = "rules", rule_id: str | None = None, con: sqlite3.Connection | None = None) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise Invalid("text: write the rule.")
    if len(text) > 600:
        raise Invalid("text: keep a rule under 600 characters.")
    _check(scope, document)
    who = person(author)
    rid = rule_id or "RL-" + uuid.uuid4().hex[:8].upper()
    at = now()
    own = con is None
    with _LOCK:
        con = con or connect()
        try:
            con.execute("INSERT INTO rules(id, text, kind, params, scope, team, document, section, section_label, author, author_name,"
                        " created_at, updated_at, updated_by, source_instruction, source, status, origin, version, method)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?, 1, ?)",
                        (rid, text, kind, json.dumps(params or {}), scope, who["team"] if scope == "team" else "", document, section or "",
                         section_label or "", author, who["name"], at, at, author, (source_instruction or "")[:2000],
                         json.dumps(source or {}), origin, method))
            _event(con, rid, author, "created", None, {"text": text, "scope": scope, "document": document, "section": section})
            con.commit()
            return get(rid, con)
        finally:
            if own:
                con.close()


def can_edit(rule: dict[str, Any], username: str) -> bool:
    me = person(username)
    if me["is_admin"] or rule["author"] == username:
        return True
    if rule["scope"] == "team":
        return bool(me["team"]) and me["team"] == rule["team"]
    if rule["scope"] == "bank":
        return me["team"] == "risk"  # Head of Credit, Head of Risk and the risk managers keep the bank's rules
    return False


def update(rule_id: str, changes: dict[str, Any], by: str, action: str = "edited") -> dict[str, Any]:
    with _LOCK:
        con = connect()
        try:
            cur = get(rule_id, con)
            if not can_edit(cur, by):
                raise Forbidden(f"Only {cur['author_name']} or the rule's owners can change this rule.")
            upd = {k: v for k, v in changes.items() if k in EDITABLE and v is not None}
            if "status" in upd and upd["status"] not in STATUSES:
                raise Invalid("status must be active, paused or removed.")
            scope, document = upd.get("scope", cur["scope"]), upd.get("document", cur["document"])
            _check(scope, document)
            if "text" in upd:
                upd["text"] = str(upd["text"]).strip()
                if not upd["text"]:
                    raise Invalid("text: write the rule.")
            if "scope" in upd:
                upd["team"] = person(cur["author"])["team"] if scope == "team" else ""
            if not upd:
                return cur
            before = {k: cur.get(k) for k in upd}
            sets = ", ".join(f"{k}=?" for k in upd)
            vals = [json.dumps(v) if k == "params" else v for k, v in upd.items()]
            con.execute(f"UPDATE rules SET {sets}, updated_at=?, updated_by=?, version=version+1 WHERE id=?",  # noqa: S608 - keys from EDITABLE
                        [*vals, now(), by, rule_id])
            _event(con, rule_id, by, action, before, upd)
            con.commit()
            return get(rule_id, con)
        finally:
            con.close()


def remove(rule_id: str, by: str) -> dict[str, Any]:
    return update(rule_id, {"status": "removed"}, by, action="removed")
