"""The Deposit requirement term in every Deal Desk document (Round D).

Each document keeps its own rows and tables; the term is added as rows of the kind the document already has:

    bank form / committee paper  `apply_to_paper(D)`: a dd_security row (lien-marked cash, pending until placed and
                                 lien-marked) and a dd_tnc row (the placement / maintenance condition) for the structure the
                                 paper is written on; `committee_rows(D)`: the key-numbers row of the decision summary
    RM's business request        `rm_security(w, items)` / `rm_terms(w, items)`: the deposit the RM typed in the ask
                                 (`parse_text`), else the one on the deal's own record
    credit response              `credit_response_cps(c, terms)`: the condition precedent on the recommended structure
    review                       `review_condition(f)` (a tracked condition from the proposal's own term) and
                                 `review_counter_lines(pid, terms)` (the counter-proposal's terms and conditions precedent)

Amounts printed are the engine's (`engine.analyse(...)["deposit"]`), or the RM's own inputs (a % of a named limit) in the
business request, never a figure computed here.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.deposit_requirement.term import TYPES, describe, maintenance_words, normalise, short

SOURCE = "Deal Desk engine · Deposit requirement term"


def _engine(p: dict[str, Any], terms: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    from backend.dealdesk import engine
    t = engine.merge_terms(p, terms)
    if normalise(t) is None:
        return t, None
    return t, engine.analyse(p, t, validate=False).get("deposit")


def for_deal(pid_or_p: Any, terms: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """{term, terms, deposit (engine block), p, ccy, limit, text, short} for a deal on given terms (None: the ask), or None."""
    from backend.dealdesk import engine, proposals
    try:
        p = proposals.get(pid_or_p) if isinstance(pid_or_p, str) else pid_or_p
    except Exception:  # noqa: BLE001 - not a desk deal
        return None
    if not isinstance(p, dict) or not p.get("ask"):
        return None
    t, dep = _engine(p, terms)
    term = normalise(t)
    if term is None or dep is None:
        return None
    ccy = t["currency"]
    fx = engine.fx(ccy)
    amt_ccy = float(dep["amount_sar_mn"]) / fx
    fac = {"term_loan": "the proposed term loan", "revolver": "the proposed revolver"}.get(t["facility_type"], "the proposed facility")
    return {"term": term, "terms": t, "deposit": dep, "p": p, "ccy": ccy, "limit": float(t["amount"]), "amount_ccy": amt_ccy,
            "text": describe(t, ccy, float(t["amount"]), t.get("tenor_years"), p, fac, amount_ccy=amt_ccy),
            "short": short(t, ccy, amt_ccy), "maintenance": maintenance_words(term, t.get("tenor_years"))}


def condition_text(x: dict[str, Any]) -> str:
    """The placement / maintenance condition in the bank's voice."""
    term, ccy, amt = x["term"], x["ccy"], x["amount_ccy"]
    if term["type"] == "lien_cash":
        return (f"Prior to the first drawdown: cash deposit of {ccy} {amt:,.1f}m placed with the Bank and lien-marked in the Bank's favour, "
                f"maintained {x['maintenance']} and released only on full settlement or with Credit's written approval")
    return (f"Operating balances: average balances of not less than {ccy} {amt:,.1f}m maintained with the Bank {x['maintenance']}, "
            f"tested quarterly; a shortfall reported to Credit within 10 working days")


def change_entry(ask: dict[str, Any] | None, terms: dict[str, Any] | None) -> dict[str, Any] | None:
    """A structure's change of deposit requirement from the ask, in the {field, ask, value} shape of the change lists."""
    if not terms:
        return None
    a, b = short(ask or {}, (ask or {}).get("currency", "SAR")), short(terms, terms.get("currency", "SAR"))
    return None if a == b else {"field": "deposit", "ask": a, "value": b}


# ------------------------------------------------------------------ bank form and committee paper

def _asof(D: Any) -> str:
    from backend.dealdesk.house_style.bankform.ctx import d
    return d(D.get("as_of")) or str(D.as_of)


def _paper_terms(D: Any) -> dict[str, Any] | None:
    feed = getattr(D, "feed", None)
    terms = None
    if feed is not None:
        st = getattr(feed, "structure", None) or {}
        terms = st.get("terms") or None
    return for_deal(D.pid, terms)


def apply_to_paper(D: Any) -> None:
    """Add the term to the paper's security and terms rows (idempotent)."""
    if any(str(r.get("security_id") or r.get("tnc_id") or "").startswith("DEP-") for r in D.rows("dd_security") + D.rows("dd_tnc")):
        return
    try:
        x = _paper_terms(D)
    except Exception:  # noqa: BLE001 - the term never takes a paper down
        return
    if x is None:
        return
    D.deposit = x
    new = [r for r in D.rows("dd_facility_limit") if not (r.get("existing") or 0) and (r.get("proposed") or 0)]
    group = str(new[0].get("name")) if new and x["term"]["facility"] in ("", "proposed", "this") else "All limits"
    src = {"domain": "Deal Desk", "relation": "deposit requirement term (engine)"}
    if x["term"]["type"] == "lien_cash":
        t = x["term"]
        what = (f"{t['pct']:,.0f}% of the {x['ccy']} {x['limit']:,.1f}m limit, " if t["basis"] == "pct" else "") + x["maintenance"]
        D.data["dd_security"] = list(D.rows("dd_security")) + [{
            "security_id": "DEP-1", "item_type": f"Lien-marked cash deposit ({what})", "guarantor": "Borrower",
            "value": round(x["amount_ccy"], 4), "perfection_status": "pending", "limit_group": group,
            "perfection_due": f"the first drawdown, as per the Deal Desk structure of {_asof(D)}", "_src": src}]
        D.status.setdefault("dd_security", "live")
    D.data["dd_tnc"] = list(D.rows("dd_tnc")) + [{"tnc_id": "DEP-1", "text": condition_text(x), "status": "new", "category": "cover",
                                                  "limit_group": group, "_src": src}]
    D.status.setdefault("dd_tnc", "live")


def committee_rows(D: Any) -> list[list[str]]:
    x = getattr(D, "deposit", None)
    if not x:
        return []
    dep = x["deposit"]
    fx = dep["amount_sar_mn"] / x["amount_ccy"] if x["amount_ccy"] else 1.0
    if x["term"]["type"] == "lien_cash":
        val = f"{x['short']}; EAD year one {D.money(dep['ead_y1'] / fx)} → {D.money(dep['ead_net_y1'] / fx)} net of the deposit"
    else:
        val = f"{x['short']}; relationship RAROC +{(dep.get('relationship_raroc_uplift') or 0) * 100:.1f} pts from the balances' funding value"
    return [["Deposit requirement", val, SOURCE]]


# ------------------------------------------------------------------ the RM's business request

LIEN = re.compile(r"lien[- ]?mark\w*|\blien\b|cash collateral|cash cover|blocked deposit|margin deposit", re.I)
REL = re.compile(r"(operating|average|current[- ]account|relationship|minimum)\s+(?:account\s+)?(balances?|deposits?)", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MONTHS = re.compile(r"(\d+(?:\.\d+)?)\s*[- ]?(months?|mths?|years?|yrs?)\b", re.I)


def parse_text(text: str) -> dict[str, Any] | None:
    """A deposit requirement typed in the RM's ask, as terms ({deposit_type, deposit_pct | deposit_amount, ...}) with the clause.
    Only the part of the clause that names the deposit is read (a facility's tenor or price in the same clause is not the deposit's)."""
    from backend.dealdesk.rm_request.ask import amounts, clauses
    for c in clauses(text or ""):
        for part in re.split(r"[,;]|\band\b(?=\s+(?:new|renew|increase|reduce|a|an|the)\b)", c):
            if not re.search(r"deposit|balance|lien|cash collateral|cash cover", part, re.I):
                continue
            typ = "lien_cash" if LIEN.search(part) and re.search(r"deposit|cash", part, re.I) else "relationship" if REL.search(part) else None
            if typ is None:
                continue
            out: dict[str, Any] = {"deposit_type": typ, "deposit_pct": 0, "deposit_amount": 0, "deposit_tenor_months": 0, "deposit_facility": "",
                                   "clause": part.strip()}
            k = re.search(r"lien|deposit|balances?|cash collateral|cash cover|operating|average", part, re.I)
            tail, head = part[k.start():], part[:k.start()]

            def money_in(x: str) -> list[dict[str, Any]]:
                return [a for a in amounts(re.sub(r"\d+(?:\.\d+)?\s*%", " ", x)) if a.get("ccy") or a.get("unit")]
            pm = PCT.search(tail) or (list(PCT.finditer(head)) or [None])[-1]
            am = money_in(tail) or money_in(head)[-1:]
            if pm and (not money_in(tail) or PCT.search(tail)):
                out["deposit_pct"] = float(pm.group(1))
            elif am:
                out["deposit_amount"] = float(am[0]["value"])
            else:
                continue
            mm = MONTHS.search(tail)
            if mm:
                n = float(mm.group(1))
                out["deposit_tenor_months"] = int(round(n * 12 if mm.group(2).lower().startswith("y") else n))
            return out
    return None


def _rm_term(w: Any) -> dict[str, Any] | None:
    """The RM's typed deposit first; else the deal's own record (engine figure)."""
    if getattr(w, "_deposit", None) is not None:
        return w._deposit or None
    typed = parse_text(str((w.ask or {}).get("text") or ""))
    if typed:
        items = [i for i in w.ask.get("items", []) if i.get("action") in ("new", "increase", "takeover") and i.get("amount")]
        lim = items[0] if items else None
        fac = lim.get("facility") if lim and "not stated" not in str(lim.get("facility")) else None
        x = {"origin": "typed", "terms": typed, "term": normalise(typed), "facility": fac,
             "limit": float(lim["amount"]) if lim else None, "src": w.ask_src}
    else:
        pid = (w.c or {}).get("proposal_id")
        rec = for_deal(pid) if pid else None
        x = None if rec is None else {"origin": "record", **rec, "facility": None, "src": f"{SOURCE} on {pid}'s record"}
    w._deposit = x or {}
    return x


def rm_security(w: Any, items: list[str]) -> list[str]:
    """The deposit as a security / support line of the business request (replacing the raw typed clause)."""
    x = _rm_term(w)
    if not x or not x.get("term"):
        return items
    term = x["term"]
    clause = (x["terms"].get("clause") or "").strip().lower()
    items = [i for i in items if not (clause and clause[:40] in i.lower())]
    fac = f"the {x['facility']}" if x.get("facility") else "the proposed facility"
    if x["origin"] == "record":
        amt = w.m(x["amount_ccy"], x["src"], "deposit requirement amount")
        pct = f" ({w.pc(term['pct'], x['src'], 'deposit requirement % of limit', dp=0)} of the {w.m(x['limit'], x['src'], 'limit')} limit)" if term["basis"] == "pct" else ""
        what = f"{amt}{pct}"
    elif term["basis"] == "pct":
        what = (f"{w.pc(term['pct'], x['src'], 'deposit requirement % of limit', dp=0)} of "
                + (f"the {w.m(x['limit'], x['src'], 'limit secured by the deposit')} {(x.get('facility') or 'proposed limit').lower()}" if x.get("limit") else "the limit"))
    else:
        what = w.m(term["amount"], x["src"], "deposit requirement amount")
    per = maintenance_words(term)
    if term["type"] == "lien_cash":
        line = f"Lien-marked cash deposit of {what}, held with the Bank under lien in the Bank's favour {per}, securing {fac} (proposed)."
    else:
        line = f"Operating balances of not less than {what} on average, maintained with the Bank {per}, supporting {fac} (proposed; support, not security)."
    return items + [line]


def rm_terms(w: Any, out: list[str]) -> list[str]:
    x = _rm_term(w)
    if not x or not x.get("term"):
        return out
    term = x["term"]
    per = maintenance_words(term)
    if term["type"] == "lien_cash":
        out.append(f"Prior to the first drawdown: the cash deposit (section 4) placed with the Bank and lien-marked in the Bank's favour; "
                   f"maintained {per} and released only on full settlement or with Credit's written approval.")
    else:
        out.append(f"Operating balances (section 4) maintained with the Bank {per}, tested quarterly on the average balance; a shortfall "
                   "reported to Credit within 10 working days.")
    return out


# ------------------------------------------------------------------ credit response

def credit_response_cps(c: dict[str, Any], terms: dict[str, Any] | None) -> list[str]:
    """The condition precedent of a deposit on the recommended structure of a credit-response case."""
    if not terms or normalise(terms) is None:
        return []
    from backend.dealdesk import proposals
    pid = (c.get("deal") or {}).get("proposal_id") or c.get("proposal_id") or (c.get("steps", {}).get("deal") or {}).get("data", {}).get("proposal_id")
    try:
        p = proposals.get(pid) if pid else None
    except Exception:  # noqa: BLE001
        p = None
    x = for_deal(p, terms) if p else None
    if x is None:
        return []
    return [f"{condition_text(x)} ({TYPES[x['term']['type']].lower()}, per the Deal Desk engine on the recommended structure)"]


# ------------------------------------------------------------------ review

def review_condition(f: dict[str, Any]) -> dict[str, Any] | None:
    """The proposal's own deposit term as a tracked condition (review_conditions trigger body)."""
    dd = f.get("dd") or {}
    pid = (f.get("subject") or {}).get("id") or dd.get("proposal_id")
    x = for_deal(dd if dd.get("ask") else pid)
    if x is None:
        return None
    lien = x["term"]["type"] == "lien_cash"
    return {"kind": "cp" if lien else "covenant", "what": condition_text(x), "source": SOURCE,
            "due": "before drawdown" if lien else "monthly", "owner": "RM"}


def review_counter_lines(pid: str, terms: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """(terms lines, conditions precedent) of a counter-proposal that carries a deposit."""
    x = for_deal(pid, terms) if terms else None
    if x is None:
        return [], []
    return [f"Deposit requirement: {x['text']}"], [condition_text(x)]


__all__ = ["for_deal", "condition_text", "apply_to_paper", "committee_rows", "parse_text", "rm_security", "rm_terms",
           "credit_response_cps", "review_condition", "review_counter_lines"]
