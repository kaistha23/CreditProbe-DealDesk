"""Number formatting for Lenses (PLAN_R5 G5): one rule set for every tile, table, tooltip and export.

  amounts       SAR m (1-2 decimals) or SAR bn when >= 1,000 m
  percentages   1-2 decimals with a % sign (values are stored in percent units: 12.5 means 12.5%)
  ratios        2 decimals with an x (leverage, DSCR)
  bps           integers
  counts        thousands separators

Same output as `frontend/src/lib/v5/format.ts` (Session T's shared formatter, THREAD_API.md section 3):
"SAR 1.23bn", "SAR 12.3m", "12.2%", "1.27", "44 bps", "12,345". When T's Python twin `backend/common/format.py`
lands, `fmt_value` can delegate to it; the unit names below are this module's contract.
"""
from __future__ import annotations

import math
from typing import Any

UNITS = ("sar_mn", "pct", "ratio", "bps", "count", "score", "days", "text")
UNIT_SUFFIX = {"sar_mn": "SAR m", "pct": "%", "ratio": "x", "bps": "bps", "count": "", "score": "points", "days": "days"}


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def amount(v: Any) -> str:
    f = _num(v)
    if f is None:
        return "–"
    if f == 0:
        return "SAR 0m"
    if abs(f) >= 1000:
        return f"SAR {f / 1000:,.2f}bn"
    if abs(f) >= 10:
        return f"SAR {f:,.1f}m"
    return f"SAR {f:,.2f}m"


def pct(v: Any, decimals: int = 1) -> str:
    f = _num(v)
    if f is None:
        return "–"
    d = decimals if abs(f) >= 10 else 2
    return f"{f:,.{d}f}%"


def ratio(v: Any) -> str:
    f = _num(v)
    return "–" if f is None else f"{f:,.2f}"


def bps(v: Any) -> str:
    f = _num(v)
    return "–" if f is None else f"{round(f):,} bps"


def count(v: Any) -> str:
    f = _num(v)
    return "–" if f is None else f"{round(f):,}"


def fmt_value(v: Any, unit: str) -> str:
    if unit == "sar_mn":
        return amount(v)
    if unit == "pct":
        return pct(v)
    if unit == "ratio":
        return ratio(v)
    if unit == "bps":
        return bps(v)
    if unit in ("count", "days"):
        return count(v) + (" days" if unit == "days" and _num(v) is not None else "")
    if unit == "score":
        f = _num(v)
        return "–" if f is None else f"{f:,.1f}"
    return "–" if v is None else str(v)


def round_for(v: Any, unit: str) -> Any:
    """The stored value rounded the way it is shown (no raw floats with 6 decimals in a row a user can see)."""
    f = _num(v)
    if f is None:
        return v
    if unit in ("count", "bps", "days"):
        return int(round(f))
    if unit == "sar_mn":
        return round(f, 4)          # small retail amounts keep their size ("SAR 0.03m", never "SAR 0m")
    if unit in ("pct", "ratio", "score"):
        return round(f, 2)
    return v


def axis_suffix(unit: str) -> str:
    return {"pct": "%", "ratio": "x"}.get(unit, "")


def axis_title(label: str, unit: str) -> str:
    suf = {"sar_mn": "SAR m", "bps": "bps", "pct": "%", "ratio": "x"}.get(unit, "")
    return f"{label} ({suf})" if suf and suf not in label else label


def hover(unit: str, var: str = "y") -> str:
    """A Plotly d3 hover format for the unit."""
    return {"sar_mn": f"SAR %{{{var}:,.2f}} m", "pct": f"%{{{var}:,.2f}}%", "ratio": f"%{{{var}:,.2f}}x",
            "bps": f"%{{{var}:,.0f}} bps", "count": f"%{{{var}:,.0f}}", "days": f"%{{{var}:,.0f}} days",
            "score": f"%{{{var}:,.1f}}"}.get(unit, f"%{{{var}}}")


def tickformat(unit: str) -> str:
    return {"sar_mn": ",.1f", "pct": ",.1f", "ratio": ",.2f", "bps": ",.0f", "count": ",.0f", "days": ",.0f", "score": ",.0f"}.get(unit, "")
