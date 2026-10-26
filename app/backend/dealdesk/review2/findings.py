"""Findings by severity with evidence, and the dd_review_finding schema (shared with Session C, PLAN_R12 sessions table).

A finding row (relation dd_review_finding, one row per deal and finding):

  finding_id      "<deal>:<code>:<n>"           deal_id        the deal (DD-nn, PL-nn, PRP-*)
  point           1..12 (the I16 point)          point_name     e.g. "Claims against evidence"
  code            R12 code (ADJ-01, BUR-01 ...) or the R11 rule id (DATA-08 ...)
  rule_ids        R11 rule ids folded into it    author         "B" (review), "C" (group, governance, conduct)
  severity        critical | major | minor | info
  title, finding  the finding in the credit voice (fact, number, date)
  evidence        JSON list [{source, text, ref: {relation, key, period}}]
  value, threshold, policy_ref, crm_article, doa_level
  status          open | query_sent | answered | addressed | waived
  query_id        the RM query raised for it, if any
  raised_at, review_version, period

C publishes rows with author "C"; review() reads them back and places them under their point.
"""
from __future__ import annotations

import json
from typing import Any

from backend.dealdesk.review2 import publish as P

SEV_RANK = {"critical": 0, "major": 1, "minor": 2, "info": 3}

POINTS = [
    (1, "Completeness", "Required documents and information for the deal type; the missing-information register and RM queries."),
    (2, "Claims against evidence", "Memo figures against the books, bureau, audited accounts, conduct and other-bank letters."),
    (3, "Consistency", "Totals, the ask against the recommendation and conditions, the memo's own stress against its recommendation."),
    (4, "Re-performed analysis", "Independent spreading, adjusted ratios, receivables quality, auditor quality, projections tested against history."),
    (5, "Policy and regulation", "Exceptions with their clause and DoA level, missing sign-offs, pricing against the hurdle."),
    (6, "Group and connected parties", "Group exposure against the cap, connected names classified or in litigation, staff and insider links."),
    (7, "Collateral and legal", "Perfection, legal-opinion age, guarantee format and enforceability, valuation age, registration."),
    (8, "Track record", "Conditions of the previous approval met, covenant history, promised against delivered business."),
    (9, "Precedent and peers", "n of N outcomes for similar deals in the book, peer ratios."),
    (10, "Language check", "Unevidenced claims and one-sided wording in the memo."),
    (11, "Versions", "Memo versions reviewed, queries answered and still open."),
    (12, "Outputs", "Findings by severity, counter-proposal, conditions as triggers, quality score, reviewer opinion, sign-off."),
]
POINT_NAME = {n: name for n, name, _ in POINTS}

#: R11 rule id -> point (rules.json categories map by default: data 2, consistency 3, policy 5, connected 6).
R11_POINT = {"DATA-09": 1, "PRJ-01": 4, "PRJ-02": 4, "PRJ-03": 4, "PRJ-04": 4, "BKL-01": 4, "BKL-02": 4, "BKL-03": 4,
             "WC-01": 4, "WC-02": 4, "WC-03": 4, "WC-04": 4, "WC-05": 4, "RET-01": 4, "FS-01": 4, "GOV-03": 4, "GOV-04": 4,
             "RP-01": 6, "RP-02": 6, "GOV-01": 6, "LIM-01": 6, "GOV-02": 8, "GOV-05": 5, "CONS-07": 5,
             "EXC-03": 7, "EXC-04": 7, "SEC-01": 7, "COV-01": 8, "COV-02": 8}
CAT_POINT = {"data": 2, "consistency": 3, "policy": 5, "connected": 6}

#: R12 finding code -> the R11 rules it supersedes (same issue; the R12 text carries the adjusted figure and the R11
#: anchors, DoA and article are kept on it).
SUPERSEDES = {"AUD-01": ["FS-01"], "AUD-02": ["GOV-03"], "TRK-01": ["COV-01", "GOV-02", "EXC-05"], "INS-01": ["CP-04"], "INS-02": ["CP-02"],
              "BUR-01": ["DATA-08"], "DR-07": ["DATA-09"], "DR-21": ["GOV-04"], "DR-09": ["EXC-04"], "DR-24": ["EXC-03"], "BUR-03": ["DATA-07", "DATA-05"], "BUR-04": ["CP-03", "CP-01"],
              "RCV-01": ["WC-03"], "RCV-02": ["BKL-03"], "RCV-03": ["RET-01"], "RCV-04": ["RP-02"], "RCV-05": ["WC-04"]}


def from_check(c: dict[str, Any], ref: dict[str, Any] | None = None) -> dict[str, Any]:
    pt = R11_POINT.get(c["rule_id"]) or CAT_POINT.get(c["category"], 5)
    return {"code": c["rule_id"], "point": pt, "severity": c.get("severity") or "minor", "title": c["title"], "finding": c["finding"],
            "evidence": [{**e, "ref": ref} for e in c.get("evidence") or []], "measured": c.get("value"), "threshold": c.get("threshold"),
            "policy_ref": c.get("policy_ref", ""), "crm_article": c.get("crm_article", ""), "doa_level": (c.get("doa") or {}).get("level"),
            "rule_ids": [c["rule_id"]], "line_ids": c.get("line_ids") or [], "verdict": c["verdict"], "author": "B", "origin": "r11-rule"}


def merge(r12: list[dict[str, Any]], r11_checks: list[dict[str, Any]], ref: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """R12 analytics findings plus every failed R11 check, the overlaps folded into one finding each."""
    failed = {c["rule_id"]: c for c in r11_checks if c["verdict"] in ("contradicted", "exception")}
    used: set[str] = set()
    out = []
    for f in r12:
        f = {**f, "rule_ids": [], "line_ids": [], "crm_article": f.get("crm_article", ""), "doa_level": f.get("doa_level"), "author": "B",
             "origin": "r12-analytics", "verdict": f.get("verdict") or "exception"}
        for rid in SUPERSEDES.get(f["code"], []):
            c = failed.get(rid)
            if c and rid not in used:
                used.add(rid)
                f["rule_ids"].append(rid)
                f["line_ids"] += c.get("line_ids") or []
                f["crm_article"] = f["crm_article"] or c.get("crm_article", "")
                f["doa_level"] = f["doa_level"] or (c.get("doa") or {}).get("level")
                if SEV_RANK.get(c.get("severity") or "minor", 3) < SEV_RANK.get(f["severity"], 3):
                    f["severity"] = c["severity"]
                if c["verdict"] == "contradicted":
                    f["verdict"] = "contradicted"
        out.append(f)
    out += [from_check(c, ref) for rid, c in failed.items() if rid not in used]
    return out


def number(deal_id: str, items: list[dict[str, Any]], period: str | None, version: str) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    out = []
    for f in sorted(items, key=lambda f: (SEV_RANK.get(f["severity"], 3), f["point"], f["code"])):
        n = seen[f["code"]] = seen.get(f["code"], 0) + 1
        out.append({**f, "finding_id": f.get("finding_id") or f"B-{deal_id}-{f['code']}-{n}", "deal_id": deal_id,
                    "point_name": POINT_NAME.get(f["point"], ""), "status": f.get("status") or "open", "period": period, "review_version": version})
    return out


SEV_OUT = {"critical": "critical", "major": "high", "minor": "medium", "info": "info"}
SEV_IN = {"critical": "critical", "high": "major", "medium": "minor", "low": "minor", "info": "info", "major": "major", "minor": "minor"}
STATUS_OUT = {"open": "open", "query_sent": "open", "answered": "open", "addressed": "resolved", "waived": "accepted"}
CATEGORY = {"ADJ": "adjusted_ratios", "RCV": "receivables_quality", "AUD": "auditor_quality", "BUR": "bureau_reconciliation",
            "TRK": "earlier_conditions", "INS": "insider_link", "DR": "documents", "LNG": "language", "VER": "versions", "PRC": "precedent"}


def others(deal_id: str) -> list[dict[str, Any]]:
    """Findings other sessions published for this deal (C: governance and conduct; D: stress; I: book), from Data Domains.
    B's own rows (B-) and E's seeded demo rows (E-) are not read back: this review recomputes them."""
    rows = [r for r in P.read("dd_review_finding", proposal_id=deal_id)
            if not str(r.get("finding_id") or "").startswith(("B-", "E-")) and str(r.get("status") or "open") != "superseded"]
    rows += [r for r in P.staged("dd_review_finding") if r.get("proposal_id") == deal_id and not str(r.get("finding_id") or "").startswith(("B-", "E-"))]
    out = []
    for r in rows:
        rel = r.get("evidence_relation")
        key = dict(kv.split("=", 1) for kv in str(r.get("evidence_key") or "").split(";") if "=" in kv)
        ev = [{"source": rel or "Group review", "text": r.get("claim_text") or r.get("title") or "",
               "ref": {"relation": rel, "key": key, "period": r.get("reporting_quarter")} if rel else None}]
        author = str(r.get("raised_by") or str(r.get("finding_id"))[:1] or "C")[:1].upper()
        out.append({"code": r.get("category") or f"{author}-FINDING", "point": int(r.get("review_point") or 6),
                    "severity": SEV_IN.get(str(r.get("severity") or "").lower(), "major"), "title": r.get("title") or "",
                    "finding": r.get("finding_text") or r.get("title") or "", "evidence": ev, "measured": r.get("evidence_value"),
                    "threshold": r.get("claim_value"), "policy_ref": "", "crm_article": "", "doa_level": None, "rule_ids": [], "line_ids": [],
                    "author": author, "origin": "published", "finding_id": r.get("finding_id"), "verdict": "exception",
                    "rating_notch": r.get("rating_notch"), "condition_id": r.get("condition_id")})
    return out


def _num(x: Any) -> float | None:
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def rows(findings: list[dict[str, Any]], raised_at: str | None = None) -> list[dict[str, Any]]:
    """B's findings as dd_review_finding rows (R12_DATA_CONTRACT)."""
    out = []
    for f in findings:
        if f.get("author") not in (None, "B"):
            continue
        ev = (f.get("evidence") or [{}])[0] or {}
        ref = ev.get("ref") or {}
        key = ";".join(f"{k}={v}" for k, v in (ref.get("key") or {}).items())
        out.append({"finding_id": f["finding_id"], "proposal_id": f["deal_id"], "review_point": f["point"],
                    "category": CATEGORY.get(f["code"].split("-")[0], f["code"].split("-")[0].lower()) + f":{f['code']}",
                    "severity": SEV_OUT.get(f["severity"], "medium"), "title": f["title"], "finding_text": f["finding"],
                    "claim_text": "; ".join(e.get("text", "") for e in (f.get("evidence") or [])[:3])[:1000] or None,
                    "claim_value": _num(f.get("threshold")), "evidence_value": _num(f.get("measured")), "evidence_unit": None,
                    "evidence_domain": None, "evidence_relation": ref.get("relation"), "evidence_key": key or None,
                    "status": STATUS_OUT.get(f.get("status") or "open", "open"), "rating_notch": 0, "condition_id": None,
                    "query_id": f.get("query_id"), "raised_by": "B", "raised_at": raised_at})
    return out


def publish(findings: list[dict[str, Any]], deal_id: str | None = None) -> dict[str, Any]:
    import datetime as dt
    at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rs = rows(findings, at)
    if deal_id:  # earlier B findings for this deal that no longer fire are superseded, not deleted
        now_ids = {r["finding_id"] for r in rs}
        for old in P.read("dd_review_finding", proposal_id=deal_id):
            fid = str(old.get("finding_id") or "")
            if fid.startswith("B-") and fid not in now_ids and old.get("status") != "superseded":
                rs.append({k: old.get(k) for k in ("finding_id", "proposal_id", "review_point", "category", "severity", "title", "finding_text",
                                                   "claim_text", "claim_value", "evidence_value", "evidence_unit", "evidence_domain",
                                                   "evidence_relation", "evidence_key", "rating_notch", "condition_id", "query_id", "raised_by",
                                                   "raised_at")} | {"status": "superseded", "resolved_at": at})
    return P.publish("dd_review_finding", rs, key=("finding_id",))


def counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_RANK}
