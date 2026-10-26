"""R16 d: arithmetic helpers: statements that balance, money formats, deterministic series."""
from __future__ import annotations

import datetime as dt
import random
from typing import Any

PL_ORDER = ["revenue", "cost_of_sales", "gross_profit", "operating_expenses", "operating_profit", "finance_cost", "zakat", "net_profit"]
CA = ["cash", "trade_receivables", "retention_receivables", "contract_assets", "inventory", "due_from_related", "other_current_assets"]
NCA = ["ppe", "other_noncurrent_assets"]
CL = ["short_term_borrowings", "trade_payables", "due_to_related", "other_current_liabilities", "current_portion_ltd"]
NCL = ["long_term_borrowings", "end_of_service"]
EQ = ["share_capital", "statutory_reserve", "retained_earnings"]


def statement(d: dict[str, float], plug: str = "other_current_liabilities") -> dict[str, float]:
    """Complete a statement given in SAR million: P&L subtotals, then the balance sheet with `plug` solved so that
    assets = liabilities + equity. Returns a new dict rounded to 3 decimals (SAR thousands)."""
    s = {k: round(float(v), 3) for k, v in d.items()}
    for k in CA + NCA + CL + NCL + EQ:
        s.setdefault(k, 0.0)
    s["gross_profit"] = round(s["revenue"] - s["cost_of_sales"], 3)
    s["operating_profit"] = round(s["gross_profit"] - s["operating_expenses"], 3)
    s.setdefault("zakat", 0.0)
    s["net_profit"] = round(s["operating_profit"] - s["finance_cost"] - s["zakat"], 3)
    s["current_assets"] = round(sum(s[k] for k in CA), 3)
    s["total_assets"] = round(s["current_assets"] + sum(s[k] for k in NCA), 3)
    s["total_equity"] = round(sum(s[k] for k in EQ), 3)
    others = round(sum(s[k] for k in CL + NCL if k != plug), 3)
    s[plug] = round(s["total_assets"] - s["total_equity"] - others, 3)
    if s[plug] <= 0:
        raise ValueError(f"plug {plug} is {s[plug]}: the statement does not close")
    s["current_liabilities"] = round(sum(s[k] for k in CL), 3)
    s["total_liabilities"] = round(s["current_liabilities"] + sum(s[k] for k in NCL), 3)
    s["ebitda"] = round(s["operating_profit"] + s.get("depreciation", 0.0), 3)
    return s


def ocf(prev: dict[str, float], cur: dict[str, float]) -> float:
    """Indirect operating cash flow (SAR m): NP + D&A + zakat paid approx. - change in working capital."""
    wc = ["trade_receivables", "retention_receivables", "contract_assets", "inventory", "due_from_related", "other_current_assets"]
    wl = ["trade_payables", "due_to_related", "other_current_liabilities", "end_of_service"]
    d_assets = sum(cur.get(k, 0) - prev.get(k, 0) for k in wc)
    d_liab = sum(cur.get(k, 0) - prev.get(k, 0) for k in wl)
    return round(cur["net_profit"] + cur.get("depreciation", 0) - d_assets + d_liab, 3)


def sar(m: float | None) -> int | None:
    """SAR million -> SAR units (integer)."""
    return None if m is None else int(round(m * 1_000_000))


def fmt_sar(units: int | float | None, prefix: bool = True) -> str:
    if units is None:
        return "—"
    v = int(round(units))
    s = f"{abs(v):,}"
    s = f"({s})" if v < 0 else s
    return f"SAR {s}" if prefix else s


def fmt_m(m: float | None, prefix: bool = True) -> str:
    return fmt_sar(sar(m), prefix)


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    y, mo, d = iso.split("-")
    return f"{d}/{mo}/{y}"


def fmt_pct(v: float, nd: int = 1) -> str:
    return f"{v:.{nd}f}%"


def months(start: str, n: int) -> list[str]:
    y, m = map(int, start.split("-")[:2])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def month_end(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - dt.timedelta(days=1)).isoformat()


def add_days(iso: str, n: int) -> str:
    return (dt.date.fromisoformat(iso) + dt.timedelta(days=n)).isoformat()


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def split(total: float, n: int, rnd: random.Random, spread: float = 0.6, nd: int = 2) -> list[float]:
    """n positive parts that sum exactly to total (rounded to nd decimals)."""
    w = [1 + spread * (rnd.random() - 0.5) * 2 for _ in range(n)]
    sw = sum(w)
    parts = [round(total * x / sw, nd) for x in w[:-1]]
    parts.append(round(total - sum(parts), nd))
    return parts


def series(total: float, n: int, rnd: random.Random, trend: float = 0.0, noise: float = 0.08, nd: int = 3) -> list[float]:
    """n monthly values summing to total, with a linear trend (fraction over the window) and noise."""
    w = [(1 + trend * (i / max(1, n - 1) - 0.5)) * (1 + noise * (rnd.random() - 0.5) * 2) for i in range(n)]
    sw = sum(w)
    vals = [round(total * x / sw, nd) for x in w[:-1]]
    vals.append(round(total - sum(vals), nd))
    return vals


def ratios(s: dict[str, float]) -> dict[str, Any]:
    tnw = s["total_equity"]
    debt = s["short_term_borrowings"] + s["current_portion_ltd"] + s["long_term_borrowings"]
    return {"gpm": 100 * s["gross_profit"] / s["revenue"], "npm": 100 * s["net_profit"] / s["revenue"],
            "opm": 100 * s["operating_profit"] / s["revenue"], "current_ratio": s["current_assets"] / s["current_liabilities"],
            "leverage": s["total_liabilities"] / tnw, "gearing": debt / tnw, "debt": debt,
            "roe": 100 * s["net_profit"] / tnw, "roa": 100 * s["net_profit"] / s["total_assets"],
            "wc": s["current_assets"] - s["current_liabilities"],
            "dso": 365 * s["trade_receivables"] / s["revenue"] if s.get("months", 12) == 12 else 273 * s["trade_receivables"] / s["revenue"]}
