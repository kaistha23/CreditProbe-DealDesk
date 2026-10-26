"""Read an uploaded document into text, whatever it is: Word, a PDF with text, a scanned PDF or an image (OCR), text.

OCR uses the system Tesseract and Poppler (`tesseract`, `pdftoppm`) when they are installed; no Python package is
added (N3). Without them a scan is refused with a plain message and the prepared fallback case is offered.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_BYTES = 25 * 1024 * 1024
WORD = (".docx",)
PDF = (".pdf",)
IMAGE = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
TEXT = (".txt", ".md")
ACCEPTED = WORD + PDF + IMAGE + TEXT

_AR = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LAT = re.compile(r"[A-Za-z]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


class ReadError(ValueError):
    pass


def ocr_status() -> dict[str, Any]:
    tess = shutil.which("tesseract")
    langs: list[str] = []
    if tess:
        try:
            out = subprocess.run([tess, "--list-langs"], capture_output=True, text=True, timeout=10).stdout
            langs = [x.strip() for x in out.splitlines()[1:] if x.strip()]
        except Exception:  # noqa: BLE001 - tesseract present but not answering: treat as absent
            langs = []
    return {"available": bool(tess) and "eng" in langs, "pdf_pages": bool(shutil.which("pdftoppm")), "languages": langs,
            "arabic": "ara" in langs}


def language(text: str) -> str:
    """'ar' when Arabic letters outnumber Latin ones, else 'en'."""
    a, latin = len(_AR.findall(text)), len(_LAT.findall(text))
    return "ar" if a > latin else "en"


def normalise_digits(text: str) -> str:
    return text.translate(_AR_DIGITS)


def _docx(data: bytes) -> tuple[str, list[list[list[str]]]]:
    from docx import Document
    d = Document(io.BytesIO(data))
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    lines: list[str] = []
    tables: list[list[list[str]]] = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = Paragraph(el, d).text.strip()
            if t:
                lines.append(t)
        elif tag == "tbl":
            rows = [[c.text.strip() for c in r.cells] for r in Table(el, d).rows]
            tables.append(rows)
            lines.extend(" | ".join(r) for r in rows)
    return "\n".join(lines), tables


def _ocr_one(p: Path, langs: str) -> str:
    # one thread per Tesseract process: the pages run side by side instead of fighting over the cores
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    r = subprocess.run(["tesseract", str(p), "stdout", "-l", langs, "--psm", "3"], capture_output=True, text=True, timeout=180, env=env)
    return r.stdout


def _ocr_images(paths: list[Path], langs: str) -> str:
    from concurrent.futures import ThreadPoolExecutor
    workers = max(1, min(len(paths), os.cpu_count() or 2))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return "\n".join(ex.map(lambda p: _ocr_one(p, langs), paths))


def _ocr_langs(st: dict[str, Any]) -> str:
    return "eng+ara" if st["arabic"] else "eng"


def ocr_pdf(data: bytes) -> str:
    st = ocr_status()
    if not (st["available"] and st["pdf_pages"]):
        raise ReadError("This PDF is a scan (no text layer) and OCR is not installed on this laptop (Tesseract and Poppler). "
                        "Use a Word or text PDF, or run the prepared fallback case.")
    with tempfile.TemporaryDirectory(prefix="try-ocr-") as td:
        src = Path(td) / "in.pdf"
        src.write_bytes(data)
        import pypdf
        n = len(pypdf.PdfReader(io.BytesIO(data)).pages)
        dpi = "300" if n <= 3 else "200"  # 200 dpi reads a typed page as well and is about four times faster
        subprocess.run(["pdftoppm", "-r", dpi, "-png", str(src), str(Path(td) / "p")], check=True, capture_output=True, timeout=180)
        pages = sorted(Path(td).glob("p*.png"))
        return _ocr_images(pages, _ocr_langs(st))


def ocr_image(name: str, data: bytes) -> str:
    st = ocr_status()
    if not st["available"]:
        raise ReadError("This is an image (a scan) and OCR is not installed on this laptop (Tesseract). "
                        "Use a Word or text PDF, or run the prepared fallback case.")
    with tempfile.TemporaryDirectory(prefix="try-ocr-") as td:
        p = Path(td) / ("in" + Path(name).suffix.lower())
        p.write_bytes(data)
        return _ocr_images([p], _ocr_langs(st))


def read(name: str, data: bytes) -> dict[str, Any]:
    """{text, tables, method, pages, language, characters}. Raises ReadError with a plain message."""
    low = name.lower()
    if not low.endswith(ACCEPTED):
        raise ReadError(f"{name}: upload a Word (.docx), PDF, scanned image (.png, .jpg, .tif) or text file.")
    if len(data) > MAX_BYTES:
        raise ReadError(f"{name} is larger than 25 MB.")
    if not data:
        raise ReadError(f"{name} is empty.")
    tables: list[list[list[str]]] = []
    pages = 1
    if low.endswith(WORD):
        try:
            text, tables = _docx(data)
        except Exception as e:  # noqa: BLE001 - any unreadable file
            raise ReadError(f"{name} is not a readable Word document.") from e
        method = "word"
    elif low.endswith(PDF):
        import pypdf
        try:
            rd = pypdf.PdfReader(io.BytesIO(data))
            pages = len(rd.pages)
            text = "\n".join((p.extract_text() or "") for p in rd.pages)
        except Exception as e:  # noqa: BLE001
            raise ReadError(f"{name} is not a readable PDF.") from e
        method = "pdf text"
        if len(re.sub(r"\s", "", text)) < 40 * max(pages, 1) // 4:
            text = ocr_pdf(data)
            method = "pdf scan (OCR)"
    elif low.endswith(IMAGE):
        text = ocr_image(name, data)
        method = "image scan (OCR)"
    else:
        text = data.decode("utf-8", errors="replace")
        method = "text"
    text = normalise_digits(text)
    if not text.strip():
        raise ReadError(f"{name}: no text could be read.")
    return {"name": name, "text": text, "tables": tables, "method": method, "pages": pages, "language": language(text),
            "characters": len(text)}
