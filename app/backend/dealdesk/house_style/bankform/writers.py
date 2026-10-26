"""Deterministic writers for the 20 anatomy sections (PROPOSAL_ANATOMY.md §2), N6: complete text with no model.

Each writer takes the deal (`ctx.Deal`) and returns (blocks, gaps). A gap names a contract item the data did not provide; the
text then says "not provided" / "not available" rather than inventing anything. Every prose sentence carries a figure and a
date (or an explicit attribution), prior-year figures in brackets and shares of totals (see voice.py).
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.house_style.bankform.blocks import BL, BOX, H, KV, NL, P, SIGN, T
from backend.dealdesk.house_style.bankform.ctx import Deal, d, num, pct, share, xx
from backend.dealdesk.house_style.bankform.source import first

Out = tuple[list[dict[str, Any]], list[str]]
NA = "not available"


def _asof(D: Deal) -> str:
    return d(D.get("as_of", "reporting_date")) or d(D.as_of) or str(D.as_of)


def _days(a: Any, b: Any) -> int:
    from datetime import date as _date
    try:
        x, y = _date.fromisoformat(str(a)[:10]), _date.fromisoformat(str(b)[:10])
        return (y - x).days
    except (TypeError, ValueError):
        return 0


def one(text: Any) -> str:
    """A quoted relation note as one sentence (its own sentences joined by ';'), so its attribution covers all of it."""
    return re.sub(r"\.\s+(?=[A-Z0-9])", "; ", str(text or "").strip().rstrip("."))


def _profile_text(r: dict[str, Any]) -> str:
    """A dd_business_profile item in proposal voice, with its attribution made explicit."""
    t = one(r.get("text") or r.get("label") or "")
    att = str(r.get("attribution") or "")
    if r.get("year") and not re.search(r"\b(19|20)\d\d\b", t):
        t += f" (FY{r.get('year')})"
    low = t.lower()
    if att == "as_per_business" and not any(x in low for x in ("as per business", "business conveys", "business attributes", "business states")):
        t += ", as per business"
    elif att == "audited" and "audited" not in low:
        t += f", per the audited accounts for FY{r.get('year')}" if r.get("year") else ", per the audited accounts"
    elif att == "not_provided" and "not provided" not in low:
        t += " (not provided)"
    return t + "."


def _lc(t: str) -> str:
    return t[:1].lower() + t[1:] if t[:1].isupper() and not t[1:2].isupper() and not t.split(" ")[0] in ("Mr", "Mrs", "Ms", "Dr") else t


def _obs_text(f: dict[str, Any]) -> str:
    """R12 M: one sentence per observation, so the attribution covers all of it. Session B's document findings lead with
    the document's name as its own sentence ("Trade licence (valid). <entity>: <status>. Required by <clause>.")."""
    parts = [x.strip() for x in str(f.get("text", "")).strip().rstrip(".").split(". ") if x.strip()]
    if not parts:
        return ""
    if len(parts) > 1 and str(f.get("title", "")).lower().startswith(parts[0].lower()):
        parts = [f"{parts[0]}: {parts[1]}"] + parts[2:]
    return "; ".join([parts[0]] + [_lc(x) for x in parts[1:]])


def status_phrase(c: Any) -> str:
    c = str(c or "").lower().replace("_", " ")
    return {"watch": "on the watch list", "watch list": "on the watch list", "litigation": "in litigation", "past due": "past due"}.get(c, f"classified {c.replace('classified ', '')}")


def _tick(v: Any, kind: str) -> str:
    return "[x]" if str(v or "").lower() == kind else "[ ]"


# ------------------------------------------------------------------------------------------------ 1 header block

def w_header(D: Deal) -> Out:
    p = D.p
    kind = str(first(p, "request_kind", "case_type", default="")).lower()
    rp = first(p, "related_party_flag")
    pairs = [("Branch / unit", first(p, "branch", "business_unit", default=NA)), ("Customer", D.name),
             ("Date account opened", d(first(p, "account_opened")) or NA), ("CIF / base no.", first(p, "obligor_id", "cif", default=NA)),
             ("Group no.", first(p, "group_id", default=NA)), ("Group", D.group or NA),
             ("Related / connected party", ("Yes, party CIF " + str(first(p, "related_party_cif", default=""))) if str(rp) in ("1", "True", "true") else "No"),
             ("Date", _asof(D)), ("AO / RO", f"{first(p, 'ao', default='–')} / {first(p, 'ro', default='–')}"),
             ("Purpose code", first(p, "purpose_code", default=NA)),
             ("Request", "  ".join(f"{_tick(kind, k)} {k.capitalize()}" for k in ("new", "existing", "renewal", "additional", "amendment"))),
             ("Review date", d(first(p, "review_date")) or NA), ("Industry code", first(p, "industry_code", "sector_code", default=NA)),
             ("Collateral code", first(p, "collateral_code", default=NA)),
             ("Rating existing / proposed", f"{first(p, 'internal_rating', default='–')} / {first(p, 'proposed_rating', 'internal_rating', default='–')}"),
             ("RM / unit", first(p, "rm", default=NA))]
    gaps = [k for k, v in pairs if v == NA]
    return [KV(pairs, cols=2)], gaps


# ------------------------------------------------------------------------------------------------ 2 action requested (business voice)

def _limits(D: Deal) -> list[dict[str, Any]]:
    rows = D.rows("dd_facility_limit")
    if rows:
        return rows
    out = []  # pre-R12 deals: one line per proposal facility from dd_proposal_facility, or the ask itself
    for r in D.rows("dd_proposal_facility"):
        out.append({"limit_id": r.get("line_id"), "parent_limit_id": "", "limit_group": "Facilities", "name": str(r.get("facility_type", "")).replace("_", " ").capitalize(),
                    "existing": r.get("limit_sar_mn") if r.get("line_kind") == "existing" else 0.0, "outstanding": r.get("drawn_sar_mn"),
                    "proposed": r.get("limit_sar_mn"), "tenor": f"{r.get('tenor_years') or ''} years", "_src": r["_src"]})
    if not out and D.get("amount") is not None:
        out.append({"limit_id": "ASK", "parent_limit_id": "", "limit_group": "Facilities", "name": str(D.get("facility_type", default="Facility")).replace("_", " ").capitalize(),
                    "existing": D.get("existing_ead_sar_mn", default=0.0), "outstanding": None, "proposed": D.get("amount"),
                    "pricing": (f"Margin {D.get('margin_bps')} bps" if D.get("margin_bps") else ""), "tenor": f"{D.get('tenor_years', default='')} years"})
    return out


def _tops(D: Deal) -> list[dict[str, Any]]:
    return [r for r in _limits(D) if not r.get("parent_limit_id")]


def totals(D: Deal) -> tuple[float, float, float]:
    tops = _tops(D)
    return (sum(num(r.get("existing")) or 0 for r in tops), sum(num(r.get("outstanding")) or 0 for r in tops),
            sum(num(r.get("proposed")) or 0 for r in tops))


def asks(D: Deal) -> list[str]:
    """Each ask in one line: renew, reduce, increase, new one-off limit, cap change."""
    out = []
    tops = _tops(D)
    subs = [r for r in _limits(D) if r.get("parent_limit_id") and num(r.get("existing")) and num(r.get("existing")) != num(r.get("proposed"))]
    for r in tops + subs:
        e, pr = num(r.get("existing")) or 0.0, num(r.get("proposed")) or 0.0
        nm = r.get("name", "limit") + (" sub-limit" if r in subs else "")
        if e == 0 and pr > 0:
            out.append(f"approve a new {nm} of {D.money(pr)}")
        elif pr > e:
            out.append(f"increase the {nm} from {D.money(e)} to {D.money(pr)}")
        elif pr < e:
            out.append(f"reduce the {nm} from {D.money(e)} to {D.money(pr)}")
        else:
            out.append(f"renew the {nm} of {D.money(pr)}")
    ce, cp = num(D.get("group_cap_existing")), num(D.get("group_cap_proposed"))
    if ce is not None and cp is not None and cp != ce:
        out.append(f"{'increase' if cp > ce else 'reduce'} the group exposure cap from {D.money(ce)} to {D.money(cp)}")
    return out


def w_action(D: Deal) -> Out:
    te, to, tp = totals(D)
    a = asks(D)
    gaps = []
    ref, rd = D.get("previous_committee_ref"), d(D.get("previous_committee_date"))
    blocks = []
    if a:
        move = f"taking total limits from {D.money(te)} to {D.money(tp)} ({'+' if tp >= te else ''}{D.money(tp - te)})" if abs(tp - te) > 0.05 else f"with total limits unchanged at {D.money(tp)}"
        blocks.append(P(f"Business requests approval, as at {_asof(D)}, to " + "; ".join(a) + f", {move}."))
    else:
        gaps.append("facility lines")
        blocks.append(P(f"Facility lines not provided in Data Domains as at {_asof(D)}."))
    purpose = D.get("purpose")
    if purpose:
        blocks.append(P(f"Purpose as per business: {purpose} (requested {d(D.get('received_date')) or _asof(D)})."))
    if ref:
        blocks.append(P(f"The limits were last approved by {ref}" + (f" on {rd}" if rd else "") + f" at {D.money(_last_total(D) or te)}."))
    else:
        gaps.append("previous committee reference")
        blocks.append(P(f"Previous committee reference not provided as at {_asof(D)}."))
    fee = D.get("study_fee")
    if fee is not None:
        blocks.append(P(f"Study and documentation fee of {D.money(fee, 2)} payable on approval, as at {_asof(D)}."))
    return blocks, gaps


def _last_total(D: Deal) -> float | None:
    h = [r for r in D.rows("dd_reference") if num(r.get("total_limit")) is not None]
    return num(h[-1].get("total_limit")) if h else None


# ------------------------------------------------------------------------------------------------ 3 facilities table

def w_facilities(D: Deal) -> Out:
    lines = _limits(D)
    if not lines:
        return [P(f"Facilities table not available in Data Domains (dd_facility_limit {D.status.get('dd_facility_limit', 'missing')}) as at {_asof(D)}.")], ["dd_facility_limit"]
    kids: dict[str, list[dict[str, Any]]] = {}
    for r in lines:
        kids.setdefault(str(r.get("parent_limit_id") or ""), []).append(r)
    rows = []

    def add(r: dict[str, Any], depth: int) -> None:
        part = "; ".join(x for x in (r.get("pricing"), r.get("validity"), r.get("tenor"), r.get("repayment")) if x and x != "n/a")
        cm = num(r.get("cash_margin_pct"))
        rows.append([("    " * depth) + str(r.get("name", "")), D.m(r.get("existing")), D.m(r.get("outstanding")), D.m(r.get("proposed")),
                     (pct(cm, 0) if cm else "–"), part or "–"])
        for k in kids.get(str(r.get("limit_id")), []):
            add(k, depth + 1)
    for r in kids.get("", []):
        add(r, 0)
    te, to, tp = totals(D)
    rows.append(["**Total limits**", D.m(te), D.m(to), D.m(tp), "", ""])
    src = D.src("dd_facility_limit") if D.rows("dd_facility_limit") else D.src("dd_proposal_facility")
    blocks = [T(["Limit / sub-limit", f"Existing ({D.ccy} m)", "Outstanding", "Proposed", "Cash margin", "Particulars (pricing, validity, tenor, repayment)"],
                rows, source=src, widths=[5.0, 1.6, 1.7, 1.6, 1.3, 5.8], size=7)]
    used = (to / te) if te else None
    blocks.append(P(f"Total limits of {D.money(tp)} proposed against {D.money(te)} existing as at {_asof(D)}; outstanding {D.money(to)}"
                    + (f" ({pct(used)} of existing limits)." if used is not None else ".")))
    if not D.rows("dd_facility_limit"):
        blocks.append(P(f"The limit and sub-limit tree is not provided in Data Domains (dd_facility_limit {D.status.get('dd_facility_limit', 'missing')}) as at {_asof(D)}; "
                        f"the {len(lines)} line(s) above are read from the proposal's ask."))
    floors = [r for r in lines if "floor" in str(r.get("pricing", "")).lower()]
    if floors:
        blocks.append(P(f"{len(floors)} funded line(s) priced at benchmark plus spread with a floor, as per business on {d(D.get('received_date')) or _asof(D)}."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 4 security and support

def w_security(D: Deal) -> Out:
    items = D.rows("dd_security")
    if not items:
        return [P(f"Security and support not provided in Data Domains as at {_asof(D)}.")], ["dd_security"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in items:
        groups.setdefault(str(r.get("limit_group") or "All limits"), []).append(r)
    blocks = []
    for g, rs in groups.items():
        blocks.append(H(f"Security for {g}"))
        bl = []
        for r in rs:
            kind = str(first(r, "item_type", "item_kind", default="Security"))
            who = first(r, "guarantor", default="")
            val = num(first(r, "value_sar_mn", "value"))
            nw, nwd = num(r.get("guarantor_net_worth")), d(r.get("nw_statement_date"))
            st, due = str(r.get("perfection_status") or ""), d(r.get("perfection_due"))
            s = f"{kind}" + (f" of {who}" if who and who != "Borrower" else "") + (f" for {D.money(val)}" if val is not None else "")
            if nw is not None:
                s += f", net worth {D.money(nw)} per statement dated {nwd or 'not provided'}"
            elif nwd:
                s += f", net-worth statement dated {nwd}"
            if st == "pending":
                s += f"; not yet perfected, to be perfected by {due or 'a date not provided'}"
            elif st:
                s += f"; {st} as at {_asof(D)}"
            else:
                s += f"; perfection status not provided as at {_asof(D)}"
            note = r.get("note")
            # R16 x: on a paper over a business request, only the request's own items (RQ-) are the business's words; a seeded
            # note is the Bank's security register
            lab = "As per business" if not D.p.get("exposure_after_request") or str(r.get("security_id") or "").startswith("RQ-") else "Per the Bank's security register"
            bl.append(s + "." + (f" {lab}: {str(note).rstrip('.')}." if note else ""))
        blocks.append(BL(bl))
    pend = [r for r in items if r.get("perfection_status") == "pending"]
    tot = sum(num(first(r, "value_sar_mn", "value")) or 0 for r in pend)
    blocks.append(P(f"{len(pend)} of {len(items)} security items, covering {D.money(tot)}, are not perfected as at {_asof(D)}."
                    if pend else f"All {len(items)} security items are executed or held as at {_asof(D)}."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 5 terms and conditions

CAT_ORDER = ["cp", "utilisation", "cap", "purpose", "disbursement", "settlement", "cover", "reporting", "routing", "auditor", "eot", "undertaking"]


def w_terms(D: Deal) -> Out:
    cs = D.rows("dd_tnc")
    if not cs:
        return [P(f"Terms and conditions not provided in Data Domains (dd_tnc {D.status.get('dd_tnc', 'missing')}) as at {_asof(D)}.")], ["dd_tnc"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(cs, key=lambda r: CAT_ORDER.index(r.get("category")) if r.get("category") in CAT_ORDER else 99):
        groups.setdefault(str(r.get("limit_group") or "All limits"), []).append(r)
    blocks, n = [], 0
    for g, rs in groups.items():
        blocks.append(H(f"Terms for {g}"))
        items = []
        for k, r in enumerate(rs, start=1):
            n += 1
            st = str(r.get("status") or "")
            tail = {"new": f" (condition {k} of {len(rs)}; new, proposed {_asof(D)})",
                    "existing": f" (condition {k} of {len(rs)}; existing, carried forward {_asof(D)})"}.get(st, f" (condition {k} of {len(rs)}, {_asof(D)})")
            if st == "not complied":
                tail = f" (existing condition of {r.get('committee_ref') or 'the last approval'}: not complied as at {_asof(D)})"
            elif st == "complied":
                tail = f" (condition {k} of {len(rs)}; existing, complied as at {_asof(D)})"
            items.append(f"{r.get('text', '').rstrip('.')}{tail}.")
        blocks.append(NL(items))
    nc = [r for r in D.rows("dd_condition") if r.get("status") == "not complied"]  # the earlier approval's conditions, with measures
    seen = {str(r.get("text", "")).strip().lower() for r in nc}
    nc += [r for r in cs if r.get("status") == "not complied" and str(r.get("text", "")).strip().lower() not in seen]
    blocks.append(H("Status of existing conditions"))
    if nc:
        rows = []
        for r in nc:
            ach, req = num(r.get("achieved")), num(r.get("required"))
            status = f"Not complied: {xx(ach)} achieved against {xx(req)} ({pct(ach / req) if ach is not None and req else '–'})" if req else "Not complied"
            rows.append([r.get("text", ""), r.get("committee_ref") or "–", d(r.get("due")) or "–", status])
        blocks.append(T(["Condition", "Committee ref.", "Due", "Status"], rows, source=" + ".join(D.src(x) for x in ("dd_tnc", "dd_condition") if D.rows(x)),
                        widths=[8.0, 2.4, 2.0, 4.6]))
        blocks.append(P(f"{len(nc)} of {max(len(nc), len([r for r in cs if r.get('status') != 'new']))} existing conditions not complied as at {_asof(D)}."))
    else:
        blocks.append(P(f"No existing condition recorded as not complied in dd_tnc or dd_condition as at {_asof(D)}."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 6 group exposure and references

def _ref_decision(D: Deal, text: Any) -> str:
    """A committee decision quoted in a reference line; a paper on a request keeps its case (R16 x: "LG and OD lines", "SAR 160m")."""
    t = str(text or "").strip()
    return t.rstrip(".") if D.p.get("exposure_after_request") else t.lower()


def w_group_exposure(D: Deal) -> Out:
    gf, gt = num(D.get("group_exposure_funded")), num(D.get("group_exposure_total"))
    ce, cp = num(D.get("group_cap_existing")), num(D.get("group_cap_proposed"))
    blocks, gaps = [], []
    ents = D.rows("b360_entity")
    if gt is None and ents:
        gf = sum(num(r.get("exposure_funded")) or 0 for r in ents)
        gt = sum(num(r.get("exposure_total")) or 0 for r in ents)
    tp = totals(D)[2] if D.p.get("exposure_after_request") else 0.0
    if tp and ents and any(str(r.get("relation") or "").lower() == "subject" for r in ents):
        # R16 x: a paper on a request (the credit response): the group after the request is the other entities' exposure plus
        # the borrower's proposed total limits, not the register's exposure today
        others = [r for r in ents if str(r.get("relation") or "").lower() != "subject"]
        gt = round(sum(num(r.get("exposure_total")) or 0 for r in others) + tp, 1)
        gf = None
    if gt is not None:
        s = f"Group exposure after this request is {D.money(gt)} total" + (f", of which {D.money(gf)} funded ({pct(gf / gt)})" if gf is not None and gt else "") + f", as at {_asof(D)}."
        blocks.append(P(s))
        if ce is not None and not (cp or ce):
            blocks.append(P(f"No group exposure cap is set for {D.group or D.name} in dd_deal (0.0 as at {_asof(D)}); not applicable."))
        elif ce is not None:
            blocks.append(P(f"The approved group cap is {D.money(ce)}" + (f" and {D.money(cp)} is proposed" if cp is not None and cp != ce else " and is unchanged")
                            + f"; exposure uses {pct(gt / (cp or ce))} of the {'proposed' if cp else 'approved'} cap as at {_asof(D)}"
                            + (f"; __the group exposure of {D.money(gt)} is above the approved cap of {D.money(ce)}__" if D.p.get("exposure_after_request") and ce and gt > ce else "")
                            + "."))
        else:
            gaps.append("group cap")
            blocks.append(P(f"Group exposure cap not provided as at {_asof(D)}."))
    else:
        gaps.append("group exposure")
        blocks.append(P(f"Group exposure not available in Data Domains as at {_asof(D)}."))
    if ents:
        blocks.append(T(["Group entity", "Relation", f"Funded ({D.ccy} m)", "Total", "Classification"],
                        [[r.get("entity"), r.get("relation"), D.m(r.get("exposure_funded")), D.m(r.get("exposure_total")), r.get("classification") or "Regular"] for r in ents],
                        source=D.src("b360_entity"), widths=[6.0, 3.0, 2.4, 2.4, 3.2]))
    hist = [r for r in D.rows("dd_reference") if num(r.get("total_limit")) is not None]
    other = [r for r in D.rows("dd_reference") if num(r.get("total_limit")) is None]
    blocks.append(H("References"))
    if hist:
        blocks.append(BL([f"{r.get('committee_ref')} dated {d(r.get('date'))}: total limits {D.money(r.get('total_limit'))}"
                          + (f" (PY {D.money(hist[i - 1].get('total_limit'))})" if i else " (earliest approval per dd_reference)") + f"; {_ref_decision(D, r.get('decision'))}." for i, r in enumerate(hist)]))
    rd = D.get("received_date")
    refs = [f"Credit file requested on {d(rd)}, {_days(rd, D.get('as_of'))} days before the paper date of {_asof(D)}." if rd else ""]
    refs += [f"{str(r.get('kind') or 'reference').replace('_', ' ').capitalize()} {r.get('committee_ref') or ''} dated {d(r.get('date'))}: {str(r.get('decision') or '').rstrip('.')} (per dd_reference)."
             for r in other]
    ev = sorted(D.rows("dd_workflow_event"), key=lambda r: num(r.get("seq")) or 0)
    refs += [f"{str(r.get('to_state') or r.get('state') or r.get('event')).replace('_', ' ').capitalize()} on {d(str(r.get('at') or r.get('date') or '')[:10])} by "
             f"{r.get('actor') or r.get('by') or 'not recorded'} (per dd_workflow_event)." for r in ev[:6]]
    if any(refs):
        blocks.append(BL(refs))
    if not hist and not ev:
        blocks.append(P(f"Committee history not available in Data Domains as at {_asof(D)}."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 7 background and ownership

def _age(dob: Any, asof: str) -> str:
    try:
        return str(int(str(asof)[:4]) - int(str(dob)[:4]))
    except (TypeError, ValueError):
        return "–"


def w_background(D: Deal) -> Out:
    p = D.p
    blocks, gaps = [], []
    inc, place = d(first(p, "incorporation_date")), first(p, "incorporation_place")
    if inc:
        blocks.append(P(f"Trade licence {first(p, 'trade_licence_no', default='(number not provided)')}: incorporated on {inc}" + (f" in {place}" if place else "")
                        + f" as a {str(first(p, 'legal_status', default='legal status not provided')).lower()}; activity as per the trade licence: "
                        f"{first(p, 'activity', 'sub_sector', default='not provided')}."))
    else:
        gaps.append("trade licence")
        blocks.append(P(f"Trade licence details not provided in Data Domains as at {_asof(D)}; sector as per dd_proposal: {D.get('sector', default='not provided')}."))
    sh = D.rows("b360_shareholder")
    if sh:
        blocks.append(H("Shareholders"))
        y = str(D.as_of or "2026")[:4] if str(D.as_of or "")[:4].isdigit() else str(_asof(D))[-4:]
        blocks.append(T(["Entity", "Shareholder", "Age", "Nationality", "Share", "UBO"],
                        [[r.get("entity"), r.get("holder"), _age(r.get("dob"), y) if r.get("dob") else "–", r.get("nationality") or "–", pct(r.get("pct")),
                          "Yes" if str(r.get("ubo_flag")) in ("1", "True", "true") else "No"] for r in sh],
                        source=D.src("b360_shareholder"), widths=[4.6, 4.4, 1.0, 2.0, 1.6, 1.2]))
        ubo = [r for r in sh if str(r.get("ubo_flag")) in ("1", "True", "true")]
        if ubo:
            blocks.append(P("Beneficial owner(s) per Borrower 360 as at " + _asof(D) + ": " + "; ".join(f"{r.get('holder')} ({pct(r.get('pct'))} of {r.get('entity')})" for r in ubo) + "."))
    else:
        gaps.append("b360_shareholder")
        blocks.append(P(f"Shareholders and UBOs not available in Borrower 360 (b360_shareholder {D.status.get('b360_shareholder', 'missing')}) as at {_asof(D)}."))
    oc = D.rows("b360_ownership_change")
    if oc:
        blocks.append(P("Recent ownership changes per Borrower 360: " + "; ".join(
            f"{pct(r.get('pct'))} of {r.get('entity')} from {r.get('from_holder')} to {r.get('to_holder')} on {d(r.get('date'))}" for r in oc) + "."))
    else:
        blocks.append(P(f"No ownership change recorded in Borrower 360 (b360_ownership_change {D.status.get('b360_ownership_change', 'missing')}) as at {_asof(D)}."))
    bd = D.rows("b360_board")
    if bd:
        blocks.append(H("Board and key persons"))
        blocks.append(T(["Person", "Role", "Entity", "Since", "Other directorships"],
                        [[r.get("person"), r.get("role"), r.get("entity"), d(r.get("since")) or "–", r.get("other_directorships") or "None recorded"] for r in bd],
                        source=D.src("b360_board"), widths=[3.6, 2.8, 4.4, 2.0, 4.2]))
    ents = D.rows("b360_entity")
    if ents:
        blocks.append(H("Group entities"))
        blocks.append(T(["Entity", "Relation", "Activity", "Country"], [[r.get("entity"), r.get("relation"), r.get("activity"), r.get("country")] for r in ents],
                        source=D.src("b360_entity"), widths=[5.4, 3.0, 6.2, 2.4]))
        blocks.append(P(f"The group has {len(ents)} entities per Borrower 360 as at {_asof(D)}; their exposure at the bank is in section 6."))
    mix, st, pt, staff = first(p, "activity_mix"), first(p, "sales_terms"), first(p, "purchase_terms"), first(p, "staff_count")
    lines = []
    bp = [r for r in D.rows("dd_business_profile") if r.get("item_kind") not in ("geopolitical", "market")]
    if bp:
        lab = {"activity_mix": "Activity mix", "sales_terms": "Sales terms", "purchase_terms": "Purchase terms", "top_customer": "Customers",
               "top_supplier": "Suppliers", "staff": "Staff"}
        for r in bp:
            lines.append(f"{lab.get(str(r.get('item_kind')), 'Profile')}: {_profile_text(r)}")
        mix = st = pt = None
        if any(r.get("item_kind") == "staff" for r in bp):
            staff = None
    if mix:
        lines.append(f"Activity mix as per business: {mix}.")
    if st:
        lines.append(f"Sales terms as per business: {st} ({_asof(D)}).")
    if pt:
        lines.append(f"Purchase terms as per business: {pt} ({_asof(D)}).")
    if staff:
        lines.append(f"Staff count of {int(num(staff) or 0):,} as per business at {_asof(D)}.")
    if lines:
        blocks.append(BL(lines))
    else:
        gaps.append("activity and terms")
        blocks.append(P(f"Activity mix, sales and purchase terms not provided as at {_asof(D)}."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 8 relationship with the bank (conduct)

def w_relationship(D: Deal) -> Out:
    blocks, gaps = [], []
    since = d(D.get("account_opened"))
    dm = sorted(D.rows("dd_account_conduct"), key=lambda r: str(first(r, "month", "reporting_month", default="")))
    others: dict[str, list[dict[str, Any]]] = {}
    obs = {str(r.get("obligor_id")) for r in dm if r.get("obligor_id")}
    if len(obs) > 1:
        # R16 x: the deal's conduct rows hold the borrower and its connected parties month by month: the borrower's 12 months
        # first, each connected party apart (its cheques are not the borrower's)
        me = {str(x) for x in (D.get("obligor_id"), D.get("cif"), D.get("book_obligor_id")) if x}
        if me & obs:
            for r in dm:
                if str(r.get("obligor_id")) not in me:
                    others.setdefault(str(r.get("obligor_id")), []).append(r)
            dm = [r for r in dm if str(r.get("obligor_id")) in me]
    if since:
        blocks.append(P(f"The relationship dates from {since}, with the account in the name of {D.name} (CIF {D.get('obligor_id', default='not provided')})."))
    else:
        gaps.append("account opened")
        blocks.append(P(f"Date the account was opened not provided as at {_asof(D)}."))
    if dm:
        last12 = dm[-12:]
        tov = sum(num(first(r, "credit_turnover", "turnover_sar_mn", "credit_turnover_sar_mn")) or 0 for r in last12)
        bal = sum(num(first(r, "avg_balance", "avg_balance_sar_mn")) or 0 for r in last12) / len(last12)
        rc = sum(num(first(r, "returned_cheques", "cheques_returned")) or 0 for r in last12)
        rca = sum(num(r.get("returned_cheques_amount")) or 0 for r in last12)
        pdmax = max(num(first(r, "past_due_days_max", "dpd_max")) or 0 for r in last12)
        m0, m1 = d(first(last12[0], "month", "reporting_month")), d(first(last12[-1], "month", "reporting_month"))
        te, to, tp = totals(D)
        blocks.append(P(f"Credit turnover of {D.money(tov)} in the {len(last12)} months {m0} to {m1}"
                        + (f", {xx(tov / te)} the existing limits of {D.money(te)}" if te else "") + f"; average balance {D.money(bal)} over the same months."))
        blocks.append(P(f"{int(rc)} cheques returned between {m0} and {m1}" + (f" for {D.money(rca, 2)}" if rca else "") + "; "
                        + (f"maximum past due of {int(pdmax)} days in the period." if pdmax else f"no past dues recorded in the {len(last12)} months to {m1}.")))
        blocks.append(T(["Month", f"Credit turnover ({D.ccy} m)", "Average balance", "Returned cheques", "Max days past due"],
                        [[d(first(r, "month", "reporting_month")), D.m(first(r, "credit_turnover", "turnover_sar_mn")), D.m(first(r, "avg_balance", "avg_balance_sar_mn")),
                          int(num(first(r, "returned_cheques", "cheques_returned")) or 0), int(num(first(r, "past_due_days_max", "dpd_max")) or 0)] for r in last12],
                        source=D.src("dd_account_conduct"), widths=[2.6, 3.6, 3.2, 3.2, 3.2]))
        if others:
            names = {str(e.get(k)): e.get("entity") for e in D.rows("b360_entity") for k in ("entity_id", "borrower_id") if e.get(k)}
            orows = []
            for oid, rs in sorted(others.items()):
                o12 = rs[-12:]
                orows.append([f"{names.get(oid) or oid} ({oid})", f"{d(first(o12[0], 'month', 'reporting_month'))} to {d(first(o12[-1], 'month', 'reporting_month'))}",
                              D.m(sum(num(first(r, "credit_turnover", "turnover_sar_mn")) or 0 for r in o12)),
                              int(sum(num(first(r, "returned_cheques", "cheques_returned")) or 0 for r in o12)),
                              D.m(sum(num(r.get("returned_cheques_amount")) or 0 for r in o12), 2),
                              int(max(num(first(r, "past_due_days_max", "dpd_max")) or 0 for r in o12))])
            blocks.append(H("Connected parties' accounts (not the borrower's)"))
            blocks.append(T(["Connected party", "Months", f"Credit turnover ({D.ccy} m)", "Returned cheques", "Amount", "Max days past due"], orows,
                            source=D.src("dd_account_conduct"), widths=[5.0, 3.6, 2.6, 2.2, 2.0, 2.2]))
    else:
        gaps.append("dd_account_conduct")
        blocks.append(P(f"Account turnover, balances and returned cheques not available in Deposits (dd_account_conduct {D.status.get('dep_month', 'missing')}) as at {_asof(D)}."))
    lines = [r for r in _tops(D) if num(r.get("existing"))]
    if lines:
        blocks.append(H("Utilisation per limit"))
        blocks.append(BL([f"{r.get('name')}: {D.money(r.get('outstanding'))} outstanding against {D.money(r.get('existing'))} "
                          f"({pct((num(r.get('outstanding')) or 0) / (num(r.get('existing')) or 1))}) as at {_asof(D)}." for r in lines]))
    hist = [r for r in D.rows("dd_reference") if num(r.get("total_limit")) is not None]
    if hist:
        blocks.append(P("History of limits: " + "; ".join(f"{D.money(r.get('total_limit'))} by {r.get('committee_ref')} on {d(r.get('date'))}" for r in hist) + "."))
    pr = D.rows("dd_promise")
    if pr:
        def _prom(r: dict[str, Any]) -> str:
            u = str(r.get("unit") or "")
            if u.startswith("x"):
                return f"{r.get('kind')} of {xx(r.get('promised'), 2)} the limit promised, {xx(r.get('delivered'), 2)} delivered by {d(r.get('due'))} ({r.get('status')})"
            return f"{r.get('kind')} of {r.get('promised')} {u} promised, {r.get('delivered')} delivered by {d(r.get('due'))} ({r.get('status')})"
        blocks.append(P("Undertakings tracked in Deal Desk: " + "; ".join(_prom(r) for r in pr) + "."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 9 status of financed projects

def _is_contractor(D: Deal) -> bool:
    return "construct" in str(D.get("sector", default="")).lower() or bool(D.rows("dd_project"))


def w_projects(D: Deal) -> Out:
    pr = [r for r in D.rows("dd_project") if not r.get("is_new")]
    if not _is_contractor(D):
        return [P(f"Not applicable: {D.name} is in {D.get('sector', default='a sector')} with no financed projects in dd_project as at {_asof(D)}.")], []
    if not pr:
        return [P(f"Status of financed projects not available in Data Domains (dd_project {D.status.get('dd_project', 'missing')}) as at {_asof(D)}.")], ["dd_project"]
    rows = [[r.get("name"), r.get("employer"), r.get("consultant") or "–", D.m(r.get("contract_value_original")), D.m(r.get("contract_value_revised")),
             d(r.get("start_date")), d(r.get("end_date_revised") or r.get("end_date_original")), pct(r.get("wd_pct")), D.m(r.get("received")), D.m(r.get("due")),
             f"{r.get('last_ipc_no') or '–'} ({d(r.get('last_ipc_date')) or '–'})"] for r in pr]
    blocks = [T(["Project", "Employer", "Consultant", "Original", "Revised", "Start", "Completion", "WD%", "Received", "Due", "Last IPC"], rows,
                source=D.src("dd_project"), widths=[2.6, 2.4, 2.0, 1.2, 1.2, 1.5, 1.5, 1.0, 1.2, 1.0, 1.6], size=6.5)]
    for r in pr:
        cv, rv = num(r.get("contract_value_original")), num(r.get("contract_value_revised"))
        eo, er = d(r.get("end_date_original")), d(r.get("end_date_revised"))
        s = [f"**{r.get('name')}** ({r.get('employer')}): contract value {D.money(rv or cv)}" + (f" (original {D.money(cv)})" if rv and cv and rv != cv else "")
             + f", work done {pct(r.get('wd_pct'))} and {D.money(r.get('received'))} received ({pct((num(r.get('received')) or 0) / (rv or cv or 1))} of the contract value) as at {_asof(D)}."]
        if eo and er and eo != er:
            s.append(f"Completion moved from {eo} to {er}; extension of time: {r.get('eot_status') or 'not provided'}.")
        if num(r.get("due")):
            s.append(f"{D.money(r.get('due'))} certified and due as at {d(r.get('last_ipc_date')) or _asof(D)}.")
        if r.get("note"):
            s.append(f"As per business: {one(r.get('note'))}.")
        blocks.append(P(" ".join(s)))
    late = [r for r in pr if r.get("end_date_original") and r.get("end_date_revised") and str(r["end_date_revised"]) > str(r["end_date_original"])]
    blocks.append(P(f"{len(late)} of {len(pr)} financed projects are past their original completion date as at {_asof(D)}; "
                    f"{len([r for r in late if 'not formalised' in str(r.get('eot_status', '')).lower()])} of them have extensions of time not formalised."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 10 CBRBR, 11 bureau, 12 other banks

def w_cbrbr(D: Deal) -> Out:
    rs = D.rows("bureau_cbrbr")
    if not rs:
        return [P(f"Central bank risk bureau (CBRBR) data not available in Data Domains (bureau_cbrbr {D.status.get('bureau_cbrbr', 'missing')}) as at {_asof(D)}.")], ["bureau_cbrbr"]
    rows, tot = [], [0.0, 0.0, 0.0, 0.0]
    for r in rs:
        v = [num(r.get(k)) or 0 for k in ("funded_limit", "funded_outstanding", "nonfunded_limit", "nonfunded_outstanding")]
        tot = [a + b for a, b in zip(tot, v)]
        rows.append([r.get("entity"), *[D.m(x) for x in v], D.m(v[1] + v[3]), r.get("banks") or "–", r.get("classification") or "–"])
    rows.append(["**Total**", *[D.m(x) for x in tot], D.m(tot[1] + tot[3]), "", ""])
    rd = d(rs[0].get("report_date"))
    blocks = [T(["Entity", "Funded limit", "Funded o/s", "Non-funded limit", "Non-funded o/s", "Total o/s", "Banks", "Classification"], rows,
                source=D.src("bureau_cbrbr"), widths=[4.2, 1.7, 1.7, 1.8, 1.8, 1.7, 1.1, 2.0], size=7)]
    blocks.append(P(f"Total CBRBR outstanding of {D.money(tot[1] + tot[3])} across {len(rs)} entities per the report of {rd}; funded {D.money(tot[1])} "
                    f"({pct(tot[1] / (tot[1] + tot[3]) if tot[1] + tot[3] else 0)})."))
    bad = [r for r in rs if str(r.get("classification", "Regular")).lower() not in ("regular", "", "none")]
    if bad:
        blocks.append(P("Classified or watch-listed per CBRBR on " + rd + ": " + "; ".join(
            f"{r.get('entity')} ({r.get('classification')}, {D.money((num(r.get('funded_outstanding')) or 0) + (num(r.get('nonfunded_outstanding')) or 0))} outstanding)" for r in bad) + "."))
    return blocks, []


def w_bureau(D: Deal) -> Out:
    rs = D.rows("bureau_entity_report")
    if not rs:
        return [P(f"Credit bureau (AECB / SIMAH) reports not available in Data Domains (bureau_entity_report {D.status.get('bureau_entity_report', 'missing')}) as at {_asof(D)}.")], ["bureau_entity_report"]
    got = [r for r in rs if str(r.get("provided", 1)) not in ("0", "False", "false")]
    miss = [r for r in rs if r not in got]
    rows = [[r.get("entity"), r.get("role") or "–", D.m(r.get("outstanding")), D.m(r.get("overdue")), int(num(r.get("returned_cheques")) or 0),
             r.get("returned_cheque_dates") or "–", r.get("score") or "–", int(num(r.get("court_cases")) or 0), d(r.get("report_date"))] for r in got]
    blocks = [T(["Entity / UBO", "Role", "Outstanding", "Overdue", "Ret. cheques", "Cheque dates", "Score", "Court cases", "Report"], rows,
                source=D.src("bureau_entity_report"), widths=[4.0, 1.6, 1.6, 1.4, 1.3, 2.4, 1.0, 1.2, 1.9], size=7)]
    for r in got:
        bits = []
        if num(r.get("overdue")):
            bits.append(f"{D.money(r.get('overdue'))} overdue")
        if num(r.get("returned_cheques")):
            bits.append(f"{int(num(r.get('returned_cheques')))} returned cheques ({r.get('returned_cheque_dates') or 'dates not provided'})")
        if num(r.get("court_cases")):
            bits.append(f"{int(num(r.get('court_cases')))} court case(s)")
        if bits:
            blocks.append(P(f"{r.get('entity')}: " + ", ".join(bits) + f" per the bureau report of {d(r.get('report_date'))}."))
    if miss:
        blocks.append(P("Reports not provided: " + "; ".join(f"{r.get('entity')} ({r.get('role')}): {str(r.get('reason') or 'reason not provided').lower()}" for r in miss) + "."))
    return blocks, []


def w_other_banks(D: Deal) -> Out:
    rs = D.rows("other_bank_facility")
    if not rs:
        return [P(f"Other banks' facilities not available in Data Domains (other_bank_facility {D.status.get('other_bank_facility', 'missing')}) as at {_asof(D)}.")], ["other_bank_facility"]
    rows, tot = [], [0.0, 0.0, 0.0, 0.0]
    for r in rs:
        v = [num(r.get(k)) or 0 for k in ("declared_limit", "bureau_limit", "declared_outstanding", "bureau_outstanding")]
        tot = [a + b for a, b in zip(tot, v)]
        rows.append([r.get("bank"), r.get("entity"), *[D.m(x) for x in v], D.m(v[3] - v[2])])
    rows.append(["**Total**", "", *[D.m(x) for x in tot], D.m(tot[3] - tot[2])])
    asof = d(rs[0].get("as_of")) or _asof(D)
    blocks = [T(["Bank", "Group entity", "Limit (client)", "Limit (bureau)", "O/s (client)", "O/s (bureau)", "Difference o/s"], rows,
                source=D.src("other_bank_facility"), widths=[2.6, 4.6, 1.8, 1.8, 1.8, 1.8, 1.8], size=7)]
    blocks.append(P(f"Client-declared limits of {D.money(tot[0])} against {D.money(tot[1])} per the bureau as at {asof}; outstanding declared {D.money(tot[2])} "
                    f"against {D.money(tot[3])} per the bureau, a difference of {D.money(tot[3] - tot[2])} ({pct((tot[3] - tot[2]) / tot[3] if tot[3] else 0)})."))
    notes = [r for r in rs if r.get("note")]
    if notes:
        blocks.append(BL([f"{r.get('bank')} / {r.get('entity')}: {one(r.get('note'))} (per other_bank_facility as at {d(r.get('as_of')) or asof})." for r in notes]))
    gap = [r for r in rs if abs((num(r.get("bureau_limit")) or 0) - (num(r.get("declared_limit")) or 0)) > 0.05]
    if gap:
        blocks.append(P(f"{len(gap)} of {len(rs)} bank lines differ between the client's declaration and the bureau as at {asof}; the difference is not clarified by business."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 13 new project details and cash flow

def w_new_project(D: Deal) -> Out:
    new = [r for r in D.rows("dd_project") if r.get("is_new")]
    if not new:
        if _is_contractor(D):
            return [P(f"No new project in this request per dd_project as at {_asof(D)}; not applicable.")], []
        return [P(f"Not applicable: no project finance in this request for {D.name} as at {_asof(D)}.")], []
    r = new[0]
    blocks = [KV([("Project", r.get("name")), ("Scope", r.get("scope") or "not provided"), ("Employer", r.get("employer")),
                  ("Main contractor", r.get("main_contractor") or D.name), ("Consultant", r.get("consultant") or "not provided"),
                  ("Contract value", D.money(r.get("contract_value_original"))), ("LG requirement", r.get("lg_requirement") or "not provided"),
                  ("Payment terms", r.get("payment_terms") or "not provided"), ("Start / completion", f"{d(r.get('start_date'))} / {d(r.get('end_date_original'))}"),
                  ("Expected margin (business)", pct(r.get("expected_margin_pct")) or "not provided")], cols=2)]
    cf = sorted([x for x in D.rows("dd_project_cashflow") if x.get("project_id") in (r.get("project_id"), None)], key=lambda x: num(x.get("month")) or 0)
    gaps = []
    if cf:
        cost_keys = [k for k in ("cost_materials", "cost_subcontract", "cost_labour", "cost_overheads") if any(num(x.get(k)) for x in cf)]
        tc = {k: sum(num(x.get(k)) or 0 for x in cf) for k in cost_keys}
        total = sum(tc.values()) or 1
        blocks.append(P(f"Project cost of {D.money(total)} over {len(cf)} months from {d(cf[0].get('period'))} to {d(cf[-1].get('period'))}: "
                        + ", ".join(f"{k.replace('cost_', '')} {D.money(v)} ({pct(v / total)})" for k, v in tc.items()) + "."))
        peak = min(cf, key=lambda x: num(x.get("cumulative")) or 0)
        ret = sum(num(x.get("retention_held")) or 0 for x in cf)
        blocks.append(P(f"Cumulative deficit peaks at {D.money(-(num(peak.get('cumulative')) or 0))} in month {int(num(peak.get('month')) or 0)} "
                        f"({d(peak.get('period'))}); retention of {D.money(ret)} is held by the employer by {d(cf[-1].get('period'))}."))
        if any(x.get("cumulative_delay_60d") is not None for x in cf):
            pk2 = min(cf, key=lambda x: num(x.get("cumulative_delay_60d")) or 0)
            base, stressed = -(num(peak.get("cumulative")) or 0), -(num(pk2.get("cumulative_delay_60d")) or 0)
            blocks.append(P(f"With certificates paid 60 days late the peak deficit is {D.money(stressed)} in month {int(num(pk2.get('month')) or 0)} ({d(pk2.get('period'))}), "
                            f"{pct((stressed - base) / base if base else 0)} above the base case."))
        step = max(1, len(cf) // 10)
        blocks.append(T(["Month", "Period", f"Costs ({D.ccy} m)", "Receipts", "Retention held", "Cumulative", "Cumulative (60-day delay)"],
                        [[int(num(x.get("month")) or 0), d(x.get("period")), D.m(sum(num(x.get(k)) or 0 for k in cost_keys)), D.m(x.get("receipts")),
                          D.m(x.get("retention_held")), D.m(x.get("cumulative")), D.m(x.get("cumulative_delay_60d"))] for x in cf[::step]],
                        source=D.src("dd_project_cashflow"), widths=[1.4, 2.0, 2.4, 2.4, 2.4, 2.4, 3.0]))
    else:
        gaps.append("dd_project_cashflow")
        blocks.append(P(f"Project cash flow not available in Data Domains (dd_project_cashflow {D.status.get('dd_project_cashflow', 'missing')}) as at {_asof(D)}."))
    blocks.append(H("About the project employer"))
    blocks.append(P(f"As per business ({_asof(D)}): {r.get('employer_profile') or 'employer ownership, listing and size not provided'}."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 14 financials, 15 synopsis

FIN_ROWS = [("Revenue", "revenue"), ("Gross profit", "gross_profit"), ("GPM", "_gpm"), ("Operating profit", "operating_profit"), ("OPM", "_opm"),
            ("Net profit", "net_profit"), ("NPM", "_npm"), ("EBITDA", "ebitda"), ("Total assets", "total_assets"), ("ROA", "_roa"),
            ("Bank debt short term", "bank_debt_st"), ("Bank debt long term", "bank_debt_lt"), ("Net worth", "net_worth"), ("ROE", "_roe"),
            ("Leverage (TL/NW)", "_lev"), ("Gearing (bank debt/NW)", "_gear"), ("Working capital", "_wc"), ("Current ratio", "_cr"),
            ("Cash cycle (days)", "cash_cycle_days"), ("Operating cash flow", "ocf")]


def _actual(x: dict[str, Any]) -> bool:
    """An audited (or actual) year: not an interim period, not a projection."""
    return str(x.get("kind") or "audited") in ("audited", "actual")


def fin_rows(D: Deal) -> list[dict[str, Any]]:
    rows = D.rows("dd_financials_detail")
    out = []
    for r in rows:
        g = lambda *k: num(first(r, *k))  # noqa: E731
        x = dict(r)
        x["revenue"], x["ebitda"], x["net_worth"] = g("revenue", "revenue_sar_mn"), g("ebitda", "ebitda_sar_mn"), g("net_worth", "net_worth_sar_mn")
        if x.get("bank_debt_st") is None and g("total_debt_sar_mn") is not None:
            x["bank_debt_st"] = g("total_debt_sar_mn")
        ann = 12.0 / (g("months") or 12.0)
        rev, nw, ta = x["revenue"], x["net_worth"], g("total_assets")
        tl = (ta - nw) if ta is not None and nw is not None else None
        ca, cl = g("current_assets"), g("current_liabilities")
        for key, a, b, k in (("_gpm", "gross_profit", rev, 1), ("_opm", "operating_profit", rev, 1), ("_npm", "net_profit", rev, 1)):
            v = g(a)
            x[key] = (v / b) if v is not None and b else None
        x["_roa"] = (g("net_profit") or 0) * ann / ta if ta and g("net_profit") is not None else None
        x["_roe"] = (g("net_profit") or 0) * ann / nw if nw and g("net_profit") is not None else None
        x["_lev"] = tl / nw if tl is not None and nw else None
        debt = (num(x.get("bank_debt_st")) or 0) + (num(x.get("bank_debt_lt")) or 0)
        x["_gear"] = debt / nw if nw and debt else None
        x["_wc"] = ca - cl if ca is not None and cl is not None else None
        x["_cr"] = ca / cl if ca is not None and cl else (g("current_ratio_x"))
        x["_tl"] = tl
        x["_label"] = (f"FY{r.get('year')}" if str(r.get("kind", "audited")) in ("audited", "actual", "") else
                       f"{'H1' if (g('months') or 12) == 6 else str(int(g('months') or 0)) + 'M'} {r.get('year')}" if r.get("kind") == "interim" else f"{r.get('year')} P")
        out.append(x)
    return out


def _scopes(D: Deal) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for x in fin_rows(D):
        out.setdefault(str(x.get("entity_scope") or "standalone"), []).append(x)
    for k in out:
        out[k].sort(key=lambda x: (int(x.get("year") or 0), 0 if x.get("kind") != "interim" else 1))
    return out


def _cell(x: dict[str, Any], key: str) -> str:
    v = num(x.get(key))
    if v is None:
        return "–"
    if key in ("_gpm", "_opm", "_npm", "_roa", "_roe"):
        return f"{v * 100:,.1f}%"
    if key in ("_lev", "_gear", "_cr"):
        return f"{v:,.2f}x"
    if key == "cash_cycle_days":
        return f"{v:,.0f}"
    return f"{v:,.1f}"


def w_financials(D: Deal) -> Out:
    sc = _scopes(D)
    if not sc:
        return [P(f"Financial statements not available in Data Domains (dd_financials_detail {D.status.get('dd_financials_detail', 'missing')}) as at {_asof(D)}.")], ["dd_financials_detail"]
    blocks, gaps = [], []
    main = sc.get("standalone") or next(iter(sc.values()))
    last = [x for x in main if _actual(x)][-1:] or main[-1:]
    a = last[0]
    aud, panel, op = a.get("auditor"), a.get("auditor_panel"), str(a.get("opinion") or "")
    if aud:
        blocks.append(P(f"As per the audited accounts for FY{a.get('year')}, the auditor is {aud}" + (f", {panel}" if panel else "")
                        + f", with a {op or 'not provided'} opinion on the statements to {d(a.get('period_end')) or 'FY' + str(a.get('year'))}."))
        if op.lower() == "qualified":
            blocks.append(P(f"Basis of qualification as per the auditor (FY{a.get('year')}): {one(a.get('qualification_basis')) or 'not provided'}."))
    else:
        gaps.append("auditor and opinion")
        blocks.append(P(f"Auditor, opinion and qualification basis not provided for FY{a.get('year')}."))
    if len(sc) > 1 or any(x.get("entity_name") for x in main):
        blocks.append(P(f"{len(sc)} statement scope(s) in Data Domains as at {_asof(D)}: " + "; ".join(
            f"{k} ({(v[0].get('entity_name') or D.name)}, {', '.join(x['_label'] for x in v)})" for k, v in sc.items()) + "."))
    for k, v in sc.items():
        blocks.append(H(f"{k.capitalize()}: {v[0].get('entity_name') or D.name} ({D.ccy} m)"))
        blocks.append(T(["Item"] + [x["_label"] for x in v], [[lab] + [_cell(x, key) for x in v] for lab, key in FIN_ROWS if any(num(x.get(key)) is not None for x in v)],
                        source=D.src("dd_financials_detail"), size=7))
    return blocks, gaps


def _yoy(D: Deal, cur: Any, prev: Any, label: str, year: Any, unit: str = "money") -> str:
    c, p = num(cur), num(prev)
    if c is None:
        return ""
    f = (lambda v: D.money(v)) if unit == "money" else (lambda v: f"{v * 100:,.1f}%") if unit == "pct" else (lambda v: f"{v:,.2f}x") if unit == "x" else (lambda v: f"{v:,.0f} days")
    if p is None:
        return f"{label} of {f(c)} in FY{year} (PY not provided)."
    verb = "rose" if c > p else "fell" if c < p else "was unchanged"
    chg = f", {'+' if c >= p else ''}{(c - p) / abs(p) * 100:,.1f}%" if p and unit == "money" else ""
    return f"{label} {verb} to {f(c)} in FY{year} (PY {f(p)}{chg})."


def adjusted(x: dict[str, Any]) -> dict[str, Any]:
    """Credit's re-performance: net worth less intangibles, related-party receivables, non-core investments; shareholder
    accounts added back when subordinated. Every adjustment is listed."""
    nw = num(x.get("net_worth"))
    if nw is None:
        return {}
    adj, items = nw, []
    for k, lab, sign in (("intangibles", "intangibles", -1), ("related_party_receivable", "due from related parties", -1),
                         ("noncore_investments", "non-core investments", -1), ("shareholder_accounts", "subordinated shareholder accounts", +1)):
        v = num(x.get(k))
        if v:
            adj += sign * v
            items.append((lab, sign * v))
    tl = x.get("_tl")
    ca, cl = num(x.get("current_assets")), num(x.get("current_liabilities"))
    rp = num(x.get("related_party_receivable")) or 0
    out = {"net_worth": nw, "adj_net_worth": adj, "items": items}
    if tl is not None and adj > 0:
        out["adj_leverage"] = (tl - (num(x.get("shareholder_accounts")) or 0)) / adj
    if ca is not None and cl is not None:
        out["adj_wc"] = ca - rp - cl
        out["adj_cr"] = (ca - rp) / cl if cl else None
    return out


def w_synopsis(D: Deal) -> Out:
    sc = _scopes(D)
    if not sc:
        return [P(f"Financial synopsis not available: no statements in Data Domains as at {_asof(D)}; adjusted figures not provided.")], ["dd_financials_detail"]
    main = sc.get("standalone") or next(iter(sc.values()))
    aud = [x for x in main if _actual(x)]
    cur = aud[-1] if aud else main[-1]
    prev = aud[-2] if len(aud) > 1 else {}
    y = cur.get("year")
    b: list[str] = []
    b.append(_yoy(D, cur.get("revenue"), prev.get("revenue"), "Revenue", y))
    b.append(_yoy(D, cur.get("_gpm"), prev.get("_gpm"), "Gross margin", y, "pct"))
    b.append(_yoy(D, cur.get("net_profit"), prev.get("net_profit"), "Net profit", y))
    ca = num(cur.get("current_assets"))
    if ca:
        parts = [(lab, num(cur.get(k))) for lab, k in (("receivables", "receivables"), ("inventory", "inventory"), ("retentions", "retention_receivable"),
                                                       ("due from related parties", "related_party_receivable"), ("cash", "cash")) if num(cur.get(k))]
        b.append(f"Current assets of {D.money(ca)} at {d(cur.get('period_end')) or 'FY' + str(y)}: " + ", ".join(f"{lab} {D.money(v)} ({pct(v / ca)})" for lab, v in parts) + ".")
    rec = num(cur.get("receivables"))
    if rec and any(num(cur.get(k)) is not None for k in ("rec_0_90", "rec_over_365")):
        buckets = [(lab, num(cur.get(k))) for lab, k in (("0-90 days", "rec_0_90"), ("91-180", "rec_91_180"), ("181-365", "rec_181_365"), ("over 365", "rec_over_365")) if num(cur.get(k)) is not None]
        b.append(f"Receivables ageing at {d(cur.get('period_end'))}: " + ", ".join(f"{lab} {D.money(v)} ({pct(v / rec)})" for lab, v in buckets) + ".")
    elif rec:
        b.append(f"Receivables ageing for FY{y} not provided; receivables of {D.money(rec)} at {d(cur.get('period_end')) or 'FY' + str(y)}.")
    if num(cur.get("top_n_share")) is not None:
        b.append(f"Concentration: the top {int(num(cur.get('top_n')) or 0)} counterparties account for {pct(cur.get('top_n_share'))} of receivables at {d(cur.get('period_end'))}.")
    rp = num(cur.get("related_party_receivable"))
    if rp:
        b.append(f"Due from related parties of {D.money(rp)} at {d(cur.get('period_end'))}" + (f" (PY {D.money(prev.get('related_party_receivable'))})" if prev.get("related_party_receivable") else "")
                 + (f", {pct(rp / ca)} of current assets" if ca else "") + (f" and {pct(rp / rec)} of receivables." if rec else "."))
    if num(cur.get("retention_receivable")):
        b.append(f"Retention receivables of {D.money(cur.get('retention_receivable'))} at {d(cur.get('period_end'))}" + (f", {pct(num(cur.get('retention_receivable')) / ca)} of current assets." if ca else "."))
    if num(cur.get("backlog")) is not None:
        bl, blp = num(cur.get("backlog")), num(cur.get("backlog_prior"))
        b.append(f"Backlog of {D.money(bl)} at {d(cur.get('period_end'))}" + (f" (PY {D.money(blp)})" if blp else "") + (f", {xx(bl / num(cur.get('revenue')), 1)} FY{y} revenue." if num(cur.get("revenue")) else "."))
    if cur.get("_tl") is not None:
        b.append(f"Total liabilities of {D.money(cur['_tl'])} at {d(cur.get('period_end'))}, of which bank debt {D.money((num(cur.get('bank_debt_st')) or 0) + (num(cur.get('bank_debt_lt')) or 0))} "
                 f"({pct(((num(cur.get('bank_debt_st')) or 0) + (num(cur.get('bank_debt_lt')) or 0)) / cur['_tl'] if cur['_tl'] else 0)}).")
    b.append(_yoy(D, cur.get("_lev"), prev.get("_lev"), "Leverage (total liabilities / net worth)", y, "x"))
    b.append(_yoy(D, cur.get("_wc"), prev.get("_wc"), "Working capital", y))
    a = adjusted(cur)
    if a.get("items"):
        b.append(f"Adjusted net worth of {D.money(a['adj_net_worth'])} at {d(cur.get('period_end'))} against {D.money(a['net_worth'])} reported, after "
                 + ", ".join(f"{'adding' if v > 0 else 'netting'} {lab} of {D.money(abs(v))} ({pct(abs(v) / a['net_worth'])} of reported net worth)" for lab, v in a["items"]) + ".")
        if a.get("adj_leverage") is not None:
            b.append(f"On the adjusted net worth, leverage is {xx(a['adj_leverage'])} against {xx(cur.get('_lev'))} reported at {d(cur.get('period_end'))}.")
        if a.get("adj_wc") is not None and rp:
            b.append(f"Excluding due from related parties, adjusted working capital is {D.money(a['adj_wc'])} and the adjusted current ratio {xx(a.get('adj_cr'))} at {d(cur.get('period_end'))} "
                     f"(reported {D.money(cur.get('_wc'))} and {xx(cur.get('_cr'))}).")
    else:
        b.append(f"Adjusted net worth not computed: intangibles, related-party balances and shareholder accounts not provided for FY{y}.")
    if num(cur.get("contingent_liabilities")):
        b.append(f"Contingent liabilities of {D.money(cur.get('contingent_liabilities'))} at {d(cur.get('period_end'))}, {xx(num(cur.get('contingent_liabilities')) / (num(cur.get('net_worth')) or 1), 1)} net worth.")
    b.append(_yoy(D, cur.get("ocf"), prev.get("ocf"), "Operating cash flow", y))
    b.append(_yoy(D, cur.get("cash_cycle_days"), prev.get("cash_cycle_days"), "Cash cycle", y, "days"))
    inter = [x for x in main if x.get("kind") == "interim"]
    if inter:
        i = inter[-1]
        mths = num(i.get("months")) or 6
        ann = (num(i.get("revenue")) or 0) * 12 / mths
        b.append(f"Interim {i['_label']} revenue of {D.money(i.get('revenue'))} annualises to {D.money(ann)}"
                 + (f", {pct(ann / num(cur.get('revenue')) - 1)} against FY{y} (PY basis {D.money(cur.get('revenue'))})." if num(cur.get("revenue")) else ".")
                 + f" Net worth of {D.money(i.get('net_worth'))} at {d(i.get('period_end'))} (unaudited).")
    par = sc.get("consolidated")
    if par:
        pc = ([x for x in par if _actual(x)] or par)[-1]
        b.append(f"Parent consolidated FY{pc.get('year')}: revenue {D.money(pc.get('revenue'))}, net worth {D.money(pc.get('net_worth'))}, leverage {xx(pc.get('_lev'))}, "
                 f"bank debt {D.money((num(pc.get('bank_debt_st')) or 0) + (num(pc.get('bank_debt_lt')) or 0))} at {d(pc.get('period_end'))}.")
        if pc.get("note"):
            b.append(f"As per business ({d(pc.get('period_end'))}): {pc.get('note')}.")
    return [BL([x for x in b if x])] + fin_quality_blocks(D), []


def fin_quality_blocks(D: Deal, max_lines: int = 6) -> list[dict[str, Any]]:
    """R13 Q: the "Financial quality" paragraph (grade A-D, the flagged signals with number, threshold and source, the
    statistical screens with their reliability, what could not be assessed), from backend.dealdesk.fin_quality."""
    try:
        from backend.dealdesk import fin_quality as FQ
        ps = FQ.paragraph(D.pid, max_lines=max_lines)
    except Exception as e:  # noqa: BLE001 - the screen never takes the synopsis down
        return [H("Financial quality"), P(f"Financial quality screen not available as at {_asof(D)} ({type(e).__name__}).")]
    if not ps:
        return []
    return [H("Financial quality"), P(ps[0])] + ([BL(ps[1:])] if len(ps) > 1 else [])


# ------------------------------------------------------------------------------------------------ 16 geopolitical effects

def w_geopolitical(D: Deal) -> Out:
    sec = str(D.get("sector", default="")).lower()
    sc = [r for r in D.rows("dd_stress_scenario") if r.get("family") in ("macro", None) and r.get("narrative") and str(r.get("scope") or "bank") == "bank" and (not r.get("sectors") or any(
        s.strip().lower() in sec or sec in s.strip().lower() for s in str(r.get("sectors")).split(";")))]
    out, gaps = [], []
    if sc:
        out.append(BL([f"{r.get('name')} ({r.get('severity')}): {str(r.get('narrative')).rstrip('.')}, per the bank's scenario set as at {d(r.get('as_of')) or _asof(D)}." for r in sc]))
    elif D.rows("dd_stress_scenario"):
        gaps.append("scenario narratives")
        out.append(P(f"Scenario narratives for {D.get('sector', default='this sector')} not available in dd_stress_scenario as at {_asof(D)}."))
    else:
        gaps.append("dd_stress_scenario")
        out.append(P(f"Scenario narratives for {D.get('sector', default='this sector')} not available in Data Domains (dd_stress_scenario {D.status.get('dd_stress_scenario', 'missing')}) as at {_asof(D)}."))
    macro = [r for r in D.rows("dd_stress_result") if r.get("family") == "macro"]
    for r in macro:
        out.append(P(f"Under '{r.get('scenario')}' ({r.get('severity')}), " + (f"{r.get('what_breaks')} at {r.get('value')}" if str(r.get("breaks")) in ("1", "True", "true") else "nothing breaks")
                     + f" per the Deal Desk stress of {_asof(D)}."))
    geo = [r for r in D.rows("dd_business_profile") if r.get("item_kind") in ("geopolitical", "market")]
    if geo:
        out.append(H("As per business"))
        out.append(BL([f"{r.get('label')}: {_profile_text(r)}" for r in geo]))
    else:
        out.append(P(f"Effect on routes, ports, input costs and labour as per business: not provided in the request of {d(D.get('received_date')) or _asof(D)}."
                     if not D.get("geopolitical_note") else f"As per business ({d(D.get('received_date')) or _asof(D)}): {D.get('geopolitical_note')}."))
    return out, gaps


# ------------------------------------------------------------------------------------------------ 17 exceptions and other observations

def w_exceptions(D: Deal) -> Out:
    fs = D.rows("dd_review_finding") + D.rows("dd_policy_exception")
    # R13 Q: the financial-quality findings are written once, under Financial quality in the synopsis (section 15)
    fq = [f for f in fs if str(f.get("category") or "") == "financial_quality"]
    fs = [f for f in fs if f not in fq]
    exc = [f for f in fs if str(f.get("kind", "")).lower() == "exception"]
    obs = [f for f in fs if f not in exc]
    blocks, gaps = [], []
    blocks.append(H("Exceptions"))
    if exc:
        blocks.append(NL([f"{str(f.get('title')).replace('Pricing clears the hurdle', 'Pricing below the hurdle')}: {str(f.get('text', '')).rstrip('.')} (finding {f.get('finding_id')}, {f.get('severity')}, per dd_review_finding, {_asof(D)}). "
                          f"{(str(f.get('business_reason')).rstrip('.') + '.') if f.get('business_reason') else 'Reason not provided by business.'}" for f in exc]))
    elif D.status.get("dd_review_finding") == "missing":
        gaps.append("dd_review_finding")
        blocks.append(P(f"Policy exceptions not available: review findings not yet published to Data Domains as at {_asof(D)}."))
    else:
        blocks.append(P(f"Review findings not available in dd_review_finding as at {_asof(D)}; 0 policy exceptions recorded."))
    blocks.append(H("Other observations"))
    def _u(t: str, sev: Any) -> str:  # R14 p: key concerns bold and underlined
        return f"__{t}__" if str(sev) in ("critical", "high") else t
    obs = sorted(obs, key=lambda f: ({"critical": 0, "high": 0, "major": 1, "medium": 1, "minor": 2}.get(str(f.get("severity")), 3), str(f.get("finding_id"))))
    items = [_u(f"We note that {_obs_text(f)} (finding {f.get('finding_id')}, {f.get('severity')}, per dd_review_finding)" + ("" if any(ch.isdigit() for ch in str(f.get("text", ""))) else f", as at {_asof(D)}"), f.get("severity")) + "."
             for f in obs[:15]]
    if len(obs) > 15:
        items.append(f"{len(obs) - 15} further observations are in the findings register (dd_review_finding) as at {_asof(D)}.")
    docs = D.rows("dd_document")
    miss = [x for x in docs if str(x.get("status")) in ("pending", "expired", "missing")]
    if miss:
        items.append(f"{len(miss)} of {len(docs)} required documents are pending or expired as at {_asof(D)}: " + "; ".join(
            f"{x.get('name')} ({x.get('status')}{', dated ' + d(x.get('date')) if x.get('date') else ''}; {x.get('clause')})" for x in miss) + ".")
    elif D.status.get("dd_document") != "live":
        items.append(f"Document checklist not available in Data Domains (dd_document {D.status.get('dd_document', 'missing')}) as at {_asof(D)}.")
    pend = [r for r in D.rows("dd_security") if r.get("perfection_status") == "pending"]
    if pend:
        items.append(f"{len(pend)} security item(s) unperfected as at {_asof(D)}: " + "; ".join(f"{r.get('item_type')} due {d(r.get('perfection_due')) or 'date not provided'}" for r in pend) + ".")
    ins = D.rows("b360_insider_link")
    for r in ins:
        items.append(f"Insider link per Borrower 360: {r.get('person')} ({pct(r.get('share_pct'))} of {r.get('entity')}) is a {r.get('link_kind')} ({r.get('staff_role')}), as at {d(r.get('as_of')) or _asof(D)}.")
    ents = [r for r in D.rows("b360_entity") if str(r.get("classification", "")).lower() not in ("", "regular", "none") or str(r.get("litigation")) in ("1", "True")]
    gtot = sum(num(r.get("exposure_total")) or 0 for r in D.rows("b360_entity")) or None
    for r in ents:
        ex = num(r.get("exposure_total")) or 0.0
        items.append(f"Related party {r.get('entity')} is {status_phrase(r.get('classification') or 'litigation')}"
                     + f" with {D.money(ex)} of exposure at the bank ({pct(ex / gtot if gtot else 0.0)} of group exposure)"
                     + f" as at {_asof(D)}" + (f" ({r.get('credit_status_note')})" if r.get("credit_status_note") else "") + ".")
    if fq:
        items.append(f"{sum(1 for f in fq if not str(f.get('finding_id', '')).endswith('-GRADE'))} financial-quality finding(s) per dd_review_finding "
                     f"as at {_asof(D)} are set out under Financial quality in the financial synopsis (section 15).")
    if items:
        blocks.append(BL(items))
    else:
        blocks.append(P(f"0 other observations recorded per dd_review_finding, dd_document and Borrower 360 as at {_asof(D)}."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 18 key strengths

def w_strengths(D: Deal) -> Out:
    s = [r for r in D.rows("dd_swot") if str(r.get("kind", "")).lower().startswith("s")]
    if s:
        return [BL([f"{one(r.get('text'))} (per dd_swot, as at {_asof(D)})." for r in s[:4]])], []
    out = []
    since = d(D.get("account_opened"))
    if since:
        out.append(f"Relationship with the bank since {since}, {_days(D.get('account_opened'), D.get('as_of')) // 365} years to {_asof(D)}.")
    fr = fin_rows(D)
    aud = sorted([x for x in fr if _actual(x)], key=lambda x: int(x.get("year") or 0))
    if len(aud) >= 2 and num(aud[-1].get("revenue")) and num(aud[-2].get("revenue")):
        out.append(_yoy(D, aud[-1]["revenue"], aud[-2]["revenue"], "Revenue", aud[-1].get("year")))
    g = [r for r in D.rows("dd_security") if num(r.get("guarantor_net_worth"))]
    if g:
        out.append(f"{g[0].get('item_type')} of {g[0].get('guarantor')} with net worth of {D.money(g[0].get('guarantor_net_worth'))} per statement of {d(g[0].get('nw_statement_date')) or 'a date not provided'}.")
    note = P(f"SWOT not available in Data Domains (dd_swot {D.status.get('dd_swot', 'missing')}) as at {_asof(D)}; the {len(out)} strength(s) below are read from the data.")
    if not out:
        return [P(f"Key strengths not available: SWOT not yet published to Data Domains (dd_swot {D.status.get('dd_swot', 'missing')}) as at {_asof(D)}.")], ["dd_swot"]
    return [note, BL(out)], ["dd_swot"]


# ------------------------------------------------------------------------------------------------ 19 recommendation (credit voice)

def recommendation_items(D: Deal) -> list[str]:
    items = []
    te, to, tp = totals(D)
    res = {r.get("view"): r for r in D.rows("dd_result")}
    rec = res.get("recommended")
    plan = D.one("dd_monitoring_plan")
    verdict = str((plan or {}).get("verdict") or "")
    for r in _tops(D):
        e, pr = num(r.get("existing")) or 0.0, num(r.get("proposed")) or 0.0
        verb = "Approve the new" if e == 0 else "Renew the" if pr == e else ("Approve the increase of the" if pr > e else "Approve the reduction of the")
        items.append(f"{verb} {r.get('name')} at {D.money(pr)}" + (f" (existing {D.money(e)})" if e and pr != e else "") + (f", valid to {d(D.get('review_date'))}." if D.get("review_date") else f", valid to the next review (as at {_asof(D)})."))
    for r in [r for r in _limits(D) if r.get("parent_limit_id") and num(r.get("existing")) and num(r.get("existing")) != num(r.get("proposed"))]:
        e, pr = num(r.get("existing")) or 0.0, num(r.get("proposed")) or 0.0
        items.append(f"{'Increase' if pr > e else 'Reduce'} the {r.get('name')} sub-limit from {D.money(e)} to {D.money(pr)} within its parent limit, as at {_asof(D)}.")
    ce, cp = num(D.get("group_cap_existing")), num(D.get("group_cap_proposed"))
    gt = num(D.get("group_exposure_total"))
    if ce is not None and cp is not None and cp != ce:
        items.append(f"Approve the group exposure cap of {D.money(cp)} (existing {D.money(ce)}; group exposure after this request {D.money(gt)}) as at {_asof(D)}.")
    if rec and rec.get("trace_note"):
        items.append(f"Structure as per CreditProbe's recommended alternative ({rec.get('trace_note')}), lifting lifetime RAROC to {num(rec.get('lifetime_raroc_pct')):.1f}% "
                     f"against a {num(rec.get('hurdle_pct')):.1f}% hurdle as at {_asof(D)}.")
    items.append(f"Security as listed in section 4: {len(D.rows('dd_security'))} items, all to be executed and perfected as set out in the conditions below ({_asof(D)}).")
    if plan:
        items.append(f"Monitoring tier {plan.get('tier')} ({verdict or 'verdict not provided'}): {str(plan.get('review_frequency') or 'review frequency not provided').lower()} review, "
                     f"named triggers {plan.get('thresholds') or 'not provided'}, set by {plan.get('set_by')} on {d(plan.get('set_on'))}.")
    return items


def additional_conditions(D: Deal) -> list[str]:
    out = []
    for r in D.rows("dd_security"):
        if r.get("perfection_status") == "pending":
            out.append(f"Prior to limit loading: {r.get('item_type')} for {D.money(first(r, 'value_sar_mn', 'value'))} to be perfected by {d(r.get('perfection_due')) or 'a date to be set'}; RM to confirm in writing.")
    for r in D.rows("dd_condition"):
        if r.get("category") == "cp" or (r.get("status") == "not complied"):
            text = str(r.get("text")).rstrip(".").replace(" prior to limit loading", "")
            out.append(f"{'Prior to limit loading' if r.get('category') == 'cp' else 'Undertaking'}: {text}"
                       + (f" (not complied under {r.get('committee_ref')}; to be met by {d(D.get('review_date')) or 'the next review'})" if r.get("status") == "not complied"
                          else f" (as per section 5, {_asof(D)})") + ".")
    for x in D.rows("dd_document"):
        if str(x.get("status")) in ("pending", "expired"):
            out.append(f"Prior to limit loading: {x.get('name')} ({x.get('status')} as at {_asof(D)}; {x.get('clause')}).")
    plan = D.one("dd_monitoring_plan")
    if plan and str(plan.get("tier")) == "High":
        out.append(f"Monitoring: {str(plan.get('review_frequency') or 'quarterly').lower()} review dually by the RM and the regional head from {d(plan.get('set_on'))}; "
                   f"breach of {plan.get('thresholds')} to be reported within 5 working days.")
    for r in D.rows("b360_insider_link"):
        out.append(f"Staff-related party: disclosure to Compliance of {r.get('person')}'s {pct(r.get('share_pct'))} holding in {r.get('entity')} before limit loading ({d(r.get('as_of')) or _asof(D)}).")
    return list(dict.fromkeys(out))  # R14 p: one line per condition (a document required for two entities is listed once)


def w_recommendation(D: Deal) -> Out:
    items = recommendation_items(D)
    ac = additional_conditions(D)
    te, to, tp = totals(D)
    blocks = [P(f"Credit division recommends, as at {_asof(D)}, approval of total limits of {D.money(tp)} subject to the {len(items)} decisions and {len(ac)} additional conditions below.")]
    blocks.append(NL(items))
    gt = num(D.get("group_exposure_total"))
    if gt is not None:
        blocks.append(P(f"Group exposure after approval: {D.money(gt)} total and {D.money(D.get('group_exposure_funded'))} funded as at {_asof(D)}."))
    blocks.append(H("Additional conditions"))
    blocks.append(NL(ac) if ac else P(f"No additional condition beyond the terms in section 5 as at {_asof(D)}."))
    gaps = [] if D.rows("dd_monitoring_plan") else ["dd_monitoring_plan"]
    if gaps:
        blocks.append(P(f"Monitoring tier not available: the stress verdict is not yet published to Data Domains as at {_asof(D)}."))
    return blocks, gaps


# ------------------------------------------------------------------------------------------------ 20 signature blocks

AUTHORITY = [(0.0, "Head of Credit"), (100.0, "Credit Committee (CC level 2)"), (250.0, "Credit Committee (CC level 1)"), (500.0, "Board Credit Committee")]


def approval_authority(D: Deal) -> str:
    try:  # R14 E (K18, N2): the one approval-authority engine, on the recommended structure (E's counter-offer)
        from backend.dealdesk.approval import approval_authority as _engine_doa
        return str(_engine_doa(D.pid, "recommended")["level"])
    except Exception:  # noqa: BLE001 - a deal the engines cannot read keeps the R12 fallbacks below
        pass
    if D.get("approval_authority"):
        return str(D.get("approval_authority"))
    res = {r.get("view"): r for r in D.rows("dd_result")}
    lvl = (res.get("recommended") or res.get("ask") or {}).get("approval_level")
    if lvl:
        return str(lvl)
    gt = num(D.get("group_exposure_total")) or totals(D)[2]
    return [a for t, a in AUTHORITY if gt >= t][-1]


def w_signatures(D: Deal) -> Out:
    return [SIGN([("Analyst / Senior Manager, Credit", ""), ("VP Credit", ""), ("Chief Credit Officer", "")]),
            BOX("CRO review / comments", 4),
            BOX(f"Credit committee approval / instructions · approval authority: {approval_authority(D)}", 5)], []


__all__ = ["w_header", "w_action", "w_facilities", "w_security", "w_terms", "w_group_exposure", "w_background", "w_relationship", "w_projects",
           "w_cbrbr", "w_bureau", "w_other_banks", "w_new_project", "w_financials", "w_synopsis", "w_geopolitical", "w_exceptions", "w_strengths",
           "w_recommendation", "w_signatures", "totals", "asks", "approval_authority", "fin_rows", "adjusted", "recommendation_items",
           "additional_conditions"]
