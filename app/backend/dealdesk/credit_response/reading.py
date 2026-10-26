"""Read one uploaded file into text for the request parser and the document classifier.

Word: paragraphs and table rows (cells joined by " | "). PDF with text: pypdf's layout mode, so a table row stays on one
line; runs of two or more spaces become cell breaks (" | ") and a wrapped first cell is joined to its row. Scanned PDF and
photos: OCR. Session i's intake reader is used when it is merged (its OCR is the bundled pure-wheel engine); otherwise the
Deal Desk reader (system Tesseract when installed). Every result says how it was read.
"""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any

from backend.dealdesk.try_docs import reader as R

IMAGE = R.IMAGE


class ReadError(ValueError):
    pass


def _layout_lines(text: str) -> list[str]:
    out: list[str] = []
    prev_cells = 0
    for raw in text.splitlines():
        raw = raw.replace("\x7f", "•").replace("\uf0b7", "•")
        if not raw.strip():
            prev_cells = 0 if not out else prev_cells
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        cells = [c.strip() for c in re.split(r"\s{2,}", raw.strip()) if c.strip()]
        from backend.dealdesk.credit_response.request import heading_key
        if heading_key(raw.strip()) is not None or re.match(r"^\s*\d{1,2}\.\s+[A-Z]", raw):
            out.append(raw.strip())
            prev_cells = 0
            continue
        has_nums = sum(1 for c in cells if re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?\)?", c)) >= 2
        if prev_cells >= 4 and indent < 12 and out and not has_nums and len(cells) <= max(1, prev_cells // 2) and len(cells) > 1:
            first, *rest = out[-1].split(" | ")
            out[-1] = " | ".join([f"{first} {cells[0]}", *rest])
            continue
        if len(cells) == 1 and prev_cells >= 4 and indent < 12 and out and len(cells[0]) < 60 and not cells[0].endswith((".", ":")):
            # the wrapped first cell of the row above ("Project limit 1: Al Wusta Residential" / "Towers")
            first, *rest = out[-1].split(" | ")
            out[-1] = " | ".join([f"{first} {cells[0]}", *rest])
            continue
        if len(cells) >= 2 and prev_cells >= 4 and indent >= 40 and out:
            continue  # wrapped tail cells of the row above (tenor, particulars): kept on the row's own line already
        if len(cells) == 1 and prev_cells >= 4 and indent >= 40:
            continue
        out.append(" | ".join(cells) if len(cells) > 1 else cells[0])
        prev_cells = len(cells)
    return out


def _pdf(data: bytes) -> tuple[str, int, str]:
    import pypdf
    rd = pypdf.PdfReader(io.BytesIO(data))
    pages = len(rd.pages)
    plain = "\n".join((p.extract_text() or "") for p in rd.pages)
    if len(re.sub(r"\s", "", plain)) < 40 * max(pages, 1) // 4:
        return _ocr("scan.pdf", data), pages, "pdf scan (OCR)"
    try:
        lay = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in rd.pages)
        return "\n".join(_layout_lines(lay)), pages, "pdf text (layout)"
    except Exception:  # noqa: BLE001 - an older pypdf: the plain text
        return plain, pages, "pdf text"


def _ocr(name: str, data: bytes) -> str:
    """Session i's OCR (backend/dealdesk/intake/ocr.py: rapidocr, then Tesseract) when merged, else the Deal Desk reader."""
    try:
        from backend.dealdesk.intake import ocr as IO
    except Exception:  # noqa: BLE001 - i not merged
        IO = None
    if IO is not None and IO.status().get("available"):
        try:
            if name.lower().endswith(".pdf"):
                lines, _eng, _n = IO.pdf_scan_lines(data)
            else:
                lines, _eng = IO.image_lines(data)
            if lines:
                return "\n".join(lines)
        except Exception:  # noqa: BLE001 - fall back to the Deal Desk reader
            pass
    try:
        if name.lower().endswith(".pdf"):
            return R.ocr_pdf(data)
        return R.ocr_image(name, data)
    except R.ReadError as e:
        raise ReadError(str(e)) from e


def _ocr_lines(text: str) -> str:
    """OCR text: columns come as runs of spaces; the same cell rule as the PDF layout."""
    return "\n".join(_layout_lines(text))


def read(name: str, data: bytes) -> dict[str, Any]:
    low = name.lower()
    if not low.endswith(R.ACCEPTED):
        raise ReadError(f"{name}: upload a Word (.docx), PDF, photo or scan (.png, .jpg, .tif) or text file.")
    if not data:
        raise ReadError(f"{name} is empty.")
    if len(data) > R.MAX_BYTES:
        raise ReadError(f"{name} is larger than 25 MB.")
    sha = hashlib.sha256(data).hexdigest()[:16]
    pages = 1
    if low.endswith(".pdf"):
        try:
            text, pages, method = _pdf(data)
        except ReadError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ReadError(f"{name} is not a readable PDF.") from e
        if "OCR" in method:
            text = _ocr_lines(text)
    elif low.endswith(IMAGE):
        text, method = _ocr_lines(_ocr(name, data)), "image (OCR)"
    else:
        try:
            r = R.read(name, data)
        except R.ReadError as e:
            raise ReadError(str(e)) from e
        text, method = r["text"], r["method"]
    text = R.normalise_digits(text)
    if not text.strip():
        raise ReadError(f"{name}: no text could be read.")
    return {"name": name, "text": text, "method": method, "pages": pages, "sha": sha, "characters": len(text)}
