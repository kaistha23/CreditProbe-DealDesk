"""R16 c: credit response from an uploaded business request (prefix /api/v1/dealdesk). One include_router line in the
`# R16 routers` block of backend/dealdesk/api.py.

    GET    /credit-response                              steps, accepted files, OCR status, recent cases, the demo pack (if present)
    POST   /credit-response/cases          multipart: files (several; the business request and the documents), request_name?
    POST   /credit-response/cases/demo     {kind: docx | pdf | jpg, documents: pdf | word | images}  customer 2's pack from the repo
    GET    /credit-response/cases/{cid}                  the case: every step with status, seconds, plain words and result
    POST   /credit-response/cases/{cid}/steps/{step}     run one step (read, deal, check, review, analysis, structure, stress,
                                                         proof, recommendation, brief, response)
    POST   /credit-response/cases/{cid}/run              run every step not yet run
    GET    /credit-response/cases/{cid}/paper            the response as sections and blocks (the in-app preview)
    GET    /credit-response/cases/{cid}/response.docx    the credit division's response in the bank form, Word
    GET    /credit-response/cases/{cid}/response.pdf     the same, PDF
    GET    /credit-response/cases/{cid}/brief.docx       the feedback brief to the RM, Word
"""
from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk.credit_response import reading as RD
from backend.dealdesk.credit_response import service as SV

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-credit-response"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
V5 = pathlib.Path(__file__).resolve().parents[3]
DEMO = V5 / "data" / "dealdesk" / "demo_customers" / "c2_sawaed_al_bina"


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - works without the Core service
        return ""


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except SV.CaseError as e:
        msg = str(e)
        raise HTTPException(404 if msg.startswith("No such") else 400, msg) from None
    except RD.ReadError as e:
        raise HTTPException(400, str(e)) from None


def _file(data: bytes, name: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def demo_pack() -> dict[str, Any] | None:
    if not (DEMO / "business_request").exists():
        return None
    return {"customer": "Sawaed Al Bina Contracting Co. (fictional customer 2)",
            "request": sorted(p.name for p in (DEMO / "business_request").iterdir() if p.is_file()),
            "documents": {k: len(list((DEMO / k).glob("*.*"))) for k in ("pdf", "word", "images") if (DEMO / k).exists()}}


def demo_files(kind: str = "pdf", documents: str = "pdf") -> list[tuple[str, bytes]]:
    req = {"docx": ["business_request.docx"], "pdf": ["business_request.pdf"],
           "jpg": sorted(p.name for p in (DEMO / "business_request").glob("business_request_p*.jpg"))}.get(kind)
    if req is None or documents not in ("pdf", "word", "images"):
        raise SV.CaseError("kind is docx, pdf or jpg; documents is pdf, word or images.")
    if not (DEMO / "business_request").exists():
        raise SV.CaseError("No such demo pack in this installation.")
    files = [(n, (DEMO / "business_request" / n).read_bytes()) for n in req]
    files += [(p.name, p.read_bytes()) for p in sorted((DEMO / documents).glob("*.*"))]
    return files


@router.get("/credit-response")
def overview() -> dict[str, Any]:
    try:
        from backend.dealdesk.intake import ocr
        ocr_st = ocr.status()
    except Exception:  # noqa: BLE001
        from backend.dealdesk.try_docs import reader
        ocr_st = reader.ocr_status()
    return {"steps": [{"key": k, "label": lb} for k, lb in SV.STEPS], "accepted": list(RD.R.ACCEPTED), "ocr": ocr_st,
            "cases": SV.cases()[:12], "demo": demo_pack(),
            "plain_words": ["Upload the RM's business request (Word, PDF or photos of its pages) with the customer's documents.",
                            "CreditProbe reads the request, runs the Deal Desk flow on it and writes the RM feedback brief and the "
                            "credit division's response in the bank form (Word and PDF)."]}


@router.post("/credit-response/cases")
async def create(request: Request, files: list[UploadFile] = File(...), request_name: str | None = Form(None)) -> dict[str, Any]:
    got = []
    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        if len(data) > RD.R.MAX_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 25 MB.")
        got.append((f.filename, data))
    return _call(SV.start, got, by=_user(request), request_name=request_name or None)


@router.post("/credit-response/cases/demo")
def create_demo(request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    b = body or {}
    return _call(lambda: SV.start(demo_files(str(b.get("kind") or "pdf"), str(b.get("documents") or "pdf")), by=_user(request)))


@router.get("/credit-response/cases")
def list_cases() -> list[dict[str, Any]]:
    return SV.cases()


@router.get("/credit-response/cases/{cid}")
def get_case(cid: str) -> dict[str, Any]:
    return _call(lambda: SV.view(SV.get(cid)))


@router.post("/credit-response/cases/{cid}/steps/{step}")
def step(cid: str, step: str) -> dict[str, Any]:
    return _call(SV.step, cid, step)


@router.post("/credit-response/cases/{cid}/run")
def run(cid: str) -> dict[str, Any]:
    return _call(SV.run, cid)


@router.get("/credit-response/cases/{cid}/paper")
def paper(cid: str) -> dict[str, Any]:
    p = _call(SV.paper, cid)
    from backend.dealdesk.house_style.bankform import render_bank as RB
    from backend.dealdesk.credit_response import response as RS
    RS._register_parts()  # noqa: SLF001
    return {**{k: v for k, v in p.items() if k != "sections"}, "parts": RB.parts(p)}


@router.get("/credit-response/cases/{cid}/response.docx")
def response_docx(cid: str) -> Response:
    data, name = _call(SV.response_docx, cid)
    return _file(data, name, DOCX)


@router.get("/credit-response/cases/{cid}/response.pdf")
def response_pdf(cid: str) -> Response:
    data, name = _call(SV.response_pdf, cid)
    return _file(data, name, "application/pdf")


@router.get("/credit-response/cases/{cid}/brief.docx")
def brief_docx(cid: str) -> Response:
    data, name = _call(SV.brief_docx, cid)
    return _file(data, name, DOCX)
