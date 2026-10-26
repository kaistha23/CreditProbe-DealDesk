"""CreditProbe Mail store: threads, messages, recipients, per-user state, attachments, drafts, notifications.

Visibility rule: a message is visible to a user only if they sent it or are in its To/Cc/Bcc. A thread is visible
when any of its messages is. Bcc recipients are private: only the sender (and the Bcc recipient, for themself) sees
them; To/Cc recipients never do, and Reply all never reaches them. The Administrator reads any mailbox through `mailbox=` (read only, audited).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from typing import Any

from backend.identity_v5 import paths, store as ids
from backend.identity_v5.store import Invalid, NotFound, NotPermitted, now
from backend.mail_v5.sanitize import sanitize_html, to_text

SEED_VERSION = "mail-2"
#: Deal Desk edition (PLAN_DEALDESK_EDITION Round C): its own seed, all about deals (backend.mail_v5.seed_dealdesk).
SEED_VERSION_DEALDESK = "mail-2-dd3"


def seed_version() -> str:
    """The mail seed this process expects in its store: the Deal Desk edition's or the full product's."""
    from backend.v5common.edition import is_dealdesk
    return SEED_VERSION_DEALDESK if is_dealdesk() else SEED_VERSION
FOLDERS = ("inbox", "sent", "drafts", "archive", "starred", "all")
BULK_ACTIONS = ("archive", "unarchive", "read", "unread", "star", "unstar", "label", "unlabel", "move")
OBJECT_TYPES = ("investigation", "project", "cockpit-thread", "attention-item", "early-warning-list", "borrower", "whatif-thread",
                "whatif-scenario", "report", "analysis", "document", "scorecard-validation", "dealdesk-proposal", "dealdesk-analysis",
                "lens", "thread-answer")  # R16 t (M7): one answer or a whole thread, any module
MAX_BODY = 200_000
MAX_FILE = 25 * 1024 * 1024
MAX_RECIPIENTS = 20
MAX_OBJECTS = 10
MAX_FILES = 10
MODES = ("new", "reply", "reply_all", "forward")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_threads(
  id TEXT PRIMARY KEY, subject TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  last_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_messages(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, thread_id TEXT NOT NULL, sender TEXT NOT NULL,
  sent_at TEXT NOT NULL, body_html TEXT NOT NULL, body_text TEXT NOT NULL, in_reply_to TEXT,
  kind TEXT NOT NULL DEFAULT 'message');
CREATE INDEX IF NOT EXISTS mail_messages_thread ON mail_messages(thread_id, seq);
CREATE TABLE IF NOT EXISTS mail_recipients(
  message_seq INTEGER NOT NULL, username TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(message_seq, username));
CREATE INDEX IF NOT EXISTS mail_recipients_user ON mail_recipients(username);
CREATE TABLE IF NOT EXISTS mail_attachments(
  id INTEGER PRIMARY KEY, message_seq INTEGER NOT NULL, kind TEXT NOT NULL, file_id TEXT, obj_type TEXT,
  obj_id TEXT, label TEXT NOT NULL DEFAULT '', href TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
  meta TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS mail_attachments_msg ON mail_attachments(message_seq);
CREATE TABLE IF NOT EXISTS mail_files(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, content_type TEXT NOT NULL, sha256 TEXT NOT NULL,
  uploader TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_state(
  thread_id TEXT NOT NULL, username TEXT NOT NULL, last_read_seq INTEGER NOT NULL DEFAULT 0,
  starred INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, labels TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY(thread_id, username));
CREATE TABLE IF NOT EXISTS mail_labels(
  owner TEXT NOT NULL, name TEXT NOT NULL, color TEXT NOT NULL DEFAULT '#6366f1', PRIMARY KEY(owner, name));
CREATE TABLE IF NOT EXISTS mail_drafts(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_notifications(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, href TEXT NOT NULL,
  from_user TEXT, thread_id TEXT, created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS mail_notifications_user ON mail_notifications(username, id);
CREATE TABLE IF NOT EXISTS mail_idem(
  key TEXT NOT NULL, username TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(key, username));
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


_QUOTE = re.compile(r"<blockquote\b[^>]*>(?:(?!<blockquote\b).)*?</blockquote>", re.I | re.S)


def strip_quotes(body_html: str) -> str:
    """The body without quoted replies (innermost blockquotes first, so nesting is handled)."""
    prev = None
    out = body_html or ""
    while prev != out:
        prev, out = out, _QUOTE.sub("", out)
    return out


def snippet_of(body_html: str, n: int = 140) -> str:
    """The list preview: the new text of a message, without what it quotes."""
    return re.sub(r"\s+", " ", to_text(strip_quotes(body_html))).strip()[:n]


# ---------------------------------------------------------------- helpers


def _users(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return ids.user_map(con)


def _check_usernames(um: dict[str, dict[str, Any]], names: list[str], field: str) -> list[str]:
    out: list[str] = []
    for n in names or []:
        n = (n or "").strip().lower()
        if n not in um:
            raise Invalid(f"Unknown user '{n}' in {field}.")
        if n not in out:
            out.append(n)
    return out


def _clean_object(o: dict[str, Any]) -> dict[str, Any]:
    t = (o.get("type") or "").strip()
    if t not in OBJECT_TYPES:
        raise Invalid(f"Unknown object type '{t}'. Registered: {', '.join(OBJECT_TYPES)}.")
    oid = str(o.get("id") or "").strip()
    if not oid or len(oid) > 120:
        raise Invalid("An attached object needs an id of up to 120 characters.")
    label = str(o.get("label") or "").strip()
    if not label or len(label) > 200:
        raise Invalid("An attached object needs a label of up to 200 characters.")
    href = str(o.get("href") or "").strip()
    if not re.match(r"^/(?!/)", href) or len(href) > 500:
        raise Invalid("An attached object's href must be an in-app path starting with '/'.")
    summary = str(o.get("summary") or "")[:400]
    meta = o.get("meta") or {}
    if not isinstance(meta, dict) or len(json.dumps(meta)) > 2048:
        raise Invalid("An object's meta must be a JSON object of up to 2 KB.")
    return {"type": t, "id": oid, "label": label, "href": href, "summary": summary, "meta": meta}


def _file_row(con: sqlite3.Connection, file_id: str) -> sqlite3.Row:
    r = con.execute("SELECT * FROM mail_files WHERE id=?", (file_id,)).fetchone()
    if r is None:
        raise Invalid(f"Unknown file '{file_id}'.")
    return r


def _visible_seqs(con: sqlite3.Connection, thread_id: str, user: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT m.* FROM mail_messages m WHERE m.thread_id=? AND (m.sender=? OR EXISTS("
        " SELECT 1 FROM mail_recipients r WHERE r.message_seq=m.seq AND r.username=?)) ORDER BY m.seq",
        (thread_id, user, user)).fetchall()


def _state(con: sqlite3.Connection, thread_id: str, user: str) -> sqlite3.Row:
    r = con.execute("SELECT * FROM mail_state WHERE thread_id=? AND username=?", (thread_id, user)).fetchone()
    if r is None:
        con.execute("INSERT INTO mail_state(thread_id, username) VALUES(?,?)", (thread_id, user))
        r = con.execute("SELECT * FROM mail_state WHERE thread_id=? AND username=?", (thread_id, user)).fetchone()
    return r


def _person(um: dict[str, dict[str, Any]], username: str) -> dict[str, Any]:
    u = um.get(username)
    return u if u else {"username": username, "name": username, "initials": "?", "role": "", "title": "",
                        "department": "", "books": [], "team": "", "is_admin": False}


def _attachments(con: sqlite3.Connection, seq: int) -> list[dict[str, Any]]:
    out = []
    for a in con.execute("SELECT * FROM mail_attachments WHERE message_seq=? ORDER BY id", (seq,)):
        if a["kind"] == "file":
            f = con.execute("SELECT * FROM mail_files WHERE id=?", (a["file_id"],)).fetchone()
            out.append({"kind": "file", "file_id": a["file_id"], "name": f["name"] if f else a["label"],
                        "size": f["size"] if f else 0, "content_type": f["content_type"] if f else "",
                        "href": f"/api/v1/mail/files/{a['file_id']}"})
        else:
            out.append({"kind": "object", "object": {"type": a["obj_type"], "id": a["obj_id"], "label": a["label"],
                                                      "href": a["href"], "summary": a["summary"],
                                                      "meta": json.loads(a["meta"])}})
    return out


def _message(con: sqlite3.Connection, m: sqlite3.Row, um: dict[str, dict[str, Any]], me: str,
             last_read: int) -> dict[str, Any]:
    recips = con.execute("SELECT username, kind FROM mail_recipients WHERE message_seq=? ORDER BY rowid",
                         (m["seq"],)).fetchall()
    # Bcc is private: the sender sees every Bcc recipient, a Bcc recipient sees only themself, nobody else any.
    bcc = [r["username"] for r in recips if r["kind"] == "bcc" and (m["sender"] == me or r["username"] == me)]
    return {"message_id": m["id"], "sender": _person(um, m["sender"]),
            "to": [_person(um, r["username"]) for r in recips if r["kind"] == "to"],
            "cc": [_person(um, r["username"]) for r in recips if r["kind"] == "cc"],
            "bcc": [_person(um, u) for u in bcc],
            "sent_at": m["sent_at"], "body_html": m["body_html"], "body_text": m["body_text"],
            "kind": m["kind"], "in_reply_to": m["in_reply_to"], "attachments": _attachments(con, m["seq"]),
            "unread": m["sender"] != me and m["seq"] > last_read}


def _user_threads(con: sqlite3.Connection, user: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT t.id FROM mail_threads t JOIN mail_messages m ON m.thread_id=t.id "
        "WHERE m.sender=? OR EXISTS(SELECT 1 FROM mail_recipients r WHERE r.message_seq=m.seq AND r.username=?)",
        (user, user)).fetchall()
    return [r["id"] for r in rows]


def _summary(con: sqlite3.Connection, tid: str, user: str, um: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    msgs = _visible_seqs(con, tid, user)
    if not msgs:
        return None
    t = con.execute("SELECT * FROM mail_threads WHERE id=?", (tid,)).fetchone()
    st = _state(con, tid, user)
    last = msgs[-1]
    people: list[str] = []
    for m in msgs:
        for u in [m["sender"]] + [r["username"] for r in con.execute(
                "SELECT username, kind FROM mail_recipients WHERE message_seq=?", (m["seq"],))
                if r["kind"] != "bcc" or m["sender"] == user or r["username"] == user]:
            if u not in people:
                people.append(u)
    snippet = snippet_of(last["body_html"]) or re.sub(r"\s+", " ", last["body_text"]).strip()[:140]
    has_att = bool(con.execute("SELECT 1 FROM mail_attachments WHERE message_seq IN (%s) LIMIT 1"
                               % ",".join(str(m["seq"]) for m in msgs)).fetchone())
    unread = any(m["sender"] != user and m["seq"] > st["last_read_seq"] for m in msgs)
    received = any(con.execute("SELECT 1 FROM mail_recipients WHERE message_seq=? AND username=?",
                               (m["seq"], user)).fetchone() for m in msgs)
    sent = any(m["sender"] == user for m in msgs)
    senders: list[str] = []
    for m in msgs:
        if m["sender"] not in senders:
            senders.append(m["sender"])
    return {"thread_id": tid, "subject": t["subject"], "snippet": snippet, "last_at": last["sent_at"],
            "senders": [_person(um, p) for p in senders], "first_at": msgs[0]["sent_at"],
            "has_files": bool(con.execute("SELECT 1 FROM mail_attachments WHERE kind='file' AND message_seq IN (%s) LIMIT 1"
                                          % ",".join(str(m["seq"]) for m in msgs)).fetchone()),
            "last_sender": _person(um, last["sender"]), "participants": [_person(um, p) for p in people],
            "message_count": len(msgs), "unread": unread, "starred": bool(st["starred"]),
            "archived": bool(st["archived"]), "labels": json.loads(st["labels"]), "has_attachments": has_att,
            "_received": received, "_sent": sent, "_seq": last["seq"]}


# ------------------------------------------------------------------ reads


def counts(con: sqlite3.Connection, user: str) -> dict[str, Any]:
    um = _users(con)
    inbox = unread = starred = archive = sent = total = 0
    by = {"inbox": 0, "starred": 0, "archive": 0, "sent": 0, "all": 0}
    for tid in _user_threads(con, user):
        s = _summary(con, tid, user, um)
        if s is None:
            continue
        total += 1
        by["all"] += int(s["unread"])
        if s["starred"]:
            starred += 1
            by["starred"] += int(s["unread"])
        if s["archived"]:
            archive += 1
            by["archive"] += int(s["unread"])
            continue
        if s["_received"]:
            inbox += 1
            if s["unread"]:
                unread += 1
        if s["_sent"]:
            sent += 1
            by["sent"] += int(s["unread"])
    by["inbox"] = unread
    drafts = int(con.execute("SELECT COUNT(*) FROM mail_drafts WHERE owner=?", (user,)).fetchone()[0])
    notes = int(con.execute("SELECT COUNT(*) FROM mail_notifications WHERE username=? AND read=0",
                            (user,)).fetchone()[0])
    return {"inbox": inbox, "unread": unread, "drafts": drafts, "starred": starred, "archive": archive,
            "sent": sent, "all": total, "notifications": notes, "unread_by_folder": by}


def _day(v: str, field: str) -> str:
    v = (v or "").strip()
    if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        raise Invalid(f"{field} must be a date as YYYY-MM-DD.")
    return v


def thread_list(con: sqlite3.Connection, user: str, folder: str = "inbox", q: str = "", unread: bool = False,
                label: str = "", limit: int = 50, offset: int = 0, sender: str = "", recipient: str = "",
                has_attachment: bool = False, date_from: str = "", date_to: str = "") -> dict[str, Any]:
    """One folder's conversations, newest first. Search: free text `q`, plus `sender` (a message from), `recipient`
    (a message to, cc, or a Bcc the user may see), `has_attachment`, `label`, and a date range on any message
    (`date_from`/`date_to`, inclusive days, UTC)."""
    if folder not in FOLDERS:
        raise Invalid(f"Unknown folder '{folder}'. Use: {', '.join(FOLDERS)}.")
    date_from, date_to = _day(date_from, "date_from"), _day(date_to, "date_to")
    sender, recipient = (sender or "").strip().lower(), (recipient or "").strip().lower()
    um = _users(con)
    if folder == "drafts":
        items = []
        for d in con.execute("SELECT * FROM mail_drafts WHERE owner=? ORDER BY updated_at DESC", (user,)):
            data = json.loads(d["data"])
            items.append({"thread_id": None, "draft_id": d["id"], "subject": data.get("subject") or "(no subject)",
                          "snippet": to_text(data.get("body_html", ""))[:140], "last_at": d["updated_at"],
                          "participants": [_person(um, u) for u in data.get("to", []) if u in um],
                          "message_count": 1, "unread": False, "starred": False, "labels": [],
                          "has_attachments": bool(data.get("attachments"))})
        if q:
            ql = q.lower()
            items = [i for i in items if ql in i["subject"].lower() or ql in i["snippet"].lower()]
        if recipient:
            items = [i for i in items if any(_who_matches(p, recipient) for p in i["participants"])]
        if has_attachment:
            items = [i for i in items if i["has_attachments"]]
        if date_from:
            items = [i for i in items if i["last_at"][:10] >= date_from]
        if date_to:
            items = [i for i in items if i["last_at"][:10] <= date_to]
        if sender or label:
            items = []  # a draft has no sender yet and carries no labels
        return {"threads": items[offset:offset + limit], "total": len(items)}
    rows = []
    ql = q.lower().strip()
    for tid in _user_threads(con, user):
        s = _summary(con, tid, user, um)
        if s is None:
            continue
        if folder == "inbox" and (s["archived"] or not s["_received"]):
            continue
        if folder == "sent" and (s["archived"] or not s["_sent"]):
            continue
        if folder == "archive" and not s["archived"]:
            continue
        if folder == "starred" and not s["starred"]:
            continue
        if folder == "all" and not (s["_received"] or s["_sent"]):
            continue
        if unread and not s["unread"]:
            continue
        if label and label not in s["labels"]:
            continue
        if ql and not _matches(con, tid, user, um, s, ql):
            continue
        if has_attachment and not s["has_attachments"]:
            continue
        if (sender or recipient or date_from or date_to) and not _filter_messages(
                con, tid, user, um, sender, recipient, date_from, date_to):
            continue
        rows.append(s)
    rows.sort(key=lambda s: (s["last_at"], s["_seq"]), reverse=True)
    total = len(rows)
    page = rows[max(0, offset):max(0, offset) + max(1, min(limit, 200))]
    for s in page:
        for k in ("_received", "_sent", "_seq"):
            s.pop(k, None)
    return {"threads": page, "total": total}


def _who_matches(p: dict[str, Any], term: str) -> bool:
    return term == p["username"] or term in p["name"].lower() or term in p["username"]


def _filter_messages(con: sqlite3.Connection, tid: str, user: str, um: dict[str, dict[str, Any]], sender: str,
                     recipient: str, date_from: str, date_to: str) -> bool:
    """True when one visible message matches every message-level filter at once."""
    for m in _visible_seqs(con, tid, user):
        day = m["sent_at"][:10]
        if (date_from and day < date_from) or (date_to and day > date_to):
            continue
        if sender and not _who_matches(_person(um, m["sender"]), sender):
            continue
        if recipient:
            rs = con.execute("SELECT username, kind FROM mail_recipients WHERE message_seq=?", (m["seq"],)).fetchall()
            seen = [r["username"] for r in rs if r["kind"] != "bcc" or m["sender"] == user or r["username"] == user]
            if not any(_who_matches(_person(um, u), recipient) for u in seen):
                continue
        return True
    return False


def _matches(con: sqlite3.Connection, tid: str, user: str, um: dict[str, dict[str, Any]], s: dict[str, Any],
             ql: str) -> bool:
    if ql in s["subject"].lower():
        return True
    for p in s["participants"]:
        if ql in p["name"].lower() or ql in p["username"].lower():
            return True
    for lab in s["labels"]:
        if ql in lab.lower():
            return True
    for m in _visible_seqs(con, tid, user):
        if ql in m["body_text"].lower():
            return True
        for a in con.execute("SELECT label, summary FROM mail_attachments WHERE message_seq=?", (m["seq"],)):
            if ql in (a["label"] or "").lower() or ql in (a["summary"] or "").lower():
                return True
    return False


def thread_detail(con: sqlite3.Connection, thread_id: str, user: str) -> dict[str, Any]:
    um = _users(con)
    msgs = _visible_seqs(con, thread_id, user)
    if not msgs:
        if con.execute("SELECT 1 FROM mail_threads WHERE id=?", (thread_id,)).fetchone() is None:
            raise NotFound(f"No thread '{thread_id}'.")
        raise NotPermitted("You are not a participant in this thread.")
    t = con.execute("SELECT * FROM mail_threads WHERE id=?", (thread_id,)).fetchone()
    st = _state(con, thread_id, user)
    return {"thread_id": thread_id, "subject": t["subject"],
            "messages": [_message(con, m, um, user, st["last_read_seq"]) for m in msgs],
            "starred": bool(st["starred"]), "archived": bool(st["archived"]), "labels": json.loads(st["labels"]),
            "unread": any(m["sender"] != user and m["seq"] > st["last_read_seq"] for m in msgs)}


def get_message(con: sqlite3.Connection, message_id: str, user: str) -> sqlite3.Row:
    m = con.execute("SELECT * FROM mail_messages WHERE id=?", (message_id,)).fetchone()
    if m is None:
        raise NotFound(f"No message '{message_id}'.")
    if m["sender"] != user and not con.execute(
            "SELECT 1 FROM mail_recipients WHERE message_seq=? AND username=?", (m["seq"], user)).fetchone():
        raise NotPermitted("You are not a participant in this message.")
    return m


# ----------------------------------------------------------------- writes


def _insert_message(con: sqlite3.Connection, thread_id: str, sender: str, to: list[str], cc: list[str],
                    body_html: str, in_reply_to: str | None, attachments: list[dict[str, Any]],
                    kind: str = "message", sent_at: str | None = None, mid: str | None = None,
                    bcc: list[str] | None = None) -> dict[str, Any]:
    bcc = bcc or []
    clean = sanitize_html(body_html)
    text = to_text(clean)
    mid = mid or new_id("m")
    at = sent_at or now()
    cur = con.execute(
        "INSERT INTO mail_messages(id, thread_id, sender, sent_at, body_html, body_text, in_reply_to, kind)"
        " VALUES(?,?,?,?,?,?,?,?)", (mid, thread_id, sender, at, clean, text, in_reply_to, kind))
    seq = int(cur.lastrowid)
    for u in to:
        con.execute("INSERT OR IGNORE INTO mail_recipients(message_seq, username, kind) VALUES(?,?,'to')", (seq, u))
    for u in cc:
        con.execute("INSERT OR IGNORE INTO mail_recipients(message_seq, username, kind) VALUES(?,?,'cc')", (seq, u))
    for u in bcc:
        con.execute("INSERT OR IGNORE INTO mail_recipients(message_seq, username, kind) VALUES(?,?,'bcc')", (seq, u))
    for a in attachments:
        if a["kind"] == "file":
            f = _file_row(con, a["file_id"])
            con.execute("INSERT INTO mail_attachments(message_seq, kind, file_id, label) VALUES(?, 'file', ?, ?)",
                        (seq, f["id"], f["name"]))
        else:
            o = a["object"]
            con.execute("INSERT INTO mail_attachments(message_seq, kind, obj_type, obj_id, label, href, summary, meta)"
                        " VALUES(?, 'object', ?,?,?,?,?,?)",
                        (seq, o["type"], o["id"], o["label"], o["href"], o["summary"], json.dumps(o["meta"])))
    con.execute("UPDATE mail_threads SET last_at=? WHERE id=?", (at, thread_id))
    # The sender has read their own message; a recipient's archived thread comes back to the Inbox.
    st = _state(con, thread_id, sender)
    con.execute("UPDATE mail_state SET last_read_seq=MAX(last_read_seq, ?) WHERE thread_id=? AND username=?",
                (seq, thread_id, sender))
    del st
    for u in set(to) | set(cc) | set(bcc):
        if u != sender:
            _state(con, thread_id, u)
            con.execute("UPDATE mail_state SET archived=0 WHERE thread_id=? AND username=?", (thread_id, u))
    return {"message_id": mid, "seq": seq, "thread_id": thread_id}


def _notify(con: sqlite3.Connection, recipients: list[str], sender: str, um: dict[str, dict[str, Any]],
            subject: str, thread_id: str, kind: str) -> None:
    who = um[sender]["name"]
    verb = "shared with you" if kind == "share" else "sent you"
    for u in recipients:
        if u == sender:
            continue
        con.execute("INSERT INTO mail_notifications(username, kind, title, href, from_user, thread_id, created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (u, kind, f"{who} {verb}: {subject}"[:240], f"/messages?thread={thread_id}", sender, thread_id,
                     now()))


def _clean_attachments(con: sqlite3.Connection, items: list[dict[str, Any]], sender: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = objs = 0
    for a in items or []:
        kind = a.get("kind")
        if kind == "file":
            files += 1
            f = _file_row(con, str(a.get("file_id") or ""))
            if f["uploader"] != sender and not _file_visible(con, f["id"], sender):
                raise NotPermitted(f"You cannot attach file '{f['name']}'.")
            out.append({"kind": "file", "file_id": f["id"]})
        elif kind == "object":
            objs += 1
            out.append({"kind": "object", "object": _clean_object(a.get("object") or {})})
        else:
            raise Invalid("An attachment needs kind 'file' or 'object'.")
    if files > MAX_FILES or objs > MAX_OBJECTS:
        raise Invalid(f"At most {MAX_FILES} files and {MAX_OBJECTS} objects per message.")
    return out


def _file_visible(con: sqlite3.Connection, file_id: str, user: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM mail_attachments a JOIN mail_messages m ON m.seq=a.message_seq WHERE a.file_id=? AND "
        "(m.sender=? OR EXISTS(SELECT 1 FROM mail_recipients r WHERE r.message_seq=m.seq AND r.username=?)) LIMIT 1",
        (file_id, user, user)).fetchone())


def send(con: sqlite3.Connection, sender: str, to: list[str], cc: list[str], subject: str, body_html: str,
         attachments: list[dict[str, Any]], mode: str = "new", thread_id: str | None = None,
         in_reply_to: str | None = None, draft_id: str | None = None, kind: str = "message",
         bcc: list[str] | None = None) -> dict[str, Any]:
    um = _users(con)
    if mode not in MODES:
        raise Invalid(f"mode must be one of {', '.join(MODES)}.")
    if len(body_html or "") > MAX_BODY:
        raise Invalid("The message body is too large.")
    to = _check_usernames(um, to, "To")
    cc = [u for u in _check_usernames(um, cc, "Cc") if u not in to]
    bcc = [u for u in _check_usernames(um, bcc or [], "Bcc") if u not in to and u not in cc and u != sender]
    atts = _clean_attachments(con, attachments, sender)
    subject = (subject or "").strip()[:300]
    if mode == "forward":
        orig = get_message(con, in_reply_to or "", sender)
        src = con.execute("SELECT subject FROM mail_threads WHERE id=?", (orig["thread_id"],)).fetchone()
        subject = subject or (src["subject"] if src and src["subject"].lower().startswith("fwd:")
                              else f"Fwd: {src['subject'] if src else ''}")
        if not to:
            raise Invalid("Add at least one recipient (To).")
        # carry the original's attachments unless the caller already listed them
        have = {(a["kind"], a.get("file_id") or a["object"]["id"]) for a in atts}
        for a in _attachments(con, orig["seq"]):
            key = ("file", a["file_id"]) if a["kind"] == "file" else ("object", a["object"]["id"])
            if key not in have:
                atts.append({"kind": "file", "file_id": a["file_id"]} if a["kind"] == "file"
                            else {"kind": "object", "object": a["object"]})
        thread_id = None
    elif mode in ("reply", "reply_all"):
        if not thread_id or not in_reply_to:
            raise Invalid("A reply needs thread_id and in_reply_to.")
        orig = get_message(con, in_reply_to, sender)
        if orig["thread_id"] != thread_id:
            raise Invalid("in_reply_to is not in that thread.")
        if not to:
            to = [orig["sender"]] if orig["sender"] != sender else [r["username"] for r in con.execute(
                "SELECT username FROM mail_recipients WHERE message_seq=? AND kind='to'", (orig["seq"],))]
            if mode == "reply_all":
                # To and Cc only: Bcc recipients are never revealed or re-addressed by Reply all.
                everyone = [r["username"] for r in con.execute(
                    "SELECT username FROM mail_recipients WHERE message_seq=? AND kind IN ('to','cc')", (orig["seq"],))]
                cc = [u for u in dict.fromkeys(everyone + cc) if u not in to and u != sender]
        if sender in to and len(to) > 1:
            to = [u for u in to if u != sender]
        if not to:
            raise Invalid("Add at least one recipient (To).")
    else:
        if not to:
            raise Invalid("Add at least one recipient (To).")
        if not subject:
            subject = "(no subject)"
    bcc = [u for u in bcc if u not in to and u not in cc]
    if len(to) + len(cc) + len(bcc) > MAX_RECIPIENTS:
        raise Invalid(f"At most {MAX_RECIPIENTS} recipients per message.")
    if mode in ("reply", "reply_all"):
        t = con.execute("SELECT * FROM mail_threads WHERE id=?", (thread_id,)).fetchone()
        subject = t["subject"]
    else:
        thread_id = new_id("t")
        con.execute("INSERT INTO mail_threads(id, subject, created_by, created_at, last_at) VALUES(?,?,?,?,?)",
                    (thread_id, subject or "(no subject)", sender, now(), now()))
    msg = _insert_message(con, thread_id, sender, to, cc, body_html, in_reply_to, atts, kind=kind, bcc=bcc)
    _notify(con, to + cc + bcc, sender, um, subject, thread_id, "share" if kind == "share" else "mail")
    if draft_id:
        con.execute("DELETE FROM mail_drafts WHERE id=? AND owner=?", (draft_id, sender))
    out = {"thread_id": thread_id, "message_id": msg["message_id"], "recipients": to + cc}
    if bcc:
        out["bcc"] = bcc
    return out


def share(con: sqlite3.Connection, sender: str, to: list[str], cc: list[str], note: str,
          objects: list[dict[str, Any]], subject: str = "") -> dict[str, Any]:
    um = _users(con)
    to = _check_usernames(um, to, "To")
    if not to:
        raise Invalid("Choose at least one person to share with.")
    if sender in to:
        raise Invalid("You cannot share with yourself.")
    if not objects or len(objects) > MAX_OBJECTS:
        raise Invalid(f"Share needs between 1 and {MAX_OBJECTS} objects.")
    clean = [{"kind": "object", "object": _clean_object(o)} for o in objects]
    first = clean[0]["object"]
    subject = (subject or "").strip() or f"Shared: {first['label']}"
    from html import escape
    if note and note.strip():
        body = "<p>" + escape(note.strip()).replace("\n", "<br>") + "</p>"
    else:
        body = f"<p>{escape(um[sender]['name'])} shared this with you.</p>"
    res = send(con, sender, to, cc, subject, body, clean, mode="new", kind="share")
    aid = ids.audit(con, sender, sender, "share", res["thread_id"],
                    {"to": to, "cc": cc, "objects": [o["id"] for o in objects], "subject": subject})
    res["audit_id"] = aid
    return res


def save_draft(con: sqlite3.Connection, owner: str, data: dict[str, Any], draft_id: str | None = None) -> dict[str, Any]:
    um = _users(con)
    clean = {
        "to": [u for u in _check_usernames(um, data.get("to", []), "To")],
        "cc": [u for u in _check_usernames(um, data.get("cc", []), "Cc")],
        "bcc": [u for u in _check_usernames(um, data.get("bcc", []) or [], "Bcc")],
        "subject": str(data.get("subject") or "")[:300],
        "body_html": sanitize_html(str(data.get("body_html") or ""))[:MAX_BODY],
        "attachments": _clean_attachments(con, data.get("attachments") or [], owner),
        "mode": data.get("mode") if data.get("mode") in MODES else "new",
        "thread_id": data.get("thread_id"), "in_reply_to": data.get("in_reply_to"),
    }
    at = now()
    if draft_id:
        r = con.execute("SELECT owner FROM mail_drafts WHERE id=?", (draft_id,)).fetchone()
        if r is None:
            raise NotFound(f"No draft '{draft_id}'.")
        if r["owner"] != owner:
            raise NotPermitted("That is not your draft.")
        con.execute("UPDATE mail_drafts SET data=?, updated_at=? WHERE id=?", (json.dumps(clean), at, draft_id))
    else:
        draft_id = new_id("d")
        con.execute("INSERT INTO mail_drafts(id, owner, data, updated_at) VALUES(?,?,?,?)",
                    (draft_id, owner, json.dumps(clean), at))
    return {"draft_id": draft_id, **clean, "updated_at": at}


def get_draft(con: sqlite3.Connection, owner: str, draft_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM mail_drafts WHERE id=?", (draft_id,)).fetchone()
    if r is None:
        raise NotFound(f"No draft '{draft_id}'.")
    if r["owner"] != owner:
        raise NotPermitted("That is not your draft.")
    data = json.loads(r["data"])
    data.setdefault("bcc", [])
    files = {}
    for a in data.get("attachments", []):
        if a.get("kind") == "file":
            f = con.execute("SELECT name, size FROM mail_files WHERE id=?", (a["file_id"],)).fetchone()
            if f:
                files[a["file_id"]] = {"name": f["name"], "size": f["size"]}
    return {"draft_id": draft_id, **data, "files": files, "updated_at": r["updated_at"]}


def delete_draft(con: sqlite3.Connection, owner: str, draft_id: str) -> dict[str, Any]:
    get_draft(con, owner, draft_id)
    con.execute("DELETE FROM mail_drafts WHERE id=?", (draft_id,))
    return {"ok": True}


def _require_thread(con: sqlite3.Connection, thread_id: str, user: str) -> None:
    if not _visible_seqs(con, thread_id, user):
        if con.execute("SELECT 1 FROM mail_threads WHERE id=?", (thread_id,)).fetchone() is None:
            raise NotFound(f"No thread '{thread_id}'.")
        raise NotPermitted("You are not a participant in this thread.")


def mark_read(con: sqlite3.Connection, thread_id: str, user: str, read: bool = True) -> dict[str, Any]:
    _require_thread(con, thread_id, user)
    st = _state(con, thread_id, user)
    msgs = _visible_seqs(con, thread_id, user)
    if read:
        con.execute("UPDATE mail_state SET last_read_seq=? WHERE thread_id=? AND username=?",
                    (msgs[-1]["seq"], thread_id, user))
    else:
        inbound = [m["seq"] for m in msgs if m["sender"] != user]
        if inbound:
            con.execute("UPDATE mail_state SET last_read_seq=? WHERE thread_id=? AND username=?",
                        (max(0, inbound[-1] - 1), thread_id, user))
    del st
    if read:
        con.execute("UPDATE mail_notifications SET read=1 WHERE username=? AND thread_id=?", (user, thread_id))
    return {"thread_id": thread_id, "unread": not read}


def set_flag(con: sqlite3.Connection, thread_id: str, user: str, field: str, value: bool) -> dict[str, Any]:
    if field not in ("starred", "archived"):
        raise Invalid("Unknown flag.")
    _require_thread(con, thread_id, user)
    _state(con, thread_id, user)
    con.execute(f"UPDATE mail_state SET {field}=? WHERE thread_id=? AND username=?",
                (1 if value else 0, thread_id, user))
    return {"thread_id": thread_id, field: value}


def set_labels(con: sqlite3.Connection, thread_id: str, user: str, add: list[str], remove: list[str]) -> dict[str, Any]:
    _require_thread(con, thread_id, user)
    st = _state(con, thread_id, user)
    labels = json.loads(st["labels"])
    for name in add or []:
        name = name.strip()[:40]
        if not name:
            continue
        con.execute("INSERT OR IGNORE INTO mail_labels(owner, name) VALUES(?,?)", (user, name))
        if name not in labels:
            labels.append(name)
    labels = [l for l in labels if l not in (remove or [])]
    con.execute("UPDATE mail_state SET labels=? WHERE thread_id=? AND username=?",
                (json.dumps(labels), thread_id, user))
    return {"thread_id": thread_id, "labels": labels}


def bulk(con: sqlite3.Connection, user: str, thread_ids: list[str], action: str, label: str = "") -> dict[str, Any]:
    """One action on many conversations: all or nothing (an unknown or foreign thread refuses the whole call).
    `move` = apply the label and take the conversation out of the Inbox (archive), as a mail client's Move to."""
    if action not in BULK_ACTIONS:
        raise Invalid(f"action must be one of {', '.join(BULK_ACTIONS)}.")
    ids_ = list(dict.fromkeys(t for t in thread_ids or [] if t))
    if not ids_ or len(ids_) > 200:
        raise Invalid("Choose between 1 and 200 conversations.")
    if action in ("label", "unlabel", "move") and not (label or "").strip():
        raise Invalid("Choose a label.")
    for tid in ids_:
        _require_thread(con, tid, user)
    for tid in ids_:
        if action in ("archive", "unarchive"):
            set_flag(con, tid, user, "archived", action == "archive")
        elif action in ("star", "unstar"):
            set_flag(con, tid, user, "starred", action == "star")
        elif action in ("read", "unread"):
            mark_read(con, tid, user, action == "read")
        elif action == "label":
            set_labels(con, tid, user, [label], [])
        elif action == "unlabel":
            set_labels(con, tid, user, [], [label])
        else:
            set_labels(con, tid, user, [label], [])
            set_flag(con, tid, user, "archived", True)
    return {"action": action, "label": label or None, "thread_ids": ids_, "updated": len(ids_)}


def list_labels(con: sqlite3.Connection, user: str) -> list[dict[str, Any]]:
    rows = con.execute("SELECT name, color FROM mail_labels WHERE owner=? ORDER BY name", (user,)).fetchall()
    out = []
    um = _users(con)
    summaries = [x for x in (_summary(con, tid, user, um) for tid in _user_threads(con, user)) if x]
    for r in rows:
        tagged = [x for x in summaries if r["name"] in x["labels"]]
        out.append({"name": r["name"], "color": r["color"], "count": len(tagged),
                    "unread": sum(1 for x in tagged if x["unread"])})
    return out


def create_label(con: sqlite3.Connection, user: str, name: str, color: str = "#6366f1") -> dict[str, Any]:
    name = (name or "").strip()[:40]
    if not name:
        raise Invalid("A label needs a name.")
    if not re.match(r"^#[0-9a-fA-F]{6}$", color or ""):
        color = "#6366f1"
    con.execute("INSERT OR REPLACE INTO mail_labels(owner, name, color) VALUES(?,?,?)", (user, name, color))
    return {"name": name, "color": color}


def delete_label(con: sqlite3.Connection, user: str, name: str) -> dict[str, Any]:
    con.execute("DELETE FROM mail_labels WHERE owner=? AND name=?", (user, name))
    for r in con.execute("SELECT thread_id, labels FROM mail_state WHERE username=?", (user,)).fetchall():
        ls = json.loads(r["labels"])
        if name in ls:
            con.execute("UPDATE mail_state SET labels=? WHERE thread_id=? AND username=?",
                        (json.dumps([l for l in ls if l != name]), r["thread_id"], user))
    return {"ok": True}


# ------------------------------------------------------------------ files


def save_file(con: sqlite3.Connection, uploader: str, name: str, content_type: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_FILE:
        raise Invalid("Files can be up to 25 MB.")
    if not data:
        raise Invalid("The file is empty.")
    name = re.sub(r"[\\/\x00-\x1f]", "_", (name or "file").strip())[:200] or "file"
    fid = new_id("f")
    d = paths.files_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / fid).write_bytes(data)
    con.execute("INSERT INTO mail_files(id, name, size, content_type, sha256, uploader, created_at) VALUES(?,?,?,?,?,?,?)",
                (fid, name, len(data), (content_type or "application/octet-stream")[:100],
                 hashlib.sha256(data).hexdigest(), uploader, now()))
    return {"file_id": fid, "name": name, "size": len(data), "content_type": content_type or "application/octet-stream"}


def file_for(con: sqlite3.Connection, file_id: str, user: str, admin: bool) -> tuple[sqlite3.Row, bytes]:
    f = con.execute("SELECT * FROM mail_files WHERE id=?", (file_id,)).fetchone()
    if f is None:
        raise NotFound(f"No file '{file_id}'.")
    if not (admin or f["uploader"] == user or _file_visible(con, file_id, user)):
        raise NotPermitted("You cannot open this file.")
    p = paths.files_dir() / f["id"]
    if not p.exists():
        raise NotFound("The file is no longer stored.")
    return f, p.read_bytes()


# ---------------------------------------------------------- notifications


def notifications(con: sqlite3.Connection, user: str, unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
    um = _users(con)
    where = "username=?" + (" AND read=0" if unread_only else "")
    rows = con.execute(f"SELECT * FROM mail_notifications WHERE {where} ORDER BY id DESC LIMIT ?",
                       (user, max(1, min(limit, 200)))).fetchall()
    return {"notifications": [{"id": r["id"], "kind": r["kind"], "title": r["title"], "href": r["href"],
                               "from": _person(um, r["from_user"]) if r["from_user"] else None,
                               "created_at": r["created_at"], "read": bool(r["read"])} for r in rows],
            "unread": int(con.execute("SELECT COUNT(*) FROM mail_notifications WHERE username=? AND read=0",
                                      (user,)).fetchone()[0])}


def notifications_read(con: sqlite3.Connection, user: str, note_id: int | None) -> dict[str, Any]:
    if note_id is None:
        con.execute("UPDATE mail_notifications SET read=1 WHERE username=?", (user,))
    else:
        con.execute("UPDATE mail_notifications SET read=1 WHERE username=? AND id=?", (user, note_id))
    return {"ok": True}


# ---------------------------------------------------------- shared-with-me


def shared_with_me(con: sqlite3.Connection, user: str, types: list[str]) -> dict[str, Any]:
    q = ("SELECT a.obj_type, a.obj_id, m.sender, m.sent_at, m.thread_id, a.label, a.href FROM mail_attachments a "
         "JOIN mail_messages m ON m.seq=a.message_seq JOIN mail_recipients r ON r.message_seq=m.seq "
         "WHERE a.kind='object' AND r.username=? AND m.sender<>?")
    args: list[Any] = [user, user]
    if types:
        q += " AND a.obj_type IN (%s)" % ",".join("?" * len(types))
        args += types
    q += " ORDER BY m.seq DESC"
    seen: set[tuple[str, str]] = set()
    out = []
    for r in con.execute(q, args):
        k = (r["obj_type"], r["obj_id"])
        if k in seen:
            continue
        seen.add(k)
        out.append({"type": r["obj_type"], "id": r["obj_id"], "label": r["label"], "href": r["href"],
                    "shared_by": r["sender"], "shared_at": r["sent_at"], "thread_id": r["thread_id"]})
    return {"objects": out}


def admin_mailboxes(con: sqlite3.Connection) -> dict[str, Any]:
    rows = []
    for u in ids.users(con):
        rows.append({"user": u, "counts": counts(con, u["username"])})
    return {"mailboxes": rows}
