"""Deal Desk number formatting (PLAN_R5 G5) for the Word report, the Playbook section and AI commentary.

Uses Session T's `backend.common.format` (the Python twin of `frontend/src/lib/v5/format.ts`) when it is in
this checkout; until then the same rules, as fixed in docs/v5/THREAD_API.md section 3:

  amounts      SAR m or bn, 1-2 decimals     sar(1234.5) -> "SAR 1.23bn", sar(12.34) -> "SAR 12.3m", sar(1.234) -> "SAR 1.23m"
  percentages  1-2 decimals                  pct(0.1218) -> "12.2%", pct(0.0092) -> "0.92%"
  ratios       2 decimals                    ratio(1.23456) -> "1.23"
  bps          integer                       bps(43.6) -> "44 bps"
  counts       thousands separators          count(12345) -> "12,345"
"""
from __future__ import annotations

import math
import re
from typing import Any

DASH = "–"


def _ok(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _sar(m: Any, unit: str | None = None) -> str:
    if not _ok(m):
        return DASH
    m = float(m)
    if m == 0:
        return "SAR 0m"
    a = abs(m)
    sign = "−" if m < 0 else ""
    if (unit == "bn") or (unit is None and a >= 1000):
        return f"{sign}SAR {a / 1000:,.2f}bn"
    return f"{sign}SAR {a:,.{2 if a < 10 else 1}f}m"


def _pct(v: Any, dp: int | None = None, signed: bool = False, points: bool = False) -> str:
    if not _ok(v):
        return DASH
    p = float(v) if points else float(v) * 100
    d = dp if dp is not None else (1 if abs(p) >= 10 else 2)
    d = min(2, max(1, d))
    s = f"{abs(p):,.{d}f}%"
    return ("−" if p < 0 else "+" if signed and p > 0 else "") + s


def _ratio(v: Any) -> str:
    return f"{float(v):,.2f}" if _ok(v) else DASH


def _bps(v: Any, signed: bool = False) -> str:
    if not _ok(v):
        return DASH
    n = int(math.floor(float(v) + 0.5))  # half up, as format.ts (Math.round), so screen and commentary agree
    return f"{'+' if signed and n > 0 else ''}{n:,} bps"


def _count(v: Any) -> str:
    return f"{int(round(float(v))):,}" if _ok(v) else DASH


try:  # Session T's twin, when merged
    from backend.common import format as _common  # type: ignore[import-not-found]
    sar = getattr(_common, "sar", _sar)
    ratio = getattr(_common, "ratio", _ratio)
    count = getattr(_common, "count", _count)
except Exception:  # noqa: BLE001
    sar, ratio, count = _sar, _ratio, _count

# pct and bps keep their keyword arguments stable for this module's callers
pct = _pct
bps = _bps


def times(v: Any) -> str:
    """A cover ratio such as DSCR or leverage: 1.23x."""
    return f"{float(v):,.2f}x" if _ok(v) else DASH


def amount(v: Any, ccy: str = "SAR") -> str:
    """A deal amount in its own currency, millions."""
    if not _ok(v):
        return DASH
    a = float(v)
    return f"{ccy} {a / 1000:,.2f}bn" if abs(a) >= 1000 else f"{ccy} {a:,.{2 if abs(a) < 10 else 1}f}m"


def num(v: Any) -> str:
    if not _ok(v):
        return DASH
    f = float(v)
    if f.is_integer():
        return f"{int(f):,}"
    return f"{f:,.{1 if abs(f) >= 100 else 2}f}"


def by_unit(v: Any, unit: str) -> str:
    """Format a value by an engine unit: 'SAR m', 'share', 'x', 'years', 'bps', '%', 'rating'."""
    if isinstance(v, str) or v is None:
        return DASH if v is None else v
    u = (unit or "").strip()
    if u in ("SAR m", "sar"):
        return sar(v)
    if u in ("share", "ratio_share"):
        return pct(v)
    if u == "x":
        return times(v)
    if u == "years":
        return f"{num(v)} years"
    if u == "bps":
        return bps(v)
    if u == "%":
        return pct(v, points=True)
    if u.endswith(" m"):
        return amount(v, u.split()[0])
    return num(v)


# ---- by column key (the twin of format.ts kindOf / auto / header)

_TEXTY = re.compile(r"(_type|_name|_code|_band|_label|_kind|_status|_date|_period|_grade|_rating|^key$|^name$|^status$|^kind$|^scope$|"
                    r"breaches$|^approval$|_id$|^proposal$|^obligor|^sector$|^rm$|^structure$|^scenario$|^constraint$|^lever$)")
_BPS = re.compile(r"(^|_)bps$|_bp$|basis_points")
_PCT_POINTS = re.compile(r"(_pct|_pp|percent)$|^pct$")
_COUNT = re.compile(r"(count|^n$|^n_|_n$|number_of|borrowers$|facilities$|accounts$|customers$|names$|obligors$|warned$|rows$|notches)")
_RATIO = re.compile(r"(dscr|leverage|multiple|^ratio$|_ratio$|hhi|debt_ebitda)")
_SHARE = re.compile(r"(share|rate|coverage|utili[sz]ation|ltv|weight|probability|(^|_)pd($|_)|(^|_)lgd($|_)|ccf|raroc|roe|hurdle|yield|growth|"
                    r"concentration|cost_of_risk|^limit_share)")
_MONEY = re.compile(r"(sar|(^|_)ead($|_)|(^|_)ecl($|_)|limit|exposure|amount|rwa|capital|headroom|balance|income|(^|_)sva($|_)|_mn$|_m$|"
                    r"outstanding|provision|collateral_value|loss|profit|fee|(^|_)el($|_)|value$|used)")


def kind_of(key: str) -> str:
    k = re.sub(r"[\s-]+", "_", (key or "").lower())
    if _TEXTY.search(k):
        return "text"
    if _BPS.search(k):
        return "bps"
    if _PCT_POINTS.search(k):
        return "pct_points"
    if _COUNT.search(k):
        return "count"
    if _RATIO.search(k):
        return "ratio"
    if _SHARE.search(k):
        return "pct"
    if _MONEY.search(k):
        return "sar"
    return "num"


def auto(v: Any, key: str = "") -> str:
    """Format one value by its column key (G5). Text passes through; booleans read Yes/No."""
    if v is None:
        return DASH
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str):
        return v.replace("_", " ") if re.fullmatch(r"[a-z_]+", v) and "_" in v else v
    if not _ok(v):
        return DASH
    k = kind_of(key)
    if key in ("limit", "before", "value") and abs(float(v)) <= 1.0 and float(v) != 0:
        return pct(v)  # a share limit (sector, rating bucket), not money
    if k == "sar":
        return sar(v)
    if k == "pct":
        return pct(v) if abs(float(v)) <= 1.5 else pct(v, points=True)
    if k == "pct_points":
        return pct(v, points=True)
    if k == "ratio":
        return times(v) if "dscr" in key or "ebitda" in key else ratio(v)
    if k == "bps":
        return bps(v)
    if k == "count":
        return count(v)
    return num(v)


_ACR = {"ead": "EAD", "ecl": "ECL", "pd": "PD", "lgd": "LGD", "rwa": "RWA", "raroc": "RAROC", "sva": "SVA", "ltv": "LTV", "dscr": "DSCR",
        "el": "EL", "ccf": "CCF", "ftp": "FTP", "rm": "RM", "id": "ID", "sar": "SAR", "fx": "FX", "sme": "SME"}
_PLAIN = {"key": "Name", "share": "Share of book", "limit": "Limit", "kind": "Limit type", "headroom_share": "Headroom (share of book)",
          "headroom_sar_mn": "Headroom (SAR m)", "ead": "EAD (SAR m)", "amount_sar_mn": "Amount (SAR m)", "lifetime_raroc": "Lifetime RAROC (%)",
          "clears_hurdle": "Clears the hurdle", "hard_breaches": "Hard breaches", "soft_breaches": "Soft breaches", "obligor_name": "Obligor",
          "proposal_id": "Proposal", "tenor_years": "Tenor (years)", "trace_id": "Engine trace", "name": "Name", "used": "Used (SAR m)",
          "headroom": "Headroom", "sva": "SVA (SAR m)"}
_UNITS = {"sar", "mn", "m", "bn", "pct", "pp", "bps", "bp"}


def header(key: str) -> str:
    """A column key in plain words with its unit: 'headroom_sar_mn' -> 'Headroom (SAR m)'. Words pass through."""
    if not key:
        return ""
    if key in _PLAIN:
        return _PLAIN[key]
    if not re.fullmatch(r"[a-z0-9_]+", key):
        return key
    words = [w for w in key.split("_") if w and not (w in _UNITS and len(key.split("_")) > 1)]
    text = " ".join(_ACR.get(w, w) for w in words)
    text = text[:1].upper() + text[1:]
    k = kind_of(key)
    unit = {"sar": " (SAR m)", "pct": " (%)", "pct_points": " (%)", "bps": " (bps)"}.get(k, "")
    return text + unit


_LONG = re.compile(r"(?<![\d.\w])(-?\d+)\.(\d{3,})(?![\d.])")


def tidy(text: str) -> str:
    """Long decimals in prose rounded to 2 places (nothing with more than 4 decimals ever shows)."""
    return _LONG.sub(lambda m: f"{float(m.group(1) + '.' + m.group(2)):.2f}", str(text or ""))


__all__ = ["sar", "pct", "ratio", "bps", "count", "times", "amount", "num", "by_unit", "tidy", "auto", "header", "kind_of"]
