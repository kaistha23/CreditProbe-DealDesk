"""PLAN_R6 E1: every thread answer and commentary emphasises its key figures and its conclusion.

`RULE` is the one instruction every v5 writer's prompt carries. `emphasise(text)` is the deterministic twin of
`frontend/src/lib/v5/emphasis.ts`: when a text carries no `**` at all (a deterministic writer, or a model that did not
follow the rule), the figures in its prose are put in bold. Tables, headings and code are left alone, and a text
that already carries emphasis is returned unchanged.
"""
from __future__ import annotations

import re

RULE = ("Emphasis: put the key figures and the one-line conclusion in **bold** markdown (for example "
        "'**RAROC 21.4%** clears the **15.0% hurdle**'); bold only what the reader must not miss, at least once "
        "per answer.")

_FIGURE = re.compile(
    r"(?<![\w*`])((?:SAR|USD|US\$)\s?-?\d[\d,]*(?:\.\d+)?\s?(?:bn|billion|m|mn|million|k|thousand)?"
    r"|[-+−]?\d[\d,]*(?:\.\d+)?\s?(?:%|pp|bps|x)(?![\w%])"
    r"|[-+−]?\d[\d,]*(?:\.\d+)?\s(?:basis points|percentage points|notches?|borrowers|names|accounts|facilities))"
    r"(?![\w*])")


def _line(line: str) -> str:
    if re.match(r"^\s*(\||#|```)", line):
        return line
    parts = re.split(r"(`[^`]*`)", line)
    return "".join(p if p.startswith("`") else _FIGURE.sub(r"**\1**", p) for p in parts)


def emphasise(text: str) -> str:
    s = str(text or "")
    if not s.strip() or "**" in s:
        return s
    out, fence = [], False
    for line in s.split("\n"):
        if re.match(r"^\s*```", line):
            fence = not fence
            out.append(line)
            continue
        out.append(line if fence else _line(line))
    return "\n".join(out)


def has_emphasis(text: str) -> bool:
    return bool(re.search(r"\*\*[^*]+\*\*", emphasise(text)))
