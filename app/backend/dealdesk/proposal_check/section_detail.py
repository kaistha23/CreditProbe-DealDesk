"""R15 b (L10): every section row of the proposal check opens its detail.

For each of the 20 bank-form sections: what the bank form requires there (PROPOSAL_ANATOMY, one plain line), what the RM's
paper contains (quoted, first lines), each check run on it with its result and evidence (the Data Domains source), why it
scored what it did, the queries to the RM, and why a section does not apply. Plus the one-line summary at the top
("6 of 20 sections present; 11 missing; worst: Facilities, T&Cs, Bureau"). Deterministic; reads only the check result and
the parsed document.
"""
from __future__ import annotations

from typing import Any

#: what the bank form requires in each section (docs/v5/house_style/PROPOSAL_ANATOMY.md, in one plain line each)
REQUIRES = {
    "header": "Customer, CIF, group, RM, branch, sector, rating, request type and date: the identity block on every page.",
    "action": "What the committee is asked to approve: new, renewal or amendment, the total limit and the approval level.",
    "facilities": "Every limit line: facility type, amount, currency, tenor, pricing, purpose, existing versus proposed and outstanding.",
    "security": "Collateral, guarantees and support with values, valuation dates and coverage, plus the covenant thresholds.",
    "terms": "Terms and conditions per limit: conditions precedent, covenants with test dates and cure periods, pricing triggers.",
    "group_exposure": "Total group exposure with the bank after the deal, connected parties and bank and trade references.",
    "background": "Establishment, legal form, shareholders and UBOs with percentages, board and management.",
    "relationship": "Years with the bank, account conduct (balances, turnover, returned cheques, excesses) and earnings.",
    "projects": "For contractors: each financed project with employer, value, completion and receivables.",
    "cbrbr": "The central bank risk bureau extract for the group: limits and outstanding at every bank, with its date.",
    "bureau": "The credit bureau (SIMAH) report for the borrower and guarantors: score, defaults, enquiries, with its date.",
    "other_banks": "Facilities at other banks: bank, limit, outstanding, security and pricing.",
    "new_project": "For a new project: description, cost, funding plan and the project cash flow.",
    "financials": "Three years of audited financials (and interim) with the auditor and opinion.",
    "synopsis": "The analyst's reading of the financials: growth, margins, leverage, DSCR, liquidity, with the reasons.",
    "geopolitical": "How the current market and regional situation affects this borrower, in the bank's dated view.",
    "exceptions": "Every policy exception and observation, each with its mitigant.",
    "strengths": "The key strengths that support the deal, each backed by a fact.",
    "recommendation": "The credit division's recommendation: approve, decline or conditions, with the reasons.",
    "signatures": "RM, unit head and credit signatures with dates, and the approval authority.",
}

#: why a section can be not applicable (the check's own rule in engine.run)
NOT_APPLICABLE = {
    "new_project": "Not applicable: this deal finances no new project (no project with status 'new' in dd_project).",
    "projects": "Not applicable: the borrower is not a contractor with financed projects (no financed project in dd_project).",
}

SHORT = {"terms": "T&Cs", "cbrbr": "CBRBR", "bureau": "Bureau", "group_exposure": "Group exposure", "other_banks": "Other banks",
         "new_project": "New project", "geopolitical": "Market situation", "recommendation": "Recommendation"}


def _short(s: dict[str, Any]) -> str:
    return SHORT.get(s["key"], s["heading"].split(" (")[0])


def summary_line(sections: list[dict[str, Any]]) -> str:
    """"6 of 20 sections present; 11 missing; worst: Facilities, T&Cs, Bureau"."""
    app = [s for s in sections if s.get("applicable", True)]
    present = sum(1 for s in sections if s.get("present"))
    missing = [s for s in app if not s.get("present")]
    na = len(sections) - len(app)
    worst = sorted(app, key=lambda s: (s.get("score", 0.0), -s.get("critical", 0), -s.get("defects", 0), s.get("n", 0)))[:3]
    worst = [s for s in worst if s.get("score", 100.0) < 100.0]
    out = f"{present} of {len(sections)} sections present; {len(missing)} missing"
    if na:
        out += f"; {na} not applicable"
    if worst:
        out += "; worst: " + ", ".join(_short(s) for s in worst)
    return out


def _why(s: dict[str, Any], mine: list[dict[str, Any]]) -> str:
    if not s.get("applicable", True):
        return NOT_APPLICABLE.get(s["key"], "Not applicable to this deal.")
    if not s.get("present"):
        return "Missing: the RM's paper has no such section, so it scores 0. Add it, or write 'information not provided' with the reason."
    d = [f for f in mine if f.get("result") == "defect"]
    if not d and not [f for f in mine if f.get("result") == "observation"]:
        return "Present and every check on it passed: 100."
    parts = []
    for sev, pen in (("critical", "critical"), ("major", "major"), ("minor", "minor")):
        n = sum(1 for f in d if f.get("severity") == sev)
        if n:
            parts.append(f"{n} {pen}")
    obs = sum(1 for f in mine if f.get("result") == "observation")
    why = f"Present; scored {s.get('score', 0):.0f} because of " + (", ".join(parts) + " defect" + ("s" if len(d) != 1 else "") if parts else "")
    if obs:
        why += (" and " if parts else "") + f"{obs} observation{'s' if obs != 1 else ''}"
    return why + " (each defect takes points off by severity)."


def details(res: dict[str, Any], doc: dict[str, Any] | None = None) -> dict[str, Any]:
    """The per-section detail for every row of the score list, and the summary line."""
    found = list(res.get("defects") or []) + list(res.get("observations") or []) + list(res.get("passes") or [])
    text = {s["key"]: [p.get("text", "") for p in s.get("paras") or [] if p.get("text")] for s in (doc or {}).get("sections") or []}
    out = {}
    for s in res.get("sections") or []:
        k = s["key"]
        mine = [f for f in found if f.get("section_key") == k]
        quote = text.get(k) or []
        out[k] = {
            "requires": REQUIRES.get(k, ""),
            "quote": [q if len(q) <= 320 else q[:319].rsplit(" ", 1)[0] + "…" for q in quote[:3]],
            "quote_more": max(0, len(quote) - 3),
            "checks": [{"check": f.get("check"), "result": f.get("result"), "severity": f.get("severity"), "title": f.get("title"),
                        "evidence": f.get("evidence") or "", "source": f.get("evidence_relation") or "", "key": f.get("evidence_key") or ""}
                       for f in sorted(mine, key=lambda f: ({"defect": 0, "observation": 1, "pass": 2}.get(f.get("result"), 3), f.get("n", 0)))],
            "why": _why(s, mine),
            "queries": [f["query"] for f in mine if f.get("query")],
            "not_applicable": None if s.get("applicable", True) else NOT_APPLICABLE.get(k, "Not applicable to this deal."),
            "draft_from_data": bool(s.get("applicable", True)),
        }
    return {"summary": summary_line(res.get("sections") or []), "sections": out}


SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}
SEV_LABEL = {"critical": "Critical: must be fixed before review", "major": "Major", "minor": "Minor", "info": "For information"}


def rm_brief(res: dict[str, Any], due_days: int = 3, today: Any = None) -> dict[str, Any]:
    """R15 b (L11 (1)): one page of every issue for the RM: numbered queries grouped by severity (critical first) then section,
    each with the bank's evidence and the due date. Deterministic; the reviewer edits it before sending."""
    import datetime as dt
    base = today or dt.date.today()  # the due date runs from the day the brief is written
    due = base + dt.timedelta(days=due_days)
    while due.weekday() in (4, 5):  # the Saudi weekend (Friday, Saturday): the next working day
        due += dt.timedelta(days=1)
    due_s = due.isoformat()
    by_check = {f.get("check"): f for f in res.get("defects") or []}
    items = []
    for q in sorted(res.get("queries") or [], key=lambda q: (SEV_ORDER.get(q.get("severity"), 4), q.get("section") or 0, q.get("n") or 0)):
        f = by_check.get(q.get("check")) or {}
        items.append({"severity": q.get("severity"), "section": q.get("section"), "heading": q.get("heading"), "title": q.get("title"),
                      "query": q.get("query"), "evidence": f.get("evidence") or "", "source": f.get("evidence_relation") or "", "due": due_s})
    for i, it in enumerate(items):
        it["n"] = i + 1
    groups = []
    for sev in ("critical", "major", "minor", "info"):
        g = [it for it in items if it["severity"] == sev]
        if g:
            groups.append({"severity": sev, "label": SEV_LABEL[sev], "items": g})
    rm = res.get("rm") or "RM"
    crit = sum(1 for it in items if it["severity"] == "critical")
    lines = [f"To: {rm}", f"Subject: {res.get('customer')}: {len(items)} queries on your credit proposal (reply by {due_s})", "",
             f"Your proposal for {res.get('customer')} scored {res.get('score', 0):.0f}/100 (grade {res.get('grade')}) on the bank-form check"
             f" as at {str(res.get('as_of'))[:10]}. Please answer the {len(items)} queries below by {due_s}"
             + (f"; the {crit} critical one{'s' if crit != 1 else ''} first, the paper cannot go to review without them." if crit else "."), ""]
    for g in groups:
        lines.append(g["label"])
        for it in g["items"]:
            lines.append(f"{it['n']}. Section {it['section']} {it['heading']}: {it['title']}")
            lines.append(f"   Query: {it['query']}")
            if it["evidence"]:
                lines.append(f"   Bank's evidence: {it['evidence']}" + (f" (Data Domains: {it['source']})" if it["source"] else ""))
            lines.append(f"   Due: {it['due']}")
        lines.append("")
    lines.append("Credit review")
    return {"to": rm, "subject": lines[1][len("Subject: "):], "due": due_s, "count": len(items), "critical": crit, "groups": groups,
            "text": "\n".join(lines).strip()}


def document_view(res: dict[str, Any], doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """R15 b (L11 (2)): the RM's document itself, section by section, with the check's comments anchored to each section."""
    found = list(res.get("defects") or []) + list(res.get("observations") or [])
    out = []
    for s in (doc or {}).get("sections") or []:
        mine = [f for f in found if f.get("section_key") == s.get("key")]
        out.append({"key": s.get("key"), "n": s.get("n"), "heading": s.get("heading"),
                    "paras": [p.get("text", "") for p in s.get("paras") or [] if p.get("text")],
                    "tables": s.get("tables") or [],
                    "comments": [{"severity": f.get("severity"), "result": f.get("result"), "title": f.get("title"), "claim": f.get("claim") or "",
                                  "query": f.get("query") or "", "evidence": f.get("evidence") or ""}
                                 for f in sorted(mine, key=lambda f: (SEV_ORDER.get(f.get("severity"), 4), f.get("n", 0)))]})
    return out
