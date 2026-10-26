"""R16 d: build every document model of a customer pack from its spec (one builder per document type).

Each builder returns (model, fields, meta): `model` for render.py, `fields` = the printed values in contract units
(SAR units, ISO dates), `meta` = issuer, issue/expiry dates, period.
"""
from __future__ import annotations

import random
from typing import Any

from ops.r16_customers import fin
from ops.r16_customers.doctypes import BY_CODE
from ops.r16_customers.fin import fmt_date as D
from ops.r16_customers.fin import fmt_m as M
from ops.r16_customers.fin import fmt_pct as P
from ops.r16_customers.fin import fmt_sar as S
from ops.r16_customers.fin import sar
from ops.r16_customers.ids import BANK

GOV = "gov"


def _kv(code: str, values: dict[str, Any], amounts: bool = True) -> list[tuple[str, str]]:
    """The Key details block: every non-list field of the type, in registry order, printed. With amounts=False (financial
    statements) the amounts are left to the statement tables, whose row labels are the printed labels."""
    out = []
    for name, label, typ in BY_CODE[code].fields:
        if typ.startswith("list") or name not in values or (not amounts and typ == "sar"):
            continue
        v = values[name]
        if typ == "date":
            pv = D(v)
        elif typ == "sar":
            pv = S(v)
        elif typ == "pct":
            pv = P(v)
        elif typ == "int":
            pv = f"{int(v):,}"
        else:
            pv = str(v)
        out.append((label, pv))
    return out


def _co(sp) -> dict[str, Any]:
    return {"customer_name": sp["co"]["name"], "cr_number": sp["co"]["cr_number"]}


def _company_head(sp) -> tuple[str, list[str]]:
    c = sp["co"]
    return c["name"], [f"CR {c['cr_number']} · VAT {c['vat_number']} · {c['address']}", f"Tel {c['phone']} · {c['email']}"]


# ================================================================================================ KYC / legal
def national_id(sp, p) -> tuple:
    f = {"full_name": p["name"], "id_number": p["id_number"], "nationality": p["nationality"], "date_of_birth": p["dob"],
         "issue_date": p["id_issue"], "expiry_date": p["id_expiry"]}
    m = {"title": "NATIONAL IDENTITY CARD", "subtitle": "Kingdom of Saudi Arabia · Civil Status (fictional specimen)", "style": GOV,
         "issuer": "Civil Status Registry (specimen)", "issuer_lines": ["Identity document copy certified by the customer"],
         "ref": f"Copy provided for account and credit file of {sp['co']['name']}", "fields": _kv("national_id", f),
         "blocks": [{"p": f"Holder: {p['name']}. Role in the company: {p['role']}."}, {"stamp": "TRUE COPY OF ORIGINAL"}]}
    return m, f, {"issuer": m["issuer"], "issue_date": p["id_issue"], "expiry_date": p["id_expiry"]}


def articles(sp) -> tuple:
    c = sp["co"]
    holders = [{"name": h["name"], "id_number": h["id_number"], "nationality": h["nationality"], "shares": h["shares"], "pct": h["pct"]}
               for h in c["shareholders"]]
    mgrs = [{"name": m["name"], "role": m["role"], "powers": m["powers"]} for m in c["managers"]]
    f = {**_co(sp), "legal_form": c["legal_form"], "date_of_incorporation": c["incorporated"], "share_capital": sar(c["capital_mn"]),
         "amendment_date": c["aoa_amended"], "shareholders": holders, "managers": mgrs}
    blocks = [{"h": "Article 1 — Name and form"}, {"p": f"{c['name']}, a {c['legal_form'].lower()} registered in {c['city']}."},
              {"h": "Article 2 — Objects"}, {"p": c["activity"]},
              {"h": "Article 6 — Capital and shareholders"},
              {"p": f"The capital is {M(c['capital_mn'])} divided into {c['shares_total']:,} shares of SAR {c['share_value']:,} each, held as follows:"},
              {"table": {"cols": ["Shareholder", "ID / CR", "Nationality", "Shares", "%"],
                         "rows": [[h["name"], h["id_number"], h["nationality"], f"{h['shares']:,}", P(h["pct"])] for h in holders],
                         "widths": [0.34, 0.18, 0.16, 0.16, 0.16]}},
              {"h": "Article 14 — Management"},
              {"table": {"cols": ["Name", "Role", "Powers"], "rows": [[m["name"], m["role"], m["powers"]] for m in mgrs], "widths": [0.3, 0.25, 0.45]}},
              {"p": c.get("aoa_borrowing_clause", "The managers may borrow from banks and give guarantees in the company's name, within the limits set by the partners' resolution.")},
              {"h": "Amendments"}, {"p": c.get("aoa_amendment_text", f"Last amended on {D(c['aoa_amended'])}.")}]
    m = {"title": "ARTICLES OF ASSOCIATION", "subtitle": f"{c['name']} ({c['legal_form']})", "style": "company",
         "issuer": c["name"], "issuer_lines": [f"Articles as amended on {D(c['aoa_amended'])}", "Notarised copy"],
         "ref": f"CR {c['cr_number']}", "fields": _kv("articles_of_association", f), "blocks": blocks}
    return m, f, {"issuer": c["name"], "issue_date": c["aoa_amended"]}


def cr(sp) -> tuple:
    c = sp["co"]
    f = {**_co(sp), "legal_form": c["legal_form"], "city": c["city"], "activity": c["activity_short"], "issue_date": c["cr_issue"],
         "expiry_date": c["cr_expiry"], "share_capital": sar(c["capital_mn"]),
         "owners": [{"name": h["name"], "pct": h["pct"]} for h in c["shareholders"]],
         "managers": [{"name": m["name"], "role": m["role"]} for m in c["managers"]]}
    m = {"title": "COMMERCIAL REGISTRATION CERTIFICATE", "subtitle": "Main registration (fictional specimen)", "style": GOV,
         "issuer": "Commercial Register (specimen)", "issuer_lines": [f"{c['city']} registry office"], "ref": f"Registration printed on {D(c['cr_print'])}",
         "fields": _kv("commercial_registration", f),
         "blocks": [{"h": "Owners"}, {"table": {"cols": ["Owner", "Share"], "rows": [[h["name"], P(h["pct"])] for h in c["shareholders"]], "widths": [0.7, 0.3]}},
                    {"h": "Managers"}, {"table": {"cols": ["Name", "Role"], "rows": [[x["name"], x["role"]] for x in c["managers"]], "widths": [0.6, 0.4]}},
                    {"stamp": "VALID REGISTRATION"}]}
    return m, f, {"issuer": m["issuer"], "issue_date": c["cr_issue"], "expiry_date": c["cr_expiry"]}


def vat_cert(sp) -> tuple:
    c = sp["co"]
    f = {**_co(sp), "vat_number": c["vat_number"], "effective_date": c["vat_effective"], "filing_frequency": c["vat_frequency"],
         "issue_date": c["vat_cert_issue"]}
    m = {"title": "VAT REGISTRATION CERTIFICATE", "subtitle": "Tax Identification (fictional specimen)", "style": GOV,
         "issuer": "Tax Authority (specimen)", "issuer_lines": ["Value Added Tax registration"], "fields": _kv("vat_certificate", f),
         "blocks": [{"p": f"This certifies that {c['name']} is registered for Value Added Tax with the registration number above, "
                          f"filing {c['vat_frequency'].lower()} returns."}, {"stamp": "REGISTERED"}]}
    return m, f, {"issuer": m["issuer"], "issue_date": c["vat_cert_issue"]}


def zakat(sp) -> tuple:
    c = sp["co"]
    z = c["zakat"]
    f = {**_co(sp), "certificate_number": z["number"], "fiscal_year": z["fy_end"], "issue_date": z["issue"], "expiry_date": z["expiry"]}
    m = {"title": "ZAKAT CERTIFICATE", "subtitle": "Certificate of filing and payment (fictional specimen)", "style": GOV,
         "issuer": "Zakat Authority (specimen)", "issuer_lines": ["Zakat, tax and customs"], "fields": _kv("zakat_certificate", f),
         "blocks": [{"p": f"{c['name']} has filed its zakat return for the year ended {D(z['fy_end'])} and settled the zakat due. "
                          f"This certificate is valid until {D(z['expiry'])}."}, {"stamp": "ZAKAT PAID"}]}
    return m, f, {"issuer": m["issuer"], "issue_date": z["issue"], "expiry_date": z["expiry"]}


def nitaqat(sp) -> tuple:
    c = sp["co"]
    n = c["nitaqat"]
    f = {**_co(sp), "establishment_number": n["establishment"], "nitaqat_band": n["band"], "saudisation_pct": n["rate"],
         "band_threshold_pct": n["threshold"], "total_staff": n["total"], "saudi_staff": n["saudi"], "issue_date": n["issue"], "expiry_date": n["expiry"]}
    m = {"title": "NITAQAT CERTIFICATE", "subtitle": "Saudisation band (fictional specimen)", "style": GOV, "issuer": "Labour Registry (specimen)",
         "issuer_lines": ["Nitaqat programme"], "fields": _kv("nitaqat_certificate", f),
         "blocks": [{"table": {"cols": ["Band", "Minimum Saudisation", "Entity rate", "Headroom"],
                               "rows": [[n["band"], P(n["threshold"]), P(n["rate"]), f"{n['rate'] - n['threshold']:.1f} pp"]], "widths": [0.25] * 4}},
                    {"p": "Bands are reviewed monthly on the average of the last 26 weeks of registered staff."}]}
    return m, f, {"issuer": m["issuer"], "issue_date": n["issue"], "expiry_date": n["expiry"]}


def vat_returns(sp) -> tuple:
    c = sp["co"]
    rows = sp["vat"]
    tot = sum(r["taxable_sales"] for r in rows)
    out_vat = sum(r["output_vat"] for r in rows)
    f = {**_co(sp), "vat_number": c["vat_number"], "period_from": rows[0]["from"], "period_to": rows[-1]["to"],
         "filing_frequency": c["vat_frequency"], "total_taxable_sales": sar(tot), "total_output_vat": sar(out_vat),
         "returns": [{"period": r["period"], "taxable_sales": sar(r["taxable_sales"]), "zero_rated_sales": sar(r["zero_rated"]),
                      "output_vat": sar(r["output_vat"]), "input_vat": sar(r["input_vat"]), "net_vat_due": sar(r["output_vat"] - r["input_vat"]),
                      "filed_on": r["filed_on"]} for r in rows]}
    blocks = [{"h": "Returns filed"},
              {"table": {"cols": ["Period", "Standard-rated sales", "Zero-rated", "Output VAT", "Input VAT", "Net VAT due", "Filed on"],
                         "rows": [[r["period"], S(sar(r["taxable_sales"]), False), S(sar(r["zero_rated"]), False), S(sar(r["output_vat"]), False),
                                   S(sar(r["input_vat"]), False), S(sar(r["output_vat"] - r["input_vat"]), False), D(r["filed_on"])] for r in rows]
                         + [["Total", S(sar(tot), False), S(sar(sum(r["zero_rated"] for r in rows)), False), S(sar(out_vat), False),
                             S(sar(sum(r["input_vat"] for r in rows)), False), S(sar(out_vat - sum(r["input_vat"] for r in rows)), False), ""]],
                         "bold_last": True, "widths": [0.12, 0.17, 0.12, 0.15, 0.15, 0.15, 0.14]}},
              {"p": "Each return was filed and the net VAT paid by the due date (portal acknowledgements on file)."}]
    m = {"title": "VAT RETURN FILINGS — LAST 12 MONTHS", "subtitle": "Portal extract of filed returns", "style": GOV, "issuer": "Tax Authority portal (specimen)",
         "issuer_lines": [f"VAT {c['vat_number']}"], "fields": _kv("vat_returns", f), "blocks": blocks}
    return m, f, {"issuer": m["issuer"], "issue_date": rows[-1]["filed_on"], "period_from": rows[0]["from"], "period_to": rows[-1]["to"]}


# ================================================================================================ bureau
def simah_company(sp) -> tuple:
    c, s = sp["co"], sp["simah_company"]
    fac = s["facilities"]
    f = {**_co(sp), "report_date": s["date"], "report_number": s["number"], "score": s["score"],
         "total_limits": sar(sum(x["limit"] for x in fac)), "total_outstanding": sar(sum(x["outstanding"] for x in fac)),
         "total_overdue": sar(sum(x["overdue"] for x in fac)), "lenders_count": len({x["lender"] for x in fac}),
         "defaults_count": s.get("defaults", 0), "enquiries_6m": s["enquiries"],
         "facilities": [{"lender": x["lender"], "product": x["product"], "limit": sar(x["limit"]), "outstanding": sar(x["outstanding"]),
                         "overdue": sar(x["overdue"]), "status": x["status"], "opened": x["opened"], "remark": x.get("remark", "")} for x in fac]}
    blocks = [{"h": "Credit facilities"},
              {"table": {"cols": ["Lender", "Product", "Limit", "Outstanding", "Overdue", "Status", "Opened", "Remark"],
                         "rows": [[x["lender"], x["product"], S(sar(x["limit"]), False), S(sar(x["outstanding"]), False), S(sar(x["overdue"]), False),
                                   x["status"], D(x["opened"]), x.get("remark", "")] for x in fac],
                         "widths": [0.16, 0.14, 0.11, 0.12, 0.09, 0.11, 0.1, 0.17]}},
              {"h": "Payment history (24 months)"}, {"p": s["history"]},
              {"h": "Enquiries"}, {"p": s.get("enquiry_text", f"{s['enquiries']} enquiries in the last 6 months.")},
              {"h": "Legal and court records"}, {"p": s.get("court", "None recorded.")}]
    m = {"title": "SIMAH COMMERCIAL CREDIT REPORT", "subtitle": c["name"], "style": "bureau", "issuer": "SIMAH credit bureau (specimen extract)",
         "issuer_lines": ["Commercial report · fictional data"], "ref": f"Report {s['number']} dated {D(s['date'])}",
         "fields": _kv("simah_company", f), "blocks": blocks}
    return m, f, {"issuer": m["issuer"], "issue_date": s["date"]}


def simah_consumer(sp, p) -> tuple:
    s = p["simah"]
    fac, gua = s["facilities"], s.get("guarantees", [])
    f = {"full_name": p["name"], "id_number": p["id_number"], "report_date": s["date"], "report_number": s["number"], "score": s["score"],
         "total_outstanding": sar(sum(x["outstanding"] for x in fac)), "total_overdue": sar(sum(x["overdue"] for x in fac)),
         "worst_status_24m": s["worst"],
         "facilities": [{"lender": x["lender"], "product": x["product"], "limit": sar(x["limit"]), "outstanding": sar(x["outstanding"]),
                         "overdue": sar(x["overdue"]), "status": x["status"], "remark": x.get("remark", "")} for x in fac],
         "guarantees": [{"beneficiary": g["beneficiary"], "lender": g["lender"], "amount": sar(g["amount"]), "status": g["status"]} for g in gua]}
    blocks = [{"h": "Credit facilities"},
              {"table": {"cols": ["Lender", "Product", "Limit", "Outstanding", "Overdue", "Status", "Remark"],
                         "rows": [[x["lender"], x["product"], S(sar(x["limit"]), False), S(sar(x["outstanding"]), False), S(sar(x["overdue"]), False),
                                   x["status"], x.get("remark", "")] for x in fac], "widths": [0.18, 0.15, 0.12, 0.13, 0.11, 0.12, 0.19]}},
              {"h": "Guarantees given"},
              {"table": {"cols": ["Guaranteed party", "Lender", "Amount", "Status"],
                         "rows": [[g["beneficiary"], g["lender"], S(sar(g["amount"]), False), g["status"]] for g in gua] or [["None", "", "", ""]],
                         "widths": [0.35, 0.25, 0.2, 0.2]}},
              {"h": "Payment history (24 months)"}, {"p": s["history"]}]
    m = {"title": "SIMAH CONSUMER CREDIT REPORT", "subtitle": p["name"], "style": "bureau", "issuer": "SIMAH credit bureau (specimen extract)",
         "issuer_lines": ["Consumer report · fictional data"], "ref": f"Report {s['number']} dated {D(s['date'])} · consent on file",
         "fields": _kv("simah_consumer", f), "blocks": blocks}
    return m, f, {"issuer": m["issuer"], "issue_date": s["date"]}


def simah_consent(sp) -> tuple:
    c, x = sp["co"], sp["consent"]
    f = {**_co(sp), "signatory": x["by"], "signed_on": x["on"]}
    m = {"title": "CONSENT TO OBTAIN AND SHARE CREDIT INFORMATION (SIMAH)", "style": "form", "issuer": BANK,
         "issuer_lines": ["Corporate Banking · credit information consent"], "fields": _kv("simah_consent", f),
         "blocks": [{"p": f"{c['name']} and its owners and guarantors authorise {BANK} to obtain their credit reports from the credit bureau and "
                          "to share the information of their facilities with the bureau, for the life of the relationship."},
                    {"sig": [(x["by"], x["role"])]}]}
    return m, f, {"issuer": BANK, "issue_date": x["on"]}


# ================================================================================================ financials
_FS_ROWS = [("Revenue", "revenue"), ("Cost of revenue", "cost_of_sales"), ("Gross profit", "gross_profit"),
            ("Operating expenses", "operating_expenses"), ("Operating profit", "operating_profit"), ("Finance cost", "finance_cost"),
            ("Zakat", "zakat"), ("Net profit", "net_profit")]
_BS_ROWS = [("Cash and bank balances", "cash"), ("Trade receivables, net", "trade_receivables"), ("Retention receivables", "retention_receivables"),
            ("Contract assets", "contract_assets"), ("Inventories", "inventory"), ("Due from related parties", "due_from_related"),
            ("Prepayments and other current assets", "other_current_assets"), ("Total current assets", "current_assets"),
            ("Property, plant and equipment", "ppe"), ("Other non-current assets", "other_noncurrent_assets"), ("Total assets", "total_assets"),
            ("Short-term borrowings", "short_term_borrowings"), ("Trade payables", "trade_payables"), ("Due to related parties", "due_to_related"),
            ("Accruals and other current liabilities", "other_current_liabilities"), ("Current portion of long-term borrowings", "current_portion_ltd"),
            ("Total current liabilities", "current_liabilities"), ("Long-term borrowings", "long_term_borrowings"),
            ("Employees' end-of-service benefits", "end_of_service"), ("Total liabilities", "total_liabilities"),
            ("Share capital", "share_capital"), ("Statutory reserve", "statutory_reserve"), ("Retained earnings", "retained_earnings"),
            ("Total equity", "total_equity"), ("Total liabilities and equity", "_tle")]


def _fs_table(rows, cur, prev, cur_label, prev_label, skip_zero=True):
    out = []
    for lab, k in rows:
        cv = cur["total_liabilities"] + cur["total_equity"] if k == "_tle" else cur.get(k, 0.0)
        pv = None if prev is None else (prev["total_liabilities"] + prev["total_equity"] if k == "_tle" else prev.get(k, 0.0))
        if skip_zero and not cv and not pv:
            continue
        out.append([lab, S(sar(cv), False)] + ([S(sar(pv), False)] if prev is not None else []))
    return {"cols": ["SAR", cur_label] + ([prev_label] if prev is not None else []), "rows": out,
            "widths": [0.56, 0.22, 0.22] if prev is not None else [0.66, 0.34]}


def audited_fs(sp, year: str) -> tuple:
    c = sp["co"]
    fs = sp["fs"][year]
    prev_key = {"FY2025": "FY2024", "FY2024": "FY2023"}.get(year)
    prev = sp["fs"].get(prev_key)
    a = sp["audit"][year]
    fy_end = f"{year[2:]}-12-31"
    f = {**_co(sp), "fiscal_year": fy_end, "auditor": a["auditor"], "opinion": a["opinion"], "qawaem_reference": a["qawaem"]}
    for name, _, typ in BY_CODE["audited_fs"].fields:
        if typ == "sar" and name in fs:
            f[name] = sar(fs[name])
    f["depreciation"] = sar(fs.get("depreciation", 0))
    f["operating_cash_flow"] = sar(fs["operating_cash_flow"])
    f["related_party_sales"] = sar(fs.get("related_party_sales", 0.0))
    opinion_text = a.get("opinion_text") or ("In our opinion, the accompanying financial statements present fairly, in all material respects, "
                                               f"the financial position of {c['name']} as at {D(fy_end)} and its financial performance and cash flows "
                                               "for the year then ended in accordance with IFRS as endorsed in the Kingdom.")
    blocks = [{"h": "Independent auditor's report"}, {"p": opinion_text}]
    if a.get("basis"):
        blocks += [{"h2": "Basis for qualified opinion"}, {"p": a["basis"]}]
    blocks += [{"p": f"{a['auditor']}, {a['city']}. Signed by {a['partner']}, licence {a['licence']}, on {D(a['signed'])}."},
               {"pagebreak": 1},
               {"h": "Statement of financial position"}, {"table": _fs_table(_BS_ROWS, fs, prev, D(fy_end), D(f"{prev_key[2:]}-12-31") if prev else "")},
               {"h": "Statement of profit or loss"}, {"table": _fs_table(_FS_ROWS, fs, prev, year, prev_key or "")},
               {"h": "Statement of cash flows (summary)"},
               {"table": {"cols": ["SAR", year], "rows": [["Net profit", S(sar(fs["net_profit"]), False)],
                                                          ["Depreciation and amortisation", S(sar(fs.get("depreciation", 0)), False)],
                                                          ["Working capital changes and other", S(sar(fs["operating_cash_flow"] - fs["net_profit"] - fs.get("depreciation", 0)), False)],
                                                          ["Net cash from operating activities", S(sar(fs["operating_cash_flow"]), False)]],
                          "widths": [0.66, 0.34]}},
               {"pagebreak": 1}, {"h": "Selected notes"}]
    if fs.get("related_party_sales"):
        blocks += [{"table": {"cols": ["Related-party disclosure", "SAR"], "rows": [["Sales to related parties (note)", S(sar(fs["related_party_sales"]), False)]],
                              "widths": [0.66, 0.34]}}]
    for title, text in sp["notes"][year]:
        blocks += [{"h2": title}, {"p": text}]
    m = {"title": f"{c['name'].upper()} — FINANCIAL STATEMENTS {year}", "subtitle": "INDEPENDENT AUDITOR'S REPORT AND STATEMENT OF FINANCIAL POSITION",
         "style": "audit", "issuer": a["auditor"], "issuer_lines": [f"Certified public accountants · {a['city']}", f"Qawaem filing {a['qawaem']}"],
         "ref": f"For the year ended {D(fy_end)}", "fields": _kv("audited_fs", f, amounts=False), "blocks": blocks}
    return m, f, {"issuer": a["auditor"], "issue_date": a["signed"], "period_from": f"{year[2:]}-01-01", "period_to": fy_end}


def inhouse_fs(sp) -> tuple:
    c = sp["co"]
    fs = sp["fs"]["9M2026"]
    f = {**_co(sp), "period_from": "2026-01-01", "period_to": "2026-09-30", "prepared_by": sp["inhouse_by"]}
    for name, _, typ in BY_CODE["inhouse_fs"].fields:
        if typ == "sar" and name in fs:
            f[name] = sar(fs[name])
    blocks = [{"p": "Unaudited management accounts prepared by the company's finance department. Subject to year-end audit adjustments."},
              {"h": "Profit or loss, 1 January – 30 September 2026"}, {"table": _fs_table(_FS_ROWS, fs, None, "9M2026", "")},
              {"h": "Balance sheet at 30 September 2026"}, {"table": _fs_table(_BS_ROWS, fs, None, "30/09/2026", "")}]
    blocks += [{"p": x} for x in sp.get("inhouse_notes", [])]
    m = {"title": "MANAGEMENT ACCOUNTS (UNAUDITED) — 9 MONTHS 2026", "subtitle": c["name"], "style": "company",
         "issuer": c["name"], "issuer_lines": _company_head(sp)[1], "ref": "Period 01/01/2026 – 30/09/2026",
         "fields": _kv("inhouse_fs", f, amounts=False), "blocks": blocks + [{"sig": [(sp["inhouse_by"], "Finance")]}]}
    return m, f, {"issuer": c["name"], "issue_date": sp["inhouse_date"], "period_from": "2026-01-01", "period_to": "2026-09-30"}


# ================================================================================================ bank statements
def bank_statement(sp, acc) -> tuple:
    c = sp["co"]
    txns, monthly = statement_lines(acc)
    tc, td = sum(m["credits"] for m in monthly), sum(m["debits"] for m in monthly)
    f = {**_co(sp), "bank_name": acc["bank"], "account_number": acc["number"], "iban": acc["iban"], "account_type": acc["type"],
         "period_from": "2025-10-01", "period_to": "2026-09-30", "opening_balance": sar(acc["opening"]), "total_credits": sar(tc),
         "total_debits": sar(td), "closing_balance": sar(monthly[-1]["closing"]), "returned_cheques": sum(m["returned"] for m in monthly),
         "monthly": [{"month": m["month"], "credits": sar(m["credits"]), "debits": sar(m["debits"]), "closing_balance": sar(m["closing"]),
                      "avg_balance": sar(m["avg"]), "returned_cheques": m["returned"]} for m in monthly],
         "transactions": [{"date": t["date"], "description": t["desc"], "debit": sar(t["debit"]) if t["debit"] else None,
                           "credit": sar(t["credit"]) if t["credit"] else None, "balance": sar(t["balance"])} for t in txns]}
    blocks = [{"h": "Monthly summary"},
              {"table": {"cols": ["Month", "Credits", "Debits", "Closing balance", "Average balance", "Returned cheques"],
                         "rows": [[m["month"], S(sar(m["credits"]), False), S(sar(m["debits"]), False), S(sar(m["closing"]), False),
                                   S(sar(m["avg"]), False), str(m["returned"])] for m in monthly]
                         + [["Total", S(sar(tc), False), S(sar(td), False), "", "", str(sum(m["returned"] for m in monthly))]],
                         "bold_last": True, "widths": [0.12, 0.18, 0.18, 0.18, 0.18, 0.16]}},
              {"pagebreak": 1}, {"h": "Transactions"},
              {"table": {"cols": ["Date", "Description", "Debit", "Credit", "Balance"],
                         "rows": [[D(t["date"]), t["desc"], S(sar(t["debit"]), False) if t["debit"] else "", S(sar(t["credit"]), False) if t["credit"] else "",
                                   S(sar(t["balance"]), False)] for t in txns], "widths": [0.11, 0.47, 0.14, 0.14, 0.14], "font": 7}}]
    m = {"title": "ACCOUNT STATEMENT", "subtitle": f"{c['name']} · {acc['type']}", "style": "bank" if acc["bank"] == BANK else "other_bank",
         "issuer": acc["bank"], "issuer_lines": [f"Statement of account {acc['number']} · IBAN {acc['iban']}", "Period 01/10/2025 – 30/09/2026"],
         "ref": f"Issued {D(acc['issued'])}", "fields": _kv("bank_statement", f), "blocks": blocks}
    return m, f, {"issuer": acc["bank"], "issue_date": acc["issued"], "period_from": "2025-10-01", "period_to": "2026-09-30"}


def statement_lines(acc) -> tuple[list[dict], list[dict]]:
    """Deterministic transactions per month whose sums equal the account's monthly credit/debit targets. A debit that
    would take the balance below SAR 250k waits for the next receipt (as a treasurer would schedule it)."""
    bal = acc["opening"]
    txns, monthly = [], []
    floor = acc.get("floor", 0.25)
    for i, ym in enumerate(acc["months"]):
        dim = int(fin.month_end(ym)[-2:])
        credits = sorted([(d, desc, a) for desc, a, d in acc["credit_items"][i]])
        debits = sorted([(d, desc, a) for desc, a, d in acc["debit_items"][i]])
        events, pending = [], list(debits)
        for day in range(1, dim + 1):
            for d, desc, a in [c for c in credits if c[0] == day]:
                bal = round(bal + a, 6)
                events.append((day, desc, 0.0, a, bal))
            keep = []
            for d, desc, a in pending:
                if day == dim or (d <= day and bal - a >= floor):
                    bal = round(bal - a, 6)
                    events.append((day, desc, a, 0.0, bal))
                else:
                    keep.append((d, desc, a))
            pending = keep
        start_bal = monthly[-1]["closing"] if monthly else acc["opening"]
        acc_bal, cur, pd_ = 0.0, start_bal, 1
        for day, _, _, _, b in events:
            acc_bal += cur * (day - pd_)
            cur, pd_ = b, day
        acc_bal += cur * (dim - pd_ + 1)
        for day, desc, dr, cr_, b in events:
            txns.append({"date": f"{ym}-{day:02d}", "desc": desc, "debit": dr, "credit": cr_, "balance": b})
        monthly.append({"month": ym, "credits": round(sum(a for _, _, a in credits), 6), "debits": round(sum(a for _, _, a in debits), 6),
                        "closing": round(bal, 6), "avg": round(acc_bal / dim, 6), "returned": acc.get("returned", {}).get(ym, 0)})
    return txns, monthly


# ================================================================================================ letters and lists
def request_letter(sp) -> tuple:
    c, r = sp["co"], sp["request"]
    tot = sum(x["amount"] for x in r["facilities"])
    f = {**_co(sp), "letter_date": r["date"], "addressed_to": f"{BANK}, Corporate Banking", "requested_total": sar(tot),
         "facilities": [{"facility": x["facility"], "amount": sar(x["amount"]), "purpose": x["purpose"]} for x in r["facilities"]],
         "signatory": r["by"], "signatory_role": r["role"]}
    blocks = [{"p": f"Dear Sirs,"}, {"p": r["body"]},
              {"table": {"cols": ["Facility", "Amount (SAR)", "Purpose"], "rows": [[x["facility"], S(sar(x["amount"]), False), x["purpose"]] for x in r["facilities"]]
                         + [["Total", S(sar(tot), False), ""]], "bold_last": True, "widths": [0.35, 0.2, 0.45]}}]
    blocks += [{"p": x} for x in r.get("more", [])]
    blocks += [{"p": "Yours faithfully,"}, {"sig": [(r["by"], r["role"])]}, {"stamp": "COMPANY SEAL"}]
    h, lines = _company_head(sp)
    m = {"title": "REQUEST FOR CREDIT FACILITIES", "style": "letter", "issuer": h, "issuer_lines": lines,
         "ref": f"Ref {r['ref']} · {D(r['date'])}", "fields": _kv("facility_request_letter", f), "blocks": blocks}
    return m, f, {"issuer": c["name"], "issue_date": r["date"]}


def board_resolution(sp) -> tuple:
    c, r = sp["co"], sp["resolution"]
    f = {**_co(sp), "resolution_date": r["date"], "resolution_number": r["number"], "authorised_amount": sar(r["amount"]),
         "authorised_persons": r["persons"]}
    h, lines = _company_head(sp)
    m = {"title": "PARTNERS' RESOLUTION", "subtitle": "Resolution to borrow and give security", "style": "company", "issuer": h, "issuer_lines": lines,
         "ref": f"Resolution {r['number']} · {D(r['date'])}", "fields": _kv("board_resolution", f),
         "blocks": [{"p": r["text"]}, {"sig": [(x["name"], f"Partner ({P(x['pct'])})") for x in c["shareholders"]]}]}
    return m, f, {"issuer": c["name"], "issue_date": r["date"]}


def signatories(sp) -> tuple:
    c, s = sp["co"], sp["signatories"]
    f = {**_co(sp), "as_of": s["as_of"], "signatories": s["rows"]}
    h, lines = _company_head(sp)
    m = {"title": "AUTHORISED SIGNATORIES", "style": "company", "issuer": h, "issuer_lines": lines, "fields": _kv("authorised_signatories", f),
         "blocks": [{"table": {"cols": ["Name", "ID number", "Role", "Limit", "Mode"],
                               "rows": [[x["name"], x["id_number"], x["role"], x["limit"], x["mode"]] for x in s["rows"]], "widths": [0.26, 0.15, 0.2, 0.2, 0.19]}},
                    {"sig": [(c["managers"][0]["name"], c["managers"][0]["role"])]}]}
    return m, f, {"issuer": c["name"], "issue_date": s["as_of"]}


def pnw(sp, g) -> tuple:
    n = g["pnw"]
    ta, tl = sum(a["value"] for a in n["assets"]), sum(x["value"] for x in n["liabilities"])
    f = {"full_name": g["name"], "id_number": g["id_number"], "statement_date": n["date"], "total_assets": sar(ta), "total_liabilities": sar(tl),
         "net_worth": sar(ta - tl), "assets": [{"asset": a["asset"], "description": a["description"], "value": sar(a["value"])} for a in n["assets"]],
         "liabilities": [{"liability": x["liability"], "description": x["description"], "value": sar(x["value"])} for x in n["liabilities"]]}
    m = {"title": "PERSONAL NET WORTH STATEMENT", "subtitle": g["name"], "style": "form", "issuer": BANK, "issuer_lines": ["Guarantor's declaration (bank form)"],
         "ref": f"As at {D(n['date'])}", "fields": _kv("personal_net_worth", f),
         "blocks": [{"h": "Assets"}, {"table": {"cols": ["Asset", "Description", "Value (SAR)"],
                                                "rows": [[a["asset"], a["description"], S(sar(a["value"]), False)] for a in n["assets"]] + [["Total assets", "", S(sar(ta), False)]],
                                                "bold_last": True, "widths": [0.25, 0.5, 0.25]}},
                    {"h": "Liabilities"}, {"table": {"cols": ["Liability", "Description", "Value (SAR)"],
                                                     "rows": [[x["liability"], x["description"], S(sar(x["value"]), False)] for x in n["liabilities"]] + [["Total liabilities", "", S(sar(tl), False)]],
                                                     "bold_last": True, "widths": [0.25, 0.5, 0.25]}},
                    {"p": f"Net worth: {S(sar(ta - tl))}. I declare that the above is true and complete. Values are my own estimates unless a valuation is attached."},
                    {"sig": [(g["name"], "Guarantor")]}]}
    return m, f, {"issuer": g["name"], "issue_date": n["date"]}


def other_bank_offer(sp, ob) -> tuple:
    c = sp["co"]
    tot = sum(x["limit"] for x in ob["facilities"])
    f = {**_co(sp), "bank_name": ob["bank"], "letter_date": ob["offer_date"], "letter_reference": ob["offer_ref"], "total_limits": sar(tot),
         "expiry_date": ob["offer_expiry"], "facilities": [{"facility": x["facility"], "limit": sar(x["limit"]), "pricing": x["pricing"], "tenor": x["tenor"]}
                                                             for x in ob["facilities"]], "security": ob["security"]}
    blocks = [{"p": f"Dear Sirs, we are pleased to confirm the following facilities to {c['name']}:"},
              {"table": {"cols": ["Facility", "Limit (SAR)", "Pricing", "Tenor"], "rows": [[x["facility"], S(sar(x["limit"]), False), x["pricing"], x["tenor"]] for x in ob["facilities"]]
                         + [["Total", S(sar(tot), False), "", ""]], "bold_last": True, "widths": [0.32, 0.18, 0.3, 0.2]}},
              {"h": "Security"}, {"p": ob["security"]}]
    blocks += [{"p": x} for x in ob.get("offer_terms", [])]
    blocks += [{"sig": [(ob["offer_signed"], "Relationship Director")]}]
    m = {"title": "FACILITY OFFER LETTER", "style": "other_bank", "issuer": ob["bank"], "issuer_lines": ["Corporate Banking"],
         "ref": f"Ref {ob['offer_ref']} · {D(ob['offer_date'])}", "fields": _kv("other_bank_offer_letter", f), "blocks": blocks}
    return m, f, {"issuer": ob["bank"], "issue_date": ob["offer_date"], "expiry_date": ob["offer_expiry"]}


def other_bank_stmt(sp, ob) -> tuple:
    rows = ob["statement"]
    f = {**_co(sp), "bank_name": ob["bank"], "statement_date": ob["statement_date"], "total_limits": sar(sum(x["limit"] for x in rows)),
         "total_outstanding": sar(sum(x["outstanding"] for x in rows)),
         "facilities": [{"facility": x["facility"], "limit": sar(x["limit"]), "outstanding": sar(x["outstanding"]), "overdue": sar(x["overdue"]),
                         "maturity": x["maturity"]} for x in rows]}
    m = {"title": "STATEMENT OF FACILITIES", "subtitle": sp["co"]["name"], "style": "other_bank", "issuer": ob["bank"], "issuer_lines": ["Liability statement"],
         "ref": f"As at {D(ob['statement_date'])}", "fields": _kv("other_bank_statement", f),
         "blocks": [{"table": {"cols": ["Facility", "Limit", "Outstanding", "Overdue", "Maturity"],
                               "rows": [[x["facility"], S(sar(x["limit"]), False), S(sar(x["outstanding"]), False), S(sar(x["overdue"]), False), x["maturity"]] for x in rows],
                               "widths": [0.32, 0.17, 0.17, 0.14, 0.2]}}] + [{"p": x} for x in ob.get("statement_notes", [])]}
    return m, f, {"issuer": ob["bank"], "issue_date": ob["statement_date"]}


def rec_ageing(sp) -> tuple:
    a = sp["rec_ageing"]
    rows = a["rows"]
    keys = ("b0_90", "b91_180", "b181_365", "over_365")
    tot = {k: sum(r[k] for r in rows) for k in keys}
    T = sum(tot.values())
    f = {**_co(sp), "as_of": a["as_of"], "total": sar(T), "bucket_0_90": sar(tot["b0_90"]), "bucket_91_180": sar(tot["b91_180"]),
         "bucket_181_365": sar(tot["b181_365"]), "bucket_over_365": sar(tot["over_365"]),
         "by_customer": [{"customer": r["customer"], **{k: sar(r[k]) for k in keys}, "total": sar(sum(r[k] for k in keys))} for r in rows]}
    h, lines = _company_head(sp)
    m = {"title": "RECEIVABLES AGEING", "subtitle": f"As at {D(a['as_of'])}", "style": "company", "issuer": h, "issuer_lines": lines,
         "fields": _kv("receivables_ageing", f),
         "blocks": [{"table": {"cols": ["Customer", "0-90", "91-180", "181-365", "Over 365", "Total"],
                               "rows": [[r["customer"]] + [S(sar(r[k]), False) for k in keys] + [S(sar(sum(r[k] for k in keys)), False)] for r in rows]
                               + [["Total"] + [S(sar(tot[k]), False) for k in keys] + [S(sar(T), False)]],
                               "bold_last": True, "widths": [0.3, 0.14, 0.14, 0.14, 0.14, 0.14]}}] + [{"p": x} for x in a.get("notes", [])]}
    return m, f, {"issuer": sp["co"]["name"], "issue_date": a["as_of"]}


def pay_ageing(sp) -> tuple:
    a = sp["pay_ageing"]
    rows = a["rows"]
    keys = ("b0_90", "b91_180", "over_180")
    tot = {k: sum(r[k] for r in rows) for k in keys}
    T = sum(tot.values())
    f = {**_co(sp), "as_of": a["as_of"], "total": sar(T), "bucket_0_90": sar(tot["b0_90"]), "bucket_91_180": sar(tot["b91_180"]),
         "bucket_over_180": sar(tot["over_180"]),
         "by_supplier": [{"supplier": r["supplier"], **{k: sar(r[k]) for k in keys}, "total": sar(sum(r[k] for k in keys))} for r in rows]}
    h, lines = _company_head(sp)
    m = {"title": "PAYABLES AGEING", "subtitle": f"As at {D(a['as_of'])}", "style": "company", "issuer": h, "issuer_lines": lines,
         "fields": _kv("payables_ageing", f),
         "blocks": [{"table": {"cols": ["Supplier", "0-90", "91-180", "Over 180", "Total"],
                               "rows": [[r["supplier"]] + [S(sar(r[k]), False) for k in keys] + [S(sar(sum(r[k] for k in keys)), False)] for r in rows]
                               + [["Total"] + [S(sar(tot[k]), False) for k in keys] + [S(sar(T), False)]],
                               "bold_last": True, "widths": [0.36, 0.16, 0.16, 0.16, 0.16]}}]}
    return m, f, {"issuer": sp["co"]["name"], "issue_date": a["as_of"]}


def top_cs(sp) -> tuple:
    t = sp["top"]
    f = {**_co(sp), "year": t["year"],
         "customers": [{"name": x["name"], "relationship": x["relationship"], "sales": sar(x["sales"]), "share_pct": x["share"], "terms": x["terms"]} for x in t["customers"]],
         "suppliers": [{"name": x["name"], "country": x["country"], "purchases": sar(x["purchases"]), "share_pct": x["share"], "terms": x["terms"]} for x in t["suppliers"]]}
    h, lines = _company_head(sp)
    m = {"title": "TOP CUSTOMERS AND SUPPLIERS", "subtitle": f"Financial year {t['year']}", "style": "company", "issuer": h, "issuer_lines": lines,
         "fields": _kv("top_customers_suppliers", f),
         "blocks": [{"h": "Top customers"}, {"table": {"cols": ["Customer", "Relationship", "Sales (SAR)", "Share", "Terms"],
                                                       "rows": [[x["name"], x["relationship"], S(sar(x["sales"]), False), P(x["share"]), x["terms"]] for x in t["customers"]],
                                                       "widths": [0.3, 0.18, 0.18, 0.1, 0.24]}},
                    {"h": "Top suppliers"}, {"table": {"cols": ["Supplier", "Country", "Purchases (SAR)", "Share", "Terms"],
                                                       "rows": [[x["name"], x["country"], S(sar(x["purchases"]), False), P(x["share"]), x["terms"]] for x in t["suppliers"]],
                                                       "widths": [0.3, 0.14, 0.2, 0.1, 0.26]}}] + [{"p": x} for x in t.get("notes", [])]}
    return m, f, {"issuer": sp["co"]["name"], "issue_date": t["date"]}


def project_list(sp) -> tuple:
    pl = sp["projects"]
    f = {**_co(sp), "as_of": pl["as_of"],
         "projects": [{"project_id": p["id"], "project": p["name"], "employer": p["employer"], "contract_value": sar(p["value"]), "start": p["start"],
                       "planned_completion": p["completion_shown"], "work_done_pct": p["done_pct"], "billed": sar(p["billed"]), "received": sar(p["received"]),
                       "retention_held": sar(p["retention"]), "status": p["status"]} for p in pl["rows"]]}
    h, lines = _company_head(sp)
    m = {"title": "PROJECT LIST — WORK IN HAND", "subtitle": f"As at {D(pl['as_of'])}", "style": "company", "issuer": h, "issuer_lines": lines,
         "fields": _kv("project_list", f),
         "blocks": [{"table": {"cols": ["Id", "Project", "Employer", "Contract value", "Start", "Completion", "Done", "Billed", "Received", "Retention", "Status"],
                               "rows": [[p["id"], p["name"], p["employer"], S(sar(p["value"]), False), D(p["start"]), D(p["completion_shown"]), P(p["done_pct"], 0),
                                         S(sar(p["billed"]), False), S(sar(p["received"]), False), S(sar(p["retention"]), False), p["status"]] for p in pl["rows"]],
                               "widths": [0.05, 0.15, 0.13, 0.09, 0.07, 0.08, 0.05, 0.09, 0.09, 0.08, 0.12], "font": 6.6}}]
         + [{"p": x} for x in pl.get("notes", [])]}
    return m, f, {"issuer": sp["co"]["name"], "issue_date": pl["as_of"]}


def project_contract(sp, p) -> tuple:
    k = p["contract"]
    f = {**_co(sp), "project_id": f"{p['id']} {p['name']}", "employer": p["employer"], "consultant": p["consultant"], "contract_date": k["date"],
         "contract_value": sar(p["value"]), "advance_pct": k["advance_pct"], "retention_pct": k["retention_pct"], "payment_terms_days": k["pay_days"],
         "start_date": p["start"], "completion_date": p["completion_contract"], "performance_bond_pct": k["pb_pct"]}
    m = {"title": "CONTRACT AGREEMENT (EXTRACT)", "subtitle": p["name"], "style": "letter", "issuer": p["employer"], "issuer_lines": [f"Consultant: {p['consultant']}"],
         "ref": f"Contract {k['number']} dated {D(k['date'])}", "fields": _kv("project_contract", f),
         "blocks": [{"p": x} for x in k["clauses"]] + [{"sig": [(k["employer_sig"], p["employer"]), (k["contractor_sig"], sp["co"]["name"])]}]}
    return m, f, {"issuer": p["employer"], "issue_date": k["date"]}


def payment_cert(sp, p, ipc) -> tuple:
    f = {**_co(sp), "project_id": f"{p['id']} {p['name']}", "certificate_number": ipc["no"], "period_to": ipc["period_to"], "certified_on": ipc["certified"],
         "gross_work_done": sar(ipc["cum_gross"]), "this_certificate_gross": sar(ipc["gross"]), "retention_this": sar(ipc["retention"]),
         "advance_recovery": sar(ipc["advance"]), "net_payable": sar(ipc["net"]), "cumulative_retention": sar(ipc["cum_retention"]), "due_date": ipc["due"]}
    m = {"title": "INTERIM PAYMENT CERTIFICATE", "subtitle": f"{p['name']} · {ipc['no']}", "style": "letter", "issuer": p["consultant"],
         "issuer_lines": [f"Engineer for {p['employer']}"], "ref": f"Work up to {D(ipc['period_to'])} · certified {D(ipc['certified'])}",
         "fields": _kv("payment_certificate", f),
         "blocks": [{"table": {"cols": ["Item", "SAR"], "rows": [["Cumulative work done (gross)", S(sar(ipc["cum_gross"]), False)],
                                                                 ["Less: previously certified", S(sar(ipc["cum_gross"] - ipc["gross"]), False)],
                                                                 ["Gross this certificate", S(sar(ipc["gross"]), False)],
                                                                 ["Less: retention (10%)", S(sar(ipc["retention"]), False)],
                                                                 ["Less: advance recovery", S(sar(ipc["advance"]), False)],
                                                                 ["Net amount payable", S(sar(ipc["net"]), False)]], "widths": [0.7, 0.3], "bold_last": True}},
                    {"p": f"Payable within {p['contract']['pay_days']} days of certification, i.e. by {D(ipc['due'])}. Cumulative retention held: {S(sar(ipc['cum_retention']))}."},
                    {"sig": [(p["engineer"], "The Engineer")]}]}
    return m, f, {"issuer": p["consultant"], "issue_date": ipc["certified"]}


def valuation(sp, col) -> tuple:
    v = col["valuation"]
    f = {"property": col["property"], "owner": col["owner"], "deed_number": col["deed"], "valuer": v["valuer"], "valuation_date": v["date"],
         "market_value": sar(v["mv"]), "forced_sale_value": sar(v["fsv"])}
    m = {"title": "VALUATION REPORT", "subtitle": col["property"], "style": "letter", "issuer": v["valuer"], "issuer_lines": ["Accredited real-estate valuer (fictional)"],
         "fields": _kv("valuation_report", f), "blocks": [{"p": x} for x in v["text"]] + [{"sig": [(v["signed"], "Valuer")]}]}
    return m, f, {"issuer": v["valuer"], "issue_date": v["date"]}


def title_deed(sp, col) -> tuple:
    t = col["deed_doc"]
    f = {"deed_number": col["deed"], "owner": col["owner"], "property": col["property"], "area_sqm": t["area"], "deed_date": t["date"], "encumbrance": t["encumbrance"]}
    m = {"title": "TITLE DEED", "style": GOV, "issuer": "Real Estate Registry (specimen)", "issuer_lines": ["Electronic title deed extract"],
         "fields": _kv("title_deed", f), "blocks": [{"p": t["text"]}]}
    return m, f, {"issuer": m["issuer"], "issue_date": t["date"]}


def insurance(sp, col) -> tuple:
    i = col["insurance"]
    f = {"policy_number": i["number"], "insured": col["owner"], "insurer": i["insurer"], "property": col["property"], "sum_insured": sar(i["sum"]),
         "loss_payee": i["loss_payee"], "issue_date": i["from"], "expiry_date": i["to"]}
    m = {"title": "INSURANCE POLICY SCHEDULE", "style": "letter", "issuer": i["insurer"], "issuer_lines": ["Property all risks"],
         "fields": _kv("insurance_policy", f), "blocks": [{"p": i.get("text", "Property all risks including fire and allied perils.")}]}
    return m, f, {"issuer": i["insurer"], "issue_date": i["from"], "expiry_date": i["to"]}


def site_visit(sp) -> tuple:
    s = sp["site_visit"]
    f = {**_co(sp), "visit_date": s["date"], "visited_by": s["by"], "met_with": s["met"], "premises": s["premises"], "staff_seen": s["staff"],
         "observations": s["summary"]}
    m = {"title": "SITE VISIT REPORT", "style": "bank", "issuer": BANK, "issuer_lines": ["Corporate Banking · Relationship management"],
         "fields": _kv("site_visit_report", f), "blocks": [{"h": "Observations"}, {"b": s["points"]}, {"sig": [(s["by"], "Relationship Manager")]}]}
    return m, f, {"issuer": BANK, "issue_date": s["date"]}


def aml(sp) -> tuple:
    a = sp["aml"]
    f = {**_co(sp), "completed_on": a["date"], "ubos": a["ubos"], "pep_flag": a["pep"], "countries": a["countries"], "cash_intensive": a["cash"],
         "risk_rating": a["rating"]}
    m = {"title": "AML / KYC QUESTIONNAIRE", "style": "form", "issuer": BANK, "issuer_lines": ["Compliance · customer due diligence"],
         "fields": _kv("aml_kyc_questionnaire", f),
         "blocks": [{"h": "Ultimate beneficial owners"}, {"table": {"cols": ["Name", "Ownership", "PEP"], "rows": [[u["name"], P(u["pct"]), u["pep"]] for u in a["ubos"]],
                                                                    "widths": [0.5, 0.25, 0.25]}}] + [{"p": x} for x in a.get("notes", [])]
         + [{"sig": [(a["by"], "Authorised signatory")]}]}
    return m, f, {"issuer": BANK, "issue_date": a["date"]}
