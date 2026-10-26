"""The credit division's response to the business request, in the bank form (PROPOSAL_ANATOMY §1-§3, the credit voice).

    paper = build(case)        # the bank-form paper of the deal (bankform.paper.write: every anatomy section from Data Domains,
                               # the request's limits, security and terms included) with credit's response laid over it:
                               #   the request as received and read (action requested)
                               #   documents reviewed, checklist and what the documents say read together (credit comments)
                               #   credit's observations in the credit voice ("We note that ...", "Upon checking ..."), each
                               #     with its evidence and source, merged into Exceptions and other observations
                               #   the Deal Desk flow on the request (CreditProbe analysis)
                               #   the numbered recommendation, conditions precedent "prior to limit loading", monitoring
    data, name = docx(paper) / pdf(paper)     # the bank's layout (render_bank)

Deterministic: every sentence is written by a rule; every figure names its document or relation.
"""
from __future__ import annotations

import copy
import math
import re
from datetime import date
from typing import Any

from backend.dealdesk.house_style.bankform import blocks as B

# the response's own sections sit in the bank form's parts (render_bank.PARTS) beside the anatomy sections: the request as
# received and the documents reviewed open their parts (right after the header), credit's comments close the "credit
# division comments" part (after the exceptions, before the strengths and the recommendation), the Deal Desk flow is an
# annex after the signatures
_FIRST = {"action": ("cr_request",), "comments": ("cr_documents",)}
_LAST = {"comments": ("cr_file",)}
_ANNEX = ("annex", "ANNEX", "Deal Desk flow on the request (CreditProbe)", ("cr_flow",))
_ORDER = ("cr_request", "cr_documents", "cr_file", "cr_flow")


def _register_parts() -> None:
    from backend.dealdesk.house_style.bankform import render_bank as RB
    out = []
    for key, title, sub, keys in RB.PARTS:
        if key == _ANNEX[0]:
            continue
        keys = tuple(k for k in keys if k not in _ORDER)
        keys = _FIRST.get(key, ()) + keys + _LAST.get(key, ())
        out.append((key, title, sub, keys))
    out.append(_ANNEX)
    RB.PARTS[:] = out


def _ordered(secs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sections in the order the parts print them (the in-app preview and the Markdown read the list)."""
    from backend.dealdesk.house_style.bankform import render_bank as RB
    rank: dict[str, int] = {}
    for _key, _t, _s, keys in RB.PARTS:
        for k in keys:
            rank.setdefault(k, len(rank))
    pos = {id(s): i for i, s in enumerate(secs)}
    head = [s for s in secs if s["key"] == "header"]
    rest = [s for s in secs if s["key"] != "header"]
    return head + sorted(rest, key=lambda s: (rank.get(s["key"], len(rank)), pos[id(s)]))


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def d(x: Any) -> str:
    try:
        v = date.fromisoformat(str(x)[:10])
        return f"{v.day} {MONTHS[v.month - 1]} {v.year}"
    except (TypeError, ValueError):
        return str(x or "")


def m(x: Any, dp: int = 1) -> str:
    try:
        return f"SAR {float(x):,.{dp}f}m"
    except (TypeError, ValueError):
        return "not provided"


def _today() -> str:
    from backend.dealdesk.credit_response.projects import as_of
    return d(as_of().isoformat())


# ------------------------------------------------------------------ what the documents and the bank's data say

QUERY_OF = {
    "payment_certificates_late": ("critical", "Status of financed projects",
                                  "Provide the employer's written confirmation of the payment dates of the certificates past due, the reason for the delay "
                                  "and any demand letter issued.",
                                  "Prior to limit loading: employer's written confirmation of the payment schedule of the certificates past due; "
                                  "RM and regional head to confirm receipt of the overdue certificates monthly."),
    "guarantor": ("critical", "Security and support",
                  "Provide the guarantor's assets outside the borrower (title deeds, statements) or propose additional security; the shareholding in the "
                  "borrower carries no value if the borrower fails.",
                  "Prior to limit loading: personal guarantee of the guarantor supported by a net-worth statement showing assets outside the borrower "
                  "(net of the borrower's shares) of not less than the new limit, or additional tangible security."),
    "retention_build_up": ("minor", "Status of financed projects", "Provide the retention release schedule per project and the defects-liability end dates.", ""),
    "receivables": ("major", "Financials", "Explain the receivables older than 180 days by customer and the expected collection dates; confirm any provision.", ""),
    "saudisation": ("minor", "Background", "Confirm the Saudisation plan that keeps the Nitaqat band (government contracts depend on it).", ""),
    "owners": ("major", "Background", "Provide the missing owner IDs and SIMAH consumer reports for every owner and guarantor.", ""),
    "revenue": ("major", "Financials", "Explain the gap between audited revenue, VAT filings and bank-statement credits for the same 12 months.", ""),
    "related": ("major", "Financials", "Provide the related-party balances by counterparty with their settlement dates.", ""),
    "concentration": ("major", "Financials", "Provide the contracts behind the top customers and the plan to reduce the concentration.", ""),
    "bureau": ("major", "Credit bureau", "Explain the bureau items (overdue, restructured or classified facilities) and provide the lenders' clearance letters.", ""),
    "contract_overrun": ("major", "Status of financed projects", "Provide the employer's written approval of the extension of time.", ""),
    "project_portfolio": ("major", "Status of financed projects", "Provide the collection plan for billed but unreceived amounts per project.", ""),
    "conduct": ("major", "Relationship with the bank", "Explain the account conduct items (past dues, returned cheques).", ""),
    "returned_cheques_connected": ("major", "Relationship with the bank",
                                   "Explain the returned cheques and past dues of the connected party, provide its regularisation plan and the repayment "
                                   "schedule of the amounts it owes the borrower.", ""),
    "connected_party": ("major", "Group exposure",
                        "Explain the connected party's account conduct and its balances with the borrower; provide its regularisation plan.", ""),
    "nitaqat_headroom": ("minor", "Background", "Confirm the Saudisation plan that keeps the Nitaqat band (government contracts depend on it).", ""),
    "adjusted_net_worth": ("major", "Financials", "Provide the settlement plan of the related-party balances netted from net worth, with dates.", ""),
}


def _short(t: str, n: int = 120) -> str:
    t = re.sub(r"\s+", " ", str(t)).strip().rstrip(".")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def _qkey(test: str) -> str:
    for k in QUERY_OF:
        if test.startswith(k) or k in test:
            return k
    return ""


def intake_facts(c: dict[str, Any]) -> dict[str, Any] | None:
    iid = (c["steps"].get("read") or {}).get("data", {}).get("intake_id")
    if not iid:
        return None
    try:
        from backend.dealdesk.intake import service as IS
        return IS.facts(iid)
    except Exception:  # noqa: BLE001 - intake not merged or the file was removed
        return None


def _texts(c: dict[str, Any]) -> list[tuple[str, str]]:
    """(file name, text) of the supporting documents this case read itself (Word and PDF; photos are read by the intake)."""
    from backend.dealdesk.credit_response import service as SV
    out = []
    for f in (c["steps"].get("read") or {}).get("data", {}).get("texts", []):
        p = SV._dir(c["case_id"]) / "texts" / f
        if p.exists():  # wrapped lines joined: a sentence (or a contract clause) reads whole
            out.append((f.rsplit(".", 1)[0], re.sub(r"[ \t]*\n[ \t]*(?=[a-z0-9(])", " ", p.read_text())))
    return out


def _eot(c: dict[str, Any]) -> list[dict[str, Any]]:
    """Extensions of time requested but not approved in writing, read from the documents' own words."""
    out = []
    for name, t in _texts(c):
        for mt in re.finditer(r"(?:[^.\n]|\.(?=\d))*extension of time(?:[^.\n]|\.(?=\d))*\.", t, re.I):
            s = mt.group(0).strip()
            if re.search(r"approved in writing|valid only", s, re.I):
                continue
            if re.search(r"request|submitted|awaited|pending|not (?:yet )?(?:approved|formalised)", s, re.I):
                out.append({"file": name, "sentence": s})
    seen, uniq = set(), []
    for e in out:
        k = re.sub(r"\W+", "", e["sentence"].lower())[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq[:3]


def _clause(c: dict[str, Any], pat: str) -> str:
    for _n, t in _texts(c):
        mt = re.search(rf"(?:[^.\n]|\.(?=\d))*{pat}(?:[^.\n]|\.(?=\d))*\.", t, re.I)
        if mt:
            return mt.group(0).strip()
    return ""


def observations(c: dict[str, Any]) -> list[dict[str, Any]]:
    """Credit's observations on the request, each {severity, section, title, text, query, cp, source}; deterministic order."""
    out: list[dict[str, Any]] = []
    asof = _today()
    f = intake_facts(c)
    if f:
        for t in f.get("reconciliation") or []:
            if t.get("severity", 0) < 1 or t.get("status") == "agrees" or (str(t.get("test") or "").startswith("owner") and "(100%" in t.get("sentence", "")):
                continue
            if str(t.get("test") or "").startswith("payment_certificates") and _certs(c):
                continue  # credit's own join of certificates and statements (VAT-inclusive receipts named by IPC) stands for this fact
            k = _qkey(t.get("test") or "")
            sev, sec, q, cp = QUERY_OF.get(k, ("major" if t["severity"] >= 2 else "minor", "Credit comments", f"Please explain {t['title'].rstrip('.')} ({_short(t.get('sentence') or '')}).", ""))
            if t.get("severity", 0) >= 3 and sev not in ("critical",):
                sev = "major"
            files = sorted({str(e.get("file")).replace("__", "_") for e in t.get("evidence") or [] if e.get("file")})
            sentence = t["sentence"]
            if str(t.get("test") or "").startswith("guarantor") and t.get("a") and t.get("b"):
                tot = (c["steps"]["read"]["data"]["request"].get("totals") or {}).get("proposed")
                outside = float(t["a"]) - float(t["b"])
                if tot:
                    sentence = sentence.rstrip(".") + f", {_f(outside / float(tot) * 100, 0)}% of the SAR {_f(tot)}m of facilities proposed."
            out.append({"severity": sev, "section": sec, "title": t["title"], "text": sentence, "query": q, "cp": cp,
                        "source": ("uploaded: " + ", ".join(files[:4])) if files else "customer file (intake reconciliation)", "test": t.get("test")})
        miss = [x for x in f.get("missing") or []]
        if miss:
            names = [str(x.get("label") or x.get("doc_label") or x.get("requirement") or x.get("doc_type")) + (f" ({x['subject']})" if x.get("subject") else "") for x in miss]
            out.append({"severity": "major", "section": "Documents", "title": f"{len(miss)} required documents not provided",
                        "text": f"{len(miss)} of {f.get('counts', {}).get('required', '–')} required documents are not provided as at {asof}: " + "; ".join(names[:10]) + ".",
                        "query": "Provide: " + "; ".join(names[:10]) + ".", "cp": "Prior to limit loading: the documents listed as not provided, "
                        "each current on the date of limit loading.", "source": "customer file checklist (dd_intake)"})
        exp = [x for x in f.get("checklist") or [] if str(x.get("status")) == "expired"]
        if exp:
            out.append({"severity": "major", "section": "Documents", "title": f"{len(exp)} documents expired",
                        "text": f"{len(exp)} documents are expired as at {asof}: " + "; ".join(str(x.get("label") or x.get("doc_label")) for x in exp[:8]) + ".",
                        "query": "Provide current copies of the expired documents.", "cp": "", "source": "customer file checklist (dd_intake)"})
    out += _contractor_observations(c)
    eot = _eot(c)
    if eot:
        clause = _clause(c, r"extensions? of time (?:are|is) valid only")
        txt = f"Upon checking, as per {eot[0]['file'].replace('__', '_')}: {eot[0]['sentence']}"
        if clause:
            txt += f" The contract provides: {clause}"
        txt += f" No written approval of the employer is on file as at {asof}; __the extension of time is not formalised__."
        out.append({"severity": "critical", "section": "Status of financed projects", "title": "Extension of time not formalised", "text": txt,
                    "query": "Provide the employer's written approval of the extension of time; until then delay damages and LG extension exposure apply.",
                    "cp": "", "source": "uploaded: " + ", ".join(sorted({e['file'].replace('__', '_') for e in eot}))})
    out += _bank_observations(c)
    out += _flow_observations(c)
    rank = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    for o in out:
        o["source"] = str(o.get("source") or "").replace("__", "_")
        if o.get("cp") and not re.search(r"\d", re.sub(r"prior to limit loading", "", o["cp"], flags=re.I)):
            o["cp"] = o["cp"].rstrip(".") + f" (not provided as at {_today()})."
    return sorted(out, key=lambda o: rank.get(o["severity"], 4))


def _docs(c: dict[str, Any]) -> list[dict[str, Any]]:
    return [x for x in (c["steps"].get("read") or {}).get("data", {}).get("documents", []) if not x.get("duplicate")]


def _certs(c: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.dealdesk.credit_response import projects as PJ
    return PJ.certificates(_docs(c))


def _f(x: Any, dp: int = 1) -> str:
    try:
        return f"{float(x):,.{dp}f}"
    except (TypeError, ValueError):
        return "–"


def _latest(c: dict[str, Any], code: str) -> dict[str, Any]:
    xs = [x for x in _docs(c) if x.get("doc_type") == code]
    xs.sort(key=lambda x: str(x["fields"].get("fiscal_year") or x["fields"].get("period_to") or x["fields"].get("statement_date") or ""))
    return xs[-1]["fields"] if xs else {}


def _contractor_observations(c: dict[str, Any]) -> list[dict[str, Any]]:
    """Credit's own joins for a contractor: certificates against the statements, retention, backlog on one employer,
    delay damages against net worth. Every figure names its documents."""
    out: list[dict[str, Any]] = []
    cs = _certs(c)
    req = c["steps"]["read"]["data"]["request"]
    if cs:
        aged = d(cs[0]["aged_to"])
        late_paid = [x for x in cs if x["status"] == "paid" and (x["days_late"] or 0) > 0]
        overdue = [x for x in cs if x["status"] == "overdue"]
        unpaid = [x for x in cs if x["status"] != "paid"]
        parts = []
        if late_paid:
            lo, hi = min(x["days_late"] for x in late_paid), max(x["days_late"] for x in late_paid)
            parts.append(f"{', '.join(x['certificate_number'] for x in late_paid)} paid {lo if lo == hi else f'{lo}–{hi}'} days after "
                         f"the due date (receipt of {d(late_paid[-1]['paid_on'])} incl. VAT, as per the account statement)")
        if overdue:
            amt = sum(x["net_payable_mn"] or 0 for x in overdue)
            parts.append(f"{overdue[0]['certificate_number']} to {overdue[-1]['certificate_number']} ({m(amt)} net) unpaid and past due by up to "
                         f"{max(x['days_late'] for x in overdue)} days at {aged}, the last statement date")
        if unpaid:
            parts.append(f"{len(unpaid)} certificates ({m(sum(x['net_payable_mn'] or 0 for x in unpaid))} net) unpaid in total")
        claim = re.search(r"[^.]*(?:payments are assured|receivables (?:are )?current|paid on time)[^.]*\.", " ".join(req["sections"].get("projects", []) + req["sections"].get("justification", [])), re.I)
        txt = (f"Upon checking the {len(cs)} payment certificates against the account statements: " + "; ".join(parts) + "."
               + (f" __This contradicts the request (as per business: \"{claim.group(0).strip()}\")__." if claim else ""))
        if overdue:
            out.append({"severity": "critical", "section": "Status of financed projects", "title": "Payment certificates paid late and overdue", "text": txt,
                        "query": f"Explain the employer's payment delays ({len(overdue)} certificates past due at {aged}) and provide the employer's confirmation of the payment dates.",
                        "cp": f"Prior to limit loading: the employer's written confirmation of the payment schedule of the {len(overdue)} certificates past due at {aged}; "
                              "new DMCCM drawings only while no certificate is more than 60 days past due.",
                        "source": "uploaded: " + ", ".join(sorted({x['source'].replace('__', '_') for x in cs})[:3]) + " and the account statements", "test": "certificates"})
    # retention build-up from the audited and in-house statements
    fs = sorted([x for x in _docs(c) if x.get("doc_type") in ("audited_fs", "inhouse_fs")],
                key=lambda x: str(x["fields"].get("fiscal_year") or x["fields"].get("period_to") or ""))
    ret = [(str(x["fields"].get("fiscal_year") or x["fields"].get("period_to") or "")[:10], x["fields"].get("retention_receivables"), x["fields"].get("current_assets"), x["doc_type"])
           for x in fs if x["fields"].get("retention_receivables")]
    plist_ret = sum((r.get("retention_mn") or 0) for r in req.get("projects") or [])
    if len(ret) >= 2:
        last = ret[-1]
        share = (float(last[1]) / float(last[2]) * 100) if last[2] else None
        seq = " → ".join(f"{'FY' + r[0][:4] if r[3] == 'audited_fs' else '9M' + r[0][:4]} SAR {_f(float(r[1]) / 1e6)}m" for r in ret)
        out.append({"severity": "major", "section": "Financial synopsis", "title": "Retention receivables building up",
                    "text": f"We note that retention receivables rose {seq} (PY SAR {_f(float(ret[-2][1]) / 1e6)}m)"
                            + (f", {_f(share)}% of current assets at {d(last[0])}" if share else "") + "; retention is released only at taking-over and at the end of "
                            "the defects-liability period (as per the contracts).",
                    "query": "Provide the retention release schedule per project with the taking-over and defects-liability dates.", "cp": "",
                    "source": "uploaded audited and in-house financial statements", "test": "retention"})
    # Package C and the backlog on one employer
    prj = req.get("projects") or []
    act = req["action"].get("text") or ""
    newv = re.search(r"contract\s*value\s*(?:of\s*)?SAR\s*([\d,.]+)\s*m", act, re.I)
    emp = re.search(r"awarded\s*by\s*([A-Z][^()]{3,80}?)\s*\(([A-Z]{2,8})\)", act)
    if prj and newv and emp:
        rem = sum((r["value_mn"] or 0) * (1 - (r["done_pct"] or 0) / 100.0) for r in prj)
        same = sum((r["value_mn"] or 0) * (1 - (r["done_pct"] or 0) / 100.0) for r in prj if emp.group(2) in (r["employer"] or "") or emp.group(1)[:12] in (r["employer"] or ""))
        cv = float(newv.group(1).replace(",", ""))
        tot = rem + cv
        sh = (same + cv) / tot * 100 if tot else 0
        if sh >= 50:
            out.append({"severity": "major", "section": "New project details", "title": f"Backlog concentrated on {emp.group(2)}",
                        "text": f"We note that with the new award of SAR {_f(cv)}m the work in hand of SAR {_f(tot)}m is {_f(sh)}% on {emp.group(1).strip()} ({emp.group(2)}) "
                                f"as at {_today()}, the same employer whose certificates are paid late (as per the request and the project schedule).",
                        "query": f"Explain how the new project's cash flow is funded while {emp.group(2)} pays late; provide the new project's cash-flow forecast.",
                        "cp": f"Prior to limit loading: the signed contract of the new project and the employer's acknowledgement of the assignment of its proceeds "
                              f"(not provided as at {_today()}).", "source": "business request (sections 1 and 8)", "test": "concentration_employer"})
    # delay damages against net worth when the extension of time is not approved
    ct = next((x["fields"] for x in _docs(c) if x.get("doc_type") == "project_contract"), {})
    clause = _clause(c, r"delay damages")
    capm = re.search(r"capped at\s*(\d+(?:\.\d+)?)\s*%", clause or "", re.I)
    eq = _latest(c, "inhouse_fs").get("total_equity") or _latest(c, "audited_fs").get("total_equity")
    if ct.get("contract_value") and capm and _eot(c):
        dmg = float(ct["contract_value"]) * float(capm.group(1)) / 100.0 / 1e6
        out.append({"severity": "critical", "section": "Status of financed projects", "title": "Delay damages exposure",
                    "text": f"Upon checking the contract of {ct.get('project_id')}, delay damages are capped at {capm.group(1)}% of SAR {_f(float(ct['contract_value']) / 1e6)}m, "
                            f"i.e. up to SAR {_f(dmg)}m" + (f" ({_f(dmg / (float(eq) / 1e6) * 100, 0)}% of net worth of SAR {_f(float(eq) / 1e6)}m)" if eq else "")
                            + f" while the extension of time is not approved in writing as at {_today()}.",
                    "query": "Provide the employer's written approval of the extension of time or an undertaking that no delay damages will be levied.",
                    "cp": f"Prior to limit loading: the employer's written approval of the extension of time, or its undertaking not to levy delay damages "
                          f"(not provided as at {_today()}).", "source": "uploaded project contract", "test": "delay_damages"})
    return out


def _deal(c: dict[str, Any]) -> Any | None:
    try:
        from backend.dealdesk.house_style.bankform import ctx
        return ctx.load(c["proposal_id"], price=False)
    except Exception:  # noqa: BLE001
        return None


def _bank_observations(c: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    D = _deal(c)
    if D is None:
        return out
    asof = _today()
    nc = [t for t in D.rows("dd_tnc") if str(t.get("existing_status")) == "not_complied"]
    if any(not str(t.get("tnc_id") or "").startswith("RQ-") for t in nc):  # the Bank's own condition record first; the request's copy adds nothing
        nc = [t for t in nc if not str(t.get("tnc_id") or "").startswith("RQ-")]
    for t in nc[:4]:
        out.append({"severity": "major", "section": "Terms and conditions", "title": "Existing condition not complied",
                    "text": f"Upon checking the conditions of the last approval, the following is not complied as at {asof}: {t.get('text')}",
                    "query": f"Explain why the condition is not complied and when it will be: {str(t.get('text'))[:160]}",
                    "cp": f"Prior to limit loading: compliance with the existing condition: {str(t.get('text'))[:200]}", "source": "per dd_tnc (the Bank's conditions)"})
    subj = {str(e.get("entity_id")) for e in D.rows("b360_entity") if e.get("role") == "subject"}
    names = {str(e.get("entity_id")): e.get("entity_name") or e.get("name") for e in D.rows("b360_entity")}
    rc = [r for r in D.rows("dd_returned_cheque")]
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rc:
        by.setdefault(str(r.get("entity_id") or r.get("obligor_id") or r.get("drawer") or "subject"), []).append(r)
    hdr = " ".join(str(v) for v in ((c["steps"].get("read") or {}).get("data", {}).get("request", {}).get("header") or {}).values())
    for mt in re.finditer(r"([A-Z][\w .&'-]{3,60}?)\s*\(\s*CIF\s*([A-Z]{1,4}\s?\d{3,})", hdr):
        names.setdefault(mt.group(2).replace(" ", ""), mt.group(1).strip(" —-"))
    f = intake_facts(c) or {}
    told = " ".join(t.get("sentence", "") for t in f.get("reconciliation") or [] if "returned" in t.get("sentence", "").lower())
    for eid, rows in by.items():
        who = names.get(eid) or rows[0].get("entity_name") or rows[0].get("drawer_name") or eid
        if eid in told or (who and who in told):
            continue  # the customer file already reports these cheques (one engine per fact)
        amt = sum(float(r.get("amount_mn") or r.get("amount") or 0) for r in rows)
        dates = sorted(str(r.get("returned_date") or r.get("return_date") or r.get("date") or "")[:10] for r in rows)
        connected = eid not in subj and who != c.get("customer")
        out.append({"severity": "major" if connected else "minor", "section": "Relationship with the bank",
                    "title": f"Returned cheques: {who}" + (" (connected party)" if connected else ""),
                    "text": f"We note that {who}{' (a connected party of the group)' if connected else ''} has {len(rows)} returned cheque{'s' if len(rows) != 1 else ''} "
                            f"of {m(amt, 2)} between {d(dates[0])} and {d(dates[-1])} (per dd_returned_cheque).",
                    "query": f"Explain the returned cheques of {who} and the group's exposure to it.", "cp": "",
                    "source": "per dd_returned_cheque"})
    cls = [r for r in D.rows("bureau_entity_report") if str(r.get("classification") or r.get("status") or "").lower() not in ("", "regular", "standard", "current", "clear", "none")]
    for r in cls[:3]:
        who = r.get("entity_name") or r.get("name") or r.get("entity_id")
        out.append({"severity": "major", "section": "Credit bureau", "title": f"Bureau classification: {who}",
                    "text": f"Upon checking the bureau, {who} is reported as {r.get('classification') or r.get('status')} "
                            f"(overdue {m(r.get('overdue_mn'), 2)}, report of {d(r.get('report_date'))}) (per bureau_entity_report).",
                    "query": f"Explain the bureau classification of {who} and its link to the borrower.", "cp": "", "source": "per bureau_entity_report"})
    return out


def _flow_observations(c: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    st = c["steps"]
    an = (st.get("analysis") or {}).get("data") or {}
    asof = _today()
    if an.get("within_capacity") is False:
        out.append({"severity": "critical", "section": "Analysis", "title": "Ask above the borrower's capacity",
                    "text": f"As per the Deal Desk capacity engine, the ask of {m(an.get('ask_mn'))} is above the capacity of {m(an.get('capacity_mn'))} as at {asof}.",
                    "query": "Justify the amount against the borrower's cash cycle and project cash flow, or reduce the ask to capacity.",
                    "cp": "", "source": "per Deal Desk (capacity engine)"})
    try:
        if an.get("raroc_pct") is not None and an.get("hurdle_pct") is not None and float(an["raroc_pct"]) < float(an["hurdle_pct"]):
            out.append({"severity": "major", "section": "Analysis", "title": "Pricing below the hurdle",
                        "text": f"As per the Deal Desk economics engine, RAROC on the ask is {float(an['raroc_pct']):.1f}% against a {float(an['hurdle_pct']):.1f}% hurdle as at {asof}.",
                        "query": "Propose pricing (commission, margin, fees) or ancillary business that brings the deal to the hurdle.", "cp": "",
                        "source": "per Deal Desk (economics engine)"})
    except (TypeError, ValueError):
        pass
    sx = (st.get("stress") or {}).get("data") or {}
    ask = next((s for s in sx.get("structures") or [] if s.get("key") == "ask"), None)
    if ask and ask.get("survives_up_to") in (None, "none", "mild"):
        out.append({"severity": "major", "section": "Stress", "title": "The ask does not survive moderate stress",
                    "text": f"As per the Deal Desk stress engine, the ask " + (f"survives up to {ask['survives_up_to']} stress" if ask.get("survives_up_to") not in (None, "none")
                                                                                 else "does not survive even the mild stress") + f" as at {asof}"
                            + (f"; first break: {ask['first_break']}" if ask.get("first_break") else "") + ".",
                    "query": "Comment on the structure changes credit proposes (stress-proofed structure) or offer mitigants.", "cp": "",
                    "source": "per Deal Desk (stress engine)"})
    return out


# ------------------------------------------------------------------ the paper

def _sec(key: str, heading: str, voice: str, blocks: list[dict[str, Any]], part: str = "response", sources: list[str] | None = None) -> dict[str, Any]:
    return {"key": key, "n": None, "heading": heading, "voice": voice, "part": part, "blocks": blocks, "gaps": [], "needs": [], "uses": [],
            "contract_met": True, "method": "deterministic", "sources": sources or []}


def _request_section(c: dict[str, Any]) -> dict[str, Any]:
    rd = c["steps"]["read"]["data"]
    req = rd["request"]
    dl = (c["steps"].get("deal") or {}).get("data") or {}
    h, t = req["header"], req["totals"]
    rm = req["fields"].get("rm") or "the RM"
    when = d(req["action"].get("previous_date")) if req["action"].get("previous_date") else ""
    bl = [B.P(f"Business request of {rm} dated {h.get('date') or 'not provided'} received by the credit division on {_today()} as {req['document']} "
              f"(read as {req['method']}); as per business, total limits of {m(t.get('proposed'))} against {m(t.get('existing'))} existing "
              f"and {m(t.get('outstanding'))} outstanding."),
          B.P(f"Read from the request: {req['counts']['facilities']} limit lines, {req['counts']['security']} security items and {req['counts']['terms']} terms "
              f"(per dd_credit_request, case {c['case_id']}).")]
    if dl:
        mt = dl.get("match") or {}
        bl.append(B.P(f"Customer identified by {mt.get('how')}: {'existing customer, CIF ' + mt['cif'] if mt.get('existing') and mt.get('cif') else 'new to the Bank'}; "
                      f"deal {dl.get('proposal_id')}; the engines read the ask as {m(dl.get('ask', {}).get('amount'))} ({dl.get('amount_basis')}) as at {_today()}."))
    if req["action"].get("previous_ref"):
        bl.append(B.P(f"As per business, the limits were last approved under {req['action']['previous_ref']}" + (f" on {when}" if when else "") + "."))
    if req.get("read_gaps"):
        bl.append(B.BL([f"Not read from the request: {g} (not provided in a readable form)." for g in req["read_gaps"]]))
    just = []
    for ln in req["sections"].get("justification") or []:
        if re.search(r"_{4,}|relationship manager$|unit head|^\s*[A-Z][a-z]+ [A-Z][a-z'-]+(?: [A-Z][a-z'-]+)?\s*$", ln):
            break
        just.append(ln)
    if just:
        sents = [x.strip() for x in re.split(r"(?<=[.;])\s+(?=[A-Z])", " ".join(just)) if x.strip()]
        bl.append(B.H("RM's justification (as per business)"))
        bl.append(B.BL([f"As per business: {x}" for x in sents[:10]]))
    return _sec("cr_request", "Business request received and read", "business", bl, sources=[f"uploaded: {req['document']}"])


def _documents_section(c: dict[str, Any]) -> dict[str, Any]:
    rd = c["steps"]["read"]["data"]
    docs = [x for x in rd["documents"] if not x.get("duplicate")]
    f = intake_facts(c)
    bl: list[dict[str, Any]] = []
    if f:
        k = f.get("counts") or {}
        bl.append(B.P(f"Customer file {f.get('intake_id')}: {k.get('received', 0)} of {k.get('required', 0)} required documents received, {k.get('missing', 0)} not provided "
                      f"and {k.get('expired', 0)} expired as at {_today()} (per dd_intake checklist)."))
        rows = []
        for x in f.get("checklist") or []:
            if str(x.get("status")) in ("not_applicable",):
                continue
            rows.append([str(x.get("label") or x.get("doc_label") or x.get("requirement") or ""), str(x.get("subject") or ""), str(x.get("status") or "").replace("_", " "),
                         str(x.get("file_name") or x.get("files") or "")[:60] if not isinstance(x.get("files"), list) else ", ".join(map(str, x["files"]))[:60]])
        if rows:
            bl.append(B.T(["Requirement", "Subject", "Status", "File"], rows[:60], source="Customer file checklist (session i intake, dd_intake)", size=7.0))
        flags = [t for t in f.get("reconciliation") or [] if t.get("status") == "agrees"]
        if flags:
            bl.append(B.H("Figures that agree across the documents"))
            bl.append(B.BL([f"{t['sentence'].rstrip('.')} (source: customer file reconciliation)." for t in flags[:8]]))
    else:
        rows = [[x["name"], x.get("label") or "", x.get("method") or "", "read" if x.get("doc_type") else (x.get("read_error") or "not recognised")] for x in docs]
        bl.append(B.P(f"{len(docs)} supporting documents uploaded with the request as at {_today()}; the customer-file checklist is not available."))
        if rows:
            bl.append(B.T(["File", "Document", "Read as", "Status"], rows, source="uploaded with the request", size=7.0))
    return _sec("cr_documents", "Documents reviewed", "credit", bl, sources=["dd_intake", "uploaded documents"])


def voiced(text: str, source: str) -> str:
    """Each sentence that carries no figure-and-date and no attribution gets its source in brackets (the credit voice, V1)."""
    from backend.dealdesk.house_style.bankform import voice as V
    out = []
    for snt in V.sentences(text):
        if V.sentence_problems(snt, "credit"):
            end = snt[-1] if snt[-1] in ".?" else ""
            core = snt[:-1] if end else snt
            close = "__" if core.endswith("__") else ""
            core = core[:-2] if close else core
            snt = f"{core}{close} (source: {source}){end or '.'}"
        out.append(snt)
    return " ".join(out)


COMMON_FIRST = {"The", "Receivables", "Retention", "Cumulative", "If", "Revenue", "Owners", "Payment", "All", "Net", "Both", "Bank", "Credit",
                "Certified", "Statement", "Turnover", "Sales", "Audited", "Gross", "Total", "Current", "Due", "Related", "Top", "One", "Two", "Three"}


def _file_section(obs: list[dict[str, Any]]) -> dict[str, Any]:
    if not obs:
        return _sec("cr_file", "Credit comments on the request and the documents", "credit",
                    [B.P(f"No exception found when the request, the documents and the Bank's data are read together as at {_today()} (per CreditProbe).")])
    items = []
    for o in obs:
        t = o["text"]
        if not re.match(r"^(We note|Upon checking|As per)", t):
            first = t.split(" ", 1)[0]
            t = "We note that " + (t[0].lower() + t[1:] if first in COMMON_FIRST else t)
        if o["severity"] == "critical" and "__" not in t:
            t = f"__{t.rstrip('.')}__."
        t = voiced(t, o["source"])
        items.append(f"{t.rstrip('.')} ({o['severity']}).") if t.rstrip(".").endswith(f"(source: {o['source']})") else \
            items.append(f"{t.rstrip('.')} ({o['severity']}; source: {o['source']}).")
    return _sec("cr_file", "Credit comments on the request and the documents", "credit", [B.BL(items)], sources=sorted({o["source"] for o in obs}))


def _flow_section(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.credit_response import flow as FL
    rows = []
    for k, label in FL.STEPS:
        s = c["steps"].get(k) or {}
        rows.append([label, s.get("status", "not run"), (s.get("headline") or "; ".join(s.get("plain_words") or []))[:260], f"{s.get('seconds', '–')}"])
    bl = [B.P(f"The request was run through the Deal Desk flow on {_today()}: proposal check, review, analysis, structure and optimise, stress, "
              f"stress-proof and recommendation (per Deal Desk, deal {c.get('proposal_id')})."),
          B.T(["Step", "Status", "Result", "Seconds"], rows, source="Deal Desk engines (one engine per fact)", size=7.0)]
    st = (c["steps"].get("structure") or {}).get("data") or {}
    srows = [[r.get("label"), m((r.get("terms") or {}).get("amount")), f"{r.get('raroc'):.1f}%" if isinstance(r.get("raroc"), (int, float)) else "–",
              f"{r.get('hurdle'):.1f}%" if isinstance(r.get("hurdle"), (int, float)) else "–", f"{r.get('dscr'):.2f}x" if isinstance(r.get("dscr"), (int, float)) else "–",
              "yes" if r.get("recommendable") else (r.get("not_recommendable_reason") or "no")[:60]] for r in st.get("rows") or []]
    if srows:
        bl += [B.H("Structures compared"), B.T(["Structure", "Amount", "RAROC", "Hurdle", "DSCR", "Recommendable"], srows, source="per dd_structure_set", size=7.0)]
    pr = (c["steps"].get("proof") or {}).get("data") or {}
    if pr.get("changes"):
        bl.append(B.P(f"As per the stress-proofing engine, the structure that survives moderate stress needs: {'; '.join(pr['changes'][:5])}"
                      + (f" (RAROC {pr['raroc_before_pct']:.1f}% → {pr['raroc_after_pct']:.1f}%)" if isinstance(pr.get("raroc_before_pct"), (int, float)) and isinstance(pr.get("raroc_after_pct"), (int, float)) else "")
                      + f", as at {_today()}."))
    return _sec("cr_flow", "Deal Desk flow on the request (CreditProbe)", "credit", bl, sources=["dd_structure_set", "dd_stress_result", "dd_stress_proof"])


def _decision(c: dict[str, Any], obs: list[dict[str, Any]]) -> tuple[str, str]:
    rec = (c["steps"].get("recommendation") or {}).get("data") or {}
    crit = [o for o in obs if o["severity"] == "critical"]
    tone = rec.get("tone") or ""
    label = rec.get("decision") or ""
    st = rec.get("structure") or {}
    if "counter" in label.lower():
        terms = rec.get("structure_terms") or {}
        return ("Counter-offer", f"Credit division does not support the request as proposed and offers the {st.get('label') or 'recommended'} structure"
                + (f" ({m(terms.get('amount'))} for the new limit)" if terms.get("amount") else "") + f" as at {_today()}"
                + (f", subject to the {len(crit)} critical matter{'s' if len(crit) != 1 else ''} below being cleared prior to limit loading" if crit else "") + ".")
    if tone == "negative" or "not" in label.lower():
        return ("Not supported as proposed", f"Credit division does not support the request as proposed as at {_today()}: {rec.get('why') or label}"
                + (f"; {len(crit)} critical matter{'s' if len(crit) != 1 else ''} remain open" if crit else "") + ".")
    if crit:
        return ("Supported subject to conditions", f"Credit division supports the request on the {st.get('label') or 'recommended'} structure as at {_today()}, "
                f"subject to the {len(crit)} critical matter{'s' if len(crit) != 1 else ''} below being cleared prior to limit loading.")
    return ("Supported", f"Credit division supports the request on the {st.get('label') or 'recommended'} structure as at {_today()} (per Deal Desk recommendation).")


def _recommendation(base: dict[str, Any] | None, c: dict[str, Any], obs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    rec = (c["steps"].get("recommendation") or {}).get("data") or {}
    an = (c["steps"].get("analysis") or {}).get("data") or {}
    head, line = _decision(c, obs)
    st = rec.get("structure") or {}
    terms = rec.get("structure_terms") or {}
    co = counter_offer(c, obs)
    crit = [o for o in obs if o["severity"] == "critical"]
    if co:
        nw, dm = co["project"], co["dmccm"]
        head = "Counter-offer"
        line = (f"Credit division supports the renewal and the {nw['name']} limit with a reduced and staged funded line of {m(co['project_mn'])} "
                f"(asked {m(nw['limit_mn'])}) as at {_today()}, given the employer's payment delays on the financed projects"
                + (f", subject to the {len(crit)} critical matter{'s' if len(crit) != 1 else ''} below being cleared prior to limit loading" if crit else "") + ".")
    nums = [f"**{head}**: {line}"]
    if co:
        nw, dm = co["project"], co["dmccm"]
        for g in co["general"]:
            e, pr = g.get("existing_mn") or 0.0, g.get("proposed_mn") or 0.0
            nums.append(f"{'Renew' if pr == e else 'Approve'} the {g['limit_name']} of {m(pr)}" + (f" (existing {m(e)})" if pr != e else "")
                        + f", structure and pricing as per the request ({_today()}).")
        subs = [f"{k['limit_name']} {m(k['proposed_mn'])}" if k is not dm else f"{k['limit_name']} {m(co['dmccm_mn'])} (requested {_f(dm['proposed_mn'])})"
                for k in nw["kids"]]
        s2 = co["stress"]["two"][0]
        nums.append(f"Approve the {nw['name']} project limit at {m(co['project_mn'])}: " + "; ".join(subs)
                    + f"; the DMCCM covers the project's peak deficit with certificates paid 2 months late ({m(s2)}, credit's re-performance in section 13) "
                      f"and is released only while no certificate of the financed projects is more than 60 days overdue ({_today()}).")
        nums.append(f"Total facilities {m(co['total_mn'])} (asked {m((c['steps']['read']['data']['request'].get('totals') or {}).get('proposed'))}); "
                    f"group exposure cap {m(co['cap_mn'])}" + (f" (requested {_f(co['cap_asked'])})" if co.get("cap_asked") else "")
                    + f": borrower {m(co['total_mn'])} and the other group entities {m(co['others_mn'])} = {m(co['group_mn'])} (per b360_entity, {_today()}).")
        cp_rows = [o for o in obs if "connected party" in o["title"].lower()]
        if cp_rows:
            who = re.sub(r"\s*\(connected party\)$", "", cp_rows[0]["title"].split(":", 1)[-1]).strip()
            nums.append(f"{who}: keep on watchlist, no new limits; regularise the returned cheques and past dues and report to credit monthly "
                        f"(per dd_returned_cheque, {_today()}).")
        st = {}
    elif st:
        nums.append(f"Structure: {st.get('label')}, {m(terms.get('amount'))}"
                    + (f", {terms.get('tenor_years')} years" if terms.get("tenor_years") else "")
                    + (f", commission {terms.get('commission_bps')} bps" if terms.get("commission_bps") else "")
                    + (f", margin {terms.get('margin_bps')} bps" if terms.get("margin_bps") else "")
                    + (f"; RAROC {float(st['raroc']):.1f}% against {float(st['hurdle']):.1f}%" if isinstance(st.get("raroc"), (int, float)) and isinstance(st.get("hurdle"), (int, float)) else "")
                    + f" (per Deal Desk, {_today()}).")
    ap = rec.get("approval") or an.get("approval")
    if ap:
        nums.append(f"Approval authority: **{ap}**" + (f"; {rec.get('approval_rule') or an.get('approval_rule')}" if (rec.get("approval_rule") or an.get("approval_rule")) else "")
                    + f" (per the engine's delegation of authority, {_today()}).")
    cps: list[str] = []
    for o in obs:
        if o.get("cp") and o["cp"] not in cps:
            cps.append(o["cp"])
    for x in rec.get("conditions_precedent") or []:
        x = str(x)
        if x and x not in cps:
            cps.append(x if x.lower().startswith("prior to limit loading") else f"Prior to limit loading: {x}")
    req = c["steps"]["read"]["data"]["request"]
    base_perfection = any("perfected" in x for bk in (base or {}).get("blocks") or [] if bk["t"] == "numbered" for x in bk["items"])
    for s in ([] if base_perfection else req.get("security") or []):  # the bank-form writer lists the perfection conditions itself
        if s["perfection_status"] == "pending":
            cps.append(f"Prior to limit loading: {s['text'][:180].rstrip('.')} to be perfected; RM to confirm in writing (as per business, deadline "
                       f"{d(s.get('deadline')) or 'not provided'}).")
    under = [str(x) for x in rec.get("covenants") or [] if x][:6]
    mon = rec.get("monitoring") or {}
    duties = []
    if mon:
        duties.append(f"Monitoring tier {mon.get('tier') or 'not set'}, review every {mon.get('review_frequency_months') or '–'} months (per Deal Desk monitoring plan, {_today()}).")
    if any(o.get("test", "").startswith("payment_certificates") or "certificate" in o["title"].lower() for o in obs):
        duties.append(f"RM and regional head to report the ageing and collection of every certified payment certificate within 5 working days of each month end "
                      f"from {_today()}, dually signed.")
    if any("extension of time" in o["title"].lower() for o in obs):
        duties.append(f"RM to obtain the employer's written decision on the extension of time and report it to credit within 2 months of {_today()}.")
    blocks = [B.P(f"Credit division response as at {_today()}: {line}"), B.H("Decision"), B.NL(nums)]
    # the bank-form writer's own decisions (structure, limits, group exposure), its additional conditions merged into the
    # conditions precedent, and its findings-and-cures table, in that order
    sub, kept, extra_cps, tail = "", [], [], []
    for bk in (base or {}).get("blocks") or []:
        if bk["t"] == "h":
            sub = bk["text"]
            continue
        if bk["t"] == "numbered" and "condition" in sub.lower():
            extra_cps += [re.sub(r"\bfor\s+to be\b", "to be", x) for x in bk["items"] if x not in cps]  # an item without an amount
        elif bk["t"] == "numbered" or (bk["t"] == "p" and "group exposure" in bk.get("text", "").lower()):
            kept.append(bk)
        elif bk["t"] == "table" or ("finding" in sub.lower() and bk["t"] == "p"):
            tail.append(bk)
    if kept and head not in ("Not supported as proposed", "Counter-offer"):
        # the bank-form writer's approve-lines are the ask's: they stand only when credit supports the ask (one decision per paper)
        blocks += [B.H("Decisions on the structure and the limits")] + kept
    if intake_facts(c):
        # the customer file's checklist is the one engine for documents: the bank-form's policy-document list is not repeated
        extra_cps = [x for x in extra_cps if not re.search(r"\(pending as at [^;]*; Credit Policy", x)]
    if co:
        extra_cps = [re.sub(r"Promissory note for SAR [\d,.]+m", f"Promissory note for {m(co['total_mn'])}", x) for x in extra_cps]
    cps = cps + extra_cps
    from backend.dealdesk.deposit_requirement.docs import credit_response_cps  # Round D: the deposit on the recommended structure
    cps += [x for x in credit_response_cps(c, terms) if not any(re.search(r"lien-marked cash deposit|operating balances", y, re.I) for y in cps)]
    cps = [voiced(x, f"credit division, {_today()}") for x in cps]
    duties = [voiced(x, f"credit division, {_today()}") for x in duties]
    if cps:
        blocks += [B.H("Conditions precedent (prior to limit loading)"), B.NL(cps)]
    if under:
        blocks += [B.H("Covenants and undertakings"), B.NL([u if re.search(r"\d", u) else f"{u} (per Deal Desk recommendation, {_today()})" for u in under])]
    if duties:
        blocks += [B.H("Monitoring duties"), B.NL(duties)]
    if tail:
        blocks += [B.H("Findings and their cures (per Deal Desk)")] + tail
    sec = copy.deepcopy(base) if base else _sec("recommendation", "Credit division recommendation", "credit", [])
    sec["blocks"] = blocks
    summary = {"decision": f"{head}: {line}", "head": head, "recommendation": [re.sub(r"\*\*|__", "", x) for x in nums], "conditions": cps,
               "monitoring": duties, "covenants": under}
    return sec, summary


def _gross_margin(c: dict[str, Any]) -> tuple[float, str]:
    for code, label in (("inhouse_fs", "in-house"), ("audited_fs", "audited")):
        f = _latest(c, code)
        try:
            gm = float(f["gross_profit"]) / float(f["revenue"])
            per = str(f.get("period_to") or f.get("fiscal_year") or "")[:10]
            return gm, f"{label} statements to {d(per)}"
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
    return 0.10, "assumed 10% (no statement read)"


def counter_offer(c: dict[str, Any], obs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Credit's counter-offer on a new project limit when the employer pays late (a critical certificate finding): the project's
    DMCCM is cut to the peak cash deficit of the project under a two-month payment delay (rounded up to SAR 5m), released only while
    no certificate of the financed projects is more than 60 days overdue; a longer delay is for the shareholders to fund."""
    from backend.dealdesk.credit_response import projects as PJ
    req = c["steps"]["read"]["data"]["request"]
    nw = PJ.new_award(req)
    if not nw or not nw.get("limit") or not nw.get("months"):
        return None
    if not any(o.get("test") == "certificates" and o["severity"] == "critical" for o in obs):
        return None
    dm = next((k for k in nw["kids"] if re.search(r"DMCCM|murabaha|against .*certificates", k["limit_name"], re.I)), None)
    if not dm or not dm.get("proposed_mn"):
        return None
    gm, gm_src = _gross_margin(c)
    adv = next((k["proposed_mn"] / nw["value_mn"] for k in nw["kids"] if re.search(r"advance payment", k["limit_name"], re.I) and nw["value_mn"]), 0.10)
    base, s2, s4 = (PJ.cash_gap(nw["value_mn"], nw["months"], gm, advance=adv, delay=x) for x in (0, 2, 4))
    rec_dm = min(float(dm["proposed_mn"]), math.ceil(s2[0] / 5.0) * 5.0)
    if rec_dm >= float(dm["proposed_mn"]):
        return None
    cut = float(dm["proposed_mn"]) - rec_dm
    tot = (req.get("totals") or {}).get("proposed") or 0.0
    D = _deal(c)
    others = 0.0
    if D is not None:
        from backend.dealdesk.house_style.bankform import writers as W
        others = sum(W.num(e.get("exposure_total")) or 0 for e in D.rows("b360_entity") if str(e.get("relation") or "").lower() != "subject")
    total = round(tot - cut, 1)
    act = req.get("action") or {}
    cap = math.ceil((total + others) / 5.0) * 5.0
    return {"project": nw, "dmccm": dm, "dmccm_mn": rec_dm, "project_mn": round(float(nw["limit"]["proposed_mn"]) - cut, 1), "total_mn": total,
            "others_mn": round(others, 1), "group_mn": round(total + others, 1), "cap_mn": cap, "cap_asked": act.get("cap_to"),
            "stress": {"base": base, "two": s2, "four": s4}, "gm": gm, "gm_src": gm_src, "advance": adv,
            "general": [f for f in req.get("facilities") or [] if not f.get("total") and f.get("level") == 1 and f is not nw["limit"]]}


def _new_project_stress(c: dict[str, Any], secs: list[dict[str, Any]]) -> None:
    """§13: credit's re-performance of the new project's cash flow (business did not provide one)."""
    from backend.dealdesk.credit_response import projects as PJ
    req = c["steps"]["read"]["data"]["request"]
    nw = PJ.new_award(req)
    sec = next((s for s in secs if s["key"] == "new_project"), None)
    if not nw or not nw.get("months") or sec is None:
        return
    gm, gm_src = _gross_margin(c)
    adv = next((k["proposed_mn"] / nw["value_mn"] for k in nw["kids"] if re.search(r"advance payment", k["limit_name"], re.I) and nw["value_mn"]), 0.10)
    dm = next((k for k in nw["kids"] if re.search(r"DMCCM|murabaha|against .*certificates", k["limit_name"], re.I)), None)
    co = counter_offer(c, observations(c)) if dm else None
    rows = []
    for label, x in (("Base: paid 2 months after certification", 0), ("Stressed: paid 2 months late", 2), ("Stressed: paid 4 months late", 4)):
        pk, when = PJ.cash_gap(nw["value_mn"], nw["months"], gm, advance=adv, delay=x)
        row = [label, _f(pk), f"month {when}"]
        if dm:
            row.append(_f(max(0.0, pk - float(dm["proposed_mn"]))))
        if co:
            row.append(_f(max(0.0, pk - co["dmccm_mn"])))
        rows.append(row)
    cols = ["Scenario (SAR m)", "Peak deficit", "When"] + ([f"Not covered by DMCCM {_f(dm['proposed_mn'])} (asked)"] if dm else []) \
        + ([f"Not covered by DMCCM {_f(co['dmccm_mn'])} (recommended)"] if co else [])
    blk = [B.H("Credit's re-performance of the project cash flow (credit division)"),
           B.P(f"Business did not provide a cash flow for {nw['name']} as at {_today()}: credit re-performed it on SAR {_f(nw['value_mn'] / nw['months'])}m of work "
               f"per month over {nw['months']} months, costs at {_f((1 - gm) * 100)}% ({gm_src}) paid the following month, a {_f(adv * 100, 0)}% advance at start "
               f"against the advance payment guarantee, 10% retention and the advance recovery deducted from each certificate, certificates paid "
               f"2 months after certification (base) and 2 and 4 months later (stressed) (source: credit division re-performance, {_today()})."),
           B.T(cols, rows, source="credit division re-performance on the request's contract value and tenor", size=7.0)]
    sec["blocks"] = list(sec["blocks"]) + blk


def _elapsed(c: dict[str, Any], secs: list[dict[str, Any]]) -> None:
    """§9: time elapsed against work done per ongoing financed project ("63% of the contract period has elapsed against 41% of
    work done"), from the deal's dd_project rows."""
    sec = next((s for s in secs if s["key"] == "projects"), None)
    D = _deal(c)
    if sec is None or D is None:
        return
    from backend.dealdesk.credit_response.projects import as_of
    today = as_of()
    cs = _certs(c)
    try:  # work done is reported at the data date (the last statement the certificates are aged to), not the paper date
        today = date.fromisoformat(str(cs[0]["aged_to"])[:10]) if cs and cs[0].get("aged_to") else today
    except ValueError:
        pass
    out = []
    for r in D.rows("dd_project"):
        if r.get("is_new") or str(r.get("status") or "") in ("new", "completed"):
            continue
        try:
            st = date.fromisoformat(str(r.get("start_date"))[:10])
            en = date.fromisoformat(str(r.get("completion_original") or r.get("end_date_original"))[:10])
            wd = float(r.get("work_done_pct"))
        except (TypeError, ValueError):
            continue
        if en <= st:
            continue
        el = min(100.0, max(0.0, (today - st).days / (en - st).days * 100))
        name = re.sub(r"\s*\[.*?\]\s*$", "", str(r.get("project_name") or r.get("name") or ""))
        out.append(f"{name}: {_f(el, 0)}% of the contract period ({d(st.isoformat())} to {d(en.isoformat())}) has elapsed against {_f(wd, 0)}% of work done "
                   f"as at {d(today.isoformat())}" + (" (__behind programme__)" if el - wd >= 15 else "") + " (per dd_project).")
    if out:
        sec["blocks"] = list(sec["blocks"]) + [B.H("Time elapsed against work done (credit division)"), B.BL(out)]


def _audit_opinion(c: dict[str, Any], secs: list[dict[str, Any]]) -> None:
    """§14: the audit opinion as the uploaded audited statements give it (FY2025 "unqualified, with emphasis of matter"), before the
    Bank's register (dd_financials_detail says "clean")."""
    xs = sorted([x for x in _docs(c) if x.get("doc_type") == "audited_fs" and x["fields"].get("opinion")],
                key=lambda x: str(x["fields"].get("fiscal_year") or ""))
    if not xs:
        return
    f, name = xs[-1]["fields"], xs[-1]["name"].replace("__", "_")
    op = str(f["opinion"]).strip().rstrip(".")
    fy = str(f.get("fiscal_year") or "")[:4]
    em = ""
    if "emphasis" in op.lower():
        em = _clause(c, r"emphasis of matter") or ""
        em = re.sub(r"\s+", " ", em).strip().rstrip(".")
        em = re.sub(r"^emphasis of matter\s*:\s*", "", em, flags=re.I)
        em = re.split(r",\s*and that\b|;\s", em)[0]
        if len(em) > 240:
            em = em[:240].rsplit(",", 1)[0]
    kind = re.sub(r",?\s*with emphasis of matter", "", op, flags=re.I).strip().lower() or "unqualified"
    phrase = f"{'an' if kind[:1] in 'aeiou' else 'a'} {kind} opinion" + (" with emphasis of matter" if "emphasis" in op.lower() else "")
    text = f"with {phrase} (as per the uploaded {name}" + (f": {em}" if em else "") + ")"
    for s in secs:
        if s["key"] != "financials":
            continue
        for b in s["blocks"]:
            if b.get("t") == "p" and re.search(r"with an? [\w ,-]*? opinion on the statements", b.get("text", "")) and (not fy or f"FY{fy}" in b["text"]):
                b["text"] = re.sub(r"with an? [\w ,-]*? opinion on the statements", text + " on the statements", b["text"], count=1)
                return


_SESSION = re.compile(r"\b(?:per\s+)?session [a-z]\b\s*(?:current regime\s*\(backend/[\w/.]+\)|economics engine|structure set)?")


def _plain_sources(t: str) -> str:
    """No session or code names in a bank paper: "session m current regime (backend/scenarios/regime.py)" -> "CreditProbe market regime"."""
    def rep(mt: re.Match[str]) -> str:
        s = mt.group(0)
        lead = "per " if s.startswith("per ") else ""
        if "regime" in s:
            return lead + "CreditProbe market regime"
        if "economics" in s:
            return lead + "the CreditProbe economics engine"
        if "structure set" in s:
            return lead + "CreditProbe structure set"
        return lead + "CreditProbe "
    return _SESSION.sub(rep, t) if "session " in t else t


def _polish(secs: list[dict[str, Any]], obs: list[dict[str, Any]]) -> None:
    """The bank-form sections read as credit's response: §2 without the engine's structure notes (the action is business's ask),
    §18 without the "not available" line and without a strength a critical finding contradicts, no session or code names."""
    crit = " ".join(o["text"] for o in obs if o["severity"] == "critical")
    for s in secs:
        bl = []
        for b in s["blocks"]:
            if s["key"] == "action" and b.get("t") == "p" and re.match(r"(Credit has structured the request|As per the Deal Desk flow, no structure is selected"
                                                                        r"|No structure selected and no counter-proposal|The proposal is written on the structure)", b.get("text", "")):
                continue
            if s["key"] == "strengths" and b.get("t") == "p" and re.match(r"SWOT not available", b.get("text", "")):
                continue
            if s["key"] == "strengths" and "items" in b:
                keep = []
                for x in b["items"]:
                    g = re.search(r"guarantee of ([A-Z][\w'-]+(?: [A-Z][\w'-]+){1,3})", x)
                    if g and g.group(1) in crit:
                        continue  # the guarantor's net worth is mostly the borrower's own shares (critical finding)
                    keep.append(x)
                b = {**b, "items": keep}
                if not keep:
                    continue
            if "text" in b:
                b = {**b, "text": _plain_sources(b["text"])}
            if "items" in b:
                b = {**b, "items": [_plain_sources(x) if isinstance(x, str) else x for x in b["items"]]}
            if "pairs" in b:
                b = {**b, "pairs": [[k, _plain_sources(v) if isinstance(v, str) else v] for k, v in b["pairs"]]}
            bl.append(b)
        s["blocks"] = bl


def build(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.house_style.bankform import coverage, paper as BP, voice
    _register_parts()
    pid = c["proposal_id"]
    try:
        # the response is dated the day credit reads the request (the paper date), not the deal's data quarter: every
        # bank-form writer prints _asof(D) (statements and other data dates stay as their documents give them)
        from backend.dealdesk.credit_response.projects import as_of as _paper_date
        from backend.dealdesk.house_style.bankform import ctx
        D = ctx.load(pid)
        D.as_of = _paper_date().isoformat()
        D.p["as_of"] = D.as_of
        D.p["exposure_after_request"] = True  # group exposure = the other entities + the proposed total (w_group_exposure)
        act = ((c["steps"].get("read") or {}).get("data") or {}).get("request", {}).get("action") or {}
        if act.get("cap_to") is not None:
            D.p["group_cap_proposed"] = act["cap_to"]
            if act.get("cap_from") is not None:
                D.p["group_cap_existing"] = act["cap_from"]
        from backend.dealdesk.house_style.bankform import writers as W
        ents = D.rows("b360_entity")
        tp = W.totals(D)[2]
        if tp and any(str(e.get("relation") or "").lower() == "subject" for e in ents):
            D.p["group_exposure_total"] = round(sum(W.num(e.get("exposure_total")) or 0 for e in ents if str(e.get("relation") or "").lower() != "subject") + tp, 1)
        p = BP.write(pid, D=D)
    except Exception as e:  # noqa: BLE001 - the deal could not be read as a paper: the response still stands on the case
        p = {"proposal_id": pid, "kind": "bank_form_proposal", "title": "", "customer": c.get("customer") or "", "group": "", "currency": "SAR",
             "as_of": "", "as_of_label": _today(), "rating": "", "sector": "", "sections": [], "totals": {}, "header_line": [], "error": str(e)}
    obs = observations(c)
    secs = list(p.get("sections") or [])
    _audit_opinion(c, secs)
    _new_project_stress(c, secs)
    fee = (((c["steps"].get("read") or {}).get("data") or {}).get("request", {}).get("action") or {}).get("fee")
    for s in secs:
        if s["key"] == "facilities" and fee:
            s["blocks"] = [{**b, "text": f"Study and documentation fee: {fee} (as per business)."} if b.get("t") == "p" and
                           b.get("text", "").startswith("Study and documentation fee: not provided") else b for b in s["blocks"]]
    try:
        _elapsed(c, secs)
    except Exception:  # noqa: BLE001 - an added table never stops the response
        pass
    by ={s["key"]: s for s in secs}
    # the response's own sections
    extra = [_request_section(c), _documents_section(c), _file_section(obs), _flow_section(c)]
    rec_sec, summary = _recommendation(by.get("recommendation"), c, obs)
    out = []
    for s in secs:
        if s["key"] == "recommendation":
            out.append(rec_sec)
        else:
            out.append(s)
    if "recommendation" not in by:
        out.append(rec_sec)
    # observations also land in the anatomy's "Exceptions and other observations" (section 17), in the credit voice
    exc = next((s for s in out if s["key"] == "exceptions"), None)
    if exc is not None and obs:
        base_blocks = []
        for bk in exc["blocks"]:
            if "items" in bk and intake_facts(c):
                items = [x for x in bk.get("items", []) if not re.search(r"required documents are pending or expired", x)]
                if not items:
                    continue
                bk = {**bk, "items": items}
            base_blocks.append(bk)
        crit = [o for o in obs if o["severity"] == "critical"]
        rest = [o for o in obs if o["severity"] != "critical"]
        add = [B.H("Exceptions (credit division, " + _today() + ")")]
        ex_items = [f"{re.sub(r'__', '', o['text']).rstrip('.')} (source: {o['source']})." for o in crit]
        D = _deal(c)
        gt = (by.get("group_exposure") or {}).get("blocks") or []
        cap_line = next((b["text"] for b in gt if b.get("t") == "p" and "above the approved cap" in b.get("text", "")), "")
        mt = re.search(r"group exposure of (SAR [\d,.]+m) is above the approved cap of (SAR [\d,.]+m)", cap_line)
        if mt:
            ex_items.append(f"Group exposure after the request of {mt.group(1)} is above the approved group cap of {mt.group(2)} as at {_today()} (per section 6).")
        if D is not None:
            for t in D.rows("dd_tnc"):
                if str(t.get("existing_status")) == "not_complied" and not str(t.get("tnc_id") or "").startswith("RQ-"):
                    ex_items.append(f"Existing condition not complied as at {_today()}: {str(t.get('text')).rstrip('.')} (per dd_tnc).")
        add.append(B.BL(ex_items) if ex_items else B.P(f"No exception as at {_today()} (credit division)."))
        if rest:
            add += [B.H("Other observations (details in the credit comments)"),
                    B.BL([f"{o['title']} ({o['severity']}; source: {o['source']})." for o in rest[:12]])]
        exc["blocks"] = base_blocks + add
    out += extra
    _polish(out, obs)
    p["sections"] = _ordered(out)
    cust = p.get("customer") or c.get("customer") or ""
    p["title"] = f"Credit division response · {cust}"
    p["kind"] = "credit_response"
    p["form_title"] = "CREDIT DIVISION RESPONSE"
    p["case_id"] = c["case_id"]
    p["header_line"] = [(k, (v.replace("-BFP", "-CDR") if k == "Ref" else _today() if k == "Date" else v)) for k, v in (p.get("header_line") or [])]
    p["as_of_label"] = _today()
    p["voice"] = voice.check_paper(p)
    p["density"] = voice.score(p)
    p["coverage"] = coverage.check(p)
    crit = sum(1 for o in obs if o["severity"] == "critical")
    summary["observations"] = [{"title": o["title"], "text": o["text"], "severity": o["severity"], "source": o["source"]} for o in obs]
    summary["plain_words"] = [f"Credit's answer: {summary['head'].lower()}.",
                              f"{len(obs)} observations from reading the request, the documents and the bank's data together ({crit} critical); "
                              f"{len(summary['conditions'])} conditions before the limits are loaded.",
                              f"The response is the bank form: the request as received, credit's comments section by section, the numbered "
                              f"recommendation and the signature blocks ({len(out)} sections; Word and PDF)."]
    summary["sections"] = len(out)
    summary["voice_problems"] = len(p["voice"])
    p["summary"] = summary
    return p


def _render_paper(paper: dict[str, Any]) -> dict[str, Any]:
    _register_parts()
    q = copy.deepcopy(paper)
    q["proposal_id"] = f"{paper['proposal_id']}"
    return q


def docx(paper: dict[str, Any]) -> tuple[bytes, str]:
    from backend.dealdesk.house_style.bankform import render_bank as RB
    data, _name = RB.docx(_render_paper(paper), "Credit division (CreditProbe)")
    return data, f"Credit_response_{paper['proposal_id']}.docx"


def pdf(paper: dict[str, Any]) -> tuple[bytes, str]:
    from backend.dealdesk.house_style.bankform import render_bank as RB
    data, _name, _pages = RB.pdf(_render_paper(paper))
    return data, f"Credit_response_{paper['proposal_id']}.pdf"
