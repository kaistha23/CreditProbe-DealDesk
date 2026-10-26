"""R13 IE item 18: inspection responder.

Given a regulator's or auditor's request (free text, a sample list of borrowers, facilities or deals, or both), the
engine assembles the evidence pack: figures with lineage to relation, row and period; the approvals and conditions
history; the policy clauses that apply; and a coverage check of what was asked against what the pack answers.
Parsing is deterministic (identifier patterns and a keyword map); when the request names no items, it draws the
sample itself from the book (largest exposures matching the request's filters) and says so.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pandas as pd

from . import common as C

MAX_ITEMS = 25
DEFAULT_SAMPLE = 5

ID_PATTERNS = {
    "borrower": re.compile(r"\bCB\d{5}\b", re.I),
    "facility": re.compile(r"\bCF\d{6}\b", re.I),
    "deal": re.compile(r"\b(?:DD-\d{2}|PL-\d{2}|R12-[A-Z0-9]+)\b", re.I),
    "decision": re.compile(r"\bGD-\d{5}\b", re.I),
}
TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "exposure": ("Exposure and limits", ("exposure", "limit", "ead", "outstanding", "drawn", "balance")),
    "classification": ("Stage and arrears", ("stage", "classif", "ifrs", "dpd", "arrear", "past due", "overdue", "sicr", "default", "npl")),
    "provision": ("ECL and provisions", ("ecl", "provision", "impair", "coverage", "expected credit loss")),
    "rating": ("Rating", ("rating", "grade", "pd ", "probability of default")),
    "approval": ("Approvals and authority", ("approv", "authority", "doa", "delegat", "sanction", "committee", "decision")),
    "conditions": ("Conditions and covenants", ("condition", "covenant", "compliance certificate")),
    "exceptions": ("Policy exceptions", ("exception", "deviation", "waiver", "breach of policy", "override")),
    "promises": ("Commitments", ("promise", "commitment", "routing", "cross-sell")),
    "review": ("Credit review findings", ("review", "finding", "query", "queries")),
    "policy": ("Policy clauses", ("policy", "clause", "procedure")),
}
DEFAULT_TOPICS = ["exposure", "classification", "provision", "approval", "conditions", "exceptions", "policy"]
CLAUSES = {
    "classification": ["8.3", "8.4", "8.5", "8.6"], "provision": ["8.3", "8.4", "8.7"], "rating": ["4.1", "8.1"],
    "approval": ["1.3", "2.1", "3.2"], "conditions": ["10.1", "10.2", "8.2"], "exceptions": ["1.2"],
    "exposure": ["5.1", "5.2"], "review": ["1.3", "3.1"], "promises": ["3.1"], "policy": ["1.1", "1.2"],
}
FILTERS = {
    "stage 3": ("stage", 3), "stage 2": ("stage", 2), "default": ("default_flag", 1), "restructur": ("restructured_flag", 1),
    "watchlist": ("watchlist_flag", 1), "watch list": ("watchlist_flag", 1), "exception": ("has_exception", 1),
}


#: R14 G (K14): three requests a user can click when the box is empty (an auditor, the regulator, internal audit)
SAMPLES = [
    {"key": "auditor_stage3", "who": "External auditor",
     "label": "Auditor: Stage 3 sample in Construction",
     "request": "The auditor asks for the approvals, conditions and stage history of the 5 largest Stage 3 borrowers in Construction"},
    {"key": "sama_concentration", "who": "Regulator",
     "label": "SAMA: largest exposures and their approvals",
     "request": "SAMA asks for the exposure, limits, rating, approvals and authority of the 10 largest borrowers"},
    {"key": "ia_exceptions", "who": "Internal audit",
     "label": "Internal audit: policy exceptions on watch-list names",
     "request": "Internal audit asks for the policy exceptions, approvals and conditions of the 5 largest watch list borrowers"},
]
#: what the Word pack holds, in order (the preview before download)
PACK_SECTIONS = ["Cover: the request, the pack reference and the as-of quarter",
                 "Summary and the answer per item: EAD, stage path, approval with level and date, conditions and their status",
                 "Coverage check: each item and topic asked against what the data holds",
                 "Evidence per item: facilities, approval steps, conditions and exceptions",
                 "Policy clauses cited, quoted from the policy library",
                 "Method and data note; the Excel holds every figure with its relation, row and period"]
EVIDENCE = {"corporate book": "the corporate book", "governance register (demo seed)": "the governance register (demo seed)",
            "deal file": "the Deal Desk file", "policy library": "the policy library", "none": "no source"}


# ------------------------------------------------------------------ parse

def parse(request: str, sample: list[str] | None = None) -> dict[str, Any]:
    text = " ".join([request or ""] + list(sample or []))
    low = (request or "").lower()
    ids: dict[str, list[str]] = {}
    for kind, pat in ID_PATTERNS.items():
        seen: list[str] = []
        for m in pat.findall(text):
            u = m.upper()
            if u not in seen:
                seen.append(u)
        if seen:
            ids[kind] = seen
    topics = [t for t, (_, kws) in TOPICS.items() if any(k in low for k in kws)]
    implied = not topics
    if implied:
        topics = list(DEFAULT_TOPICS)
    elif "policy" not in topics:
        topics.append("policy")
    n = re.search(r"\b(\d{1,2})\s+(?:largest|top|sample|borrowers|facilities|obligors|files|accounts|names)", low)
    filters = sorted({FILTERS[k] for k in FILTERS if k in low})
    sectors = sorted({s for s in C.borrowers()["sector"].dropna().unique() if s.lower() in low})
    return {"ids": ids, "topics": topics, "topics_implied": implied, "sample_size": min(MAX_ITEMS, int(n.group(1))) if n else None,
            "filters": [list(f) for f in filters], "sectors": sectors}


# ------------------------------------------------------------------ items

def _latest(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["reporting_quarter"] == C.AS_OF_QUARTER]


def draw_sample(ask: dict[str, Any]) -> tuple[list[str], str]:
    f = _latest(C.facilities())
    b = _latest(C.borrowers())[["borrower_id", "sector", "watchlist_flag", "restructured_flag"]]
    agg = f.groupby("borrower_id").agg(ead=("ead_sar_mn", "sum"), stage=("stage", "max"), default_flag=("default_flag", "max")).reset_index()
    agg = agg.merge(b, on="borrower_id", how="left")
    ex = C.exceptions()
    agg["has_exception"] = agg["borrower_id"].isin(set(ex["borrower_id"])).astype(int) if not ex.empty else 0
    desc = []
    for col, val in ask["filters"]:
        agg = agg[agg[col] == val]
        desc.append(f"{col.replace('_flag', '').replace('_', ' ')} = {val}")
    if ask["sectors"]:
        agg = agg[agg["sector"].isin(ask["sectors"])]
        desc.append("sector in " + ", ".join(ask["sectors"]))
    n = ask["sample_size"] or DEFAULT_SAMPLE
    pick = agg.sort_values(["ead", "borrower_id"], ascending=[False, True]).head(n)
    rule = (f"Sample drawn by CreditProbe: the {len(pick)} largest borrowers by EAD at {C.AS_OF_QUARTER}"
            + (f" where {'; '.join(desc)}" if desc else "") + f" ({len(agg):,} matched).")
    return list(pick["borrower_id"]), rule


def _fac_rows(bid: str) -> list[dict[str, Any]]:
    f = _latest(C.facilities())
    return f[f["borrower_id"] == bid].sort_values("facility_id").to_dict("records")


def _stage_history(bid: str) -> list[dict[str, Any]]:
    f = C.facilities()
    g = f[f["borrower_id"] == bid].groupby("reporting_quarter").agg(stage=("stage", "max"), dpd=("dpd_days", "max")).reset_index()
    g = g.assign(qi=g["reporting_quarter"].map(C.q_index)).sort_values("qi")
    out, prev = [], None
    for r in g.itertuples(index=False):
        if r.stage != prev:
            out.append({"quarter": r.reporting_quarter, "stage": int(r.stage), "max_dpd": int(r.dpd),
                        "source": {"relation": "corp_facility_quarter", "filter": {"borrower_id": bid}, "period": r.reporting_quarter}})
            prev = r.stage
    return out


def _decisions_for(bid: str | None = None, did: str | None = None) -> list[dict[str, Any]]:
    d, s, e = C.decisions(), C.steps(), C.exceptions()
    if d.empty:
        return []
    sel = d[d["borrower_id"] == bid] if bid else d[d["decision_id"] == did]
    out = []
    for r in sel.assign(qi=sel["decision_quarter"].map(C.q_index)).sort_values("qi").to_dict("records"):
        st = s[s["decision_id"] == r["decision_id"]].sort_values("seq")
        ex = e[e["decision_id"] == r["decision_id"]]
        out.append({
            "decision_id": r["decision_id"], "quarter": r["decision_quarter"], "decided_on": r["decided_on"],
            "case_type": r["case_type"], "decision": r["decision"], "required_level": r["required_level"],
            "rm": r["rm_name"], "branch": r["branch_name"],
            "limit": C.fig("gov_decision", r, "limit_sar_mn", "SAR million"),
            "rating": r["rating_at_decision"],
            "steps": [{"level": x["level_name"], "received_on": x["received_on"], "decided_on": x["decided_on"],
                       "days": x["days"], "output": x["output"], "source": C.fig("gov_approval_step", x, "days", "days")["source"]}
                      for x in st.to_dict("records")],
            "conditions": {"set": int(r["conditions_set"]), "met": int(r["conditions_met"]), "breached": int(r["conditions_breached"]),
                           "source": C.fig("gov_decision", r, "conditions_set")["source"]},
            "promises": {"made": int(r["promises_made"]), "delivered": int(r["promises_delivered"])},
            "exceptions": [{"exception_id": x["exception_id"], "type": x["exception_type"], "clause": x["clause"],
                            "measured": C.fig("gov_policy_exception", x, "measured", x.get("unit") or ""),
                            "threshold": x["threshold"], "approved_by": x["approved_by_level"], "mitigant": x["mitigant"]}
                           for x in ex.to_dict("records")],
        })
    return out


def _deal(pid: str) -> dict[str, Any] | None:
    deals = C.frame("dd_deal")
    row = deals[deals["proposal_id"] == pid]
    if row.empty:
        return None
    r = row.iloc[0].to_dict()
    res = C.frame("dd_result")
    res = res[res["proposal_id"] == pid].to_dict("records")
    wf = C.frame("dd_workflow_event")
    wf = wf[wf["proposal_id"] == pid].sort_values("seq").to_dict("records")
    co = C.frame("dd_condition")
    co = co[co["proposal_id"] == pid].to_dict("records")
    fi = C.frame("dd_review_finding")
    fi = fi[fi["proposal_id"] == pid]
    pr = C.frame("dd_promise")
    pr = pr[pr["proposal_id"] == pid].to_dict("records")
    return {
        "proposal_id": pid, "deal_name": r.get("deal_name"), "obligor_id": r.get("obligor_id"), "rm": r.get("rm"),
        "status": r.get("status"), "workflow_state": r.get("workflow_state"), "approval_authority": r.get("approval_authority"),
        "proposed_limits": C.fig("dd_deal", r, "proposed_limits_mn", "SAR million"),
        "results": [{"view": x["view"], "approval_level": x["approval_level"], "decision": x["decision"],
                     "raroc": C.fig("dd_result", x, "lifetime_raroc_pct", "%")} for x in res],
        "workflow": [{"seq": int(x["seq"]), "to_state": x["to_state"], "actor": x["actor"], "role": x["actor_role"], "at": x["at"],
                      "source": C.fig("dd_workflow_event", x, "seq")["source"]} for x in wf],
        "conditions": [{"condition_id": x["condition_id"], "kind": x["kind"], "text": x["text"], "status": x["status"],
                        "due_date": x["due_date"], "set_by": x["set_by"], "source": C.fig("dd_condition", x, "status")["source"]}
                       for x in co],
        "findings": {"total": int(len(fi)), "by_severity": {k: int(v) for k, v in fi["severity"].value_counts().items()},
                     "high": [{"finding_id": x["finding_id"], "title": x["title"], "status": x["status"],
                               "source": C.fig("dd_review_finding", x, "severity")["source"]}
                              for x in fi[fi["severity"].isin(["critical", "high"])].head(5).to_dict("records")]},
        "promises": [{"promise_id": x["promise_id"], "text": x["text"], "status": x["status"],
                      "delivered_pct": C.fig("dd_promise", x, "delivered_pct", "%")} for x in pr],
    }


def _borrower(bid: str) -> dict[str, Any] | None:
    facs = _fac_rows(bid)
    b = C.borrowers()
    br = b[(b["borrower_id"] == bid) & (b["reporting_quarter"] == C.AS_OF_QUARTER)]
    if not facs and br.empty:
        return None
    brow = br.iloc[0].to_dict() if len(br) else {}
    deals = C.frame("dd_deal", ["proposal_id", "obligor_id"])
    return {
        "borrower_id": bid, "name": brow.get("borrower_name") or (facs[0].get("borrower_id") if facs else bid),
        "sector": brow.get("sector"), "rating": C.fig("corp_borrower_quarter", brow, "rating_current") if brow else None,
        "facilities": [{"facility_id": f["facility_id"], "limit": C.fig("corp_facility_quarter", f, "limit_sar_mn", "SAR million"),
                        "ead": C.fig("corp_facility_quarter", f, "ead_sar_mn", "SAR million"),
                        "stage": C.fig("corp_facility_quarter", f, "stage"), "dpd": C.fig("corp_facility_quarter", f, "dpd_days", "days"),
                        "ecl": C.fig("corp_facility_quarter", f, "ecl_sar_mn", "SAR million")} for f in facs],
        "stage_history": _stage_history(bid),
        "decisions": _decisions_for(bid=bid),
        "deals": [_deal(p) for p in deals[deals["obligor_id"] == bid]["proposal_id"]],
    }


# ------------------------------------------------------------------ coverage

def _covers(item: dict[str, Any], topic: str) -> tuple[str, str]:
    kind = item["kind"]
    ev = item.get("evidence") or {}
    if not ev:
        return "not_available", f"{item['id']} is not in Data Domains."
    decs = ev.get("decisions") or []
    deals = [d for d in (ev.get("deals") or []) if d] + ([ev] if kind == "deal" else [])
    facs = ev.get("facilities") or []
    if topic in ("exposure", "classification", "provision"):
        if facs:
            return "answered", f"{len(facs)} facilities at {C.AS_OF_QUARTER} from corp_facility_quarter" + (
                f"; stage history {len(ev.get('stage_history') or [])} changes" if topic == "classification" else "")
        if kind == "deal":
            return ("partial", "Deal not yet booked: proposed limits and engine results only.") if topic == "exposure" else (
                "not_available", "Deal not yet booked: no stage, arrears or ECL exist.")
        return "not_available", "No book rows."
    if topic == "rating":
        return ("answered", "Rating from corp_borrower_quarter.") if ev.get("rating") else (
            ("partial", "Proposed rating on the deal record.") if kind == "deal" else ("not_available", "No rating row."))
    if topic == "approval":
        n = len(decs) + sum(len(d.get("workflow") or []) for d in deals)
        return ("answered", f"{len(decs)} decisions with level-by-level steps; {sum(len(d.get('workflow') or []) for d in deals)} workflow events.") if n else (
            "not_available", "No approval history recorded for this item.")
    if topic == "conditions":
        n = sum(x["conditions"]["set"] for x in decs) + sum(len(d.get("conditions") or []) for d in deals)
        if n:
            return "answered", f"{n} conditions with status."
        return ("answered", "Approved without conditions.") if decs else ("not_available", "No conditions recorded.")
    if topic == "exceptions":
        n = sum(len(x["exceptions"]) for x in decs)
        return ("answered", f"{n} approved policy exceptions with clause and measured value." if n else
                "No policy exception approved on the recorded decisions.") if decs or deals else ("not_available", "No decision recorded.")
    if topic == "promises":
        n = sum(x["promises"]["made"] for x in decs) + sum(len(d.get("promises") or []) for d in deals)
        return ("answered", f"{n} commitments with delivery.") if n else (("answered", "No commitments made.") if decs or deals else
                                                                          ("not_available", "No decision recorded."))
    if topic == "review":
        n = sum((d.get("findings") or {}).get("total", 0) for d in deals)
        return ("answered", f"{n} review findings.") if n else (
            ("partial", "Historical decisions carry query counts only; no finding text.") if decs else ("not_available", "No review on record."))
    if topic == "policy":
        return "answered", "Clauses quoted from dd_policy_clause."
    return "not_available", "Topic not recognised."


def _tl(topic: str) -> str:
    """Topic label in running text: first letter lower-cased unless it starts an acronym (ECL)."""
    t = TOPICS[topic][0]
    return t if t[:2].isupper() else t[0].lower() + t[1:]


def write(ask: dict[str, Any], items: list[dict[str, Any]], cov: list[dict[str, Any]], rule: str | None) -> list[str]:
    a = sum(c["status"] == "answered" for c in cov)
    p = sum(c["status"] == "partial" for c in cov)
    m = sum(c["status"] == "not_available" for c in cov)
    found = sum(1 for i in items if i.get("evidence"))
    labels = [_tl(t) for t in ask["topics"]]
    lines = [f"Asked: {len(items)} items × {len(ask['topics'])} topics ({', '.join(labels)})"
             + (" — no topic named, so the standard inspection set was used." if ask["topics_implied"] else ".")]
    if rule:
        lines.append(rule)
    lines.append(f"Answered {a} of {len(cov)} requests in full, {p} in part; {m} cannot be answered from Data Domains.")
    missing = [i["id"] for i in items if not i.get("evidence")]
    groups: dict[tuple[str, str], list[str]] = {}
    for c in cov:
        if c["status"] != "answered" and c["item"] not in missing:
            groups.setdefault((c["item"], c["reason"].rstrip(".")), []).append(_tl(c["topic"]))
    if groups:
        lines.append("Gaps: " + "; ".join(f"{item} ({', '.join(ts)}): {why}" for (item, why), ts in list(groups.items())[:3]) + ".")
    if missing:
        lines.append(f"Not found in Data Domains: {', '.join(missing)}; nothing is answered for "
                     f"{'it' if len(missing) == 1 else 'them'}.")
    return lines[:5]


def respond(request: str = "", sample: list[str] | None = None) -> dict[str, Any]:
    ask = parse(request, sample)
    ids = ask["ids"]
    rule = None
    items: list[dict[str, Any]] = []
    for bid in ids.get("borrower", []):
        items.append({"kind": "borrower", "id": bid})
    fac = _latest(C.facilities())
    for fid in ids.get("facility", []):
        row = fac[fac["facility_id"] == fid]
        items.append({"kind": "facility", "id": fid, "borrower_id": row.iloc[0]["borrower_id"] if len(row) else None})
    for pid in ids.get("deal", []):
        items.append({"kind": "deal", "id": pid})
    d = C.decisions()
    for did in ids.get("decision", []):
        row = d[d["decision_id"] == did]
        items.append({"kind": "decision", "id": did, "borrower_id": row.iloc[0]["borrower_id"] if len(row) else None})
    if not items:
        pick, rule = draw_sample(ask)
        items = [{"kind": "borrower", "id": b} for b in pick]
    items = items[:MAX_ITEMS]
    for it in items:
        if it["kind"] == "borrower":
            it["evidence"] = _borrower(it["id"])
        elif it["kind"] in ("facility", "decision"):
            ev = _borrower(it["borrower_id"]) if it.get("borrower_id") else None
            if ev and it["kind"] == "facility":
                ev["facilities"] = [f for f in ev["facilities"] if f["facility_id"] == it["id"]]
            if ev and it["kind"] == "decision":
                ev["decisions"] = [x for x in ev["decisions"] if x["decision_id"] == it["id"]]
            it["evidence"] = ev
        else:
            it["evidence"] = _deal(it["id"])
    clauses_needed = sorted({c for t in ask["topics"] for c in CLAUSES.get(t, [])}
                            | {x["clause"] for it in items for dd in ((it.get("evidence") or {}).get("decisions") or [])
                               for x in dd["exceptions"]}, key=lambda c: [int(p) for p in c.split(".")])
    pc = C.frame("dd_policy_clause")
    clauses = [{"clause": r["clause"], "heading": r["heading"], "quote": r["quote"], "policy_id": r["policy_id"],
                "source": C.fig("dd_policy_clause", r, "quote")["source"]}
               for r in pc[pc["clause"].isin(clauses_needed)].to_dict("records")]
    clauses.sort(key=lambda c: [int(p) for p in c["clause"].split(".")])
    cov = [{"item": it["id"], "kind": it["kind"], "topic": t, "topic_label": TOPICS[t][0],
            **dict(zip(("status", "reason"), _covers(it, t)))} for it in items for t in ask["topics"]]
    key = json.dumps({"r": request, "s": sample or []}, sort_keys=True)
    pack_id = "IP-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper()
    for c in cov:
        c["evidence"] = _evidence_kind(c["topic"], next((i for i in items if i["id"] == c["item"]), {}))
    answers = [answer(it, ask["topics"]) for it in items]
    return {
        "available": True, "kind": "inspection_pack", "pack_id": pack_id,
        "pack_note": (f"{pack_id} is this pack's reference: the same request and sample always give the same reference, so the reply to the "
                      "inspector can cite it and the pack can be rebuilt later with the same figures."),
        "summary": summary_line(ask, items, cov, answers), "answers": answers, "samples": SAMPLES, "sections": PACK_SECTIONS,
        "as_of": C.AS_OF_QUARTER, "request": request, "sample": sample or [], "ask": ask, "sample_rule": rule,
        "lines": write(ask, items, cov, rule), "items": items, "clauses": clauses, "coverage": cov,
        "coverage_summary": {s: sum(c["status"] == s for c in cov) for s in ("answered", "partial", "not_available")},
        "method": __doc__.strip().split("\n\n", 1)[1].replace("\n", " "), "data_note": C.SEED_NOTE,
    }



# ------------------------------------------------------------------ R14 G (K15): the answer, not only the coverage

def _evidence_kind(topic: str, item: dict[str, Any]) -> str:
    ev = item.get("evidence") or {}
    if not ev:
        return "none"
    if topic in ("exposure", "classification", "provision", "rating"):
        return "corporate book" if ev.get("facilities") or ev.get("rating") else ("deal file" if item.get("kind") == "deal" else "none")
    if topic == "policy":
        return "policy library"
    if topic in ("approval", "conditions", "exceptions", "promises"):
        if ev.get("decisions"):
            return "governance register (demo seed)"
        if item.get("kind") == "deal" or any(ev.get("deals") or []):
            return "deal file"
        return "none"
    if topic == "review":
        return "deal file" if item.get("kind") == "deal" or any(ev.get("deals") or []) else "governance register (demo seed)"
    return "none"


def _stage_path(hist: list[dict[str, Any]]) -> str:
    if not hist:
        return ""
    parts = [f"S{hist[0]['stage']}"] + [f"S{h['stage']} {h['quarter']}" for h in hist[1:]]
    return " → ".join(parts)


def _date(d: Any) -> str:
    try:
        return pd.Timestamp(str(d)).strftime("%-d %b %Y")
    except Exception:  # noqa: BLE001
        return str(d or "")


def answer(item: dict[str, Any], topics: list[str]) -> dict[str, Any]:
    """One borrower's (or deal's) answer in a line per topic: name, EAD, stage path, approval, conditions (K15)."""
    ev = item.get("evidence") or {}
    bid = ev.get("borrower_id") or item.get("borrower_id") or (ev.get("obligor_id") if item.get("kind") == "deal" else None)
    out: dict[str, Any] = {"item": item["id"], "kind": item["kind"], "found": bool(ev), "borrower_id": bid,
                           "name": ev.get("name") or ev.get("deal_name") or item["id"]}
    if bid:
        out["href"] = f"/borrower-360?domain=corporate&customer_id={bid}&from=governance"
    if item.get("kind") == "deal":
        out["href"] = f"/deal-desk/{item['id']}?from=governance"
    if not ev:
        out["note"] = "Not found in Data Domains: nothing answered."
        return out
    facs = ev.get("facilities") or []
    if facs:
        ead = sum(float(f["ead"]["value"] or 0) for f in facs)
        src0 = dict(facs[0]["ead"]["source"])
        src0["key"] = {"borrower_id": bid, "reporting_quarter": C.AS_OF_QUARTER}
        src0["method"] = f"sum of ead_sar_mn over the borrower's {len(facs)} facilities at {C.AS_OF_QUARTER}"
        out["ead"] = {"value": round(ead, 4), "unit": "SAR million", "source": src0}
        out["facilities"] = len(facs)
        out["stage_now"] = max(int(f["stage"]["value"] or 0) for f in facs)
        out["max_dpd"] = max(int(f["dpd"]["value"] or 0) for f in facs)
    elif item.get("kind") == "deal":
        out["proposed_limits"] = ev.get("proposed_limits")
    hist = ev.get("stage_history") or []
    if hist:
        out["stage_path"] = _stage_path(hist)
    decs = ev.get("decisions") or []
    if decs:
        d = decs[-1]
        out["approval"] = {"ref": d["decision_id"], "level": d["required_level"], "date": d["decided_on"], "decision": d["decision"],
                           "text": f"{d['decision_id']}, {d['required_level']}, {_date(d['decided_on'])}",
                           "evidence": "governance register (demo seed)", "source": d["limit"]["source"]}
        cs, cm, cb = (sum(x["conditions"][k] for x in decs) for k in ("set", "met", "breached"))
        out["conditions"] = {"set": cs, "met": cm, "breached": cb, "open": max(0, cs - cm - cb),
                             "text": (f"{cm} of {cs} met" + (f"; {cb} breached" if cb else "") + (f"; {cs - cm - cb} open" if cs - cm - cb > 0 else "")
                                      if cs else "none set"),
                             "evidence": "governance register (demo seed)"}
        out["exceptions"] = sum(len(x["exceptions"]) for x in decs)
        out["decisions"] = len(decs)
    deals = [x for x in (ev.get("deals") or []) if x] + ([ev] if item.get("kind") == "deal" else [])
    dconds = [c for x in deals for c in (x.get("conditions") or [])]
    if dconds:
        met = sum(c["status"] == "met" for c in dconds)
        q_end = str(pd.Period(C.AS_OF_QUARTER, freq="Q").end_time.date())
        overdue = sum(c["status"] == "not_complied" or (c["status"] != "met" and str(c.get("due_date") or "9999") < q_end) for c in dconds)
        out["deal_conditions"] = {"set": len(dconds), "met": met, "overdue": overdue,
                                  "text": f"{met} of {len(dconds)} met" + (f"; {overdue} overdue" if overdue else ""), "evidence": "deal file"}
        if "conditions" not in out:
            out["conditions"] = {**out["deal_conditions"]}
    if item.get("kind") == "deal" and ev.get("approval_authority"):
        out.setdefault("approval", {"ref": item["id"], "level": ev.get("approval_authority"), "date": "", "decision": ev.get("status"),
                                    "text": f"{item['id']}, {ev.get('approval_authority')}, {ev.get('workflow_state') or ev.get('status') or ''}".rstrip(", "),
                                    "evidence": "deal file"})
    lines = []
    if "ead" in out:
        lines.append(f"SAR {out['ead']['value']:,.1f}m EAD over {out['facilities']} facilit{'y' if out['facilities'] == 1 else 'ies'}, Stage {out['stage_now']} now")
    if out.get("stage_path"):
        lines.append(f"Stage path {out['stage_path']}")
    if out.get("approval"):
        lines.append(f"Approved {out['approval']['text']}")
    if out.get("conditions"):
        lines.append(f"Conditions {out['conditions']['text']}" if out["conditions"]["set"] else "Approved without conditions")
    out["line"] = "; ".join(lines) + "." if lines else "No answer rows."
    return out


def summary_line(ask: dict[str, Any], items: list[dict[str, Any]], cov: list[dict[str, Any]], answers: list[dict[str, Any]]) -> str:
    """'5 borrowers, SAR x EAD; all 4 topics answered; approvals from the governance register (demo seed).'"""
    kinds = {i["kind"] for i in items}
    noun = (f"{len(items)} borrower{'s' if len(items) != 1 else ''}" if kinds == {"borrower"} else f"{len(items)} item{'s' if len(items) != 1 else ''}")
    ead = sum(a["ead"]["value"] for a in answers if a.get("ead"))
    nt = len(ask["topics"])
    full_topics = [t for t in ask["topics"] if all(c["status"] == "answered" for c in cov if c["topic"] == t)]
    topics = (f"all {nt} topics answered" if len(full_topics) == nt else f"{len(full_topics)} of {nt} topics answered in full")
    seed = any(c["evidence"] == "governance register (demo seed)" for c in cov)
    s = f"{noun}" + (f", SAR {ead:,.1f}m EAD" if ead else "") + f"; {topics}"
    if seed:
        s += "; approvals and conditions from the governance register (demo seed)"
    return s + "."
