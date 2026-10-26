"""The customer file a business request is written from: the documents (as intake read them) and the bank's own data.

    cf = load("R16-C1")                 # by proposal_id, customer key ("c1"), CIF or CR number
    cf = load("R16-C3", documents=[...])  # documents given by the caller (intake's extraction, same shape as below)

    cf["customer"]   {key, proposal_id, cif, group_id, group_name, name, cr_number, vat_number, city, sector, sub_sector, case,
                      existing}
    cf["documents"]  [{doc_id, doc_type, subject, title, issuer, issue_date, expiry_date, period_from, period_to, status,
                       fields, file, source}]       status received | expired | missing (checked against demo day)
    cf["missing"]    [{doc_type, subject, why}]
    cf["bank"]       {relation: rows}  the Bank's own data for an existing customer (Data Domains; [] for new-to-bank)
    cf["origin"]     where the documents came from: "intake" (session i's extraction) | "caller" | "pack" (the demo pack's
                     printed fields, data/dealdesk/demo_customers/<folder>/manifest.json)

Document shapes and field names are the R16 contract (data/dealdesk/demo_customers/CONTRACT.md §3-§4). Amounts in `fields` are
SAR units; Data Domains rows are SAR million.
"""
from __future__ import annotations

import json
import re
import pathlib
from datetime import date
from typing import Any

from backend.dealdesk.house_style.bankform import source as S

ROOT = pathlib.Path(__file__).resolve().parents[3]
PACKS = ROOT / "data" / "dealdesk" / "demo_customers"
AS_OF = "2026-10-21"

#: the Bank's relations read for an existing customer (CONTRACT §6) and their key
BANK_DEAL = ("dd_facility_limit", "dd_security", "dd_tnc", "dd_reference", "dd_group_exposure", "bureau_entity_report", "bureau_cbrbr",
             "other_bank_facility", "dd_financials_detail")
BANK_OBLIGOR = ("dd_customer_account", "dd_account_conduct", "dd_returned_cheque")
BANK_GROUP = ("b360_entity",)

LABELS = {  # CONTRACT §4 labels (used in the checklist and the sources line)
    "national_id": "National ID", "articles_of_association": "Articles of Association", "commercial_registration": "Commercial Registration",
    "vat_certificate": "VAT certificate", "zakat_certificate": "Zakat certificate", "nitaqat_certificate": "Nitaqat certificate",
    "vat_returns": "VAT filings (12 months)", "simah_company": "SIMAH company report", "simah_consumer": "SIMAH consumer report",
    "simah_consent": "SIMAH consent", "audited_fs": "Audited financial statements", "inhouse_fs": "In-house financial statements",
    "bank_statement": "Bank statement (12 months)", "facility_request_letter": "Facility request letter", "board_resolution": "Board resolution",
    "authorised_signatories": "Authorised signatory list", "personal_net_worth": "Personal net-worth statement",
    "other_bank_offer_letter": "Other bank's offer letter", "other_bank_statement": "Other bank's facility statement",
    "receivables_ageing": "Receivables ageing", "payables_ageing": "Payables ageing", "top_customers_suppliers": "Top customers and suppliers",
    "project_list": "Project list", "project_contract": "Project contract", "payment_certificate": "Payment certificate",
    "valuation_report": "Valuation report", "title_deed": "Title deed", "insurance_policy": "Insurance policy",
    "site_visit_report": "Site-visit report", "aml_kyc_questionnaire": "AML/KYC questionnaire", "business_request": "Business request",
}
#: validity rules (CONTRACT §4): "expiry" or months
VALIDITY = {"national_id": "expiry", "commercial_registration": "expiry", "zakat_certificate": "expiry", "nitaqat_certificate": "expiry",
            "insurance_policy": "expiry", "simah_company": 3, "simah_consumer": 3, "simah_consent": 12, "inhouse_fs": 6, "bank_statement": 3,
            "facility_request_letter": 3, "board_resolution": 12, "authorised_signatories": 12, "personal_net_worth": 12,
            "other_bank_statement": 3, "receivables_ageing": 3, "payables_ageing": 3, "top_customers_suppliers": 12, "project_list": 3,
            "valuation_report": 12, "site_visit_report": 6, "aml_kyc_questionnaire": 12}
#: the required list (PLAN_R16 "Required documents"): (doc_type, required_for)
REQUIRED = [("national_id", "all"), ("articles_of_association", "all"), ("commercial_registration", "all"), ("vat_certificate", "all"),
            ("zakat_certificate", "all"), ("nitaqat_certificate", "all"), ("vat_returns", "all"), ("simah_company", "all"),
            ("simah_consumer", "all"), ("audited_fs", "all"), ("inhouse_fs", "all"), ("bank_statement", "all"),
            ("facility_request_letter", "all"), ("board_resolution", "all"), ("authorised_signatories", "all"),
            ("personal_net_worth", "all"), ("other_bank_offer_letter", "all"), ("other_bank_statement", "all"),
            ("receivables_ageing", "all"), ("payables_ageing", "all"), ("top_customers_suppliers", "all"), ("project_list", "contractor"),
            ("project_contract", "contractor"), ("payment_certificate", "contractor"), ("valuation_report", "secured"),
            ("title_deed", "secured"), ("insurance_policy", "secured"), ("site_visit_report", "all"), ("aml_kyc_questionnaire", "all"),
            ("simah_consent", "all")]


class NotFound(KeyError):
    pass


def customers() -> list[dict[str, Any]]:
    """The demo customers (customers.json from session d, else the ids module)."""
    p = PACKS / "customers.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return data["customers"] if isinstance(data, dict) and "customers" in data else list(data)
        except (ValueError, KeyError, TypeError):
            pass
    try:
        from ops.r16_customers.ids import CUSTOMERS
        return [dict(c) for c in CUSTOMERS]
    except Exception:  # noqa: BLE001
        return []


def find(ref: str) -> dict[str, Any] | None:
    """A demo customer by key, proposal id, CIF, CR number or name; else any Deal Desk deal by its proposal id (dd_deal), so the
    business request can be written for every deal the desk knows."""
    r = str(ref or "").strip().lower()
    for c in customers():
        if r in {str(c.get(k, "")).lower() for k in ("key", "proposal_id", "cif", "cr_number", "folder", "name", "short") if c.get(k)}:
            return dict(c)
    rows = S.read("dd_deal", proposal_id=str(ref).strip()) if r else []
    if rows:
        d = rows[0]
        pj = d.get("proposal_json") if isinstance(d.get("proposal_json"), dict) else {}
        ob = (pj or {}).get("obligor") or {}
        cif = str(d.get("cif") or d.get("obligor_id") or ob.get("obligor_id") or "")
        return {"key": "", "proposal_id": d["proposal_id"], "cif": cif, "group_id": d.get("group_id") or "", "group_name": d.get("group_name") or "",
                "name": d.get("obligor_name") or ob.get("name") or d["proposal_id"], "short": d.get("obligor_name") or "", "cr_number": str(ob.get("cr_number") or ""),
                "city": ob.get("city") or "", "sector": ob.get("sector") or "", "sub_sector": "", "case": "existing" if cif else "new_to_bank",
                "case_label": str(d.get("case_type") or ""), "rm": d.get("rm") or ""}
    return _from_deal_file(str(ref).strip()) if r else None


def _from_deal_file(pid: str) -> dict[str, Any] | None:
    """A deal opened on the desk from uploaded documents (New proposal → Customer documents): the customer is the intake file's
    profile (a demo customer when its CR number matches, keeping this deal's id), else the desk proposal's obligor."""
    prof: dict[str, Any] = {}
    try:
        from backend.dealdesk.intake import service as IS
        f = IS.facts(proposal_id=pid)
        prof = (f or {}).get("profile") or {}
    except Exception:  # noqa: BLE001
        prof = {}
    cr = str(prof.get("cr_number") or "")
    if cr:
        c = next((dict(x) for x in customers() if str(x.get("cr_number")) == cr), None)
        if c is not None:
            if c.get("proposal_id") != pid:
                c.update({"proposal_id": pid, "demo_proposal_id": c.get("proposal_id")})
            return c
        return {"key": "", "proposal_id": pid, "cif": "", "group_id": "", "group_name": "", "name": prof.get("customer_name") or pid,
                "short": prof.get("customer_name") or "", "cr_number": cr, "city": prof.get("city") or "", "sector": prof.get("sector") or "",
                "sub_sector": prof.get("activity") or "", "case": "new_to_bank"}
    try:
        from backend.dealdesk.house_style.bankform import ctx
        D = ctx.load(pid, price=False)
    except Exception:  # noqa: BLE001
        return None
    p = D.p
    cif = str(S.first(p, "cif", "obligor_id", default="") or "")
    return {"key": "", "proposal_id": pid, "cif": cif if not cif.startswith("NEW") else "", "group_id": str(S.first(p, "group_id", default="") or ""),
            "group_name": D.group, "name": D.name, "short": D.name, "cr_number": str(S.first(p, "cr_number", default="") or ""),
            "city": "", "sector": str(S.first(p, "sector", default="") or ""), "sub_sector": "", "case": "existing" if cif else "new_to_bank"}


def _d(x: Any) -> date | None:
    if not x:
        return None
    s = str(x)[:10]
    try:
        if "/" in s:
            dd, mm, yy = s.split("/")
            return date(int(yy), int(mm), int(dd))
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def status_of(doc: dict[str, Any], as_of: str = AS_OF) -> str:
    """received | expired, by the contract's validity rule (expired = printed expiry before demo day; stale = older than N months)."""
    if doc.get("status") in ("missing",):
        return "missing"
    rule = VALIDITY.get(doc.get("doc_type", ""))
    today = _d(as_of) or date.today()
    if rule == "expiry":
        e = _d(doc.get("expiry_date") or (doc.get("fields") or {}).get("expiry_date"))
        return "expired" if e and e < today else "received"
    if isinstance(rule, int):
        f = doc.get("fields") or {}
        i = _d(doc.get("issue_date") or f.get("report_date") or f.get("statement_date") or f.get("as_of") or doc.get("period_to"))
        if i and (today.year - i.year) * 12 + (today.month - i.month) - (1 if today.day < i.day else 0) >= rule:
            return "expired"
    return "received"


def source_label(doc: dict[str, Any]) -> str:
    """'Audited financial statements FY2025 (C1-07)' — how a figure from a document is cited."""
    lab = LABELS.get(doc.get("doc_type", ""), doc.get("title") or doc.get("doc_type", "document"))
    sub = str(doc.get("subject") or "").replace("_", " ").strip()
    if sub and sub.lower() not in lab.lower():
        lab = f"{lab} · {sub.upper() if sub.lower().startswith('fy') else sub.title()}"
    did = str(doc.get("doc_id") or "")
    return f"{lab} ({did})" if did else lab


def _pack(c: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    p = PACKS / str(c.get("folder", "")) / "manifest.json"
    if not p.exists():
        return [], []
    m = json.loads(p.read_text())
    docs = []
    for d in m.get("documents", []):
        if d.get("doc_type") in ("reference_proposal",):
            continue  # the answer is never read
        x = dict(d)
        x["file"] = (d.get("files") or {}).get("docx") or (d.get("files") or {}).get("pdf") or ""
        docs.append(x)
    return docs, list(m.get("missing", []))


def _subject(x: Any) -> str:
    """A checklist line's subject when it names someone or something ("Turki Al-Sawaed", "FY2024"), else '' ("the undersigned", "65.0%")."""
    t = str(x or "").strip()
    if not t or t.lower().startswith(("the ", "(", "company")) or re.fullmatch(r"[\d.,%()\s]+", t):
        return ""
    return t


_DATE_FIELDS = ("issue_date", "report_date", "statement_date", "letter_date", "resolution_date", "as_of", "completed_on", "visit_date",
                "valuation_date", "signed_on", "certified_on", "fiscal_year", "effective_date", "deed_date")


def _intake(c: dict[str, Any]) -> dict[str, Any] | None:
    """Session i's customer file for this customer (backend.dealdesk.intake.service.facts): by the deal it is attached to, else
    the latest intake file whose CR number is the customer's. None when intake has no file for the customer."""
    try:
        from backend.dealdesk.intake import service as IS
    except Exception:  # noqa: BLE001 - intake not on this branch
        return None
    f = None
    try:
        if c.get("proposal_id"):
            f = IS.facts(proposal_id=c["proposal_id"])
        if f is None and c.get("cr_number"):
            for r in IS.recent(40):
                ff = IS.facts(iid=r["intake_id"])
                if ff and str((ff.get("profile") or {}).get("cr_number") or "") == str(c["cr_number"]):
                    f = ff
                    break
    except Exception:  # noqa: BLE001 - an unreadable intake file: fall back to the pack
        return None
    if not f or not f.get("documents"):
        return None
    docs = []
    for code, xs in f["documents"].items():
        for x in xs:
            fl = dict(x.get("fields") or {})
            docs.append({"doc_id": x.get("doc_id"), "doc_type": code, "subject": x.get("subject") or "", "status": x.get("status") or "received",
                         "fields": fl, "file": x.get("file_name") or "", "read_method": x.get("read_method") or "",
                         "issue_date": next((fl[k] for k in _DATE_FIELDS if fl.get(k)), None), "expiry_date": fl.get("expiry_date"),
                         "period_from": fl.get("period_from"), "period_to": fl.get("period_to") or fl.get("fiscal_year")})
    missing = [{"doc_type": m.get("doc_type"), "subject": _subject(m.get("subject")), "why": m.get("reason") or "not in the uploaded documents"}
               for m in f.get("checklist", []) if m.get("status") == "missing"]
    return {"documents": docs, "missing": missing, "intake": {"intake_id": f.get("intake_id"), "checklist": f.get("checklist") or [], "bank": f.get("bank") or {},
                                                              "reconciliation": f.get("reconciliation") or [], "counts": f.get("counts") or {}}}


def bank(c: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The Bank's rows for an existing customer (empty lists for new-to-bank). Each row carries `_src` (relation, row)."""
    pid, cif = c.get("proposal_id"), c.get("cif")
    out: dict[str, list[dict[str, Any]]] = {}
    for r in BANK_DEAL:
        out[r] = S.read(r, proposal_id=pid) if pid else []
    for r in BANK_OBLIGOR:
        rows = S.read(r, obligor_id=cif) if cif else []
        out[r] = rows or (S.read(r, proposal_id=pid) if pid else [])
    out["dd_deal"] = S.read("dd_deal", proposal_id=pid) if pid else []
    gid = c.get("group_id")
    out["b360_entity"] = S.read("b360_entity", group_id=gid) if gid else []
    ents = [e.get("entity_id") for e in out["b360_entity"]]
    out["b360_shareholder"] = S.read("b360_shareholder", entity_id=ents) if ents else []
    out["b360_board"] = S.read("b360_board", entity_id=ents) if ents else []
    out["b360_edge"] = S.read("b360_edge", group_id=gid) if gid else []
    for k in out:
        out[k] = [r for r in out[k] if r]
    return out


def load(ref: str, documents: list[dict[str, Any]] | None = None, missing: list[dict[str, Any]] | None = None,
         customer: dict[str, Any] | None = None, as_of: str = AS_OF, with_bank: bool = True) -> dict[str, Any]:
    c = find(ref) or (dict(customer) if customer else None)
    if c is None:
        raise NotFound(f"no customer file for {ref!r}")
    if customer:
        c.update({k: v for k, v in customer.items() if v not in (None, "")})
    intake = None
    if documents is not None:
        docs, miss, origin = list(documents), list(missing or []), "caller"
    else:
        got = _intake(c)
        if got:
            docs, miss, intake, origin = got["documents"], got["missing"], got["intake"], "intake"
        else:
            (docs, miss), origin = _pack(c), "pack"
    for d in docs:
        d.setdefault("fields", {})
        if origin != "intake":  # intake's checklist engine already set received / expired (one engine per fact)
            d["status"] = status_of(d, as_of)
        d["source"] = source_label(d)
    c["existing"] = bool(c.get("cif")) and str(c.get("case", "existing")).startswith("existing")
    bk = bank(c) if with_bank and c.get("cif") else {}
    return {"customer": c, "as_of": as_of, "documents": docs, "missing": miss, "bank": bk, "origin": origin, "intake": intake}


# ---------------------------------------------------------------- reading helpers used by the writers

def docs(cf: dict[str, Any], doc_type: str, status: str | None = None) -> list[dict[str, Any]]:
    out = [d for d in cf["documents"] if d.get("doc_type") == doc_type and (status is None or d.get("status") == status)]
    return sorted(out, key=lambda d: str(d.get("period_to") or d.get("issue_date") or (d.get("fields") or {}).get("fiscal_year") or ""))


def doc(cf: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    """The latest document of a type (any status: an expired document still says what it printed)."""
    got = docs(cf, doc_type)
    return got[-1] if got else None


def field(cf: dict[str, Any], doc_type: str, name: str, default: Any = None) -> tuple[Any, str]:
    """(value, source) of a printed field from the latest document of a type."""
    d = doc(cf, doc_type)
    if d is None:
        return default, ""
    v = (d.get("fields") or {}).get(name)
    return (default if v in (None, "") else v), d["source"]


def checklist(cf: dict[str, Any]) -> list[dict[str, Any]]:
    """The required documents against what was received (received / expired / missing / not required)."""
    if cf.get("intake") and cf["intake"].get("checklist"):  # session i's checklist engine (one engine per fact)
        return [{"doc_type": x.get("doc_type"), "label": x.get("requirement") or LABELS.get(x.get("doc_type"), x.get("doc_type")), "subject": _subject(x.get("subject")),
                 "status": x.get("status") if x.get("status") in ("received", "expired", "missing") else "received", "doc_id": x.get("doc_ids") or "",
                 "date": "", "expiry": x.get("valid_until") or "", "why": x.get("reason") or ""}
                for x in cf["intake"]["checklist"] if x.get("status") in ("received", "expired", "missing")]
    c = cf["customer"]
    contractor = str(c.get("sector", "")).lower().startswith("construct") or bool(docs(cf, "project_list"))
    secured = bool(docs(cf, "valuation_report") or docs(cf, "title_deed")) or any(
        str(r.get("kind", "")).lower() in ("mortgage", "real estate", "real_estate") for r in cf["bank"].get("dd_security", []))
    out = []
    for t, need in REQUIRED:
        if (need == "contractor" and not contractor) or (need == "secured" and not secured):
            continue
        got = docs(cf, t)
        miss = [m for m in cf.get("missing", []) if m.get("doc_type") == t]
        if got:
            for d in got:
                out.append({"doc_type": t, "label": LABELS.get(t, t), "subject": d.get("subject") or "", "status": d["status"],
                            "doc_id": d.get("doc_id"), "date": d.get("issue_date") or d.get("period_to") or "", "expiry": d.get("expiry_date") or ""})
            for m in miss:
                out.append({"doc_type": t, "label": LABELS.get(t, t), "subject": m.get("subject") or "", "status": "missing", "why": m.get("why", "")})
        else:
            out.append({"doc_type": t, "label": LABELS.get(t, t), "subject": (miss[0].get("subject") if miss else "") or "", "status": "missing",
                        "why": (miss[0].get("why") if miss else "") or "not provided"})
    return out
