"""Deal facts that replace sector defaults in the transmission chain (I19-5).

Where the deal file has its own number (the largest customer's share of revenue, the revenue tied to financed
projects), the chain uses it and says so; otherwise the sector sensitivity from `dd_stress_sensitivity`.
Facts are read from Data Domains relations through `store.read` (Session E's reader once merged):

    dd_financials_detail    the largest debtor's share of receivables (top1_receivable_pct), latest audited period
    dd_obligor_financials   top-customer concentration columns (any of CONC_COLUMNS), when present
    dd_project              open projects: contract value (revised, else original), start and revised completion, WD%
    the proposal itself     `concentration.largest_customer_share` or `facts.largest_customer_share` when present
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.dealdesk.stress2 import store

CONC_COLUMNS = ("largest_customer_share", "top1_customer_share", "top_customer_share", "top1_customer_share_pct",
                "largest_customer_share_pct", "top_1_customer_pct", "concentration_top1_pct")
PROJECT_SECTORS_MIN_SHARE = 0.25


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _share(v: Any) -> float | None:
    f = _num(v)
    if f is None:
        return None
    return f / 100.0 if f > 1.0 else f


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    key = next((k for k in ("fiscal_year", "year", "period", "reporting_quarter", "period_end") if k in rows[0]), None)
    return sorted(rows, key=lambda r: str(r.get(key) or ""))[-1] if key else rows[-1]


def _year(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v)
    try:
        d = date.fromisoformat(s[:10])
        return d.year + (d.timetuple().tm_yday - 1) / 365.0
    except ValueError:
        f = _num(s[:4])
        return f


def largest_customer(p: dict[str, Any]) -> dict[str, Any] | None:
    for path in (("concentration", "largest_customer_share"), ("facts", "largest_customer_share")):
        v = p.get(path[0], {}) if isinstance(p.get(path[0]), dict) else {}
        s = _share(v.get(path[1]))
        if s is not None:
            return {"value": s, "source": f"deal file: {'.'.join(path)}", "relation": "dd_proposal", "row": p["proposal_id"]}
    # dd_financials_detail (E): the largest debtor's share of receivables, latest audited period of the subject entity
    det = [r for r in store.read("dd_financials_detail", proposal_id=p["proposal_id"]) if _share(r.get("top1_receivable_pct")) is not None]
    if det:
        aud = [r for r in det if r.get("period_kind") == "audited"] or det
        subj = [r for r in aud if r.get("entity_scope") in ("standalone", "branch")] or aud
        r = sorted(subj, key=lambda x: (str(x.get("period_end") or ""), str(x.get("period_label") or "")))[-1]
        s_ = _share(r["top1_receivable_pct"])
        if s_ is not None and 0 < s_ <= 1:
            return {"value": s_, "source": f"deal file: largest debtor {s_ * 100:.0f}% of receivables, {r.get('entity_name') or r.get('entity_id')} "
                                           f"{r.get('period_label')} (dd_financials_detail)", "relation": "dd_financials_detail",
                    "row": f"{p['proposal_id']} {r.get('entity_id')} {r.get('period_label')}",
                    "trace": store.source("dd_financials_detail", {"proposal_id": p["proposal_id"], "entity_id": r.get("entity_id"),
                                                                   "period_label": r.get("period_label")}, "top1_receivable_pct")}
    rows = store.read("dd_obligor_financials", proposal_id=p["proposal_id"])
    if not rows and p["obligor"].get("obligor_id"):
        rows = store.read("dd_obligor_financials", obligor_id=p["obligor"]["obligor_id"])
    r = _latest(rows)
    if r:
        for c in CONC_COLUMNS:
            s = _share(r.get(c))
            if s is not None and 0 < s <= 1:
                per = r.get("fiscal_year") or r.get("year") or r.get("reporting_quarter") or ""
                return {"value": s, "source": f"deal file: {c} {per}".strip(), "relation": "dd_obligor_financials",
                        "row": f"{p['proposal_id']} {per}".strip()}
    return None


def projects(p: dict[str, Any]) -> dict[str, Any] | None:
    """Annual revenue the deal's financed projects carry, as a share of the latest audited revenue."""
    rows = store.read("dd_project", proposal_id=p["proposal_id"])
    if not rows and p["obligor"].get("obligor_id"):
        rows = store.read("dd_project", obligor_id=p["obligor"]["obligor_id"])
    if not rows:
        return None
    ys = [y for y in p["financials"]["years"] if y["kind"] == "actual"]
    rev = float(ys[-1]["revenue"]) if ys else 0.0
    annual = 0.0
    rows = [r for r in rows if str(r.get("status") or "") != "completed"]
    for r in rows:
        cv = _num(r.get("contract_value_revised_mn")) or _num(r.get("contract_value_original_mn")) or _num(r.get("contract_value_revised")) or \
            _num(r.get("contract_value")) or 0.0
        wd = _share(r.get("work_done_pct") or r.get("wd_pct"))
        s, e = _year(r.get("start_date") or r.get("start")), _year(r.get("completion_revised") or r.get("completion_original") or r.get("end_date"))
        dur = max(0.5, (e - s)) if (s is not None and e is not None) else 2.0
        remaining = cv * (1 - wd) if wd is not None else cv
        annual += remaining / max(0.5, dur * (1 - wd) if wd is not None else dur)
    if rev <= 0 or annual <= 0:
        return None
    share = min(1.0, annual / rev)
    return {"value": share, "projects": len(rows), "annual_project_revenue": annual,
            "trace": store.source("dd_project", {"proposal_id": p["proposal_id"]}, "contract_value_revised_mn"),
            "source": f"deal file: {len(rows)} financed project{'s' if len(rows) != 1 else ''} (dd_project), "
                      f"{annual:,.1f} m a year against revenue {rev:,.1f} m", "relation": "dd_project", "row": p["proposal_id"]}


def deal_facts(p: dict[str, Any]) -> dict[str, Any]:
    return {"largest_customer_share": largest_customer(p), "project_revenue_share": projects(p)}
