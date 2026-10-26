"""R16 i: the document checklist of a customer file against the requirements (PLAN_R16 "Required documents").

Requirements are built from what the documents themselves say: one ID and one personal bureau report per owner who is
a person (owners from the AoA / CR / AML form), two audited years and the current-year in-house accounts, 12 months of
bank statements and VAT filings, one offer letter and one facility statement per other bank (lenders on the company
SIMAH report other than the Bank), project documents when the customer is a contractor, collateral documents when
security is offered, and the extras. Each line is received, missing, expired (printed expiry passed, or older than the
validity rule) or not applicable, with the reason in words.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from backend.dealdesk.intake.doctypes import BY_CODE, DOC_TYPES
from backend.dealdesk.intake.extract import norm

BANK_NAME = "Sandstone Harbour Bank"  # the demo bank ("the Bank"); data/dealdesk/demo_customers/CONTRACT.md
GROUP_ORDER = ["kyc", "company_legal", "credit_bureau", "financials", "bank_statements", "extras"]
GROUP_LABEL = {"kyc": "KYC", "company_legal": "Company legal", "credit_bureau": "Credit bureau", "financials": "Financials",
               "bank_statements": "Bank statements", "extras": "Other documents"}
#: the Deal Desk document rule each type answers (data/dealdesk/params/v1/documents.json), for the deal's own checklist
RULE_REF = {"commercial_registration": "DR-01", "articles_of_association": "DR-02", "audited_fs": "DR-03", "inhouse_fs": "DR-04",
            "simah_company": "DR-05", "simah_consumer": "DR-06", "other_bank_offer_letter": "DR-07", "personal_net_worth": "DR-08",
            "insurance_policy": "DR-10", "project_contract": "DR-11", "payment_certificate": "DR-12", "valuation_report": "DR-16",
            "board_resolution": "DR-19", "national_id": "DR-20", "bank_statement": "DR-26", "vat_returns": "DR-27",
            "aml_kyc_questionnaire": "DR-20"}
DATE_FIELDS = ("issue_date", "report_date", "letter_date", "statement_date", "resolution_date", "as_of", "certified_on",
               "valuation_date", "visit_date", "completed_on", "signed_on", "deed_date", "contract_date", "request_date", "period_to",
               "fiscal_year", "effective_date")
COMPANY_WORDS = re.compile(r"(?i)\b(co\.?|company|holding|llc|est\.?|establishment|group|trading|contracting|industries|ltd|limited|w\.?l\.?l)\b")


def fv(doc: dict[str, Any], f: str) -> Any:
    x = (doc.get("fields") or {}).get(f)
    return x.get("value") if isinstance(x, dict) else None


def add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    import calendar
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _date(s: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def ref_date(doc: dict[str, Any]) -> str | None:
    for f in DATE_FIELDS:
        v = fv(doc, f)
        if v and _date(v):
            return str(v)
    return None


def doc_status(doc: dict[str, Any], as_of: dt.date) -> tuple[str, str, str]:
    """(status, reason, valid_until) for one classified document."""
    d = BY_CODE.get(doc.get("doc_type") or "")
    if d is None:
        return "received", "", ""
    if d.validity == "expiry_date":
        exp = _date(fv(doc, "expiry_date"))
        if exp is None:
            return "received", "expiry date not read", ""
        if exp < as_of:
            return "expired", f"expired on {exp:%d/%m/%Y}", exp.isoformat()
        return "received", f"valid until {exp:%d/%m/%Y}", exp.isoformat()
    if d.validity.startswith("months:"):
        n = int(d.validity.split(":")[1])
        ref = _date(ref_date(doc))
        if ref is None:
            return "received", "date not read", ""
        until = add_months(ref, n)
        if until < as_of:
            return "expired", f"dated {ref:%d/%m/%Y}, older than {n} months", until.isoformat()
        return "received", f"dated {ref:%d/%m/%Y}, valid {n} months", until.isoformat()
    return "received", "", ""


def is_person(name: str) -> bool:
    return bool(name) and not COMPANY_WORDS.search(name)


def same_name(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    fa = (re.findall(r"[a-z]{2,}", str(a).lower()) or [""])[0]
    fb = (re.findall(r"[a-z]{2,}", str(b).lower()) or [""])[0]
    if min(len(na), len(nb)) >= 6 and (na in nb or nb in na) and (fa == fb or not fa or not fb):
        return True
    import difflib
    if min(len(na), len(nb)) >= 8 and difflib.SequenceMatcher(None, na, nb).ratio() >= 0.88:  # OCR: one or two letters misread
        return True
    wa = re.findall(r"[a-z]{2,}", str(a).lower())
    wb = re.findall(r"[a-z]{2,}", str(b).lower())
    if not wa or not wb or wa[0] != wb[0]:  # brothers share every name but the first: the first name must agree
        return False
    ta = set(w for w in wa if len(w) >= 3) - {"bin", "bint", "abdul"}
    tb = set(w for w in wb if len(w) >= 3) - {"bin", "bint", "abdul"}
    return len(ta & tb) >= 2


def owners(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Owners and their % from the AoA (first), the CR, the AML UBO list; persons and companies."""
    out: list[dict[str, Any]] = []

    def add(name: str, pct: Any, src: str) -> None:
        if not name:
            return
        for o in out:
            if same_name(o["name"], name):
                o["sources"].append(src)
                if o.get("pct") is None and pct is not None:
                    o["pct"] = pct
                return
        out.append({"name": name, "pct": pct, "person": is_person(name), "sources": [src]})
    for code, f, src in (("articles_of_association", "shareholders", "AoA"), ("commercial_registration", "owners", "CR"),
                         ("aml_kyc_questionnaire", "ubos", "AML form")):
        for doc in docs:
            if doc.get("doc_type") != code:
                continue
            for r in fv(doc, f) or []:
                if isinstance(r, dict):
                    add(str(r.get("name") or "").strip(), r.get("pct"), src)
    return out


def guarantors(docs: list[dict[str, Any]], own: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for doc in docs:
        if doc.get("doc_type") == "personal_net_worth" and fv(doc, "full_name"):
            names.append(str(fv(doc, "full_name")))
        if doc.get("doc_type") in ("business_request", "facility_request_letter"):
            text = " ".join(doc.get("lines") or [])
            for m in re.finditer(r"(?i)personal guarantee[s]? (?:of|from|by)\s+(?:Mr\.?\s+|Ms\.?\s+)?([A-Z][A-Za-z' \-]{4,60}?)(?=[,;.(]| for | covering | and |$)", text):
                g = m.group(1).strip()
                if not re.match(r"(?i)(the|our|its|their|his|her|both|all|each)\b", g):
                    names.append(g)
        if doc.get("doc_type") == "simah_consumer":  # a person who already guarantees the customer's facilities
            cust = next((fv(x, "customer_name") for x in docs if fv(x, "customer_name")), "")
            for r in fv(doc, "guarantees") or []:
                if isinstance(r, dict) and cust and same_name(str(r.get("beneficiary") or ""), str(cust)) and fv(doc, "full_name"):
                    names.append(str(fv(doc, "full_name")))
                    break
    if not names:  # no stated guarantor: owners who are persons holding 25% or more
        names = [o["name"] for o in own if o["person"] and (o.get("pct") or 0) >= 25]
    uniq: list[str] = []
    for n in names:
        if not any(same_name(n, u) for u in uniq):
            uniq.append(n)
    return uniq


def other_banks(docs: list[dict[str, Any]]) -> list[str]:
    banks: list[str] = []
    for doc in docs:
        if doc.get("doc_type") == "simah_company":
            for r in fv(doc, "facilities") or []:
                b = str((r or {}).get("lender") or "").strip()
                if b and not same_name(b, BANK_NAME) and not any(same_name(b, x) for x in banks):
                    banks.append(b)
        if doc.get("doc_type") in ("other_bank_offer_letter", "other_bank_statement"):
            b = str(fv(doc, "bank_name") or "").strip()
            if b and not same_name(b, BANK_NAME) and not any(same_name(b, x) for x in banks):
                banks.append(b)
    return banks


def _months_covered(docs: list[dict[str, Any]], code: str) -> tuple[set[str], list[str]]:
    months: set[str] = set()
    ids: list[str] = []
    for doc in docs:
        if doc.get("doc_type") != code:
            continue
        a, b = _date(fv(doc, "period_from")), _date(fv(doc, "period_to"))
        if a and b:
            d = dt.date(a.year, a.month, 1)
            while d <= b:
                months.add(f"{d:%Y-%m}")
                d = add_months(d, 1)
        ids.append(doc["doc_id"])
    return months, ids


def build(docs: list[dict[str, Any]], as_of: dt.date, *, contractor: bool | None = None, secured: bool | None = None,
          existing: bool = False) -> list[dict[str, Any]]:
    docs = [d for d in docs if d.get("doc_type") and d.get("doc_type") != "unknown"]
    by: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        by.setdefault(d["doc_type"], []).append(d)
    own = owners(docs)
    persons = [o for o in own if o["person"]]
    guar = guarantors(docs, own)
    banks = other_banks(docs)
    if contractor is None:
        contractor = bool(by.get("project_list") or by.get("project_contract") or by.get("payment_certificate"))
    if secured is None:
        secured = bool(by.get("valuation_report") or by.get("title_deed") or by.get("insurance_policy"))
    lines: list[dict[str, Any]] = []

    def line(code: str, subject: str, found: list[dict[str, Any]], *, applicable: bool = True, reason_missing: str = "",
             requirement: str = "") -> None:
        d = BY_CODE[code]
        rec = {"req_group": d.group, "doc_type": code, "requirement": requirement or d.label, "subject": subject,
               "doc_ids": ",".join(x["doc_id"] for x in found), "rule_ref": RULE_REF.get(code, ""), "valid_until": ""}
        if not applicable:
            rec.update(status="not_applicable", reason=reason_missing or "not required for this case")
        elif not found:
            rec.update(status="missing", reason=reason_missing or "not in the uploaded documents")
        else:
            sts = [doc_status(x, as_of) for x in found]
            best = next((s for s in sts if s[0] == "received"), sts[0])
            rec.update(status=best[0], reason=best[1], valid_until=best[2])
        lines.append(rec)

    def match(code: str, field: str, name: str) -> list[dict[str, Any]]:
        return [x for x in by.get(code, []) if same_name(str(fv(x, field) or ""), name)]

    # KYC: an ID per owner who is a person (owners known from the documents; else every ID uploaded)
    if persons:
        for o in persons:
            line("national_id", o["name"], match("national_id", "full_name", o["name"]), requirement="National ID of owner")
        for x in by.get("national_id", []):  # signatories / guarantors who are not owners
            if not any(same_name(str(fv(x, "full_name") or ""), o["name"]) for o in persons):
                line("national_id", str(fv(x, "full_name") or "signatory"), [x], requirement="National ID of signatory / guarantor")
    else:
        found = by.get("national_id", [])
        if found:
            for x in found:
                line("national_id", str(fv(x, "full_name") or "owner"), [x])
        else:
            line("national_id", "owners", [], reason_missing="no ID uploaded and no owner list (AoA / CR) to know whose")
    # company legal
    for code in ("articles_of_association", "commercial_registration", "vat_certificate", "zakat_certificate", "nitaqat_certificate"):
        line(code, "company", by.get(code, []))
    vm, vids = _months_covered(docs, "vat_returns")
    want = {f"{add_months(dt.date(as_of.year, as_of.month, 1), -k):%Y-%m}" for k in range(1, 13)}
    line("vat_returns", "12 months", [x for x in by.get("vat_returns", [])],
         reason_missing="no VAT filings uploaded")
    if vids and lines[-1]["status"] == "received":
        got = len(want & vm) if vm else 0
        months_n = len(vm)
        if months_n < 12:
            lines[-1].update(status="missing", reason=f"{months_n} of 12 months filed in the uploaded returns")
        else:
            lines[-1]["reason"] = f"{months_n} months filed ({min(vm)} to {max(vm)})"
            if got < 9:
                lines[-1].update(status="expired", reason=f"latest month filed {max(vm)}: not the last 12 months")
    # bureau
    line("simah_company", "company", by.get("simah_company", []))
    bureau_people = persons or [{"name": g} for g in guar]
    for o in bureau_people:
        line("simah_consumer", o["name"], match("simah_consumer", "full_name", o["name"]), requirement="SIMAH consumer report of owner")
    for g in guar:
        if not any(same_name(g, o["name"]) for o in bureau_people):
            line("simah_consumer", g, match("simah_consumer", "full_name", g), requirement="SIMAH consumer report of guarantor")
    if not bureau_people and not guar:
        line("simah_consumer", "owners", by.get("simah_consumer", []), reason_missing="no owner list to know whose")
    line("simah_consent", "company", by.get("simah_consent", []))
    # financials: two audited years, current-year in-house
    for y in (as_of.year - 2, as_of.year - 1):
        found = [x for x in by.get("audited_fs", []) if str(fv(x, "fiscal_year") or fv(x, "period_to") or "")[:4] == str(y)]
        line("audited_fs", f"FY{y}", found, requirement=f"Audited financial statements FY{y}")
    found = [x for x in by.get("inhouse_fs", []) if str(fv(x, "period_to") or "")[:4] == str(as_of.year)]
    line("inhouse_fs", f"{as_of.year} to date", found or by.get("inhouse_fs", []),
         requirement=f"In-house financial statements {as_of.year}")
    # bank statements: 12 months
    sm, sids = _months_covered(docs, "bank_statement")
    line("bank_statement", "12 months, all accounts", by.get("bank_statement", []), reason_missing="no bank statement uploaded")
    if sids:
        n = len(sm)
        rec = lines[-1]
        accts = len(sids)
        if n < 12:
            rec.update(status="missing", reason=f"{n} of 12 months covered ({accts} statement{'s' if accts != 1 else ''})")
        elif rec["status"] == "received":
            rec["reason"] = f"{n} months covered ({min(sm)} to {max(sm)}), {accts} statement{'s' if accts != 1 else ''}"
    # extras
    for code in ("facility_request_letter", "board_resolution", "authorised_signatories"):
        line(code, "company", by.get(code, []))
    for g in guar:
        line("personal_net_worth", g, match("personal_net_worth", "full_name", g), requirement="Personal net-worth statement of guarantor")
    if not guar:
        line("personal_net_worth", "guarantors", by.get("personal_net_worth", []), applicable=bool(by.get("personal_net_worth")),
             reason_missing="no personal guarantee offered")
    for b in banks:
        line("other_bank_offer_letter", b, match("other_bank_offer_letter", "bank_name", b))
        line("other_bank_statement", b, match("other_bank_statement", "bank_name", b))
    if not banks:
        line("other_bank_offer_letter", "other banks", [], applicable=False, reason_missing="no other bank on the company bureau report")
    for code in ("receivables_ageing", "payables_ageing", "top_customers_suppliers"):
        line(code, "company", by.get(code, []))
    line("project_list", "company", by.get("project_list", []), applicable=contractor, reason_missing="not a contractor")
    if contractor:
        # contracts and certificates are asked for the projects the Bank finances: those already evidenced by a contract
        # or a payment certificate, and a new award named in the project list or the request (the subject of the ask)
        projects: list[str] = []
        for x in by.get("project_contract", []) + by.get("payment_certificate", []):
            pid = str(fv(x, "project_id") or "").strip()
            if pid and not any(norm(pid) == norm(p) for p in projects):
                projects.append(pid)
        new_award = ""
        for x in by.get("project_list", []) + by.get("facility_request_letter", []) + by.get("business_request", []):
            for ln in x.get("lines") or []:
                m = re.search(r"(?i)new award[^:]*:\s*([^,;(]+)", ln)
                if m:
                    new_award = m.group(1).strip()
                    break
            if new_award:
                break

        def same_project(a: str, b: str) -> bool:
            na, nb = norm(a), norm(b)
            return bool(na and nb) and (na == nb or na in nb or nb in na)
        for p in projects:
            line("project_contract", p, [x for x in by.get("project_contract", []) if same_project(str(fv(x, "project_id") or ""), p)],
                 requirement="Project contract")
            certs = [x for x in by.get("payment_certificate", []) if same_project(str(fv(x, "project_id") or ""), p)]
            line("payment_certificate", p, sorted(certs, key=lambda x: str(fv(x, "certified_on") or ""))[-1:] if certs else [],
                 requirement="Latest payment certificate")
        if new_award and not any(same_project(new_award, p) for p in projects):
            line("project_contract", new_award, [x for x in by.get("project_contract", []) if same_project(str(fv(x, "project_id") or ""), new_award)],
                 requirement="Project contract (new award)", reason_missing="contract not provided (letter of award only?)")
    for code in ("valuation_report", "title_deed", "insurance_policy"):
        line(code, "collateral", by.get(code, []), applicable=secured, reason_missing="no real-estate security offered")
    for code in ("site_visit_report", "aml_kyc_questionnaire"):
        line(code, "company", by.get(code, []))
    for i, ln in enumerate(lines):
        ln["order"] = i
    lines.sort(key=lambda r: (GROUP_ORDER.index(r["req_group"]) if r["req_group"] in GROUP_ORDER else 9, r["order"]))
    return lines


def counts(lines: list[dict[str, Any]]) -> dict[str, int]:
    c = {"received": 0, "missing": 0, "expired": 0, "not_applicable": 0}
    for ln in lines:
        c[ln["status"]] = c.get(ln["status"], 0) + 1
    c["required"] = c["received"] + c["missing"] + c["expired"]
    return c


def requirement_catalogue() -> list[dict[str, Any]]:
    return [{"doc_type": d.code, "label": d.label, "group": d.group, "per": d.per, "validity": d.validity,
             "required_for": list(d.required_for)} for d in DOC_TYPES if d.required_for]
