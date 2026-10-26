"""PLAN_R11 Session P: the house-style drafting API (prefix /api/v1/dealdesk), included in backend/dealdesk/api.py.

    GET   /house-style/profile?bank=&kind=&segment=&proposal_id=   the profile, its style guide, the groups
    GET   /house-style/corpus                                       every proposal in the corpus
    POST  /house-style/corpus                                       upload a proposal (.docx/.md/.txt): the profile adds it
    POST  /house-style/rebuild                                      re-derive the profile from the corpus and every event
    GET   /house-style/held-out?proposal_id=                        the P3 held-out test
    POST  /proposals/{pid}/draft  {sections?, use_model?, bank?}    draft the proposal in the house style
    GET   /proposals/{pid}/draft                                    the latest draft for the proposal (404 if none)
    GET   /proposals/{pid}/draft/review-prose                       house-style prose keyed by Session R's "Draft from data" sections
    GET   /drafts/{did}                                             a draft
    POST  /drafts/{did}/sections/{key}/regenerate                   redraft one section
    PATCH /drafts/{did}/sections/{key}                              RM edit and/or accept; the diff feeds the profile
    GET   /drafts/{did}/score                                       style score, band and lint
    GET   /drafts/{did}/docx                                        Word export
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk.house_style import service as svc

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-house-style"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - works without the Core service
        return ""


def _nf(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except svc.NotFound as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "Not found.") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def _flag(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off", "")
    return default if v is None else bool(v)


@router.get("/house-style/profile")
def get_profile(bank: str = "", kind: str = "", segment: str = "", proposal_id: str = "") -> dict[str, Any]:
    return _nf(svc.profile_view, bank, kind, segment, proposal_id)


@router.get("/house-style/corpus")
def get_corpus() -> dict[str, Any]:
    return svc.corpus_list()


@router.post("/house-style/corpus")
async def post_corpus(file: UploadFile = File(...), bank: str = Form("house-uae"), kind: str = Form(""),
                      segment: str = Form("")) -> dict[str, Any]:
    name = file.filename or "proposal.docx"
    if not name.lower().endswith((".docx", ".md", ".txt")):
        raise HTTPException(422, "Upload a Word (.docx), Markdown (.md) or text (.txt) proposal.")
    try:
        return svc.ingest(name, await file.read(), bank, kind or None, segment or None)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except Exception as e:  # noqa: BLE001 - an unreadable file
        raise HTTPException(422, f"{name} could not be read ({type(e).__name__}).") from None


@router.post("/house-style/rebuild")
def post_rebuild() -> dict[str, Any]:
    return svc.rebuild()


@router.get("/house-style/held-out")
def get_held_out(proposal_id: str = Query("DD-05")) -> dict[str, Any]:
    return _nf(svc.held_out, proposal_id)


@router.post("/proposals/{pid}/draft")
def post_draft(pid: str, request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
    body = body if isinstance(body, dict) else {}
    return _nf(svc.create_draft, pid, body.get("sections") or None, _flag(body.get("use_model")), _user(request), body.get("bank") or None)


@router.get("/proposals/{pid}/draft")
def get_latest(pid: str) -> dict[str, Any]:
    d = svc.latest(pid)
    if d is None:
        raise HTTPException(404, f"No draft yet for {pid}.")
    return d


@router.get("/proposals/{pid}/draft/review-prose")
def get_review_prose(pid: str) -> dict[str, Any]:
    """House-style prose keyed by Session R's "Draft from data" sections (for M to wire R's button to P's drafter)."""
    return _nf(svc.prose_for_review, pid)


@router.get("/drafts/{did}")
def get_draft(did: str) -> dict[str, Any]:
    return _nf(svc.get_draft, did)


@router.post("/drafts/{did}/sections/{key}/regenerate")
def post_regenerate(did: str, key: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
    return _nf(svc.regenerate, did, key, _flag((body or {}).get("use_model")))


@router.patch("/drafts/{did}/sections/{key}")
def patch_section(did: str, key: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _nf(svc.edit_section, did, key, body, _user(request))


@router.get("/drafts/{did}/score")
def get_score(did: str) -> dict[str, Any]:
    return _nf(svc.score, did)


@router.get("/drafts/{did}/docx")
def get_docx(did: str, request: Request) -> Response:
    from urllib.parse import quote
    data, name = _nf(svc.docx, did, _user(request))
    ascii_name = name.encode("ascii", "ignore").decode() or "Draft-proposal.docx"
    if not ascii_name.endswith(".docx"):
        ascii_name = "Draft-proposal.docx"
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})
