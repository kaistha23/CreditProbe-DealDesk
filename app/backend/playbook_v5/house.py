"""The house style for Playbook and Policy Docs Word documents: one adapter onto the shared export module.

PLAN_R3 section 0: every Excel and Word export uses the shared house style defined in S3-1, and S1 calls it
rather than styling files itself. This module is the only place Playbook touches styling. When the shared module
(`backend.house_style`, S3-1 on `v5/r3-work`) is importable it is used for the cover page, headings, page numbers
and table styles; until then a local equivalent with the same palette keeps the documents professional.
"""
from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

try:  # S3-1: the shared house style (backend/house_style, docs/v5/HOUSE_STYLE.md).
    from backend import house_style as _shared  # type: ignore[attr-defined]
    from backend.house_style import docx as _hd
except Exception:  # noqa: BLE001 - a branch without S3-1 keeps the local equivalent below
    _shared = None
    _hd = None

INK = "1B2430"
MUTED = "6B7684"
RULE = "D8DDE3"
ACCENT = "1F4E6B"
ACCENT_2 = "2E7D9A"
BAND = "F4F6F8"
RAG = {"green": ("E4F1E6", "1E5B2C", "Green"), "amber": ("FDF2DC", "7A5210", "Amber"),
       "red": ("FBE6E6", "8B1D1D", "Red")}


def shared_available() -> bool:
    return _shared is not None


def _rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_)


def _shade(cell, fill: str) -> None:
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc.append(shd)


def _field(paragraph, instr: str) -> None:
    run = paragraph.add_run()
    for tag, attr in (("w:fldChar", {"w:fldCharType": "begin"}), ("w:instrText", None),
                      ("w:fldChar", {"w:fldCharType": "end"})):
        el = OxmlElement(tag)
        if attr:
            for k, v in attr.items():
                el.set(qn(k), v)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        run._r.append(el)


def new_document(title: str, subtitle: str, meta: list[tuple[str, str]], *, kind: str = "Report",
                 generated_by: str = "", landscape: bool = False) -> Document:
    """A house-style document with its cover page, running header and page numbers."""
    if _shared is not None and hasattr(_shared, "word_document"):
        try:
            return _shared.word_document(title=title, subtitle=subtitle, meta=meta, kind=kind,
                                         generated_by=generated_by)
        except Exception:  # noqa: BLE001 - fall back to the local equivalent rather than fail an export
            pass
    doc = Document()
    sec = doc.sections[0]
    if landscape:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin, s.bottom_margin = Cm(2.0), Cm(2.0)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = _rgb(INK)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    for name, size, colour in (("Title", 26, ACCENT), ("Heading 1", 16, ACCENT), ("Heading 2", 13, ACCENT),
                               ("Heading 3", 11.5, INK)):
        st = styles[name]
        st.font.name = "Calibri"
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = _rgb(colour)
        st.paragraph_format.space_before = Pt(14 if name != "Title" else 0)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True
    # Cover page
    band = doc.add_paragraph()
    band.paragraph_format.space_before = Pt(90)
    r = band.add_run("CREDITPROBE")
    r.font.size, r.font.bold, r.font.color.rgb = Pt(11), True, _rgb(ACCENT_2)
    r = band.add_run(f"   ·   {kind.upper()}")
    r.font.size, r.font.color.rgb = Pt(11), _rgb(MUTED)
    t = doc.add_paragraph(style="Title")
    t.add_run(title)
    if subtitle:
        p = doc.add_paragraph()
        rr = p.add_run(subtitle)
        rr.font.size, rr.font.color.rgb = Pt(13), _rgb(MUTED)
    doc.add_paragraph()
    tbl = doc.add_table(rows=0, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    stamp = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
    for k, v in [*meta, ("Generated", f"{stamp}" + (f" by {generated_by}" if generated_by else ""))]:
        cells = tbl.add_row().cells
        cells[0].width, cells[1].width = Cm(4.5), Cm(11)
        a = cells[0].paragraphs[0].add_run(k)
        a.font.size, a.font.color.rgb, a.font.bold = Pt(9.5), _rgb(MUTED), True
        b = cells[1].paragraphs[0].add_run(v or "—")
        b.font.size = Pt(10)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(60)
    rr = p.add_run("Internal. Prepared in CreditProbe from the bank's books; every figure links back to its source.")
    rr.font.size, rr.font.italic, rr.font.color.rgb = Pt(8.5), True, _rgb(MUTED)
    p.add_run().add_break(WD_BREAK.PAGE)
    # Running header and footer with page numbers
    hdr = sec.header.paragraphs[0]
    hr = hdr.add_run(f"CreditProbe  |  {title}")
    hr.font.size, hr.font.color.rgb = Pt(8), _rgb(MUTED)
    ftr = sec.footer.paragraphs[0]
    ftr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fr = ftr.add_run("Page ")
    fr.font.size, fr.font.color.rgb = Pt(8), _rgb(MUTED)
    _field(ftr, "PAGE")
    fr = ftr.add_run(" of ")
    fr.font.size, fr.font.color.rgb = Pt(8), _rgb(MUTED)
    _field(ftr, "NUMPAGES")
    sec.different_first_page_header_footer = True
    return doc


def contents(doc: Document) -> None:
    doc.add_heading("Contents", level=1)
    p = doc.add_paragraph()
    _field(p, 'TOC \\o "1-2" \\h \\z \\u')
    note = doc.add_paragraph()
    r = note.add_run("Right-click and choose Update Field to refresh the page numbers.")
    r.font.size, r.font.italic, r.font.color.rgb = Pt(8), True, _rgb(MUTED)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def para(doc: Document, text: str) -> None:
    """A body paragraph with light markdown (**bold**, *italic*)."""
    if _hd is not None:
        _hd.para(doc, text.replace("*", "") if "**" not in text else text)
        return
    rich(doc.add_paragraph(), text)


def bullets(doc: Document, items: list[str]) -> None:
    if _hd is not None:
        _hd.bullets(doc, items)
        return
    for it in items:
        rich(doc.add_paragraph(style="List Bullet"), it)


def label(doc: Document, text: str) -> None:
    """A small bold line above a table (its title)."""
    if _hd is not None:
        _hd.para(doc, f"**{text}**", size=10)
        return
    r = doc.add_paragraph().add_run(text)
    r.bold, r.font.size = True, Pt(10)


def figure(doc: Document, png: bytes, caption_text: str = "") -> None:
    if _hd is not None:
        _hd.figure(doc, png, width_cm=16, caption=caption_text)
        return
    doc.add_picture(io.BytesIO(png), width=Cm(16))
    if caption_text:
        caption(doc, caption_text)


def rich(paragraph, text: str) -> None:
    """Light markdown: **bold** and *italic*."""
    import re

    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def table(doc: Document, header: list[str], rows: list[list[str]], *, numeric: list[bool] | None = None,
          widths: list[float] | None = None, fills: list[list[str | None]] | None = None,
          inks: list[list[str | None]] | None = None) -> None:
    """A house-style table: accent header row, banded body, numbers right-aligned."""
    if _shared is not None and hasattr(_shared, "word_table"):
        try:
            t = _shared.word_table(doc, header, rows, numeric=numeric)
            _fit(t, header, rows, widths)
            return
        except Exception:  # noqa: BLE001
            pass
    numeric = numeric or [False] * len(header)
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        _shade(c, ACCENT)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if numeric[i] else WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(h)
        r.bold, r.font.size, r.font.color.rgb = True, Pt(9), _rgb("FFFFFF")
    tr = t.rows[0]._tr.get_or_add_trPr()
    rh = OxmlElement("w:tblHeader")
    rh.set(qn("w:val"), "true")
    tr.append(rh)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            c = cells[i]
            fill = (fills[ri][i] if fills else None) or (BAND if ri % 2 else None)
            if fill:
                _shade(c, fill)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if numeric[i] else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(v)
            r.font.size = Pt(9)
            ink = inks[ri][i] if inks else None
            if ink:
                r.font.color.rgb, r.bold = _rgb(ink), True
    for row in t.rows:
        for c in row.cells:
            c.paragraphs[0].paragraph_format.space_after = Pt(1)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _fit(t, header: list[str], rows: list[list[str]], widths: list[float] | None, total_cm: float = 16.6) -> None:
    """Column widths in proportion to their longest word and text, so a name column does not break mid-word."""
    if t is None:
        return
    if not widths:
        weight = []
        for i, h in enumerate(header):
            cells = [str(r[i]) for r in rows if i < len(r)] + [str(h)]
            # A short cell ("SAR 26.8m", "In review") must not break; a long one may wrap at its words.
            longest_word = max((len(c) if len(c) <= 14 else max(len(w) for w in c.split() or [c]) for c in cells), default=4)
            longest = max((len(c) for c in cells), default=4)
            weight.append(max(longest_word, min(longest, 34) * 0.55, 3) + 2.5)  # + cell padding
        total = sum(weight)
        widths = [total_cm * w / total for w in weight]
    t.autofit = False
    # Word reads the cell widths, LibreOffice the table grid: set both, with a fixed layout.
    grid = t._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        if i < len(widths):
            gc.set(qn("w:w"), str(int(Cm(widths[i]).twips)))
    pr = t._tbl.tblPr
    layout = pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    for row in t.rows:
        for i, w in enumerate(widths):
            if i < len(row.cells):
                row.cells[i].width = Cm(w)


def caption(doc: Document, text: str) -> None:
    if _hd is not None:
        _hd.note(doc, text)
        return
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size, r.font.italic, r.font.color.rgb = Pt(8.5), True, _rgb(MUTED)


def callout(doc: Document, text: str, tone: str = "info") -> None:
    if _hd is not None:
        word = {"info": "Note", "warning": "Attention", "critical": "Critical"}.get(tone, "Note")
        _hd.para(doc, f"**{word}:** {text}")
        return
    fill = {"info": "E8F1F6", "warning": "FDF2DC", "critical": "FBE6E6"}.get(tone, "E8F1F6")
    t = doc.add_table(rows=1, cols=1)
    c = t.rows[0].cells[0]
    _shade(c, fill)
    rich(c.paragraphs[0], text)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def save(doc: Document) -> bytes:
    if _hd is not None:
        return _hd.to_bytes(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def docx_text(data: bytes) -> str:
    """All text of a .docx (body, tables, header, footer), for checks."""
    d = Document(io.BytesIO(data))
    parts: list[str] = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    for s in d.sections:
        parts.extend(p.text for p in s.header.paragraphs)
    return "\n".join(parts)


__all__: list[Any] = ["bullets", "callout", "caption", "contents", "docx_text", "figure", "label", "new_document",
                      "para", "rich", "save", "shared_available", "table"]
