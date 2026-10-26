"""Core service (v5): `uvicorn backend.workspace_v5.api:app --port 8505`.

Serves four things on one port, one sqlite store each:

  users, sign-in, view-as ..... backend.identity_v5.api   /api/v1/auth/*, /api/v1/users
  CreditProbe Mail ............ backend.mail_v5.api       /api/v1/mail/*     (docs/v5/MAIL_API.md)
  attention-item chart data ... backend.attention_v5.api  /api/v1/attention/charts
  the Workspace ............... this module              /api/v1/workspace/*
  (My workspace / Inbox, Projects, Investigations, Analyses, Documents)

Every request is answered for the signed-in user (cookie cp_session; the effective user when the
Administrator is viewing as someone). Projects, investigations, analyses and documents are visible to
their owner, to their members, to the owner's team, to anyone they were shared with by mail, and to the
Administrator.

  GET  /health
  GET  /summary
  GET  /inbox?kind=                      conversations (from Mail), mentions, assignments, notifications
  POST /inbox/{item_id}/read
  GET  /projects            GET /projects/{id}            POST /projects
  POST /projects/{id}/tasks                               POST /projects/{id}/tasks/{task_id}/status
  GET  /investigations      GET /investigations/{id}
  POST /investigations/{id}/notes                         POST /investigations/{id}/status
  GET  /analyses            GET /analyses/{id}
  GET  /documents           GET /documents/{id}
  POST /investigations                                    POST /investigations/{id}/items   (add from another screen)
  POST /documents                                         POST /documents/{id}/sections
  S3-2 (analyses refresh, investigation import, project scope/documents/threads): backend.workspace_v5.api_r3
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from pydantic import BaseModel, Field

from backend.identity_v5 import directory, paths as id_paths, store as ids
from backend.identity_v5.api import Ctx, require_ctx, router as identity_router
from backend.mail_v5 import store as mail_store
from backend.mail_v5.api import router as mail_router
from backend.attention_v5.api import router as attention_router
from backend.thread_actions.api import router as thread_actions_router  # R16 t (M7)
from backend.workspace_v5 import answer_first, paths, store

PREFIX = "/api/v1/workspace"

_TEAM = {u["username"]: u["team"] for u in directory.seed_users()}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    ids.ensure()
    store.ensure()
    try:  # PLAN_R4 A3: the seeded project replies, re-answered once through the forked Cockpit conversation
        from backend.workspace_v5 import seed_r3
        seed_r3.refresh_seeded_answers()
    except Exception:  # noqa: BLE001 - the service starts whatever the seed refresh does
        pass
    yield


app = FastAPI(title="CreditProbe v5 Core service", version="2.0.0", lifespan=_lifespan)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "projects", routes={"/api/v1/mail": "mail", "/api/v1/attention": "cockpit"})
app.add_middleware(CORSMiddleware, allow_origins=id_paths.UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"])
app.include_router(identity_router)
app.include_router(mail_router)
app.include_router(attention_router)
app.include_router(thread_actions_router)  # R16 t (M7): Share, Trace, Word, Add to report on every answer


def _run(fn, *args, **kwargs) -> Any:
    try:
        with store.db() as con:
            return fn(con, *args, **kwargs)
    except store.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except store.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc
    except store.Invalid as exc:
        raise HTTPException(400, str(exc)) from exc


# ------------------------------------------------------------- visibility


def _shared(ctx: Ctx, kinds: tuple[str, ...]) -> set[tuple[str, str]]:
    with ids.db() as con:
        got = mail_store.shared_with_me(con, ctx.username, list(kinds))["objects"]
    return {(o["type"], o["id"]) for o in got}


def _can_see(ctx: Ctx, kind: str, item: dict[str, Any], shared: set[tuple[str, str]],
             project_ok: set[str] | None = None) -> bool:
    if ctx.is_admin and ctx.viewing_as is None:
        return True
    me = ctx.username
    owner = (item.get("owner") or {}).get("id")
    members = {m["id"] for m in item.get("members", []) if m}
    pid = item.get("project_id")
    return bool(owner == me or me in members or (kind, item["id"]) in shared
                or (owner and _TEAM.get(owner) == _TEAM.get(me) and _TEAM.get(me) != "admin")
                or (pid and project_ok is not None and pid in project_ok))


def _visible_projects(ctx: Ctx) -> list[dict[str, Any]]:
    shared = _shared(ctx, ("project",))
    return [p for p in _run(store.projects) if _can_see(ctx, "project", p, shared)]


def _visible(ctx: Ctx, kind: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shared = _shared(ctx, (kind,))
    ok = {p["id"] for p in _visible_projects(ctx)}
    return [i for i in items if _can_see(ctx, kind, i, shared, ok)]


def _guard(ctx: Ctx, kind: str, item: dict[str, Any]) -> None:
    shared = _shared(ctx, (kind,))
    ok = {p["id"] for p in _visible_projects(ctx)}
    if not _can_see(ctx, kind, item, shared, ok):
        raise HTTPException(403, "This is not shared with you.")


def _writer(ctx: Ctx = Depends(require_ctx)) -> Ctx:
    if ctx.viewing_as is not None:
        raise HTTPException(403, f"Read only while viewing as {ctx.viewing_as['name']}.")
    return ctx


# ------------------------------------------------------------------ models


class ItemIn(BaseModel):
    """Something from another screen being added to an investigation or a report."""
    title: str = Field(max_length=200)
    body: str = Field(default="", max_length=store.MAX_TEXT)
    href: str = Field(default="", max_length=500)
    label: str = Field(default="", max_length=200)
    type: str = Field(default="link", max_length=40)


class NewInvestigationIn(BaseModel):
    title: str = Field(max_length=200)
    summary: str = Field(default="", max_length=store.MAX_TEXT)


class NewDocumentIn(BaseModel):
    title: str = Field(max_length=200)
    kind: str = "Report"


class ReplyLink(BaseModel):
    label: str = Field(default="", max_length=200)
    href: str = Field(max_length=500)
    type: str = Field(default="link", max_length=40)


class StatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=2000)


class ProjectIn(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=store.MAX_TEXT)
    period: str = Field(default="", max_length=20)
    members: list[str] = Field(default_factory=list)
    due_at: str | None = None
    instructions: str = Field(default="", max_length=store.MAX_TEXT)
    domains: list[str] | None = None


class TaskIn(BaseModel):
    title: str = Field(max_length=200)
    detail: str = Field(default="", max_length=store.MAX_TEXT)
    assignee_id: str | None = None
    href: str = Field(default="", max_length=500)
    link_label: str = Field(default="", max_length=120)


class TaskStatusIn(BaseModel):
    status: str


class NoteIn(BaseModel):
    body: str = Field(max_length=store.MAX_TEXT)
    mentions: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- reads


@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    info = store.ensure()
    with store.db() as con:
        counts = store.table_counts(con)
    return {"status": "ok", "service": "core", "port": paths.API_PORT, "store": info["store"],
            "seed_version": store.seed_version(), "counts": counts,
            "books": {"ews": paths.EWS_CORP, "cockpit": paths.CORP_BOOK}}


@app.get(PREFIX + "/summary")
def summary(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    counts = {"projects": len(_visible_projects(ctx)),
              "investigations": len(_visible(ctx, "investigation", _run(store.investigations))),
              "analyses": len(_visible(ctx, "analysis", _run(store.analyses))),
              "documents": len(_visible(ctx, "document", _run(store.documents)))}
    return _run(store.summary, ctx.username, counts)


@app.get(PREFIX + "/inbox")
def inbox(kind: str = Query(""), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return _run(store.inbox, ctx.username, kind)


@app.post(PREFIX + "/inbox/{item_id}/read")
def inbox_read(item_id: str, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    return _run(store.inbox_read, ctx.username, item_id)


# ---------------------------------------------------------------- projects


@app.get(PREFIX + "/projects")
def projects(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"projects": _visible_projects(ctx)}


@app.get(PREFIX + "/projects/{project_id}")
def project(project_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    out = _run(store.project, project_id)
    _guard(ctx, "project", out)
    return out


@app.post(PREFIX + "/projects", status_code=201)
def create_project(payload: ProjectIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    out = _run(store.create_project, ctx.username, payload.name, payload.description, payload.period,
               payload.members, payload.due_at)
    # A new project may use the Cockpit books, Early Warning and What-If unless its access rules say otherwise.
    return _run(store.update_project, ctx.username, out["id"], instructions=payload.instructions,
                domains=payload.domains if payload.domains is not None else ["corporate", "retail", "ews", "whatif"])


@app.post(PREFIX + "/projects/{project_id}/tasks", status_code=201)
def add_task(project_id: str, payload: TaskIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "project", _run(store.project, project_id))
    return _run(store.add_project_task, ctx.username, project_id, payload.title, payload.detail,
                payload.assignee_id, payload.href, payload.link_label)


@app.post(PREFIX + "/projects/{project_id}/tasks/{task_id}/status")
def task_status(project_id: str, task_id: int, payload: TaskStatusIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "project", _run(store.project, project_id))
    return _run(store.task_status, ctx.username, project_id, task_id, payload.status)


# ---------------------------------------------------------- investigations


@app.get(PREFIX + "/investigations")
def investigations(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"investigations": _visible(ctx, "investigation", _run(store.investigations)),
            "statuses": list(store.INVESTIGATION_STATUSES)}


@app.get(PREFIX + "/investigations/{inv_id}")
def investigation(inv_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    out = _run(store.investigation, inv_id)
    _guard(ctx, "investigation", out)
    return out


@app.post(PREFIX + "/investigations/{inv_id}/notes", status_code=201)
def add_note(inv_id: str, payload: NoteIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "investigation", _run(store.investigation, inv_id))
    return _run(store.add_note, ctx.username, inv_id, payload.body, payload.mentions)


@app.post(PREFIX + "/investigations", status_code=201)
def create_investigation(payload: NewInvestigationIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    return _run(store.create_investigation, ctx.username, payload.title, payload.summary)


@app.post(PREFIX + "/investigations/{inv_id}/items", status_code=201)
def add_investigation_item(inv_id: str, payload: ItemIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "investigation", _run(store.investigation, inv_id))
    return _run(store.add_to_investigation, ctx.username, inv_id, payload.title, payload.body, payload.href,
                payload.label, payload.type)


@app.post(PREFIX + "/investigations/{inv_id}/status")
def investigation_status(inv_id: str, payload: StatusIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "investigation", _run(store.investigation, inv_id))
    return _run(store.investigation_status, ctx.username, inv_id, payload.status, payload.note)


# ------------------------------------------------------ analyses, documents


@app.get(PREFIX + "/analyses")
def analyses(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    # R10 Q2: each analysis reads as the answer to its question (title = question, headline first).
    return {"analyses": [answer_first.view(a) for a in _visible(ctx, "analysis", _run(store.analyses))]}


@app.get(PREFIX + "/analyses/{analysis_id}")
def analysis(analysis_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    out = _run(store.analysis, analysis_id)
    _guard(ctx, "analysis", out)
    return answer_first.view(out)


@app.get(PREFIX + "/documents")
def documents(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"documents": _visible(ctx, "document", _run(store.documents))}


@app.post(PREFIX + "/documents", status_code=201)
def create_document(payload: NewDocumentIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    return _run(store.create_document, ctx.username, payload.title, payload.kind)


@app.post(PREFIX + "/documents/{doc_id}/sections", status_code=201)
def add_document_section(doc_id: str, payload: ItemIn, ctx: Ctx = Depends(_writer)) -> dict[str, Any]:
    _guard(ctx, "document", _run(store.document, doc_id))
    return _run(store.add_to_document, ctx.username, doc_id, payload.title, payload.body, payload.href, payload.label,
                payload.type)


@app.get(PREFIX + "/documents/{doc_id}")
def document(doc_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    out = _run(store.document, doc_id)
    _guard(ctx, "document", out)
    return out


# ------------------------------------------------------------------ home (PLAN_R3 S3-4)


@app.get(PREFIX + "/home")
def home(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """Everything waiting on the signed-in user, for My workspace (backend/workspace_v5/home.py)."""
    from backend.workspace_v5 import home as home_mod
    user = ctx.user
    lists = (_visible_projects(ctx), _visible(ctx, "investigation", _run(store.investigations)),
             _visible(ctx, "analysis", _run(store.analyses)), _visible(ctx, "document", _run(store.documents)))
    with store.db() as con:
        out = home_mod.build(con, ctx.username, dict(user or {}), *lists)
    out["reviews"] = home_mod.reviews(ctx.token, ctx.username)
    return out


# S3-2: analyses (save, refresh), investigations (import, continue), projects (scope, documents, threads).
from backend.workspace_v5.api_r3 import router as _r3_router  # noqa: E402

app.include_router(_r3_router, prefix=PREFIX)
# The process trace of a project thread turn (PLAN_R5 G4, docs/v5/THREAD_API.md 2.2).
from backend.convo import trace as _trace  # noqa: E402
_trace.install(app, PREFIX)
