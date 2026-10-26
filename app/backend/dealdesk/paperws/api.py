"""Rounds W and T: the paper workspace API (prefix /api/v1/dealdesk), included in backend/dealdesk/api.py (# Round W/T).

    POST /paper-workspaces                         {kind, proposal_id?, ref?, structure?, paper?, source?, fresh?} -> open (or reopen) a workspace
    GET  /paper-workspaces?proposal_id=&kind=&mine=  workspaces, newest first (Recent work, the deal's Papers, the Workspace)
    GET  /paper-workspaces/{ws}?version=           the document (a version), versions, the thread, pending marks, rules applied
    POST /paper-workspaces/{ws}/instruct           {text, focus?} -> one section edited (marked), a structure change, or a reply
    POST /paper-workspaces/{ws}/versions/{n}/accept
    POST /paper-workspaces/{ws}/versions/{n}/undo
    POST /paper-workspaces/{ws}/final              {version?, final?: true} the committee copy
    GET  /paper-workspaces/{ws}/versions           the version list (no papers)
    GET  /paper-workspaces/{ws}/provenance?version=   Round T: every section and point with its evidence
    GET  /paper-workspaces/{ws}/export.docx|.pdf?version=current|final|<n>   Word / PDF with the provenance annex
    GET  /proposals/{pid}/papers/provenance        the provenance of the deal's bank-form proposal as written now (no workspace)
    GET  /business-requests/{rid}/provenance       R16's figure trace, point by point (extends /business-requests/{rid}/trace)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import Response

from backend.dealdesk.paperws import provenance as PV
from backend.dealdesk.paperws import service as S
from backend.dealdesk.paperws import sources as SRC

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-paper-workspace"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5 import client
        u = client.current_user(request) or {}
        return {"username": u.get("username") or "", "name": u.get("name") or u.get("username") or ""}
    except Exception:  # noqa: BLE001
        return {}


def _label(request: Request) -> str:
    try:
        from backend.house_style import generated_by
        return generated_by(request) or ""
    except Exception:  # noqa: BLE001
        return ""


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except S.WsError as e:
        raise HTTPException(e.status, str(e)) from None


@router.post("/paper-workspaces")
def ws_open(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    kind = str(body.get("kind") or "proposal")
    return _run(S.open_workspace, kind, proposal_id=body.get("proposal_id"), ref=body.get("ref"), structure=body.get("structure"),
                paper=body.get("paper"), source=body.get("source"), fresh=bool(body.get("fresh")), user=_user(request))


@router.get("/paper-workspaces")
def ws_list(request: Request, proposal_id: str | None = Query(None), kind: str | None = Query(None), mine: bool = Query(False),
            limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    owner = _user(request).get("username") if mine else None
    return {"workspaces": S.listing(proposal_id=proposal_id, kind=kind, owner=owner or None, limit=limit)}


@router.get("/paper-workspaces/{ws_id}")
def ws_get(ws_id: str, version: int | None = Query(None)) -> dict[str, Any]:
    return _run(S.state, ws_id, version)


@router.post("/paper-workspaces/{ws_id}/instruct")
def ws_instruct(ws_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _run(S.instruct, ws_id, str(body.get("text") or ""), focus=body.get("focus") or None, user=_user(request))


@router.post("/paper-workspaces/{ws_id}/versions/{n}/accept")
def ws_accept(ws_id: str, n: int, request: Request) -> dict[str, Any]:
    return _run(S.accept, ws_id, n, _user(request))


@router.post("/paper-workspaces/{ws_id}/versions/{n}/undo")
def ws_undo(ws_id: str, n: int, request: Request) -> dict[str, Any]:
    return _run(S.undo, ws_id, n, _user(request))


@router.post("/paper-workspaces/{ws_id}/final")
def ws_final(ws_id: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _run(S.mark_final, ws_id, body.get("version"), _user(request), final=body.get("final", True) is not False)


@router.get("/paper-workspaces/{ws_id}/versions")
def ws_versions(ws_id: str) -> dict[str, Any]:
    st = _run(S.state, ws_id)
    return {"ws_id": ws_id, "versions": st["versions"], "final_version": st["workspace"]["final_version"]}


@router.get("/paper-workspaces/{ws_id}/provenance")
def ws_provenance(ws_id: str, version: str | None = Query(None)) -> dict[str, Any]:
    return _run(S.provenance, ws_id, version)


@router.get("/paper-workspaces/{ws_id}/export.docx")
def ws_docx(ws_id: str, request: Request, version: str | None = Query(None)) -> Response:
    data, name = _run(S.export, ws_id, "docx", version, _label(request))
    return Response(content=data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/paper-workspaces/{ws_id}/export.pdf")
def ws_pdf(ws_id: str, request: Request, version: str | None = Query(None)) -> Response:
    data, name = _run(S.export, ws_id, "pdf", version, _label(request))
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/proposals/{pid}/papers/provenance")
def proposal_provenance(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    try:
        p = SRC.proposal(pid, structure)
    except SRC.SourceError as e:
        raise HTTPException(404, str(e)) from None
    return PV.build(p)


@router.get("/business-requests/{rid}/provenance")
def request_provenance(rid: str) -> dict[str, Any]:
    try:
        p = SRC.request(rid)
    except SRC.SourceError as e:
        raise HTTPException(404, str(e)) from None
    return PV.build(p)
