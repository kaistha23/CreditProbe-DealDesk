"""Word and PDF of any version of a workspace, in the bank's form, with the provenance annex (Round T).

    data, name = docx(paper, pv, meta)      # the bank-form renderer (render_bank / rm_request.render) + "Annex: Provenance"
    data, name = pdf(paper, pv, meta)       # the bank-form PDF + the annex pages (reportlab), one file

meta = {"version": 3, "final": True, "ws_id": "PW-…", "generated_by": "Anne", "versions": [...]} — the annex opens with the
version line (vN, who, when, final or draft) and the change log.
"""
from __future__ import annotations

import contextlib
import io
import re
import threading
import time
from typing import Any

from backend.dealdesk.paperws import provenance as PV

_PARTS_LOCK = threading.Lock()


def _strip(paper: dict[str, Any]) -> dict[str, Any]:
    """The paper as the renderers expect it (workspace-only keys removed)."""
    return {**paper, "sections": [{k: v for k, v in s.items() if k != "engine_blocks"} for s in paper.get("sections") or []]}


@contextlib.contextmanager
def _request_parts(paper: dict[str, Any]):
    """render_bank groups sections by the proposal's parts; a business request (or a given paper) prints under its own."""
    from backend.dealdesk.house_style.bankform import render_bank as RB
    if paper.get("doc_kind") == "proposal":
        yield
        return
    with _PARTS_LOCK:
        old = RB.PARTS
        RB.PARTS = [(p["key"], p["title"], p.get("subtitle") or "", tuple(p["sections"])) for p in paper.get("parts") or []]
        try:
            yield
        finally:
            RB.PARTS = old


def _when(at: Any) -> str:
    return time.strftime("%d %b %Y %H:%M UTC", time.gmtime(at)) if isinstance(at, (int, float)) else str(at or "")


def _version_line(meta: dict[str, Any]) -> str:
    v = meta.get("version")
    return (f"Version v{v}" + (" · FINAL (committee copy)" if meta.get("final") else " · working draft")
            + (f" · workspace {meta['ws_id']}" if meta.get("ws_id") else ""))


def _annex_docx(doc, pv: dict[str, Any], meta: dict[str, Any]) -> None:
    from docx.shared import Pt
    from backend.house_style import docx as hd
    hd.page_break(doc)
    hd.heading(doc, "Annex: Provenance", 1)
    p = doc.add_paragraph(_version_line(meta))
    p.runs[0].font.size = Pt(8.5)
    for line in pv.get("plain_words") or []:
        q = doc.add_paragraph(line)
        q.runs[0].font.size = Pt(8.5)
    vers = meta.get("versions") or []
    if vers:
        hd.heading(doc, "Versions", 2)
        tb = doc.add_table(rows=1, cols=4)
        tb.style = "Table Grid"
        for c, h in zip(tb.rows[0].cells, ("Version", "Who", "When", "Instruction or action")):
            c.text = h
        for v in vers:
            row = tb.add_row().cells
            ch = (v.get("change") or {}).get("status")
            row[0].text = f"v{v['n']}" + (" (final)" if meta.get("final_version") == v["n"] else "")
            row[1].text = str(v.get("author") or "")
            row[2].text = _when(v.get("at"))
            row[3].text = (v.get("instruction") or v.get("action") or "") + (f" [{ch}]" if ch else "")
        _small(tb)
    hd.heading(doc, "Evidence by section and point", 2)
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    for c, h in zip(tb.rows[0].cells, ("Section", "Point", "Kind", "Evidence")):
        c.text = h
    for sec, point, kind, ev in PV.annex_rows(pv):
        row = tb.add_row().cells
        row[0].text, row[1].text, row[2].text, row[3].text = sec, point, kind, ev
    _small(tb)
    un = pv["summary"].get("untraced") or []
    if un:
        hd.heading(doc, "Figures without a traced source", 2)
        for u in un:
            q = doc.add_paragraph(f"{u['section']}: {u['text']}", style="List Bullet")
            q.runs[0].font.size = Pt(8)


def _small(tb) -> None:
    from docx.shared import Pt
    for r in tb.rows:
        for c in r.cells:
            for par in c.paragraphs:
                for run in par.runs:
                    run.font.size = Pt(7.5)


def docx(paper: dict[str, Any], pv: dict[str, Any], meta: dict[str, Any]) -> tuple[bytes, str]:
    from docx import Document
    base = _strip(paper)
    if paper.get("doc_kind") == "request" and paper.get("request_id"):
        from backend.dealdesk.rm_request import render as RD
        data, name = RD.docx(base, generated_by=meta.get("generated_by") or "")
    else:
        from backend.dealdesk.house_style.bankform import render_bank as RB
        if paper.get("doc_kind") != "proposal":
            base.setdefault("form_title", "BUSINESS REQUEST")
        with _request_parts(paper):
            data, name = RB.docx(base, generated_by=meta.get("generated_by") or "")
    doc = Document(io.BytesIO(data))
    _annex_docx(doc, pv, meta)
    buf = io.BytesIO()
    doc.save(buf)
    v = meta.get("version")
    name = re.sub(r"\.docx$", f"-v{v}{'-final' if meta.get('final') else ''}.docx", name)
    return buf.getvalue(), name


def _annex_pdf(pv: dict[str, Any], meta: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=7.2, leading=8.6)
    esc = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    story = [Paragraph("Annex: Provenance", ss["Heading1"]), Paragraph(esc(_version_line(meta)), small)]
    story += [Paragraph(esc(x), small) for x in pv.get("plain_words") or []]
    vers = meta.get("versions") or []
    if vers:
        story += [Spacer(1, 6), Paragraph("Versions", ss["Heading2"])]
        rows = [["Version", "Who", "When", "Instruction or action"]] + [
            [f"v{v['n']}", esc(v.get("author") or ""), _when(v.get("at")), Paragraph(esc(v.get("instruction") or v.get("action") or ""), small)] for v in vers]
        t = Table(rows, colWidths=[1.6 * cm, 3 * cm, 3.6 * cm, 9.4 * cm], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
    story += [Spacer(1, 6), Paragraph("Evidence by section and point", ss["Heading2"])]
    rows = [["Section", "Point", "Kind", "Evidence"]] + [[Paragraph(esc(a), small), Paragraph(esc(b), small), c, Paragraph(esc(d), small)]
                                                         for a, b, c, d in PV.annex_rows(pv)]
    t = Table(rows, colWidths=[3.2 * cm, 6 * cm, 1.4 * cm, 7 * cm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                      title="Annex: Provenance").build(story)
    return buf.getvalue()


def pdf(paper: dict[str, Any], pv: dict[str, Any], meta: dict[str, Any]) -> tuple[bytes, str]:
    from pypdf import PdfReader, PdfWriter
    from backend.dealdesk.house_style.bankform import render_bank as RB
    base = _strip(paper)
    if paper.get("doc_kind") != "proposal":
        base.setdefault("form_title", "BUSINESS REQUEST")
        base.setdefault("proposal_id", paper.get("request_id") or paper.get("proposal_id") or "")
    with _request_parts(paper):
        data, name, _ = RB.pdf(base, generated_by=meta.get("generated_by") or "")
    w = PdfWriter()
    for src in (data, _annex_pdf(pv, meta)):
        for pg in PdfReader(io.BytesIO(src)).pages:
            w.add_page(pg)
    buf = io.BytesIO()
    w.write(buf)
    v = meta.get("version")
    if paper.get("doc_kind") == "request":
        name = name.replace("Credit-proposal", "Business-request")
    name = re.sub(r"\.pdf$", f"-v{v}{'-final' if meta.get('final') else ''}.pdf", name)
    return buf.getvalue(), name
