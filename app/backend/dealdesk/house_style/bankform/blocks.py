"""The content model of a paper: sections made of blocks, rendered alike to Word and PDF.

Blocks:
  {"t": "p", "text": str}                                   a paragraph (**bold** runs; "exempt": True for form lines)
  {"t": "bullets", "items": [str]}                          bullet list
  {"t": "numbered", "items": [str]}                         numbered list (recommendation, T&Cs)
  {"t": "table", "header": [...], "rows": [[...]], "source": str, "widths": [cm] | None, "size": pt}
  {"t": "kv", "pairs": [(label, value)], "cols": 2|3}        the header block (form)
  {"t": "sign", "rows": [(role, name/blank)]}                signature boxes
  {"t": "box", "title": str, "lines": int}                   a blank box signed by hand (CRO comments, committee instructions)
  {"t": "h", "text": str}                                   a sub-heading inside a section
"""
from __future__ import annotations

from typing import Any


def P(text: str, exempt: bool = False) -> dict[str, Any]:
    return {"t": "p", "text": text, "exempt": exempt}


def BL(items: list[str]) -> dict[str, Any]:
    return {"t": "bullets", "items": [i for i in items if i]}


def NL(items: list[str]) -> dict[str, Any]:
    return {"t": "numbered", "items": [i for i in items if i]}


def T(header: list[str], rows: list[list[Any]], source: str = "", widths: list[float] | None = None, size: float = 7.5) -> dict[str, Any]:
    return {"t": "table", "header": header, "rows": [["" if c is None else c for c in r] for r in rows], "source": source,
            "widths": widths, "size": size}


def KV(pairs: list[tuple[str, Any]], cols: int = 2) -> dict[str, Any]:
    return {"t": "kv", "pairs": [(k, "" if v is None else str(v)) for k, v in pairs], "cols": cols}


def H(text: str) -> dict[str, Any]:
    return {"t": "h", "text": text}


def SIGN(rows: list[tuple[str, str]]) -> dict[str, Any]:
    return {"t": "sign", "rows": rows}


def BOX(title: str, lines: int = 4) -> dict[str, Any]:
    return {"t": "box", "title": title, "lines": lines}
