"""Monitoring-tier rules: review frequency, Early Warning threshold override and named triggers per stressed driver.

A named trigger is an observable condition on the name, set from the stress result that drove the tier:
"largest customer share > 40%", "operating inflows down 18% or more on the year", "any rating downgrade". Each names
the metric, where it is observed (an EWS book field, a borrower ratio, a deal-file relation) and its threshold.
Tier High: a fired trigger raises an Early Warning alert and a Book card. Tier Medium: the driver is watched (a
Book card, no alert). Tier Standard: no named trigger.

EWS threshold override (tier High only): the name's EWS band floors are lowered by `HIGH_FLOOR_FACTOR` (rounded
down, at least 1 point apart), so the same rule score reaches a band sooner for that name. The EWS rule set and
its book-wide floors are unchanged.
"""
from __future__ import annotations

import math
from typing import Any

TIERS = ("High", "Medium", "Standard")
REVIEW_MONTHS = {"High": 3, "Medium": 6, "Standard": 12}
HIGH_FLOOR_FACTOR = 0.75
TIER_ORDER = {"Standard": 0, "Medium": 1, "High": 2}


def ews_thresholds(tier: str, domain: str = "corporate") -> dict[str, Any]:
    from backend.ews_domain import ews_rules as er
    mod, high, crit = er.BAND_FLOORS[domain]
    if tier != "High":
        return {"domain": domain, "ruleset": er.RULESET_VERSION, "override": False,
                "band_floors": {"moderate": mod, "high": high, "critical": crit}, "book_floors": {"moderate": mod, "high": high, "critical": crit}}
    m2 = max(1, math.floor(mod * HIGH_FLOOR_FACTOR))
    h2 = max(m2 + 1, math.floor(high * HIGH_FLOOR_FACTOR))
    c2 = max(h2 + 1, math.floor(crit * HIGH_FLOOR_FACTOR))
    return {"domain": domain, "ruleset": er.RULESET_VERSION, "override": True, "factor": HIGH_FLOOR_FACTOR,
            "band_floors": {"moderate": m2, "high": h2, "critical": c2}, "book_floors": {"moderate": mod, "high": high, "critical": crit},
            "basis": f"Tier High: this name's EWS band floors are the book's x {HIGH_FLOOR_FACTOR:g} (rounded down)."}


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _row_with(rows: list[dict[str, Any]], pred) -> dict[str, Any] | None:
    sev = {"mild": 0, "moderate": 1, "severe": 2}
    c = [r for r in rows if r.get("applicable") and r.get("breaks") and pred(r)]
    return min(c, key=lambda r: sev.get(r["severity"], 3)) if c else None


def triggers_for(tier: str, drivers: list[str], rows: list[dict[str, Any]], rv: dict[str, Any] | None, lab: Any,
                 facts: dict[str, Any]) -> list[dict[str, Any]]:
    if tier == "Standard":
        return []
    action = "alert" if tier == "High" else "watch"
    out: list[dict[str, Any]] = []
    rev_be = None
    if rv:
        r = next((x for x in rv["drivers"] if x["driver"] == "revenue_pct"), None)
        if r:
            found = [c for c in r["criteria"] if c["status"] == "found"]
            if found:
                rev_be = min(found, key=lambda c: abs(c["value"]))
    for d in drivers:
        if d == "revenue":
            if rev_be:
                x = abs(rev_be["value"]) / 2
                basis = f"half the revenue fall at which {rev_be['label']} ({abs(rev_be['value']) * 100:.0f}%), so the bank acts before the break"
            else:
                row = _row_with(rows, lambda r: abs((r.get("resolved") or {}).get("revenue_pct", 0)) > 0)
                x = abs((row or {}).get("resolved", {}).get("revenue_pct", 0.2)) / 2 or 0.1
                basis = "half the revenue fall of the mildest breaking scenario"
            x = max(0.05, round(x * 20) / 20)
            out.append({"trigger_id": "T-REVENUE", "driver": d, "label": f"Operating inflows down {_fmt_pct(x)} or more on the year",
                        "metric": "inflow_trend_pct", "source": "ews_corp_exposure (Open Banking inflows)", "op": "<=",
                        "threshold": -x * 100, "unit": "%", "action": action, "basis": basis})
        elif d == "customer":
            f = facts.get("largest_customer_share")
            share = f["value"] if f else None
            th = max(0.40, (share or 0) + 0.10)
            out.append({"trigger_id": "T-CUSTOMER", "driver": d, "label": f"Largest customer share above {_fmt_pct(th)}",
                        "metric": "largest_customer_share", "source": "dd_obligor_financials (annual and interim review)", "op": ">",
                        "threshold": th, "unit": "share", "action": action,
                        "basis": ("deal file share " + _fmt_pct(share) + " + 10 points, at least 40%") if share is not None else "sector default; at least 40%"})
        elif d == "margin":
            fin = lab.base_r
            m0 = fin["ebitda"] / fin["revenue"] if fin["revenue"] else 0
            row = _row_with(rows, lambda r: (r.get("resolved") or {}).get("ebitda_margin_bps", 0) < 0)
            bps = abs((row or {}).get("resolved", {}).get("ebitda_margin_bps", -300)) / 2
            th = (m0 - bps / 1e4) * 100
            out.append({"trigger_id": "T-MARGIN", "driver": d, "label": f"EBITDA margin below {th:.1f}% (approval {m0 * 100:.1f}%)",
                        "metric": "ebitda_margin_pct", "source": "corp_borrower_quarter (borrower ratios)", "op": "<", "threshold": th, "unit": "%",
                        "action": action, "basis": "half the margin squeeze of the mildest breaking scenario"})
        elif d == "payment_delay":
            out.append({"trigger_id": "T-PAYMENTS", "driver": d, "label": "Returned payments 2 or more a quarter, or past due at another lender",
                        "metric": "returned_payments_q", "source": "ews_corp_exposure (Open Banking, bureau)", "op": ">=", "threshold": 2, "unit": "count",
                        "also": {"metric": "external_dpd_days", "op": ">", "threshold": 30}, "action": action,
                        "basis": "slower collections show first as returned payments and external arrears"})
        elif d == "project_delay":
            out.append({"trigger_id": "T-PROJECT", "driver": d, "label": "Financed project extension of time 3 months or more",
                        "metric": "extension_months", "source": "dd_project (payment certificates and EOT)", "op": ">=", "threshold": 3, "unit": "months",
                        "action": action, "basis": "the mildest delay in the ladder"})
        elif d == "rates":
            out.append({"trigger_id": "T-RATES", "driver": d, "label": "Benchmark rate up 100 bps or more since approval",
                        "metric": "benchmark_change_bps", "source": "Treasury (FTP curve)", "op": ">=", "threshold": 100, "unit": "bps",
                        "action": action, "basis": "the mild rate scenario"})
        elif d == "collateral":
            out.append({"trigger_id": "T-COLLATERAL", "driver": d, "label": "Collateral LTV above 80%", "metric": "collateral_ltv_pct",
                        "source": "ews_corp_exposure (collateral register)", "op": ">", "threshold": 80, "unit": "%", "action": action,
                        "basis": "the cover the collateral scenarios break at"})
        elif d == "rating":
            out.append({"trigger_id": "T-RATING", "driver": d, "label": "Any rating downgrade", "metric": "rating_notches_moved",
                        "source": "ews_corp_exposure (rating history)", "op": "<", "threshold": 0, "unit": "notches", "action": action,
                        "basis": "the rating family breaks the deal"})
        elif d == "guarantee":
            out.append({"trigger_id": "T-GUARANTEE", "driver": d, "label": "Guarantor downgraded or legal opinion outstanding",
                        "metric": "guarantor_rating_notches_moved", "source": "dd_collateral_guarantee", "op": "<", "threshold": 0, "unit": "notches",
                        "action": action, "basis": "the deal does not stand on the obligor alone"})
        elif d == "dscr":
            pass
    # DSCR is always watched for High and Medium: the covenant plus 10% headroom
    cov = next((c for c in lab.p["security"].get("covenants", []) if c["type"].lower().startswith("dscr")), None)
    th = float(cov["threshold"]) * 1.1 if cov else 1.1
    out.append({"trigger_id": "T-DSCR", "driver": "dscr", "label": f"DSCR below {th:.2f}x", "metric": "dscr_x",
                "source": "corp_borrower_quarter (borrower ratios)", "op": "<", "threshold": th, "unit": "x", "action": action,
                "basis": ("DSCR covenant " + f"{float(cov['threshold']):.2f}x + 10% headroom") if cov else "DSCR 1.0 + 10% headroom"})
    return out


def fires(trig: dict[str, Any], obs: dict[str, Any]) -> tuple[bool | None, Any]:
    """(fired, observed value); None when the metric is not observed for the name."""
    def one(metric: str, op: str, th: float) -> tuple[bool | None, Any]:
        v = obs.get(metric)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None, None
        v = float(v)
        return {"<=": v <= th, "<": v < th, ">=": v >= th, ">": v > th}[op], v
    f, v = one(trig["metric"], trig["op"], float(trig["threshold"]))
    if trig.get("also"):
        a = trig["also"]
        f2, _ = one(a["metric"], a["op"], float(a["threshold"]))
        if f2:
            f = True
        elif f is None and f2 is not None:
            f = f2
    return f, v
