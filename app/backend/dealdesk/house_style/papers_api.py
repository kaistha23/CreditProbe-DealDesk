"""PLAN_R12 Session F: the papers API (prefix /api/v1/dealdesk), included in backend/dealdesk/api.py (# R12 routers).

    GET  /papers/registry                                the section registry: 20 anatomy + CreditProbe sections, voice, data contract
    GET  /proposals/{pid}/papers                         what can be written for the deal: bank-form proposal, committee paper, summary memo
    GET  /proposals/{pid}/bank-form?polish=              the bank-form credit proposal (sections, coverage, voice, gaps)
    GET  /proposals/{pid}/bank-form.docx|.pdf|.md        the proposal in Word / PDF / Markdown
    GET  /proposals/{pid}/committee-paper                the committee paper (2-page decision summary + full paper in committee order)
    GET  /proposals/{pid}/committee-paper.docx|.pdf      the committee paper in Word / PDF
    GET  /proposals/{pid}/papers/figures                 every figure the papers print, traced to relation, row and column

The "Summary memo" is the R11 house-style draft, unchanged: POST/GET /proposals/{pid}/draft and GET /drafts/{did}/docx.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from backend.dealdesk.house_style.bankform import ctx, paper as bf, registry, render, render_bank

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-papers"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(request: Request) -> str:
    try:
        from backend.house_style import generated_by
        return generated_by(request)
    except Exception:  # noqa: BLE001
        return ""


def _structure(structure: str | None) -> Any:
    """?structure= ask | recommended | counter:<id> | a key of the structure set | a JSON terms object."""
    if not structure:
        return None
    if structure.strip().startswith("{"):
        import json
        try:
            return json.loads(structure)
        except ValueError:
            raise HTTPException(422, "structure: not valid JSON terms") from None
    return structure


def _paper(pid: str, order: str = "proposal", polish: bool = False, structure: str | None = None, request: Request | None = None) -> dict[str, Any]:
    try:
        p = bf.write(pid, order=order, polish_text=polish, structure=_structure(structure))
    except ctx.NotFound as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    from backend.dealdesk.rules import hook as rules_hook  # Round K: the analyst's, their team's and the bank's rules
    return rules_hook.on_paper(p, rules_hook.username(request), "proposal")


def _cp(pid: str, polish: bool = False) -> dict[str, Any]:
    from backend.dealdesk import committee_paper as C
    try:
        return C.build(pid, polish_text=polish)
    except ctx.NotFound as e:
        raise HTTPException(404, str(e).strip("'\"")) from None


def _file(data: bytes, name: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/papers/registry")
def papers_registry() -> dict[str, Any]:
    return {"sections": registry.contract(), "proposal_order": registry.PROPOSAL_ORDER, "committee_order": registry.COMMITTEE_ORDER,
            "anatomy": "docs/v5/house_style/PROPOSAL_ANATOMY.md"}


@router.get("/proposals/{pid}/papers")
def papers_menu(pid: str) -> dict[str, Any]:
    p = _paper(pid)
    base = f"{PREFIX}/proposals/{pid}"
    return {"proposal_id": pid, "customer": p["customer"], "as_of": p["as_of_label"],
            "bank_form": {"label": "Credit proposal (bank form)", "voice": "business (action requested) and credit (comments, recommendation)",
                          "json": f"{base}/bank-form", "docx": f"{base}/bank-form.docx", "pdf": f"{base}/bank-form.pdf",
                          "sections": len(p["sections"]), "coverage": p["coverage"], "voice_problems": len(p["voice"]), "gaps": p["gaps"]},
            "committee_paper": {"label": "Committee paper", "json": f"{base}/committee-paper", "docx": f"{base}/committee-paper.docx",
                                "pdf": f"{base}/committee-paper.pdf"},
            "summary_memo": {"label": "Summary memo", "create": f"{base}/draft", "latest": f"{base}/draft",
                             "docx": f"{PREFIX}/drafts/{{draft_id}}/docx", "note": "The R11 short memo in the house style, unchanged."}}


@router.get("/proposals/{pid}/bank-form")
def bank_form(pid: str, request: Request, polish: bool = Query(False), structure: str | None = Query(None)) -> dict[str, Any]:
    return _paper(pid, polish=polish, structure=structure, request=request)


@router.get("/proposals/{pid}/bank-form.docx")
def bank_form_docx(pid: str, request: Request, polish: bool = Query(False), structure: str | None = Query(None),
                   layout: str = Query("bank", pattern="^(bank|classic)$")) -> Response:
    p = _paper(pid, polish=polish, structure=structure, request=request)
    data, name = render_bank.docx(p, generated_by=_user(request)) if layout == "bank" else render.docx(p, kind="Credit proposal", generated_by=_user(request))
    return _file(data, name, DOCX)


@router.get("/proposals/{pid}/bank-form.pdf")
def bank_form_pdf(pid: str, request: Request, polish: bool = Query(False), structure: str | None = Query(None),
                  layout: str = Query("bank", pattern="^(bank|classic)$")) -> Response:
    p = _paper(pid, polish=polish, structure=structure, request=request)
    if layout == "classic":
        data, name = render.pdf(p, kind="Credit proposal", generated_by=_user(request))
    else:
        data, name, _ = render_bank.pdf(p, generated_by=_user(request))
    return _file(data, name, "application/pdf")


@router.post("/proposals/{pid}/credit-proposal")
@router.get("/proposals/{pid}/credit-proposal")
def credit_proposal(pid: str, request: Request, structure: str | None = Query(None)) -> dict[str, Any]:
    """R14 K26 "Prepare the credit proposal": the bank-form proposal on the selected structure (or ?structure=), with the page
    map of the Word/PDF layout (the on-screen preview paginates by it), the parts (two voices) and the download links."""
    p = _paper(pid, structure=structure, request=request)
    pm = render_bank.page_map(p)
    q = f"?structure={structure}" if structure else ""
    base = f"{PREFIX}/proposals/{pid}"
    parts = [{"key": x["key"], "title": x["title"], "subtitle": x["subtitle"], "sections": [s["key"] for s in x["sections"]]} for x in render_bank.parts(p)]
    return {**p, "pages": pm, "parts": parts, "links": {"docx": f"{base}/bank-form.docx{q}", "pdf": f"{base}/bank-form.pdf{q}", "json": f"{base}/bank-form{q}"},
            "plain_words": plain_words(p, pm)}


def plain_words(p: dict[str, Any], pm: dict[str, Any]) -> list[str]:
    f = p.get("feed") or {}
    st = (f.get("structure") or {}).get("label") or "the ask"
    n_gap = len(p.get("gaps") or [])
    lines = [f"This is the credit proposal in the bank's own form: 20 sections plus CreditProbe's analysis, {pm.get('total')} pages.",
             f"It is written on the {st} structure" + (f": RAROC {f['raroc'] * 100:.1f}% against {f['hurdle'] * 100:.1f}%, approval by {f.get('approval')}." if f.get("raroc") is not None and f.get("hurdle") else "."),
             (f"{n_gap} section(s) say plainly what information was not provided; every figure names its Data Domains source." if n_gap
              else "Every section is filled from the deal file; every figure names its Data Domains source."),
             "Download the Word file to edit, or the PDF for committee."]
    return lines


@router.get("/proposals/{pid}/bank-form.md")
def bank_form_md(pid: str) -> Response:
    return Response(content=render.markdown(_paper(pid)), media_type="text/markdown")


@router.get("/proposals/{pid}/committee-paper")
def committee_paper(pid: str, polish: bool = Query(False)) -> dict[str, Any]:
    cp = _cp(pid, polish)
    return {**cp, "paper": cp["paper"]}


@router.get("/proposals/{pid}/committee-paper.docx")
def committee_paper_docx(pid: str, request: Request) -> Response:
    from backend.dealdesk import committee_paper as C
    data, name = C.docx(pid, generated_by=_user(request), cp=_cp(pid))
    return _file(data, name, DOCX)


@router.get("/proposals/{pid}/committee-paper.pdf")
def committee_paper_pdf(pid: str, request: Request) -> Response:
    from backend.dealdesk import committee_paper as C
    data, name = C.pdf(pid, generated_by=_user(request), cp=_cp(pid))
    return _file(data, name, "application/pdf")


@router.get("/proposals/{pid}/papers/figures")
def papers_figures(pid: str) -> dict[str, Any]:
    from backend.dealdesk import committee_paper as C
    try:
        return C.lineage_figures(pid)
    except ctx.NotFound as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
