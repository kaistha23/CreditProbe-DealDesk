"""CreditProbe Mail routes, mounted on the Core service. See docs/v5/MAIL_API.md."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field

from backend.identity_v5 import store as ids
from backend.identity_v5.api import Ctx, require_admin, require_ctx, run
from backend.mail_v5 import store

router = APIRouter(prefix="/api/v1/mail")


def writer(ctx: Ctx = Depends(require_ctx)) -> Ctx:
    """The signed-in user may write as themselves; a view-as session is read only."""
    if ctx.viewing_as is not None:
        raise HTTPException(403, f"Read only while viewing as {ctx.viewing_as['name']}. Stop viewing as to act.")
    return ctx


def mailbox_ctx(request: Request, mailbox: str = Query(""), ctx: Ctx = Depends(require_ctx)) -> tuple[str, bool]:
    """(username whose mailbox is read, whether that is somebody else's). Only the Administrator may name one."""
    if mailbox and mailbox != ctx.username:
        if not ctx.is_admin:
            raise HTTPException(403, "Only the Administrator can read another mailbox.")
        run(ids.get_user, mailbox)
        return mailbox, True
    return ctx.username, False


class AttachmentIn(BaseModel):
    kind: str
    file_id: str | None = None
    object: dict[str, Any] | None = None


class SendIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = Field(default="", max_length=300)
    body_html: str = Field(default="", max_length=store.MAX_BODY)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    mode: str = "new"
    thread_id: str | None = None
    in_reply_to: str | None = None
    draft_id: str | None = None


class ShareIn(BaseModel):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=8000)
    objects: list[dict[str, Any]]
    subject: str = Field(default="", max_length=300)


class DraftIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = Field(default="", max_length=300)
    body_html: str = Field(default="", max_length=store.MAX_BODY)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    mode: str = "new"
    thread_id: str | None = None
    in_reply_to: str | None = None


class BulkIn(BaseModel):
    thread_ids: list[str] = Field(default_factory=list, max_length=200)
    action: str
    label: str = Field(default="", max_length=40)


class ReadIn(BaseModel):
    read: bool = True


class FlagIn(BaseModel):
    value: bool = True


class LabelsIn(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class LabelIn(BaseModel):
    name: str = Field(max_length=40)
    color: str = "#6366f1"


def _atts(items: list[AttachmentIn]) -> list[dict[str, Any]]:
    return [a.model_dump() for a in items]


def _idem(ctx: Ctx, key: str | None, produce, response: Response) -> dict[str, Any]:
    if not key:
        return produce()
    with ids.db() as con:
        hit = con.execute("SELECT response FROM mail_idem WHERE key=? AND username=?",
                          (key[:80], ctx.username)).fetchone()
    if hit:
        response.status_code = 200
        return {**json.loads(hit["response"]), "replayed": True}
    out = produce()
    with ids.db() as con:
        con.execute("INSERT OR IGNORE INTO mail_idem(key, username, response) VALUES(?,?,?)",
                    (key[:80], ctx.username, json.dumps(out)))
    return out


# ------------------------------------------------------------------ reads


@router.get("/counts")
def counts(box: tuple[str, bool] = Depends(mailbox_ctx)) -> dict[str, Any]:
    return run(store.counts, box[0])


@router.get("/folders")
def folders(box: tuple[str, bool] = Depends(mailbox_ctx)) -> dict[str, Any]:
    return {"folders": list(store.FOLDERS), "labels": run(store.list_labels, box[0]), "counts": run(store.counts, box[0])}


@router.get("/threads")
def threads(folder: str = Query("inbox"), q: str = Query(""), unread: bool = Query(False),
            label: str = Query(""), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
            from_: str = Query("", alias="from", max_length=80), to: str = Query("", max_length=80),
            has_attachment: bool = Query(False), date_from: str = Query("", max_length=10),
            date_to: str = Query("", max_length=10),
            ctx: Ctx = Depends(require_ctx), box: tuple[str, bool] = Depends(mailbox_ctx)) -> dict[str, Any]:
    out = run(store.thread_list, box[0], folder, q, unread, label, limit, offset, from_, to, has_attachment,
              date_from, date_to)
    return {**out, "mailbox": box[0]}


@router.get("/threads/{thread_id}")
def thread(thread_id: str, ctx: Ctx = Depends(require_ctx),
           box: tuple[str, bool] = Depends(mailbox_ctx)) -> dict[str, Any]:
    out = run(store.thread_detail, thread_id, box[0])
    if box[1]:
        with ids.db() as con:
            ids.audit(con, ctx.actor, box[0], "admin_read", thread_id, {"subject": out["subject"]})
    return {**out, "mailbox": box[0]}


@router.get("/labels")
def labels(box: tuple[str, bool] = Depends(mailbox_ctx)) -> dict[str, Any]:
    return {"labels": run(store.list_labels, box[0])}


@router.get("/notifications")
def notifications(unread: bool = Query(False), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return run(store.notifications, ctx.username, unread)


@router.get("/files/{file_id}")
def get_file(file_id: str, ctx: Ctx = Depends(require_ctx)) -> Response:
    f, data = run(store.file_for, file_id, ctx.username, ctx.is_admin)
    safe = f["content_type"] if f["content_type"].split("/")[0] in ("image", "application", "text") and \
        "html" not in f["content_type"] and "svg" not in f["content_type"] else "application/octet-stream"
    name = f["name"].replace('"', "")
    return Response(content=data, media_type=safe,
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "X-Content-Type-Options": "nosniff"})


@router.get("/shared-with-me")
def shared_with_me(type: list[str] = Query(default=[]), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return run(store.shared_with_me, ctx.username, type)


# ----------------------------------------------------------------- writes


@router.post("/send", status_code=201)
def send(payload: SendIn, response: Response, ctx: Ctx = Depends(writer),
         idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
    def produce() -> dict[str, Any]:
        with ids.db() as con:
            out = store.send(con, ctx.username, payload.to, payload.cc, payload.subject, payload.body_html,
                             _atts(payload.attachments), payload.mode, payload.thread_id, payload.in_reply_to,
                             payload.draft_id, bcc=payload.bcc)
            ids.audit(con, ctx.actor, ctx.username, "send", out["thread_id"],
                      {"to": payload.to, "cc": payload.cc, "bcc": payload.bcc, "mode": payload.mode})
            return out
    try:
        return _idem(ctx, idempotency_key, produce, response)
    except ids.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except ids.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ids.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/share", status_code=201)
def share(payload: ShareIn, response: Response, ctx: Ctx = Depends(writer),
          idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
    def produce() -> dict[str, Any]:
        with ids.db() as con:
            return store.share(con, ctx.username, payload.to, payload.cc, payload.note, payload.objects,
                               payload.subject)
    try:
        return _idem(ctx, idempotency_key, produce, response)
    except ids.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except ids.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ids.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/drafts", status_code=201)
def create_draft(payload: DraftIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    data = payload.model_dump()
    data["attachments"] = _atts(payload.attachments)
    out = run(store.save_draft, ctx.username, data, None)
    with ids.db() as con:
        ids.audit(con, ctx.actor, ctx.username, "draft_save", out["draft_id"])
    return out


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: str, payload: DraftIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    data = payload.model_dump()
    data["attachments"] = _atts(payload.attachments)
    return run(store.save_draft, ctx.username, data, draft_id)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return run(store.get_draft, ctx.username, draft_id)


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: str, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.delete_draft, ctx.username, draft_id)


@router.post("/threads/{thread_id}/read")
def read(thread_id: str, payload: ReadIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.mark_read, thread_id, ctx.username, payload.read)


@router.post("/threads/{thread_id}/star")
def star(thread_id: str, payload: FlagIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.set_flag, thread_id, ctx.username, "starred", payload.value)


@router.post("/threads/{thread_id}/archive")
def archive(thread_id: str, payload: FlagIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.set_flag, thread_id, ctx.username, "archived", payload.value)


@router.post("/threads/{thread_id}/labels")
def thread_labels(thread_id: str, payload: LabelsIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.set_labels, thread_id, ctx.username, payload.add, payload.remove)


@router.post("/bulk")
def bulk(payload: BulkIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    """Archive, move to Inbox, mark read or unread, star, label or move to a label: many conversations at once."""
    out = run(store.bulk, ctx.username, payload.thread_ids, payload.action, payload.label)
    with ids.db() as con:
        ids.audit(con, ctx.actor, ctx.username, "bulk", ",".join(out["thread_ids"])[:500],
                  {"action": payload.action, "label": payload.label, "count": out["updated"]})
    return out


@router.post("/labels", status_code=201)
def make_label(payload: LabelIn, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.create_label, ctx.username, payload.name, payload.color)


@router.delete("/labels/{name}")
def remove_label(name: str, ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.delete_label, ctx.username, name)


@router.post("/notifications/read")
def notifications_read(id: int | None = Query(None), ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    return run(store.notifications_read, ctx.username, id)


@router.post("/files", status_code=201)
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(writer)) -> dict[str, Any]:
    data = await file.read(store.MAX_FILE + 1)
    if len(data) > store.MAX_FILE:
        raise HTTPException(413, "Files can be up to 25 MB.")
    out = run(store.save_file, ctx.username, file.filename or "file", file.content_type or "", data)
    with ids.db() as con:
        ids.audit(con, ctx.actor, ctx.username, "file_upload", out["file_id"], {"name": out["name"], "size": out["size"]})
    return out


# ------------------------------------------------------------------ admin


@router.get("/admin/mailboxes")
def mailboxes(ctx: Ctx = Depends(require_admin)) -> dict[str, Any]:
    return run(store.admin_mailboxes)


@router.get("/audit")
def audit(actor: str = Query(""), action: str = Query(""), limit: int = Query(100, ge=1, le=500),
          offset: int = Query(0, ge=0), ctx: Ctx = Depends(require_admin)) -> dict[str, Any]:
    return run(ids.audit_list, actor, action, limit, offset)
