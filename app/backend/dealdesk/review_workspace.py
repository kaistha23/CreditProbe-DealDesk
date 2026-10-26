"""R11 Session R: the proposal review workspace, the committee decision sheet and RM "Draft from data".

review(subject_id) runs, in order:
  R1 the claims ledger of the memo (review_ledger),
  R2 every rule in rules.json against the evidence (review_facts, review_rules), with the DoA level,
  R3 counter-proposals priced by the optimiser (review_counter),
  R4 conditions captured as tracked triggers (review_conditions),
  R5 precedent from the book (review_precedent),
and returns the answer first ("Do not approve as proposed: 3 critical, 5 major findings; ..."), then the evidence.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

from backend.dealdesk import params, proposals
from backend.dealdesk.proposal_cases import CASES
from backend.dealdesk import review_conditions as RCN
from backend.dealdesk import review_counter as RC
from backend.dealdesk import review_facts as RF
from backend.dealdesk import review_precedent as RP
from backend.dealdesk import review_rules as RR

PACK = {"pack": "P7", "name": "Proposal & Regulatory Response Intelligence"}
SEV_RANK = {"critical": 0, "major": 1, "minor": 2}
MARK_RANK = {"contradicted": 0, "exception": 1, "unverifiable": 2, "supported": 3}
CLEAN_MEMOS = ("DD-01", "DD-08", "DD-12")

_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()
TTL = 600.0


def subjects() -> list[dict[str, Any]]:
    out = [{"id": cid, "kind": "case", "name": c["borrower"], "sector": c["sector"], "rating": c["rating"],
            "amount": sum(f["proposed"] for f in c["facilities"]), "currency": c["currency"], "file": c["file_name"]} for cid, c in CASES.items()]
    for pid, p in sorted(proposals.all_proposals().items()):
        out.append({"id": pid, "kind": "dd", "name": p["obligor"]["name"], "sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"],
                    "amount": p["ask"]["amount"], "currency": p["ask"]["currency"], "file": f"{pid}.docx"})
    return out


# ------------------------------------------------------------------ the answer

def _counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return {s: sum(1 for x in findings if x["severity"] == s) for s in ("critical", "major", "minor")}


def _plural(n: int, w: str) -> str:
    return f"{n} {w}"


def answer(findings: list[dict[str, Any]], counter: dict[str, Any], doa: dict[str, Any]) -> dict[str, Any]:
    n = _counts(findings)
    cps = counter.get("counter_proposals") or []
    if n["critical"]:
        decision, tone = "Do not approve as proposed", "negative"
    elif n["major"]:
        decision, tone = "Approve with conditions", "warning"
    else:
        decision, tone = "Approve as proposed", "positive"
    parts = [f"{n[s]} {s}" for s in ("critical", "major", "minor") if n[s]]
    head = decision + (": " + ", ".join(parts) + f" finding{'s' if sum(n.values()) != 1 else ''}" if parts else ": no findings")
    if cps and decision != "Approve as proposed":
        head += "; " + cps[0]["title"][0].lower() + cps[0]["title"][1:]
    elif decision == "Approve as proposed":
        head += "; every check is supported by the data"
    return {"decision": decision, "tone": tone, "headline": head, "counts": n, "approval": doa["level"],
            "counter_proposal": cps[0]["id"] if cps else None}


def _memo_view(led: dict[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_line: dict[str, list[dict[str, Any]]] = {}
    for c in checks:
        for lid in c.get("line_ids") or []:
            by_line.setdefault(lid, []).append(c)
    sections: list[dict[str, Any]] = []
    for ln in led["lines"]:
        if ln["kind"] == "heading":
            sections.append({"title": ln["section"], "line_id": ln["line_id"], "lines": []})
            continue
        if not sections:
            sections.append({"title": ln["section"], "line_id": ln["line_id"], "lines": []})
        cs = by_line.get(ln["line_id"], [])
        if cs:
            mark = min((c["verdict"] for c in cs), key=lambda v: MARK_RANK[v])
        elif ln.get("claim_ids"):
            mark = "unverifiable"
        else:
            mark = None
        sections[-1]["lines"].append({"line_id": ln["line_id"], "kind": ln["kind"], "text": ln["text"], "mark": mark,
                                      "check_ids": [c["check_id"] for c in cs], "claim_ids": ln.get("claim_ids", []),
                                      "evidence": [{"verdict": c["verdict"], "title": c["title"], "finding": c["finding"],
                                                    "source": "; ".join(e["source"] for e in c.get("evidence") or []) or "Rule"}
                                                   for c in sorted(cs, key=lambda c: MARK_RANK[c["verdict"]])][:4]})
    return [s for s in sections if s["lines"]]


def _features(f: dict[str, Any]) -> dict[str, Any]:
    if f["subject"]["kind"] == "case":
        fin = f["case"]["financials"]
        return {"leverage": fin["net_debt"] / fin["ebitda"], "dscr": fin["ebitda"] / fin["debt_service"],
                "backlog_cover_over_3x": bool(fin.get("backlog") and fin["backlog"] / fin["revenue"] > 3),
                "related_party_over_25pct": bool((fin.get("related_party_share_ca") or fin.get("parent_related_party_share") or 0) > 0.25)}
    m = f.get("metrics") or {}
    return {"leverage": m.get("debt_ebitda_post"), "dscr": m.get("dscr_post"), "watchlist": (f.get("book") or {}).get("watchlist")}


def review(sid: str, refresh: bool = False, with_counter: bool = True) -> dict[str, Any]:
    if not RF.known(sid):
        raise KeyError(sid)
    key = (sid, params.version_tag())
    with _LOCK:
        hit = _CACHE.get(key)
    if hit and not refresh and time.time() - hit[0] < TTL and (hit[1].get("counter") or not with_counter):
        return hit[1]
    t0 = time.time()
    f = RF.facts(sid)
    checks = RR.run(f)
    findings = sorted([c for c in checks if c["verdict"] in ("contradicted", "exception")],
                      key=lambda c: (SEV_RANK.get(c["severity"] or "minor", 3), 0 if c["verdict"] == "contradicted" else 1, c["rule_id"]))
    doa = RR.required_doa(f, checks)
    counter = RC.counter_proposals(sid, checks, RF.is_case(sid)) if with_counter else {"counter_proposals": [], "ask": None}
    triggers = RCN.capture_from(sid, f, checks)
    RCN.upsert(triggers, deal_id=sid)
    RCN.remember_facts(sid, f)
    cond = RCN.listing(sid)
    prec = RP.precedent({"sector": f["subject"]["sector"], "rating": f["subject"]["rating"], "amount_sar": f["subject"]["amount_sar"]}, _features(f))
    led = f["ledger"]
    by_cat = {cat: {v: sum(1 for c in checks if c["category"] == cat and c["verdict"] == v) for v in RR.VERDICTS} for cat in RR.CATEGORIES}
    out = {
        "subject": f["subject"], "as_of": f["as_of"], "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "answer": answer(findings, counter, doa),
        "memo": {"file": (CASES[sid]["file_name"] if RF.is_case(sid) else f"{sid}.docx"), "sections": _memo_view(led, checks),
                 "counts": led["counts"]},
        "claims": led["claims"],
        "findings": findings, "checks": checks, "by_category": by_cat,
        "verdicts": {v: sum(1 for c in checks if c["verdict"] == v) for v in RR.VERDICTS},
        "doa": doa, "counter": counter, "conditions": cond, "precedent": prec,
        "rules": {"version": RR.rulebook()["version"], "count": len(RR.rules()), "file": "data/dealdesk/review/rules.json"},
        "powered_by": {**PACK, "rules": sorted({c["crm_article"] for c in findings if c.get("crm_article")}), "confidence": "High",
                       "trace": f"review/{sid}"},
        "basis": "Claims from the memo; each rule in rules.json run against the books, account conduct, bureau, audited financials and project "
                 "data; counter-proposals priced by the Deal Desk optimiser; conditions tracked from data where a check exists.",
        "seconds": round(time.time() - t0, 2),
    }
    if not RF.is_case(sid):
        _with_engines(sid, out, with_counter)  # R14 E
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def _with_engines(sid: str, out: dict[str, Any], with_counter: bool) -> None:
    """R14 E (K18 #5, K19, K22, K24): a Deal Desk deal's review reads the findings engine — every finding (live rules +
    every dd_review_finding incl. financial quality + capacity + covenant headroom) with result titles and cures, the one
    count source (findings header, chips and memo legend), the verdict naming the critical and major findings, and the
    counter-offer that addresses every critical/major finding first in the counter-proposals."""
    try:
        from backend.dealdesk.findings import counter_offer, deal_findings
        fs = deal_findings(sid)
    except Exception:  # noqa: BLE001 - the engine cannot read this deal: the R11 review stands alone
        return
    out["engine"] = {"findings": fs["findings"], "counts": fs["counts"], "chips": fs["chips"], "verdict": fs["verdict"],
                     "source": fs["source"]}
    v = fs["verdict"]
    out["answer"] = {**out["answer"], "decision": v["decision"], "tone": v["tone"], "headline": v["headline"],
                     "counts": {k: fs["counts"]["by_severity"][k] for k in ("critical", "major", "minor")}}
    out["verdicts"] = dict(fs["counts"]["checks"])
    if not with_counter:
        return
    try:
        co = counter_offer(sid)
    except Exception:  # noqa: BLE001
        return
    if not co.get("needed", True) and not co["cures"]:
        return  # the ask clears with no critical or major finding: no counter-proposal
    e, st = co["economics"], co["structure"]
    ask_m = (out.get("counter") or {}).get("ask") or {}
    title = ("Counter-offer: amount to capacity, priced to the hurdle, every critical and major finding cured or flagged"
             if co.get("needed", True) else "As proposed, with every critical and major finding cured by conditions")
    cp = {"id": "CP-E", "title": title,
          "terms": [st["amount_note"], "Priced by " + st["method"]],
          "structure": {"amount": st["terms"]["amount"], "currency": st["terms"]["currency"], "tenor_years": st["terms"]["tenor_years"],
                        "margin_bps": st["terms"]["margin_bps"], "commission_bps": st["terms"].get("commission_bps"),
                        "funded_share_pct": st["terms"].get("funded_share_pct"), "cash_margin_pct": st["terms"].get("cash_margin_pct"),
                        "covenant_package": st["terms"].get("covenant_package")},
          "changes": st["changes"], "raroc": e["lifetime_raroc"], "hurdle": e["hurdle"], "clears_hurdle": e["clears_hurdle"],
          "sva": e["sva"], "ecl_day1": None, "rwa": e["rwa_y1"], "amount": st["terms"]["amount"],
          "vs_ask": {"raroc": (e["lifetime_raroc"] or 0) - (ask_m.get("raroc") or 0), "sva": e["sva"] - (ask_m.get("sva") or 0), "ecl_day1": None},
          "approval": co["approval"]["level"], "approval_rule": co["approval"]["rule"], "soft_breaches": [], "hard_breaches": [],
          "method": "optimiser" if "optimiser" in st["method"] else "engine", "method_text": st["method"],
          "conditions_precedent": co["conditions_precedent"], "forward_risk": None,
          "cures": co["cures"], "not_curable": co["not_curable"], "headline": co["headline"],
          "basis": "R14 findings engine counter-offer (backend.dealdesk.findings.counter): capacity engine + optimiser + cures"}
    from backend.dealdesk.deposit_requirement.docs import review_counter_lines  # Round D: the counter-proposal's deposit term
    dl, dcp = review_counter_lines(sid, st["terms"])
    cp["terms"] = cp["terms"] + dl
    cp["conditions_precedent"] = list(cp["conditions_precedent"] or []) + dcp
    cps = (out.get("counter") or {}).get("counter_proposals") or []
    n_open = sum(1 for c in co["cures"])
    for c in cps:  # R11 packages fix one lever: say what they leave open
        c["leaves_open"] = n_open
        c["note"] = f"Fixes {c['title'].lower()} only; leaves {n_open} critical and major findings to the conditions."
    out.setdefault("counter", {})["counter_proposals"] = [cp] + cps
    out["answer"]["counter_proposal"] = "CP-E"


def quick(sid: str) -> dict[str, Any]:
    """Rules only (no optimiser), for listings."""
    f = RF.facts(sid)
    checks = RR.run(f)
    findings = [c for c in checks if c["verdict"] in ("contradicted", "exception")]
    doa = RR.required_doa(f, checks)
    a = answer(findings, {"counter_proposals": []}, doa)
    if not RF.is_case(sid):  # R14 E: the listing shows the same decision and counts as the Review (findings engine)
        try:
            from backend.dealdesk.findings import deal_findings
            fs = deal_findings(sid, with_cures=False)
            v = fs["verdict"]
            a = {**a, "decision": v["decision"], "tone": v["tone"],
                 "counts": {k: fs["counts"]["by_severity"][k] for k in ("critical", "major", "minor")}}
        except Exception:  # noqa: BLE001 - the rule-book decision stands
            pass
    return {"id": sid, "decision": a["decision"], "tone": a["tone"], "counts": a["counts"], "approval": doa["level"],
            "contradicted": sum(1 for c in checks if c["verdict"] == "contradicted"), "checks": len(checks), "_f": f, "_checks": checks}


def capture_all(ids: list[str] | None = None) -> dict[str, Any]:
    """Capture every subject's triggers (the landing's 'Conditions due' needs them before any review is opened)."""
    n = 0
    for sid in ids or [s["id"] for s in subjects()]:
        try:
            q = quick(sid)
        except Exception:  # noqa: BLE001 - a subject whose evidence cannot be read is skipped
            continue
        tr = RCN.capture_from(sid, q["_f"], q["_checks"])
        RCN.upsert(tr, deal_id=sid)
        RCN.remember_facts(sid, q["_f"])
        n += len(tr)
    return {"captured": n}


_BOOT = {"done": False}
_BOOT_LOCK = threading.Lock()


def ensure_conditions() -> None:
    with _BOOT_LOCK:
        if _BOOT["done"]:
            return
        have = {t["deal_id"] for t in RCN.stored()}
        missing = [s["id"] for s in subjects() if s["id"] not in have]
        if missing:
            capture_all(missing)
        _BOOT["done"] = True


# ------------------------------------------------------------------ committee decision sheet (R6)

def sheet(sid: str) -> dict[str, Any]:
    r = review(sid)
    s = r["subject"]
    ccy = s["currency"]
    if RF.is_case(sid):
        c = CASES[sid]
        ask = {"lines": [{"name": x["name"], "existing": x["existing"], "proposed": x["proposed"]} for x in c["facilities"]],
               "summary": c["request_summary"], "total_existing": sum(x["existing"] for x in c["facilities"]),
               "total_proposed": sum(x["proposed"] for x in c["facilities"]), "recommendation": c["recommendation"]}
    else:
        p = proposals.get(sid)
        a = p["ask"]
        ask = {"lines": [{"name": a["facility_type"].replace("_", " ").capitalize(), "existing": p["obligor"].get("existing_exposure_sar_mn", 0.0),
                          "proposed": a["amount"]}],
               "summary": [p["purpose"]], "total_existing": p["obligor"].get("existing_exposure_sar_mn", 0.0), "total_proposed": a["amount"],
               "recommendation": "As requested"}
    sev = {k: [{"rule_id": x["rule_id"], "title": x["title"], "finding": x["finding"], "verdict": x["verdict"], "ref": x["crm_article"],
                "policy": x["policy_ref"]} for x in r["findings"] if x["severity"] == k] for k in ("critical", "major", "minor")}
    cps = r["counter"]["counter_proposals"]
    return {"subject": s, "currency": ccy, "as_of": r["as_of"], "ask": ask, "answer": r["answer"], "findings": sev, "doa": r["doa"],
            "counter_proposal": cps[0] if cps else None, "alternatives": cps[1:],
            "conditions": [{"what": t["what"], "kind": t["kind"], "due": t["due_text"], "owner": t["owner"], "status": t["status"]}
                           for t in r["conditions"]["items"]],
            "precedent": r["precedent"]["line"], "verdicts": r["verdicts"], "powered_by": r["powered_by"]}


def sheet_docx(sid: str, generated_by: str = "") -> tuple[bytes, str]:
    """The one-page committee decision sheet in Word (house style, no cover page)."""
    import re

    from backend.house_style import Meta
    from backend.house_style import docx as hd
    sh = sheet(sid)
    s, a = sh["subject"], sh["answer"]
    ccy = sh["currency"]
    meta = Meta(f"Committee decision sheet · {s['name']}", book="corporate", period=sh["as_of"], subject=f"{sid} · {s['sector']} · {s['rating']}",
                generated_by=generated_by, reference=f"{sid}-CDS")
    from docx.shared import Cm
    doc = hd.document(meta, kind="Committee decision sheet", subtitle=f"{s['name']} · {sid}", cover=False)
    sec = doc.sections[0]
    sec.top_margin, sec.bottom_margin = Cm(1.7), Cm(1.4)
    hd.heading(doc, f"Committee decision sheet: {s['name']}")
    hd.para(doc, f"{sid} · {s['sector']} · rating {s['rating']}{(' · ' + s['tier']) if s.get('tier') else ''} · as of {sh['as_of']} · "
                 f"approval level **{sh['doa']['level']}** ({sh['doa']['binding']['detail']})", size=8)
    hd.para(doc, f"**{a['headline']}.**", size=10)
    ask = sh["ask"]
    hd.heading(doc, "The ask", 2)
    hd.para(doc, f"Limits {ccy} {ask['total_existing']:,.1f}m → {ccy} {ask['total_proposed']:,.1f}m. " + "; ".join(x for x in ask["summary"] if not x.lower().startswith("total limits"))
            + f". Relationship recommendation: {ask['recommendation']}.", size=8)
    hd.heading(doc, "Findings", 2)
    crit = sh["findings"]["critical"]
    if crit:
        hd.table(doc, ["Critical finding", "Reference"], [[x["finding"], x["ref"] or x["policy"]] for x in crit], widths=[14.2, 2.8], gap=False, size=6.5)
    for k in ("major", "minor"):
        if sh["findings"][k]:
            hd.para(doc, f"**{k.capitalize()} ({len(sh['findings'][k])}):** " + " · ".join(x["title"] for x in sh["findings"][k]) + ".", size=7)
    if not any(sh["findings"].values()):
        hd.para(doc, "No findings: every check is supported by the data.", size=8)
    hd.para(doc, f"**Precedent:** {sh['precedent']}", size=7.5)
    cp = sh["counter_proposal"]
    if cp:
        hd.heading(doc, "Counter-proposal", 2)
        hd.para(doc, f"**{cp['title']}.** {ccy} {cp['amount']:,.1f}m; lifetime RAROC {cp['raroc']:.1%} against a {cp['hurdle']:.1%} hurdle; "
                     f"SVA {ccy} {cp['sva']:,.2f}m; Day-1 ECL {ccy} {cp['ecl_day1']:,.2f}m. Terms: " + "; ".join(cp["terms"]) + ".", size=7.5)
        if sh["alternatives"]:
            hd.para(doc, "Alternatives: " + "; ".join(f"{x['title']} (RAROC {x['raroc']:.1%}, {ccy} {x['amount']:,.1f}m)" for x in sh["alternatives"]) + ".", size=7)
    if sh["conditions"]:
        hd.heading(doc, "Conditions", 2)
        kind = {"CP": "CP", "covenant": "Covenant", "watch": "Watch"}
        main = [c for c in sh["conditions"] if c["kind"] != "watch"]
        watch = [c for c in sh["conditions"] if c["kind"] == "watch"]
        if main:
            hd.table(doc, ["Condition precedent or covenant", "Due · owner · status"],
                     [[f"{kind.get(c['kind'], c['kind'])}: {c['what']}", f"{c['due']} · {c['owner']} · {c['status']}"] for c in main],
                     widths=[10.5, 6.5], gap=False, size=6.5)
        if watch:
            hd.para(doc, "**Watch items:** " + "; ".join(f"{c['what']} ({c['due']}, {c['owner']})" for c in watch) + ".", size=7)
    safe = re.sub(r"[^\w-]+", "-", f"Committee-sheet-{sid}-{s['name']}")[:80].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"


# ------------------------------------------------------------------ RM drafting: "Draft from data" (R6)

JUDGEMENT = ("Business case and purpose", "Risks and mitigants", "Recommendation")


def draft(sid: str) -> dict[str, Any]:
    """The factual memo sections filled from data, each figure with its source; the judgement sections left to the RM."""
    f = RF.facts(sid)
    secs: list[dict[str, Any]] = []
    if f["subject"]["kind"] == "dd":
        p, o = f["dd"], f["obligor"]
        fx_ccy = p["ask"]["currency"]
        book = f.get("book")
        ex_rows = [[x["facility_id"], x["product"].replace("_", " "), f"{x['limit']:,.2f}", f"{x['ead']:,.2f}", f"Stage {x['stage']}"]
                   for x in o.get("existing_facilities") or []]
        secs.append({"key": "exposure", "title": "Existing exposure", "kind": "fact", "source": "Corporate book, " + "2026Q2",
                     "text": (f"{o['name']} has {len(ex_rows)} facilities with the bank, EAD SAR {book['ead']:,.2f}m at 2026Q2; highest stage "
                              f"{book['stage_max']}, maximum DPD over 4 quarters {book['dpd_max_4q']} days.") if book else
                             f"{o['name']} is new to the bank: no existing exposure.",
                     "table": {"header": ["Facility", "Product", "Limit (SAR m)", "EAD (SAR m)", "Stage"], "rows": ex_rows} if ex_rows else None})
        cd = f.get("conduct")
        secs.append({"key": "conduct", "title": "Account conduct", "kind": "fact", "source": (cd or {}).get("source", "Deposits domain"),
                     "text": (f"Over the last {cd['months']} months: {cd['returned_cheques']} returned cheques "
                              f"(SAR {cd['returned_cheques_sar_mn']:,.2f}m), {cd['excess_days']} excess days.") if cd else
                             "No account history with the bank.", "table": None})
        secs.append({"key": "bureau", "title": "Bureau", "kind": "fact", "source": "SIMAH flag on the proposal record",
                     "text": f"SIMAH status: {o.get('simah_flag', 'not available')}.", "table": None})
        yrs = p["financials"]["years"]
        rows = [[k.replace("_", " ").capitalize()] + [f"{y.get(k):,.2f}" if isinstance(y.get(k), (int, float)) else "" for y in yrs]
                for k in ("revenue", "ebitda", "total_debt", "debt_service", "net_worth")]
        rows.append(["EBITDA margin"] + [f"{y['ebitda'] / y['revenue']:.1%}" for y in yrs])
        rows.append(["Debt / EBITDA (x)"] + [f"{y['total_debt'] / y['ebitda']:.2f}" for y in yrs])
        rows.append(["DSCR (x)"] + [f"{y['ebitda'] / y['debt_service']:.2f}" if y.get("debt_service") else "" for y in yrs])
        last = f["fin_last"]
        acts = [y for y in yrs if y["kind"] == "actual"]
        g = (acts[-1]["revenue"] / acts[0]["revenue"]) ** (1 / (len(acts) - 1)) - 1 if len(acts) >= 2 and acts[0]["revenue"] else None
        secs.append({"key": "financials", "title": "Financial spreading (SAR m)", "kind": "fact", "source": "Financial spreading on the proposal record",
                     "text": f"Latest actual year {last['year']}: revenue SAR {last['revenue']:,.2f}m, EBITDA SAR {last['ebitda']:,.2f}m "
                             f"({last['ebitda'] / last['revenue']:.1%} margin), debt / EBITDA {last['total_debt'] / last['ebitda']:.2f}x"
                             + (f"; revenue growth {g:.1%} a year over the actuals." if g is not None else "."),
                     "table": {"header": ["Item"] + [str(y["year"]) + ("" if y["kind"] == "actual" else " P") for y in yrs], "rows": rows}})
        cols = f["collateral"]
        amt = float(p["ask"]["amount"])
        secs.append({"key": "collateral", "title": "Collateral and guarantees", "kind": "fact", "source": "Security on the proposal record",
                     "text": (f"Collateral pledged {fx_ccy} {sum(c['value'] for c in cols if c.get('pledged_in_ask')):,.2f}m against a {fx_ccy} "
                              f"{amt:,.2f}m ask ({sum(c['value'] for c in cols if c.get('pledged_in_ask')) / amt:.0%} cover).") if cols else
                             "No collateral pledged.",
                     "table": {"header": ["ID", "Type", "Value", "Valuation date"], "rows": [[c["collateral_id"], c["type"].replace("_", " "),
                                                                                              f"{c['value']:,.2f}", c["valuation_date"]] for c in cols]} if cols else None})
    else:
        c = f["case"]
        fin = c["financials"]
        ev = f["ev"]
        secs.append({"key": "exposure", "title": "Existing exposure", "kind": "fact", "source": ev["sources"].get("los", "LOS"),
                     "text": f"Existing limits AED {sum(x['existing'] for x in c['facilities']):,.1f}m across {sum(1 for x in c['facilities'] if x['existing'] > 0)} lines."
                             + (f" Group exposure after the request AED {c['group_cap']['group_exposure_after']:,.1f}m against a cap of AED {c['group_cap']['existing']:,.0f}m." if c.get("group_cap") else ""),
                     "table": {"header": ["Line", "Existing (AED m)", "Proposed (AED m)"], "rows": [[x["name"], f"{x['existing']:,.1f}", f"{x['proposed']:,.1f}"] for x in c["facilities"]]}})
        d = c["deposits"]
        secs.append({"key": "conduct", "title": "Account conduct", "kind": "fact", "source": ev["sources"].get("conduct", "Account conduct"),
                     "text": f"Average balance AED {d['avg_balance']:,.1f}m; turnover {d['turnover_to_revenue']:.0%} of revenue"
                             + (f"; routing {ev['routing']['achieved_x']:.2f}x against a {ev['routing']['required_x']:.1f}x undertaking." if ev.get("routing") else "."),
                     "table": None})
        b = ev["bureau"]
        secs.append({"key": "bureau", "title": "Bureau", "kind": "fact", "source": ev["sources"].get("bureau", "Bureau"),
                     "text": "; ".join([f"{b.get('affiliate_returned_cheques', 0)} returned cheques in the group"]
                                       + ([f"CBRBR other-bank limits AED {b['cbrbr_other_bank_limits']:,.0f}m against AED "
                                           f"{b['client_reported_other_bank_limits']:,.0f}m reported by the client"] if b.get("cbrbr_other_bank_limits") else [])
                                       + ([f"{len(b['group_entities_loss'])} group entities at Loss"] if b.get("group_entities_loss") else [])) + ".",
                     "table": None})
        secs.append({"key": "financials", "title": "Financial spreading (AED m)", "kind": "fact", "source": ev["sources"].get("audited", "Audited accounts"),
                     "text": f"Revenue AED {fin['revenue']:,.1f}m, EBITDA AED {fin['ebitda']:,.1f}m ({fin['ebitda'] / fin['revenue']:.1%}), "
                             f"net debt / EBITDA {fin['net_debt'] / fin['ebitda']:.2f}x, DSCR {fin['ebitda'] / fin['debt_service']:.2f}x.",
                     "table": {"header": ["Item", "Value"], "rows": [[k.replace("_", " ").capitalize(), f"{v:,.2f}" if isinstance(v, float) and v > 1 else (f"{v:.1%}" if isinstance(v, float) else str(v))]
                                                                       for k, v in fin.items() if isinstance(v, (int, float))]}})
        sec = ev["security"]
        secs.append({"key": "collateral", "title": "Collateral and guarantees", "kind": "fact", "source": ev["sources"].get("security", "Security register"),
                     "text": f"Cash margin {sec['cash_margin_pct']:.0f}%; guarantees {sec['guarantee_expiry']} in the {sec['guarantee_format']} format; "
                             f"corporate guarantee {sec['corporate_guarantee_perfection']}"
                             + (f"; legal opinion dated {sec['legal_opinion_date']}." if sec.get("legal_opinion_date") else "."), "table": None})
    for t in JUDGEMENT:
        secs.append({"key": t.lower().split()[0], "title": t, "kind": "judgement", "source": "For the RM",
                     "text": "", "table": None})
    return {"subject": f["subject"], "sections": secs, "facts_filled": sum(1 for s in secs if s["kind"] == "fact"),
            "basis": "Factual sections filled from the books, account conduct, bureau, financial spreading and the security record; "
                     "judgement sections are left to the RM."}


def draft_docx(sid: str, generated_by: str = "") -> tuple[bytes, str]:
    import re

    from backend.house_style import Meta
    from backend.house_style import docx as hd
    d = draft(sid)
    s = d["subject"]
    meta = Meta(f"Credit proposal · {s['name']}", book="corporate", period=d["subject"]["as_of"], subject=f"{sid} · {s['sector']} · {s['rating']}",
                generated_by=generated_by, reference=f"{sid}-DRAFT")
    doc = hd.document(meta, kind="Credit proposal (draft from data)", subtitle=f"{s['name']} · {sid}", cover="block")
    for i, sec in enumerate(d["sections"], start=1):
        hd.heading(doc, f"{i}. {sec['title']}")
        if sec["kind"] == "judgement":
            hd.note(doc, "For the relationship manager to complete.")
            continue
        hd.para(doc, sec["text"])
        if sec.get("table"):
            hd.table(doc, sec["table"]["header"], sec["table"]["rows"], gap=False, size=7.5)
        hd.note(doc, f"Source: {sec['source']}")
    safe = re.sub(r"[^\w-]+", "-", f"Draft-{sid}-{s['name']}")[:80].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"
