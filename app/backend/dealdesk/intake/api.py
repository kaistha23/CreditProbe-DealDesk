"""R16 i: the customer-file API (prefix /api/v1/dealdesk/intake). One include_router line in backend/dealdesk/api.py.

    GET    /intake                                   OCR status, accepted files, the requirement catalogue, recent files
    POST   /intake/files          multipart files[] (+ as_of, proposal_id)   open a customer file from a first batch
    GET    /intake/files/{iid}                       the file view (profile, bank pull, documents, checklist, reconciliation, plain words)
    POST   /intake/files/{iid}/documents   multipart files[]   add more documents
    GET    /intake/files/{iid}/documents/{doc_id}    one document: fields read, the text read (OCR or file)
    GET    /intake/files/{iid}/documents/{doc_id}/raw   the uploaded file itself
    POST   /intake/files/{iid}/documents/{doc_id}/type  {doc_type}   correct the classification
    DELETE /intake/files/{iid}/documents/{doc_id}    remove one document
    POST   /intake/files/{iid}/attach    {proposal_id}   the deal created from this file
    GET    /intake/files/{iid}/facts                 the normalised customer file (for the business request / credit response writers)
    GET    /intake/by-deal/{proposal_id}             the file attached to a deal (404 when none)
    GET    /intake/by-deal/{proposal_id}/facts       the same, normalised
    DELETE /intake/files/{iid}                       delete the file and its rows
"""
from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk.intake import checklist as CL
from backend.dealdesk.intake import ocr
from backend.dealdesk.intake import reader as RD
from backend.dealdesk.intake import service as S
from backend.dealdesk.intake.doctypes import DOC_TYPES

PREFIX = "/api/v1/dealdesk/intake"
router = APIRouter(prefix=PREFIX, tags=["r16-intake"])
MAX_FILES = 80


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except S.IntakeError as e:
        msg = str(e)
        raise HTTPException(404 if msg.startswith("No such") else 400, msg) from None


async def _files(files: list[UploadFile] | None) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for f in files or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        if len(data) > RD.MAX_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 25 MB.")
        out.append((f.filename, data))
    if len(out) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} files at once.")
    return out


@router.get("")
def overview() -> dict[str, Any]:
    return {"ocr": ocr.status(), "accepted": list(RD.ACCEPTED), "max_mb": RD.MAX_BYTES // (1024 * 1024),
            "doc_types": [{"code": d.code, "label": d.label, "group": d.group} for d in DOC_TYPES],
            "groups": [{"key": g, "label": CL.GROUP_LABEL[g]} for g in CL.GROUP_ORDER],
            "requirements": CL.requirement_catalogue(), "recent": S.recent(),
            "plain_words": ["Drop the customer's documents here: Word, PDF or photos of the pages, many at once.",
                            "CreditProbe reads each one (photos by OCR), says what it is and reads its fields.",
                            "It ticks them off against the required list, flags missing or expired ones, and checks the numbers agree across documents.",
                            "If the customer already banks with us, it pulls their accounts, facilities, conduct and group."]}


@router.post("/files")
async def open_file(request: Request, files: list[UploadFile] = File(...), as_of: str = Form(""), proposal_id: str = Form("")) -> dict[str, Any]:
    fs = await _files(files)
    return _call(S.open_file, fs, by=_user(request), as_of=as_of or None, proposal_id=proposal_id)


@router.get("/files/{iid}")
def get_file(iid: str) -> dict[str, Any]:
    return _call(S.get, iid)


@router.post("/files/{iid}/documents")
async def add(iid: str, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    fs = await _files(files)
    return _call(S.add_files, iid, fs)


@router.get("/files/{iid}/documents/{doc_id}")
def doc(iid: str, doc_id: str) -> dict[str, Any]:
    return _call(S.document, iid, doc_id)


@router.get("/files/{iid}/documents/{doc_id}/raw")
def raw(iid: str, doc_id: str) -> Response:
    name, data = _call(S.file_bytes, iid, doc_id)
    mt = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(data, media_type=mt, headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/files/{iid}/documents/{doc_id}/type")
def set_type(iid: str, doc_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _call(S.reclassify, iid, doc_id, str(body.get("doc_type") or ""))


@router.delete("/files/{iid}/documents/{doc_id}")
def remove(iid: str, doc_id: str) -> dict[str, Any]:
    return _call(S.remove_document, iid, doc_id)


@router.post("/files/{iid}/attach")
def attach(iid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _call(S.attach, iid, str(body.get("proposal_id") or ""))


@router.get("/files/{iid}/facts")
def facts(iid: str) -> dict[str, Any]:
    return _call(S.facts, iid=iid)


@router.get("/by-deal/{proposal_id}")
def by_deal(proposal_id: str) -> dict[str, Any]:
    v = _call(S.by_deal, proposal_id)
    if v is None:
        raise HTTPException(404, f"No customer file is attached to {proposal_id}.")
    return v


@router.get("/by-deal/{proposal_id}/facts")
def by_deal_facts(proposal_id: str) -> dict[str, Any]:
    v = _call(S.facts, proposal_id=proposal_id)
    if v is None:
        raise HTTPException(404, f"No customer file is attached to {proposal_id}.")
    return v


@router.delete("/files/{iid}")
def delete(iid: str) -> dict[str, Any]:
    return _call(S.delete, iid)
