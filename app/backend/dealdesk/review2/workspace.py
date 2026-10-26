"""PLAN_R12 Session B: review(deal_id) and preflight(deal_id).

review() runs the R11 workspace (claims ledger, the 52 rules, counter-proposals, conditions as triggers, precedent), adds the R12
analytics, the document checklist, the language and version checks and the findings other sessions published (C), and returns:

  answer       decision line first (counts by severity, approval level, counter-proposal)
  points       the 12 review points, each with status, summary, findings and its analysis
  findings     every finding by severity, with evidence and lineage; published to dd_review_finding
  analytics    adjusted ratios, receivables, auditor, bureau and other-bank matrix, earlier conditions, insider links
  documents    the checklist (published to dd_document)          queries   RM queries through Mail (dd_query)
  quality      the proposal quality score                          opinion   the reviewer opinion in the credit voice (credit view only)
  signoff      second-line sign-off with its audit trail
  lineage      every block's relation, key and period

preflight() is the same rules run for the RM before submission (the Prepare view): blockers, warnings, documents, ready or not.
It never shows credit's internal opinion or notes (I17 segregation of duties).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import time
from typing import Any

from backend.dealdesk import documents as DOC
from backend.dealdesk import paths
from backend.dealdesk.review2 import base as BASE
from backend.dealdesk.review2 import analytics as A
from backend.dealdesk.review2 import findings as F
from backend.dealdesk.review2 import opinion as O
from backend.dealdesk.review2 import points as PT
from backend.dealdesk.review2 import queries as Q
from backend.dealdesk.review2 import source as S

VERSION = "r12-b1"
_LOCK = threading.Lock()
SIGNOFF_ROLES = ("analyst", "senior_manager", "vp_credit", "cco", "cro")


def _subject_extra(d: dict[str, Any]) -> dict[str, Any]:
    r11 = d["r11"]
    return {"request_summary": (r11.get("case") or {}).get("request_summary") or d["subject"].get("request_summary") or []}


def _answer(findings: list[dict[str, Any]], base: dict[str, Any], docs: dict[str, Any]) -> dict[str, Any]:
    n = F.counts(findings)
    if n["critical"]:
        decision, tone = "Do not approve as proposed", "negative"
    elif n["major"]:
        decision, tone = "Approve with conditions", "warning"
    else:
        decision, tone = "Approve as proposed", "positive"
    parts = [f"{n[s]} {s}" for s in ("critical", "major", "minor") if n[s]]
    head = decision + (": " + ", ".join(parts) + f" finding{'s' if sum(n[s] for s in ('critical', 'major', 'minor')) != 1 else ''}" if parts else ": no findings")
    tail = []
    cp = base.get("counter_proposal")
    if cp and decision != "Approve as proposed":
        tail.append(base["headline"].split("; ", 1)[1] if "; " in base["headline"] else "")
    if docs["missing_count"]:
        tail.append(f"{docs['missing_count']} documents missing")
    head += ("; " + "; ".join(t for t in tail if t)) if any(tail) else ""
    if base.get("engine_verdict"):  # R14 E (K18 #5): the findings engine's verdict names the critical and major findings
        v = base["engine_verdict"]
        decision, tone = v["decision"], v["tone"]
        head = v["headline"].rstrip(".") + (f"; {docs['missing_count']} documents missing" if docs["missing_count"] else "")
    return {"decision": decision, "tone": tone, "headline": head, "counts": n, "approval": base["approval"], "counter_proposal": cp}


def review(sid: str, refresh: bool = False, view: str = "review", publish: bool = True) -> dict[str, Any]:
    if not S.known(sid):
        raise KeyError(sid)
    t0 = time.time()
    if refresh:
        S.clear()
    d = S.deal_file(sid)
    base = BASE.review(sid, refresh=refresh)
    an = A.all_for(d)
    docs = DOC.checklist(sid, d)
    qs = Q.listing(sid)
    lang = PT.language_check(d["r11"]["ledger"]) if not (base.get("memo") or {}).get("generated") else \
        {"lines_checked": 0, "unevidenced": [], "balance_words": [], "one_sided": False, "findings": [],
         "source": {"relation": "dd_deal", "key": {"proposal_id": sid}, "period": None},
         "headline": "No memo submitted by business yet; the language check runs on the submitted or uploaded proposal."}
    ver = PT.versions(sid, {"counts": (base.get("memo") or {}).get("counts") or {}}, qs)
    r12 = [f for k in ("adjusted", "receivables", "auditor", "bureau", "earlier", "insider", "conduct", "projections") for f in an[k]["findings"]]
    r12 += PT.documents_findings(docs) + lang["findings"] + ver["findings"] + PT.precedent_findings(base["precedent"])
    merged = F.merge(r12, base["checks"], d["lineage"]["financials"]) + F.others(sid)
    fs = F.number(sid, merged, d["subject"].get("as_of"), VERSION)
    # link open queries to their findings
    by_ref = {q["ref_id"]: q for q in qs["items"] if q.get("ref_id")}
    for f in fs:
        q = by_ref.get(f["finding_id"]) or next((by_ref.get(i) for i in f.get("document_items") or [] if by_ref.get(i)), None)
        if q:
            f["query_id"] = q["query_id"]
            f["status"] = {"queued": "query_sent", "sent": "query_sent", "answered": "answered", "closed": "addressed"}[q["status"]]
    ans = _answer([f for f in fs if f["severity"] != "info"], {**base["answer"], "engine_verdict": (base.get("engine") or {}).get("verdict")}, docs)  # R14 E
    ccy = d["subject"]["currency"]
    ld = d["lineage"]
    by_cat = base["by_category"]
    pblocks = {
        1: {"summary": docs["headline"], "analysis": ["documents"], "checks": {"documents": len(docs["items"])},
            "floor": "attention" if docs["missing_count"] else None},
        2: {"summary": f"{base['verdicts']['supported']} checks supported by the evidence, {base['verdicts']['contradicted']} contradicted "
                       f"(each listed under the point it concerns), {base['verdicts']['unverifiable']} unverifiable. " + an["bureau"]["headline"]
                       + " " + an["conduct"]["headline"],
            "analysis": ["bureau"],
            "checks": by_cat.get("data", {})},
        3: {"summary": f"{sum(by_cat.get('consistency', {}).values())} consistency checks: " +
                       ", ".join(f"{v} {k}" for k, v in by_cat.get("consistency", {}).items() if v), "checks": by_cat.get("consistency", {})},
        4: {"summary": " ".join(x for x in (an["adjusted"]["headline"], an["receivables"]["headline"], an["auditor"]["headline"],
                                            an["projections"]["headline"]) if x),
            "analysis": ["adjusted", "receivables", "auditor"]},
        5: {"summary": f"{sum(by_cat.get('policy', {}).values())} policy checks; approval at {base['doa']['level']} ({base['doa']['binding']['detail']}).",
            "checks": by_cat.get("policy", {})},
        6: {"summary": an["insider"]["headline"] + (f" {sum(by_cat.get('connected', {}).values())} connected-party checks."
                                                    if sum(by_cat.get("connected", {}).values()) else ""),
            "analysis": ["insider"], "checks": by_cat.get("connected", {})},
        7: {"summary": "Security, perfection, legal opinion and valuation: " + (
            ", ".join(f"{i['name'].lower()} {i['status']}" for i in docs["items"] if i["group"] in ("Legal", "Security"))[:300] or "no security items") + "."},
        8: {"summary": an["earlier"]["headline"], "analysis": ["earlier"], "assessed": True},
        9: {"summary": base["precedent"].get("line") or "No precedent in the book.", "analysis": ["precedent"]},
        10: {"summary": lang["headline"], "analysis": ["language"], "assessed": bool(lang["lines_checked"])},
        11: {"summary": ver["headline"], "analysis": ["versions"]},
        12: {"summary": "", "analysis": ["outputs"]},
    }
    qual = O.quality(docs, base["verdicts"], [f for f in fs if f["severity"] != "info"], lang)
    pblocks[12]["summary"] = (f"{ans['headline']}. {qual['headline']} Counter-proposals: {len(base['counter'].get('counter_proposals') or [])}; "
                              f"conditions tracked: {len((base['conditions'] or {}).get('items') or [])}.")
    pts = PT.assemble(fs, pblocks)
    pts[11]["status"] = {"negative": "fail", "warning": "attention", "positive": "pass"}[ans["tone"]]
    ctx = {"subject": {**d["subject"], **_subject_extra(d)}, "answer": ans, "findings": [f for f in fs if f["severity"] != "info"], "analytics": an,
           "documents": docs, "queries": qs, "counter": base["counter"], "doa": base["doa"], "conditions": base["conditions"], "quality": qual,
           "precedent": base["precedent"], "checks_run": len(base["checks"]) + len(docs["items"]) + 6,
           "request_summary": _subject_extra(d)["request_summary"]}
    op = O.opinion(ctx)
    pub = {}
    if publish:
        try:
            pub["findings"] = F.publish(fs, sid)
            pub["documents"] = DOC.publish(sid)
            pub["conditions"] = _publish_conditions(sid)
        except Exception as e:  # noqa: BLE001 - publishing must never block the review
            pub["error"] = str(e)[:200]
    out = {
        "deal_id": sid, "version": VERSION, "view": view, "subject": d["subject"], "currency": ccy, "as_of": d["subject"].get("as_of"),
        "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "answer": ans, "points": pts, "findings": fs, "counts": F.counts(fs),
        "analytics": {**an, "language": lang, "versions": ver, "precedent": base["precedent"]},
        "documents": docs, "queries": qs, "quality": qual, "figures": figures(d),
        "opinion": op if view == "review" else None,
        "r11": {"memo": base["memo"], "verdicts": base["verdicts"], "doa": base["doa"], "counter": base["counter"], "conditions": base["conditions"]},
        "signoff": signoffs(sid) if view == "review" else None,
        "lineage": {**ld, "findings": {"relation": "dd_review_finding", "key": {"deal_id": sid}, "period": d["subject"].get("as_of")},
                    "queries": {"relation": "dd_query", "key": {"deal_id": sid}, "period": None}},
        "published": pub, "seconds": round(time.time() - t0, 2),
        "basis": "The R11 claims ledger and 52 rules, plus the R12 analyses (adjusted ratios, receivables, auditor, bureau and other banks, "
                 "earlier conditions, insider links), the document checklist from the bank's document rules, the language and "
                 "version checks, and the group findings published by the group review; every figure tagged with its Data Domains relation.",
    }
    return out


def _publish_conditions(sid: str) -> dict[str, Any]:
    """The review's conditions (R11 triggers) into dd_condition through E's bridge, only when they changed."""
    from backend.dealdesk import review_conditions as RCN
    from backend.dealdesk.data import bridge
    from backend.dealdesk.review2 import publish as P
    trig = [RCN.evaluate_trigger(t, RCN.facts_for(t["deal_id"])) for t in RCN.stored(sid)]
    rows = bridge.r11_condition_rows(trig)
    if not rows or not P._changed("dd_condition", rows, ["condition_id"]):
        return {"relation": "dd_condition", "rows": len(rows), "result": "unchanged"}
    return bridge.publish_r11_conditions(sid, actor="B")


# ------------------------------------------------------------------ traced figures (PLAN §0: every number to its relation and row)

FIGURE_COLUMNS = {
    "financials": ("dd_financials_detail", ("net_worth_mn", "intangibles_mn", "due_from_related_mn", "shareholder_accounts_mn", "noncore_investments_mn",
                                            "current_assets_mn", "current_liabilities_mn", "bank_debt_st_mn", "bank_debt_lt_mn", "receivables_mn",
                                            "ageing_0_90_mn", "ageing_91_180_mn", "ageing_181_365_mn", "ageing_over_365_mn", "top2_receivable_pct",
                                            "retention_receivables_mn", "cash_cycle_days")),
    "bureau_entity_report": ("bureau_entity_report", ("outstanding_mn", "overdue_mn", "returned_cheques_n", "court_cases_n")),
    "other_bank_facility": ("other_bank_facility", ("declared_limit_mn", "bureau_limit_mn", "difference_mn")),
    "dd_condition": ("dd_condition", ("trigger_threshold", "measured_value")),
    "b360_insider_link": ("b360_insider_link", ("share_pct",)),
}


def figures(d: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The review's source figures as traced figures ({value, unit, source}) for every block read from Data Domains."""
    try:
        from backend.dealdesk.data import lineage
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for block, (rel, cols) in FIGURE_COLUMNS.items():
        figs = []
        for row in (d.get("raw") or {}).get(block) or []:
            for c in cols:
                if row.get(c) is not None:
                    f = lineage.figure(rel, row, c)
                    f["label"] = f"{row.get('entity_name') or row.get('bank_name') or row.get('text') or row.get('period_label') or ''} {c}".strip()
                    figs.append(f)
        if figs:
            out[block] = figs
    return out


# ------------------------------------------------------------------ pre-flight (Prepare view)

def preflight(sid: str) -> dict[str, Any]:
    r = review(sid, view="prepare", publish=False)
    fs = [f for f in r["findings"] if f["severity"] != "info"]
    blockers = [f for f in fs if f["severity"] == "critical" or (f["code"].startswith("DR-") and f["severity"] in ("critical", "major"))]
    warnings = [f for f in fs if f not in blockers and f["severity"] == "major"]
    notes = [f for f in fs if f not in blockers and f not in warnings]
    strip = lambda f: {k: f.get(k) for k in ("finding_id", "point", "point_name", "code", "severity", "title", "finding", "policy_ref", "status",  # noqa: E731
                                              "document_items", "query_id")}
    ready = not blockers
    return {"deal_id": sid, "view": "prepare", "ready": ready,
            "headline": ("Ready to submit" if ready else f"Fix {len(blockers)} item{'s' if len(blockers) != 1 else ''} before submitting") +
                        f": {len(blockers)} blocking, {len(warnings)} to explain, {r['documents']['missing_count']} documents missing; quality {r['quality']['score']}/100.",
            "blockers": [strip(f) for f in blockers], "warnings": [strip(f) for f in warnings], "notes": [strip(f) for f in notes],
            "documents": r["documents"], "queries": r["queries"], "quality": r["quality"],
            "points": [{k: p[k] for k in ("point", "name", "status", "counts")} for p in r["points"]],
            "basis": "The same rules credit runs in Review, run before submission; credit's opinion and internal notes are not shown."}


# ------------------------------------------------------------------ second-line sign-off

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS r12_signoff (deal_id TEXT, role TEXT, by TEXT, decision TEXT, note TEXT, at TEXT, version TEXT)")
    return con


def signoffs(sid: str) -> dict[str, Any]:
    with _LOCK, _db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM r12_signoff WHERE deal_id=? ORDER BY at", (sid,))]
    latest = {}
    for r in rows:
        latest[r["role"]] = r
    return {"roles": list(SIGNOFF_ROLES), "latest": latest, "trail": rows}


def sign(sid: str, role: str, decision: str, by: str, note: str = "") -> dict[str, Any]:
    if role not in SIGNOFF_ROLES:
        raise ValueError(f"role must be one of {', '.join(SIGNOFF_ROLES)}")
    if decision not in ("agree", "agree with conditions", "disagree"):
        raise ValueError("decision must be agree, agree with conditions or disagree")
    with _LOCK, _db() as con:
        con.execute("INSERT INTO r12_signoff VALUES (?,?,?,?,?,?,?)",
                    (sid, role, by or "reviewer", decision, note, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), VERSION))
    return signoffs(sid)


def queue_missing(sid: str, by: str | None = None, to: str | None = None) -> dict[str, Any]:
    """One RM query per missing or expired required document (I26: missing items create queries)."""
    docs = DOC.checklist(sid)
    made = []
    for i in docs["items"]:
        if i["mandatory"] and i["status"] in ("pending", "expired"):
            q = f"Please provide the {i['name'].lower()} for {i['for']}" + (" (the copy on file has expired)" if i["status"] == "expired" else "") + \
                f"; required by {i['clause']}."
            made.append(Q.raise_query(sid, q, "document", i["item_id"], to=to, by=by))
    return {"raised": len(made), "items": made}
