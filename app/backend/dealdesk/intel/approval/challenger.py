"""Committee challenger (R14 backlog #1, R13 Session IA).

The 5-7 questions a credit committee will ask about this deal, each answered from data with its source, and the
questions the proposal avoids.

Method (deterministic writer, N3)
  Candidate questions come from eight sources, each scored for how hard a committee would press it:
    returns      engine.analyse: lifetime RAROC against the hurdle, breakeven margin (engine.breakeven_margin);
                 when it clears, the downgrade notches before it stops clearing (optimizer.robustness)
    limits       every hard or policy breach after the deal (constraints), with the approval level (DoA)
    stress       the latest dd_stress_result run: the mildest severity that still breaks something, what breaks,
                 the verdict and tier (stress2.verdict rule), and the named triggers of dd_monitoring_plan
    findings     open critical and high dd_review_finding rows, with their evidence relation
    weaknesses   dd_swot weaknesses and threats with no covering mitigant (covered_flag 0)
    group        dd_group_exposure (group total) and the connected-group limit after the deal
    conditions   dd_condition rows set by an earlier committee (prior_committee_ref) that were not complied or
                 breached, and the earlier committee decision (dd_reference)
    precedent    conditions earlier committees set on similar deals (similarity as in decision consistency) that
                 this proposal does not carry
  plus the security register (dd_security notes) and open RM queries (dd_query).
  The top questions by score are kept, at most two per source, five to seven in all. A question counts as avoided
  when nothing on file answers it: no covering mitigant, no condition, no query raised and no monitoring trigger.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk import engine, optimizer
from backend.dealdesk.intel.approval import common as C

SCORE = {"critical": 92, "high": 76}
OPS = {">=": "at least ", "<=": "at most ", ">": "above ", "<": "below ", "==": ""}
MAX_PER_SOURCE = 2


def _q(qid: str, source: str, score: float, question: str, answer: str, evidence: list[dict[str, Any]],
       avoided: bool, avoided_reason: str = "", asks_for: str = "") -> dict[str, Any]:
    return {"id": qid, "source": source, "score": score, "question": question, "answer": answer, "evidence": [e for e in evidence if e],
            "avoided": avoided, "avoided_reason": avoided_reason if avoided else "", "asks_for": asks_for}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower())}


def _mentioned(topic_words: set[str], texts: list[str]) -> bool:
    return any(len(topic_words & _words(t)) >= 2 for t in texts)


def _returns(pid: str, p: dict[str, Any], a: dict[str, Any], swot: list[dict[str, Any]]) -> list[dict[str, Any]]:
    m, t = a["metrics"], a["terms"]
    raroc = C.efig(pid, m["lifetime_raroc"], "share", "Lifetime RAROC")
    hurdle = C.efig(pid, m["hurdle"], "share", "Hurdle")
    if not m["clears_hurdle"]:
        be = None
        try:
            be = engine.breakeven_margin(p, t)
        except Exception:  # noqa: BLE001
            be = None
        cov = [s for s in swot if s.get("topic") == "returns"]
        covered = any(int(s.get("covered_flag") or 0) == 1 for s in cov)
        ans = (f"Lifetime RAROC is {C.pct(m['lifetime_raroc'])} against a hurdle of {C.pct(m['hurdle'])} (SVA {C.mn(m['sva'], t['currency'], 2)}). "
               + (f"The margin that brings it to the hurdle is {be:,.0f} bps against {float(t['margin_bps']):,.0f} bps asked." if be is not None
                  else "Pricing alone does not move it to the hurdle on this structure (unfunded or no margin lever)."))
        ev = [raroc, hurdle, C.efig(pid, be, "bps", "Breakeven margin", "engine.breakeven_margin") if be is not None else None]
        return [_q("returns", "returns", 90, f"Why bring a deal that earns {C.pct(m['lifetime_raroc'])} against a {C.pct(m['hurdle'])} hurdle?",
                   ans, ev, not covered, "The proposal names no pricing or structure fix for the shortfall.", "Reverse solver: the smallest change that clears")]
    n = optimizer.robustness(p, t)
    ans = (f"Lifetime RAROC {C.pct(m['lifetime_raroc'])} against {C.pct(m['hurdle'])}; it still clears after {n} notch"
           f"{'es' if n != 1 else ''} of downgrade (rating {p['obligor']['internal_rating']}).")
    return [_q("returns", "returns", 40 if n >= 2 else 62, "How much room is there before this stops paying for its risk?", ans,
               [raroc, hurdle, C.efig(pid, n, "notches", "Downgrade notches before the hurdle", "optimizer.robustness")], False)]


def _limits(pid: str, a: dict[str, Any], conds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    texts = [c["text"] for c in conds]
    for c in C.hard_breaches(a) + C.soft_breaches(a):
        hard = c["kind"] == "hard"
        val = c["value"] if not isinstance(c["value"], float) else round(c["value"], 2)
        lab = c["label"] if "after the deal" in c["label"] else f"{c['label']} after the deal"
        lim = c["limit"] if not isinstance(c["limit"], float) else round(c["limit"], 2)
        ans = (f"{lab} is {val} against {lim} {c['unit']} ({c['basis']}). "
               f"Approval sits with {a['approval']['level']}" + ("; a hard limit needs an exception or a smaller deal." if hard else "; a policy breach needs the exception noted."))
        words = _words(c["label"])
        out.append(_q(f"limit:{c['name']}", "limits", 95 if hard else 70,
                      f"The {c['label'][0].lower() + c['label'][1:] if not c['label'][:4].isupper() else c['label']} {'limit' if hard else 'policy limit'} is breached: how is it cured, and who signs the exception?",
                      ans, [C.efig(pid, c["value"], c["unit"], c["label"]) if isinstance(c["value"], (int, float)) else None,
                            C.efig(pid, c["limit"], c["unit"], "Limit") if isinstance(c["limit"], (int, float)) else None],
                      not _mentioned(words, texts), "No condition or exception for this limit is on file.", "Reverse solver"))
    return out


def _stress(pid: str, conds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st = C.latest_stress(pid)
    if not st["run_id"]:
        return [_q("stress", "stress", 50, "Has the deal been stressed?", "No stress run is recorded in Data Domains (dd_stress_result) for this deal.",
                   [], True, "No stress result on file.")]
    sev = st["worst_breaking_severity"]
    br = [r for r in st["breaking"] if r["severity"] == sev] if sev != "none" else []
    breaks = sorted({b for r in br for b in str(r["breaks"]).split(";") if b})
    plans = C.rows("dd_monitoring_plan", proposal_id=pid)
    trig = [t for pl in plans for t in (pl.get("named_triggers") or []) if isinstance(t, dict)]
    covmetrics = {str(c.get("trigger_metric") or "") for c in conds}
    covered = bool(trig) or any(b in " ".join(covmetrics) for b in breaks)
    ev = [C.rfig("dd_stress_result", r, "raroc_pct", "%", f"RAROC under {r['scenario_id']}") for r in br[:3]]
    if sev == "none":
        ans = f"Nothing breaks up to severe stress (run {st['run_id']}); verdict {st['verdict']}, monitoring tier {st['tier']}."
        return [_q("stress", "stress", 25, "What breaks under stress?", ans, ev, False)]
    names = {x["scenario_id"]: x.get("label") or x["scenario_id"] for x in C.rows("dd_stress_scenario")}
    words = {"dscr": "DSCR", "leverage": "leverage", "covenant": "covenants", "limit": "limits", "rating": "rating", "stage2": "Stage 2",
             "hurdle": "the hurdle", "ltv": "LTV", "raroc": "RAROC"}
    ans = (f"It breaks first at {sev} severity ({len(br)} scenario{'s' if len(br) != 1 else ''}: {', '.join(sorted({names.get(r['scenario_id'], r['scenario_id']) for r in br})[:4])}) "
           f"on {', '.join(words.get(b, b) for b in breaks)}. Verdict under the R12 rule: {st['verdict']}, tier {st['tier']}."
           + (f" Named triggers on file: {', '.join(t.get('label') or t.get('metric', '') for t in trig)}." if trig else ""))
    return [_q("stress", "stress", {"mild": 86, "moderate": 66, "severe": 36}[sev], f"It breaks at {sev} stress: what protects the bank when it does?",
               ans, ev, not covered, "No covenant, trigger or monitoring plan covers the metric that breaks.", "Covenant on the breaking metric")]


def _findings(pid: str, fs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in sorted([f for f in fs if f.get("status") == "open" and f.get("severity") in SCORE],
                    key=lambda f: (C.SEV_ORDER.get(f["severity"], 9), f["finding_id"])):
        groups.setdefault(f["title"], []).append(f)
    for title, grp in groups.items():
        f = grp[0]
        ev = [C.rfig("dd_review_finding", g, "evidence_value", g.get("evidence_unit") or "", g["title"])
              if isinstance(g.get("evidence_value"), (int, float)) else {"value": None, "source": C.row_source("dd_review_finding", g, "finding_text")}
              for g in grp[:3]]
        body = " ".join(g["finding_text"] for g in grp[:3])
        ids = ", ".join(g["finding_id"] for g in grp)
        q = _q(f"finding:{f['finding_id']}", "findings", SCORE[f["severity"]], f"{title}: what is the answer?",
               f"{body} Open {f['severity']} finding{'s' if len(grp) > 1 else ''}, raised in the review.", ev,
               not any(g.get("query_id") or g.get("condition_id") for g in grp), "Open, with no query to the RM and no condition attached.")
        q["category"] = f.get("category") or ""
        out.append(q)
    return out


def _capacity(pid: str, p: dict[str, Any], a: dict[str, Any]) -> list[dict[str, Any]]:
    m = a["metrics"]
    cov = {str(c.get("type", "")).lower(): c.get("threshold") for c in (p.get("security") or {}).get("covenants") or []}
    ds, lev = m.get("dscr_post"), m.get("debt_ebitda_post")
    if ds is None or lev is None or ds != ds or lev != lev or ds == float("inf"):
        return []
    dmin = cov.get("dscr") or 1.2
    lmax = next((v for k, v in cov.items() if "ebitda" in k), None) or 4.0
    tight = ds < dmin * 1.15 or lev > lmax * 0.9
    ans = (f"After the deal DSCR is {ds:.2f}x (covenant {dmin:.2f}x) and Debt/EBITDA {lev:.2f}x (covenant {lmax:.2f}x), "
           "on the latest actual year of the proposal financials.")
    return [_q("capacity", "capacity", 64 if tight else 34, "Can the client carry this debt, and how much covenant headroom is left?", ans,
               [C.efig(pid, ds, "x", "DSCR after the deal"), C.efig(pid, lev, "x", "Debt/EBITDA after the deal")], False)]


def _book_precedent(pid: str, p: dict[str, Any], a: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.review_precedent import precedent
        r = precedent({"sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"], "amount_sar": a["metrics"]["amount_sar_mn"]},
                      {"leverage": a["metrics"].get("debt_ebitda_post"), "dscr": a["metrics"].get("dscr_post")})
    except Exception:  # noqa: BLE001 - the corporate book is optional evidence
        return []
    h4 = next((h for h in r.get("horizons", []) if h["quarters"] == 4), None)
    if not h4 or not h4["N"]:
        return []
    src = {"domain": "cockpit", "relation": "corp_facility_quarter", "key": {}, "column": "stage", "window": h4["window"], "match": h4["match"]}
    worse = (h4["stage2_rate"] or 0) > (h4["book_stage2_rate"] or 0) * 1.25
    return [_q("book_precedent", "precedent", 58 if worse else 32, "How have similar borrowers in our book performed?",
               r["line"], [{"value": h4["stage2"], "unit": f"of {h4['N']} borrowers", "source": src, "label": "Reached Stage 2 within 4 quarters"},
                           {"value": h4["book_stage2_rate"], "unit": "share", "source": src, "label": "Book Stage 2 rate"}], False)]


def _weak(pid: str, swot: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in swot:
        if s.get("quadrant") not in ("W", "T") or int(s.get("covered_flag") or 0) == 1 or s.get("topic") == "returns":
            continue
        out.append(_q(f"swot:{s['swot_id']}", "weaknesses", 60 if s["quadrant"] == "W" else 55,
                      f"{'Weakness' if s['quadrant'] == 'W' else 'Threat'}: {s['text'].rstrip('.')}. What mitigates it?",
                      f"No covering mitigant is recorded. {('Suggested in the SWOT: ' + s['mitigant_text']) if s.get('mitigant_text') else ''}".strip()
                      ,
                      [{"value": None, "source": C.row_source("dd_swot", s, "text")}], True, "The SWOT marks it as not covered."))
    return out


def _group(pid: str, p: dict[str, Any], a: dict[str, Any]) -> list[dict[str, Any]]:
    gx = C.rows("dd_group_exposure", proposal_id=pid)
    gc = next((c for c in a["constraints"] if c["name"] == "group_connected"), None)
    if not gx and not gc:
        return []
    ev = [C.rfig("dd_group_exposure", r, "total_proposed_mn", "SAR m", r["entity_name"]) for r in gx[:4]]
    tot = sum(float(r.get("total_proposed_mn") or 0) for r in gx)
    parts = []
    if gx:
        parts.append(f"Group facilities proposed across {len(gx)} entit{'ies' if len(gx) != 1 else 'y'}: SAR {tot:,.1f}m (dd_group_exposure).")
    score = 30
    if gc:
        ev.append(C.efig(pid, gc["value"], gc["unit"], "Connected group EAD after the deal"))
        ev.append(C.efig(pid, gc["limit"], gc["unit"], "Connected group limit"))
        parts.append(f"Connected-group exposure after the deal {gc['value']:,.1f} against {gc['limit']:,.1f} {gc['unit']} ({gc['basis']}).")
        head = (gc["headroom"] or 0) / gc["limit"] if gc["limit"] else 1
        score = 82 if gc["status"] == "breach" else 52 if head < 0.2 else 30
    return [_q("group", "group", score, f"What does the bank have on the {p['obligor'].get('group_name') or 'group'} in total, and how close is the cap?",
               " ".join(parts), ev, gc is not None and gc["status"] == "breach", "The group cap is breached and no cap increase is on file.")]


def _history(pid: str, conds: list[dict[str, Any]], queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    qtexts = [f"{q.get('subject', '')} {q.get('body', '')}" for q in queries]
    for c in conds:
        if not c.get("prior_committee_ref") or c.get("status") not in ("not_complied", "breached"):
            continue
        thr = c.get("trigger_threshold")
        mv = c.get("measured_value")
        ans = (f"Set by {c['set_by']} ({c['prior_committee_ref']}): \"{c['text']}\" Status {c['status'].replace('_', ' ')}"
               + (f": measured {mv} against {OPS.get(c.get('trigger_operator') or '', '')}{thr} at {c.get('measured_at')}." if mv is not None and thr is not None else "."))
        ev = [C.rfig("dd_condition", c, "measured_value", "", "Measured") if isinstance(mv, (int, float)) else None,
              C.rfig("dd_condition", c, "trigger_threshold", "", "Threshold") if isinstance(thr, (int, float)) else None]
        ev = [e for e in ev if e] or [{"value": None, "source": C.row_source("dd_condition", c, "status")}]
        out.append(_q(f"condition:{c['condition_id']}", "conditions", 88,
                      f"The committee set \"{c['text'].rstrip('.')}\" last time and it was not met. Why renew on the same terms?", ans, ev,
                      not _mentioned(_words(c["text"]), qtexts), "The proposal does not explain the missed condition and no query asks for it."))
    for r in C.rows("dd_reference", proposal_id=pid):
        if r.get("kind") == "committee_decision" and not out:
            out.append(_q(f"reference:{r['ref_id']}", "conditions", 45, f"What did the committee decide last time ({r['ref_no']}), and what has changed?",
                          f"{r['ref_no']} ({r['ref_date']}, {r['authority']}): {r['text']}",
                          [C.rfig("dd_reference", r, "amount_mn", "SAR m", "Approved amount") if r.get("amount_mn") is not None
                           else {"value": None, "source": C.row_source("dd_reference", r, "text")}], False))
    return out


def _precedent(pid: str, conds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.dealdesk.intel.approval import consistency as K
    feats = K.features()
    me = feats.get(pid)
    if not me:
        return []
    have = {c.get("kind") for c in conds} | {str(c.get("trigger_metric") or "") for c in conds}
    mine_words = [c["text"] for c in conds]
    cands = []
    for c in C.rows("dd_condition"):
        if c["proposal_id"] == pid or not c.get("prior_committee_ref"):
            continue
        f = feats.get(c["proposal_id"])
        if not f:
            continue
        s = K.similarity(me, f)
        if s < 0.3 or c.get("trigger_metric") in have or _mentioned(_words(c["text"]), mine_words):
            continue
        cands.append((s, c, f))
    cands.sort(key=lambda x: (-x[0], x[1]["condition_id"]))
    out = []
    seen = set()
    for s, c, f in cands:
        if c["kind"] in seen:
            continue
        seen.add(c["kind"])
        out.append(_q(f"precedent:{c['condition_id']}", "precedent", 50 + 10 * s,
                      f"On a similar deal ({c['proposal_id']}, {f['obligor']}) the committee required \"{c['text'].rstrip('.')}\". Why not here?",
                      f"{c['set_by']} set it ({c['prior_committee_ref']}, {c['kind']}) on {c['proposal_id']} ({f['sector']}, {f['rating']}, "
                      f"similarity {s:.2f}). This proposal carries no {c['kind']} condition of that kind.",
                      [{"value": round(s, 4), "unit": "similarity", "source": C.row_source("dd_condition", c, "text")}], True,
                      "The proposal carries no equivalent condition."))
        if len(out) == 2:
            break
    return out


def _security(pid: str) -> list[dict[str, Any]]:
    out = []
    for r in C.rows("dd_security", proposal_id=pid):
        issue = r.get("note") or (f"perfection {r['perfection_status']}" if r.get("perfection_status") not in (None, "", "perfected") else "")
        if not issue:
            continue
        ev = [C.rfig("dd_security", r, "net_worth_mn", "SAR m", "Net worth") if r.get("net_worth_mn") is not None else
              C.rfig("dd_security", r, "amount_mn", "SAR m", "Amount") if r.get("amount_mn") is not None else None]
        out.append(_q(f"security:{r['security_id']}", "security", 48, f"Is the {str(r['kind']).replace('_', ' ')} from {r['provider']} still good?",
                      f"{r['security_id']} {str(r['kind']).replace('_', ' ')} from {r['provider']}: {issue}"
                      + (f"; net-worth statement {r['net_worth_statement_date']}" if r.get("net_worth_statement_date") else "")
                      + (f"; perfection {r['perfection_status']}" if r.get("perfection_status") else "") + ".",
                      ev or [{"value": None, "source": C.row_source("dd_security", r, "note")}], True, "No refreshed document or condition on file."))
    return out


def _queries(pid: str, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    op = [q for q in queries if q.get("status") == "open"]
    if not op:
        return []
    return [_q("queries", "queries", 44, f"{len(op)} reviewer quer{'ies are' if len(op) != 1 else 'y is'} still open: will they be closed before committee?",
               "Open: " + "; ".join(f"{q['subject']} (sent {str(q['sent_at'])[:10]})" for q in op[:4]) + ".",
               [{"value": len(op), "unit": "queries", "source": C.row_source("dd_query", op[0], "status")}], False)]


def challenge(pid: str) -> dict[str, Any]:
    pid = C.resolve_id(pid)
    p = C.proposal(pid)
    a = C.analysis(pid)
    conds = C.rows("dd_condition", proposal_id=pid)
    fs = C.rows("dd_review_finding", proposal_id=pid)
    swot = C.rows("dd_swot", proposal_id=pid)
    queries = C.rows("dd_query", proposal_id=pid)
    cands = (_returns(pid, p, a, swot) + _limits(pid, a, conds) + _stress(pid, conds) + _findings(pid, fs) + _weak(pid, swot)
             + _group(pid, p, a) + _history(pid, conds, queries) + _precedent(pid, conds) + _security(pid) + _queries(pid, queries)
             + _capacity(pid, p, a) + _book_precedent(pid, p, a))
    has = {q["source"] for q in cands}
    if any(str(q.get("category", "")).startswith("precedent:") for q in cands):
        cands = [q for q in cands if q["id"] != "book_precedent"]
    cands = [q for q in cands if not (q.get("category", "").startswith("cons:") and ({"limits", "returns"} & has)
                                      and q["category"] in ("cons:CONS-05", "cons:CONS-07", "cons:CONS-06"))]
    cands.sort(key=lambda q: (-q["score"], q["id"]))
    picked, per = [], {}
    for q in cands:
        if per.get(q["source"], 0) >= MAX_PER_SOURCE:
            continue
        if any(len(_words(q["question"]) & _words(x["question"])) >= 4 for x in picked):
            continue
        picked.append(q)
        per[q["source"]] = per.get(q["source"], 0) + 1
        if len(picked) == 7:
            break
    if len(picked) < 5:  # top up from what was held back by the per-source cap
        for q in cands:
            if q not in picked:
                picked.append(q)
            if len(picked) == 5:
                break
    avoided = [q for q in cands if q["avoided"]]
    for i, q in enumerate(picked, 1):
        q["rank"] = i
    n_av = sum(1 for q in picked if q["avoided"])
    head = (f"{len(picked)} questions committee is likely to ask about {p['obligor']['name']}; {n_av} of them the proposal does not answer. "
            f"Hardest: {picked[0]['question']}" if picked else "No questions could be formed from the data on file.")
    return {"proposal_id": pid, "obligor": p["obligor"]["name"], "headline": head, "questions": picked,
            "avoided": [{"id": q["id"], "question": q["question"], "reason": q["avoided_reason"], "source": q["source"]} for q in avoided][:8],
            "considered": len(cands), "sources_used": sorted({q["source"] for q in cands}),
            "approval": a["approval"], "method": __doc__.split("Method", 1)[1].strip()}
