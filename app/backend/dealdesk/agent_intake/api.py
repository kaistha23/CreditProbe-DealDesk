"""Round A: the agentic intake API (prefix /api/v1/dealdesk/agent-intake). One include_router line in backend/dealdesk/api.py.

    GET  /agent-intake                         the model in use, the checklists and the weights, the sample pack's manifest
    GET  /agent-intake/sample                  the Saqr Al Wadi sample deal: ask, notes, the 16 files
    GET  /agent-intake/sample/files/{name}     one sample file (the UI loads them into the drop)
    POST /agent-intake/runs                    multipart files[] (+ ask, notes, rm, market, parent_run_id, sync) -> the run (202: it works in the background)
    GET  /agent-intake/runs?proposal_id=       recent runs
    GET  /agent-intake/runs/{run_id}           the run: steps with timings, documents with both readings, the check, the draft (streamed text while writing)
    POST /agent-intake/runs/{run_id}/revise    {instruction} -> the model revises the draft (a new version)
    POST /agent-intake/runs/{run_id}/attach    {proposal_id} -> the deal opened or created from this file
    GET  /agent-intake/runs/{run_id}/calls     the run's model calls (telemetry rows tagged with the run id)
    GET  /agent-intake/runs/{run_id}.docx      the business request in Word (R16's bank-form layout)
    GET  /agent-intake/runs/{run_id}.md        the business request as markdown
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from backend.dealdesk.agent_intake import checklist as CK
from backend.dealdesk.agent_intake import export as EX
from backend.dealdesk.agent_intake import model as M
from backend.dealdesk.agent_intake import sample as SA
from backend.dealdesk.agent_intake import service as S
from backend.dealdesk.agent_intake import store as ST

PREFIX = "/api/v1/dealdesk/agent-intake"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-agent-intake"])
MAX_BYTES = 60 * 1024 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _get(rid: str) -> dict[str, Any]:
    try:
        return ST.get(rid)
    except ST.NotFound:
        raise HTTPException(404, f"No agent run {rid}.") from None


@router.get("")
def overview() -> dict[str, Any]:
    try:
        sample = SA.manifest()
    except Exception:  # noqa: BLE001
        sample = None
    return {"model": M.available(), "checklists": {k: [{"id": i, "label": lab} for i, lab in v] for k, v in CK.CHECK.items()},
            "content": CK.CONTENT, "accepted": list(S.RD.ACCEPTED) + [".zip"], "sample": sample, "recent": ST.listing(8)}


@router.get("/sample")
def sample() -> dict[str, Any]:
    return SA.manifest()


@router.get("/sample/files/{name}")
def sample_file(name: str) -> Response:
    names = {d["name"] for d in SA.texts()["documents"]}
    if name not in names or not (SA.DIR / name).exists():
        raise HTTPException(404, f"No sample file {name}.")
    import mimetypes
    return Response((SA.DIR / name).read_bytes(), media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/runs")
async def create_run(request: Request, files: list[UploadFile] | None = File(None), ask: str = Form(""), notes: str = Form(""),
                     rm: str = Form(""), market: str = Form(""), parent_run_id: str = Form(""), sync: str = Form("")) -> JSONResponse:
    got: list[tuple[str, bytes]] = []
    total = 0
    for f in files or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        total += len(data)
        if total > MAX_BYTES:
            raise HTTPException(413, "The pack is larger than 60 MB: upload it in two runs.")
        got.append((f.filename, data))
    try:
        run = S.start(got, ask, notes, rm=rm, by=_user(request), market=market, parent_run_id=parent_run_id, sync=sync in ("1", "true"))
    except ST.NotFound:
        raise HTTPException(404, f"No agent run {parent_run_id}.") from None
    except S.AgentError as e:
        raise HTTPException(400, str(e)) from None
    return JSONResponse(S.public(run), status_code=200 if run["status"] in ("done", "failed") else 202)


@router.get("/runs")
def runs(proposal_id: str = Query("")) -> dict[str, Any]:
    return {"runs": ST.listing(30, proposal_id)}


@router.get("/runs/{rid}.docx")
def run_docx(rid: str, request: Request) -> Response:
    run = _get(rid)
    if not (run.get("draft") or {}).get("md"):
        raise HTTPException(409, "The draft is not ready yet.")
    data, name = EX.docx(run, generated_by=_user(request) or run.get("rm") or "")
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/runs/{rid}.md")
def run_md(rid: str) -> PlainTextResponse:
    run = _get(rid)
    return PlainTextResponse((run.get("draft") or {}).get("md") or "", media_type="text/markdown")


@router.get("/runs/{rid}")
def run_get(rid: str) -> dict[str, Any]:
    return S.public(_get(rid))


@router.get("/runs/{rid}/calls")
def run_calls(rid: str) -> dict[str, Any]:
    run = _get(rid)
    try:
        from backend.convo import telemetry
        rows = telemetry.rows({"run_id": rid}, limit=500)
    except Exception:  # noqa: BLE001
        rows = []
    return {"run_id": rid, "calls": run.get("model_calls") or [], "telemetry": rows}


@router.post("/runs/{rid}/revise")
def run_revise(rid: str, request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    _get(rid)
    try:
        run = S.revise(rid, str(body.get("instruction") or ""), by=_user(request), sync=bool(body.get("sync")))
    except S.AgentError as e:
        raise HTTPException(409, str(e)) from None
    return JSONResponse(S.public(run), status_code=202 if run.get("status") == "revising" else 200)


@router.post("/runs/{rid}/attach")
def run_attach(rid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _get(rid)
    try:
        return S.public(S.attach(rid, str(body.get("proposal_id") or "")))
    except S.AgentError as e:
        raise HTTPException(400, str(e)) from None
