"""The figure check of the paper workspace: the model (or the analyst through an instruction) writes words, never figures.

    ev = evidence(paper, extra=[17.9, 0.103])     # every figure the paper already prints (and the engine's values), as allowed forms
    bad = unknown("RAROC is 12.4%", ev)           # [12.4] -> the edit is rejected, the number is sent to the structure step instead

A figure is allowed when it is printed somewhere in the paper (any section, table or header) or is an engine / evidence value,
written at 0, 1 or 2 decimals (a ratio also x100). Years (1900-2099), references (DD-06, C1-13) and list numbers are not figures.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

NUM = re.compile(r"(?<![\w\-./])\d[\d,]*(?:\.\d+)?")
YEAR = re.compile(r"^(19|20)\d\d$")


DATE = re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}Q\d\b|\bFY\d{2,4}\b|\b\d{1,2}M\d{4}\b")


def numbers(text: str, dates: bool = True) -> list[float]:
    """The figures in a text. dates=False leaves dates out (30 Jun 2026, 2026-06-30, 2026Q2), as the provenance counts figures."""
    t = str(text or "").replace("**", "").replace("__", "")
    if not dates:
        t = DATE.sub(" ", t)
    out = []
    for m in NUM.finditer(t):
        tok = m.group(0).rstrip(",")
        if YEAR.match(tok):
            continue
        try:
            out.append(round(float(tok.replace(",", "")), 4))
        except ValueError:
            continue
    return out


def block_texts(b: dict[str, Any]) -> list[str]:
    t = b.get("t")
    if t in ("p", "h"):
        return [str(b.get("text") or "")]
    if t in ("bullets", "numbered"):
        return [str(x) for x in b.get("items") or []]
    if t == "table":
        return [" | ".join(map(str, b.get("header") or []))] + [" | ".join(map(str, r)) for r in b.get("rows") or []] + [str(b.get("source") or "")]
    if t == "kv":
        return [f"{k}: {v}" for k, v in b.get("pairs") or []]
    if t == "sign":
        return [f"{k}: {v}" for k, v in b.get("rows") or []]
    if t == "box":
        return [str(b.get("title") or "")]
    return []


def paper_texts(paper: dict[str, Any]) -> list[str]:
    out = [f"{k}: {v}" for k, v in paper.get("header_line") or []]
    for s in paper.get("sections") or []:
        out.append(str(s.get("heading") or ""))
        for b in s.get("blocks") or []:
            out += block_texts(b)
    return out


def _forms(v: float, ratio: bool = False) -> set[float]:
    out: set[float] = set()
    for x in ((v, v * 100) if ratio else (v,)):
        x = abs(x)
        out.add(round(x, 4))
        for d in (0, 1, 2):
            out.add(round(round(x, d), 4))
    return out


def evidence(paper: dict[str, Any], extra: Iterable[Any] = ()) -> set[float]:
    ok: set[float] = set()
    for t in paper_texts(paper):
        for n in numbers(t):
            ok |= _forms(n)
    for v in extra:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            ok |= _forms(float(v), ratio=abs(float(v)) <= 1.5)
    return ok


def unknown(text: str, allowed: set[float]) -> list[float]:
    """The figures in `text` that are not in the evidence (empty: the text may stand)."""
    return [n for n in numbers(text) if round(abs(n), 4) not in allowed]


def blocks_unknown(blocks: list[dict[str, Any]], allowed: set[float]) -> list[float]:
    out: list[float] = []
    for b in blocks:
        for t in block_texts(b):
            out += unknown(t, allowed)
    return list(dict.fromkeys(out))
