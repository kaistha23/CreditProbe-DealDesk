"""R14 E (K19, K22, K24): findings, verdict, counter-offer with cures, "why does the ask fail?", structure evaluation.

    from backend.dealdesk.findings import deal_findings, counter_offer, why_ask_fails, evaluate_structure
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.findings.collect import deal_findings  # noqa: F401 - public API
from backend.dealdesk.findings.counter import counter_offer  # noqa: F401 - public API
from backend.dealdesk.findings.why import answer_markdown, why_ask_fails  # noqa: F401 - public API


def evaluate_structure(pid: str, structure: Any = None, label: str | None = None) -> dict[str, Any]:
    """One row of the structure set (session f): base RAROC and SVA (lifetime, labelled), DSCR, covenant headroom,
    capacity check, approval and whether it fails before stress (with the reasons)."""
    from backend.dealdesk.approval import approval_authority
    from backend.dealdesk.capacity import capacity
    from backend.dealdesk.economics import deal as D
    from backend.dealdesk.economics.core import covenant_headroom
    pid = D.resolve_id(pid)
    st = D.structure_terms(pid, structure)
    a = D.analysis(pid, st["terms"])
    m = a["metrics"]
    cov = covenant_headroom(pid, a)
    cap = capacity(pid, st["terms"])
    appr = approval_authority(pid, st["terms"])
    hard = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    fails = []
    if not m["clears_hurdle"]:
        fails.append(f"RAROC {m['lifetime_raroc']:.2%} < {m['hurdle']:.1%}")
    for c in hard:
        fails.append(f"{c['label']} breached (hard limit)")
    for c in cov:
        if c["breached"]:
            fails.append(f"{c['covenant']} covenant breached ({c['value']:.2f}x vs {c['threshold']:.2f}x)")
    if not cap["within"]:
        fails.append(f"Above capacity (SAR {cap['ask_sar_mn']:,.1f}m vs SAR {cap['capacity_sar_mn']:,.1f}m)")
    return {"proposal_id": pid, "key": st["key"], "label": label or st["label"], "terms": st["terms"],
            "raroc": m["lifetime_raroc"], "hurdle": m["hurdle"], "sva": m["sva"], "sva_basis": "lifetime",
            "dscr": m["dscr_post"], "debt_ebitda": m["debt_ebitda_post"], "covenant_headroom": cov,
            "capacity": {"method": cap["method"], "capacity_sar_mn": cap["capacity_sar_mn"], "ask_sar_mn": cap["ask_sar_mn"],
                         "within": cap["within"]},
            "approval": {"level": appr["level"], "rank": appr["rank"], "rule": appr["rule"]},
            "clears": not fails, "fails_base_reasons": fails, "fails_before_stress": bool(fails)}
