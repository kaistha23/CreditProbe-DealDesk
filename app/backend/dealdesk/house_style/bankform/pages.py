"""Page counts of a rendered paper (tests and the STATUS page counts; never at runtime): Word through LibreOffice when it is
installed, PDF through pypdf."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile

from backend.dealdesk.house_style.bankform.render import pdf_pages


def soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def docx_pages(data: bytes) -> int | None:
    exe = soffice()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        src = pathlib.Path(d) / "paper.docx"
        src.write_bytes(data)
        subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", d, str(src)], check=False, capture_output=True, timeout=180)
        out = pathlib.Path(d) / "paper.pdf"
        return pdf_pages(out.read_bytes()) if out.exists() else None
