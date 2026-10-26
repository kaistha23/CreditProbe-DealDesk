"""The one number formatter, Python twin of frontend/src/lib/v5/format.ts (PLAN_R5 G5).

Every number in a Word/Excel export, a Playbook section or an AI answer goes through here:
  amounts      SAR m or bn, 1–2 decimals     sar(1234.5) -> "SAR 1.23bn"; sar(12.34) -> "SAR 12.3m"
  percentages  1–2 decimals                  pct(0.1218) -> "12.2%" (fraction); pct(12.18, points=True) -> "12.2%"
  ratios       2 decimals                    ratio(1.23456) -> "1.23"
  bps          integer                       bps(43.6) -> "44 bps"
  counts       thousands separators          count(12345) -> "12,345"
`auto(value, key)` picks by column key; `header(key)` gives plain words with the unit; `tidy_text` rounds long
decimals in prose; `EXCEL_FORMATS` are the matching Excel number formats. Contract: docs/v5/THREAD_API.md section 3.
"""
from __future__ import annotations

import math
import re
from typing import Any

DASH = "–"


def _ok(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def sar(millions: Any, unit: str | None = None) -> str:
    if not _ok(millions):
        return DASH
    if millions == 0:
        return "SAR 0m"
    bn = unit == "bn" if unit else abs(millions) >= 1000
    if bn:
        return f"SAR {millions / 1000:,.2f}bn"
    return f"SAR {millions:,.{2 if abs(millions) < 10 else 1}f}m"


def pct(v: Any, points: bool = False, dp: int | None = None, signed: bool = False) -> str:
    if not _ok(v):
        return DASH
    p = v if points else v * 100
    d = dp if dp is not None else (1 if abs(p) >= 10 else 2)
    d = min(2, max(1, d))
    return f"{'+' if signed and p > 0 else ''}{p:,.{d}f}%"


def ratio(v: Any) -> str:
    return f"{v:,.2f}" if _ok(v) else DASH


def bps(v: Any, signed: bool = False) -> str:
    if not _ok(v):
        return DASH
    n = int(round(v)) or 0
    return f"{'+' if signed and n > 0 else ''}{n:,} bps"


def pp(v: Any, signed: bool = False) -> str:
    if not _ok(v):
        return DASH
    d = 1 if abs(v) >= 10 else 2
    x = round(v, d) or 0.0
    return f"{'+' if signed and x > 0 else ''}{x:,.{d}f}pp"


def count(v: Any) -> str:
    return f"{int(round(v)):,}" if _ok(v) else DASH


def num(v: Any) -> str:
    if not _ok(v):
        return DASH
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.{1 if abs(v) >= 100 else 2}f}"


#: A yes/no column ("clears_hurdle", "is_watchlist"): never a percentage or an amount (twin of FLAG in format.ts).
FLAG = re.compile(r"^(clears|is|has|passes|meets|breached|flag)(_|$)|_flag$|^(feasible|pass|ok)$")


def kind_of(key: str) -> str:
    k = re.sub(r"[\s-]+", "_", (key or "").lower())
    if FLAG.search(k):
        return "num"
    if re.search(r"(_type|_name|_code|_band|_label|_kind|_status|_date|_period|_grade|_rating)$", k):
        return "num"
    if re.search(r"(^|_)bps$|_bp$|basis_points", k):
        return "bps"
    if re.search(r"(_pp$|_pp_|^pp$|percentage_points)", k):
        return "pp"
    if re.search(r"(_pct|percent|_%|^%$|^pct$|_pct_)", k):
        return "pct_points"
    if re.search(r"(_sar_bn|_bn$|^sar_bn$)", k):
        return "sar_bn"
    if re.search(r"(count|^n$|^n_|_n$|number_of|borrowers$|facilities$|accounts$|customers$|names$|obligors$|warned$|_ids?$|rows$)", k):
        return "count"
    if re.search(r"(dscr|leverage|multiple|gini|auc|(^|_)ks($|_)|psi|(^|_)iv($|_)|vif|woe|^ratio$|_ratio$|hhi|brier|z_score|beta)", k):
        return "ratio"
    if re.search(r"(share|rate|coverage|utili[sz]ation|ltv|weight|probability|(^|_)pd($|_)|(^|_)lgd($|_)|ccf|raroc|roe|hurdle|"
                 r"margin|yield|growth|change_rel|concentration|cost_of_risk)", k):
        return "pct_auto"
    if re.search(r"(sar|(^|_)ead($|_)|(^|_)ecl($|_)|limit|exposure|amount|rwa|capital|headroom|balance|income|(^|_)sva($|_)|_mn$|_m$|"
                 r"outstanding|provision|collateral_value|loss|profit|fee)", k):
        return "sar"
    return "num"


#: A raw float as text ("0.2810632681763545"), formatted as the number it is (PLAN_R6 E2).
RAW_FLOAT = re.compile(r"^-?\d+\.\d{5,}$")


def auto(v: Any, key: str = "") -> str:
    if v is None:
        return DASH
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str) and RAW_FLOAT.match(v.strip()):
        return auto(float(v.strip()), key)
    if not isinstance(v, (int, float)):
        return str(v)
    if not math.isfinite(v):
        return DASH
    k = kind_of(key)
    if k == "sar":
        return sar(v)
    if k == "sar_bn":
        return sar(v * 1000)
    if k == "pct_points":
        return pct(v, points=True)
    if k == "pct_auto":
        return pct(v, points=abs(v) > 1.5)
    if k == "pp":
        return pp(v)
    if k == "ratio":
        return ratio(v)
    if k == "bps":
        return bps(v)
    if k == "count":
        return count(v)
    return num(v)


ACRONYMS = {"ead": "EAD", "ecl": "ECL", "pd": "PD", "lgd": "LGD", "rwa": "RWA", "raroc": "RAROC", "sva": "SVA", "ltv": "LTV",
            "dscr": "DSCR", "hhi": "HHI", "npl": "NPL", "dpd": "DPD", "ccf": "CCF", "ftp": "FTP", "rm": "RM", "id": "ID",
            "psi": "PSI", "csi": "CSI", "iv": "IV", "ks": "KS", "auc": "AUC", "mev": "MEV", "ews": "EWS", "sicr": "SICR",
            "sar": "SAR", "roe": "ROE", "gdp": "GDP", "vif": "VIF", "woe": "WoE", "el": "EL", "sme": "SME", "qoq": "QoQ", "yoy": "YoY"}
UNIT_TOKENS = {"sar", "mn", "m", "bn", "pct", "pp", "bps", "bp"}


def header(key: str) -> str:
    if not key:
        return ""
    if "_" not in key and re.search(r"[A-Z ]", key) and key != key.upper():
        return key
    k = kind_of(key)
    if FLAG.search(key.lower()):
        return key[:1].upper() + key[1:].lower().replace("_", " ")
    words =[w for w in re.split(r"[_\s]+", key.lower()) if w]
    if len(words) > 1:
        words = [w for w in words if w not in UNIT_TOKENS] or words
    text = " ".join(ACRONYMS.get(w, w.capitalize() if i == 0 else w) for i, w in enumerate(words))
    unit = {"sar": " (SAR m)", "sar_bn": " (SAR bn)", "pct_points": " (%)", "pct_auto": " (%)", "bps": " (bps)", "pp": " (pp)"}.get(k, "")
    return text + unit


_LONG = re.compile(r"(^|[^\d.\w])(-?\d+)\.(\d{3,})(?![\d.])")


def tidy_text(text: str) -> str:
    """Long decimals in prose rounded to 2 places (G5: no visible number with more than 4 decimals, ever)."""
    return _LONG.sub(lambda m: f"{m.group(1)}{float(m.group(2) + '.' + m.group(3)):.2f}", text or "")


#: Excel number formats matching the kinds (house style exports).
EXCEL_FORMATS = {"pp": '0.00"pp"', "sar": '#,##0.0', "sar_bn": '#,##0.00', "pct_points": '0.0"%"', "pct_auto": '0.0%', "ratio": '0.00',
                 "bps": '0" bps"', "count": '#,##0', "num": '#,##0.00'}

__all__ = ["sar", "pct", "pp", "ratio", "bps", "count", "num", "auto", "kind_of", "header", "tidy_text", "EXCEL_FORMATS"]
