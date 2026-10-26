"""Every figure in an answer must come from this run's evidence.

The Cockpit binds each numeric claim to a stored artifact cell or to arithmetic
over cells it recomputes (`finalization.py`, frozen). The fork applies the same
rule to free prose: every number in the answer is matched against the run's
evidence -- query results, tool outputs, the knowledge notes the assistant read,
and the question itself -- directly, at a display scale (x100, /1000, ...), or as
arithmetic over cells the server recomputes (column totals and means, shares of a
column total, differences and changes between two cells of one row or one column).
A number that matches nothing is unverified: the assistant is told which ones and
corrects once; whatever is still unverified after that is removed with its
sentence before the answer is published.
"""
from __future__ import annotations

import bisect
import math
import re
from typing import Any, Iterable

NUM = re.compile(r"(?<![\w.\-/])([-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+−]?\d+(?:\.\d+)?)(?!\d)")
SCALES = (1.0, 100.0, 0.01, 1e-3, 1e3, 1e-6, 1e-9, 1e4, 1e-4)
MAX_CANDIDATES = 400_000


def numbers(text: str) -> list[tuple[str, float, int]]:
    """(token, value, decimals) for every number in `text` that is a figure (not part of an ID such as CB01312
    or a period such as 2026Q2)."""
    out = []
    for m in NUM.finditer(text or ""):
        tok = m.group(1)
        end = m.end(1)
        nxt = text[end:end + 1]
        if nxt.isalpha() and nxt.upper() in "QMHW" and re.match(r"[QMHW]\d", text[end:end + 2] or ""):
            continue                                              # 2026Q2, 2025M08
        try:
            v = float(tok.replace(",", "").replace("−", "-"))
        except ValueError:
            continue
        dec = len(tok.split(".")[1]) if "." in tok else 0
        out.append((tok, v, dec))
    return out


def _walk(x: Any, out: list[float]) -> None:
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        if not (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            out.append(float(x))
    elif isinstance(x, str):
        out.extend(v for _, v, _ in numbers(x))
    elif isinstance(x, dict):
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk(v, out)


def _derived(rows: list[dict[str, Any]], out: list[float]) -> None:
    if not rows:
        return
    cols = [c for c in rows[0] if all(isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool)
                                      for r in rows if r.get(c) is not None)]
    out.append(float(len(rows)))
    for c in cols:
        vals = [float(r[c]) for r in rows if r.get(c) is not None]
        if not vals:
            continue
        tot = sum(vals)
        out += [tot, tot / len(vals), max(vals), min(vals)]
        if tot:
            out += [v / tot * 100 for v in vals]
            if len(vals) <= 60:
                # cumulative shares (top-n concentration)
                acc = 0.0
                for v in sorted(vals, reverse=True):
                    acc += v
                    out.append(acc / tot * 100)
                    out.append(acc)
        if len(vals) <= 40:
            for i, a in enumerate(vals):
                for b in vals[i + 1:]:
                    out += [a - b, b - a]
                    if b:
                        out.append((a / b - 1) * 100)
                        out.append(a / b)
                    if a:
                        out.append((b / a - 1) * 100)
                        out.append(b / a)
    for r in rows[:300]:
        vals = [float(r[c]) for c in cols if r.get(c) is not None]
        for i, a in enumerate(vals):
            for b in vals[i + 1:]:
                out += [a - b, b - a, a + b]
                if b:
                    out += [(a / b - 1) * 100, a / b * 100, a / b]
                if a:
                    out += [(b / a - 1) * 100, b / a * 100, b / a]


class Evidence:
    def __init__(self):
        self.values: list[float] = []
        self._sorted: list[float] | None = None

    def add(self, x: Any) -> None:
        _walk(x, self.values)
        self._sorted = None

    def add_rows(self, rows: list[dict[str, Any]] | None) -> None:
        if rows:
            _walk(rows, self.values)
            _derived(rows, self.values)
            self._sorted = None

    def _index(self) -> list[float]:
        if self._sorted is None:
            cands = set()
            for v in self.values[: MAX_CANDIDATES // len(SCALES)]:
                for s in SCALES:
                    c = round(v * s, 9)
                    cands.add(c)
                    cands.add(abs(c))
            self._sorted = sorted(cands)
        return self._sorted

    def supports(self, value: float, decimals: int) -> bool:
        if decimals == 0 and float(value).is_integer() and (abs(value) <= 12 or 1990 <= value <= 2040):
            return True                                           # counts, stage numbers, years
        idx = self._index()
        tol = max(0.5 * 10 ** (-decimals), 0.005 * abs(value))
        for v in (value, abs(value)):
            i = bisect.bisect_left(idx, v - tol)
            if i < len(idx) and idx[i] <= v + tol:
                return True
        return False

    def unverified(self, text: str) -> list[str]:
        bad = []
        for tok, v, dec in numbers(text):
            if not self.supports(v, dec):
                bad.append(tok)
        return bad


def strip_unverified(markdown: str, bad: Iterable[str]) -> str:
    """Remove each sentence (or table row / bullet) that carries an unverified figure."""
    bad = set(bad)
    if not bad:
        return markdown
    out_lines = []
    for line in markdown.split("\n"):
        if not any(re.search(rf"(?<![\w.]){re.escape(b)}(?![\d])", line) for b in bad):
            out_lines.append(line)
            continue
        if line.lstrip().startswith(("|", "-", "*")) and not line.lstrip().startswith("**"):
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        keep = [p for p in parts if not any(re.search(rf"(?<![\w.]){re.escape(b)}(?![\d])", p) for b in bad)]
        if keep:
            out_lines.append(" ".join(keep))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
