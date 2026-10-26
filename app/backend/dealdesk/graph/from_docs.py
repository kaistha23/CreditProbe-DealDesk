"""Round G: one read document → graph statements (entities, links, standing, figures), each with the document, page and date.

Input: a document in R16's intake schema (backend/dealdesk/intake/service.read_pages, or Round A's agentic reader through
hook.push_documents): {doc_id, doc_type, doc_label, file_name, pages, fields: {name: {value, label, line, page?}}}. A field
may also be a plain value. Figures are copied exactly as read; nothing is computed.

What each document type maps to (the subject is the customer whose file it is):

| document | links | standing / figures |
|---|---|---|
| articles_of_association, commercial_registration | has_shareholder (pct), has_director (role) | share capital, CR expiry |
| aml_kyc_questionnaire | has_ubo (pct) | |
| simah_company | borrows_from (lender: product, limit, outstanding, status) | score, totals; a facility not "current" → the subject's standing |
| simah_consumer (owner / guarantor) | the beneficiaries of the person's guarantees → guaranteed_by | a guarantee not "current" → the beneficiary's standing |
| personal_net_worth | guaranteed_by | net worth of the guarantor |
| bank_statement | banks_with | total credits |
| other_bank_offer_letter, other_bank_statement | borrows_from (total limits, outstanding) | overdue → past due |
| receivables_ageing, top_customers_suppliers (customers) | has_buyer (share, sales, receivable) | |
| payables_ageing, top_customers_suppliers (suppliers) | has_supplier (share, purchases, payable) | |
| project_list, project_contract | has_project; project —employer→, —consultant→ | |
| valuation_report, title_deed, insurance_policy | pledges (collateral: value) | |
| audited_fs, inhouse_fs, vat_returns, nitaqat_certificate | | revenue, net profit, equity, assets, liabilities, sales, band |
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from backend.dealdesk.graph import names as N
from backend.dealdesk.graph import store as G

DOC_LABEL = {
    "articles_of_association": "Articles of Association", "commercial_registration": "Commercial Registration",
    "aml_kyc_questionnaire": "AML/KYC questionnaire", "simah_company": "SIMAH company report", "simah_consumer": "SIMAH consumer report",
    "personal_net_worth": "Personal net-worth statement", "bank_statement": "Bank statement", "other_bank_offer_letter": "Other bank's offer letter",
    "other_bank_statement": "Other bank's facility statement", "receivables_ageing": "Receivables ageing", "payables_ageing": "Payables ageing",
    "top_customers_suppliers": "Top customers and suppliers", "project_list": "Project list", "project_contract": "Project contract",
    "valuation_report": "Valuation report", "title_deed": "Title deed", "insurance_policy": "Insurance policy", "audited_fs": "Audited financial statements",
    "inhouse_fs": "In-house financial statements", "vat_returns": "VAT returns", "nitaqat_certificate": "Nitaqat certificate",
}

#: figures learned per document type: (field, label, unit)
FACTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "audited_fs": (("revenue", "Revenue", "SAR"), ("net_profit", "Net profit", "SAR"), ("total_assets", "Total assets", "SAR"),
                   ("total_liabilities", "Total liabilities", "SAR"), ("total_equity", "Total equity", "SAR"),
                   ("operating_cash_flow", "Operating cash flow", "SAR"), ("auditor", "Auditor", ""), ("opinion", "Audit opinion", "")),
    "inhouse_fs": (("revenue", "Revenue", "SAR"), ("net_profit", "Net profit", "SAR"), ("total_equity", "Total equity", "SAR")),
    "simah_company": (("score", "SIMAH score", ""), ("total_limits", "Bureau total limits", "SAR"), ("total_outstanding", "Bureau total outstanding", "SAR"),
                      ("total_overdue", "Bureau total overdue", "SAR"), ("lenders_count", "Lenders", ""), ("defaults_count", "Defaults on the bureau", "")),
    "commercial_registration": (("share_capital", "CR capital", "SAR"), ("expiry_date", "CR expiry", "date"), ("activity", "CR activity", "")),
    "nitaqat_certificate": (("nitaqat_band", "Nitaqat band", ""), ("saudisation_pct", "Saudisation", "%")),
    "vat_returns": (("total_taxable_sales", "VAT standard-rated sales, 12 months", "SAR"),),
    "receivables_ageing": (("total", "Receivables", "SAR"), ("bucket_over_365", "Receivables over 365 days", "SAR")),
    "payables_ageing": (("total", "Payables", "SAR"),),
    "personal_net_worth": (("net_worth", "Net worth", "SAR"),),
}

_BAD = (("default", re.compile(r"(?i)\bdefault|written[- ]off|\bloss\b")),
        ("classified", re.compile(r"(?i)substandard|doubtful|classified")),
        ("restructured", re.compile(r"(?i)restructur|reschedul")),
        ("past_due", re.compile(r"(?i)past due|overdue|\bdpd\b|days late")))


def standing(text: Any) -> str | None:
    """'Substandard (classified 07/2026)' → classified; 'Current' → None."""
    t = str(text or "")
    if not t or re.fullmatch(r"(?i)\s*(current|regular|performing|active|ok|good|closed|settled)\s*\.?", t):
        return None
    for code, rx in _BAD:
        if rx.search(t):
            return code
    return None


def fval(doc: dict[str, Any], name: str) -> tuple[Any, int | None, int | None]:
    """(value, page, line) of a field, whatever its shape."""
    f = (doc.get("fields") or {}).get(name)
    if f is None:
        return None, None, None
    if isinstance(f, dict) and "value" in f:
        page = f.get("page")
        if page is None and int(doc.get("pages") or 1) <= 1:
            page = 1
        return f.get("value"), page, f.get("line")
    return f, (1 if int(doc.get("pages") or 1) <= 1 else None), None


def _s(v: Any) -> str:
    return str(v or "").strip()


def ref_date(doc: dict[str, Any], default: str) -> str:
    for k in ("report_date", "statement_date", "as_of", "letter_date", "valuation_date", "completed_on", "period_to", "fiscal_year",
              "visit_date", "certified_on"):
        v, _, _ = fval(doc, k)
        if isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v):
            return v
    return default


def _period(doc: dict[str, Any]) -> str:
    fy, _, _ = fval(doc, "fiscal_year")
    if fy:
        return f"FY{str(fy)[:4]}"
    a, _, _ = fval(doc, "period_from")
    b, _, _ = fval(doc, "period_to")
    if a or b:
        return f"{a or ''} to {b or ''}".strip()
    y, _, _ = fval(doc, "year")
    return str(y or "")


def ingest(c: sqlite3.Connection, doc: dict[str, Any], ctx: dict[str, Any]) -> dict[str, int]:
    """Write one document's statements. ctx: subject_name, cr, cif, proposal_id, intake_id, origin, source_kind (upload | agent |
    seed), author, as_of (ISO date), synthetic. Returns counts."""
    code = doc.get("doc_type") or ""
    n = {"edges": 0, "statuses": 0, "facts": 0, "nodes": 0}
    if code in ("", "unknown", "unreadable"):
        return n
    subj_name = _s(fval(doc, "customer_name")[0]) or ctx.get("subject_name") or ""
    if not subj_name:
        return n
    cr = re.sub(r"\D", "", _s(fval(doc, "cr_number")[0])) or ctx.get("cr") or ""
    if ctx.get("subject_name") and N.same(subj_name, ctx["subject_name"])[0]:
        subj_name, cr = ctx["subject_name"], (ctx.get("cr") or cr)
    subj = G.upsert_node(c, subj_name, "company", cif=ctx.get("cif") or "", cr=cr)
    date = ref_date(doc, ctx.get("as_of") or "")
    label = f"{doc.get('doc_id') or ''} · {doc.get('doc_label') or DOC_LABEL.get(code, code.replace('_', ' ').capitalize())}".strip(" ·")

    def ev(page: int | None, line: int | None, key: str = "") -> dict[str, Any]:
        return {"source_kind": ctx.get("source_kind") or "upload", "source_label": DOC_LABEL.get(code, code.replace("_", " ").capitalize()),
                "doc_id": doc.get("doc_id"), "doc_label": label, "doc_type": code, "intake_id": ctx.get("intake_id"), "proposal_id": ctx.get("proposal_id"),
                "page": page, "line": line, "seen_date": date, "author": ctx.get("author") or "", "origin": ctx["origin"],
                "synthetic": bool(ctx.get("synthetic")), "key": key}

    def link(name: str, kind: str, rel: str, page: int | None, line: int | None, attrs: dict[str, Any], *, src: str | None = None,
             cr_: str = "") -> str | None:
        nm = _s(name)
        if not nm or N.is_aggregate(nm):
            return None
        if kind == "auto":
            kind = "person" if N.is_person(nm) else "company"
        if N.same(nm, subj_name)[0] and kind == "company":
            return None
        if N.related_marker(nm):
            attrs = {**attrs, "related": True}
        dst = G.upsert_node(c, nm, kind, cr=cr_)
        if G.add_edge(c, src or subj, rel, dst, ev(page, line, nm), {k: v for k, v in attrs.items() if v not in (None, "")}):
            n["edges"] += 1
        return dst

    def rows(field: str) -> tuple[list[dict[str, Any]], int | None, int | None]:
        v, p, ln = fval(doc, field)
        return ([r for r in v if isinstance(r, dict)] if isinstance(v, list) else []), p, ln

    if code in ("articles_of_association", "commercial_registration"):
        for f in ("shareholders", "owners"):
            rs, p, ln = rows(f)
            for r in rs:
                cr_ = re.sub(r"\D", "", _s(r.get("id_number"))) if "CR" in _s(r.get("id_number")).upper() else ""
                link(r.get("name"), "auto", "has_shareholder", p, ln, {"pct": r.get("pct"), "shares": r.get("shares")}, cr_=cr_)
        rs, p, ln = rows("managers")
        for r in rs:
            link(r.get("name"), "person", "has_director", p, ln, {"role": r.get("role")})
    elif code == "aml_kyc_questionnaire":
        rs, p, ln = rows("ubos")
        for r in rs:
            link(r.get("name"), "person", "has_ubo", p, ln, {"pct": r.get("pct"), "pep": r.get("pep")})
    elif code == "simah_company":
        rs, p, ln = rows("facilities")
        for r in rs:
            link(r.get("lender"), "bank", "borrows_from", p, ln, {"product": r.get("product"), "limit": r.get("limit"), "outstanding": r.get("outstanding"),
                                                                    "overdue": r.get("overdue"), "status": r.get("status")})
            st = standing(r.get("status")) or standing(r.get("remark"))
            if st:
                G.add_status(c, subj, st, f"{r.get('lender')}: {r.get('product')} — {r.get('status') or r.get('remark')}", ev(p, ln, "status"))
                n["statuses"] += 1
    elif code == "simah_consumer":
        person, pp, pl = fval(doc, "full_name")
        if _s(person):
            pid = G.upsert_node(c, _s(person), "person")
            rs, p, ln = rows("guarantees")
            for r in rs:
                ben = _s(r.get("beneficiary"))
                if not ben or N.is_aggregate(ben):
                    continue
                bid = subj if N.same(ben, subj_name)[0] else G.upsert_node(c, ben, "company")
                if G.add_edge(c, bid, "guaranteed_by", pid, ev(p, ln, ben), {"lender": r.get("lender"), "amount": r.get("amount"), "status": r.get("status")}):
                    n["edges"] += 1
                st = standing(r.get("status"))
                if st:
                    G.add_status(c, bid, st, f"{r.get('lender')}: {r.get('status')} (guaranteed by {person})", ev(p, ln, "status:" + ben))
                    n["statuses"] += 1
    elif code == "personal_net_worth":
        v, p, ln = fval(doc, "full_name")
        if _s(v):
            link(_s(v), "person", "guaranteed_by", p, ln, {"basis": "personal net-worth statement"})
    elif code == "bank_statement":
        v, p, ln = fval(doc, "bank_name")
        link(_s(v), "bank", "banks_with", p, ln, {"account": _s(fval(doc, "account_number")[0])[-4:]})
    elif code in ("other_bank_offer_letter", "other_bank_statement"):
        v, p, ln = fval(doc, "bank_name")
        bid = link(_s(v), "bank", "borrows_from", p, ln, {"total_limits": fval(doc, "total_limits")[0], "total_outstanding": fval(doc, "total_outstanding")[0]})
        rs, p2, ln2 = rows("facilities")
        over = [r for r in rs if isinstance(r.get("overdue"), (int, float)) and r.get("overdue")]
        if bid and over:
            G.add_status(c, subj, "past_due", f"{v}: overdue on {len(over)} facilit{'y' if len(over) == 1 else 'ies'}", ev(p2, ln2, "status"))
            n["statuses"] += 1
    elif code in ("receivables_ageing", "payables_ageing", "top_customers_suppliers"):
        for f, rel, who, amt in (("by_customer", "has_buyer", "customer", "total"), ("by_supplier", "has_supplier", "supplier", "total"),
                                  ("customers", "has_buyer", "name", "sales"), ("suppliers", "has_supplier", "name", "purchases")):
            rs, p, ln = rows(f)
            for r in rs:
                link(r.get(who), "company", rel, p, ln, {"share_pct": r.get("share_pct"), amt: r.get(amt), "relationship": r.get("relationship"),
                                                          "terms": r.get("terms"), "country": r.get("country")})
    elif code in ("project_list", "project_contract"):
        items = rows("projects")[0] if code == "project_list" else [{"project_id": fval(doc, "project_id")[0], "project": fval(doc, "project_id")[0],
                                                                      "employer": fval(doc, "employer")[0], "consultant": fval(doc, "consultant")[0],
                                                                      "contract_value": fval(doc, "contract_value")[0]}]
        p, ln = (rows("projects")[1:] if code == "project_list" else fval(doc, "employer")[1:])
        for r in items:
            pname = _s(r.get("project")) or _s(r.get("project_id"))
            if not pname:
                continue
            jid = G.upsert_node(c, f"{pname} ({subj_name})" if len(pname) <= 4 else pname, "project",
                                attrs={"project_id": r.get("project_id"), "contractor": subj_name})
            if G.add_edge(c, subj, "has_project", jid, ev(p, ln, pname), {"contract_value": r.get("contract_value"), "status": r.get("status"),
                                                                          "work_done_pct": r.get("work_done_pct")}):
                n["edges"] += 1
            if _s(r.get("employer")):
                link(r.get("employer"), "company", "employer", p, ln, {"project": pname}, src=jid)
            if _s(r.get("consultant")):
                link(r.get("consultant"), "company", "consultant", p, ln, {"project": pname}, src=jid)
    elif code in ("valuation_report", "title_deed", "insurance_policy"):
        prop, p, ln = fval(doc, "property")
        if _s(prop):
            kid = G.upsert_node(c, _s(prop), "collateral", attrs={"deed_number": fval(doc, "deed_number")[0]})
            if G.add_edge(c, subj, "pledges", kid, ev(p, ln, "collateral"), {"market_value": fval(doc, "market_value")[0],
                                                                            "forced_sale_value": fval(doc, "forced_sale_value")[0],
                                                                            "sum_insured": fval(doc, "sum_insured")[0], "owner": fval(doc, "owner")[0]}):
                n["edges"] += 1
    # figures learned (copied exactly as read)
    target = subj
    if code == "personal_net_worth" and _s(fval(doc, "full_name")[0]):
        target = G.upsert_node(c, _s(fval(doc, "full_name")[0]), "person")
    per = _period(doc)
    for field, flabel, unit in FACTS.get(code, ()):
        v, p, ln = fval(doc, field)
        if v in (None, "") or isinstance(v, (list, dict)):
            continue
        G.add_fact(c, target, field, flabel, v, unit, per, ev(p, ln, field))
        n["facts"] += 1
    return n
