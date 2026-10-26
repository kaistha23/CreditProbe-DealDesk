"""The Admin domain's store (PLAN_R5 A7): configuration objects with versions, maker-checker changes, audit,
AI runs, evaluation runs and live workflow items. SQLite, one file (var/admin/admin.sqlite; ADMIN_STORE overrides).

Every configuration change goes draft -> submitted -> approved (live) or rejected / withdrawn. The maker cannot
approve their own change. Approving writes the object's next version, keeps the previous ones, and audits it.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.access.policy import admin_store_path
from backend.admin import seed

KINDS = {"policy": "Data access policy", "workflow": "Approval workflow", "role": "Role", "team": "Team",
         "user": "User", "studio": "AI Studio configuration", "setting": "Setting", "param": "Parameter table"}
APPROVER_ROLES = {"admin", "cro"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS live(kind TEXT, id TEXT, version INTEGER, body TEXT, updated_at TEXT, updated_by TEXT,
  PRIMARY KEY(kind, id));
CREATE TABLE IF NOT EXISTS versions(kind TEXT, id TEXT, version INTEGER, body TEXT, change_id TEXT, at TEXT, by TEXT,
  PRIMARY KEY(kind, id, version));
CREATE TABLE IF NOT EXISTS changes(change_id TEXT PRIMARY KEY, kind TEXT, object_id TEXT, op TEXT, title TEXT,
  body TEXT, base_version INTEGER, status TEXT, maker TEXT, checker TEXT, created_at TEXT, submitted_at TEXT,
  decided_at TEXT, comment TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT, kind TEXT,
  target TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS ai_runs(run_id TEXT PRIMARY KEY, at TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS eval_runs(id TEXT PRIMARY KEY, module TEXT, at TEXT, by TEXT, passed INTEGER, total INTEGER,
  body TEXT);
CREATE TABLE IF NOT EXISTS wf_items(item_id TEXT PRIMARY KEY, workflow_id TEXT, body TEXT, status TEXT, created_at TEXT);
"""


class NotFound(Exception):
    pass


class NotPermitted(Exception):
    pass


class Invalid(Exception):
    pass


_LOCK = threading.Lock()
_READY: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    path = admin_store_path()
    ensure(path)
    con = _open(path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def ensure(path: Path | None = None) -> None:
    path = path or admin_store_path()
    key = str(path)
    with _LOCK:
        if key in _READY and path.exists():
            return
        con = _open(path)
        try:
            con.executescript(SCHEMA)
            row = con.execute("SELECT value FROM meta WHERE key='seed'").fetchone()
            if row is not None and row[0] != seed.seed_version() and (row[0].endswith("-dd")) != (seed.seed_version().endswith("-dd")):
                # Deal Desk edition: a store holding the other edition's seed is rebuilt (its seeded runs, workflows,
                # policies and audit rows belong to that edition); a user's own changes in it are not carried over.
                for t in ("live", "versions", "changes", "wf_items", "ai_runs", "audit", "meta"):
                    try:
                        con.execute(f"DELETE FROM {t}")
                    except sqlite3.OperationalError:
                        pass
                row = None
            if row is None:
                _seed(con)
                con.execute("INSERT INTO meta(key, value) VALUES('seed', ?)", (seed.seed_version(),))
            elif con.execute("SELECT 1 FROM live WHERE kind='setting' AND id='model_names'").fetchone() is None:
                # PLAN_R6 B6: a store seeded before the model-name table gets it (display name -> real model ID).
                s = next(x for x in seed.SETTINGS if x["id"] == "model_names")
                _put(con, "setting", s["id"], s, "anne")
            con.commit()
        finally:
            con.close()
        _READY.add(key)


def reset_ready() -> None:
    _READY.clear()


def _put(con: sqlite3.Connection, kind: str, oid: str, body: dict[str, Any], by: str, change_id: str = "seed",
         at: str | None = None) -> int:
    at = at or now()
    r = con.execute("SELECT version FROM live WHERE kind=? AND id=?", (kind, oid)).fetchone()
    v = (r["version"] + 1) if r else 1
    body = {**body, "id": oid}
    con.execute("INSERT OR REPLACE INTO live(kind, id, version, body, updated_at, updated_by) VALUES(?,?,?,?,?,?)",
                (kind, oid, v, json.dumps(body, ensure_ascii=False), at, by))
    con.execute("INSERT INTO versions(kind, id, version, body, change_id, at, by) VALUES(?,?,?,?,?,?,?)",
                (kind, oid, v, json.dumps(body, ensure_ascii=False), change_id, at, by))
    return v


def _seed(con: sqlite3.Connection) -> None:
    at = seed._t(days=30)  # noqa: SLF001
    for r in seed.ROLES:
        _put(con, "role", r["id"], r, "anne", at=at)
    for t in seed.TEAMS:
        _put(con, "team", t["id"], t, "anne", at=at)
    for u in seed.users():
        _put(con, "user", u["username"], u, "anne", at=at)
    for p in seed.POLICIES:
        _put(con, "policy", p["id"], p, "anne", "CH-SEED", at=seed._t(days=12))  # noqa: SLF001
    for w in seed.WORKFLOWS:
        _put(con, "workflow", w["id"], w, "anne", "CH-SEED", at=seed._t(days=9))  # noqa: SLF001
    for s in seed.studio():
        _put(con, "studio", s["id"], s, "anne", at=at)
    for s in seed.SETTINGS:
        _put(con, "setting", s["id"], s, "anne", at=at)
    for r in seed.ai_runs():
        con.execute("INSERT INTO ai_runs(run_id, at, body) VALUES(?,?,?)", (r["run_id"], r["at"], json.dumps(r)))
    # Seeded history: who configured what, and approvals of the seeded policies/workflows.
    for i, p in enumerate(seed.POLICIES):
        _audit(con, "abdullah.alzahrani", "change_submitted", "policy", p["id"], {"title": p["name"]}, at=seed._t(days=13 - i * 0.1))  # noqa: SLF001
        _audit(con, "faisal.alqahtani", "change_approved", "policy", p["id"], {"title": p["name"], "version": 1}, at=seed._t(days=12 - i * 0.1))  # noqa: SLF001
    for i, w in enumerate(seed.WORKFLOWS):
        _audit(con, "anne", "change_submitted", "workflow", w["id"], {"title": w["name"]}, at=seed._t(days=10 - i * 0.1))  # noqa: SLF001
        _audit(con, "faisal.alqahtani", "change_approved", "workflow", w["id"], {"title": w["name"], "version": 1}, at=seed._t(days=9 - i * 0.1))  # noqa: SLF001
    for i, pend in enumerate(seed.PENDING):
        body = pend.get("body")
        oid = pend.get("object_id") or (body or {}).get("id")
        base = None
        if pend["op"] == "update":
            live = get_live(con, pend["kind"], oid)
            body = copy.deepcopy(live["body"])
            for path, val in pend["patch"].items():
                _set_path(body, path, val)
            base = live["version"]
        cid = f"CH-S{i + 1:02d}"
        at2 = seed._t(days=1 + i * 0.3)  # noqa: SLF001
        con.execute("INSERT INTO changes(change_id, kind, object_id, op, title, body, base_version, status, maker,"
                    " checker, created_at, submitted_at, decided_at, comment, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, pend["kind"], oid, pend["op"], pend["title"], json.dumps(body), base, "submitted",
                     pend["maker"], "", at2, at2, None, "", "seed"))
        _audit(con, pend["maker"], "change_submitted", pend["kind"], oid, {"title": pend["title"], "change_id": cid}, at=at2)
    _seed_items(con)


def _seed_items(con: sqlite3.Connection) -> None:
    """Live workflow items: Critical Early Warning names waiting for their RM's action plan, and two proposals (the
    Deal Desk edition seeds the proposals only)."""
    items = [
        ("WI-001", "WF-EWS-CRIT", {"object_type": "ews_name", "object_id": "CB01256", "title": "CB01256 Qassim Advanced Engineering banded Critical: RM action plan",
                                   "step": "s1", "assignee": "nawaf.alotaibi", "opened_at": seed._t(days=3), "due_at": seed._t(days=-2)}),  # noqa: SLF001
        ("WI-002", "WF-EWS-CRIT", {"object_type": "ews_name", "object_id": "CB03800", "title": "CB03800 Turaif Integrated Properties banded Critical: RM action plan",
                                   "step": "s1", "assignee": "nawaf.alotaibi", "opened_at": seed._t(days=11), "due_at": seed._t(days=6),  # noqa: SLF001
                                   "escalated_to": "noura.alharbi"}),
        ("WI-003", "WF-DD-DOA", {"object_type": "deal_proposal", "object_id": "DD-01", "title": "DD-01: approval at the DOA level",
                                 "step": "s3", "assignee": "noura.alharbi", "opened_at": seed._t(days=1), "due_at": seed._t(days=-2)}),  # noqa: SLF001
        ("WI-004", "WF-PB-SIGN", {"object_type": "playbook_report", "object_id": "Q2 2026 credit committee pack",
                                  "title": "Q2 2026 credit committee pack: sign-off", "step": "s3", "assignee": "faisal.alqahtani",
                                  "opened_at": seed._t(days=2), "due_at": seed._t(days=0)}),  # noqa: SLF001
    ]
    live_wfs = {w["id"] for w in seed.WORKFLOWS}
    for iid, wf, body in items:
        if wf not in live_wfs:
            continue
        con.execute("INSERT INTO wf_items(item_id, workflow_id, body, status, created_at) VALUES(?,?,?,?,?)",
                    (iid, wf, json.dumps(body), "open", body["opened_at"]))


def _set_path(body: dict[str, Any], path: str, value: Any) -> None:
    cur: Any = body
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


# ------------------------------------------------------------------ reads
def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {"kind": r["kind"], "id": r["id"], "version": r["version"], "body": json.loads(r["body"]),
            "updated_at": r["updated_at"], "updated_by": r["updated_by"]}


def live_list(con: sqlite3.Connection, kind: str) -> list[dict[str, Any]]:
    return [_row(r) for r in con.execute("SELECT * FROM live WHERE kind=? ORDER BY id", (kind,))]


def get_live(con: sqlite3.Connection, kind: str, oid: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM live WHERE kind=? AND id=?", (kind, oid)).fetchone()
    if r is None:
        raise NotFound(f"No {KINDS.get(kind, kind)} '{oid}'.")
    return _row(r)


def find_live(con: sqlite3.Connection, kind: str, oid: str) -> dict[str, Any] | None:
    try:
        return get_live(con, kind, oid)
    except NotFound:
        return None


def versions(con: sqlite3.Connection, kind: str, oid: str) -> list[dict[str, Any]]:
    return [{"version": r["version"], "body": json.loads(r["body"]), "change_id": r["change_id"], "at": r["at"], "by": r["by"]}
            for r in con.execute("SELECT * FROM versions WHERE kind=? AND id=? ORDER BY version DESC", (kind, oid))]


def _change(r: sqlite3.Row) -> dict[str, Any]:
    return {"change_id": r["change_id"], "kind": r["kind"], "kind_label": KINDS.get(r["kind"], r["kind"]),
            "object_id": r["object_id"], "op": r["op"], "title": r["title"], "body": json.loads(r["body"] or "null"),
            "base_version": r["base_version"], "status": r["status"], "maker": r["maker"], "checker": r["checker"],
            "created_at": r["created_at"], "submitted_at": r["submitted_at"], "decided_at": r["decided_at"],
            "comment": r["comment"], "source": r["source"]}


def changes(con: sqlite3.Connection, kind: str = "", status: str = "", object_id: str = "") -> list[dict[str, Any]]:
    where, args = [], []
    for col, val in (("kind", kind), ("status", status), ("object_id", object_id)):
        if val:
            if col == "status" and "," in val:
                where.append(f"status IN ({','.join('?' * len(val.split(',')))})")
                args += val.split(",")
            else:
                where.append(f"{col}=?")
                args.append(val)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return [_change(r) for r in con.execute(f"SELECT * FROM changes {clause} ORDER BY created_at DESC", args)]


def get_change(con: sqlite3.Connection, cid: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM changes WHERE change_id=?", (cid,)).fetchone()
    if r is None:
        raise NotFound(f"No change '{cid}'.")
    return _change(r)


# ------------------------------------------------------------------ maker-checker
def _audit(con: sqlite3.Connection, actor: str, action: str, kind: str, target: str, detail: dict[str, Any] | None = None,
           at: str | None = None) -> None:
    con.execute("INSERT INTO audit(at, actor, action, kind, target, detail) VALUES(?,?,?,?,?,?)",
                (at or now(), actor, action, kind, target, json.dumps(detail or {}, ensure_ascii=False)))


def audit(con: sqlite3.Connection, actor: str, action: str, kind: str = "", target: str = "",
          detail: dict[str, Any] | None = None) -> None:
    _audit(con, actor, action, kind, target, detail)


def draft(con: sqlite3.Connection, maker: str, kind: str, op: str, body: dict[str, Any] | None, title: str = "",
          object_id: str = "", source: str = "console") -> dict[str, Any]:
    if kind not in KINDS:
        raise Invalid(f"'{kind}' is not something Admin configures.")
    if op not in ("create", "update", "retire"):
        raise Invalid("op is create, update or retire.")
    if kind == "studio" and (object_id or (body or {}).get("id")) == "cockpit":
        raise NotPermitted("The Cockpit's configuration is frozen: it is read-only here.")
    base = None
    if op == "create":
        object_id = object_id or (body or {}).get("id") or ""
        if not object_id:
            object_id = f"{kind[:3].upper()}-{uuid.uuid4().hex[:6].upper()}"
        if find_live(con, kind, object_id):
            raise Invalid(f"{KINDS[kind]} '{object_id}' already exists; draft an update instead.")
    else:
        live = get_live(con, kind, object_id)
        base = live["version"]
        if op == "retire":
            body = {**live["body"], "status": "retired"}
    body = {**(body or {}), "id": object_id}
    _validate(kind, body)
    cid = "CH-" + uuid.uuid4().hex[:8].upper()
    t = now()
    con.execute("INSERT INTO changes(change_id, kind, object_id, op, title, body, base_version, status, maker, checker,"
                " created_at, submitted_at, decided_at, comment, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, kind, object_id, op, title or f"{op.title()} {KINDS[kind].lower()} {body.get('name') or object_id}",
                 json.dumps(body, ensure_ascii=False), base, "draft", maker, "", t, None, None, "", source))
    _audit(con, maker, "change_drafted", kind, object_id, {"change_id": cid, "title": title})
    return get_change(con, cid)


def update_draft(con: sqlite3.Connection, actor: str, cid: str, body: dict[str, Any], title: str = "") -> dict[str, Any]:
    ch = get_change(con, cid)
    if ch["status"] != "draft":
        raise NotPermitted("Only a draft can be edited; withdraw it first.")
    if ch["maker"] != actor:
        raise NotPermitted("Only the maker edits a draft.")
    body = {**body, "id": ch["object_id"]}
    _validate(ch["kind"], body)
    con.execute("UPDATE changes SET body=?, title=? WHERE change_id=?",
                (json.dumps(body, ensure_ascii=False), title or ch["title"], cid))
    return get_change(con, cid)


def submit(con: sqlite3.Connection, actor: str, cid: str) -> dict[str, Any]:
    ch = get_change(con, cid)
    if ch["status"] != "draft":
        raise NotPermitted(f"This change is {ch['status']}, not a draft.")
    if ch["maker"] != actor:
        raise NotPermitted("Only the maker submits a draft.")
    con.execute("UPDATE changes SET status='submitted', submitted_at=? WHERE change_id=?", (now(), cid))
    _audit(con, actor, "change_submitted", ch["kind"], ch["object_id"], {"change_id": cid, "title": ch["title"]})
    return get_change(con, cid)


def can_approve(con: sqlite3.Connection, username: str, is_admin: bool = False) -> bool:
    if is_admin:
        return True
    u = find_live(con, "user", username)
    return bool(u and u["body"].get("role") in APPROVER_ROLES)


def approve(con: sqlite3.Connection, actor: str, cid: str, is_admin: bool = False, comment: str = "") -> dict[str, Any]:
    ch = get_change(con, cid)
    if ch["status"] != "submitted":
        raise NotPermitted(f"This change is {ch['status']}; only a submitted change is approved.")
    if ch["maker"] == actor:
        raise NotPermitted("Four eyes: the maker cannot approve their own change. Another approver (Admin or CRO) must.")
    if not can_approve(con, actor, is_admin):
        raise NotPermitted("Only an Admin or a CRO approves configuration changes.")
    live = find_live(con, ch["kind"], ch["object_id"])
    if ch["op"] != "create" and live and ch["base_version"] and live["version"] != ch["base_version"]:
        raise NotPermitted(f"The live version moved to v{live['version']} since this change was drafted (v{ch['base_version']}). "
                           "Reject it and draft again.")
    v = _put(con, ch["kind"], ch["object_id"], ch["body"], actor, cid)
    t = now()
    con.execute("UPDATE changes SET status='live', checker=?, decided_at=?, comment=? WHERE change_id=?",
                (actor, t, comment, cid))
    _audit(con, actor, "change_approved", ch["kind"], ch["object_id"], {"change_id": cid, "title": ch["title"],
                                                                        "version": v, "maker": ch["maker"]})
    return get_change(con, cid)


def reject(con: sqlite3.Connection, actor: str, cid: str, comment: str = "", is_admin: bool = False) -> dict[str, Any]:
    ch = get_change(con, cid)
    if ch["status"] != "submitted":
        raise NotPermitted(f"This change is {ch['status']}; only a submitted change is rejected.")
    if ch["maker"] == actor:
        raise NotPermitted("The maker withdraws a change rather than rejecting it.")
    if not can_approve(con, actor, is_admin):
        raise NotPermitted("Only an Admin or a CRO decides on configuration changes.")
    con.execute("UPDATE changes SET status='rejected', checker=?, decided_at=?, comment=? WHERE change_id=?",
                (actor, now(), comment, cid))
    _audit(con, actor, "change_rejected", ch["kind"], ch["object_id"], {"change_id": cid, "comment": comment})
    return get_change(con, cid)


def withdraw(con: sqlite3.Connection, actor: str, cid: str) -> dict[str, Any]:
    ch = get_change(con, cid)
    if ch["status"] not in ("draft", "submitted"):
        raise NotPermitted(f"This change is {ch['status']}.")
    if ch["maker"] != actor:
        raise NotPermitted("Only the maker withdraws a change.")
    con.execute("UPDATE changes SET status='withdrawn', decided_at=? WHERE change_id=?", (now(), cid))
    _audit(con, actor, "change_withdrawn", ch["kind"], ch["object_id"], {"change_id": cid})
    return get_change(con, cid)


def _validate(kind: str, body: dict[str, Any]) -> None:
    if kind == "policy":
        if not str(body.get("name") or "").strip():
            raise Invalid("A policy needs a name.")
        books = body.get("books") or []
        if not books or not set(books) <= {"corporate", "retail"}:
            raise Invalid("A policy names at least one book: corporate, retail.")
        from backend.access import dims
        for b, sc in (body.get("scope") or {}).items():
            if b not in dims.FIELDS:
                raise Invalid(f"'{b}' is not a book.")
            for f in sc or {}:
                if f not in dims.FIELDS[b]:
                    raise Invalid(f"A {b} policy cannot filter on '{f}'. Fields: {', '.join(dims.FIELDS[b])}.")
    if kind == "workflow":
        if not str(body.get("name") or "").strip():
            raise Invalid("A workflow needs a name.")
        steps = body.get("steps") or []
        if not steps:
            raise Invalid("A workflow has at least one step.")
        for s in steps:
            if not s.get("name") or not s.get("assignee"):
                raise Invalid("Every step has a name and an assignee.")
            if s.get("sla_days") is not None and float(s["sla_days"]) < 0:
                raise Invalid("An SLA is zero or more days.")
            if s.get("escalate_after_days") not in (None, "") and float(s["escalate_after_days"]) < float(s.get("sla_days") or 0):
                raise Invalid(f"Step '{s['name']}': escalation comes after the SLA, not before.")


# ------------------------------------------------------------------ audit, AI runs, evals, items
def audit_list(con: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
    return [{"id": r["id"], "at": r["at"], "actor": r["actor"], "action": r["action"], "kind": r["kind"],
             "target": r["target"], "detail": json.loads(r["detail"] or "{}")}
            for r in con.execute("SELECT * FROM audit ORDER BY at DESC, id DESC LIMIT ?", (limit,))]


def seeded_runs(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [json.loads(r["body"]) for r in con.execute("SELECT body FROM ai_runs ORDER BY at DESC")]


def save_eval(con: sqlite3.Connection, module: str, by: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    eid = "EV-" + uuid.uuid4().hex[:8].upper()
    passed = sum(1 for r in results if r.get("pass"))
    body = {"id": eid, "module": module, "at": now(), "by": by, "passed": passed, "total": len(results), "results": results}
    con.execute("INSERT INTO eval_runs(id, module, at, by, passed, total, body) VALUES(?,?,?,?,?,?,?)",
                (eid, module, body["at"], by, passed, len(results), json.dumps(body)))
    _audit(con, by, "evaluation_run", "studio", module, {"passed": passed, "total": len(results)})
    return body


def evals(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [json.loads(r["body"]) for r in con.execute("SELECT body FROM eval_runs ORDER BY at DESC LIMIT 100")]


def items(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{"item_id": r["item_id"], "workflow_id": r["workflow_id"], "status": r["status"], **json.loads(r["body"])}
            for r in con.execute("SELECT * FROM wf_items ORDER BY created_at DESC")]


def set_kill_switch(con: sqlite3.Connection, actor: str, module: str, on: bool, reason: str = "") -> dict[str, Any]:
    """The kill switch is an emergency control: it applies at once (no checker), and is audited."""
    live = get_live(con, "studio", module)
    if live["body"].get("read_only"):
        raise NotPermitted("The Cockpit is frozen; its assistant is not switched from here.")
    body = {**live["body"], "kill_switch": bool(on)}
    v = _put(con, "studio", module, body, actor, "KILL-SWITCH")
    _audit(con, actor, "kill_switch_on" if on else "kill_switch_off", "studio", module, {"reason": reason, "version": v})
    return get_live(con, "studio", module)
