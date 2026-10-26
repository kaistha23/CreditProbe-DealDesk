"""Playbook and Policy Docs service (v5): `uvicorn backend.playbook_v5.api:app --port 8506`.

Routes: docs/v5/PLAYBOOK_SERVICE.md (every route) and docs/v5/PLAYBOOK_API.md (the import contract for other
modules). Identity is the `cp_session` cookie, resolved by the Core service (8505); writes are refused while the
Administrator is viewing as someone.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from backend.playbook_v5 import ai, assistant, export_docx, ingest, paths, policy, resolvers, store, templates

PB = "/api/v1/playbook"
PO = "/api/v1/policy"
COOKIE = "cp_session"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    store.ensure()
    yield


app = FastAPI(title="CreditProbe v5 Playbook and Policy Docs service", version="1.0.0", lifespan=_lifespan)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "playbook", routes={"/api/v1/policy": "policy_docs"})
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])
# The process trace of every assistant turn (PLAN_R5 G4, docs/v5/THREAD_API.md 2.2).
from backend.convo import trace as _trace  # noqa: E402
from backend.identity_v5.client import cookie_name as _cookie_name
_trace.install(app, PB)


# ---------------------------------------------------------------- identity


@dataclass
class Ctx:
    user: dict[str, Any]
    viewing_as: dict[str, Any] | None
    token: str | None

    @property
    def username(self) -> str:
        return self.user["username"]


_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _me(token: str) -> dict[str, Any] | None:
    """/auth/me of the Core service for this cookie (5 s cache). In tests the Core store is read directly."""
    if os.environ.get("PLAYBOOK_IDENTITY_DIRECT") == "1":
        from backend.identity_v5 import store as ids

        with ids.db() as con:
            info = ids.session_info(con, token)
        return None if info is None else {"effective_user": info["effective_user"], "viewing_as": info["viewing_as"]}
    hit = _cache.get(token)
    now = time.monotonic()
    if hit and now - hit[0] < 5:
        return hit[1]
    base = (os.environ.get("CORE_API_ORIGIN") or paths.SERVICES["core"]).rstrip("/")
    try:
        req = urllib.request.Request(base + "/api/v1/auth/me", headers={"Cookie": f"{_cookie_name()}={token}"})
        with urllib.request.urlopen(req, timeout=3) as r:  # noqa: S310 - fixed loopback origin
            out: dict[str, Any] | None = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again in a moment.") from exc
        out = None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again in a moment.") from exc
    _cache[token] = (now, out)
    return out


def ctx(request: Request) -> Ctx:
    token = request.cookies.get(_cookie_name())
    fb = os.environ.get("CP_IDENTITY_FALLBACK_USER", "").strip()
    if not token:
        if fb:
            return Ctx(store.person(fb) | {"username": fb}, None, None)
        raise HTTPException(401, "not signed in")
    me = _me(token)
    if me is None:
        raise HTTPException(401, "not signed in")
    return Ctx(me["effective_user"], me.get("viewing_as"), token)


def writer(c: Ctx = Depends(ctx)) -> Ctx:
    if c.viewing_as is not None:
        raise HTTPException(403, f"Read only while viewing as {c.viewing_as.get('name', '')}.")
    return c


def _run(fn, *args, **kwargs) -> Any:
    try:
        with store.db() as con:
            return fn(con, *args, **kwargs)
    except store.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except store.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc
    except store.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


def _bare(fn, *args, **kwargs) -> Any:
    """`_run` without holding the store: for conversation turns, which open the store only to read and write."""
    try:
        return fn(*args, **kwargs)
    except store.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except store.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc
    except store.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


def _shared(c: Ctx) -> set[str]:
    """Reports mailed to the caller (Mail's shared-with-me), so a shared report is visible to its recipients."""
    if not c.token:
        return set()
    try:
        if os.environ.get("PLAYBOOK_IDENTITY_DIRECT") == "1":
            from backend.identity_v5 import store as ids
            from backend.mail_v5 import store as mail_store

            with ids.db() as con:
                got = mail_store.shared_with_me(con, c.username, ["report"])["objects"]
        else:
            got = resolvers._get("core", "/api/v1/mail/shared-with-me?type=report", c.token).get("objects") or []
        return {o["id"] for o in got}
    except Exception:  # noqa: BLE001 - sharing adds visibility; without Mail the other rules still hold
        return set()


def _guard(con, c: Ctx, report_id: str) -> None:
    r = store._row(con, report_id)
    if not store.can_see(r, c.username, _shared(c)):
        raise store.NotPermitted("This report is not shared with you.")


def _readable(c: Ctx, report_id: str) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.report(con, report_id, c.username)
    return _run(go)


# ------------------------------------------------------------------ models


class NewReportIn(BaseModel):
    title: str = Field(max_length=200)
    template: str
    book: str = ""
    period: str = Field(default="", max_length=20)
    due_date: str | None = None
    reviewers: list[str] = Field(default_factory=list)


class PatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    due_date: str | None = None
    reviewers: list[str] | None = None
    owner: str | None = None
    book: str | None = None
    period: str | None = None


class StatusIn(BaseModel):
    to: str
    note: str = Field(default="", max_length=2000)


class SectionIn(BaseModel):
    title: str = Field(max_length=200)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    position: str = "end"


class SectionPut(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    blocks: list[dict[str, Any]] | None = None


class MoveIn(BaseModel):
    direction: str


class CommentIn(BaseModel):
    body: str = Field(max_length=4000)
    section_id: str | None = None


class TextIn(BaseModel):
    text: str = Field(max_length=4000)
    thread_id: str | None = Field(default=None, max_length=80)


class ApplyIn(BaseModel):
    message_id: str = Field(max_length=80)


class UndoIn(BaseModel):
    version: int | None = Field(default=None, ge=2)


class ImportRef(BaseModel):
    type: str
    id: str = Field(max_length=200)


class ImportIn(BaseModel):
    report_id: str | None = None
    new_report: dict[str, Any] | None = None
    source: dict[str, Any]
    section: dict[str, Any]
    attachment: dict[str, Any] | None = None


class ShareIn(BaseModel):
    to: list[str]
    note: str = Field(default="", max_length=4000)


class DecisionIn(BaseModel):
    add: bool
    effective_from: str | None = None
    approver: str | None = None
    note: str = Field(default="", max_length=2000)


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=2000)


# --------------------------------------------------------------- playbook


@app.get(PB + "/health")
def health() -> dict[str, Any]:
    info = store.ensure()
    with store.db() as con:
        counts = store.table_counts(con)
        pack = policy.active(con)
    return {"status": "ok", "service": "playbook", "port": paths.API_PORT, "store": info["store"],
            "seed_version": store.seed_version(), "counts": counts, "policy_pack": pack["label"],
            "house_style": "shared" if __import__("backend.playbook_v5.house", fromlist=["x"]).shared_available()
            else "local"}


@app.get(PB + "/templates")
def get_templates() -> dict[str, Any]:
    return {"templates": templates.TEMPLATES}


def _visible_rows(con, c: Ctx) -> list[Any]:
    shared = _shared(c)
    return [r for r in store.reports(con) if store.can_see(r, c.username, shared)]


@app.get(PB + "/summary")
def summary(c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        rows = _visible_rows(con, c)
        by = {s: sum(1 for r in rows if r["status"] == s) for s in store.STATUSES}
        return {"by_status": by, "total": len(rows),
                "awaiting_my_review": sum(1 for r in rows if r["status"] == "in_review"
                                          and c.username in store._l(r["reviewers"], [])),
                "mine": sum(1 for r in rows if r["owner"] == c.username),
                "overdue": sum(1 for r in rows if store._overdue(r))}
    return _run(go)


@app.get(PB + "/reports")
def list_reports(status: list[str] = Query(default=[]), template: str = "", q: str = "", editable: bool = False,
                 c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        rows = _visible_rows(con, c)
        if status:
            rows = [r for r in rows if r["status"] in status]
        if template:
            rows = [r for r in rows if r["template"] == template]
        if editable:
            rows = [r for r in rows if store.can_edit(r, c.username)]
        out = [store.report_row(r) for r in rows]
        if q:
            ql = q.lower()
            out = [r for r in out if ql in (r["title"] + " " + r["template_name"] + " " + r["owner"]["name"]).lower()]
        return {"reports": out, "total": len(out)}
    return _run(go)


@app.post(PB + "/reports", status_code=201)
def create_report(payload: NewReportIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    return _run(store.create_report, c.username, payload.title, payload.template, payload.book, payload.period,
                payload.due_date, payload.reviewers)


@app.post(PB + "/reports/upload", status_code=201)
async def upload_report(file: UploadFile = File(...), title: str = Form(""), template: str = Form(""),
                        c: Ctx = Depends(writer)) -> dict[str, Any]:
    data = await file.read()
    if len(data) > store.MAX_FILE:
        raise HTTPException(413, "A file is up to 15 MB.")
    name = file.filename or "upload"

    def go(con):
        sections = ingest.to_sections(name, data, c.username)
        stem = name.rsplit(".", 1)[0].replace("_", " ").strip() or "Uploaded document"
        tpl = template if template in templates.IDS else (templates.guess(f"{title} {stem}") or templates.default())
        rep = store.create_report(con, c.username, ingest.clean(title or stem)[:200], tpl, origin="upload",
                                  sections=sections)
        store.save_file(con, c.username, "report", rep["id"], name, file.content_type or "application/octet-stream", data)
        store.add_message(con, f"th_{rep['id']}", rep["id"], "assistant", None,
                          f"Read “{name}” into {len(sections)} sections. Ask me to draft, revise or import into it.",
                          [], assistant.SUGGEST[:4])
        return store.report(con, rep["id"], c.username)
    return _run(go)


@app.get(PB + "/reports/{report_id}")
def get_report(report_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    return _readable(c, report_id)


@app.patch(PB + "/reports/{report_id}")
def patch_report(report_id: str, payload: PatchIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)

    def go(con):
        _guard(con, c, report_id)
        return store.update_report(con, c.username, report_id, fields)
    return _run(go)


@app.post(PB + "/reports/{report_id}/status")
def report_status(report_id: str, payload: StatusIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.set_status(con, c.username, report_id, payload.to, payload.note)
    return _run(go)


@app.post(PB + "/reports/{report_id}/sections", status_code=201)
def add_section(report_id: str, payload: SectionIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.add_section(con, c.username, report_id, payload.title, payload.blocks, payload.position)[0]
    return _run(go)


@app.put(PB + "/reports/{report_id}/sections/{section_id}")
def put_section(report_id: str, section_id: str, payload: SectionPut, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.update_section(con, c.username, report_id, section_id, payload.title, payload.blocks)
    return _run(go)


@app.delete(PB + "/reports/{report_id}/sections/{section_id}")
def delete_section(report_id: str, section_id: str, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.delete_section(con, c.username, report_id, section_id)
    return _run(go)


@app.post(PB + "/reports/{report_id}/sections/{section_id}/move")
def move_section(report_id: str, section_id: str, payload: MoveIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.move_section(con, c.username, report_id, section_id, payload.direction)
    return _run(go)


@app.post(PB + "/reports/{report_id}/comments", status_code=201)
def add_comment(report_id: str, payload: CommentIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.add_comment(con, c.username, report_id, payload.body, payload.section_id)
    return _run(go)


@app.post(PB + "/reports/{report_id}/comments/{comment_id}/resolve")
def resolve_comment(report_id: str, comment_id: str, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.resolve_comment(con, c.username, report_id, comment_id)
    return _run(go)


@app.get(PB + "/reports/{report_id}/versions")
def list_versions(report_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return {"versions": store.versions(con, report_id)}
    return _run(go)


@app.get(PB + "/reports/{report_id}/versions/{n}")
def get_version(report_id: str, n: int, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.version(con, report_id, n)
    return _run(go)


@app.post(PB + "/reports/{report_id}/versions/{n}/restore")
def restore_version(report_id: str, n: int, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return store.restore_version(con, c.username, report_id, n)
    return _run(go)


@app.get(PB + "/committee")
def committee_playbooks(c: Ctx = Depends(ctx)) -> dict[str, Any]:
    """PLAN_R9 D4: the committee-pack playbooks, each with its steps, data and output."""
    from backend.playbook_v5 import committee
    return committee.catalogue()


@app.post(PB + "/committee/{playbook_id}/run")
def committee_run(playbook_id: str, c: Ctx = Depends(ctx)) -> Response:
    """Run a committee playbook: the Word document from the books and the CBUAE CRM checks now."""
    from backend.playbook_v5 import committee
    if playbook_id not in committee.BY_ID:
        raise HTTPException(404, "That playbook does not exist.")
    data, fname = committee.run_docx(playbook_id, store.person(c.username)["name"])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'})


@app.get(PB + "/reports/{report_id}/export.docx")
def export(report_id: str, c: Ctx = Depends(ctx)) -> Response:
    rep = _readable(c, report_id)
    data = export_docx.build(rep, generated_by=store.person(c.username)["name"])
    fname = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in rep["title"])[:80].strip() or "report"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'})


@app.get(PB + "/reports/{report_id}/files/{file_id}")
def report_file(report_id: str, file_id: str, c: Ctx = Depends(ctx)) -> Response:
    def go(con):
        _guard(con, c, report_id)
        return store.read_file(con, "report", report_id, file_id)
    meta, data = _run(go)
    return Response(data, media_type=meta["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{meta["name"]}"'})


@app.get(PB + "/reports/{report_id}/thread")
def get_thread(report_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return {"thread_id": f"th_{report_id}", "report_id": report_id, "messages": store.thread(con, f"th_{report_id}")}
    return _run(go)


@app.post(PB + "/reports/{report_id}/thread")
def post_thread(report_id: str, payload: TextIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    talk = ai.is_conversation(payload.text)

    def go(con):
        _guard(con, c, report_id)
        return None if talk else assistant.report_turn(con, c.username, report_id, payload.text, c.token)
    out = _run(go)
    if out is None:
        # A question: the conversation runs outside the store lock (a model turn can take a while).
        out = _bare(ai.report_conversation, c.username, report_id, payload.text)
    return out


@app.post(PB + "/threads")
def start_thread(payload: TextIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    return _run(assistant.start_turn, c.username, payload.text, c.token, payload.thread_id)


@app.get(PB + "/threads/{thread_id}")
def get_start_thread(thread_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        msgs = store.thread(con, thread_id)
        if not msgs or (msgs[0]["author"] or {}).get("username") != c.username:
            raise store.NotFound("There is no such conversation.")
        return {"thread_id": thread_id, "messages": msgs}
    return _run(go)


@app.get(PB + "/reports/{report_id}/sections/{section_id}/thread")
def get_section_thread(report_id: str, section_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return ai.section_thread(con, c.username, report_id, section_id)
    return _run(go)


@app.post(PB + "/reports/{report_id}/sections/{section_id}/thread")
def post_section_thread(report_id: str, section_id: str, payload: TextIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    _run(lambda con: _guard(con, c, report_id))
    return _bare(ai.section_turn, c.username, report_id, section_id, payload.text, c.token)


@app.post(PB + "/reports/{report_id}/sections/{section_id}/thread/apply")
def apply_section_answer(report_id: str, section_id: str, payload: ApplyIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        return ai.apply_message(con, c.username, report_id, section_id, payload.message_id)
    return _run(go)


@app.post(PB + "/reports/{report_id}/sections/{section_id}/undo")
def undo_section_merge(report_id: str, section_id: str, payload: UndoIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    """PLAN_R5 P3: one undo restores the section as it was before the assistant's merge (a new version)."""
    def go(con):
        _guard(con, c, report_id)
        return ai.undo_merge(con, c.username, report_id, section_id, payload.version)
    return _run(go)


@app.get(PB + "/sources")
def list_sources(type: str = "", q: str = "", c: Ctx = Depends(ctx)) -> dict[str, Any]:  # noqa: A002
    return resolvers.sources(c.token, type, q)


@app.get(PB + "/section")
def resolve_section(type: str, id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:  # noqa: A002
    """One object as a ready section ({source, section: {title, blocks}}), for an Add to report button."""
    def go(_con):
        src, title, blocks = resolvers.resolve(type, id, c.token)
        return {"source": src, "section": {"title": title, "blocks": blocks}}
    return _run(go)


@app.post(PB + "/reports/{report_id}/import", status_code=201)
def import_ref(report_id: str, payload: ImportRef, c: Ctx = Depends(writer)) -> dict[str, Any]:
    def go(con):
        _guard(con, c, report_id)
        r = store.report(con, report_id, c.username)
        rep, sid, title = assistant.import_into(con, c.username, r, payload.type, payload.id, c.token)
        store.add_message(con, f"th_{report_id}", report_id, "assistant", None, f"Imported into “{title}”.",
                          [{"kind": "imported", "section_id": sid, "label": title}], [])
        return rep
    return _run(go)


@app.post(PB + "/imports", status_code=201)
def imports(payload: ImportIn, c: Ctx = Depends(writer),
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> Any:
    if bool(payload.report_id) == bool(payload.new_report):
        raise HTTPException(422, "Give exactly one of report_id and new_report.")
    sec = payload.section or {}
    if not isinstance(sec.get("blocks"), list) or not 1 <= len(sec["blocks"]) <= store.MAX_BLOCKS:
        raise HTTPException(422, f"section.blocks: 1 to {store.MAX_BLOCKS} blocks.")

    def go(con):
        prior = store.replay(con, idempotency_key, c.username)
        if prior is not None:
            return JSONResponse({**prior, "replayed": True}, status_code=200)
        created = False
        if payload.new_report:
            nr = payload.new_report
            rep = store.create_report(con, c.username, str(nr.get("title", "")), str(nr.get("template", "")),
                                      str(nr.get("book") or ""), str(nr.get("period") or ""), nr.get("due_date"),
                                      list(nr.get("reviewers") or []), origin="import")
            rid, created = rep["id"], True
        else:
            rid = str(payload.report_id)
            _guard(con, c, rid)
        src = store.clean_source(payload.source)
        if src is None:
            raise store.Invalid("source is required.")
        rep, sid, ver = store.add_section(con, c.username, rid, str(sec.get("title") or src["label"]), sec["blocks"],
                                          str(sec.get("position") or "end"), src, action="import",
                                          summary=f"Imported {src['label']}")
        if payload.attachment and payload.attachment.get("file_base64"):
            import base64

            try:
                data = base64.b64decode(payload.attachment["file_base64"], validate=True)
            except ValueError as exc:
                raise store.Invalid("attachment.file_base64 is not base64.") from exc
            store.save_file(con, c.username, "report", rid, str(payload.attachment.get("name") or "attachment"),
                            str(payload.attachment.get("content_type") or "application/octet-stream"), data, sid)
        store.add_message(con, f"th_{rid}", rid, "assistant", None, f"{src['label']} was added from "
                          f"{resolvers.TYPE_LABEL.get(src['type'], src['type'])}.",
                          [{"kind": "imported", "section_id": sid, "label": rep["title"]}], [])
        out = {"report_id": rid, "report_title": rep["title"], "section_id": sid, "version": ver,
               "created_report": created, "href": f"/playbook?report={rid}&section={sid}"}
        store.remember(con, idempotency_key, c.username, out)
        return out
    return _run(go)


@app.post(PB + "/reports/{report_id}/share")
def share(report_id: str, payload: ShareIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    rep = _readable(c, report_id)
    obj = {"type": "report", "id": report_id, "label": rep["title"], "href": f"/playbook?report={report_id}",
           "summary": f"{rep['template_name']}, {rep['status_label']}, version {rep['version']}."}
    body = json.dumps({"to": payload.to, "note": payload.note, "objects": [obj]}).encode()
    base = paths.SERVICES["core"].rstrip("/")
    req = urllib.request.Request(base + "/api/v1/mail/share", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": f"{_cookie_name()}={c.token or ''}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(exc.code, json.loads(exc.read() or b"{}").get("detail", "Mail refused the share.")) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise HTTPException(503, "Mail is temporarily unavailable. Please try again in a moment.") from exc


# ------------------------------------------------------------------ policy


@app.get(PO + "/documents")
def policy_documents(kind: str = "", q: str = "", c: Ctx = Depends(ctx)) -> dict[str, Any]:
    return {"documents": _run(policy.documents, kind, q)}


@app.get(PO + "/documents/{doc_id}")
def policy_document(doc_id: str, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    return _run(policy.document, doc_id)


@app.get(PO + "/documents/{doc_id}/files/{file_id}")
def policy_file(doc_id: str, file_id: str, c: Ctx = Depends(ctx)) -> Response:
    meta, data = _run(store.read_file, "policy", doc_id, file_id)
    return Response(data, media_type=meta["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{meta["name"]}"'})


@app.post(PO + "/documents/upload", status_code=201)
async def policy_upload(file: UploadFile = File(...), title: str = Form(""), kind: str = Form(""),
                        reference: str = Form(""), c: Ctx = Depends(writer)) -> dict[str, Any]:
    data = await file.read()
    if len(data) > store.MAX_FILE:
        raise HTTPException(413, "A file is up to 15 MB.")
    return _run(policy.upload, c.username, file.filename or "upload.txt", data, title, kind, reference)


@app.post(PO + "/documents/{doc_id}/decision")
def policy_decision(doc_id: str, payload: DecisionIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    return _run(policy.decide, c.username, doc_id, payload.add, payload.effective_from, payload.approver, payload.note)


@app.post(PO + "/documents/{doc_id}/withdraw")
def policy_withdraw(doc_id: str, payload: NoteIn, c: Ctx = Depends(writer)) -> dict[str, Any]:
    return _run(policy.withdraw, c.username, doc_id, payload.note)


@app.get(PO + "/pack")
def policy_pack(c: Ctx = Depends(ctx)) -> dict[str, Any]:
    out = _run(policy.active)
    return {**out, "pack": policy.shown(out["pack"])}


@app.get(PO + "/pack/versions")
def policy_versions(c: Ctx = Depends(ctx)) -> dict[str, Any]:
    return {"versions": _run(policy.versions)}


@app.get(PO + "/pack/versions/{v}")
def policy_version(v: int, c: Ctx = Depends(ctx)) -> dict[str, Any]:
    out = _run(policy.version, v)
    out["clauses"] = [policy._clause_out(cl, b) for b in ("corporate", "retail") for cl in policy._flat(out["pack"], b)]
    return out


@app.get(PO + "/clauses")
def policy_clauses(book: str = "", q: str = "", c: Ctx = Depends(ctx)) -> dict[str, Any]:
    return {"clauses": _run(policy.clauses, book, q)}


@app.get(PO + "/explain")
def policy_explain(book: str, measure: str, driver: str = "", segment: str = "", period: str = "") -> dict[str, Any]:
    """No session needed: it reads only the policy pack, and What-If and the drawer call it from the server too."""
    return _run(policy.explain, book, measure, driver, segment, period)
