"""R12 Session T: "Try it on your documents" and the stress calibration API (prefix /api/v1/dealdesk).
One include_router line in the `# R12 routers` block of backend/dealdesk/api.py.

    GET    /try-docs                                       notice, modes, OCR and model availability, steps, fallback case
    POST   /try-docs/sessions          multipart: proposal (required), policy (optional), mode (deterministic | model)
    POST   /try-docs/sessions/fallback {which?, mode?}     the prepared fictional case (twin + Session O's policy)
    GET    /try-docs/sessions/{sid}                        the session: every step with status, seconds and result
    POST   /try-docs/sessions/{sid}/steps/{step}           run one step (policy, extract, review, counter, draft)
    POST   /try-docs/sessions/{sid}/run                    run every remaining step
    POST   /try-docs/sessions/{sid}/approve-policy         the demo policy becomes a P6 proposal (maker-checker)
    GET    /try-docs/sessions/{sid}/draft.docx             the draft in Word (Arabic right-to-left)
    GET    /try-docs/sessions/{sid}/paper.docx             the committee paper (R11 sheet) in Word
    DELETE /try-docs/sessions/{sid}                        exit: wipe every file and row of the session
    POST   /try-docs/sessions/{sid}/wipe                   the same (for navigator.sendBeacon on page close)
    GET    /stress/calibration                             the calibrated sensitivities (calibrated v1) and the model card
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk.try_docs import reader as R
from backend.dealdesk.try_docs import session as S

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-try-docs"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - works without the Core service
        return ""


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (S.SessionError, R.ReadError) as e:
        msg = str(e)
        raise HTTPException(404 if msg.startswith("No such") else 400, msg) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


async def _read(f: UploadFile | None) -> tuple[str, bytes] | None:
    if f is None or not f.filename:
        return None
    data = await f.read()
    if len(data) > R.MAX_BYTES:
        raise HTTPException(413, f"{f.filename} is larger than 25 MB.")
    return f.filename, data


@router.get("/try-docs")
def overview() -> dict[str, Any]:
    return S.capabilities()


@router.post("/try-docs/sessions")
async def start(request: Request, proposal: UploadFile = File(...), policy: UploadFile | None = File(None),
                mode: str = Form("deterministic")) -> dict[str, Any]:
    p = await _read(proposal)
    if p is None:
        raise HTTPException(400, "Upload a proposal.")
    q = await _read(policy)
    return _call(S.start, p, q, mode=mode, by=_user(request))


@router.post("/try-docs/sessions/fallback")
def start_fallback(request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    from backend.dealdesk.try_docs import rehearse
    body = body or {}
    p, q = rehearse.fallback_bytes(str(body.get("which") or "twin_b"))
    return _call(S.start, p, q, mode=str(body.get("mode") or "deterministic"), by=_user(request))


@router.get("/try-docs/sessions/{sid}")
def session(sid: str) -> dict[str, Any]:
    return _call(S.get_view, sid)


@router.post("/try-docs/sessions/{sid}/steps/{step}")
def step(sid: str, step: str) -> dict[str, Any]:
    return _call(S.run_step, sid, step)


@router.post("/try-docs/sessions/{sid}/run")
def run_all(sid: str) -> dict[str, Any]:
    return _call(S.run_all, sid)


@router.post("/try-docs/sessions/{sid}/approve-policy")
def approve_policy(sid: str, request: Request) -> dict[str, Any]:
    from backend.dealdesk.try_docs import policy as PO
    s = _call(S.get, sid)
    if "policy" not in s["documents"]:
        raise HTTPException(400, "No policy in this session.")
    name, data = _call(S._upload, sid, "policy")  # noqa: SLF001
    return _call(PO.approve, name, data, s["documents"]["policy"], _user(request) or "demo participant")


@router.get("/try-docs/sessions/{sid}/draft.docx")
def draft_docx(sid: str) -> Response:
    from backend.dealdesk.try_docs import memo
    s = _call(S.get, sid)
    res = s["steps"]["draft"].get("result")
    if not res:
        raise HTTPException(409, "Draft the memo first.")
    name = s.get("borrower_name") or "Proposal"
    title = ("مذكرة ائتمانية: " if res.get("language") == "ar" else "Credit memo: ") + name
    return Response(memo.docx(res, title), media_type=DOCX, headers={"Content-Disposition": 'attachment; filename="draft.docx"'})


@router.get("/try-docs/sessions/{sid}/paper.docx")
def paper_docx(sid: str, request: Request) -> Response:
    from backend.dealdesk import review_workspace as RW
    from backend.dealdesk.try_docs import engines
    s = _call(S.get, sid)
    if s["steps"]["counter"]["status"] != "done":
        raise HTTPException(409, "Run the counter-proposal and committee paper step first.")
    f = engines._find(engines.F_PAPER_DOCX)  # noqa: SLF001
    data = None
    if f:
        try:
            data, _ = f[1](s["deal_id"], generated_by=_user(request))
        except Exception:  # noqa: BLE001 - F's paper cannot take this deal: the R11 sheet
            data = None
    if data is None:
        data, _ = RW.sheet_docx(s["deal_id"], generated_by=_user(request))
    return Response(data, media_type=DOCX, headers={"Content-Disposition": 'attachment; filename="committee_paper.docx"'})


@router.delete("/try-docs/sessions/{sid}")
def wipe(sid: str) -> dict[str, Any]:
    return _call(S.wipe, sid)


@router.post("/try-docs/sessions/{sid}/wipe")
def wipe_post(sid: str) -> dict[str, Any]:
    return _call(S.wipe, sid)


@router.get("/stress/calibration")
def calibration() -> dict[str, Any]:
    from backend.dealdesk.calibration import sensitivity as CS
    e = CS.load()
    return {"version": e["version"], "source": e["source"], "method": e["method"], "summary": e["summary"], "rules": e["rules"],
            "sample": {k: v for k, v in e["sample"].items() if k != "drivers"}, "rows": e["rows"], "sources": e["sources"],
            "model_card": "docs/v5/R12_STRESS_CALIBRATION.md"}
