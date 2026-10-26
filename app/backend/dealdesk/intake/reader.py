"""R16 i: read any uploaded customer document into text lines: Word, PDF with text, scanned PDF, photo (OCR), text.

Every reader returns the same shape, so the classifier and the extractors never care where a line came from:
    {name, kind, method, pages, lines: [str], ocr_engine, characters}
Table rows become one line with cells joined by " | " (Word tables, PDF columns, OCR boxes far apart on one line).
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from backend.dealdesk.intake import ocr

MAX_BYTES = 25 * 1024 * 1024
WORD = (".docx",)
PDF = (".pdf",)
IMAGE = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
TEXT = (".txt", ".md")
ACCEPTED = WORD + PDF + IMAGE + TEXT
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


class ReadError(ValueError):
    pass


def kind_of(name: str) -> str:
    low = name.lower()
    if low.endswith(WORD):
        return "word"
    if low.endswith(PDF):
        return "pdf"
    if low.endswith(IMAGE):
        return "image"
    if low.endswith(TEXT):
        return "text"
    return ""


def _docx_lines(data: bytes) -> list[str]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = Document(io.BytesIO(data))
    out: list[str] = []

    def walk(parent, body) -> None:
        for el in body.iterchildren():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "p":
                t = Paragraph(el, parent).text.strip()
                if t:
                    out.append(t)
            elif tag == "tbl":
                for r in Table(el, parent).rows:
                    cells: list[str] = []
                    seen: list[Any] = []
                    for c in r.cells:  # a merged cell is returned once per grid column: keep it once (by identity, not text)
                        if any(c._tc is x for x in seen):
                            continue
                        seen.append(c._tc)
                        cells.append(c.text.strip().replace("\n", " "))
                    if any(cells):
                        out.append(" | ".join(cells))
    for sec in d.sections:  # page headers carry the title on some forms
        try:
            for p in sec.header.paragraphs:
                if p.text.strip():
                    out.append(p.text.strip())
        except Exception:  # noqa: BLE001
            pass
    walk(d, d.element.body)
    return out


_CHUNK = re.compile(r"\S+(?: {1,2}\S+)*")


def _pdf_text_lines(data: bytes) -> tuple[list[str], int, list[list[tuple[int, int, str]]]]:
    """Layout text: runs of 3+ spaces separate cells (" | "); `spans` keeps each cell's character columns so a table row
    with empty cells (a debit-only transaction) still lands in the right columns."""
    import pypdf
    rd = pypdf.PdfReader(io.BytesIO(data))
    out: list[str] = []
    spans: list[list[tuple[int, int, str]]] = []
    for p in rd.pages:
        try:
            t = p.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 - older pypdf or odd fonts
            t = p.extract_text() or ""
        for ln in t.splitlines():
            if not ln.strip():
                continue
            ch = [(m.start(), m.end(), m.group(0)) for m in _CHUNK.finditer(ln)]
            out.append(" | ".join(c[2] for c in ch))
            spans.append(ch)
    return out, len(rd.pages), spans


def read(name: str, data: bytes) -> dict[str, Any]:
    """Read one file. Raises ReadError with a plain message."""
    kind = kind_of(name)
    if not kind:
        raise ReadError(f"{name}: upload Word (.docx), PDF, a photo (.jpg, .png) or a text file.")
    if not data:
        raise ReadError(f"{name} is empty.")
    if len(data) > MAX_BYTES:
        raise ReadError(f"{name} is larger than 25 MB.")
    pages, engine = 1, ""
    spans: list[list[tuple[int, int, str]]] | None = None
    if kind == "word":
        try:
            lines = _docx_lines(data)
        except Exception as e:  # noqa: BLE001
            raise ReadError(f"{name} is not a readable Word document.") from e
        method = "Word"
    elif kind == "pdf":
        try:
            lines, pages, spans = _pdf_text_lines(data)
        except Exception as e:  # noqa: BLE001
            raise ReadError(f"{name} is not a readable PDF.") from e
        method = "PDF text"
        if sum(len(re.sub(r"\W", "", x)) for x in lines) < 30 * max(pages, 1):
            try:
                lines, engine, pages = ocr.pdf_scan_lines(data)
                spans = None
            except ocr.OcrError as e:
                raise ReadError(f"{name}: {e}") from None
            method = "scanned PDF (OCR)"
    elif kind == "image":
        try:
            lines, engine = ocr.image_lines(data)
        except ocr.OcrError as e:
            raise ReadError(f"{name}: {e}") from None
        except Exception as e:  # noqa: BLE001 - not an image
            raise ReadError(f"{name} is not a readable image.") from e
        method = "photo (OCR)"
    else:
        lines = [x.strip() for x in data.decode("utf-8", errors="replace").splitlines() if x.strip()]
        method = "text"
    lines = [x.translate(_AR_DIGITS) for x in lines]
    if not any(x.strip() for x in lines):
        raise ReadError(f"{name}: no text could be read.")
    return {"name": Path(name).name, "kind": kind, "method": method, "pages": pages, "lines": lines, "ocr_engine": engine,
            "characters": sum(len(x) for x in lines), "spans": spans}
