"""PLAN_R12 Session G: Parameters and policy API (prefix /api/v1/dealdesk), one include_router line in the `# R12 routers` block.

    GET   /parameters                                    every parameter with its provenance (policy clause or manual), by group
    GET   /parameters/export.xlsx                        the house-style workbook: Parameters, Risk appetite, Policy register, Change log
    GET   /parameters/changes                            the change log (every value that changed between two table versions)
    GET   /policies                                      the policy library (newest first)
    POST  /policies/upload           multipart: file     learn the policy (Session O's P6) and prepare the review; nothing changes
    POST  /policies/sample                               the same with the fictional policy (Sandstone Harbour Bank PJSC)
    GET   /policies/{pid}/{v}                            one upload: its record and the review table (found / not found / new)
    GET   /policies/{pid}/{v}/view                       the viewer: clauses by section and tables
    GET   /policies/{pid}/{v}/document.docx              Word download (a PDF/Markdown/text upload rebuilt as Word)
    GET   /policies/{pid}/{v}/original                   the file as uploaded
    POST  /policies/{pid}/{v}/approve   {decisions}      one new parameter version per changed table, with provenance
    POST  /policies/{pid}/{v}/reject    {note}           the upload marked rejected; no parameter changes
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk import params
from backend.dealdesk import policy_library as PL

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-parameters-policy"])
MAX_BYTES = 25 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME = {"docx": DOCX, "pdf": "application/pdf", "md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}


def _user(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request) or {}
    except Exception:  # noqa: BLE001 - works without the Core service
        return {}


#: roles that may approve or reject a policy (besides an Administrator): the parameter owners' side of the bank
APPROVER_WORDS = ("risk", "credit", "cro", "cfo", "finance", "treasury")


def _who(request: Request) -> tuple[str, str, dict[str, Any]]:
    """The signed-in user, from the identity service only (never from the request body)."""
    u = _user(request)
    name = u.get("name") or u.get("username") or ""
    role = "administrator" if u.get("is_admin") else str(u.get("role_label") or u.get("role") or u.get("title") or "")
    return name, role, u


def _signed_in(request: Request) -> tuple[str, str]:
    name, role, _ = _who(request)
    if not name:
        raise HTTPException(401, "Sign in to upload, approve or reject a policy.")
    return name, role


def _approver(request: Request) -> tuple[str, str]:
    name, role = _signed_in(request)
    if role != "administrator" and not any(w in role.lower() for w in APPROVER_WORDS):
        raise HTTPException(403, "Only an Administrator or a risk, credit or finance owner can approve or reject a policy.")
    return name, role


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except PL.NotFound as e:
        raise HTTPException(404, str(e.args[0])) from None
    except PL.Conflict as e:
        raise HTTPException(409, str(e)) from None
    except params.ParamError as e:
        raise HTTPException(422, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _file(name: str, data: bytes, mime: str) -> Response:
    return Response(data, media_type=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


def _generated_by(request: Request) -> str:
    from backend.house_style import generated_by
    return generated_by(request)


@router.get("/parameters")
def parameters() -> dict[str, Any]:
    rows = PL.parameter_rows()
    groups = [g for g in (PL.GROUP_PARAM, PL.GROUP_APPETITE, PL.GROUP_DOA, PL.GROUP_MARKET, PL.GROUP_EXTRA) if any(r["group"] == g for r in rows)]
    active = [p for p in PL.listing() if p["status"] == "active"]
    return {"rows": rows, "groups": groups, "version": params.version_tag(),
            "from_policy": sum(1 for r in rows if r["provenance"]["kind"] == "policy"), "total": len(rows),
            "active_policies": [{"policy_id": p["policy_id"], "version": p["version"], "title": p["title"]} for p in active]}


@router.get("/parameters/export.xlsx")
def parameters_xlsx(request: Request) -> Response:
    return _file("Deal Desk parameters.xlsx", PL.export_xlsx(_generated_by(request)), XLSX)


@router.get("/parameters/changes")
def parameter_changes() -> dict[str, Any]:
    return {"changes": PL.change_log()}


@router.get("/policies")
def policies() -> dict[str, Any]:
    return {"policies": PL.listing()}


@router.post("/policies/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(400, "Choose the policy file.")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"{file.filename} is larger than 25 MB.")
    by, _ = _signed_in(request)
    return _call(PL.upload, file.filename, data, by=by)


@router.post("/policies/sample")
def sample() -> dict[str, Any]:
    return _call(PL.upload_sample)


@router.get("/policies/{pid}/{version}")
def policy(pid: str, version: int) -> dict[str, Any]:
    return _call(PL.get, pid, version)


@router.get("/policies/{pid}/{version}/view")
def view(pid: str, version: int) -> dict[str, Any]:
    return _call(PL.viewer, pid, version)


@router.get("/policies/{pid}/{version}/document.docx")
def document(pid: str, version: int, request: Request) -> Response:
    name, data = _call(PL.document_docx, pid, version, _generated_by(request))
    return _file(name, data, DOCX)


@router.get("/policies/{pid}/{version}/original")
def original(pid: str, version: int) -> Response:
    name, data = _call(PL.original, pid, version)
    return _file(name, data, MIME.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream"))


@router.post("/policies/{pid}/{version}/approve")
def approve(pid: str, version: int, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    by, role = _approver(request)
    rec = _call(PL.approve, pid, version, body.get("decisions") or {}, by=by, role=role)
    return {"policy": rec, "parameters": parameters()}


@router.post("/policies/{pid}/{version}/reject")
def reject(pid: str, version: int, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    by, _ = _approver(request)
    return {"policy": _call(PL.reject, pid, version, by=by, note=str(body.get("note") or ""))}
