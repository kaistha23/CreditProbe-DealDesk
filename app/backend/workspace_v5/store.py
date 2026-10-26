"""The Workspace store: one sqlite file, its schema, and every read and write.

Whose workspace it is comes from the signed-in session (backend.identity_v5); the
store takes the username. Messages are CreditProbe Mail (backend.mail_v5); the
workspace inbox shows a person's unread conversations beside their mentions,
assignments and notifications. Projects, investigations, analyses and documents
are owned by a user and visible to the owner, the people the work is shared with,
the owner's team and the Administrator (see `visible`).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.workspace_v5 import paths

LOCK = threading.RLock()
_READY: set[str] = set()

SEED_VERSION = "ws-3"
#: Deal Desk edition (PLAN_DEALDESK_EDITION Round C): its own seed, kept apart from the full product's.
SEED_VERSION_DEALDESK = "ws-3-dd2"


def seed_version() -> str:
    """The seed this process expects in its store: the Deal Desk edition's or the full product's."""
    from backend.v5common.edition import is_dealdesk
    return SEED_VERSION_DEALDESK if is_dealdesk() else SEED_VERSION

INBOX_KINDS = ("message", "mention", "assignment", "notification")
INVESTIGATION_STATUSES = ("open", "in_review", "escalated", "closed")
PROJECT_STATUSES = ("active", "in_review", "done")
ITEM_STATUSES = ("todo", "in_progress", "done")
MAX_TEXT = 8000

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT, initials TEXT, position INTEGER);
CREATE TABLE IF NOT EXISTS inbox_items(
  id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '', href TEXT NOT NULL DEFAULT '', actor_id TEXT, created_at TEXT NOT NULL,
  read INTEGER NOT NULL DEFAULT 0, demo INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', owner_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', due_at TEXT, period TEXT, members TEXT NOT NULL DEFAULT '[]',
  links TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0, instructions TEXT NOT NULL DEFAULT '', domains TEXT NOT NULL DEFAULT '[]',
  focus TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS project_documents(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '', data BLOB, uploaded_by TEXT NOT NULL, created_at TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS project_threads(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, owner_id TEXT NOT NULL, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS project_messages(
  id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL, role TEXT NOT NULL, author_id TEXT, text TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS project_items(
  id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, position INTEGER NOT NULL, title TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'task', status TEXT NOT NULL DEFAULT 'todo',
  assignee_id TEXT, href TEXT NOT NULL DEFAULT '', link_label TEXT NOT NULL DEFAULT '',
  demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS investigations(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', sector TEXT, period TEXT,
  compare_period TEXT, status TEXT NOT NULL DEFAULT 'open', owner_id TEXT NOT NULL, project_id TEXT,
  figures TEXT NOT NULL DEFAULT '[]', links TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '{}',
  turns TEXT NOT NULL DEFAULT '[]', continue_href TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS investigation_notes(
  id INTEGER PRIMARY KEY, investigation_id TEXT NOT NULL, author_id TEXT NOT NULL, body TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'note', created_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS analyses(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', period TEXT,
  source TEXT NOT NULL DEFAULT '', owner_id TEXT NOT NULL, project_id TEXT, investigation_id TEXT,
  columns TEXT NOT NULL DEFAULT '[]', rows TEXT NOT NULL DEFAULT '[]', totals TEXT, notes TEXT NOT NULL DEFAULT '',
  links TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0,
  question TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT '', book TEXT, answer TEXT NOT NULL DEFAULT '{}',
  spec TEXT, origin_link TEXT NOT NULL DEFAULT '{}', refreshes TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
  owner_id TEXT NOT NULL, project_id TEXT, summary TEXT NOT NULL DEFAULT '', sections TEXT NOT NULL DEFAULT '[]',
  links TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0);
"""


class NotFound(LookupError):
    pass


class NotPermitted(PermissionError):
    pass


class Invalid(ValueError):
    pass


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _l(v: str | None) -> Any:
    return json.loads(v) if v else None


# ------------------------------------------------------------- connection


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def db():
    """One connection for one request, committed on success. Seeds on first use."""
    path = paths.store_path()
    ensure(path)
    with LOCK:
        con = _open(path)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def ensure(path: Path | None = None) -> dict[str, Any]:
    """Create the schema and seed it once. Safe to call any number of times."""
    path = path or paths.store_path()
    key = str(path)
    with LOCK:
        if key in _READY and path.exists():
            return {"store": key, "seeded": True, "created": False}
        con = _open(path)
        try:
            con.executescript(SCHEMA)
            version = seed_version()
            row = con.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
            if row is not None and row["value"] != version:
                # An older seed (other users, other content), or the other edition's: start the store afresh.
                con.close()
                path.unlink()
                for ext in ("-wal", "-shm"):
                    Path(str(path) + ext).unlink(missing_ok=True)
                con = _open(path)
                con.executescript(SCHEMA)
                row = None
            created = row is None
            if created:
                if version == SEED_VERSION_DEALDESK:
                    from backend.workspace_v5 import seed_dealdesk as seed
                else:
                    from backend.workspace_v5 import seed

                seed.apply(con)
                con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seed_version', ?)", (version,))
            con.commit()
        finally:
            con.close()
        _READY.add(key)
        return {"store": key, "seeded": True, "created": created}


def table_counts(con: sqlite3.Connection) -> dict[str, int]:
    names = ["users", "inbox_items", "projects", "project_items", "investigations",
             "investigation_notes", "analyses", "documents", "project_documents", "project_threads",
             "project_messages"]
    return {n: int(con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]) for n in names}


# ------------------------------------------------------------------ users


def users(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in con.execute("SELECT id, name, title, initials FROM users ORDER BY position")]


def user_map(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {u["id"]: u for u in users(con)}


def require_user(con: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    u = user_map(con).get(user_id)
    if not u:
        raise Invalid(f"{user_id!r} is not a workspace user.")
    return u


def mail_inbox(me: str) -> list[dict[str, Any]]:
    from backend.identity_v5 import store as ids
    from backend.mail_v5 import store as mail
    with ids.db() as con:
        return mail.thread_list(con, me, "inbox", limit=50)["threads"]


def mail_counts(me: str) -> dict[str, int]:
    from backend.identity_v5 import store as ids
    from backend.mail_v5 import store as mail
    with ids.db() as con:
        return mail.counts(con, me)


def _person(um: dict[str, dict[str, Any]], uid: str | None) -> dict[str, Any] | None:
    if not uid:
        return None
    u = um.get(uid)
    return dict(u) if u else {"id": uid, "name": uid, "title": "", "initials": "?"}


def _clean_links(links: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out = []
    for link in links or []:
        href = str(link.get("href") or "").strip()
        if not href.startswith("/"):
            raise Invalid("A link must be a path inside CreditProbe, starting with '/'.")
        out.append({"label": str(link.get("label") or href)[:200], "href": href[:500],
                    "type": str(link.get("type") or "link")[:40]})
    return out


def _add_inbox(con: sqlite3.Connection, user_id: str, kind: str, title: str, body: str, href: str,
               actor_id: str | None, at: str, source: str, demo: bool = False, item_id: int | None = None) -> None:
    con.execute("INSERT OR IGNORE INTO inbox_items(id, user_id, kind, title, body, href, actor_id, created_at, read, "
                "demo, source) VALUES(?,?,?,?,?,?,?,?,0,?,?)",
                (item_id, user_id, kind, title, body, href, actor_id, at, int(demo), source))


# ------------------------------------------------------------------ inbox


def inbox(con: sqlite3.Connection, me: str, kind: str = "") -> dict[str, Any]:
    if kind and kind not in INBOX_KINDS:
        raise Invalid(f"{kind!r} is not an inbox kind; use one of {', '.join(INBOX_KINDS)}.")
    um = user_map(con)
    items: list[dict[str, Any]] = []
    for t in mail_inbox(me):
        items.append({"id": f"thread-{t['thread_id']}", "kind": "message", "title": t["subject"], "body": t["snippet"],
                      "href": f"/messages?thread={t['thread_id']}", "actor": _person(um, t["last_sender"]["username"]),
                      "created_at": t["last_at"], "read": not t["unread"], "unread": 1 if t["unread"] else 0,
                      "source": f"thread:{t['thread_id']}"})
    for r in con.execute("SELECT * FROM inbox_items WHERE user_id=?", (me,)):
        items.append({"id": f"item-{r['id']}", "kind": r["kind"], "title": r["title"], "body": r["body"],
                      "href": r["href"], "actor": _person(um, r["actor_id"]), "created_at": r["created_at"],
                      "read": bool(r["read"]), "unread": 0 if r["read"] else 1, "source": r["source"]})
    if kind:
        items = [i for i in items if i["kind"] == kind]
    items.sort(key=lambda i: (i["created_at"], i["id"]), reverse=True)
    counts = {k: sum(1 for i in items if i["kind"] == k and not i["read"]) for k in INBOX_KINDS}
    return {"user": um[me], "items": items, "total": len(items), "unread": counts,
            "unread_total": sum(counts.values())}


def inbox_read(con: sqlite3.Connection, me: str, item_id: str) -> dict[str, Any]:
    if item_id.startswith("thread-"):
        return {"id": item_id, "read": False, "note": "Open the conversation in Messages to read it."}
    if not item_id.startswith("item-") or not item_id[5:].isdigit():
        raise NotFound(f"There is no inbox item {item_id!r}.")
    n = con.execute("UPDATE inbox_items SET read=1 WHERE id=? AND user_id=?", (int(item_id[5:]), me)).rowcount
    if not n:
        raise NotFound(f"There is no inbox item {item_id!r} for {me}.")
    return {"id": item_id, "read": True}


# --------------------------------------------------------------- projects


def _project_row(con: sqlite3.Connection, r: sqlite3.Row, um: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items = con.execute("SELECT status FROM project_items WHERE project_id=?", (r["id"],)).fetchall()
    return {"id": r["id"], "name": r["name"], "description": r["description"], "owner": _person(um, r["owner_id"]),
            "status": r["status"], "due_at": r["due_at"], "period": r["period"],
            "members": [_person(um, m) for m in _l(r["members"]) or []], "created_at": r["created_at"],
            "updated_at": r["updated_at"], "items": len(items),
            "items_done": sum(1 for i in items if i["status"] == "done"),
            "instructions": r["instructions"], "domains": _l(r["domains"]) or [], "focus": _l(r["focus"]) or {},
            "document_count": int(con.execute("SELECT COUNT(*) FROM project_documents WHERE project_id=?",
                                              (r["id"],)).fetchone()[0]),
            "thread_count": int(con.execute("SELECT COUNT(*) FROM project_threads WHERE project_id=?",
                                            (r["id"],)).fetchone()[0])}


def projects(con: sqlite3.Connection) -> list[dict[str, Any]]:
    um = user_map(con)
    return [_project_row(con, r, um) for r in con.execute("SELECT * FROM projects ORDER BY updated_at DESC, id")]


def project(con: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not r:
        raise NotFound(f"There is no project {project_id!r}.")
    um = user_map(con)
    out = _project_row(con, r, um)
    out["links"] = _l(r["links"]) or []
    out["tasks"] = [{"id": int(i["id"]), "title": i["title"], "detail": i["detail"], "kind": i["kind"],
                     "status": i["status"], "assignee": _person(um, i["assignee_id"]), "href": i["href"],
                     "link_label": i["link_label"]}
                    for i in con.execute("SELECT * FROM project_items WHERE project_id=? ORDER BY position, id",
                                         (project_id,))]
    out["investigations"] = [{"id": i["id"], "title": i["title"], "status": i["status"]} for i in con.execute(
        "SELECT id, title, status FROM investigations WHERE project_id=? ORDER BY id", (project_id,))]
    out["analyses"] = [{"id": i["id"], "title": i["title"], "period": i["period"]} for i in con.execute(
        "SELECT id, title, period FROM analyses WHERE project_id=? ORDER BY id", (project_id,))]
    out["documents"] = [{"id": i["id"], "title": i["title"], "status": i["status"]} for i in con.execute(
        "SELECT id, title, status FROM documents WHERE project_id=? ORDER BY id", (project_id,))]
    out["files"] = project_files(con, project_id)
    out["threads"] = project_threads(con, project_id)
    return out


def create_project(con: sqlite3.Connection, me: str, name: str, description: str = "", period: str = "",
                   members: list[str] | None = None, due_at: str | None = None) -> dict[str, Any]:
    um = user_map(con)
    name = (name or "").strip()
    if not name:
        raise Invalid("A project needs a name.")
    team = [m for m in dict.fromkeys([me, *(members or [])])]
    unknown = [m for m in team if m not in um]
    if unknown:
        raise Invalid(f"Not workspace users: {', '.join(unknown)}.")
    pid, at = new_id("p"), now()
    con.execute("INSERT INTO projects(id, name, description, owner_id, status, due_at, period, members, links, "
                "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (pid, name[:200], (description or "")[:MAX_TEXT], me, "active", due_at, period or None, _j(team),
                 "[]", at, at))
    for m in team:
        if m != me:
            _add_inbox(con, m, "assignment", f"{um[me]['name']} added you to the project “{name}”",
                       (description or "")[:240], f"/projects/{pid}", me, at, f"project:{pid}")
    return project(con, pid)


def add_project_task(con: sqlite3.Connection, me: str, project_id: str, title: str, detail: str = "",
                     assignee_id: str | None = None, href: str = "", link_label: str = "") -> dict[str, Any]:
    p = project(con, project_id)
    um = user_map(con)
    if not (title or "").strip():
        raise Invalid("A task needs a title.")
    if assignee_id and assignee_id not in um:
        raise Invalid(f"{assignee_id!r} is not a workspace user.")
    if href and not href.startswith("/"):
        raise Invalid("A link must be a path inside CreditProbe, starting with '/'.")
    pos = con.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM project_items WHERE project_id=?",
                      (project_id,)).fetchone()[0]
    at = now()
    con.execute("INSERT INTO project_items(project_id, position, title, detail, kind, status, assignee_id, href, "
                "link_label, demo) VALUES(?,?,?,?,?,?,?,?,?,0)",
                (project_id, pos, title.strip()[:200], detail[:MAX_TEXT], "task", "todo", assignee_id, href,
                 link_label[:120]))
    con.execute("UPDATE projects SET updated_at=? WHERE id=?", (at, project_id))
    if assignee_id and assignee_id != me:
        _add_inbox(con, assignee_id, "assignment", f"{um[me]['name']} assigned you “{title.strip()}”",
                   f"In {p['name']}.", f"/projects/{project_id}", me, at, f"project:{project_id}")
    return project(con, project_id)


def task_status(con: sqlite3.Connection, me: str, project_id: str, task_id: int, status: str) -> dict[str, Any]:
    if status not in ITEM_STATUSES:
        raise Invalid(f"status must be one of {', '.join(ITEM_STATUSES)}.")
    n = con.execute("UPDATE project_items SET status=? WHERE id=? AND project_id=?",
                    (status, task_id, project_id)).rowcount
    if not n:
        raise NotFound(f"There is no task {task_id} in project {project_id!r}.")
    con.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), project_id))
    return project(con, project_id)


# --------------------------------------------------------- investigations


def _inv_row(con: sqlite3.Connection, r: sqlite3.Row, um: dict[str, dict[str, Any]]) -> dict[str, Any]:
    notes = con.execute("SELECT COUNT(*) FROM investigation_notes WHERE investigation_id=? AND kind='note'",
                        (r["id"],)).fetchone()[0]
    return {"id": r["id"], "title": r["title"], "summary": r["summary"], "sector": r["sector"], "period": r["period"],
            "compare_period": r["compare_period"], "status": r["status"], "owner": _person(um, r["owner_id"]),
            "project_id": r["project_id"], "figures": _l(r["figures"]) or [], "notes": int(notes),
            "created_at": r["created_at"], "updated_at": r["updated_at"], "source": _l(r["source"]) or {},
            "turn_count": len(_l(r["turns"]) or []), "continue_href": r["continue_href"]}


def investigations(con: sqlite3.Connection) -> list[dict[str, Any]]:
    um = user_map(con)
    return [_inv_row(con, r, um) for r in con.execute("SELECT * FROM investigations ORDER BY updated_at DESC, id")]


def investigation(con: sqlite3.Connection, inv_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM investigations WHERE id=?", (inv_id,)).fetchone()
    if not r:
        raise NotFound(f"There is no investigation {inv_id!r}.")
    um = user_map(con)
    out = _inv_row(con, r, um)
    out["links"] = _l(r["links"]) or []
    out["turns"] = _l(r["turns"]) or []
    out["timeline"] = [{"id": int(n["id"]), "author": _person(um, n["author_id"]), "body": n["body"],
                        "kind": n["kind"], "created_at": n["created_at"]}
                       for n in con.execute("SELECT * FROM investigation_notes WHERE investigation_id=? "
                                            "ORDER BY created_at, id", (inv_id,))]
    out["analyses"] = [{"id": a["id"], "title": a["title"], "period": a["period"]} for a in con.execute(
        "SELECT id, title, period FROM analyses WHERE investigation_id=? ORDER BY id", (inv_id,))]
    out["statuses"] = list(INVESTIGATION_STATUSES)
    if r["project_id"]:
        p = con.execute("SELECT id, name FROM projects WHERE id=?", (r["project_id"],)).fetchone()
        out["project"] = dict(p) if p else None
    return out


def add_note(con: sqlite3.Connection, me: str, inv_id: str, body: str,
             mentions: list[str] | None = None) -> dict[str, Any]:
    inv = investigation(con, inv_id)
    body = (body or "").strip()
    if not body:
        raise Invalid("A note needs some text.")
    um = user_map(con)
    at = now()
    con.execute("INSERT INTO investigation_notes(investigation_id, author_id, body, kind, created_at, demo) "
                "VALUES(?,?,?,?,?,0)", (inv_id, me, body[:MAX_TEXT], "note", at))
    con.execute("UPDATE investigations SET updated_at=? WHERE id=?", (at, inv_id))
    for m in dict.fromkeys(mentions or []):
        if m in um and m != me:
            _add_inbox(con, m, "mention", f"{um[me]['name']} mentioned you in “{inv['title']}”", body[:240],
                       f"/investigations/{inv_id}", me, at, f"investigation:{inv_id}")
    return investigation(con, inv_id)


def investigation_status(con: sqlite3.Connection, me: str, inv_id: str, status: str, note: str = "") -> dict[str, Any]:
    inv = investigation(con, inv_id)
    if status not in INVESTIGATION_STATUSES:
        raise Invalid(f"status must be one of {', '.join(INVESTIGATION_STATUSES)}.")
    if status == inv["status"]:
        raise Invalid(f"The investigation is already {status.replace('_', ' ')}.")
    at = now()
    text = f"Status changed from {inv['status'].replace('_', ' ')} to {status.replace('_', ' ')}."
    if note.strip():
        text += f" {note.strip()}"
    con.execute("UPDATE investigations SET status=?, updated_at=? WHERE id=?", (status, at, inv_id))
    con.execute("INSERT INTO investigation_notes(investigation_id, author_id, body, kind, created_at, demo) "
                "VALUES(?,?,?,?,?,0)", (inv_id, me, text[:MAX_TEXT], "status", at))
    owner = inv["owner"]["id"] if inv["owner"] else None
    if owner and owner != me:
        um = user_map(con)
        _add_inbox(con, owner, "notification", f"{um[me]['name']} set “{inv['title']}” to {status.replace('_', ' ')}",
                   note or "", f"/investigations/{inv_id}", me, at, f"investigation:{inv_id}")
    return investigation(con, inv_id)


# ------------------------------------------------------ analyses, documents


def _analysis_row(r: sqlite3.Row, um: dict[str, dict[str, Any]], full: bool) -> dict[str, Any]:
    out = {"id": r["id"], "title": r["title"], "description": r["description"], "period": r["period"],
           "source": r["source"], "owner": _person(um, r["owner_id"]), "project_id": r["project_id"],
           "investigation_id": r["investigation_id"], "created_at": r["created_at"],
           "rows": len(_l(r["rows"]) or []), "question": r["question"], "origin": r["origin"], "book": r["book"],
           "origin_link": _l(r["origin_link"]) or {}, "refreshable": bool(_l(r["spec"])),
           "refresh_count": len(_l(r["refreshes"]) or [])}
    # R10 Q2: the answer line (key figure bold) travels with the list too, so the list reads as answers.
    from backend.workspace_v5.answer_first import headline_for
    out["headline"] = headline_for(r["question"] or "", _l(r["answer"]) or {"narrative": r["description"]}, r["period"])
    if full:
        out.update({"columns": _l(r["columns"]) or [], "rows": _l(r["rows"]) or [], "totals": _l(r["totals"]),
                    "notes": r["notes"], "links": _l(r["links"]) or [], "answer": _l(r["answer"]) or {},
                    "spec": _l(r["spec"]), "refreshes": _l(r["refreshes"]) or []})
    return out


def analyses(con: sqlite3.Connection) -> list[dict[str, Any]]:
    um = user_map(con)
    return [_analysis_row(r, um, False) for r in con.execute("SELECT * FROM analyses ORDER BY created_at DESC, id")]


def analysis(con: sqlite3.Connection, analysis_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if not r:
        raise NotFound(f"There is no analysis {analysis_id!r}.")
    return _analysis_row(r, user_map(con), True)


def _document_row(r: sqlite3.Row, um: dict[str, dict[str, Any]], full: bool) -> dict[str, Any]:
    sections = _l(r["sections"]) or []
    out = {"id": r["id"], "title": r["title"], "kind": r["kind"], "status": r["status"],
           "owner": _person(um, r["owner_id"]), "project_id": r["project_id"], "summary": r["summary"],
           "created_at": r["created_at"], "updated_at": r["updated_at"], "section_count": len(sections),
           "words": sum(len((s.get("body") or "").split()) for s in sections)}
    if full:
        out.update({"sections": sections, "links": _l(r["links"]) or []})
    return out


def documents(con: sqlite3.Connection) -> list[dict[str, Any]]:
    um = user_map(con)
    return [_document_row(r, um, False) for r in con.execute("SELECT * FROM documents ORDER BY updated_at DESC, id")]


def document(con: sqlite3.Connection, doc_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not r:
        raise NotFound(f"There is no document {doc_id!r}.")
    return _document_row(r, user_map(con), True)


def summary(con: sqlite3.Connection, me: str, counts: dict[str, int] | None = None) -> dict[str, Any]:
    ib = inbox(con, me)
    return {"user": ib["user"], "messages": mail_counts(me), "inbox": ib["unread"],
            "inbox_unread": ib["unread_total"],
            "counts": counts or {"projects": len(projects(con)), "investigations": len(investigations(con)),
                                 "analyses": len(analyses(con)), "documents": len(documents(con))}}


# ------------------------------------------- "Add to" from other screens


def _clean_item(title: str, body: str, href: str, label: str, type_: str) -> dict[str, str]:
    title, body = (title or "").strip(), (body or "").strip()
    if not title:
        raise Invalid("The item needs a title.")
    if href and not href.startswith("/"):
        raise Invalid("A link must be a path inside CreditProbe, starting with '/'.")
    return {"title": title[:200], "body": body[:MAX_TEXT], "href": href[:500],
            "label": (label or title)[:200], "type": (type_ or "link")[:40]}


def create_investigation(con: sqlite3.Connection, me: str, title: str, summary: str = "") -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise Invalid("An investigation needs a title.")
    inv_id, at = new_id("inv"), now()
    con.execute("INSERT INTO investigations(id, title, summary, sector, period, compare_period, status, owner_id, "
                "project_id, figures, links, created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (inv_id, title[:200], (summary or "")[:MAX_TEXT], None, None, None, "open", me, None, "[]", "[]", at, at))
    return investigation(con, inv_id)


def add_to_investigation(con: sqlite3.Connection, me: str, inv_id: str, title: str, body: str, href: str = "",
                         label: str = "", type_: str = "link") -> dict[str, Any]:
    """Add something from another screen (an attention item, a list) to an investigation: a timeline entry and a link."""
    item = _clean_item(title, body, href, label, type_)
    inv = investigation(con, inv_id)
    at = now()
    text = f"Added “{item['title']}”." + (f"\n\n{item['body']}" if item["body"] else "")
    con.execute("INSERT INTO investigation_notes(investigation_id, author_id, body, kind, created_at, demo) "
                "VALUES(?,?,?,?,?,0)", (inv_id, me, text[:MAX_TEXT], "note", at))
    links = list(inv["links"])
    if item["href"] and not any(link.get("href") == item["href"] for link in links):
        links.append({"label": item["label"], "href": item["href"], "type": item["type"]})
    con.execute("UPDATE investigations SET links=?, updated_at=? WHERE id=?", (_j(links), at, inv_id))
    return investigation(con, inv_id)


DOCUMENT_KINDS = ("Report", "Committee pack", "Risk committee report", "Portfolio review", "Credit memo",
                  "Scenario report")


def create_document(con: sqlite3.Connection, me: str, title: str, kind: str = "Report") -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise Invalid("A document needs a title.")
    if kind not in DOCUMENT_KINDS:
        raise Invalid(f"kind must be one of {', '.join(DOCUMENT_KINDS)}.")
    doc_id, at = new_id("doc"), now()
    con.execute("INSERT INTO documents(id, title, kind, status, owner_id, project_id, summary, sections, links, "
                "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (doc_id, title[:200], kind, "draft", me, None, "", "[]", "[]", at, at))
    return document(con, doc_id)


def add_to_document(con: sqlite3.Connection, me: str, doc_id: str, title: str, body: str, href: str = "",
                    label: str = "", type_: str = "link") -> dict[str, Any]:
    """Add a section to a document draft: the item's text, with a link back to where it came from."""
    item = _clean_item(title, body, href, label, type_)
    doc = document(con, doc_id)
    sections = list(doc["sections"]) + [{"heading": item["title"], "body": item["body"]}]
    links = list(doc["links"])
    if item["href"] and not any(link.get("href") == item["href"] for link in links):
        links.append({"label": item["label"], "href": item["href"], "type": item["type"]})
    con.execute("UPDATE documents SET sections=?, links=?, updated_at=? WHERE id=?", (_j(sections), _j(links), now(), doc_id))
    return document(con, doc_id)


# ------------------------------------------- analyses: save and refresh (S3-2)

ORIGINS = ("cockpit", "whatif", "workspace", "dealdesk")
BOOKS = ("corporate", "retail")


def create_analysis(con: sqlite3.Connection, me: str, *, title: str, question: str, origin: str, book: str | None,
                    period: str | None, answer: dict[str, Any], spec: dict[str, Any] | None,
                    origin_link: dict[str, Any] | None = None, description: str = "", notes: str = "",
                    source: str = "", analysis_id: str | None = None, at: str | None = None,
                    demo: bool = False) -> dict[str, Any]:
    title = (title or question or "").strip()
    if not title:
        raise Invalid("An analysis needs a title or a question.")
    if origin not in ORIGINS:
        raise Invalid(f"origin must be one of {', '.join(ORIGINS)}.")
    if book is not None and book not in BOOKS:
        raise Invalid("book must be corporate or retail.")
    link = dict(origin_link or {})
    if link.get("href") and not str(link["href"]).startswith("/"):
        raise Invalid("A link must be a path inside CreditProbe, starting with '/'.")
    table = answer.get("table") or {}
    # R10 Q2 (item 17): an analysis is the answer to its question: the headline is written when it is saved.
    from backend.workspace_v5.answer_first import headline_for
    answer = {**answer, "headline": headline_for(question or "", answer, period)}
    aid, at = analysis_id or new_id("an"), at or now()
    con.execute("INSERT OR IGNORE INTO analyses(id, title, description, period, source, owner_id, project_id, "
                "investigation_id, columns, rows, totals, notes, links, created_at, demo, question, origin, book, "
                "answer, spec, origin_link, refreshes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, title[:200], (description or answer.get("narrative") or "")[:MAX_TEXT], period, source[:500], me,
                 None, None, _j(table.get("columns") or []), _j(table.get("rows") or []),
                 _j(table.get("totals")) if table.get("totals") else None, notes[:MAX_TEXT],
                 _j([link] if link.get("href") else []), at, int(demo), question[:MAX_TEXT], origin, book,
                 _j(answer), _j(spec) if spec else None, _j(link), "[]"))
    return analysis(con, aid)


def record_refresh(con: sqlite3.Connection, me: str, analysis_id: str, entry: dict[str, Any]) -> None:
    a = analysis(con, analysis_id)
    hist = list(a["refreshes"]) + [{**entry, "by": me, "at": now()}]
    con.execute("UPDATE analyses SET refreshes=? WHERE id=?", (_j(hist[-20:]), analysis_id))


# ------------------------------------- investigations: import, turns (S3-2)

SOURCE_TYPES = ("cockpit-thread", "whatif-thread", "early-warning-list", "early-warning-customer",
                "early-warning-level", "scorecard-validation", "scorecard-thread", "attention-item", "borrower",
                "project-thread", "workspace", "dealdesk-thread", "dealdesk-proposal")


def _clean_source(source: dict[str, Any]) -> dict[str, str]:
    t = str(source.get("type") or "").strip()
    if t not in SOURCE_TYPES:
        raise Invalid(f"source.type must be one of {', '.join(SOURCE_TYPES)}.")
    href = str(source.get("href") or "").strip()
    if href and not href.startswith("/"):
        raise Invalid("source.href must be a path inside CreditProbe, starting with '/'.")
    return {"type": t, "id": str(source.get("id") or "")[:200], "label": str(source.get("label") or t)[:200],
            "href": href[:500]}


def _clean_turns(turns: list[dict[str, Any]], at: str) -> list[dict[str, Any]]:
    out = []
    for t in turns or []:
        role = str(t.get("role") or "user")
        if role not in ("user", "assistant", "note", "system"):
            raise Invalid("A turn's role is user, assistant, note or system.")
        text = str(t.get("text") or "").strip()
        arts = [a for a in (t.get("artifacts") or []) if isinstance(a, dict)][:20]
        if not text and not arts:
            continue
        out.append({"role": role, "text": text[:20000], "artifacts": arts, "at": str(t.get("at") or at),
                    "author": t.get("author")})
    return out


def import_investigation(con: sqlite3.Connection, me: str, *, source: dict[str, Any], title: str,
                         turns: list[dict[str, Any]], notes: list[str] | str | None = None, summary: str = "",
                         continue_href: str = "", project_id: str | None = None, sector: str | None = None,
                         period: str | None = None, inv_id: str | None = None, at: str | None = None,
                         demo: bool = False, status: str = "open") -> dict[str, Any]:
    """Save a whole thread from anywhere as an investigation: its turns (with their artifacts) and notes."""
    title = (title or "").strip()
    if not title:
        raise Invalid("An investigation needs a title.")
    src = _clean_source(source)
    at = at or now()
    clean = _clean_turns(turns, at)
    if not clean:
        raise Invalid("An investigation needs at least one turn of the conversation.")
    cont = (continue_href or src["href"]).strip()
    if cont and not cont.startswith("/"):
        raise Invalid("continue_href must be a path inside CreditProbe, starting with '/'.")
    if project_id:
        project(con, project_id)
    inv_id = inv_id or new_id("inv")
    if not summary:
        first = next((t["text"] for t in clean if t["role"] == "user" and t["text"]), clean[0]["text"])
        summary = f"Saved from {src['label']}: {len(clean)} turns. First question: {first[:300]}"
    links = [{"label": src["label"], "href": src["href"], "type": src["type"]}] if src["href"] else []
    con.execute("INSERT OR IGNORE INTO investigations(id, title, summary, sector, period, compare_period, status, "
                "owner_id, project_id, figures, links, created_at, updated_at, demo, source, turns, continue_href) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (inv_id, title[:200], summary[:MAX_TEXT], sector, period, None, status, me, project_id, "[]",
                 _j(links), at, at, int(demo), _j(src), _j(clean), cont[:500]))
    if not demo:
        for n in ([notes] if isinstance(notes, str) else notes or []):
            if str(n).strip():
                con.execute("INSERT INTO investigation_notes(investigation_id, author_id, body, kind, created_at, "
                            "demo) VALUES(?,?,?,?,?,0)", (inv_id, me, str(n).strip()[:MAX_TEXT], "note", at))
    return investigation(con, inv_id)


def add_turns(con: sqlite3.Connection, me: str, inv_id: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Continue an investigation: append turns (with the author) to its conversation."""
    inv = investigation(con, inv_id)
    at = now()
    clean = _clean_turns([{**t, "author": me} for t in turns], at)
    if not clean:
        raise Invalid("Nothing to add: a turn needs text or an artifact.")
    con.execute("UPDATE investigations SET turns=?, updated_at=? WHERE id=?",
                (_j(list(inv["turns"]) + clean), at, inv_id))
    return investigation(con, inv_id)


# ---------------------------------------------- projects: settings, files, threads (S3-2)

DOMAINS = ("corporate", "retail", "ews", "whatif", "bureau", "open_banking", "scorecard", "dealdesk")


def _clean_domains(domains: list[str]) -> list[str]:
    bad = [d for d in domains if d not in DOMAINS]
    if bad:
        raise Invalid(f"Not data domains: {', '.join(bad)}. The domains are {', '.join(DOMAINS)}.")
    return [d for d in DOMAINS if d in domains]


def update_project(con: sqlite3.Connection, me: str, project_id: str, *, description: str | None = None,
                   instructions: str | None = None, domains: list[str] | None = None,
                   members: list[str] | None = None, name: str | None = None) -> dict[str, Any]:
    p = project(con, project_id)
    um = user_map(con)
    sets: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            raise Invalid("A project needs a name.")
        sets["name"] = name.strip()[:200]
    if description is not None:
        sets["description"] = description[:MAX_TEXT]
    if instructions is not None:
        sets["instructions"] = instructions[:MAX_TEXT]
    if domains is not None:
        sets["domains"] = _j(_clean_domains(domains))
    if members is not None:
        owner = p["owner"]["id"] if p["owner"] else me
        team = list(dict.fromkeys([owner, *members]))
        unknown = [m for m in team if m not in um]
        if unknown:
            raise Invalid(f"Not workspace users: {', '.join(unknown)}.")
        sets["members"] = _j(team)
        at = now()
        old = {m["id"] for m in p["members"] if m}
        for m in team:
            if m not in old and m != me:
                _add_inbox(con, m, "assignment", f"{um[me]['name']} added you to the project “{p['name']}”",
                           p["description"][:240], f"/projects/{project_id}", me, at, f"project:{project_id}")
    if not sets:
        return p
    sets["updated_at"] = now()
    con.execute(f"UPDATE projects SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), project_id))
    return project(con, project_id)


def set_project_scope(con: sqlite3.Connection, project_id: str, instructions: str, domains: list[str],
                      focus: dict[str, Any] | None = None) -> None:
    con.execute("UPDATE projects SET instructions=?, domains=?, focus=? WHERE id=?",
                (instructions, _j(_clean_domains(domains)), _j(focus or {}), project_id))


def project_files(con: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    um = user_map(con)
    return [{"id": r["id"], "name": r["name"], "kind": r["kind"], "size": r["size"], "words": len(r["text"].split()),
             "uploaded_by": _person(um, r["uploaded_by"]), "created_at": r["created_at"],
             "excerpt": r["text"][:280]}
            for r in con.execute("SELECT id, name, kind, size, text, uploaded_by, created_at FROM project_documents "
                                 "WHERE project_id=? ORDER BY created_at, id", (project_id,))]


def project_file_texts(con: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "name": r["name"], "text": r["text"]} for r in con.execute(
        "SELECT id, name, text FROM project_documents WHERE project_id=? ORDER BY created_at, id", (project_id,))]


def project_file(con: sqlite3.Connection, project_id: str, file_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM project_documents WHERE id=? AND project_id=?", (file_id, project_id)).fetchone()
    if not r:
        raise NotFound(f"There is no document {file_id!r} in project {project_id!r}.")
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "size": r["size"], "text": r["text"],
            "data": r["data"], "created_at": r["created_at"], "uploaded_by": _person(user_map(con), r["uploaded_by"])}


def add_project_file(con: sqlite3.Connection, me: str, project_id: str, name: str, data: bytes, text: str,
                     kind: str, file_id: str | None = None, at: str | None = None, demo: bool = False) -> dict[str, Any]:
    project(con, project_id)
    fid, at = file_id or new_id("pd"), at or now()
    con.execute("INSERT OR IGNORE INTO project_documents(id, project_id, name, kind, size, text, data, uploaded_by, "
                "created_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (fid, project_id, name[:200], kind, len(data), text, data, me, at, int(demo)))
    if not demo:
        con.execute("UPDATE projects SET updated_at=? WHERE id=?", (at, project_id))
    return project_file(con, project_id, fid)


def delete_project_file(con: sqlite3.Connection, project_id: str, file_id: str) -> None:
    if not con.execute("DELETE FROM project_documents WHERE id=? AND project_id=?", (file_id, project_id)).rowcount:
        raise NotFound(f"There is no document {file_id!r} in project {project_id!r}.")


def project_threads(con: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    um = user_map(con)
    out = []
    for r in con.execute("SELECT * FROM project_threads WHERE project_id=? ORDER BY updated_at DESC, id",
                         (project_id,)):
        n = con.execute("SELECT COUNT(*) FROM project_messages WHERE thread_id=?", (r["id"],)).fetchone()[0]
        out.append({"id": r["id"], "title": r["title"], "owner": _person(um, r["owner_id"]),
                    "created_at": r["created_at"], "updated_at": r["updated_at"], "messages": int(n)})
    return out


def project_thread(con: sqlite3.Connection, project_id: str, thread_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM project_threads WHERE id=? AND project_id=?", (thread_id, project_id)).fetchone()
    if not r:
        raise NotFound(f"There is no thread {thread_id!r} in project {project_id!r}.")
    um = user_map(con)
    msgs = [{"id": int(m["id"]), "role": m["role"], "author": _person(um, m["author_id"]), "text": m["text"],
             **(_l(m["payload"]) or {}), "created_at": m["created_at"]}
            for m in con.execute("SELECT * FROM project_messages WHERE thread_id=? ORDER BY id", (thread_id,))]
    return {"id": r["id"], "project_id": project_id, "title": r["title"], "owner": _person(um, r["owner_id"]),
            "created_at": r["created_at"], "updated_at": r["updated_at"], "messages": msgs}


def create_project_thread(con: sqlite3.Connection, me: str, project_id: str, title: str,
                          thread_id: str | None = None, at: str | None = None, demo: bool = False) -> str:
    project(con, project_id)
    tid, at = thread_id or new_id("pt"), at or now()
    con.execute("INSERT OR IGNORE INTO project_threads(id, project_id, title, owner_id, created_at, updated_at, demo) "
                "VALUES(?,?,?,?,?,?,?)", (tid, project_id, (title.strip() or "New thread")[:200], me, at, at, int(demo)))
    return tid


def add_project_message(con: sqlite3.Connection, thread_id: str, role: str, author: str | None, text: str,
                        payload: dict[str, Any] | None = None, at: str | None = None, demo: bool = False,
                        msg_id: int | None = None) -> None:
    at = at or now()
    con.execute("INSERT OR IGNORE INTO project_messages(id, thread_id, role, author_id, text, payload, created_at, "
                "demo) VALUES(?,?,?,?,?,?,?,?)",
                (msg_id, thread_id, role, author, text[:MAX_TEXT * 4], _j(payload or {}), at, int(demo)))
    con.execute("UPDATE project_threads SET updated_at=? WHERE id=?", (at, thread_id))
