"""R14 E (K19, K22, K24): the one findings list and the one count source.

deal_findings(pid) = every failed review rule check (live, review_rules) + every published dd_review_finding row for the
deal (B review, C group and conduct, D stress, I book, Q financial quality, E seeds) + the capacity check (capacity
engine) + the covenant headroom check (economics engine), de-duplicated (a B row that mirrors a live rule check is
kept once), with a result title, a display category (chips), a normalised severity and a cure.

counts is the ONE count source: the Findings header, the category chips and the memo legend read it.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.economics import deal as D
from backend.dealdesk.findings import titles

SEV = {"critical": "critical", "high": "major", "major": "major", "medium": "minor", "minor": "minor", "low": "minor", "info": "info"}
SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}
CATEGORIES = [
    ("capacity", "Capacity"), ("pricing", "Pricing"), ("covenants", "Covenants"), ("financial_quality", "Financial quality"),
    ("conduct", "Conduct and bureau"), ("governance", "Group and governance"), ("track_record", "Track record"),
    ("documents", "Documents"), ("data", "Data accuracy"), ("policy", "Policy"), ("memo", "Memo quality"),
    ("stress", "Stress and monitoring"),
]
CAT_LABEL = dict(CATEGORIES)
ROW_CAT = {"financial_quality": "financial_quality", "adjusted_ratios": "financial_quality", "auditor_quality": "financial_quality",
           "receivables_quality": "financial_quality", "conduct": "conduct", "bureau_reconciliation": "conduct", "data": "data",
           "governance": "governance", "insider_link": "governance", "group_exposure": "governance", "cp": "governance",
           "earlier_conditions": "track_record", "promise": "track_record", "drift": "track_record", "documents": "documents",
           "language": "memo", "precedent": "policy", "stress": "stress", "monitoring": "stress"}
RULE_CAT = {"CONS-07": "pricing", "CONS-05": "covenants", "CONS-06": "covenants", "DATA-05": "conduct", "DATA-06": "conduct",
            "DATA-07": "conduct", "DATA-08": "conduct"}


def _rows(pid: str) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data.store import dd_read
        return dd_read("dd_review_finding", proposal_id=pid)
    except Exception:  # noqa: BLE001
        return []


def _check_cat(c: dict[str, Any]) -> str:
    rid = c.get("rule_id") or ""
    if rid in RULE_CAT:
        return RULE_CAT[rid]
    return {"connected": "governance", "data": "data", "consistency": "data", "policy": "policy"}.get(c.get("category") or "", "policy")


def _row_cat(r: dict[str, Any]) -> str:
    if str(r.get("raised_by") or "") == "Q":
        return "financial_quality"
    cat = str(r.get("category") or "")
    head, _, code = cat.partition(":")
    if head == "cons":
        return RULE_CAT.get(code, "data")
    if code == "BUR-04" or "classified" in str(r.get("title") or "").lower():
        return "governance"
    return ROW_CAT.get(head, "policy")


def _memo_counts(pid: str, checks: list[dict[str, Any]]) -> dict[str, int]:
    """Memo claims with no rule check behind them (unverifiable), the same way the memo view marks lines."""
    try:
        from backend.dealdesk import review_facts as RF
        led = RF.memo_ledger(pid)
    except Exception:  # noqa: BLE001
        return {"unchecked_claim_lines": 0, "claim_lines": 0}
    checked = {lid for c in checks for lid in (c.get("line_ids") or [])}
    claim_lines = [ln for ln in led.get("lines") or [] if ln.get("claim_ids")]
    return {"unchecked_claim_lines": sum(1 for ln in claim_lines if ln["line_id"] not in checked), "claim_lines": len(claim_lines)}


def _finding(**kw: Any) -> dict[str, Any]:
    kw.setdefault("status", "open")
    kw["category_label"] = CAT_LABEL.get(kw["category"], kw["category"])
    return kw


def deal_findings(pid: str, *, with_cures: bool = True) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    from backend.dealdesk.approval.core import deal_checks
    from backend.dealdesk.capacity import capacity
    from backend.dealdesk.economics.core import covenant_headroom
    a = D.analysis(pid, D.structure_terms(pid, "ask")["terms"])
    m = a["metrics"]
    checks = deal_checks(pid)
    out: list[dict[str, Any]] = []
    live_rules = set()
    # 1. live review rule checks (structure-dependent ones re-evaluated on the ask's own metrics)
    for c in checks:
        if c.get("verdict") not in ("contradicted", "exception"):
            continue
        rid = c.get("rule_id")
        live_rules.add(rid)
        out.append(_finding(id=f"R-{c.get('check_id') or rid}", source="review rule", source_relation="rules.json + review_facts",
                            code=rid, category=_check_cat(c), severity=SEV.get(c.get("severity") or "minor", "minor"),
                            verdict=c.get("verdict"), title=titles.for_check(c, m), text=c.get("finding") or "",
                            evidence=[{"source": e.get("source"), "text": e.get("text")} for e in c.get("evidence") or []],
                            policy_ref=c.get("policy_ref") or "", condition=(c.get("condition") or {}).get("what"),
                            doa=(c.get("doa") or {}).get("level")))
    # 2. every published dd_review_finding row for the deal
    for r in _rows(pid):
        cat = str(r.get("category") or "")
        code = cat.split(":", 1)[1] if ":" in cat else ""
        if code and code in live_rules:
            continue  # the live rule check above is the same finding
        out.append(_finding(id=r["finding_id"], source={"B": "review", "C": "group and conduct", "D": "stress", "I": "book",
                                                         "Q": "financial quality"}.get(str(r.get("raised_by") or "")[:1], "seeded"),
                            source_relation="dd_review_finding", code=code or r["finding_id"], category=_row_cat(r),
                            severity=SEV.get(str(r.get("severity") or "medium"), "minor"), verdict=None,
                            title=titles.for_row(r, m), text=r.get("finding_text") or "",
                            evidence=[{"source": f"{r.get('evidence_domain') or 'deal_desk'}.{r.get('evidence_relation')}",
                                       "text": r.get("claim_text") or "", "value": r.get("evidence_value"), "unit": r.get("evidence_unit")}]
                            if r.get("evidence_relation") else [],
                            policy_ref="", condition=r.get("condition_id"), status=r.get("status") or "open",
                            review_point=r.get("review_point"), raised_by=r.get("raised_by")))
    # 3. capacity (critical when the ask is above it)
    cap = capacity(pid, "ask")
    if not cap["within"]:
        out.append(_finding(id=f"E14-{pid}-CAPACITY", source="capacity engine", source_relation="dd_financials_detail / dd_obligor_financials",
                            code="CAPACITY", category="capacity", severity=cap["severity"], verdict="contradicted",
                            title=cap["finding_title"], text=cap["formula"],
                            evidence=[{"source": "backend.dealdesk.capacity", "text": cap["formula"]}], policy_ref="Credit Policy: facility sizing",
                            condition=None, capacity=cap["capacity_sar_mn"], ask=cap["ask_sar_mn"]))
    # 4. covenant headroom at base (breach: major; thin headroom under 5%: major, it breaks under any shock)
    for cv in covenant_headroom(pid, a):
        hr = cv.get("headroom_pct")
        if hr is None or (hr >= 5 and not cv["breached"]):
            continue
        if "CONS-05" in live_rules and "dscr" in cv["covenant"].lower():
            continue
        if "CONS-06" in live_rules and "ebitda" in cv["covenant"].lower():
            continue
        title = (f"Covenant breached at base: {cv['covenant']} {cv['value']:.2f}x vs {cv['threshold']:.2f}x" if cv["breached"] else
                 f"Covenant headroom thin: {cv['covenant']} {cv['value']:.2f}x vs {cv['threshold']:.2f}x ({hr:.1f}% headroom)")
        out.append(_finding(id=f"E14-{pid}-COV-{cv['covenant'][:12].replace(' ', '').replace('/', '')}", source="covenant headroom",
                            source_relation="engine.analyse (dscr_post, debt_ebitda_post) + proposal covenants", code="COVENANT",
                            category="covenants", severity="major", verdict="exception", title=title, text=cv["text"],
                            evidence=[{"source": "engine.analyse", "text": cv["text"]}], policy_ref="", condition=None))
    seen: dict[str, int] = {}
    for f in out:
        seen[f["title"]] = seen.get(f["title"], 0) + 1
    for f in out:  # identical titles (one rule, several parties): name the party from the finding's first clause
        if seen[f["title"]] > 1 and f.get("text"):
            f["title"] = f"{f['title']}: {titles._first_clause(f['text'], 64)}"
    out.sort(key=lambda f: (0 if f["status"] == "open" else 1, SEV_ORDER.get(f["severity"], 4), [k for k, _ in CATEGORIES].index(f["category"])
                            if f["category"] in CAT_LABEL else 99, f["id"]))
    if with_cures:
        from backend.dealdesk.findings.cures import cure_for
        for f in out:
            f["cure"] = cure_for(pid, f, cap)
            f["curable"] = f["cure"]["kind"] != "not_curable"
    open_ = [f for f in out if f["status"] == "open"]
    by_sev = {s: sum(1 for f in open_ if f["severity"] == s) for s in SEV_ORDER}
    by_cat = {k: sum(1 for f in open_ if f["category"] == k) for k, _ in CATEGORIES}
    verdicts = {v: sum(1 for c in checks if c.get("verdict") == v) for v in ("supported", "contradicted", "exception", "unverifiable")}
    mc = _memo_counts(pid, checks)
    verdicts["unverifiable"] += mc["unchecked_claim_lines"]
    counts = {"total": len(open_), "by_severity": by_sev, "by_category": by_cat, "checks": verdicts,
              "resolved": len(out) - len(open_), "memo": mc,
              "line": f"{len(open_)} open findings: {by_sev['critical']} critical, {by_sev['major']} major, {by_sev['minor']} minor"
                      + (f", {by_sev['info']} for information" if by_sev["info"] else ""),
              "checks_line": (f"{verdicts['supported']} supported · {verdicts['contradicted']} contradicted · {verdicts['exception']} exception"
                              f" · {verdicts['unverifiable']} unverifiable")}
    chips = [{"key": "all", "label": "All", "count": len(open_)}] + [
        {"key": k, "label": lab, "count": by_cat[k]} for k, lab in CATEGORIES if by_cat[k]]
    from backend.dealdesk.findings.verdict import verdict
    if not with_cures:  # the verdict counts cures as unknown (no "not curable" tail)
        for f in out:
            f.setdefault("cure", {"kind": "unknown"})
    return {"proposal_id": pid, "findings": out, "counts": counts, "chips": chips, "verdict": verdict(pid, out, cap, m),
            "source": "review_rules (live) + dd_review_finding + backend.dealdesk.capacity + covenant headroom"}
