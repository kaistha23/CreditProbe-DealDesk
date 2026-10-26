"""D13 Committee rehearsal (K29): the questions committee will ask on the selected structure, each with a suggested
answer and its evidence, and whether the proposal on file already answers it.

Method (deterministic)
  * Questions: the R13 committee challenger's sources and scores (backend.dealdesk.intel.approval.challenger: returns,
    limits, stress, findings, SWOT weaknesses, group, earlier conditions, precedent conditions, security, queries,
    capacity, book precedent), but run on the structure the panel reads (selected > recommended > ask), not the ask.
  * Cross-deal questions (K29 #5): a condition set on another deal is only used when that deal is in the same sector
    with similarity >= 0.55 (Decision consistency), and the question states the basis (sector, rating, size,
    facility, structure); otherwise it is dropped. The book precedent states its basis (same sector and rating bucket
    in the corporate book).
  * Status (K29 #2): "Answered in the proposal" when a mitigant, condition, query or trigger on file answers it,
    else "Not in the proposal: prepare".
  * Suggested answer (K29 #3), written from the other engines on the same structure:
      returns      the pricing that clears (breakeven) and the best acceptable counter-offer (D6)
      limits       the excess over the limit and the cure (cut the amount by the excess, or the level that signs it)
      stress       the first-warning trigger of the most likely default path (D7) and the breaking severity
      findings     the condition the finding created (dd_condition), else the cure by category
      weaknesses   the SWOT mitigant, else a condition to add
      group        the connected party condition (D12) and the cap headroom
      conditions   restate the missed condition as a condition precedent with a date
      precedent    carry the same condition
      security     a refreshed document as a condition precedent
      queries      close them before committee
      capacity     the covenant headroom
  * "Questions the proposal avoids": every question raised from the data that nothing on file answers; the top ones
    are in the list, the rest are listed below it with their reason.
"""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from backend.dealdesk.intel.approval import challenger as K
from backend.dealdesk.intel.approval import consistency as CONS
from backend.dealdesk.intel2 import common as C

HEADER = ("Questions your committee is likely to ask, and whether the proposal on file already answers them. "
          "'Not in the proposal: prepare' = prepare an answer before committee.")
AVOIDS_NOTE = ("Questions the data raises that nothing on file answers (no mitigant, condition, query or trigger). "
               "The most pressing are in the list above; the rest are here.")
STATUS = {False: "Answered in the proposal", True: "Not in the proposal: prepare"}
CURE_BY_CATEGORY = {
    "auditor_quality": "Ask for the auditor's management letter; a panel auditor for the next audit is a condition.",
    "receivables_quality": "Take an assignment of receivables and size the line on the eligible (under 90 days) book only.",
    "related_party": "Subordinate the related-party balances and cap new related-party lending in the covenants.",
    "bureau_reconciliation": "Get the other banks' facility offer letters and a reconciliation signed by the client before committee; "
                             "undeclared facilities are an event of default.",
    "earlier_conditions": "Explain why it was missed; restate it as a condition precedent with a date.",
    "conduct": "Ask for the reasons in writing; a monthly conduct check (no further returned cheques or past dues) is a condition.",
    "financial_quality": "Restate the ratios on the cash and adjusted figures (Revenue truth check, Financial quality) and size the deal on them.",
    "adjusted_ratios": "Size the deal on the adjusted figures: subordinate shareholder accounts and net related-party balances, or cut the amount.",
    "documents": "Obtain the missing document before limits are loaded (condition precedent).",
    "group_exposure": "Ask for the group cap increase with this proposal, or cut the amount to the cap headroom.",
    "insider_link": "Disclose the link to the committee; the approval goes one level up and the staff member does not take part.",
    "governance": "Condition: no new money to the group while the connected party is classified; cross-default; regularisation plan with dates.",
    "precedent": "Add the monitoring triggers and conditions that would have warned on the similar deals that deteriorated.",
    "cp": "Keep the connected parties under the cross-default; no action beyond monitoring.",
}


def _sim_basis(me: dict[str, Any], f: dict[str, Any]) -> str:
    parts = [f"sector {'same' if me['sector'] == f['sector'] else 'differs'}"]
    g = C.C.notch_gap(me["rating"], f["rating"])
    parts.append(f"rating {f['rating']} ({g} notch{'es' if g != 1 else ''} apart)" if g is not None else "rating not comparable")
    parts.append(f"size SAR {f['amount_sar_mn']:,.0f}m vs {me['amount_sar_mn']:,.0f}m")
    parts.append(f"facility {'same' if me['facility_type'] == f['facility_type'] else 'differs'}")
    return ", ".join(parts)


def _precedent(pid: str, conds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feats = CONS.features()
    me = feats.get(pid)
    out = []
    for q in K._precedent(pid, conds):
        other = q["id"].split(":", 1)[1]
        c = next((x for x in C.rows("dd_condition", condition_id=other)), None)
        f = feats.get(c["proposal_id"]) if c else None
        if not me or not f or f["sector"] != me["sector"] or CONS.similarity(me, f) < CONS.THRESHOLD:
            continue  # K29 #5: a cross-deal question must state a real similarity basis, else it is dropped
        q["similarity_basis"] = _sim_basis(me, f)
        q["answer"] += f" Similarity basis: {q['similarity_basis']}."
        out.append(q)
    return out


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower())}


@functools.lru_cache(maxsize=64)
def _rehearse(pid: str, which: str, tkey: str, pv: str) -> str:
    terms = json.loads(tkey) or None
    st = C.structure(pid, which, terms)
    p = C.proposal(pid)
    a = C.analysis(pid, st["terms"])
    tsrc = {"structure": st["kind"]}
    conds = C.rows("dd_condition", proposal_id=pid)
    fs = C.rows("dd_review_finding", proposal_id=pid)
    swot = C.rows("dd_swot", proposal_id=pid)
    queries = C.rows("dd_query", proposal_id=pid)
    book = K._book_precedent(pid, p, a)
    for q in book:
        q["similarity_basis"] = f"same sector ({p['obligor']['sector']}) and rating bucket in the corporate book"
        q["answer"] += f" Basis: {q['similarity_basis']}."
    cands = (K._returns(pid, p, a, swot) + K._limits(pid, a, conds) + K._stress(pid, conds) + K._findings(pid, fs) + K._weak(pid, swot)
             + K._group(pid, p, a) + K._history(pid, conds, queries) + _precedent(pid, conds) + K._security(pid) + K._queries(pid, queries)
             + K._capacity(pid, p, a) + book)
    if any(q["source"] == "precedent" for q in cands):
        cands = [q for q in cands if q["id"] != "book_precedent"]
    # consistency confirmations (DSCR / leverage meet the covenant, pricing clears) are not questions
    cands = [q for q in cands if not str(q.get("category", "")).startswith("cons:")]
    cands.sort(key=lambda q: (-q["score"], q["id"]))
    picked, per = [], {}
    for q in cands:
        if per.get(q["source"], 0) >= K.MAX_PER_SOURCE:
            continue
        if any(len(_words(q["question"]) & _words(x["question"])) >= 4 for x in picked):
            continue
        picked.append(q)
        per[q["source"]] = per.get(q["source"], 0) + 1
        if len(picked) == 7:
            break
    if len(picked) < 5:
        for q in cands:
            if q not in picked:
                picked.append(q)
            if len(picked) == 5:
                break
    ctx = _context(pid, which, terms)
    for i, q in enumerate(picked, 1):
        q["rank"] = i
        q["status"] = STATUS[bool(q["avoided"])]
        q["fact"] = q.pop("answer")
        sug, ev = _suggest(pid, p, a, st, q, ctx, conds, fs, swot, queries, tsrc)
        q["suggested_answer"] = sug
        q["evidence"] = q["evidence"] + [e for e in ev if e]
    avoided = [q for q in cands if q["avoided"] and q not in picked]
    n_prep = sum(1 for q in picked if q["avoided"])
    head = (f"{len(picked)} questions on {C.the(st)} for {p['obligor']['name']}: {len(picked) - n_prep} answered in the proposal, "
            f"{n_prep} to prepare. Hardest: {picked[0]['question']}" if picked else "No questions could be formed from the data on file.")
    first = next((q for q in picked if q["avoided"]), picked[0] if picked else None)
    plain = C.plain("These are the questions committee will probably ask, with a suggested answer for each.",
                    f"{n_prep} of {len(picked)} are not answered in the proposal; start with: {first['question'][:90]}" if first else "No questions.",
                    "Prepare the answers marked 'prepare' and add them to the proposal before committee.")
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {k: st[k] for k in ("kind", "label", "note")},
           "header": HEADER, "headline": head, "plain": plain, "questions": picked,
           "avoids": {"note": AVOIDS_NOTE, "items": [{"id": q["id"], "question": q["question"], "reason": q["avoided_reason"], "source": q["source"]}
                                                    for q in avoided][:8]},
           "considered": len(cands), "approval": a["approval"],
           "raroc": C.efig(pid, a["metrics"]["lifetime_raroc"], "share", "Lifetime RAROC on the structure", "engine.analyse", tsrc),
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def _context(pid: str, which: str, terms: dict[str, Any] | None) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    for name, mod in (("frontier", "frontier"), ("premortem", "premortem"), ("contagion", "contagion"), ("pricing", "pricing")):
        try:
            m = __import__(f"backend.dealdesk.intel2.{mod}", fromlist=[mod])
            ctx[name] = getattr(m, mod)(pid, which, terms)
        except Exception:  # noqa: BLE001 - a missing engine leaves the generic answer
            ctx[name] = None
    return ctx


def _suggest(pid: str, p: dict[str, Any], a: dict[str, Any], st: dict[str, Any], q: dict[str, Any], ctx: dict[str, Any],
             conds: list[dict[str, Any]], fs: list[dict[str, Any]], swot: list[dict[str, Any]], queries: list[dict[str, Any]],
             tsrc: dict[str, Any]) -> tuple[str, list[dict[str, Any] | None]]:
    src = q["source"]
    m = a["metrics"]
    lab = C.the(st)
    if src == "returns":
        fr, pr = ctx.get("frontier"), ctx.get("pricing")
        if not m["clears_hurdle"]:
            off = next((o for o in (fr or {}).get("offers", []) if o["acceptable"]), None)
            be = (pr or {}).get("breakeven", {}).get("value")
            s = (f"On {lab} RAROC is {C.pct(m['lifetime_raroc'])} against {C.pct(m['hurdle'])}. "
                 + (f"Pricing at {be:,.0f} bps clears it. " if be else "")
                 + (f"Our counter-offer: {off['label'].lower()} (RAROC {C.pct(off['raroc']['value'])})." if off else "No counter-offer clears it: decline or restructure."))
            return s, [off["raroc"] if off else None, (pr or {}).get("breakeven")]
        pc = (pr or {}).get("percentile", {}).get("value")
        return (f"On {lab} RAROC is {C.pct(m['lifetime_raroc'])} against {C.pct(m['hurdle'])}"
                + (f"; the margin sits at the {C.ordinal(pc)} percentile of similar book facilities (D9)." if pc is not None else ".")), \
            [(pr or {}).get("percentile"), C.efig(pid, m["lifetime_raroc"], "share", "Lifetime RAROC", "engine.analyse", tsrc)]
    if src == "limits":
        c = next((c for c in a["constraints"] if f"limit:{c['name']}" == q["id"]), None)
        if c and isinstance(c.get("value"), (int, float)) and isinstance(c.get("limit"), (int, float)):
            ex = c["value"] - c["limit"]
            return (f"{c['label']} is over by {ex:,.1f} {c['unit']}. Cure: cut the amount by that much, or take the exception to "
                    f"{a['approval']['level']} with the mitigants on file."), [C.efig(pid, round(ex, 4), c["unit"], "Excess over the limit", "intel2.rehearsal", tsrc)]
        return f"Take the exception to {a['approval']['level']} with the mitigants on file, or reduce the amount.", []
    if src == "stress":
        pm = ctx.get("premortem") or {}
        path = next((x for x in pm.get("paths", []) if x["key"] != "contagion"), None)
        if path:
            return (f"The likeliest stress path is {path['driver'].lower()} ({C.pct(path['probability']['value'])} a year). "
                    f"Protection: {path['first_warning']}; " + ("it does not break up to severe." if path["lead"].startswith("no break") else f"it {path['lead']}.")), [path["probability"]]
        return "Add a DSCR covenant with headroom and a monitoring trigger on the metric that breaks.", []
    if src == "findings":
        f = next((f for f in fs if f"finding:{f['finding_id']}" == q["id"]), None)
        if f and f.get("cure_text"):
            return str(f["cure_text"]), []
        if f and f.get("condition_id"):
            c = next((c for c in conds if c["condition_id"] == f["condition_id"]), None)
            if c:
                return f"Answered by the condition: {c['text']}", [{"value": None, "source": C.row_source("dd_condition", c, "text")}]
        cat = str((f or {}).get("category") or "").split(":")[0]
        if cat == "governance" and (ctx.get("contagion") or {}).get("conditions"):
            return "Condition: " + ctx["contagion"]["conditions"][0]["text"], [ctx["contagion"].get("adverse_exposure")]
        return CURE_BY_CATEGORY.get(cat, "Ask the RM for the evidence now and make the answer a condition precedent."), []
    if src == "weaknesses":
        s = next((s for s in swot if f"swot:{s['swot_id']}" == q["id"]), None)
        if s and s.get("mitigant_text"):
            return f"Mitigant: {s['mitigant_text']}", [{"value": None, "source": C.row_source("dd_swot", s, "mitigant_text")}]
        return "Add a covenant or condition that answers it, and say so in the proposal.", []
    if src == "group":
        g = ctx.get("contagion") or {}
        if g.get("adverse_count"):
            c0 = (g.get("conditions") or [{}])[0].get("text")
            return (f"{', '.join(g['combined']['parties'])} {'is' if g['adverse_count'] == 1 else 'are'} in trouble; if they fail RAROC goes to "
                    f"{C.pct(g['combined']['raroc_after']['value'])}. " + (f"Condition: {c0}" if c0 else "Add a cross-default.")), [g["combined"]["raroc_after"]]
        gc = next((c for c in a["constraints"] if c["name"] == "group_connected"), None)
        if gc and gc.get("headroom") is not None:
            return f"Group cap headroom after the deal: {gc['headroom']:,.1f} {gc['unit']}.", [C.efig(pid, gc["headroom"], gc["unit"], "Group cap headroom", "engine.analyse", tsrc)]
        return "Group exposure is within the cap.", []
    if src == "conditions":
        return ("Explain why it was missed; renew only with it restated as a condition precedent with a date, and a margin step-up if missed again."), []
    if src == "precedent":
        txt = q["question"].split('"')[1] if '"' in q["question"] else "the same condition"
        return f"Carry the same condition here: \"{txt}\".", []
    if src == "security":
        return "Make a refreshed document (valuation, net-worth statement or perfection) a condition precedent before limits are loaded.", []
    if src == "queries":
        op = [x for x in queries if x.get("status") == "open"]
        return "Close them before committee: " + "; ".join(x["subject"] for x in op[:3]) + ".", []
    if src == "capacity":
        ds = C.finite(m.get("dscr_post"))
        cov = {str(c.get("type", "")).lower(): c.get("threshold") for c in (p.get("security") or {}).get("covenants") or []}
        dmin = cov.get("dscr") or 1.2
        if ds:
            return (f"DSCR {ds:.2f}x against a {dmin:.2f}x covenant: {(ds / dmin - 1) * 100:.0f}% headroom on {lab}."), \
                [C.efig(pid, round(ds / dmin - 1, 4), "share", "DSCR covenant headroom", "intel2.rehearsal", tsrc)]
    if src == "precedent" or q["id"] == "book_precedent":
        return "Similar borrowers' record is in the fact above; add the monitoring trigger that would have warned on them.", []
    return "Prepare the answer from the evidence below.", []


def rehearse(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_rehearse(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
