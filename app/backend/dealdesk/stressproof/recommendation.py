"""The Recommendation step (K24, K25 (2)-(3)): never blank. It is built on the selected structure (default the Review
counter-proposal, and it says so) and shows, without a click: the credit division's decision as numbered points with
the approval authority and its rule; key strengths and key risks from the SWOT, each sourced; every critical and major
finding with its cure (condition precedent, security, explanation) or "not curable by structure"; conditions precedent
prior to limit loading; covenants with headroom; the monitoring tier and its triggers; owners and dates; and the
severity the structure was stress-proofed to. Deterministic writer (N4)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.stressproof import adapters as AD
from backend.dealdesk.stressproof import matrix as MX
from backend.dealdesk.stressproof import structures as ST

SEV_RANK = {"critical": 0, "high": 1, "major": 1, "medium": 2, "minor": 3, "low": 3, "info": 4}
SVA_WORD = {"lifetime": "over the deal's life", "one_year": "in year one"}
TODAY = dt.date.fromisoformat(getattr(paths, "AS_OF_DATE", "2026-10-18"))


def _d(days: int) -> str:
    return (TODAY + dt.timedelta(days=days)).isoformat()


def _cure(f: dict[str, Any], sel: dict[str, Any]) -> tuple[str, str]:
    """(kind, text): how a finding is cured on the selected structure, or that it is not curable by structure."""
    cat = (f.get("category") or "").split(":")[0]
    title = (f.get("title") or "").lower()
    if cat == "documents" or "not provided" in title or "expired" in title:
        return "condition_precedent", "Condition precedent: the document, valid, before limit loading."
    if "pricing" in title or "hurdle" in title or cat == "cons":
        return ("cured_by_structure", f"Cured by the structure: {sel['label']} prices at RAROC {sel['raroc'] * 100:.2f}% against the "
                f"{sel['hurdle'] * 100:.1f}% hurdle.") if sel["clears_hurdle"] else ("open", "Not cured: the selected structure is still below the hurdle.")
    if "perfect" in title or "security" in title or "guarantee" in title or cat == "collateral":
        return "condition_precedent", "Condition precedent: security perfected and legal opinion on file before limit loading."
    if "cheque" in title or "conduct" in title or cat in ("data", "conduct"):
        return ("explanation", "Explanation required from the RM and the client; not curable by structure. "
                "Watch: no further returned cheques (monthly conduct check).")
    if "audit" in title or cat == "auditor_quality":
        return "explanation", "Explanation required: auditor's qualification addressed in writing; not curable by structure."
    if cat in ("bureau_reconciliation",) or "bureau" in title:
        return "condition_precedent", "Condition precedent: other-bank limits reconciled with the bureau (SIMAH) before limit loading."
    if "related" in title or "connected" in title or cat in ("governance", "insider_link"):
        return "explanation", "Explanation required and accepted by Credit; not curable by structure."
    if "capacity" in title or "leverage" in title or cat == "adjusted_ratios":
        cap = sel["capacity"]
        return (("cured_by_structure", f"Within capacity on {sel['label']}: funded SAR {cap['ask_sar_mn']:,.1f}m against SAR {cap['capacity_sar_mn']:,.1f}m.")
                if cap["passes"] else ("open", f"Not cured: funded SAR {cap['ask_sar_mn']:,.1f}m above capacity SAR {cap['capacity_sar_mn']:,.1f}m."))
    return "explanation", "Explanation required before committee."


def findings(pid: str, rv: dict[str, Any] | None, sel: dict[str, Any]) -> list[dict[str, Any]]:
    """Every critical and major finding of the deal, with its cure judged on the selected structure. Session E's findings
    engine (every dd_review_finding + live rules + capacity + covenants, one count source) when present, else the Review
    rules and dd_review_finding read here."""
    ef = AD.deal_findings(pid)
    if ef and ef.get("findings") is not None:
        return _from_engine(ef, sel)
    from backend.dealdesk.data import store
    items: list[dict[str, Any]] = []
    for f in (rv or {}).get("findings") or []:
        items.append({"title": f.get("finding") or f["title"], "severity": f["severity"], "category": f.get("category", ""),
                      "source": f"Review rule {f['rule_id']} ({f.get('policy_ref') or 'the review rule book'})", "relation": "review rules"})
    try:
        rows = store.dd_read("dd_review_finding", proposal_id=pid)
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        if r.get("status") in ("resolved", "superseded"):
            continue
        items.append({"title": r["title"], "severity": r["severity"], "category": r.get("category", ""),
                      "source": f"dd_review_finding {r['finding_id']}", "relation": "dd_review_finding", "text": r.get("finding_text") or ""})
    seen, out = set(), []
    for it in sorted(items, key=lambda x: (SEV_RANK.get(x["severity"], 5), x["title"])):
        k = it["title"].lower()
        if k in seen or SEV_RANK.get(it["severity"], 5) > 1:
            continue
        seen.add(k)
        kind, text = _cure(it, sel)
        out.append({**it, "severity": "critical" if it["severity"] == "critical" else "major", "cure_kind": kind, "cure": text})
    return out


E_KIND = {"cp": "condition_precedent", "security": "condition_precedent", "covenant": "covenant", "explanation": "explanation",
          "governance": "explanation", "not_curable": "not_curable", "structure": "cured_by_structure"}


def _from_engine(ef: dict[str, Any], sel: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for f in ef["findings"]:
        if f.get("status") != "open" or f.get("severity") not in ("critical", "major"):
            continue
        cu = f.get("cure") or {}
        kind = E_KIND.get(cu.get("kind") or "", "explanation")
        text = cu.get("text") or "Explanation required before committee."
        if f.get("curable") is False:
            kind = "not_curable"
            text = (text.rstrip(".") + ". Not curable by structure.") if "not curable" not in text.lower() else text
        if kind == "cured_by_structure":
            cat = f.get("category")
            if cat == "capacity":
                cap = sel["capacity"]
                if not cap["passes"]:
                    kind, text = "open", f"Not cured on {sel['label']}: SAR {cap['ask_sar_mn']:,.1f}m against capacity SAR {cap['capacity_sar_mn']:,.1f}m."
                else:
                    text = f"Cured on {sel['label']}: SAR {cap['ask_sar_mn']:,.1f}m within capacity SAR {cap['capacity_sar_mn']:,.1f}m ({cap['method'].lower()})."
            elif cat == "pricing" or f.get("code") == "CONS-07":
                if sel["clears_hurdle"]:
                    text = f"Cured on {sel['label']}: RAROC {sel['raroc'] * 100:.2f}% against the {sel['hurdle'] * 100:.1f}% hurdle."
                else:
                    kind, text = "open", f"Not cured on {sel['label']}: RAROC {sel['raroc'] * 100:.2f}% below the {sel['hurdle'] * 100:.1f}% hurdle."
            elif sel["key"] == "ask":
                kind, text = "open", "Needs the counter-offer: " + text
        out.append({"title": f["title"], "severity": f["severity"], "category": f.get("category_label") or f.get("category", ""),
                    "source": f"{f.get('source', 'findings engine')} ({f.get('source_relation') or f.get('id')})", "relation": f.get("source_relation") or "",
                    "id": f.get("id"), "cure_kind": kind, "cure": text, "owner": cu.get("owner"), "when": cu.get("when")})
    return out


def _swot(pid: str) -> dict[str, list[dict[str, Any]]]:
    try:
        from backend.dealdesk.group import api as G
        sw = G.get_swot(pid)["swot"]["points"]
    except Exception:  # noqa: BLE001
        return {"strengths": [], "risks": []}

    def src(pt: dict[str, Any]) -> str:
        ev = pt.get("evidence") or []
        return ", ".join(sorted({f"{e.get('domain')}.{e.get('relation')}" for e in ev})) or "SWOT"
    st = [{"text": x["text"], "source": src(x), "id": x.get("id")} for x in sw if x["quadrant"] == "strength"][:4]
    rk = [{"text": x["text"], "source": src(x), "id": x.get("id")} for x in sw if x["quadrant"] in ("weakness", "threat")][:4]
    return {"strengths": st, "risks": rk}


def build(pid: str) -> dict[str, Any]:
    s = ST.structure_set(pid)
    p = ST.deal(pid)
    rv = ST.review(pid)
    sel = next(r for r in s["rows"] if r["selected"])
    t = sel["terms"]
    ccy = t["currency"]
    fnd = findings(pid, rv, sel)
    crit_open = [f for f in fnd if f["severity"] == "critical" and f["cure_kind"] in ("explanation", "open", "not_curable")]
    # stress on the selected structure (the ladder's verdict and tier)
    st = MX.one(p, sel, force=True, reg=AD.regime())
    proofed = next((r for r in ST.saved(pid) if r["structure_key"] == sel["key"] and r["role"] == "stress_proofed"), None)
    proof_sev = None
    if proofed:
        lab = proofed["label"]
        proof_sev = lab[lab.find("(") + 1:lab.find(")")] if "(" in lab else None
    ap = sel["approval"]
    # decision
    if not sel["recommendable"]:
        decision, tone = "Do not approve as proposed", "negative"
        why = sel["not_recommendable_reason"]
    elif crit_open:
        decision, tone = ("Counter-offer, subject to conditions" if sel["key"] != "ask" else "Approve with conditions"), "warning"
        nc = sum(1 for f in crit_open if f["cure_kind"] == "not_curable")
        why = (f"{len(crit_open)} critical finding{'s' if len(crit_open) > 1 else ''} need an explanation before limit loading"
               + (f" ({nc} not curable by structure: accepted only with the committee's explicit consent)" if nc else ""))
    elif sel["key"] != "ask":
        decision, tone, why = "Counter-offer", "warning", f"Approve on {sel['label']} instead of the ask"
    else:
        decision, tone, why = "Approve", "positive", "The ask clears the hurdle, every hard limit, capacity and the review"
    cps = []
    for c in sel.get("conditions_precedent") or []:
        cps.append({"text": c if isinstance(c, str) else str(c), "owner": "Credit Administration", "due": "Prior to limit loading"})
    for f in fnd:
        if f["cure_kind"] == "condition_precedent":
            cps.append({"text": f"{f['title']}: {f['cure'].replace('Condition precedent: ', '')}", "owner": "RM: " + (p.get("rm") or "relationship manager"),
                        "due": "Prior to limit loading"})
    seen = set()
    cps = [c for c in cps if not (c["text"] in seen or seen.add(c["text"]))]
    covs = [{"type": c["type"], "threshold": c["threshold"], "today": c.get("value"), "headroom": c.get("headroom"), "status": c["status"]}
            for c in sel["covenants_base"]]
    tier = st.get("tier") if st.get("stressed") else "High"
    trig = []
    try:
        lr = MX.ladder_for(p, sel)
        trig = lr["tier"]["triggers"]
        tier = lr["tier"]["tier"]
        review_m = lr["tier"]["review_frequency_months"]
    except Exception:  # noqa: BLE001
        review_m = 3
    sw = _swot(pid)
    amount = f"{ccy} {t['amount']:,.1f}m"
    fee = f", upfront fee {t['upfront_fee_bps']:.0f} bps" if t.get("upfront_fee_bps") else ""
    price = (f"{'SOFR' if ccy == 'USD' else 'SAIBOR'} + {t['margin_bps']:.0f} bps" if t["facility_type"] not in ("performance_lg", "advance_payment_lg", "bid_bond", "lc")
             and float(t.get("funded_share_pct") or 0) > 0 else "") + (f", commission {t['commission_bps']:.0f} bps" if t.get("commission_bps") else "")
    points = [
        f"{decision}: {why}.",
        f"Facility: {amount} {t['facility_type'].replace('_', ' ')}, {t['tenor_years']} year{'s' if t['tenor_years'] != 1 else ''}, "
        f"{price.strip(', ') or 'pricing as per the term sheet'}{fee}"
        f" ({sel['label']}: RAROC {sel['raroc'] * 100:.2f}% against the {sel['hurdle'] * 100:.1f}% hurdle, SVA SAR {(0.0 if abs(sel['sva']) < 0.005 else sel['sva']):,.2f}m {SVA_WORD.get(sel['sva_basis'], '')}).",
        f"Approval: {ap['level']} ({ap.get('rule') or 'Delegation of Authority'}).",
        f"Conditions precedent prior to limit loading: {len(cps)}." if cps else "No condition precedent beyond the standard documentation.",
        "Covenants: " + "; ".join(f"{c['type']} {c['threshold']:.2f}x (today {c['today']:.2f}x, headroom {c['headroom'] * 100:.0f}%)"
                                  for c in covs if isinstance(c.get("today"), (int, float)) and c.get("headroom") is not None) + "." if covs else "No financial covenant.",
        f"Monitoring tier {tier}, review every {review_m} months; {len(trig)} named trigger{'s' if len(trig) != 1 else ''}.",
    ]
    if proof_sev:
        points.append(f"Stress-proofed to {proof_sev}: survives every applicable {proof_sev} scenario; severe is monitored.")
    elif st.get("stressed"):
        up = st["survives_up_to"]
        points.append(("Stress: does not survive a mild scenario" if up == "none" else f"Stress: survives up to {up}")
                      + (f"; breaks first at {MX.first_break(st)}." if MX.first_break(st) else "."))
    owners = [{"what": "Conditions precedent satisfied", "owner": "RM: " + (p.get("rm") or "relationship manager"), "due": _d(30)},
              {"what": "Limit loading after the CP checklist", "owner": "Credit Administration", "due": _d(35)},
              {"what": "First monitoring review", "owner": "Credit Risk monitoring", "due": _d(30 * int(review_m or 3))}]
    plain = [f"This is the credit division's recommendation for {p['obligor']['name']}, on the structure selected: {sel['label']}.",
             f"Decision: {decision.lower()}; it needs {ap['level']}.",
             (f"{len(crit_open)} critical issue{'s' if len(crit_open) > 1 else ''} cannot be fixed by the structure and need an explanation first."
              if crit_open else f"{len(fnd)} issues are listed with how each is cured."),
             "Prepare the credit proposal or the committee paper from here; ask questions below."]
    return {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {"key": sel["key"], "label": sel["label"], "role": sel["role"],
            "origin": sel["origin"], "terms": t, "raroc": sel["raroc"], "hurdle": sel["hurdle"], "sva": sel["sva"], "sva_label": sel["sva_label"],
            "dscr": sel["dscr"], "capacity": sel["capacity"], "recommendable": sel["recommendable"]},
            "default_note": s["default_note"], "decision": {"label": decision, "tone": tone, "why": why, "points": points},
            "approval": ap, "strengths": sw["strengths"], "risks": sw["risks"], "findings": fnd, "conditions_precedent": cps,
            "covenants": covs, "monitoring": {"tier": tier, "review_frequency_months": review_m, "triggers": trig},
            "owners": owners, "proofed_to": proof_sev, "stress": {"survives_up_to": st.get("survives_up_to"), "first_break": MX.first_break(st)},
            "plain_words": plain, "as_of": paths.AS_OF}
