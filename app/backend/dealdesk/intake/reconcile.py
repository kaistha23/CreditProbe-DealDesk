"""R16 i: reconcile key figures across the customer's documents and the Bank's own data (deterministic).

Each test returns {test, topic, title, status, severity, a, b, c, gap_pct, unit_note, sentence, evidence}. Status:
agrees | differs | flag (a question for the RM) | info. Severity 0 info · 1 note · 2 query the RM · 3 key concern.
Sentences are in the credit voice: a fact, a number and a date, prior year in brackets, attribution explicit.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from backend.dealdesk.intake.checklist import BANK_NAME, fv, owners, same_name

VAT_RATE = 0.15


def mn(x: Any) -> float | None:
    return None if x is None else round(float(x) / 1e6, 2)


def _f(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{d}f}"


def _pct(a: float | None, b: float | None) -> float | None:
    if a in (None, 0) or b is None:
        return None
    return round((b - a) / abs(a) * 100, 1)


def _of(docs: list[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    return [d for d in docs if d.get("doc_type") == code]


def _ev(doc: dict[str, Any], *fields: str) -> list[dict[str, Any]]:
    return [{"doc_id": doc["doc_id"], "file": doc.get("file_name"), "field": f, "value": fv(doc, f)} for f in fields]


def _test(test: str, topic: str, title: str, status: str, severity: int, sentence: str, *, a=None, b=None, c=None,
          gap=None, unit="SAR mn", evidence=None) -> dict[str, Any]:
    return {"test": test, "topic": topic, "title": title, "status": status, "severity": severity, "a": a, "b": b, "c": c,
            "gap_pct": gap, "unit_note": unit, "sentence": sentence, "evidence": evidence or []}


def audited_by_year(docs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for d in _of(docs, "audited_fs"):
        y = str(fv(d, "fiscal_year") or "")[:4]
        if y.isdigit():
            out[int(y)] = d
    return out


def latest_inhouse(docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    xs = sorted(_of(docs, "inhouse_fs"), key=lambda d: str(fv(d, "period_to") or ""))
    return xs[-1] if xs else None


def _months_between(a: str, b: str) -> int:
    da, db = dt.date.fromisoformat(a[:10]), dt.date.fromisoformat(b[:10])
    return (db.year - da.year) * 12 + db.month - da.month + 1


# ------------------------------------------------------------------------------------------------ tests
def identity(docs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    cr = profile.get("cr_number") or ""
    odd = [d for d in docs if fv(d, "cr_number") and re.sub(r"\D", "", str(fv(d, "cr_number"))) != cr]
    n = sum(1 for d in docs if fv(d, "cr_number"))
    if not cr:
        return [_test("identity_cr", "identity", "Same company on every document", "flag", 2,
                      "No CR number could be read from the documents; the customer is identified by name only.", unit="")]
    if odd:
        names = ", ".join(f"{d['file_name']} (CR {fv(d, 'cr_number')})" for d in odd[:4])
        return [_test("identity_cr", "identity", "Same company on every document", "differs", 3,
                      f"{len(odd)} of {n} documents carry a different CR number than {cr}: {names}. Upon checking, these are not the "
                      "customer's documents or the CR was mis-printed; to be clarified before use.", a=float(n), b=float(len(odd)), unit="documents",
                      evidence=[e for d in odd for e in _ev(d, "cr_number", "customer_name")])]
    return [_test("identity_cr", "identity", "Same company on every document", "agrees", 0,
                  f"All {n} documents that print a CR number carry {cr} ({profile.get('customer_name') or 'the customer'}).",
                  a=float(n), unit="documents")]


def revenue(docs: list[dict[str, Any]], bank: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fy = audited_by_year(docs)
    ih = latest_inhouse(docs)
    years = sorted(fy)
    if not years:
        return [_test("revenue_sources", "revenue", "Revenue: audited accounts vs bank statements vs VAT", "flag", 2,
                      "No audited financial statements were read; revenue cannot be reconciled.")]
    y1 = years[-1]
    rev1 = fv(fy[y1], "revenue")
    rev0 = fv(fy[years[-2]], "revenue") if len(years) > 1 else None
    # LTM revenue proxy over the statement window: in-house YTD + the rest of the last audited year
    ltm, ltm_note = None, ""
    if ih and fv(ih, "revenue") and fv(ih, "period_to") and fv(ih, "period_from") and rev1:
        m = _months_between(str(fv(ih, "period_from")), str(fv(ih, "period_to")))
        if 0 < m < 12 and str(fv(ih, "period_to"))[:4] == str(y1 + 1):
            ltm = float(fv(ih, "revenue")) + float(rev1) * (12 - m) / 12
            ltm_note = f"in-house {m} months {y1 + 1} + {12 - m}/12 of FY{y1}"
    if ltm is None and rev1:
        ltm, ltm_note = float(rev1), f"FY{y1} audited"
    # VAT 12 months
    vat = None
    vdocs = _of(docs, "vat_returns")
    if vdocs:
        v = vdocs[0]
        vat = fv(v, "total_taxable_sales")
        if vat is None:
            rows = fv(v, "returns") or []
            s = sum(float(r.get("taxable_sales") or 0) for r in rows if isinstance(r, dict))
            vat = s or None
        zero = sum(float(r.get("zero_rated_sales") or 0) for r in (fv(v, "returns") or []) if isinstance(r, dict))
        if vat is not None and zero:
            vat = float(vat) + zero
    # statement credits (all accounts, all banks), net of VAT
    sdocs = _of(docs, "bank_statement")
    credits = sum(float(fv(d, "total_credits") or 0) for d in sdocs) or None
    credits_net = credits / (1 + VAT_RATE) if credits else None
    ev = _ev(fy[y1], "revenue") + (_ev(ih, "revenue", "period_from", "period_to") if ih else [])
    ev += [e for d in vdocs for e in _ev(d, "total_taxable_sales", "period_from", "period_to")]
    ev += [e for d in sdocs for e in _ev(d, "bank_name", "total_credits", "period_from", "period_to")]
    a, b, c = mn(ltm), mn(vat), mn(credits_net)
    parts = [f"Revenue for the last 12 months is SAR {_f(a)}m ({ltm_note})"]
    status, sev = "agrees", 0
    if b is not None:
        g = _pct(a, b)
        parts.append(f"VAT filings show standard- and zero-rated sales of SAR {_f(b)}m ({'+' if (g or 0) >= 0 else ''}{_f(g)}%)")
        if g is not None and abs(g) > 6:
            status, sev = "differs", 2
    elif vdocs:
        parts.append("VAT filings read but their 12-month total could not be read")
    else:
        parts.append("VAT filings not provided")
    if c is not None:
        ratio = (c / a) if a else None
        parts.append(f"bank-statement credits net of VAT are SAR {_f(c)}m, {_f(ratio * 100 if ratio else None, 0)}% of revenue "
                     f"({len(sdocs)} statement{'s' if len(sdocs) != 1 else ''})")
        if ratio is not None and not (0.85 <= ratio <= 1.10):
            status, sev = "differs", max(sev, 2 if ratio > 0.7 else 3)
    else:
        parts.append("bank statements not provided")
    s = "; ".join(parts) + "."
    if status == "differs":
        s += " The sources do not agree within the normal band (VAT ±6%, collections 85–110%); business to explain."
    out.append(_test("revenue_sources", "revenue", "Revenue: audited accounts vs VAT filings vs bank-statement credits", status, sev,
                     s, a=a, b=b, c=c, gap=_pct(a, c) if c is not None else _pct(a, b), evidence=ev))
    # growth: audited revenue vs credits at the Bank (existing customer, 24 months of conduct) or vs statements
    if rev0 and rev1:
        g_rev = _pct(float(rev0), float(rev1))
        cy = (bank or {}).get("credits_by_year") or {}
        c0, c1 = cy.get(years[-2]), cy.get(y1)
        if c0 and c1:
            g_cr = _pct(c0, c1)
            gap = (g_rev or 0) - (g_cr or 0)
            st, sv = ("differs", 3) if gap > 15 else (("flag", 2) if gap > 8 else ("agrees", 0))
            out.append(_test("revenue_growth_vs_credits", "revenue", "Revenue growth vs account credits at the Bank", st, sv,
                             f"Audited revenue rose {_f(g_rev)}% to SAR {_f(mn(rev1))}m in FY{y1} (PY SAR {_f(mn(rev0))}m), yet credits to the "
                             f"customer's accounts with the Bank grew only {_f(g_cr)}% (SAR {_f(c1)}m vs SAR {_f(c0)}m)"
                             + (", which indicates sales booked but not collected through the Bank; receivables and related-party sales to be checked."
                                if st != "agrees" else "."),
                             a=g_rev, b=g_cr, gap=round(gap, 1), unit="% growth",
                             evidence=_ev(fy[y1], "revenue") + _ev(fy[years[-2]], "revenue") + [{"relation": "dd_account_conduct", "field": "credit_turnover_mn",
                                                                                                   "years": [years[-2], y1]}]))
    return out


def fs_arithmetic(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in _of(docs, "audited_fs") + _of(docs, "inhouse_fs"):
        ta, tl, te = fv(d, "total_assets"), fv(d, "total_liabilities"), fv(d, "total_equity")
        if ta and tl is not None and te is not None:
            gap = float(ta) - float(tl) - float(te)
            label = f"FY{str(fv(d, 'fiscal_year'))[:4]}" if d["doc_type"] == "audited_fs" else f"in-house to {fv(d, 'period_to')}"
            ok = abs(gap) <= max(1000.0, abs(float(ta)) * 0.001)
            out.append(_test(f"balance_{d['doc_id']}", "arithmetic", f"Balance sheet balances ({label})", "agrees" if ok else "differs", 0 if ok else 2,
                             f"{label}: total assets SAR {_f(mn(ta))}m = liabilities SAR {_f(mn(tl))}m + equity SAR {_f(mn(te))}m"
                             + ("." if ok else f"; a gap of SAR {_f(mn(gap), 2)}m is not explained (possible reading error or mis-cast statement)."),
                             a=mn(ta), b=mn(float(tl) + float(te)), gap=_pct(float(ta), float(tl) + float(te)),
                             evidence=_ev(d, "total_assets", "total_liabilities", "total_equity")))
    for d in _of(docs, "bank_statement"):
        o, cr, db, cl = (fv(d, k) for k in ("opening_balance", "total_credits", "total_debits", "closing_balance"))
        if None not in (o, cr, db, cl):
            gap = float(o) + float(cr) - float(db) - float(cl)
            ok = abs(gap) <= 1000
            if not ok:
                out.append(_test(f"statement_{d['doc_id']}", "arithmetic", f"Statement adds up ({fv(d, 'bank_name')})", "differs", 2,
                                 f"{fv(d, 'bank_name')} statement: opening SAR {_f(mn(o), 2)}m + credits {_f(mn(cr), 2)}m − debits {_f(mn(db), 2)}m "
                                 f"≠ closing {_f(mn(cl), 2)}m (gap SAR {_f(mn(gap), 2)}m).", a=mn(o), b=mn(cl),
                                 evidence=_ev(d, "opening_balance", "total_credits", "total_debits", "closing_balance")))
    return out


def owner_sets(docs: list[dict[str, Any]], bank: dict[str, Any] | None) -> list[dict[str, Any]]:
    allown = owners(docs)
    own = [o for o in allown if "AoA" in o["sources"] or "CR" in o["sources"]] or allown
    ubos = [o for o in allown if o not in own]
    if not own:
        return [_test("owners", "owners", "Owners: AoA vs CR vs bureau", "flag", 2,
                      "Shareholders could not be read (no AoA or CR in the upload); ownership not verified.", unit="")]
    aoa = [o for o in own if "AoA" in o["sources"]]
    cr = [o for o in own if "CR" in o["sources"]]
    persons = [o for o in own + ubos if o["person"]]
    bureau = [str(fv(d, "full_name") or "") for d in _of(docs, "simah_consumer")]
    ids = [str(fv(d, "full_name") or "") for d in _of(docs, "national_id")]
    issues: list[str] = []
    only_aoa = [o["name"] for o in own if "AoA" in o["sources"] and "CR" not in o["sources"] and cr]
    only_cr = [o["name"] for o in own if "CR" in o["sources"] and "AoA" not in o["sources"] and aoa]
    if only_aoa:
        issues.append(f"in the AoA but not on the CR: {', '.join(only_aoa)}")
    if only_cr:
        issues.append(f"on the CR but not in the AoA: {', '.join(only_cr)}")
    # percentages that differ between AoA and CR
    pct_diff = []
    for o in own:
        if "AoA" in o["sources"] and "CR" in o["sources"]:
            pa = next((r.get("pct") for d in _of(docs, "articles_of_association") for r in (fv(d, "shareholders") or [])
                       if isinstance(r, dict) and same_name(str(r.get("name") or ""), o["name"])), None)
            pc = next((r.get("pct") for d in _of(docs, "commercial_registration") for r in (fv(d, "owners") or [])
                       if isinstance(r, dict) and same_name(str(r.get("name") or ""), o["name"])), None)
            if pa is not None and pc is not None and abs(float(pa) - float(pc)) > 0.5:
                pct_diff.append(f"{o['name']} {pa}% (AoA) vs {pc}% (CR)")
    if pct_diff:
        issues.append("shares differ: " + "; ".join(pct_diff))
    no_bureau = [o["name"] for o in persons if not any(same_name(o["name"], b) for b in bureau)]
    no_id = [o["name"] for o in persons if not any(same_name(o["name"], b) for b in ids)]
    bank_holders = [str(h) for h in (bank or {}).get("shareholders") or []]
    not_at_bank = [o["name"] for o in own if bank_holders and not any(same_name(o["name"], h) for h in bank_holders)]
    if not_at_bank:
        issues.append(f"not in the Bank's shareholder records: {', '.join(not_at_bank)} (ownership change not notified?)")
    lst = ", ".join(f"{o['name']} {o['pct']}%" if o.get("pct") is not None else o["name"] for o in own)
    s = f"Owners per the documents: {lst}."
    if ubos:
        s += " Ultimate owners per the AML form: " + ", ".join(f"{o['name']} {o['pct']}%" if o.get("pct") is not None else o["name"] for o in ubos) + "."
    if no_bureau:
        s += f" SIMAH consumer report not provided for {', '.join(no_bureau)}."
    if no_id:
        s += f" ID not provided for {', '.join(no_id)}."
    if issues:
        s += " We note: " + "; ".join(issues) + "."
        return [_test("owners", "owners", "Owners: AoA vs CR vs bureau vs the Bank's records", "differs", 2, s, a=float(len(own)), unit="owners",
                      evidence=[e for d in _of(docs, "articles_of_association") + _of(docs, "commercial_registration") for e in _ev(d, "shareholders" if d["doc_type"] == "articles_of_association" else "owners")])]
    return [_test("owners", "owners", "Owners: AoA vs CR vs bureau vs the Bank's records", "flag" if (no_bureau or no_id) else "agrees",
                  1 if (no_bureau or no_id) else 0, s + (" AoA and CR agree" + (" with the Bank's records." if bank_holders else ".")),
                  a=float(len(own)), unit="owners")]


def related_party(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    fy = audited_by_year(docs)
    if fy:
        y = max(fy)
        d = fy[y]
        rps, rev = fv(d, "related_party_sales"), fv(d, "revenue")
        if rps and rev:
            share = float(rps) / float(rev) * 100
            prev = fy.get(y - 1)
            pshare = (float(fv(prev, "related_party_sales") or 0) / float(fv(prev, "revenue")) * 100) if prev and fv(prev, "revenue") else None
            st, sv = ("flag", 3) if share >= 20 else (("flag", 2) if share >= 10 else ("info", 0))
            out.append(_test("related_party_sales", "related_party", "Sales to related parties", st, sv,
                             f"Sales to related parties were SAR {_f(mn(rps))}m in FY{y}, {_f(share)}% of revenue"
                             + (f" (PY {_f(pshare)}%)" if pshare is not None else "") + " as per the audited note"
                             + ("; growth that depends on a related buyer is not arm's-length evidence of demand." if share >= 20 else "."),
                             a=mn(rps), b=round(share, 1), unit="SAR mn / % of revenue", evidence=_ev(d, "related_party_sales", "revenue")))
        dfr, ta = fv(d, "due_from_related"), fv(d, "total_assets")
        te = fv(d, "total_equity")
        if dfr and te:
            adj = float(te) - float(dfr)
            out.append(_test("adjusted_net_worth", "related_party", "Net worth adjusted for related-party balances", "info", 1 if float(dfr) / float(te) > 0.1 else 0,
                             f"If due from related parties (SAR {_f(mn(dfr))}m) is netted off, adjusted net worth is SAR {_f(mn(adj))}m "
                             f"(reported SAR {_f(mn(te))}m, −{_f(float(dfr) / float(te) * 100)}%).", a=mn(te), b=mn(adj),
                             evidence=_ev(d, "total_equity", "due_from_related")))
    return out


def concentration(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    # a buyer listed as a third party whose sales equal the related-party sales in the audited note
    fy = audited_by_year(docs)
    if fy:
        y = max(fy)
        rps = fv(fy[y], "related_party_sales")
        for d in _of(docs, "top_customers_suppliers"):
            for r in (fv(d, "customers") or []):
                if not isinstance(r, dict) or not rps or not r.get("sales"):
                    continue
                if abs(float(r["sales"]) - float(rps)) <= 0.02 * float(rps) and not re.search(r"(?i)related|sister|group|affiliate", str(r.get("relationship") or "")):
                    out.append(_test("related_buyer_as_third_party", "related_party", "A related buyer presented as a third party", "differs", 3,
                                     f"{r.get('name')} is listed as \"{r.get('relationship') or 'third party'}\" with sales of SAR {_f(mn(r['sales']))}m "
                                     f"({_f(r.get('share_pct'))}% of sales), the same amount as the sales to related parties in the FY{y} audited note "
                                     f"(SAR {_f(mn(rps))}m); the customer list does not disclose the relationship.",
                                     a=mn(r["sales"]), b=mn(rps), evidence=_ev(d, "customers") + _ev(fy[y], "related_party_sales")))
    for d in _of(docs, "top_customers_suppliers"):
        rows = [r for r in (fv(d, "customers") or []) if isinstance(r, dict) and r.get("share_pct") is not None
                and not re.match(r"(?i)\s*(other|others|remaining|various|local customers|all other)\b", str(r.get("name") or ""))
                and not re.search(r"\(\d+\)", str(r.get("name") or ""))]
        if rows:
            top = max(rows, key=lambda r: float(r["share_pct"]))
            sh = float(top["share_pct"])
            rel = [r for r in rows if re.search(r"(?i)related|sister|group|affiliate", str(r.get("relationship") or ""))]
            st, sv = ("flag", 3) if sh >= 40 else (("flag", 2) if sh >= 25 else ("info", 0))
            s = f"The largest customer, {top.get('name')}, is {_f(sh)}% of {fv(d, 'year') or 'the year'}'s sales"
            top2 = sorted((float(r["share_pct"]) for r in rows), reverse=True)[:2]
            if len(top2) == 2:
                s += f"; top 2 = {_f(sum(top2))}%"
            if rel:
                s += "; related or group buyers: " + ", ".join(f"{r.get('name')} {_f(float(r['share_pct']))}%" for r in rel)
            s += "." + (" Single-name dependence: loss of this customer would remove a large part of revenue." if sh >= 40 else "")
            out.append(_test("customer_concentration", "concentration", "Customer concentration", st, sv, s, a=sh, b=sum(top2), unit="% of sales",
                             evidence=_ev(d, "customers")))
    for d in _of(docs, "receivables_ageing"):
        tot = fv(d, "total")
        old = sum(float(fv(d, k) or 0) for k in ("bucket_181_365", "bucket_over_365"))
        if tot:
            sh = old / float(tot) * 100
            out.append(_test("receivables_age", "concentration", "Receivables older than 180 days", "flag" if sh >= 15 else "info", 2 if sh >= 15 else 0,
                             f"Receivables of SAR {_f(mn(tot))}m as of {fv(d, 'as_of')}; SAR {_f(mn(old))}m ({_f(sh)}%) older than 180 days.",
                             a=mn(tot), b=mn(old), gap=round(sh, 1), evidence=_ev(d, "total", "bucket_181_365", "bucket_over_365")))
            ih = latest_inhouse(docs)
            tr = fv(ih, "trade_receivables") if ih else None
            if tr:
                g = _pct(float(tr), float(tot))
                if g is not None and abs(g) > 5:
                    out.append(_test("receivables_vs_fs", "arithmetic", "Ageing total vs receivables in the accounts", "differs", 2,
                                     f"The ageing totals SAR {_f(mn(tot))}m but the in-house accounts to {fv(ih, 'period_to')} show trade receivables of "
                                     f"SAR {_f(mn(tr))}m ({'+' if g > 0 else ''}{_f(g)}%); not reconciled.", a=mn(tr), b=mn(tot), gap=g,
                                     evidence=_ev(d, "total") + _ev(ih, "trade_receivables")))
    return out


def bureau(docs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for d in _of(docs, "simah_company"):
        fac = [r for r in (fv(d, "facilities") or []) if isinstance(r, dict)]
        bad = [r for r in fac if re.search(r"(?i)restruct|resched|default|written|legal|classified|overdue", f"{r.get('status')} {r.get('remark')}")]
        tl, to, tod = fv(d, "total_limits"), fv(d, "total_outstanding"), fv(d, "total_overdue")
        s = (f"SIMAH company report of {fv(d, 'report_date') or 'n/a'}: {fv(d, 'lenders_count') or len({r.get('lender') for r in fac})} lenders, "
             f"limits SAR {_f(mn(tl))}m, outstanding SAR {_f(mn(to))}m, overdue SAR {_f(mn(tod))}m, score {fv(d, 'score') or 'n/a'}.")
        st, sv = "agrees", 0
        if bad:
            s += " Upon checking, the report shows " + "; ".join(
                f"{r.get('lender')} {r.get('product') or ''}: {r.get('status') or ''} {('(' + str(r.get('remark')) + ')') if r.get('remark') else ''}".replace("  ", " ")
                for r in bad[:4]) + "."
            st, sv = "flag", 3
            req = " ".join(" ".join(x.get("lines") or []) for x in docs if x.get("doc_type") in ("business_request", "facility_request_letter"))
            m = None
            for x in docs:
                if x.get("doc_type") not in ("business_request", "facility_request_letter"):
                    continue
                for ln in x.get("lines") or []:
                    m = re.search(r"(?i)[^.;:|]*\b(no|not|never|without)\b[^.;|]{0,60}(restructur|reschedul)[^.;|]*", ln)
                    if m:
                        break
                if m:
                    break
            if m:
                s += f" The facility request states \"{m.group(0).strip()[:140]}\", which the bureau contradicts."
            elif req and not re.search(r"(?i)restruct|resched", req):
                s += " This is not disclosed in the facility request."
        if tod and float(tod) > 0:
            st, sv = "flag", max(sv, 2)
        out.append(_test(f"bureau_company_{d['doc_id']}", "bureau", "Company credit bureau (SIMAH)", st, sv, s, a=mn(tl), b=mn(to), c=mn(tod),
                         evidence=_ev(d, "report_date", "total_limits", "total_outstanding", "total_overdue", "facilities")))
        # other-bank limits: bureau vs offer letters / facility statements
        for ob in _of(docs, "other_bank_statement") + _of(docs, "other_bank_offer_letter"):
            bn = str(fv(ob, "bank_name") or "")
            rows = [r for r in fac if same_name(str(r.get("lender") or ""), bn)]
            if not rows:
                continue
            lim_b = sum(float(r.get("limit") or 0) for r in rows)
            lim_d = fv(ob, "total_limits")
            if lim_d:
                g = _pct(float(lim_d), lim_b)
                if g is not None and abs(g) > 2:
                    out.append(_test(f"otherbank_{ob['doc_id']}", "bureau", f"{bn}: bureau vs the bank's own letter", "differs", 2,
                                     f"{bn} limits are SAR {_f(mn(lim_d))}m per the {BYLABEL.get(ob['doc_type'], 'letter')} but SAR {_f(mn(lim_b))}m on SIMAH "
                                     f"({'+' if g > 0 else ''}{_f(g)}%); not clarified.", a=mn(lim_d), b=mn(lim_b), gap=g,
                                     evidence=_ev(ob, "bank_name", "total_limits")))
    for d in _of(docs, "simah_consumer"):
        od = fv(d, "total_overdue")
        worst = str(fv(d, "worst_status_24m") or "")
        worst_q = re.sub(r"(?i)\bno (delinquency|default|arrears)\b|\bnot past due\b", "", worst)
        fac = [r for r in (fv(d, "facilities") or []) if isinstance(r, dict)]
        bad = [r for r in fac if (r.get("overdue") or 0) and float(r.get("overdue") or 0) > 0
               or re.search(r"(?i)delinq|default|written|dpd|late|restruct", f"{r.get('status')} {r.get('remark')}")]
        clean = (not od or float(od) == 0) and not bad and not re.search(r"(?i)\d+\s*dpd|delinq|default|past due|substandard|doubtful|classif|restruct|written|\b(30|60|90)\b", worst_q)
        gbad = [r for r in (fv(d, "guarantees") or []) if isinstance(r, dict) and re.search(r"(?i)restruct|resched|substandard|doubtful|default|classif|past due", str(r.get("status") or ""))]
        if gbad:
            clean = False
        s = f"SIMAH consumer report of {fv(d, 'full_name')} ({fv(d, 'report_date') or 'n/a'}): outstanding SAR {_f(mn(fv(d, 'total_outstanding')), 2)}m, overdue SAR {_f(mn(od), 2)}m, worst status in 24 months {worst or 'n/a'}, score {fv(d, 'score') or 'n/a'}."
        if bad:
            s += " " + "; ".join(f"{r.get('lender')} {r.get('product') or ''} {r.get('status') or ''} {('(' + str(r.get('remark')) + ')') if r.get('remark') else ''}".strip() for r in bad[:3]) + "."
        gs = [r for r in (fv(d, "guarantees") or []) if isinstance(r, dict)]
        if gs:
            s += f" Guarantees given: {len(gs)} (SAR {_f(mn(sum(float(r.get('amount') or 0) for r in gs)))}m)."
        for r in gbad:
            s += f" The guaranteed facility of {r.get('beneficiary')} at {r.get('lender')} (SAR {_f(mn(r.get('amount')))}m) is {str(r.get('status')).lower()}."
        out.append(_test(f"bureau_person_{d['doc_id']}", "bureau", f"Personal bureau: {fv(d, 'full_name')}", "agrees" if clean else "flag",
                         0 if clean else 2, s, a=mn(fv(d, "total_outstanding")), b=mn(od), evidence=_ev(d, "total_overdue", "worst_status_24m", "facilities")))
    return out


BYLABEL = {"other_bank_statement": "facility statement", "other_bank_offer_letter": "offer letter"}


def saudisation(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in _of(docs, "nitaqat_certificate"):
        r, t = fv(d, "saudisation_pct"), fv(d, "band_threshold_pct")
        if r is not None and t is not None:
            head = float(r) - float(t)
            st, sv = ("flag", 2) if head < 2 else ("agrees", 0)
            s = (f"Nitaqat band {fv(d, 'nitaqat_band') or 'n/a'}: Saudisation {_f(float(r))}% against a minimum of {_f(float(t))}% for the band "
                 f"({fv(d, 'saudi_staff') or '?'} of {fv(d, 'total_staff') or '?'} staff); headroom {_f(head)} points")
            if st == "flag":
                staff = fv(d, "total_staff")
                need = None
                if staff:
                    need = max(0, int(round(float(staff) * (float(t) - float(r)) / 100 + 0.4999)))
                s += "; at the edge of the band: losing " + ("one Saudi employee" if head < 1 else "a few Saudi employees") + \
                     " or hiring non-Saudis would drop the band (visa and government-contract restrictions)."
            else:
                s += "."
            out.append(_test("nitaqat_headroom", "saudisation", "Nitaqat band headroom", st, sv, s, a=float(r), b=float(t), gap=round(head, 2),
                             unit="% Saudisation", evidence=_ev(d, "nitaqat_band", "saudisation_pct", "band_threshold_pct", "total_staff", "saudi_staff")))
    return out


def projects(docs: list[dict[str, Any]], as_of: dt.date) -> list[dict[str, Any]]:
    out = []
    certs = _of(docs, "payment_certificate")
    if certs:
        late = []
        for c in certs:
            due = fv(c, "due_date")
            if due and dt.date.fromisoformat(str(due)) < as_of:
                late.append(c)
        # unpaid if the statements show no credit of the net amount after the due date (approximate: any credit within 1%)
        paid_ids = set()
        txn = [r for d in _of(docs, "bank_statement") for r in (fv(d, "transactions") or []) if isinstance(r, dict)]
        for c in late:
            net = fv(c, "net_payable")
            if net and any(abs(float(r.get("credit") or 0) - float(net)) <= max(1000, 0.01 * float(net)) for r in txn):
                paid_ids.add(c["doc_id"])
        unpaid = [c for c in late if c["doc_id"] not in paid_ids]
        if unpaid:
            days = [(as_of - dt.date.fromisoformat(str(fv(c, "due_date")))).days for c in unpaid]
            amt = sum(float(fv(c, "net_payable") or 0) for c in unpaid)
            out.append(_test("payment_certificates_late", "projects", "Payment certificates past due", "flag", 3,
                             f"{len(unpaid)} certified payment certificate{'s' if len(unpaid) != 1 else ''} worth SAR {_f(mn(amt))}m "
                             f"{'are' if len(unpaid) != 1 else 'is'} past due by {min(days)}–{max(days)} days (oldest due {min(str(fv(c, 'due_date')) for c in unpaid)}), "
                             "with no matching receipt in the bank statements provided; employer payment delays to be explained.",
                             a=mn(amt), b=float(max(days)), unit="SAR mn / days", evidence=[e for c in unpaid for e in _ev(c, "certificate_number", "net_payable", "due_date")]))
        lastc = sorted(certs, key=lambda c: str(fv(c, "certified_on") or ""))[-1]
        cr, gw = fv(lastc, "cumulative_retention"), fv(lastc, "gross_work_done")
        if cr and gw:
            out.append(_test("retention_build_up", "projects", "Retention held by the employer", "info", 1,
                             f"Cumulative retention on {fv(lastc, 'project_id')} is SAR {_f(mn(cr))}m on work done of SAR {_f(mn(gw))}m "
                             f"({_f(float(cr) / float(gw) * 100)}%) as of certificate {fv(lastc, 'certificate_number')} ({fv(lastc, 'certified_on')}); "
                             "released only at completion and handover.", a=mn(cr), b=mn(gw), evidence=_ev(lastc, "cumulative_retention", "gross_work_done")))
    for d in _of(docs, "project_list"):
        rows = [r for r in (fv(d, "projects") or []) if isinstance(r, dict)]
        if rows:
            billed = sum(float(r.get("billed") or 0) for r in rows)
            recv = sum(float(r.get("received") or 0) for r in rows)
            ret = sum(float(r.get("retention_held") or 0) for r in rows)
            cv = sum(float(r.get("contract_value") or 0) for r in rows)
            done = sum(float(r.get("contract_value") or 0) * float(r.get("work_done_pct") or 0) / 100 for r in rows)
            behind = [r for r in rows if re.search(r"(?i)delay|behind|eot|extension|slow", str(r.get("status") or ""))]
            s = (f"{len(rows)} projects, contract value SAR {_f(mn(cv))}m, backlog SAR {_f(mn(cv - done))}m; billed SAR {_f(mn(billed))}m, "
                 f"received SAR {_f(mn(recv))}m ({_f(recv / billed * 100 if billed else None, 0)}% collected), retention held SAR {_f(mn(ret))}m.")
            if behind:
                s += " Behind programme: " + "; ".join(f"{r.get('project')} ({r.get('status')})" for r in behind[:3]) + "."
            out.append(_test("project_portfolio", "projects", "Projects: billed vs received", "flag" if behind or (billed and recv / billed < 0.8) else "info",
                             2 if behind or (billed and recv / billed < 0.8) else 0, s, a=mn(billed), b=mn(recv), c=mn(ret), evidence=_ev(d, "projects")))
    for d in _of(docs, "project_contract"):
        comp = fv(d, "completion_date")
        if comp and dt.date.fromisoformat(str(comp)) < as_of:
            out.append(_test(f"contract_overrun_{d['doc_id']}", "projects", f"Contract completion date passed ({fv(d, 'project_id')})", "flag", 2,
                             f"{fv(d, 'project_id')}: contractual completion {comp} has passed; no formal extension of time was provided "
                             "(delay penalties and LG extension exposure).", evidence=_ev(d, "project_id", "completion_date")))
    return out


def guarantor_worth(docs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    name = profile.get("customer_name") or ""
    short = " ".join(re.findall(r"[A-Za-z]+", name)[:3])
    for d in _of(docs, "personal_net_worth"):
        nw = fv(d, "net_worth")
        assets = [r for r in (fv(d, "assets") or []) if isinstance(r, dict)]
        tot = sum(float(r.get("value") or 0) for r in assets) or fv(d, "total_assets")
        own_shares = [r for r in assets if re.search(r"(?i)share|equity|stake", f"{r.get('asset')} {r.get('description')}")
                      and (same_name(f"{r.get('asset')} {r.get('description')}", name) or (short and norm_in(short, f"{r.get('asset')} {r.get('description')}")))]
        val = sum(float(r.get("value") or 0) for r in own_shares)
        if nw:
            s = f"{fv(d, 'full_name')} declares net worth of SAR {_f(mn(nw))}m ({fv(d, 'statement_date') or 'undated'})"
            st, sv = "info", 0
            if val and tot:
                sh = val / float(tot) * 100
                s += f"; SAR {_f(mn(val))}m ({_f(sh)}% of assets) is the guarantor's shareholding in the borrower itself, which has no value if the borrower fails"
                if sh >= 40:
                    st, sv = "flag", 3
                    s += f"; net worth outside the borrower is SAR {_f(mn(float(nw) - val))}m"
            out.append(_test(f"guarantor_{d['doc_id']}", "guarantor", f"Guarantor support: {fv(d, 'full_name')}", st, sv, s + ".",
                             a=mn(nw), b=mn(val) if val else None, evidence=_ev(d, "net_worth", "assets")))
    return out


def norm_in(a: str, b: str) -> bool:
    from backend.dealdesk.intake.extract import norm
    return norm(a) in norm(b)


def conduct(bank: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not bank or not bank.get("existing"):
        return []
    out = []
    rc = bank.get("returned_cheques_12m")
    if rc:
        out.append(_test("returned_cheques", "conduct", "Returned cheques at the Bank (12 months)", "flag", 2,
                         f"{rc['n']} cheque{'s' if rc['n'] != 1 else ''} returned in the last 12 months (SAR {_f(rc['mn'], 2)}m) on the Bank's records.",
                         a=float(rc["n"]), b=rc["mn"], unit="n / SAR mn", evidence=[{"relation": "dd_returned_cheque"}]))
    cc = bank.get("connected_cheques")
    if cc:
        out.append(_test("connected_cheques", "conduct", "Returned cheques of connected parties", "flag", 2,
                         f"{cc['n']} cheque{'s' if cc['n'] != 1 else ''} of connected part{'ies' if len(cc['obligors']) > 1 else 'y'} {', '.join(cc['obligors'])} returned "
                         f"between {cc['dates'][0]} and {cc['dates'][-1]} (SAR {_f(cc['mn'], 2)}m) on the Bank's records.",
                         a=float(cc["n"]), b=cc["mn"], unit="n / SAR mn", evidence=[{"relation": "dd_returned_cheque"}]))
    for cp in bank.get("connected_weak") or []:
        out.append(_test(f"connected_{cp.get('id', '')}", "conduct", f"Connected party: {cp.get('name')}", "flag", 3,
                         f"{cp.get('name')} ({cp.get('relation') or 'connected party'}): {cp.get('status')}; contagion to the borrower to be assessed.",
                         evidence=[{"relation": cp.get("source") or "b360_entity", "id": cp.get("id")}]))
    return out


def run(docs: list[dict[str, Any]], profile: dict[str, Any], bank: dict[str, Any] | None, as_of: dt.date) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for fn in (lambda: identity(docs, profile), lambda: revenue(docs, bank), lambda: owner_sets(docs, bank), lambda: related_party(docs),
               lambda: concentration(docs), lambda: bureau(docs, profile), lambda: saudisation(docs), lambda: projects(docs, as_of),
               lambda: guarantor_worth(docs, profile), lambda: fs_arithmetic(docs), lambda: conduct(bank)):
        try:
            tests.extend(fn())
        except Exception as e:  # noqa: BLE001 - one broken test never hides the others
            tests.append(_test("error", "info", "A reconciliation could not run", "info", 0, f"Not computed: {type(e).__name__}: {e}"[:200], unit=""))
    tests.sort(key=lambda t: (-t["severity"], t["topic"]))
    return tests


__all__ = ["run", "BANK_NAME"]
