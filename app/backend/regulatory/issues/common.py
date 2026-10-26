"""Shared pieces of the issue views (PLAN_R14 r, K2/K4): number format, figures with their lineage, names, branches,
capital, owners and dates for the actions, and the one output shape every issue view returns.

Every figure is a dict {label, value, unit, display, source} where `source` names the Data Domains relation, the row
keys and the column it comes from (N3). Nothing here calls a model (N4): the same books give the same view.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable
from urllib.parse import quote

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt

#: The Policy Docs page of the Standards (crm_checks.HREF) and where each issue view lives.
POLICY_HREF = "/policy-docs?doc=pd_cbuae_crm"
ISSUE_PAGE = "/studio/regulatory-intelligence"

#: Owners are roles, never people (fictional names only, N9): the bank fills its own names in.
OWNERS = {
    "provisioning": "Head of IFRS 9 provisioning (Finance)",
    "collateral": "Head of collateral management",
    "model": "LGD model owner (Model Risk)",
    "remedial": "Head of remedial and recoveries",
    "board": "CRO, to the Board Risk Committee",
    "classification": "Head of credit risk control (staging)",
    "credit": "Head of corporate credit",
    "ecl_run": "ECL run owner (Risk Analytics)",
    "data": "Data owner, corporate book (Data Office)",
    "limits": "Head of portfolio management",
}


def issue_href(issue_id: str, origin: str = "") -> str:
    """The issue view's address (clicked from the brief; `from=` is added by the caller that navigates)."""
    return f"{ISSUE_PAGE}?issue={quote(issue_id, safe='')}" + (f"&from={quote(origin)}" if origin else "")


def r2(x: float | int | None, nd: int = 4) -> float:
    return round(float(x or 0.0), nd)


def pct(a: float, b: float) -> float | None:
    return round(100.0 * a / b, 2) if b else None


def fig(label: str, value: float | int | None, unit: str = "", source: dict[str, Any] | None = None,
        display: str = "") -> dict[str, Any]:
    out = {"label": label, "value": value, "unit": unit, "display": display or fmt(value, unit)}
    if source:
        out["source"] = source
    return out


def src(domain: str, relation: str, key: dict[str, Any] | None = None, column: str = "", period: str = "",
        method: str = "") -> dict[str, Any]:
    out = {"domain": domain, "relation": relation, "key": dict(key or {}), "period": period, "column": column}
    if method:
        out["method"] = method
    return out


def due(today: date, days: int) -> str:
    """A due date `days` after today, moved off a Friday or Saturday (the Saudi weekend) to the Sunday after."""
    d = today + timedelta(days=days)
    while d.weekday() in (4, 5):
        d += timedelta(days=1)
    return d.isoformat()


def action(n: int, text: str, owner_key: str, today: date, days: int, why: str, figure: dict[str, Any] | None = None,
           link: dict[str, str] | None = None) -> dict[str, Any]:
    out = {"n": n, "action": text, "owner": OWNERS[owner_key], "due": due(today, days), "why": why}
    if figure:
        out["figure"] = figure
    if link:
        out["link"] = link
    return out


def _chunks(xs: list[str], n: int = 500) -> Iterable[list[str]]:
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def borrower_names(ids: Iterable[str], period: str) -> dict[str, str]:
    """Borrower names from the corporate book (cockpit.corp_borrower_quarter)."""
    ids = sorted({str(i) for i in ids if i})
    out: dict[str, str] = {}
    for part in _chunks(ids):
        ph = ", ".join("?" for _ in part)
        r = R.read("cockpit", "corp_borrower_quarter", columns="borrower_id, any_value(borrower_name) AS name",
                   where=f"borrower_id IN ({ph}) AND reporting_quarter = ?", args=[*part, period], group="borrower_id")
        out.update({str(x["borrower_id"]): str(x["name"]) for x in r.rows})
    return out


def borrower_frame(period: str) -> dict[str, dict[str, Any]]:
    """Per borrower at the period: name, sector, group (cockpit.corp_borrower_quarter)."""
    r = R.read("cockpit", "corp_borrower_quarter",
               columns="borrower_id, borrower_name, sector, group_id, group_name, rating_current",
               where="reporting_quarter = ?", args=[period])
    return {str(x["borrower_id"]): x for x in r.rows}


def branches(period: str) -> dict[str, dict[str, Any]]:
    """Per borrower: branch and relationship manager (branches.branch_corporate_quarter)."""
    r = R.read("branches", "branch_corporate_quarter",
               columns="borrower_id, branch_id, branch_name, region, business_unit, rm_id, rm_name",
               where="reporting_quarter = ?", args=[period])
    return {str(x["borrower_id"]): x for x in r.rows}


def capital() -> dict[str, Any]:
    """Credit RWA (collateral.col_crwa, both books) and Tier 1 capital (collateral.col_large_exposure)."""
    rw = R.read("collateral", "col_crwa", columns="sum(crwa_sar_mn) AS rwa, max(as_of_date) AS d")
    t1 = R.read("collateral", "col_large_exposure", columns="max(tier1_capital_sar_mn) AS t1, max(as_of_date) AS d")
    rwa = float((rw.rows[0] or {}).get("rwa") or 0.0) if rw.rows else 0.0
    tier1 = float((t1.rows[0] or {}).get("t1") or 0.0) if t1.rows else 0.0
    return {"rwa": rwa, "tier1": tier1,
            "rwa_src": src("collateral", "col_crwa", {}, "crwa_sar_mn", str((rw.rows or [{}])[0].get("d") or ""),
                           "sum over both books"),
            "tier1_src": src("collateral", "col_large_exposure", {}, "tier1_capital_sar_mn",
                             str((t1.rows or [{}])[0].get("d") or ""))}


def impact_rows(topup: float, *, what: str = "provision top-up") -> list[dict[str, Any]]:
    """ECL, P&L and CET1 effect of a provision top-up (pre-tax and pre-zakat; credit RWA only: stated)."""
    cap = capital()
    bps = (topup / cap["rwa"] * 10000.0) if cap["rwa"] else None
    t1_pct = (100.0 * topup / cap["tier1"]) if cap["tier1"] else None
    return [
        fig(f"ECL ({what})", r2(topup), "SAR mn", src("regulatory", "crm_breach", {}, "shortfall_sar_mn", method="sum")),
        fig("P&L charge, pre-tax", r2(-topup), "SAR mn", src("regulatory", "crm_breach", {}, "shortfall_sar_mn",
                                                            method="the top-up is an impairment charge")),
        fig("CET1 ratio, bps", None if bps is None else round(-bps, 1), "bps", {**cap["rwa_src"], "method":
            "top-up ÷ credit RWA × 10,000 (pre-tax; credit RWA only)"},
            display="–" if bps is None else f"−{bps:,.0f} bps"),
        fig("Share of Tier 1 capital", None if t1_pct is None else round(t1_pct, 2), "%", cap["tier1_src"]),
    ]


def table(tid: str, title: str, columns: list[tuple[str, str, str]], rows: list[dict[str, Any]],
          total: dict[str, Any] | None = None, note: str = "") -> dict[str, Any]:
    """columns: (key, label, unit) where unit is one of "", "SAR mn", "%", "n", "text"."""
    return {"id": tid, "title": title, "columns": [{"key": k, "label": lab, "unit": u} for k, lab, u in columns],
            "rows": rows, "total": total, "note": note}


def bridge(title: str, total: float, steps: list[dict[str, Any]], method: str, unit: str = "SAR mn") -> dict[str, Any]:
    """A bridge whose steps sum to the total: rounding is closed on the largest step, and the check is returned."""
    vals = [round(float(s["value"]), 4) for s in steps]
    gap = round(round(total, 4) - sum(vals), 4)
    if steps and abs(gap) > 0:
        i = max(range(len(steps)), key=lambda k: abs(vals[k]))
        vals[i] = round(vals[i] + gap, 4)
    out = []
    for s, v in zip(steps, vals):
        out.append({**s, "value": v, "display": fmt(v, unit), "share_pct": pct(v, total) if total else None})
    return {"title": title, "total": round(total, 4), "total_display": fmt(total, unit), "unit": unit, "steps": out,
            "sums_to_total": abs(sum(vals) - round(total, 4)) < 1e-6, "method": method}


def concentration(rows: list[dict[str, Any]], value_key: str, period: str, *, label: str) -> dict[str, Any]:
    """Top 10 borrowers' share, and the split by sector, branch and relationship manager. `rows` carry borrower_id."""
    by_b: dict[str, float] = {}
    for r in rows:
        by_b[str(r["borrower_id"])] = by_b.get(str(r["borrower_id"]), 0.0) + float(r[value_key] or 0.0)
    total = sum(by_b.values())
    top = sorted(by_b.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    bor = borrower_frame(period)
    br = branches(period)

    def split(key_fn) -> list[dict[str, Any]]:
        acc: dict[str, list[float]] = {}
        for b, v in by_b.items():
            k = key_fn(b) or "Not recorded"
            a = acc.setdefault(k, [0.0, 0])
            a[0] += v
            a[1] += 1
        return [{"name": k, "value": r2(v), "display": fmt(v, "SAR mn"), "share_pct": pct(v, total), "borrowers": n}
                for k, (v, n) in sorted(acc.items(), key=lambda kv: (-kv[1][0], kv[0]))[:6]]

    top_rows = [{"borrower_id": b, "name": str((bor.get(b) or {}).get("borrower_name") or b), "value": r2(v),
                 "display": fmt(v, "SAR mn"), "share_pct": pct(v, total),
                 "sector": str((bor.get(b) or {}).get("sector") or ""),
                 "branch": str((br.get(b) or {}).get("branch_name") or ""),
                 "rm": str((br.get(b) or {}).get("rm_name") or ""),
                 "href": f"/borrower-360?id={quote(b)}"} for b, v in top]
    top_sum = sum(v for _, v in top)
    return {
        "label": label, "borrowers": len(by_b), "total": r2(total), "total_display": fmt(total, "SAR mn"),
        "top10_share_pct": pct(top_sum, total), "top": top_rows,
        "by_sector": split(lambda b: str((bor.get(b) or {}).get("sector") or "")),
        "by_branch": split(lambda b: str((br.get(b) or {}).get("branch_name") or "")),
        "by_rm": split(lambda b: str((br.get(b) or {}).get("rm_name") or "")),
        "source": [src("cockpit", "corp_borrower_quarter", {"reporting_quarter": period}, "sector", period),
                   src("branches", "branch_corporate_quarter", {"reporting_quarter": period}, "rm_name", period)],
    }


def words(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def pct_words(v: float | None) -> str:
    """A percentage in plain words: whole numbers from 10%, one decimal below."""
    if v is None:
        return "–"
    return f"{v:.0f}%" if abs(v) >= 10 else f"{v:.1f}%"


def lead_phrase(share: float) -> str:
    return "Most of the gap" if share >= 50 else "The largest part of the gap"
