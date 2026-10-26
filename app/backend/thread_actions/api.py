"""/api/v1/thread-actions (R16 t, M7), mounted on the Core service (backend/workspace_v5/api.py, port 8505).

    GET  /health
    POST /intent            {text}                                    -> {intent: null | {kind, scope, to, question, subject}}
    POST /trace             {doc, turn_index?, log?}                  -> {plain_words, sources, queries, relations, rows, counts}
    POST /memo              {doc, kind?, scope?, to?, answer_index?, trigger?, request_text?}
                                                                      -> {memo_id, title, file_name, href, plain_words, ...}
    GET  /memos/{id}.docx   the Word file (any signed-in user: a shared memo opens for the colleague it was sent to)
    GET  /memos             ?module=&thread_id=                       -> {memos: [...]}
    POST /actions           {module, thread_id, answer_id?, action, target?}   (share, report: logged in ta_action)

Every route needs a signed-in user. Deterministic writers only (no model key).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.identity_v5.api import Ctx, require_ctx

from . import doc as D
from . import intent as I
from . import memo as M
from . import store
from . import trace as T

PREFIX = "/api/v1/thread-actions"
router = APIRouter(prefix=PREFIX, tags=["thread-actions"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ACTIONS = ("share", "trace", "word", "report", "memo_intent")


class IntentIn(BaseModel):
    text: str = Field(default="", max_length=2000)


class TraceIn(BaseModel):
    doc: dict[str, Any]
    turn_index: int | None = None
    log: bool = True


class MemoIn(BaseModel):
    doc: dict[str, Any]
    kind: str = "memo"
    scope: str = "thread"
    to: str = Field(default="", max_length=120)
    answer_index: int | None = None
    trigger: str = "word_button"
    request_text: str = Field(default="", max_length=2000)


class ActionIn(BaseModel):
    module: str
    thread_id: str = Field(default="", max_length=200)
    answer_id: str = Field(default="", max_length=200)
    action: str
    target: str = Field(default="", max_length=300)


def _by(ctx: Ctx) -> str:
    u = ctx.user or {}
    name = u.get("name") or u.get("username") or ""
    return f"{name}, {u['title']}" if u.get("title") else name


def _safe(title: str) -> str:
    """A file name from a title: letters, digits, spaces and dashes; apostrophes dropped ("Today's" -> "Todays")."""
    t = str(title).replace("'", "").replace("\u2019", "")
    t = "".join(ch if ch.isalnum() or ch in " -_" else " " for ch in t)
    return " ".join(t.split())[:60].strip()


def _doc(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        return D.normalise(raw)
    except D.Invalid as e:
        raise HTTPException(422, str(e)) from e


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "thread-actions", "modules": sorted(D.MODULES)}


@router.post("/intent")
def intent(body: IntentIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"intent": I.memo_intent(body.text)}


@router.post("/trace")
def trace(body: TraceIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    doc = _doc(body.doc)
    if body.turn_index is not None and not 0 <= body.turn_index < len(doc["turns"]):
        raise HTTPException(422, "No such answer in this thread.")
    out = T.trace(doc, body.turn_index)
    if body.log:
        aid = doc["turns"][body.turn_index]["answer_id"] if body.turn_index is not None else ""
        store.log_action(doc["module"], doc["thread_id"], aid, "trace", f"{out['counts']['relations']} relations", ctx.username)
    return out


@router.post("/memo")
def memo(body: MemoIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    doc = _doc(body.doc)
    kind = body.kind if body.kind in M.KIND_LABEL else "memo"
    scope = body.scope if body.scope in ("answer", "thread") else "thread"
    trigger = body.trigger if body.trigger in ("word_button", "memo_intent") else "word_button"
    at = store.now()
    memo_id = store.new_id("TM", at, f"{doc['module']}|{doc['thread_id']}|{len(doc['turns'])}")
    by = _by(ctx)
    data = M.build(doc, kind=kind, scope=scope, to=body.to.strip(), by=by, at=at, memo_id=memo_id, answer_index=body.answer_index)
    turns = doc["turns"] if scope == "thread" else [doc["turns"][body.answer_index if body.answer_index is not None
                                                                and 0 <= body.answer_index < len(doc["turns"]) else -1]]
    tr = T.trace({**doc, "turns": turns})
    import json as _json
    row = {"module": doc["module"], "thread_id": doc["thread_id"], "scope": scope, "kind": kind, "title": doc["title"],
           "addressee": body.to.strip(), "trigger": trigger, "request_text": body.request_text[:600], "answers": len(turns),
           "tables": tr["counts"]["tables"], "sources": tr["counts"]["sources"],
           "relations_named": _json.dumps([r["relation"] for r in tr["relations"]]), "created_by": ctx.username,
           "created_at": store.stamp(at)}
    row = store.save_memo(memo_id, data, row, doc)
    store.log_action(doc["module"], doc["thread_id"], "" if scope == "thread" else turns[0]["answer_id"],
                     "memo_intent" if trigger == "memo_intent" else "word", memo_id, ctx.username)
    label = M.KIND_LABEL[kind]
    safe = _safe(doc["title"]) or doc["module_label"]
    return {"memo_id": memo_id, "kind": kind, "scope": scope, "title": doc["title"], "addressee": row["addressee"],
            "file_name": f"{label} - {safe}.docx", "href": f"{PREFIX}/memos/{memo_id}.docx", "bytes": row["file_bytes"],
            "answers": len(turns), "tables": row["tables"], "sources": row["sources"], "recorded": row["recorded"],
            "plain_words": M.plain_words(doc, turns), "module_label": doc["module_label"]}


@router.get("/memos/{memo_id}.docx")
def memo_docx(memo_id: str, ctx: Ctx = Depends(require_ctx)) -> Response:
    p = store.memo_file(memo_id)
    if p is None:
        raise HTTPException(404, "No such memo.")
    row = store.memo_row(memo_id) or {}
    label = M.KIND_LABEL.get(row.get("kind", "memo"), "Memo")
    title = _safe(row.get("title", memo_id))
    return Response(p.read_bytes(), media_type=DOCX,
                    headers={"Content-Disposition": f'attachment; filename="{label} - {title or memo_id}.docx"'})


@router.get("/memos")
def memo_list(module: str = Query(default="", max_length=40), thread_id: str = Query(default="", max_length=200),
              ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"memos": store.memos(module, thread_id)}


@router.post("/actions")
def action(body: ActionIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    if body.module not in D.MODULES:
        raise HTTPException(422, f"Unknown module '{body.module}'.")
    if body.action not in ACTIONS:
        raise HTTPException(422, f"Unknown action '{body.action}'.")
    return store.log_action(body.module, body.thread_id, body.answer_id, body.action, body.target, ctx.username)
