"""The engines a demo run calls: Session B's review and Session F's committee paper when they are merged, else the
R11 review (rules.json + counter-proposals) and the R11 committee sheet; Session E's publisher for the demo deal.

Every call is through the owning module's public functions; nothing here re-implements a review or a paper.
"""
from __future__ import annotations

import importlib
import inspect
import json
from collections.abc import Callable
from datetime import UTC
from typing import Any

from backend.dealdesk import paths

#: candidates for the R12 engines (module, function), first one present wins
B_REVIEW = [("backend.dealdesk.review2.workspace", "review")]
F_PAPER = [("backend.dealdesk.committee_paper", "build")]
F_PAPER_DOCX = [("backend.dealdesk.committee_paper", "docx")]
#: Session F's bank-form proposal: the English draft when merged (else Session P's house-style drafter)
F_PROPOSAL = [("backend.dealdesk.house_style.bankform.paper", "write")]


def _find(cands: list[tuple[str, str]]) -> tuple[str, Callable[..., Any]] | None:
    for mod, fn in cands:
        try:
            m = importlib.import_module(mod)
        except Exception:  # noqa: BLE001 - not merged yet
            continue
        f = getattr(m, fn, None)
        if callable(f):
            return f"{mod}.{fn}", f
    return None


def which() -> dict[str, str]:
    b, f = _find(B_REVIEW), _find(F_PAPER)
    return {"review": f"Session B review ({b[0]})" if b else "R11 review (rules.json, review_workspace)",
            "paper": f"Session F committee paper ({f[0]})" if f else "R11 committee sheet (review_workspace.sheet)",
            "publisher": "Session E publisher (backend.dealdesk.data.publish)" if _store() else "session folder (E's publisher not merged)"}


def _call(fn: Callable[..., Any], pid: str, **extra: Any) -> Any:
    sig = inspect.signature(fn).parameters
    kw = {k: v for k, v in (("refresh", True), ("publish", False), *extra.items()) if k in sig}
    return fn(pid, **kw)


#: Session B's severities (dd_review_finding) in the R11 words the run shows
B_SEV = {"critical": "critical", "high": "major", "medium": "minor", "low": "minor"}


# ------------------------------------------------------------------ review against THEIR policy

def _r11_review(pid: str) -> dict[str, Any]:
    from backend.dealdesk import review_workspace as RW
    return RW.review(pid, refresh=True, with_counter=False)


def _row(c: dict[str, Any], source: str) -> dict[str, Any]:
    sev = c.get("severity") or "minor"
    return {"rule_id": c.get("rule_id") or c.get("id") or c.get("finding_id"), "title": c.get("title") or c.get("rule_title") or "",
            "severity": B_SEV.get(sev, sev), "verdict": c.get("verdict"),
            "finding": c.get("finding") or c.get("finding_text") or c.get("text") or "",
            "policy_ref": c.get("policy_ref") or "", "crm_article": c.get("crm_article") or "", "source": source}


#: deal figures a check needs (by words in the rule id or title); a defaulted figure makes the check not verifiable
NEEDS = {"current_ratio": ("CURRENT-RATIO", "current ratio"), "ebitda": ("DSCR", "DEBT-EBITDA", "EBITDA", "leverage"),
         "debt_service": ("DSCR",), "total_debt": ("DEBT-EBITDA", "leverage", "debt/ebitda"), "net_worth": ("NET-WORTH", "net worth", "gearing")}


def _needs_default(c: dict[str, Any], defaulted: set[str]) -> str | None:
    key = f"{c.get('rule_id') or ''} {c.get('title') or ''}".lower()
    for f, words in NEEDS.items():
        if f in defaulted and any(w.lower() in key for w in words):
            return f
    return None


def review(pid: str, policy_rules: list[dict[str, Any]], defaulted: list[str] | None = None) -> dict[str, Any]:
    from backend.dealdesk import review_facts as RF
    from backend.dealdesk import review_rules as RR
    b = _find(B_REVIEW)
    engine = "R11 review"
    rev: dict[str, Any] | None = None
    if b:
        try:
            rev = _call(b[1], pid)
            engine = "Session B review"
        except Exception:  # noqa: BLE001 - B's engine cannot take this deal: the R11 review answers
            rev = None
    if rev is None:
        rev = _r11_review(pid)
    base = [c for c in (rev.get("findings") or []) if c.get("verdict") in ("contradicted", "exception", None)
            and c.get("severity") != "info" and not _needs_default(c, set(defaulted or []))]
    facts = RF.facts(pid)
    pol_checks: list[dict[str, Any]] = []
    for r in policy_rules:
        try:
            for c in RR.run_rule(r, facts):
                c = {**c, "clause": r.get("clause"), "quote": r.get("quote")}
                miss = _needs_default(c, set(defaulted or []))
                if miss and c.get("verdict") != "unverifiable":
                    c.update(verdict="unverifiable", finding=f"Not verifiable: the proposal does not state {miss.replace('_', ' ')} "
                                                             "(a labelled default of 0 was used for the engine).")
                pol_checks.append(c)
        except Exception as e:  # noqa: BLE001 - a rule that cannot run is reported, never silent
            pol_checks.append({"rule_id": r.get("id"), "title": r.get("title"), "verdict": "unverifiable", "severity": "minor",
                               "finding": f"Could not run: {e}", "clause": r.get("clause"), "policy_ref": r.get("policy_ref")})
    pol_find = [c for c in pol_checks if c.get("verdict") in ("contradicted", "exception")]
    counts = {v: sum(1 for c in pol_checks if c.get("verdict") == v) for v in ("supported", "contradicted", "exception", "unverifiable")}
    findings = [_row(c, f"your policy {c.get('clause') or ''}".strip()) for c in pol_find] + [_row(c, "CreditProbe rule book") for c in base]
    sev = {k: sum(1 for f in findings if f["severity"] == k) for k in ("critical", "major", "minor")}
    ans = rev.get("answer") or {}
    if engine == "Session B review" and not rev.get("doa"):
        rev = {**rev, "doa": (rev.get("r11") or {}).get("doa"), "verdicts": (rev.get("r11") or {}).get("verdicts")}
    head = ans.get("headline") if isinstance(ans, dict) else str(ans)
    summary = (f"{len(pol_checks)} checks of your policy clauses: {counts['supported']} met, {len(pol_find)} breached, "
               f"{counts['unverifiable']} need data the proposal does not give. With the CreditProbe rule book: {len(findings)} findings "
               f"({sev['critical']} critical, {sev['major']} major, {sev['minor']} minor).")
    return {"engine": engine, "headline": head, "decision": ans.get("decision") if isinstance(ans, dict) else None,
            "tone": ans.get("tone") if isinstance(ans, dict) else None, "findings": findings, "severity": sev,
            "policy_checks": [{**_row(c, f"your policy {c.get('clause') or ''}".strip()), "quote": c.get("quote")} for c in pol_checks],
            "policy_counts": counts, "doa": rev.get("doa"), "verdicts": rev.get("verdicts"), "summary": summary,
            "seconds": rev.get("seconds")}


# ------------------------------------------------------------------ counter-proposal and committee paper

def _cp_line(cp: dict[str, Any]) -> dict[str, Any]:
    keep = ("label", "title", "name", "summary", "changes", "raroc", "raroc_pct", "sva", "decision", "approval", "why", "levers",
            "amount", "margin_bps", "tenor_years", "conditions", "answer", "headline")
    return {k: cp[k] for k in keep if k in cp}


def counter_and_paper(pid: str) -> dict[str, Any]:
    from backend.dealdesk import review_workspace as RW
    rev = RW.review(pid, refresh=True, with_counter=True)
    cps = (rev.get("counter") or {}).get("counter_proposals") or []
    f = _find(F_PAPER)
    paper, engine = None, "R11 committee sheet"
    if f:
        try:
            cp = _call(f[1], pid)
            pp = cp.get("paper") or {}
            paper = {"kind": "committee paper", "summary_sections": [x.get("heading") for x in cp.get("summary") or []],
                     "sections": [x.get("heading") for x in pp.get("sections") or []], "density": cp.get("density") or [],
                     "answer": {"decision": (rev.get("answer") or {}).get("decision")}}
            engine = "Session F committee paper"
        except Exception:  # noqa: BLE001 - F's paper cannot take this deal: the R11 sheet
            paper = None
    if paper is None:
        paper = RW.sheet(pid)
    ask = (rev.get("counter") or {}).get("ask")
    first = _cp_line(cps[0]) if cps else None
    summary = (f"{len(cps)} counter-proposal{'s' if len(cps) != 1 else ''} priced by the optimiser"
               + (f"; the first: {first.get('label') or first.get('title') or first.get('name') or 'restructured terms'}" if first else "")
               + f". Committee paper: {engine}"
               + (f", decision {paper.get('answer', {}).get('decision')}" if isinstance(paper, dict) and isinstance(paper.get("answer"), dict) else "")
               + ".")
    return {"engine": engine, "counter_proposals": [_cp_line(c) for c in cps], "counter_raw": cps[:3], "ask": ask, "paper": paper,
            "summary": summary, "docx": "/try-docs/sessions/{sid}/paper.docx"}


# ------------------------------------------------------------------ Data Domains (demo scope)
#
# Session E's publisher (backend.dealdesk.data.publish) writes the demo session to Data Domains while it is open: the deal
# (dd_deal, source "try_docs:<session>"), the learned policy as a trial version (dd_policy status "trial" and its
# dd_policy_clause rows) and the review findings (dd_review_finding). The wipe removes them with replace_where (no rows
# added) and scrubs the archived versions E keeps under r12_history, so nothing of the session survives.

SEV = {"critical": "critical", "major": "high", "minor": "medium"}


def _store() -> Any | None:
    try:
        from backend.dealdesk.data import schema, store
    except Exception:  # noqa: BLE001 - E not merged
        return None
    return store if "dd_deal" in schema.RELATIONS else None


def scope_of(sid: str) -> str:
    return f"try_docs:{sid}"


def policy_id_of(sid: str) -> str:
    return "TRY-POL-" + sid.split("-")[-1][:8].upper()


def _deal_row(p: dict[str, Any], sid: str) -> dict[str, Any]:
    ob, a = p["obligor"], p["ask"]
    return {"proposal_id": p["proposal_id"], "source": scope_of(sid), "product": "corporate", "deal_name": ob["name"][:80],
            "obligor_id": ob.get("obligor_id"), "obligor_name": ob["name"], "group_id": ob.get("group_id"), "group_name": ob.get("group_name"),
            "case_type": "new", "status": p.get("status", "new"), "workflow_state": "in_review", "rm": p.get("rm") or "",
            "business_unit": p.get("business_unit", ""), "received_date": p.get("received"), "currency": a["currency"],
            "existing_limits_mn": 0.0, "proposed_limits_mn": float(a["amount"]), "rating_existing": ob["internal_rating"],
            "rating_proposed": ob["internal_rating"], "proposal_json": json.dumps(p, default=str)}


def _pub(st: Any, relation: str, rows: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    r = st.publish(relation, rows, actor="T:try_docs", **kw)
    return {"relation": relation, "version": r["version"], "written": r["written"]}


def publish_demo_deal(p: dict[str, Any], sid: str) -> dict[str, Any]:
    st = _store()
    if st is None:
        from backend.dealdesk.try_docs import deal as D
        rows = D.data_domain_rows(p, scope_of(sid))
        d = paths.VAR / "try_docs" / "sessions" / sid / "data_domains"
        d.mkdir(parents=True, exist_ok=True)
        for rel, rs in rows.items():
            (d / f"{rel}.json").write_text(json.dumps({"relation": rel, "scope": scope_of(sid), "rows": rs}, default=str))
        return {"published": False, "via": "session folder (Session E's publisher not merged)", "scope": scope_of(sid),
                "relations": {k: len(v) for k, v in rows.items()}}
    res = _pub(st, "dd_deal", [_deal_row(p, sid)], mode="upsert")
    return {"published": True, "via": "Session E publisher", "scope": scope_of(sid), "relations": {"dd_deal": 1}, "result": [res]}


def publish_demo_policy(sid: str, policy: dict[str, Any], name: str) -> dict[str, Any] | None:
    """The learned policy as a trial version (dd_policy status 'trial', I18) with its clauses."""
    st = _store()
    if st is None or not policy or not policy.get("found"):
        return None
    pid = policy_id_of(sid)
    from datetime import datetime
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    head = {"policy_id": pid, "version": 1, "title": name, "uploaded_by": "try-docs", "uploaded_at": now, "status": "trial",
            "source_file": f"{scope_of(sid)}/{name}", "clauses_n": len(policy["found"]), "summary": policy["summary"][:400]}
    seen, clauses = set(), []
    for f in policy["found"]:
        c = str(f.get("clause") or f["id"])
        if c in seen:
            c = f"{c}/{f.get('metric')}"
        seen.add(c)
        pr = f.get("param") or {}
        clauses.append({"policy_id": pid, "version": 1, "clause": c, "heading": f.get("label") or "", "quote": (f.get("quote") or "")[:400],
                        "sets_table": pr.get("table") or "", "sets_key": pr.get("row") or "",
                        "sets_value": "" if f.get("value") is None else json.dumps(f["value"], default=str)})
    out = [_pub(st, "dd_policy", [head], mode="upsert"), _pub(st, "dd_policy_clause", clauses, mode="upsert")]
    return {"published": True, "policy_id": pid, "status": "trial", "result": out}


def publish_demo_findings(sid: str, deal_id: str, review: dict[str, Any]) -> dict[str, Any] | None:
    st = _store()
    if st is None:
        return None
    from datetime import datetime
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rows = []
    for i, f in enumerate(review.get("findings") or [], start=1):
        mine = f["source"].startswith("your policy")
        rows.append({"finding_id": f"T-{deal_id}-{i:03d}", "proposal_id": deal_id, "review_point": 5 if mine else 2,
                     "category": "policy" if mine else "rule_book", "severity": SEV.get(f["severity"], "medium"),
                     "title": (f.get("title") or f.get("rule_id") or "")[:200], "finding_text": f.get("finding") or "",
                     "evidence_domain": "deal_desk", "evidence_relation": "dd_policy_clause" if mine else "dd_deal",
                     "evidence_key": (f"policy_id={policy_id_of(sid)};clause={f['source'].replace('your policy', '').strip()}" if mine
                                      else f"proposal_id={deal_id}"),
                     "status": "open", "rating_notch": 0, "raised_by": "T (try it on your documents)", "raised_at": now})
    if not rows:
        return {"published": True, "rows": 0}
    return {"published": True, "rows": len(rows), "result": [_pub(st, "dd_review_finding", rows, mode="replace_where",
                                                                    where={"proposal_id": deal_id})]}


def _scrub_history(st: Any, relation: str, needles: list[str]) -> int:
    """Remove the session's rows from E's archived versions of a relation (rewrites the archive files that hold them)."""
    import pandas as pd
    h = st.history_root() / relation
    n = 0
    for f in sorted(h.glob("*.parquet")) if h.exists() else []:
        try:
            df = pd.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        hit = pd.Series(False, index=df.index)
        for c in df.columns:
            col = df[c].astype("string")
            for x in needles:
                hit |= col.str.contains(x, regex=False, na=False)
        if hit.any():
            df[~hit].to_parquet(f, index=False)
            n += int(hit.sum())
    return n


def unpublish_demo_deal(sid: str, deal_id: str | None = None) -> dict[str, Any]:
    st = _store()
    if st is None:
        return {"removed": False, "via": "session folder (removed with the session)"}
    pid = deal_id or ""
    pol = policy_id_of(sid)
    out, scrubbed = [], 0
    targets = [("dd_deal", {"source": scope_of(sid)}), ("dd_policy", {"policy_id": pol}), ("dd_policy_clause", {"policy_id": pol})]
    if pid:
        targets.append(("dd_review_finding", {"proposal_id": pid}))
    for rel, where in targets:
        col, val = next(iter(where.items()))
        if st.dd_read(rel, columns=[col], **where):
            out.append(_pub(st, rel, [], mode="replace_where", where=where))
        scrubbed += _scrub_history(st, rel, [x for x in (sid, pid, pol) if x])
    return {"removed": True, "via": "Session E publisher", "relations": out, "archived_rows_scrubbed": scrubbed}
