"""Run the existing Deal Desk flow on the deal the business request created, step by step, timed, nothing lost on error.

    steps = run_all(pid, doc)    # [{key, label, status, seconds, plain_words, headline, data}]

The engines are the ones every Deal Desk deal uses (one engine per fact, N2): proposal check (the request against the
bank's data), review, analysis (RAROC, approval authority, capacity), structure and optimise, stress over the structures,
stress-proofing, recommendation. A step that fails says why in plain words and the next steps still run.
"""
from __future__ import annotations

import time
from typing import Any, Callable

STEPS = [("check", "Proposal check: the request against the bank's data"), ("review", "Review"), ("analysis", "Analysis: RAROC, approval, capacity"),
         ("structure", "Structure and optimise"), ("stress", "Stress over the structures"), ("proof", "Stress-proof"),
         ("recommendation", "Recommendation")]


def _f(x: Any, d: int = 1) -> str:
    try:
        return f"{float(x):,.{d}f}"
    except (TypeError, ValueError):
        return "–"


def pct(x: Any) -> float | None:
    """A rate as a percentage: the engines return fractions (0.1406), some views percentages (14.06)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v * 100.0, 4) if abs(v) <= 1.5 else round(v, 4)


def _check(pid: str, doc: dict[str, Any]) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.proposal_check import engine as PC
    from backend.dealdesk.proposal_check import store as PS
    res = PC.run(pid, doc)
    try:
        PS.remember(res)
        PS.publish(res["rows"])
    except Exception:  # noqa: BLE001 - the check result stays in the case either way
        pass
    data = {k: res.get(k) for k in ("score", "grade", "headline", "critical", "by_category", "sections_present", "run_id")}
    data["defects"] = [{k: f.get(k) for k in ("severity", "title", "evidence", "evidence_relation", "query", "section_key", "check")} for f in res.get("defects") or []]
    data["observations"] = [{k: f.get(k) for k in ("severity", "title", "evidence", "evidence_relation", "section_key", "check")} for f in res.get("observations") or []]
    data["queries"] = res.get("queries") or []
    pw = [f"The request was checked line by line against the bank's own data: {len(data['defects'])} defects "
          f"({res.get('critical', 0)} critical) and {len(data['observations'])} observations.",
          "Each defect is a query to the RM in the feedback brief, with the bank's evidence beside it."]
    return data, pw, res.get("headline") or ""


def _review(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk import review_workspace as RW
    r = RW.review(pid)
    a = r.get("answer") or {}
    fnd = r.get("findings") or []
    data = {"decision": a.get("decision"), "tone": a.get("tone"), "headline": a.get("headline"), "counts": a.get("counts"),
            "approval": (r.get("doa") or {}).get("level"),
            "findings": [{k: f.get(k) for k in ("severity", "title", "text", "rule_id", "category", "finding") if k in f} for f in fnd][:40],
            "conditions": [c if isinstance(c, str) else (c.get("text") or c.get("condition") or "") for c in (r.get("conditions") or [])][:30]}
    pw = [f"Review against the bank's credit policy and rule book: {a.get('decision') or 'no decision'}.",
          f"{len(fnd)} findings; approval level {data['approval'] or 'not set'}."]
    return data, pw, a.get("headline") or ""


def _analysis(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.economics import api as EA
    s = EA.summary_of(pid)
    rr, ap, cap, pd = s.get("raroc") or {}, s.get("approval") or {}, s.get("capacity") or {}, s.get("pd") or {}
    data = {"raroc_pct": pct(rr.get("lifetime", rr.get("raroc_pct", rr.get("value")))), "hurdle_pct": pct(rr.get("hurdle")),
            "raroc_one_year_pct": pct(rr.get("one_year")), "sva_mn": (s.get("sva") or {}).get("lifetime") if isinstance(s.get("sva"), dict) else s.get("sva"),
            "pd_12m_pct": pct(pd.get("pd_12m")), "pd_master_pct": pct(pd.get("master_scale_12m")), "approval": ap.get("level"), "approval_rule": ap.get("rule"),
            "capacity_mn": cap.get("capacity_sar_mn"), "ask_mn": cap.get("ask_sar_mn"), "within_capacity": cap.get("within"),
            "findings": (s.get("findings") or {}).get("counts")}
    head = (f"RAROC {_f(data['raroc_pct'])}% against a {_f(data['hurdle_pct'])}% hurdle; approval {data['approval'] or '–'}; "
            f"capacity SAR {_f(data['capacity_mn'])}m for an ask of SAR {_f(data['ask_mn'])}m.")
    pw = ["The deal's return on risk capital, who must approve it and how much the customer can carry, from the same engines as every deal.", head]
    return data, pw, head


def _structure(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.stressproof import structures as ST
    s = ST.structure_set(pid)
    rows = [{k: r.get(k) for k in ("key", "label", "clears_hurdle", "sva", "dscr", "approval", "recommendable", "not_recommendable_reason")}
            | {"raroc": pct(r.get("raroc")), "hurdle": pct(r.get("hurdle"))}
            | {"terms": {k: (r.get("terms") or {}).get(k) for k in ("amount", "tenor_years", "margin_bps", "commission_bps", "cash_margin_pct", "amortisation")}}
            for r in s.get("rows") or []]
    rec = next((r for r in rows if r["key"] == "recommended"), None)
    head = (f"Recommended structure: {rec['label']} (RAROC {_f(rec.get('raroc'))}%)." if rec else "No structure clears the bank's tests.")
    return {"rows": rows, "selected": s.get("selected")}, list(s.get("plain_words") or [])[:3] or [head], head


def _stress(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.stressproof import matrix as MX
    m = MX.run(pid)
    out = []
    for st in m.get("structures") or []:
        out.append({"key": st.get("key"), "label": st.get("label"), "status": st.get("status"), "survives_up_to": st.get("survives_up_to"),
                    "verdict": st.get("verdict"), "tier": st.get("tier"), "first_break": _fb(st),
                    "cells": [{k: c.get(k) for k in ("severity", "passes", "breaking", "worst_raroc", "min_dscr")} for c in st.get("cells") or []]})
    head = "; ".join(f"{s['label']}: survives up to {s['survives_up_to'] or 'none'}" for s in out[:2])
    return {"structures": out}, list(m.get("plain_words") or [])[:3] or [head], head


def _fb(st: dict[str, Any]) -> str:
    for c in st.get("cells") or []:
        fb = c.get("first_break")
        if fb:
            return fb if isinstance(fb, str) else str(fb.get("text") or fb.get("scenario") or fb)
    return ""


def _proof(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.stressproof import solver as SV
    try:
        r = SV.proof(pid, by="credit response", publish=True)
    except SV.ProofError as e:
        return {"survives": False, "error": str(e)}, [f"Stress-proofing found no structure that survives: {e}"], str(e)
    pr = r.get("proof") or {}
    data = {"survives": r.get("survives"), "new_key": r.get("new_key"), "label": r.get("label"),
            "changes": [c if isinstance(c, str) else (c.get("text") or str(c)) for c in r.get("changes") or []], "uncured": r.get("uncured"),
            "raroc_before_pct": pr.get("raroc_before_pct"), "raroc_after_pct": pr.get("raroc_after_pct"), "cost_text": pr.get("cost_text"),
            "interpretation": pr.get("interpretation")}
    head = ("Stress-proofed: " + "; ".join(data["changes"][:4])) if data["changes"] else (pr.get("interpretation") or "No change needed.")
    return data, list(r.get("plain_words") or [])[:3] or [head], head


def _recommendation(pid: str) -> tuple[dict[str, Any], list[str], str]:
    from backend.dealdesk.stressproof import recommendation as RC
    r = RC.build(pid)
    d = r.get("decision") or {}
    data = {"decision": d.get("label"), "tone": d.get("tone"), "why": d.get("why"), "points": d.get("points") or [],
            "approval": (r.get("approval") or {}).get("level"), "approval_rule": (r.get("approval") or {}).get("rule"),
            "structure": {k: (r.get("structure") or {}).get(k) for k in ("key", "label", "sva", "dscr", "capacity")}
            | {"raroc": pct((r.get("structure") or {}).get("raroc")), "hurdle": pct((r.get("structure") or {}).get("hurdle"))},
            "structure_terms": (r.get("structure") or {}).get("terms"),
            "conditions_precedent": [c if isinstance(c, str) else (c.get("text") or "") for c in r.get("conditions_precedent") or []],
            "covenants": [c if isinstance(c, str) else (c.get("text") or c.get("label") or "") for c in r.get("covenants") or []],
            "monitoring": r.get("monitoring"), "stress": r.get("stress"), "strengths": r.get("strengths") or [], "risks": r.get("risks") or []}
    return data, list(r.get("plain_words") or [])[:3] or [d.get("why") or ""], f"{d.get('label')}: {d.get('why')}"


RUNNERS: dict[str, Callable[..., tuple[dict[str, Any], list[str], str]]] = {
    "check": _check, "review": _review, "analysis": _analysis, "structure": _structure, "stress": _stress, "proof": _proof,
    "recommendation": _recommendation}


def run_step(key: str, pid: str, doc: dict[str, Any] | None = None) -> dict[str, Any]:
    label = dict(STEPS)[key]
    t0 = time.perf_counter()
    try:
        data, pw, head = RUNNERS[key](pid, doc) if key == "check" else RUNNERS[key](pid)
        status = "done"
    except Exception as e:  # noqa: BLE001 - one engine's problem never stops the response
        data, pw, head, status = {"error": f"{type(e).__name__}: {e}"[:400]}, [f"{label} could not run on this deal ({type(e).__name__}); "
                                                                                 "the response says so where it would use it."], "", "error"
    return {"key": key, "label": label, "status": status, "seconds": round(time.perf_counter() - t0, 2), "plain_words": [p for p in pw if p],
            "headline": head, "data": data}


def run_all(pid: str, doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [run_step(k, pid, doc) for k, _ in STEPS]
