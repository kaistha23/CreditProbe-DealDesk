"""R14 E (K24): "Why does the ask fail?" read from ALL findings, capacity, covenants, pricing, limits and approval —
never "fails on price, not on limits" while a critical finding, a capacity gap or a thin covenant stands."""
from __future__ import annotations

from typing import Any

from backend.dealdesk.economics import deal as D


def _mn(x: Any) -> str:
    return f"SAR {x:,.1f}m" if isinstance(x, (int, float)) else "n/a"


def why_ask_fails(pid: str) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    from backend.dealdesk.approval import approval_authority
    from backend.dealdesk.capacity import capacity
    from backend.dealdesk.economics.core import covenant_headroom
    from backend.dealdesk.findings.collect import deal_findings
    st = D.structure_terms(pid, "ask")
    a = D.analysis(pid, st["terms"])
    m = a["metrics"]
    fs = deal_findings(pid)
    cap = capacity(pid, "ask")
    appr = approval_authority(pid, "ask")
    cov = covenant_headroom(pid, a)
    open_ = [f for f in fs["findings"] if f["status"] == "open"]
    crit = [f for f in open_ if f["severity"] == "critical"]
    maj = [f for f in open_ if f["severity"] == "major"]
    reasons: list[str] = []
    lines: list[dict[str, Any]] = []
    if not cap["within"]:
        reasons.append("capacity")
        lines.append({"kind": "capacity", "severity": "critical",
                      "text": f"Capacity: the ask of {_mn(cap['ask_sar_mn'])} is above the {cap['method_label'].lower()} of "
                              f"{_mn(cap['capacity_sar_mn'])}. {cap['formula']}.", "source": "backend.dealdesk.capacity"})
    if not m["clears_hurdle"]:
        reasons.append("price")
        from backend.dealdesk import engine
        try:
            be = engine.breakeven_margin(D.proposal(pid), st["terms"])
        except Exception:  # noqa: BLE001
            be = None
        lines.append({"kind": "pricing", "severity": "major",
                      "text": f"Price: lifetime RAROC {m['lifetime_raroc']:.1%} against the {m['hurdle']:.1%} hurdle (SVA {_mn(m['sva'])}, lifetime)"
                              + (f"; breakeven margin {be:,.0f} bps against {int(st['terms']['margin_bps'])} bps proposed" if be else "") + ".",
                      "source": "engine.analyse"})
    for c in cov:
        if c["breached"] or (c.get("headroom_pct") is not None and c["headroom_pct"] < 5):
            reasons.append("covenant")
            lines.append({"kind": "covenant", "severity": "major", "text": f"Covenant: {c['text']} — any shock breaks it at base.",
                          "source": "engine.analyse + proposal covenants"})
    for f in crit:
        if f["category"] == "capacity":
            continue
        reasons.append(f["category"])
        lines.append({"kind": "finding", "severity": "critical", "text": f"{f['title']}.", "finding_id": f["id"],
                      "cure": (f.get("cure") or {}).get("text"), "source": f.get("source_relation")})
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for f in maj:
        if f["category"] in ("pricing", "covenants"):
            continue
        by_cat.setdefault(f["category_label"], []).append(f)
    for lab, xs in by_cat.items():
        lines.append({"kind": "findings", "severity": "major",
                      "text": f"{lab}: {len(xs)} major finding{'s' if len(xs) != 1 else ''} — " + "; ".join(x["title"] for x in xs[:3])
                              + (f"; and {len(xs) - 3} more" if len(xs) > 3 else "") + ".", "source": "dd_review_finding + review rules"})
    hard = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    soft = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
    if hard or soft:
        lines.append({"kind": "limits", "severity": "critical" if hard else "major",
                      "text": "Limits: " + "; ".join(f"{c['label']} ({c['kind']}) breached" for c in hard + soft) + ".",
                      "source": "constraints.evaluate"})
    else:
        lines.append({"kind": "limits", "severity": "info", "text": "Limits: every hard and soft risk-appetite limit passes on the ask — "
                                                                     "the failures above are not limit failures.", "source": "constraints.evaluate"})
    lines.append({"kind": "approval", "severity": "info", "text": f"Approval: {appr['level']} — {appr['rule']}.", "source": appr["source"]})
    parts = []
    if "capacity" in reasons:
        parts.append("capacity")
    if crit:
        parts.append(f"{len(crit)} critical finding{'s' if len(crit) != 1 else ''}")
    if "price" in reasons:
        parts.append("price")
    if "covenant" in reasons:
        parts.append("covenant headroom")
    if maj:
        parts.append(f"{len(maj)} major findings")
    head = ("The ask fails on " + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] + "."
            if parts else "The ask does not fail: no critical or major finding, within capacity and above the hurdle.")
    return {"proposal_id": pid, "headline": head, "lines": lines, "verdict": fs["verdict"], "counts": fs["counts"],
            "sources": sorted({str(x.get("source")) for x in lines if x.get("source")})}


def answer_markdown(pid: str) -> str:
    """The same answer as markdown (for the deal thread's deterministic writer)."""
    w = why_ask_fails(pid)
    out = [f"**{w['headline']}**", ""]
    for ln in w["lines"]:
        tag = {"critical": "Critical", "major": "Major"}.get(ln["severity"], "")
        out.append(f"- {('**' + tag + '** · ') if tag else ''}{ln['text']}" + (f" Cure: {ln['cure']}" if ln.get("cure") else ""))
    out += ["", f"{w['counts']['line']} (findings engine: review rules, dd_review_finding, capacity and covenants)."]
    return "\n".join(out)
