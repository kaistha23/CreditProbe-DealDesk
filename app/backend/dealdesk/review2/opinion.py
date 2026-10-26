"""The proposal quality score and the reviewer opinion in the credit division's voice (PROPOSAL_ANATOMY §3).

quality(...)   0-100 from five parts, each shown with its weight and evidence:
               completeness 30 (documents received or waived), evidence 25 (claims supported against contradicted),
               verifiability 15 (checks with the data they need), findings 20 (critical 6, major 2, minor 0.5 points off),
               language 10 (sentences with a number or source)
opinion(...)   the deterministic writer (N6): numbered paragraphs, every sentence a fact, number and source, attribution explicit
               ("as per business", "not provided"), adjusted figures, measured scepticism; key concerns flagged for underline.
               When ANTHROPIC_API_KEY is set, a polish pass may rewrite wording only; the tests check this deterministic text.
"""
from __future__ import annotations

import os
from typing import Any

from backend.dealdesk.review2 import analytics as A
from backend.dealdesk.review2.findings import SEV_RANK

WEIGHTS = {"completeness": 30, "evidence": 25, "verifiability": 15, "findings": 20, "language": 10}
PENALTY = {"critical": 6.0, "major": 2.0, "minor": 0.5, "info": 0.0}


def quality(docs: dict[str, Any], verdicts: dict[str, int], findings: list[dict[str, Any]], lang: dict[str, Any]) -> dict[str, Any]:
    sup, con, exc, unv = (verdicts.get(k, 0) for k in ("supported", "contradicted", "exception", "unverifiable"))
    tot = sup + con + exc + unv
    parts = {
        "completeness": docs.get("completeness", 1.0),
        "evidence": (sup / (sup + con)) if sup + con else 1.0,
        "verifiability": 1 - (unv / tot) if tot else 1.0,
        "findings": max(0.0, 1 - sum(PENALTY.get(f["severity"], 0) for f in findings) / WEIGHTS["findings"]),
        "language": 1 - (len(lang.get("unevidenced") or []) / lang["lines_checked"]) if lang.get("lines_checked") else 1.0,
    }
    rows = [{"part": k, "weight": w, "share": round(parts[k], 4), "points": round(parts[k] * w, 1)} for k, w in WEIGHTS.items()]
    score = round(sum(r["points"] for r in rows))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    detail = {"completeness": f"{docs.get('completeness', 1) * 100:.0f}% of required documents received or waived",
              "evidence": f"{sup} claims supported, {con} contradicted",
              "verifiability": f"{unv} of {tot} checks lacked the data they need",
              "findings": ", ".join(f"{n} {s}" for s, n in ((s, sum(1 for f in findings if f['severity'] == s)) for s in ("critical", "major", "minor")) if n) or "no findings",
              "language": f"{len(lang.get('unevidenced') or [])} of {lang.get('lines_checked', 0)} memo sentences without a number or source"}
    for r in rows:
        r["basis"] = detail[r["part"]]
    weakest = min(rows, key=lambda r: r["share"])
    return {"score": score, "grade": grade, "parts": rows,
            "headline": f"Proposal quality {score}/100 (grade {grade}); weakest: {weakest['part']} ({weakest['basis']})."}


def _lc(t: str) -> str:
    """Lower-case the first letter only when the word is not an acronym or a name."""
    return t[0].lower() + t[1:] if t[:2].isalpha() and t[1:2].islower() else t


#: The condition each kind of finding leads to (operational: who, what, by when).
CONDITION_FOR = {
    "BUR-01": "business to reconcile the other-bank limits with the bureau and provide every other bank's facility letter, prior to limit loading",
    "BUR-03": "RM to obtain the reasons for the returned cheques and confirm regularisation, prior to limit loading",
    "BUR-04": "cross-default and economic-dependency assessment of the classified related party, with exposure to it capped at today's outstanding",
    "INS-01": "staff interest declared and cleared by Compliance; approval taken one level above the staff member's line",
    "INS-02": "related holding disclosed in the proposal and the related party added to the connected-party register",
    "AUD-01": "provision for the qualified amount reflected in the covenant calculations; next audit by a panel auditor",
    "AUD-02": "auditor replaced by a panel auditor from the next financial year (undertaking prior to limit loading)",
    "ADJ-01": "related-party balances subordinated to the bank and capped; covenant on adjusted leverage tested semi-annually",
    "ADJ-02": "shareholder support to restore adjusted net worth (capital injection or subordination) prior to limit loading",
    "ADJ-03": "related-party receivables settled or subordinated; adjusted current ratio of at least 1.0x tested semi-annually",
    "TRK-01": "earlier undertakings re-confirmed in writing and measured monthly by the RM and regional head",
    "RCV-01": "receivables over 365 days provided for or collected; ageing reported quarterly",
    "RCV-02": "concentration covenant on the two largest debtors, reported quarterly",
    "RCV-03": "retention release schedule agreed with the employers; overdue retentions reported quarterly",
    "RCV-04": "related-party receivables settled or subordinated; no new related-party advances during the tenor",
}


def _sentence_list(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def opinion(ctx: dict[str, Any]) -> dict[str, Any]:
    """ctx: subject, answer, findings, analytics, documents, queries, counter, doa, conditions, quality, precedent."""
    s, ans, an = ctx["subject"], ctx["answer"], ctx["analytics"]
    ccy = s.get("currency") or ""
    fs = sorted(ctx["findings"], key=lambda f: (SEV_RANK.get(f["severity"], 3), f["point"]))
    crit = [f for f in fs if f["severity"] == "critical"]
    maj = [f for f in fs if f["severity"] == "major"]
    paras: list[dict[str, Any]] = []

    amt = s.get("amount_ccy")
    ask = (f"Business requests {A.fm(amt, ccy)} for {s['name']}" + (f" ({s['group']})" if s.get("group") else "") +
           f", rated {s.get('rating')}, {s.get('sector')} sector" + (f", against existing limits of {A.fm(s.get('existing_ccy'), ccy)}" if s.get("existing_ccy") else "") + ".")
    req = ctx.get("request_summary") or []
    if req:
        ask += " As per business: " + "; ".join(r[0].lower() + r[1:] for r in req[:4]) + "."
    paras.append({"title": "Request", "text": ask, "underline": []})

    n = ans["counts"]
    head = (f"Credit has re-performed the review on {ctx['checks_run']} checks across the 12 review points: "
            f"{n.get('critical', 0)} critical, {n.get('major', 0)} major and {n.get('minor', 0)} minor findings. ")
    key = [f["finding"] for f in (crit + maj)[:4]]
    paras.append({"title": "Key concerns", "text": head + (" ".join(key) if key else "No finding requires a condition."),
                  "underline": [f["finding"] for f in crit[:3]]})

    fin_bits = []
    adj = an["adjusted"]
    if adj["adjustments"]:
        h = adj["headline"]
        if h.startswith("FY") and ": " in h[:10]:
            yr, rest = h.split(": ", 1)
            h = f"in {yr}, {rest}"
        else:
            h = h[0].lower() + h[1:]
        fin_bits.append("We note that " + h)
    rc = an["receivables"]
    if rc["headline"] and "not provided" not in rc["headline"]:
        fin_bits.append(rc["headline"])
    au = an["auditor"]
    if au.get("auditor") or au.get("opinion"):
        fin_bits.append(f"The accounts are audited by {au['auditor'] or 'an auditor not named'}" +
                        (" (not on the approved panel)" if au.get("approved_panel") is False else "") +
                        f"; opinion {au.get('opinion') or 'not provided'}" +
                        (f"; basis of qualification: {au['qualification_basis'].rstrip('. ')}" + (f" ({A.fm(au['qualification_amount'], ccy)})" if au.get("qualification_amount") else "") if au.get("qualification_basis") else "") + ".")
    if fin_bits:
        paras.append({"title": "Financials, adjusted", "text": " ".join(fin_bits), "underline": []})

    bu = an["bureau"]
    b_bits = [bu["headline"]]
    for r in bu["reconciliation"]:
        if r["status"] == "not reconciled":
            b_bits.append(f"Upon checking, the bureau shows {A.fm(r['bureau'], ccy)} of other-bank limits for {r['entity']} against "
                          f"{A.fm(r['declared'], ccy)} declared by the client; the difference of {A.fm(r['gap'], ccy)} is not clarified.")
    if bu["not_provided"]:
        b_bits.append("Bureau reports not provided for " + _sentence_list(bu["not_provided"][:4]) + ".")
    paras.append({"title": "Bureau and other banks", "text": " ".join(b_bits),
                  "underline": [b for b in b_bits[1:] if "not clarified" in b]})

    tr = an["earlier"]
    ins = an["insider"]
    g_bits = []
    if tr["rows"]:
        g_bits.append(tr["headline"])
    if ins["rows"]:
        g_bits.append(ins["headline"])
    others = [f["finding"] for f in fs if f.get("author") not in (None, "B")][:2]
    g_bits += others
    if g_bits:
        paras.append({"title": "Track record, group and insider links", "text": " ".join(g_bits),
                      "underline": [i for i in [ins["headline"]] if ins["rows"] and any(r["kind"] == "staff" for r in ins["rows"])]})

    dl, q = ctx["documents"], ctx["queries"]
    miss = [i for i in dl["items"] if i["mandatory"] and i["status"] in ("pending", "expired")]
    d_txt = dl["headline"]
    if miss:
        d_txt += " Not provided or expired: " + _sentence_list([f"{_lc(i['name'])} ({i['for']}{', expired' if i['status'] == 'expired' else ''})" for i in miss[:5]]) + \
                 (f" and {len(miss) - 5} more" if len(miss) > 5 else "") + "."
    if q.get("items"):
        d_txt += " " + q["headline"]
    paras.append({"title": "Documents and queries", "text": d_txt, "underline": []})

    cps = (ctx.get("counter") or {}).get("counter_proposals") or []
    doa = ctx.get("doa") or {}
    conds = (ctx.get("conditions") or {}).get("items") or (ctx.get("conditions") or {}).get("conditions") or []
    rec = [f"{ans['decision']}."]
    if not cps and ans["decision"] == "Do not approve as proposed":
        rec.append("Credit does not support the proposal as submitted; it can be reconsidered once the conditions below are met.")
    if cps and ans["decision"] != "Approve as proposed":
        cp = cps[0]
        rec.append(f"Credit recommends instead: {cp['title'][0].lower() + cp['title'][1:]}" +
                   (f" (RAROC {A.pc(cp['raroc'], 1)} against a hurdle of {A.pc(cp['hurdle'], 1)})" if cp.get("raroc") is not None and cp.get("hurdle") is not None else "") + ".")
    cp_list = [c.get("what") for c in conds if c.get("kind") == "CP"][:4]
    for f in fs:
        c = CONDITION_FOR.get(f["code"])
        if c and f["severity"] in ("critical", "major") and c not in cp_list and len(cp_list) < 7:
            cp_list.append(c)
    if miss:
        cp_list.append(f"the {len(miss)} missing or expired documents received prior to limit loading")
    if cp_list:
        rec.append("Conditions: " + "; ".join(f"({i + 1}) {t[0].lower() + t[1:] if t[1:2].islower() else t}" for i, t in enumerate(cp_list)) + ".")
    if doa.get("level"):
        rec.append(f"Approval authority: {doa['level']}" + (f" ({doa['binding']['detail']})" if (doa.get("binding") or {}).get("detail") else "") + ".")
    rec.append(f"{ctx['quality']['headline']}")
    paras.append({"title": "Recommendation", "text": " ".join(rec), "underline": [rec[0]] if ans["decision"] != "Approve as proposed" else []})

    text = "\n\n".join(f"{i + 1}. {p['title']}. {p['text']}" for i, p in enumerate(paras))
    out = {"voice": "credit", "author": "Credit division", "paragraphs": paras, "text": text, "writer": "deterministic", "polished": False,
           "words": len(text.split())}
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("DD_OPINION_POLISH", "1") == "1":
        out = _polish(out)
    return out


def _polish(out: dict[str, Any]) -> dict[str, Any]:
    """Optional model polish of wording only (N6); any failure keeps the deterministic text."""
    try:
        from backend.dealdesk.house_style import polish as HP  # Session F's polish hook, when present
        fn = getattr(HP, "polish_text", None)
        if fn is None:
            return out
        new = fn(out["text"], voice="credit")
        if isinstance(new, str) and len(new) > 0.6 * len(out["text"]):
            return {**out, "text": new, "polished": True, "writer": "deterministic+polish"}
    except Exception:  # noqa: BLE001
        pass
    return out
