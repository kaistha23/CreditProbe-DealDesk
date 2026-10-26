"""Text out of a project document: .docx (paragraphs and tables), .pdf (page text) and .txt/.md/.csv."""
from __future__ import annotations

import io

MAX_BYTES = 10 * 1024 * 1024
KINDS = {".docx": "Word", ".pdf": "PDF", ".txt": "Text", ".md": "Text", ".csv": "Text"}


class DocError(ValueError):
    pass


def kind_of(name: str) -> str:
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in KINDS:
        raise DocError("A project document must be a .docx, .pdf or .txt file.")
    return ext


def extract(name: str, data: bytes) -> str:
    ext = kind_of(name)
    if len(data) > MAX_BYTES:
        raise DocError("A project document can be up to 10 MB.")
    if not data:
        raise DocError("The file is empty.")
    try:
        if ext == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for t in doc.tables:
                for row in t.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
            text = "\n\n".join(parts)
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((p.extract_text() or "").strip() for p in reader.pages)
        else:
            text = data.decode("utf-8", errors="replace")
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001 - a corrupt or encrypted file
        raise DocError(f"The text could not be read from {name}: {type(e).__name__}.") from e
    return text.strip()[:200_000]
