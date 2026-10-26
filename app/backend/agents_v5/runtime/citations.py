"""No uncited figure in a narrative (A1, A7).

Every sentence of a narrative that contains a figure must cite at least one step ([S3] or
[S3, S5]), and each figure must match a value in the cited steps' `figures` (allowing the
usual display transforms: percent, bps, millions, thousands, rounding to the shown decimals).
Labels that look like numbers (DD-07, Stage 2, 30+ DPD, Q3, years, article numbers, step ids)
are not figures. `enforce()` removes failing sentences and reports them.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

CITE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
LABELS = [
    r"\[S\d+(?:\s*,\s*S\d+)*\]", r"\bS\d+\b", r"\b[A-Z]{2,4}-\d+\b", r"\bStage\s*\d\b", r"\b\d+\+\s*(?:DPD|days)",
    r"\bQ[1-4]\b", r"\b(?:19|20)\d\d(?:Q[1-4])?\b", r"\bArt(?:icle)?\.?\s*\d+(?:\.\d+)*", r"\b\d+\s*(?:of|/)\s*\d+\s+steps\b",
    r"\bP\(\s*30\+", r"\btop[- ]\d+\b", r"\b\d+(?:st|nd|rd|th)\b", r"\b\d+-(?:quarter|year|month)s?\b",
    r"\bnext\s+\d+\s+quarters\b", r"\b\d+\s+quarters\b", r"#\d+",
]
NUM = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[*-])|\n+")


def _strip_labels(s: str) -> str:
    for pat in LABELS:
        s = re.sub(pat, " ", s, flags=re.I)
    return s


def numbers(sentence: str) -> list[tuple[float, int]]:
    out = []
    for m in NUM.finditer(_strip_labels(sentence)):
        tok = m.group(0).replace(",", "").replace("−", "-")
        try:
            v = float(tok)
        except ValueError:
            continue
        dec = len(tok.split(".")[1]) if "." in tok else 0
        out.append((abs(v), dec))
    return out


def _flatten(x: Any) -> Iterable[float]:
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        if math.isfinite(float(x)):
            yield float(x)
    elif isinstance(x, dict):
        for v in x.values():
            yield from _flatten(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _flatten(v)


def _matches(n: float, dec: int, values: Iterable[float]) -> bool:
    tol = 0.5 * 10 ** (-dec) + 1e-9
    for v in values:
        v = abs(v)
        for c in (v, v * 100, v * 1e4, v / 1e6, v / 1e3, v / 1e9, v / 100):
            if abs(c - n) <= tol:
                return True
    return False


def check(narrative: str, figures_by_step: dict[str, dict[str, Any]]) -> dict[str, Any]:
    bad: list[dict[str, Any]] = []
    sentences = [s for s in SENT.split(narrative or "") if s.strip()]
    for s in sentences:
        nums = numbers(s)
        if not nums:
            continue
        cited = [x.strip() for m in CITE.finditer(s) for x in m.group(1).split(",")]
        if not cited:
            bad.append({"sentence": s, "reason": "a figure with no step citation"})
            continue
        vals = [v for sid in cited for v in _flatten(figures_by_step.get(sid, {}))]
        for n, dec in nums:
            if not _matches(n, dec, vals):
                bad.append({"sentence": s, "reason": f"{n:g} is not in the figures of {', '.join(cited)}"})
                break
    return {"ok": not bad, "sentences": len(sentences), "uncited": bad}


def enforce(narrative: str, figures_by_step: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    res = check(narrative, figures_by_step)
    if res["ok"]:
        return narrative, res
    drop = {b["sentence"] for b in res["uncited"]}
    kept = []
    for line in (narrative or "").split("\n"):
        parts = [p for p in SENT.split(line) if p.strip()]
        keep = [p for p in parts if p not in drop]
        if parts and not keep:
            continue
        kept.append(" ".join(keep) if parts else line)
    res["removed"] = len(drop)
    return "\n".join(kept).strip(), res
