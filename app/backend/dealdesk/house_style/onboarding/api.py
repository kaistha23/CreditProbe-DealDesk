"""PLAN_R11 P6: "Learn from documents" API (prefix /api/v1/dealdesk), one include_router line in backend/dealdesk/api.py.

    GET   /onboarding                                         the latest session, the accepted versions, the demo documents
    POST  /onboarding/learn          multipart: policy (required), memos (0..n), doa, appetite
    POST  /onboarding/demo                                    learn from the fictional policy, the demo committee memos and the house's memos
    GET   /onboarding/sessions/{sid}                          a session: every learned item, conflicts, gaps, committee questions
    GET   /onboarding/sessions/{sid}/proposed/{name}          proposed_rules / _params / _checks / _conflicts / _committee / _structure
    POST  /onboarding/sessions/{sid}/items/{iid}/decision     {action: accept|edit|reject, value?, note?}: maker-checker
    GET   /onboarding/versions                                accepted versions
    GET   /onboarding/versions/{vid}                          a version: rule book, parameter tables, committee questions
    POST  /onboarding/draft-review   {proposal_id, version?}  draft with the committee questions answered, then review (timed)
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile

from backend.dealdesk.house_style.onboarding import service as svc

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-onboarding"])
PROPOSED = ("rules", "params", "checks", "conflicts", "committee", "structure")
MAX_BYTES = 25 * 1024 * 1024


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - works without the Core service
        return ""


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except svc.NotFound as e:
        raise HTTPException(404, str(e.args[0])) from None
    except svc.Conflict as e:
        raise HTTPException(409, str(e)) from None
    except KeyError as e:
        raise HTTPException(404, f"Not found: {e.args[0]}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


async def _read(f: UploadFile | None) -> tuple[str, bytes] | None:
    if f is None or not f.filename:
        return None
    data = await f.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"{f.filename} is larger than 25 MB.")
    if not f.filename.lower().endswith((".docx", ".pdf", ".md", ".txt")):
        raise HTTPException(400, f"{f.filename}: upload .docx, .pdf, .md or .txt.")
    return f.filename, data


@router.get("/onboarding")
def overview() -> dict[str, Any]:
    return svc.overview()


@router.post("/onboarding/learn")
async def learn(request: Request, policy: UploadFile = File(...), memos: list[UploadFile] | None = File(None),
                doa: UploadFile | None = File(None), appetite: UploadFile | None = File(None)) -> dict[str, Any]:
    pol = await _read(policy)
    if pol is None:
        raise HTTPException(400, "Upload the bank's credit policy.")
    ms = [m for m in [await _read(x) for x in (memos or [])] if m]
    return _call(svc.learn, pol, ms, doa=await _read(doa), appetite=await _read(appetite), by=_user(request))


@router.post("/onboarding/demo")
def demo(request: Request) -> dict[str, Any]:
    # the demo documents are supplied by the demo, not uploaded by this user: the maker is the demo, so the user can check
    return _call(svc.learn_demo, by="maker (demo documents)")


@router.get("/onboarding/sessions/{sid}")
def session(sid: str) -> dict[str, Any]:
    return _call(svc.get, sid)


@router.get("/onboarding/sessions/{sid}/proposed/{name}")
def proposed(sid: str, name: str) -> Any:
    if name not in PROPOSED:
        raise HTTPException(404, f"No proposed_{name}.json.")
    _call(svc.get, sid)
    f = svc.root() / "sessions" / sid / f"proposed_{name}.json"
    return json.loads(f.read_text())


@router.post("/onboarding/sessions/{sid}/items/{iid}/decision")
def decision(sid: str, iid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _call(svc.decide, sid, iid, str(body.get("action", "")), by=_user(request) or str(body.get("by") or ""),
                 value=body.get("value"), note=str(body.get("note") or ""))


@router.get("/onboarding/versions")
def versions() -> dict[str, Any]:
    return {"versions": svc.versions()}


@router.get("/onboarding/versions/{vid}")
def version(vid: str) -> dict[str, Any]:
    return _call(svc.version, vid)


@router.post("/onboarding/draft-review")
def draft_review(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    pid = str(body.get("proposal_id") or "")
    if not pid:
        raise HTTPException(400, "proposal_id is required.")
    return _call(svc.draft_review, pid, body.get("version") or None, by=_user(request))
