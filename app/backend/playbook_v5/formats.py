"""Display formats for block values (docs/v5/PLAYBOOK_API.md 3.2): the Word export and the assistant's prose."""
from __future__ import annotations

from typing import Any


def sar(v: float) -> str:
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}SAR {a / 1e9:,.2f}bn"
    if a >= 1e6:
        return f"{sign}SAR {a / 1e6:,.1f}m"
    if a >= 1e3:
        return f"{sign}SAR {a / 1e3:,.1f}k"
    return f"{sign}SAR {a:,.0f}"


def value(v: Any, fmt: str = "text") -> str:
    if v is None or v == "":
        return "—"
    if fmt in ("text", "rating", "date"):
        return str(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if fmt == "sar":
        return sar(f)
    if fmt == "pct":
        return f"{f * 100:.1f}%"
    if fmt == "bps":
        return f"{f:,.0f} bps"
    if fmt == "int":
        return f"{f:,.0f}"
    if fmt == "num4":
        return f"{f:,.4f}"
    return f"{f:,.2f}"


def delta(v: Any, fmt: str) -> str:
    if v is None:
        return ""
    s = value(abs(float(v)), fmt)
    if fmt == "pct":
        s = f"{abs(float(v)) * 100:.1f} pts"
    return ("+" if float(v) >= 0 else "−") + s


NUMERIC = {"sar", "pct", "bps", "int", "num", "num4"}
