"""Round G/B: small wording helpers shared by the graph, the 360 and the paper sections."""
from __future__ import annotations

import re
from typing import Any

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def dmy(v: Any) -> str:
    """'2026-10-21' → '21 Oct 2026'; '2026Q2' stays; anything else as given."""
    s = str(v or "")
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d).*", s)
    if m:
        return f"{int(m[3])} {MONTHS[int(m[2]) - 1]} {m[1]}"
    return s


def sar(v: Any) -> str:
    """SAR units → 'SAR 14.5m'."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v or "")
    if abs(x) >= 1e6:
        return f"SAR {x / 1e6:,.1f}m"
    return f"SAR {x:,.0f}"
