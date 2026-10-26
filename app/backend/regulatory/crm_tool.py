"""The CBUAE CRM breach checks as a conversation tool every v5 assistant can call (PLAN_R7 C3.1).

`crm_breaches` is a built-in tool of `backend.convo.agent` (so What-If, Deal Desk, Lenses, Scorecard, Admin, Playbook
and Projects all have it), registered for Playbook/Projects in `backend.ai_work.tools`, and answered without a model
by `answer()` when a question asks which exposures breach the Standards.
"""
from __future__ import annotations

import re
from typing import Any

from backend.regulatory import crm_checks as k

NAME = "crm_breaches"
DESCRIPTION = ("Run the CBUAE Credit Risk Management Standards breach checks on the books (deterministic): which "
               "facilities/accounts breach which article (default and staging, SICR, restructuring probation, Stage 3 "
               "provision floors, collateral haircuts and valuations, write-off, the Stage 3 ratio), each with the "
               "article id (e.g. 'CBUAE CRM Art. 9.23'), the entity, measured and required values, EAD, ECL and "
               "severity. Filter by article ('9' or '9.23'), book, severity or an entity id.")
SCHEMA = {"type": "object", "properties": {
    "article": {"type": "string", "description": "An article or paragraph: '9', '9.23' or 'CBUAE CRM Art. 9.23'."},
    "book": {"type": "string", "enum": ["", "corporate", "retail"]},
    "severity": {"type": "string", "enum": ["", "high", "medium", "low"]},
    "entity": {"type": "string", "description": "A facility, account, borrower or customer id."},
    "limit": {"type": "integer"}}}

#: A question about compliance with the Standards (the deterministic path answers it with this tool).
CRM_WORDS = re.compile(
    r"(\b(breach\w*|complian\w*|compliant|non[-\s]?complian\w*|violat\w*|exceptions?)\b.*"
    r"\b(cbuae|crm|standards?|article|art\.|regulat\w*|central bank)\b)|"
    r"(\b(cbuae|crm|standards?|article \d+|regulat\w*)\b.*\b(breach\w*|complian\w*|compliant|violat\w*)\b)",
    re.I | re.S)
ENTITY_RE = re.compile(r"\b(C[BF]N?\d{5,6}|RA\d{6,8}[BM]?\d?|RC\d{6})\b", re.I)


def is_crm_question(q: str) -> bool:
    return bool(CRM_WORDS.search(q or ""))


def parse(q: str) -> dict[str, Any]:
    """Tool arguments read from a question ("Are we compliant with Article 9 provisioning?" -> article 9)."""
    q = q or ""
    args: dict[str, Any] = {}
    m = re.search(r"\b(?:art(?:icle)?\.?)\s*(\d{1,2}(?:\.\d{1,2})?)", q, re.I)
    if m:
        args["article"] = m.group(1)
    low = q.lower()
    if "retail" in low and "corporate" not in low:
        args["book"] = "retail"
    elif ("corporate" in low or "wholesale" in low) and "retail" not in low:
        args["book"] = "corporate"
    e = ENTITY_RE.search(q)
    if e:
        args["entity"] = e.group(1).upper()
    if re.search(r"\bhigh[-\s]severity\b|\bhigh\b breaches", low):
        args["severity"] = "high"
    return args


def _mn(x: float) -> str:
    return f"SAR {x:,.1f} mn" if abs(x) >= 0.1 else f"SAR {x * 1000:,.0f} thousand"


def run(args: dict[str, Any]) -> dict[str, Any]:
    lim = int(args.get("limit") or 30)
    out = k.breaches(article=str(args.get("article") or ""), book_id=str(args.get("book") or ""),
                     severity=str(args.get("severity") or ""), entity=str(args.get("entity") or ""),
                     limit=max(1, min(lim, 200)))
    checks = [{"check_id": c["check_id"], "article": c["article"], "title": c["title"], "book": c["book"],
               "period": c["period"], "status": c["status"], "breaches": c["breaches"], "tested": c["tested"],
               "ead_sar_mn": c["ead_sar_mn"], "ecl_sar_mn": c["ecl_sar_mn"], "shortfall_sar_mn": c["shortfall_sar_mn"],
               "rule": c["rule"]} for c in out["checks"]]
    rows = [{"article": r["article"], "check": r["title"], "book": r["book"], "entity_id": r["entity_id"],
             "borrower_id": r["borrower_id"] if r["book"] == "corporate" else "",
             "customer_id": r["borrower_id"] if r["book"] == "retail" else "",
             "measured": r["measured"], "required": r["required"], "unit": r["unit"], "ead_sar_mn": r["ead_sar_mn"],
             "ecl_sar_mn": r["ecl_sar_mn"], "shortfall_sar_mn": r["shortfall_sar_mn"], "severity": r["severity"],
             "detail": r["detail"]} for r in out["breaches"]]
    return {"document": out["document"], "periods": out["periods"], "filter": out["filter"], "count": out["count"],
            "ead_sar_mn": out["ead_sar_mn"], "ecl_sar_mn": out["ecl_sar_mn"],
            "shortfall_sar_mn": out["shortfall_sar_mn"], "checks": checks, "breaches": rows,
            "truncated": out["truncated"], "not_checked": out["not_checked"], "href": out["href"],
            "citation_rule": ("Name each breach by its article id and title in bold (e.g. **CBUAE CRM Art. 9.23 Stage 3 "
                              "provision below the wholesale floor**), with the entity, the measured and required values "
                              "and the EAD/ECL; give the books' periods.")}


def summary_line(out: dict[str, Any]) -> str:
    p = out["periods"]
    scope = []
    f = out["filter"]
    if f.get("article"):
        scope.append(f"Article {f['article']}")
    if f.get("book"):
        scope.append(f"the {f['book']} book")
    if f.get("entity"):
        scope.append(f["entity"])
    where = " for " + ", ".join(scope) if scope else ""
    if not out["count"]:
        return (f"No breach of the CBUAE Credit Risk Management Standards{where} on the books "
                f"(corporate {p['corporate']}, retail {p['retail']}).")
    return (f"**{out['count']} breaches** of the CBUAE Credit Risk Management Standards{where} "
            f"(corporate {p['corporate']}, retail {p['retail']}): EAD {_mn(out['ead_sar_mn'])}, ECL "
            f"{_mn(out['ecl_sar_mn'])}" + (f", provision shortfall {_mn(out['shortfall_sar_mn'])}"
                                            if out["shortfall_sar_mn"] else "") + ".")


def markdown(out: dict[str, Any]) -> str:
    lines = [summary_line(out), ""]
    for c in out["checks"]:
        if c["breaches"]:
            lines.append(f"- **{c['article']} {c['title']}** ({c['book']}): {c['breaches']:,} of {c['tested']:,} tested, "
                         f"EAD {_mn(c['ead_sar_mn'])}" + (f", shortfall {_mn(c['shortfall_sar_mn'])}"
                                                           if c["shortfall_sar_mn"] else ""))
    ok = [c for c in out["checks"] if not c["breaches"]]
    if ok:
        lines.append("")
        lines.append("Compliant: " + "; ".join(f"**{c['article']}** {c['title'].lower()} ({c['book']})" for c in ok) + ".")
    if out["not_checked"]:
        lines.append("")
        lines.append("Not testable on these books: " + "; ".join(f"{n['article']} ({n['why']})" for n in out["not_checked"][:4]) + ".")
    return "\n".join(lines)
