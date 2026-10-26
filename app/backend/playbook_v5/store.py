"""The Playbook and Policy Docs store: one sqlite file, its schema, and every read and write.

Reports
  A report is a title, a template, an owner, reviewers, a due date, a status on the workflow
  Draft -> In review -> Approved -> Presented, and an ordered list of sections. A section holds blocks
  (paragraph, heading, bullets, kpis, table, chart, rag, callout; docs/v5/PLAYBOOK_API.md 3.2) and, when it
  was imported, the object it came from. Every change writes a version: a full snapshot, so any version can be
  opened read-only or restored. Comments sit on the report or on one section. Each report has one thread with
  the assistant.

Policy documents (backend.playbook_v5.policy)
  The library of policies and circulars, their clauses, the interpretation of an upload, and the versioned
  policy pack. Their tables live here too, so one transaction covers a decision and the pack it writes.

Who may see a report: the owner, its reviewers, anyone it was shared with by Mail, the owner's team, and the
Administrator. Who may edit: the owner, reviewers and the owner's team while it is Draft or In review; the
Administrator always (except while viewing as someone, which is refused before the store is reached).
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backend.identity_v5 import directory
from backend.playbook_v5 import paths

LOCK = threading.RLock()
_READY: set[str] = set()

SEED_VERSION = "pb-1"
#: Deal Desk edition (PLAN_DEALDESK_EDITION Round C): the DD-06 committee paper and the policy library, nothing of the
#: Cockpit's documents (backend.playbook_v5.seed.apply_dealdesk).
SEED_VERSION_DEALDESK = "pb-1-dd"


def seed_version() -> str:
    """The seed this process expects in its store: the Deal Desk edition's or the full product's."""
    from backend.v5common.edition import is_dealdesk
    return SEED_VERSION_DEALDESK if is_dealdesk() else SEED_VERSION

STATUSES = ("draft", "in_review", "approved", "presented")
STATUS_LABEL = {"draft": "Draft", "in_review": "In review", "approved": "Approved", "presented": "Presented"}
#: from -> {to: who may do it}. "editor" = owner, reviewers, owner's team; "reviewer" = a reviewer or admin.
TRANSITIONS: dict[str, dict[str, str]] = {
    "draft": {"in_review": "editor"},
    "in_review": {"approved": "reviewer", "draft": "editor"},
    "approved": {"presented": "editor", "draft": "reviewer"},
    "presented": {},
}
EDITABLE = ("draft", "in_review")

BLOCK_KINDS = ("paragraph", "heading", "bullets", "kpis", "table", "chart", "rag", "callout")
FORMATS = ("sar", "pct", "bps", "int", "num", "num4", "rating", "date", "text")
SOURCE_TYPES = ("investigation", "project", "cockpit-thread", "attention-item", "early-warning-list", "borrower",
                "whatif-thread", "whatif-scenario", "report", "analysis", "document", "scorecard-validation",
                "data-extract", "policy-document", "circular", "upload", "dealdesk-proposal", "dealdesk-analysis",
                "lens", "crm-compliance", "thread-answer")  # R16 t (M7)
MAX_TEXT = 8000
MAX_BLOCKS = 60
MAX_FILE = 15 * 1024 * 1024
BANNED = re.compile(r"synthetic|(?<![\w-])demo(?![\w-])|demo[- ]data", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, template TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
  owner TEXT NOT NULL, reviewers TEXT NOT NULL DEFAULT '[]', due_date TEXT, book TEXT NOT NULL DEFAULT '',
  period TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT 'template', sections TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_versions(
  report_id TEXT NOT NULL, version INTEGER NOT NULL, at TEXT NOT NULL, who TEXT NOT NULL, action TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '', snapshot TEXT NOT NULL, PRIMARY KEY(report_id, version));
CREATE TABLE IF NOT EXISTS report_history(
  id INTEGER PRIMARY KEY, report_id TEXT NOT NULL, at TEXT NOT NULL, who TEXT NOT NULL, from_status TEXT,
  to_status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS report_comments(
  id TEXT PRIMARY KEY, report_id TEXT NOT NULL, section_id TEXT, at TEXT NOT NULL, author TEXT NOT NULL,
  body TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS files(
  id TEXT PRIMARY KEY, owner_kind TEXT NOT NULL, owner_id TEXT NOT NULL, section_id TEXT, name TEXT NOT NULL,
  content_type TEXT NOT NULL, size INTEGER NOT NULL, path TEXT NOT NULL, uploaded_at TEXT NOT NULL,
  uploaded_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS thread_messages(
  id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, report_id TEXT, role TEXT NOT NULL, author TEXT, at TEXT NOT NULL,
  text TEXT NOT NULL, actions TEXT NOT NULL DEFAULT '[]', suggestions TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS idempotency(
  key TEXT NOT NULL, actor TEXT NOT NULL, response TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY(key, actor));
CREATE TABLE IF NOT EXISTS policy_documents(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
  book TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, effective_from TEXT, approved_by TEXT,
  uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '', clauses TEXT NOT NULL DEFAULT '[]', interpretation TEXT,
  decided_at TEXT, decided_by TEXT, decision_note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS policy_pack_versions(
  version INTEGER PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
  effective_from TEXT, approved_by TEXT, change TEXT NOT NULL, documents TEXT NOT NULL DEFAULT '[]',
  pack TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
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
    return f"{prefix}_{secrets.token_hex(4)}"


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _l(v: str | None, default: Any = None) -> Any:
    return json.loads(v) if v else default


# ------------------------------------------------------------- connection


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
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
            return {"store": key, "created": False}
        con = _open(path)
        try:
            con.executescript(SCHEMA)
            version = seed_version()
            row = con.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
            if row is not None and row["value"] != version:
                con.close()
                path.unlink()
                con = _open(path)
                con.executescript(SCHEMA)
                row = None
            created = row is None
            if created:
                from backend.playbook_v5 import seed

                if version == SEED_VERSION_DEALDESK:
                    seed.apply_dealdesk(con)
                else:
                    seed.apply(con)
                con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seed_version', ?)", (version,))
            else:  # R6 policy (P2): an existing store gains CBO BM-1230 once, keeping everything it holds
                from backend.playbook_v5 import seed

                seed.ensure_bm1230(con)
                seed.ensure_cbuae_crm(con)  # R7 (C1): CBUAE CRM Standards in, BM-1230 withdrawn
            con.commit()
        finally:
            con.close()
        _READY.add(key)
    if created:
        from backend.playbook_v5 import policy

        with db() as con:
            policy.write_active_pack(con)
    return {"store": key, "created": created}


def reset_ready() -> None:
    _READY.clear()


def table_counts(con: sqlite3.Connection) -> dict[str, int]:
    names = ["reports", "report_versions", "report_comments", "thread_messages", "files", "policy_documents",
             "policy_pack_versions"]
    return {n: int(con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]) for n in names}


# ------------------------------------------------------------------ people

_USERS = {u["username"]: u for u in directory.seed_users()}


def person(username: str | None) -> dict[str, Any] | None:
    if not username:
        return None
    u = _USERS.get(username)
    if u is None:
        return {"username": username, "name": username, "initials": username[:2].upper(), "title": ""}
    return {"username": u["username"], "name": u["name"], "initials": u["initials"], "title": u["title"]}


def team(username: str | None) -> str:
    return (_USERS.get(username or "") or {}).get("team", "")


def is_admin(username: str) -> bool:
    return bool((_USERS.get(username) or {}).get("is_admin"))


def check_users(names: list[str], field: str) -> list[str]:
    out: list[str] = []
    for n in names:
        n = (n or "").strip()
        if n not in _USERS:
            raise Invalid(f"{field}: {n!r} is not in the directory.")
        if n not in out:
            out.append(n)
    return out


def clean_text(text: str, field: str, limit: int = MAX_TEXT) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        raise Invalid(f"{field} is longer than {limit} characters.")
    if BANNED.search(text):
        raise Invalid(f"{field} contains a banned label (\"Synthetic\", \"Demo\" or \"demo data\").")
    return text


# ------------------------------------------------------------------ blocks


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise Invalid("A value must be a number, not true/false.")
    try:
        f = float(v)
    except (TypeError, ValueError) as exc:
        raise Invalid(f"{v!r} is not a number.") from exc
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _fmt(v: Any) -> str:
    v = v or "text"
    if v not in FORMATS:
        raise Invalid(f"Unknown format {v!r}. Formats: {', '.join(FORMATS)}.")
    return v


def _status(v: Any) -> str | None:
    if v in (None, ""):
        return None
    v = str(v).lower()
    if v not in ("green", "amber", "red"):
        raise Invalid("A status is green, amber or red.")
    return v


def clean_block(b: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(b, dict):
        raise Invalid("A block is an object.")
    kind = b.get("kind")
    if kind not in BLOCK_KINDS:
        raise Invalid(f"Unknown block kind {kind!r}. Kinds: {', '.join(BLOCK_KINDS)}.")
    out: dict[str, Any] = {"id": b.get("id") or new_id("blk"), "kind": kind}
    if kind == "paragraph":
        out["text"] = clean_text(str(b.get("text", "")), "Paragraph")
    elif kind == "heading":
        out["text"] = clean_text(str(b.get("text", "")), "Heading", 200)
        out["level"] = 3 if b.get("level") == 3 else 2
    elif kind == "callout":
        out["text"] = clean_text(str(b.get("text", "")), "Callout", 2000)
        out["tone"] = b.get("tone") if b.get("tone") in ("info", "warning", "critical") else "info"
    elif kind == "bullets":
        items = b.get("items") or []
        if not isinstance(items, list) or len(items) > 40:
            raise Invalid("Bullets: up to 40 items.")
        out["items"] = [clean_text(str(i), "Bullet", 2000) for i in items]
    elif kind == "kpis":
        items = b.get("items") or []
        if not isinstance(items, list) or len(items) > 8:
            raise Invalid("Key figures: up to 8 items.")
        out["items"] = [{"label": clean_text(str(i.get("label", "")), "Key figure label", 120),
                         "value": _num(i.get("value")), "format": _fmt(i.get("format")),
                         **({"delta": _num(i.get("delta"))} if i.get("delta") is not None else {}),
                         **({"status": _status(i.get("status"))} if i.get("status") else {}),
                         **({"note": clean_text(str(i.get("note")), "Key figure note", 200)} if i.get("note") else {})}
                        for i in items]
    elif kind == "table":
        cols = b.get("columns") or []
        rows = b.get("rows") or []
        if not isinstance(cols, list) or not 1 <= len(cols) <= 30:
            raise Invalid("A table has 1 to 30 columns.")
        if not isinstance(rows, list) or len(rows) > 500:
            raise Invalid("A table has up to 500 rows.")
        out["columns"] = [{"key": str(c.get("key")), "label": clean_text(str(c.get("label", c.get("key"))), "Column", 120),
                           "format": _fmt(c.get("format"))} for c in cols]
        keys = [c["key"] for c in out["columns"]]
        fmts = {c["key"]: c["format"] for c in out["columns"]}
        clean_rows = []
        for r in rows:
            if not isinstance(r, dict):
                raise Invalid("A table row is an object keyed by column key.")
            row: dict[str, Any] = {}
            for k in keys:
                v = r.get(k)
                if fmts[k] in ("text", "rating", "date"):
                    row[k] = None if v is None else clean_text(str(v), "Cell", 500)
                else:
                    row[k] = _num(v)
            clean_rows.append(row)
        out["rows"] = clean_rows
        if b.get("title"):
            out["title"] = clean_text(str(b["title"]), "Table title", 200)
        if b.get("note"):
            out["note"] = clean_text(str(b["note"]), "Table note", 1000)
    elif kind == "chart":
        fig = b.get("figure") or {}
        if not isinstance(fig, dict) or not isinstance(fig.get("data", []), list):
            raise Invalid("A chart's figure is Plotly JSON: {data: [...], layout: {...}}.")
        if len(_j(fig)) > 1_500_000:
            raise Invalid("A chart's figure is larger than 1.5 MB.")
        if BANNED.search(_j(fig)):
            raise Invalid("Chart text contains a banned label.")
        out["title"] = clean_text(str(b.get("title", "")), "Chart title", 200)
        out["figure"] = {"data": fig.get("data", []), "layout": fig.get("layout", {})}
        if b.get("png_base64"):
            out["png_base64"] = str(b["png_base64"])
        if b.get("note"):
            out["note"] = clean_text(str(b["note"]), "Chart note", 1000)
    elif kind == "rag":
        items = b.get("items") or []
        if not isinstance(items, list) or len(items) > 60:
            raise Invalid("Verdicts: up to 60 items.")
        out["items"] = [{"test": clean_text(str(i.get("test", "")), "Test", 200), "value": _num(i.get("value")),
                         "format": _fmt(i.get("format")),
                         "threshold": clean_text(str(i.get("threshold", "")), "Threshold", 300),
                         "status": _status(i.get("status")) or "amber",
                         "comment": clean_text(str(i.get("comment", "")), "Comment", 1000)} for i in items]
        if b.get("title"):
            out["title"] = clean_text(str(b["title"]), "Verdicts title", 200)
    return out


def clean_source(s: dict[str, Any] | None) -> dict[str, Any] | None:
    if not s:
        return None
    t = s.get("type")
    if t not in SOURCE_TYPES:
        raise Invalid(f"Unknown source type {t!r}.")
    href = str(s.get("href") or "")
    if href and not href.startswith("/"):
        raise Invalid("A source href is an in-app path starting with '/'.")
    out = {"type": t, "id": str(s.get("id", ""))[:120], "label": clean_text(str(s.get("label", "")), "Source label", 200),
           "href": href[:500]}
    if s.get("summary"):
        out["summary"] = clean_text(str(s["summary"]), "Source summary", 400)
    if isinstance(s.get("meta"), dict) and len(_j(s["meta"])) <= 2048:
        out["meta"] = s["meta"]
    return out


def make_section(title: str, blocks: list[dict[str, Any]], who: str, source: dict[str, Any] | None = None,
                 status: str | None = None, section_id: str | None = None) -> dict[str, Any]:
    if len(blocks) > MAX_BLOCKS:
        raise Invalid(f"A section has up to {MAX_BLOCKS} blocks.")
    clean = [clean_block(b) for b in blocks]
    return {"id": section_id or new_id("sec"), "title": clean_text(title, "Section title", 200) or "Untitled section",
            "blocks": clean, "source": clean_source(source),
            "status": status or ("imported" if source else ("drafted" if clean else "empty")),
            "updated_at": now(), "updated_by": who}


# ----------------------------------------------------------------- reports


def _row(con: sqlite3.Connection, report_id: str) -> sqlite3.Row:
    r = con.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if r is None:
        raise NotFound(f"There is no report {report_id!r}.")
    return r


def _overdue(r: sqlite3.Row) -> bool:
    return bool(r["due_date"] and r["status"] in ("draft", "in_review") and r["due_date"] < date.today().isoformat())


def report_row(r: sqlite3.Row) -> dict[str, Any]:
    from backend.playbook_v5 import templates

    sections = _l(r["sections"], [])
    reviewers = _l(r["reviewers"], [])
    return {"id": r["id"], "title": r["title"], "template": r["template"],
            "template_name": templates.name(r["template"]), "status": r["status"],
            "status_label": STATUS_LABEL[r["status"]], "owner": person(r["owner"]),
            "reviewers": [person(u) for u in reviewers], "due_date": r["due_date"], "overdue": _overdue(r),
            "created_at": r["created_at"], "updated_at": r["updated_at"], "version": r["version"],
            "section_count": len(sections), "book": r["book"], "period": r["period"], "origin": r["origin"],
            "href": f"/playbook?report={r['id']}"}


def can_see(r: sqlite3.Row | dict[str, Any], me: str, shared: set[str]) -> bool:
    owner = r["owner"] if isinstance(r, sqlite3.Row) else r["owner"]["username"]
    reviewers = _l(r["reviewers"], []) if isinstance(r, sqlite3.Row) else [p["username"] for p in r["reviewers"]]
    rid = r["id"]
    return bool(is_admin(me) or owner == me or me in reviewers or rid in shared
                or (team(owner) and team(owner) == team(me) and team(me) != "admin"))


def can_edit(r: sqlite3.Row, me: str) -> bool:
    if r["status"] not in EDITABLE:
        return False
    reviewers = _l(r["reviewers"], [])
    return bool(is_admin(me) or r["owner"] == me or me in reviewers
                or (team(r["owner"]) and team(r["owner"]) == team(me)))


def _allowed(r: sqlite3.Row, me: str) -> list[str]:
    out = []
    reviewers = _l(r["reviewers"], [])
    for to, who in TRANSITIONS[r["status"]].items():
        if who == "reviewer" and (me in reviewers or is_admin(me)):
            out.append(to)
        elif who == "editor" and (is_admin(me) or r["owner"] == me or me in reviewers
                                  or (team(r["owner"]) and team(r["owner"]) == team(me))):
            out.append(to)
    return out


def _section_out(s: dict[str, Any]) -> dict[str, Any]:
    return {**s, "updated_by": person(s.get("updated_by"))}


def report(con: sqlite3.Connection, report_id: str, me: str = "") -> dict[str, Any]:
    r = _row(con, report_id)
    out = report_row(r)
    out["sections"] = [_section_out(s) for s in _l(r["sections"], [])]
    out["history"] = [{"at": h["at"], "who": person(h["who"]), "from": h["from_status"], "to": h["to_status"],
                       "note": h["note"]} for h in con.execute(
        "SELECT * FROM report_history WHERE report_id=? ORDER BY id", (report_id,))]
    out["comments"] = [comment_row(c) for c in con.execute(
        "SELECT * FROM report_comments WHERE report_id=? ORDER BY at, id", (report_id,))]
    out["files"] = [file_row(f) for f in con.execute(
        "SELECT * FROM files WHERE owner_kind='report' AND owner_id=? ORDER BY uploaded_at, id", (report_id,))]
    out["thread_id"] = f"th_{report_id}"
    out["workflow"] = list(STATUSES)
    out["can_edit"] = can_edit(r, me) if me else False
    out["allowed_transitions"] = _allowed(r, me) if me else []
    return out


def reports(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute("SELECT * FROM reports ORDER BY updated_at DESC, id"))


def _snapshot(con: sqlite3.Connection, report_id: str, who: str, action: str, summary: str) -> int:
    r = _row(con, report_id)
    v = int(r["version"]) + 1
    at = now()
    con.execute("UPDATE reports SET version=?, updated_at=? WHERE id=?", (v, at, report_id))
    snap = report(con, report_id)
    snap.pop("comments", None)
    con.execute("INSERT INTO report_versions(report_id, version, at, who, action, summary, snapshot) "
                "VALUES(?,?,?,?,?,?,?)", (report_id, v, at, who, action, summary[:300], _j(snap)))
    return v


def require_edit(con: sqlite3.Connection, report_id: str, me: str) -> sqlite3.Row:
    r = _row(con, report_id)
    if not can_edit(r, me):
        if r["status"] not in EDITABLE:
            raise NotPermitted(f"This report is {STATUS_LABEL[r['status']]}; reopen it to Draft to change it.")
        raise NotPermitted("You can read this report but not edit it.")
    return r


def create_report(con: sqlite3.Connection, me: str, title: str, template: str, book: str = "", period: str = "",
                  due_date: str | None = None, reviewers: list[str] | None = None, origin: str = "template",
                  sections: list[dict[str, Any]] | None = None, report_id: str | None = None,
                  at: str | None = None) -> dict[str, Any]:
    from backend.playbook_v5 import templates

    title = clean_text(title, "Title", 200)
    if not title:
        raise Invalid("A report needs a title.")
    if template not in templates.IDS:
        raise Invalid(f"Unknown template {template!r}. Templates: {', '.join(templates.IDS)}.")
    if book not in ("", "corporate", "retail", "both"):
        raise Invalid("book is corporate, retail or both.")
    if due_date:
        _check_date(due_date, "due_date")
    reviewers = check_users(reviewers or [], "reviewers")
    if sections is None:
        sections = [make_section(t, [], me, status="empty") for t in templates.sections(template)]
    rid = report_id or new_id("rp")
    stamp = at or now()
    con.execute("INSERT INTO reports(id, title, template, status, owner, reviewers, due_date, book, period, origin, "
                "sections, version, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (rid, title, template, "draft", me, _j(reviewers), due_date, book, period[:20], origin,
                 _j(sections), stamp, stamp))
    con.execute("INSERT INTO report_history(report_id, at, who, from_status, to_status, note) VALUES(?,?,?,?,?,?)",
                (rid, stamp, me, None, "draft", "Created"))
    _snapshot(con, rid, me, "created", f"Created from the {templates.name(template)} template"
              if origin == "template" else "Created")
    return report(con, rid, me)


def _check_date(v: str, field: str) -> None:
    try:
        date.fromisoformat(v)
    except ValueError as exc:
        raise Invalid(f"{field} is a date, YYYY-MM-DD.") from exc


def update_report(con: sqlite3.Connection, me: str, report_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    r = _row(con, report_id)
    meta_only = set(fields) <= {"due_date", "reviewers"}
    if not meta_only:
        require_edit(con, report_id, me)
    elif not (can_edit(r, me) or is_admin(me) or r["owner"] == me):
        raise NotPermitted("Only the owner, a reviewer or the team can change this report.")
    sets: dict[str, Any] = {}
    if "title" in fields and fields["title"] is not None:
        t = clean_text(str(fields["title"]), "Title", 200)
        if not t:
            raise Invalid("A report needs a title.")
        sets["title"] = t
    if "due_date" in fields:
        if fields["due_date"]:
            _check_date(fields["due_date"], "due_date")
        sets["due_date"] = fields["due_date"] or None
    if "reviewers" in fields and fields["reviewers"] is not None:
        sets["reviewers"] = _j(check_users(list(fields["reviewers"]), "reviewers"))
    if "owner" in fields and fields["owner"]:
        sets["owner"] = check_users([fields["owner"]], "owner")[0]
    if "book" in fields and fields["book"] is not None:
        if fields["book"] not in ("", "corporate", "retail", "both"):
            raise Invalid("book is corporate, retail or both.")
        sets["book"] = fields["book"]
    if "period" in fields and fields["period"] is not None:
        sets["period"] = str(fields["period"])[:20]
    if not sets:
        return report(con, report_id, me)
    con.execute(f"UPDATE reports SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), report_id))
    _snapshot(con, report_id, me, "details", "Changed " + ", ".join(k.replace("_", " ") for k in sets))
    return report(con, report_id, me)


def set_status(con: sqlite3.Connection, me: str, report_id: str, to: str, note: str = "") -> dict[str, Any]:
    r = _row(con, report_id)
    if to not in STATUSES:
        raise Invalid(f"Unknown status {to!r}.")
    if to not in TRANSITIONS[r["status"]]:
        raise Invalid(f"A report cannot go from {STATUS_LABEL[r['status']]} to {STATUS_LABEL[to]}.")
    if to not in _allowed(r, me):
        need = TRANSITIONS[r["status"]][to]
        raise NotPermitted("Only a reviewer can approve this report." if need == "reviewer"
                           else "Only the owner, a reviewer or the team can do that.")
    if to == "in_review" and not _l(r["reviewers"], []):
        raise Invalid("Name at least one reviewer before sending the report for review.")
    note = clean_text(note, "Note", 2000)
    at = now()
    con.execute("UPDATE reports SET status=? WHERE id=?", (to, report_id))
    con.execute("INSERT INTO report_history(report_id, at, who, from_status, to_status, note) VALUES(?,?,?,?,?,?)",
                (report_id, at, me, r["status"], to, note))
    _snapshot(con, report_id, me, "status", f"{STATUS_LABEL[r['status']]} to {STATUS_LABEL[to]}"
              + (f": {note}" if note else ""))
    return report(con, report_id, me)


def _sections(r: sqlite3.Row) -> list[dict[str, Any]]:
    return _l(r["sections"], [])


def _save_sections(con: sqlite3.Connection, report_id: str, sections: list[dict[str, Any]]) -> None:
    con.execute("UPDATE reports SET sections=? WHERE id=?", (_j(sections), report_id))


def _insert(sections: list[dict[str, Any]], section: dict[str, Any], position: str) -> list[dict[str, Any]]:
    position = position or "end"
    if position == "start":
        return [section, *sections]
    if position.startswith("after:"):
        sid = position.split(":", 1)[1]
        for i, s in enumerate(sections):
            if s["id"] == sid:
                return [*sections[:i + 1], section, *sections[i + 1:]]
        raise Invalid(f"There is no section {sid!r} to insert after.")
    if position != "end":
        raise Invalid("position is end, start or after:<section id>.")
    return [*sections, section]


def add_section(con: sqlite3.Connection, me: str, report_id: str, title: str, blocks: list[dict[str, Any]],
                position: str = "end", source: dict[str, Any] | None = None, action: str = "section",
                summary: str = "") -> tuple[dict[str, Any], str, int]:
    r = require_edit(con, report_id, me)
    section = make_section(title, blocks, me, source)
    sections = _sections(r)
    # An import into a report whose template section of the same name is still empty fills that section.
    target = next((s for s in sections if s["status"] == "empty" and s["title"].lower() == section["title"].lower()),
                  None)
    if target is not None and position in ("", "end"):
        section["id"] = target["id"]
        sections = [section if s["id"] == target["id"] else s for s in sections]
    else:
        sections = _insert(sections, section, position)
    _save_sections(con, report_id, sections)
    v = _snapshot(con, report_id, me, action, summary or f"Added section “{section['title']}”")
    return report(con, report_id, me), section["id"], v


def update_section(con: sqlite3.Connection, me: str, report_id: str, section_id: str, title: str | None = None,
                   blocks: list[dict[str, Any]] | None = None, action: str = "edit", summary: str = "",
                   status: str | None = None) -> dict[str, Any]:
    r = require_edit(con, report_id, me)
    sections = _sections(r)
    for i, s in enumerate(sections):
        if s["id"] == section_id:
            new = dict(s)
            if title is not None:
                new["title"] = clean_text(title, "Section title", 200) or s["title"]
            if blocks is not None:
                if len(blocks) > MAX_BLOCKS:
                    raise Invalid(f"A section has up to {MAX_BLOCKS} blocks.")
                new["blocks"] = [clean_block(b) for b in blocks]
            new["status"] = status or ("edited" if s["status"] != "empty" else ("drafted" if new["blocks"] else "empty"))
            new["updated_at"], new["updated_by"] = now(), me
            sections[i] = new
            _save_sections(con, report_id, sections)
            _snapshot(con, report_id, me, action, summary or f"Edited section “{new['title']}”")
            return report(con, report_id, me)
    raise NotFound(f"There is no section {section_id!r} in this report.")


def delete_section(con: sqlite3.Connection, me: str, report_id: str, section_id: str) -> dict[str, Any]:
    r = require_edit(con, report_id, me)
    sections = _sections(r)
    gone = next((s for s in sections if s["id"] == section_id), None)
    if gone is None:
        raise NotFound(f"There is no section {section_id!r} in this report.")
    _save_sections(con, report_id, [s for s in sections if s["id"] != section_id])
    _snapshot(con, report_id, me, "delete", f"Removed section “{gone['title']}”")
    return report(con, report_id, me)


def move_section(con: sqlite3.Connection, me: str, report_id: str, section_id: str, direction: str) -> dict[str, Any]:
    r = require_edit(con, report_id, me)
    sections = _sections(r)
    idx = next((i for i, s in enumerate(sections) if s["id"] == section_id), None)
    if idx is None:
        raise NotFound(f"There is no section {section_id!r} in this report.")
    j = idx - 1 if direction == "up" else idx + 1
    if direction not in ("up", "down"):
        raise Invalid("direction is up or down.")
    if 0 <= j < len(sections):
        sections[idx], sections[j] = sections[j], sections[idx]
        _save_sections(con, report_id, sections)
        _snapshot(con, report_id, me, "move", f"Moved “{sections[j]['title']}” {direction}")
    return report(con, report_id, me)


# ---------------------------------------------------------------- comments


def comment_row(c: sqlite3.Row) -> dict[str, Any]:
    return {"id": c["id"], "at": c["at"], "author": person(c["author"]), "body": c["body"],
            "section_id": c["section_id"], "resolved": bool(c["resolved"])}


def add_comment(con: sqlite3.Connection, me: str, report_id: str, body: str, section_id: str | None = None,
                at: str | None = None) -> dict[str, Any]:
    r = _row(con, report_id)
    body = clean_text(body, "Comment", 4000)
    if not body:
        raise Invalid("A comment needs text.")
    if section_id and not any(s["id"] == section_id for s in _sections(r)):
        raise NotFound(f"There is no section {section_id!r} in this report.")
    cid = new_id("cm")
    con.execute("INSERT INTO report_comments(id, report_id, section_id, at, author, body) VALUES(?,?,?,?,?,?)",
                (cid, report_id, section_id, at or now(), me, body))
    return comment_row(con.execute("SELECT * FROM report_comments WHERE id=?", (cid,)).fetchone())


def resolve_comment(con: sqlite3.Connection, me: str, report_id: str, comment_id: str) -> dict[str, Any]:
    c = con.execute("SELECT * FROM report_comments WHERE id=? AND report_id=?", (comment_id, report_id)).fetchone()
    if c is None:
        raise NotFound(f"There is no comment {comment_id!r}.")
    con.execute("UPDATE report_comments SET resolved=1 WHERE id=?", (comment_id,))
    return comment_row(con.execute("SELECT * FROM report_comments WHERE id=?", (comment_id,)).fetchone())


# ---------------------------------------------------------------- versions


def versions(con: sqlite3.Connection, report_id: str) -> list[dict[str, Any]]:
    _row(con, report_id)
    return [{"version": v["version"], "at": v["at"], "who": person(v["who"]), "action": v["action"],
             "summary": v["summary"]} for v in con.execute(
        "SELECT version, at, who, action, summary FROM report_versions WHERE report_id=? ORDER BY version DESC",
        (report_id,))]


def version(con: sqlite3.Connection, report_id: str, n: int) -> dict[str, Any]:
    v = con.execute("SELECT * FROM report_versions WHERE report_id=? AND version=?", (report_id, n)).fetchone()
    if v is None:
        raise NotFound(f"Report {report_id!r} has no version {n}.")
    snap = _l(v["snapshot"], {})
    snap["can_edit"] = False
    snap["allowed_transitions"] = []
    snap.setdefault("comments", [])
    return {"version": n, "at": v["at"], "who": person(v["who"]), "report": snap}


def restore_version(con: sqlite3.Connection, me: str, report_id: str, n: int) -> dict[str, Any]:
    require_edit(con, report_id, me)
    snap = version(con, report_id, n)["report"]
    sections = [{**s, "updated_by": (s.get("updated_by") or {}).get("username", me)
                 if isinstance(s.get("updated_by"), dict) else s.get("updated_by", me)} for s in snap["sections"]]
    con.execute("UPDATE reports SET title=?, sections=? WHERE id=?", (snap["title"], _j(sections), report_id))
    _snapshot(con, report_id, me, "restore", f"Restored version {n}")
    return report(con, report_id, me)


# ------------------------------------------------------------------- files


def file_row(f: sqlite3.Row) -> dict[str, Any]:
    return {"id": f["id"], "name": f["name"], "size": f["size"], "content_type": f["content_type"],
            "uploaded_at": f["uploaded_at"], "uploaded_by": person(f["uploaded_by"]), "section_id": f["section_id"]}


def save_file(con: sqlite3.Connection, me: str, owner_kind: str, owner_id: str, name: str, content_type: str,
              data: bytes, section_id: str | None = None, at: str | None = None) -> dict[str, Any]:
    if len(data) > MAX_FILE:
        raise Invalid("A file is up to 15 MB.")
    fid = new_id("f")
    safe = re.sub(r"[^\w.\- ]+", "_", name or "file")[:120] or "file"
    d = paths.files_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{fid}_{safe}"
    p.write_bytes(data)
    con.execute("INSERT INTO files(id, owner_kind, owner_id, section_id, name, content_type, size, path, uploaded_at, "
                "uploaded_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (fid, owner_kind, owner_id, section_id, safe, content_type or "application/octet-stream", len(data),
                 p.name, at or now(), me))
    return file_row(con.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone())


def read_file(con: sqlite3.Connection, owner_kind: str, owner_id: str, file_id: str) -> tuple[dict[str, Any], bytes]:
    f = con.execute("SELECT * FROM files WHERE id=? AND owner_kind=? AND owner_id=?",
                    (file_id, owner_kind, owner_id)).fetchone()
    if f is None:
        raise NotFound(f"There is no file {file_id!r}.")
    return file_row(f), (paths.files_dir() / f["path"]).read_bytes()


# ------------------------------------------------------------------ thread


def message_row(m: sqlite3.Row) -> dict[str, Any]:
    return {"id": m["id"], "role": m["role"], "at": m["at"], "author": person(m["author"]), "text": m["text"],
            "actions": _l(m["actions"], []), "suggestions": _l(m["suggestions"], [])}


def add_message(con: sqlite3.Connection, thread_id: str, report_id: str | None, role: str, author: str | None,
                text: str, actions: list[dict[str, Any]] | None = None, suggestions: list[str] | None = None,
                at: str | None = None) -> dict[str, Any]:
    mid = new_id("msg")
    if role == "assistant":
        # The turn's process trace (PLAN_R5 G4) rides with the answer, so a reloaded thread still shows it.
        from backend.convo import trace as _trace
        rec = _trace.current()
        if rec is not None:
            if rec.steps and rec.steps[-1]["key"] != "publish":
                rec.stage("publishing")
            actions = [*(actions or []), {"kind": "trace", "trace": rec.finish()}]
    con.execute("INSERT INTO thread_messages(id, thread_id, report_id, role, author, at, text, actions, suggestions) "
                "VALUES(?,?,?,?,?,?,?,?,?)", (mid, thread_id, report_id, role, author, at or now(), text,
                                             _j(actions or []), _j(suggestions or [])))
    return message_row(con.execute("SELECT * FROM thread_messages WHERE id=?", (mid,)).fetchone())


def thread(con: sqlite3.Connection, thread_id: str) -> list[dict[str, Any]]:
    return [message_row(m) for m in con.execute(
        "SELECT * FROM thread_messages WHERE thread_id=? ORDER BY at, rowid", (thread_id,))]


# ------------------------------------------------------------- idempotency


def replay(con: sqlite3.Connection, key: str | None, actor: str) -> dict[str, Any] | None:
    if not key:
        return None
    r = con.execute("SELECT response FROM idempotency WHERE key=? AND actor=?", (key[:80], actor)).fetchone()
    return _l(r["response"]) if r else None


def remember(con: sqlite3.Connection, key: str | None, actor: str, response: dict[str, Any]) -> None:
    if key:
        con.execute("INSERT OR REPLACE INTO idempotency(key, actor, response, at) VALUES(?,?,?,?)",
                    (key[:80], actor, _j(response), now()))
