"""Customer 4: Sanad Smart Facility Services Co. (fictional). New-to-bank SME, smaller ticket, thin file.

Twist: clean, growing VAT filings (+59% revenue) but one customer, Rawdat Business Park Management Co., is 62% of FY2025
revenue on a contract ending 30/06/2027 (top-customers list, bank statement receipts, request letter); the owner's
personal SIMAH report shows a credit card 90+ days past due since 08/2026 (the AML questionnaire and request letter say
nothing); Nitaqat Low Green at 23.1% against a 22.9% minimum (one Saudi leaving drops the band); the Zakat certificate
expired on 30/04/2026, the partner's ID expired, FY2024 accounts are compiled (not audited), and several documents are
missing (net-worth statement, resolution, ageing, other bank's offer letter, site visit).
"""
from __future__ import annotations

import random

from ops.r16_customers import common, fin
from ops.r16_customers.ids import BANK, BY_KEY

TIB = "Tihama Investment Bank"
RAWDAT = "Rawdat Business Park Management Co."


def spec() -> dict:
    ids = BY_KEY["c4"]
    co = {**ids, "legal_form": "Limited Liability Company", "incorporated": "2019-03-10", "capital_mn": 1.0, "shares_total": 1_000, "share_value": 1_000,
          "address": "Office 12, Al Ghadir Business Centre, King Abdulaziz Road, Riyadh 13311", "phone": "+966 11 510 3328", "email": "admin@sanad-fm.example",
          "activity": "Facility management: cleaning, soft services, MEP maintenance and security coordination for commercial buildings and business parks.",
          "activity_short": "Facility management services", "cr_issue": "2019-03-10", "cr_expiry": "2027-03-09", "cr_print": "2026-10-12",
          "aoa_amended": "2022-01-16", "vat_effective": "2019-07-01", "vat_frequency": "Quarterly", "vat_cert_issue": "2019-07-08",
          "zakat": {"number": "ZC-2025-0731402", "fy_end": "2024-12-31", "issue": "2025-04-28", "expiry": "2026-04-30"},
          "nitaqat": {"establishment": "1-6630418", "band": "Low Green", "rate": 23.1, "threshold": 22.9, "total": 182, "saudi": 42,
                      "issue": "2026-10-01", "expiry": "2026-12-31"},
          "shareholders": [{"name": "Abdulaziz Saleh Al-Mutlaq", "id_number": "1068823410", "nationality": "Saudi", "shares": 900, "pct": 90.0},
                           {"name": "Fahad Saleh Al-Mutlaq", "id_number": "1074419035", "nationality": "Saudi", "shares": 100, "pct": 10.0}],
          "managers": [{"name": "Abdulaziz Saleh Al-Mutlaq", "role": "General Manager", "powers": "Sole signatory"}],
          "aoa_amendment_text": "Amended on 16/01/2022: entry of Fahad Saleh Al-Mutlaq with 10%."}
    people = [
        {"key": "abdulaziz", "name": "Abdulaziz Saleh Al-Mutlaq", "id_number": "1068823410", "nationality": "Saudi", "dob": "1984-06-11", "id_issue": "2024-02-05",
         "id_expiry": "2034-02-04", "role": "General Manager (90%)", "guarantor": True,
         "simah": {"date": "2026-10-13", "number": "SC-26-8823061", "score": 541, "worst": "90+ days past due (credit card, since 08/2026)",
                   "facilities": [{"lender": "Al Rimal Commercial Bank", "product": "Credit card", "limit": 0.06, "outstanding": 0.0584, "overdue": 0.0384,
                                   "status": "90+ days past due", "remark": "First missed payment 06/2026; 90+ days past due since 08/2026"},
                                  {"lender": TIB, "product": "Auto lease", "limit": 0.21, "outstanding": 0.094, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Sanad Smart Facility Services Co.", "lender": TIB, "amount": 4.0, "status": "Current"}],
                   "history": "Credit card 30 days past due in 06/2026, 60 in 07/2026, 90+ from 08/2026 (SAR 38,400 overdue). Other facilities current."}},
        {"key": "fahad", "name": "Fahad Saleh Al-Mutlaq", "id_number": "1074419035", "nationality": "Saudi", "dob": "1990-09-27", "id_issue": "2016-08-16",
         "id_expiry": "2026-08-15", "role": "Partner (10%)", "guarantor": False},
    ]
    st = fin.statement
    fy23 = st({"revenue": 15.2, "cost_of_sales": 12.1, "operating_expenses": 1.6, "finance_cost": 0.2, "zakat": 0.05, "depreciation": 0.5,
               "cash": 0.9, "trade_receivables": 4.2, "inventory": 0.3, "due_from_related": 0.3, "other_current_assets": 0.6, "ppe": 1.7, "other_noncurrent_assets": 0.2,
               "short_term_borrowings": 1.0, "trade_payables": 1.5, "current_portion_ltd": 0.4, "long_term_borrowings": 0.8, "end_of_service": 0.9,
               "share_capital": 1.0, "statutory_reserve": 0.1, "retained_earnings": 1.9})
    fy24 = st({"revenue": 21.8, "cost_of_sales": 17.0, "operating_expenses": 2.1, "finance_cost": 0.3, "zakat": 0.1, "depreciation": 0.6,
               "cash": 1.2, "trade_receivables": 6.1, "inventory": 0.4, "due_from_related": 0.6, "other_current_assets": 0.8, "ppe": 2.0, "other_noncurrent_assets": 0.2,
               "short_term_borrowings": 1.5, "trade_payables": 1.9, "current_portion_ltd": 0.8, "long_term_borrowings": 1.2, "end_of_service": 1.2,
               "share_capital": 1.0, "statutory_reserve": 0.14, "retained_earnings": 3.16})
    fy25 = st({"revenue": 34.6, "cost_of_sales": 27.3, "operating_expenses": 3.0, "finance_cost": 0.5, "zakat": 0.2, "depreciation": 0.8,
               "cash": 1.9, "trade_receivables": 9.8, "inventory": 0.6, "due_from_related": 1.2, "other_current_assets": 1.1, "ppe": 2.4, "other_noncurrent_assets": 0.2,
               "short_term_borrowings": 2.0, "trade_payables": 3.1, "current_portion_ltd": 0.8, "long_term_borrowings": 1.2, "end_of_service": 1.6,
               "share_capital": 1.0, "statutory_reserve": 0.5, "retained_earnings": 5.9})
    m9 = st({"revenue": 29.1, "cost_of_sales": 23.2, "operating_expenses": 2.5, "finance_cost": 0.5, "zakat": 0.0, "depreciation": 0.7,
             "cash": 1.4, "trade_receivables": 12.9, "inventory": 0.7, "due_from_related": 2.1, "other_current_assets": 1.3, "ppe": 2.6, "other_noncurrent_assets": 0.2,
             "short_term_borrowings": 2.8, "trade_payables": 3.6, "current_portion_ltd": 0.8, "long_term_borrowings": 0.6, "end_of_service": 1.9,
             "share_capital": 1.0, "statutory_reserve": 0.5, "retained_earnings": 8.8})
    m9["months"] = 9
    fy23["operating_cash_flow"] = 1.4
    fy24["operating_cash_flow"] = fin.ocf(fy23, fy24)
    fy25["operating_cash_flow"] = fin.ocf(fy24, fy25)
    m9["operating_cash_flow"] = fin.ocf(fy25, m9)
    fs = {"FY2023": fy23, "FY2024": fy24, "FY2025": fy25, "9M2026": m9}
    audit = {"FY2025": {"auditor": "Al Wafa Chartered Accountants", "opinion": "Unqualified", "qawaem": "QW-2026-1010712290", "city": "Riyadh",
                        "partner": "Turki Al-Harthi", "licence": "602", "signed": "2026-05-24",
                        "opinion_text": "In our opinion, the financial statements present fairly, in all material respects, the financial position of Sanad Smart "
                                        "Facility Services Co. as at 31/12/2025 and its financial performance and cash flows for the year then ended in accordance "
                                        "with IFRS for SMEs as endorsed in the Kingdom. Other matter: the comparative figures for 2024 were compiled and not audited."}}
    notes = {"FY2025": [("Note 6 — Revenue and concentration", f"Revenue from {RAWDAT} SAR 21,452,000 (62%) under a facility-management contract "
                                                                 "expiring on 30/06/2027 (2024: 58%)."),
                        ("Note 8 — Due from shareholder", "Current account of the majority shareholder SAR 1,200,000 (2024: 600,000), unsecured, no fixed terms."),
                        ("Note 11 — Borrowings", f"SME term loan from {TIB} SAR 2,000,000 (current 800,000) and short-term Murabaha SAR 2,000,000, guaranteed "
                                                 "by the majority shareholder.")]}
    rnd = random.Random("c4-vat")
    q = [9.9] + fin.series(29.1, 3, rnd, trend=0.1, noise=0.04)
    vat = []
    for (lab, fr, to), r in zip([("Q4 2025", "2025-10-01", "2025-12-31"), ("Q1 2026", "2026-01-01", "2026-03-31"), ("Q2 2026", "2026-04-01", "2026-06-30"),
                                 ("Q3 2026", "2026-07-01", "2026-09-30")], q):
        ts = round(r * (1 + 0.02 * (rnd.random() - 0.5)), 3)
        vat.append({"period": lab, "from": fr, "to": to, "taxable_sales": ts, "zero_rated": 0.0, "output_vat": round(0.15 * ts, 3),
                    "input_vat": round(0.15 * ts * rnd.uniform(0.28, 0.34), 3), "filed_on": fin.add_days(to, 19)})
    gross = sum(v["taxable_sales"] for v in vat) * 1.15
    coll = fin.series(gross * 0.94, 12, random.Random("c4-coll"), trend=0.25, noise=0.07, nd=6)
    mlist = fin.months("2025-10", 12)
    r2 = random.Random("c4-stmt")
    cr = common.credit_items(coll, [(f"{RAWDAT} — monthly invoice", 8, 62), ("Al Ghadir Business Centre Owners Association", 14, 12),
                                    ("Other commercial clients — collections", 21, 26)], r2, spread=0.2)
    lay = [("Payroll transfer (WPS)", 0.58, 27), ("GOSI contribution", 0.05, 15), ("Subcontractors and materials", 0.17, 12), ("VAT payment (quarterly)", 0.05, 28),
           ("Office rent and vehicles", 0.06, 3), ("SME loan instalment and profit", 0.03, 1), ("Transfer to shareholder (personal account)", 0.06, 20)]
    acc = {"bank": TIB, "number": "077-6630418-1", "iban": "SA5885000000776630418100", "type": "Current account (main operating)", "opening": 1.3,
           "issued": "2026-10-07", "months": mlist, "credit_items": cr, "debit_items": common.debit_items(cr, 1.3, 1.25, lay, r2), "returned": {}, "floor": 0.08}
    simah = {"date": "2026-10-13", "number": "SB-26-3302255", "score": 671, "enquiries": 1,
             "facilities": [{"lender": TIB, "product": "SME term loan", "limit": 4.0, "outstanding": 1.4, "overdue": 0.0, "status": "Current", "opened": "2023-05-01"},
                            {"lender": TIB, "product": "Short-term Murabaha", "limit": 3.0, "outstanding": 2.8, "overdue": 0.0, "status": "Current", "opened": "2024-09-15"}],
             "history": "No delinquency on the company's facilities in the last 24 months.", "enquiry_text": f"1 enquiry in the last 6 months: {BANK} (10/2026)."}
    req = {"date": "2026-10-11", "ref": "SSFS/GM/2026/19", "by": "Abdulaziz Saleh Al-Mutlaq", "role": "General Manager",
           "body": "Our revenue grew 59% in 2025 and continues to grow in 2026. We are bidding for the renewal and extension of our main contract and for two "
                   "new business parks, and request:",
           "facilities": [{"facility": "Overdraft", "amount": 3.0, "purpose": "Payroll and working capital"},
                          {"facility": "Letters of guarantee (bid and performance)", "amount": 5.0, "purpose": "Tenders and contract performance bonds"}],
           "more": ["Our customers are reputable business-park operators and pay monthly. We offer the personal guarantee of the undersigned."]}
    top = {"year": 2025, "date": "2026-10-10",
           "customers": [{"name": RAWDAT, "relationship": "Third party", "sales": 21.452, "share": 62.0, "terms": "30 days; contract to 30/06/2027"},
                         {"name": "Al Ghadir Business Centre Owners Association", "relationship": "Third party", "sales": 4.152, "share": 12.0, "terms": "30 days"},
                         {"name": "Other commercial clients (11)", "relationship": "Third parties", "sales": 8.996, "share": 26.0, "terms": "30-60 days"}],
           "suppliers": [{"name": "Manpower subcontractors (3)", "country": "KSA", "purchases": 3.9, "share": 41.0, "terms": "30 days"},
                         {"name": "Cleaning materials and tools", "country": "KSA", "purchases": 2.1, "share": 22.0, "terms": "cash / 30 days"}]}
    aml = {"date": "2026-10-11", "by": "Abdulaziz Saleh Al-Mutlaq", "pep": "No", "countries": "KSA only", "cash": "No", "rating": "Low",
           "ubos": [{"name": "Abdulaziz Saleh Al-Mutlaq", "pct": 90.0, "pep": "No"}, {"name": "Fahad Saleh Al-Mutlaq", "pct": 10.0, "pep": "No"}],
           "notes": ["Customer declares no adverse credit history of the company or its owners."]}
    return {"key": "c4", "co": co, "people": people, "fs": fs, "audit": audit, "notes": notes, "inhouse_by": "Ahmed Fathi Saber", "inhouse_date": "2026-10-09",
            "vat": vat, "accounts": [acc], "simah_company": simah, "consent": {"by": "Abdulaziz Saleh Al-Mutlaq", "role": "General Manager", "on": "2026-10-11"},
            "request": req, "other_banks": [], "top": top, "aml": aml, "collateral": [],
            "missing": [{"doc_type": "audited_fs", "subject": "fy2024", "why": "FY2024 accounts compiled, not audited"},
                        {"doc_type": "simah_consumer", "subject": "fahad_saleh_al_mutlaq", "why": "Partner's report not obtained (consent not signed)"},
                        {"doc_type": "personal_net_worth", "subject": "abdulaziz_saleh_al_mutlaq", "why": "Not provided"},
                        {"doc_type": "board_resolution", "subject": None, "why": "Not provided"},
                        {"doc_type": "authorised_signatories", "subject": None, "why": "Not provided"},
                        {"doc_type": "receivables_ageing", "subject": None, "why": "Not provided"},
                        {"doc_type": "payables_ageing", "subject": None, "why": "Not provided"},
                        {"doc_type": "other_bank_offer_letter", "subject": "tihama_investment_bank", "why": "Not provided"},
                        {"doc_type": "other_bank_statement", "subject": "tihama_investment_bank", "why": "Not provided"},
                        {"doc_type": "site_visit_report", "subject": None, "why": "Visit not yet done"}],
            "facts": {"rev12": round(sum(q), 3)}}


def bank(sp: dict) -> dict:
    pid = "R16-C4"
    limits = [("L0", "", 0, "Total facilities", "", 0, 0.0, 0.0, 8.0, None, None, "", None, None, "", "", "", ""),
              ("S1", "L0", 1, "Overdraft", "OD", 1, 0.0, 0.0, 3.0, 0.0, None, "3M SAIBOR", 3.00, 7.00, "12 months", "On demand", "", ""),
              ("S2", "L0", 1, "Letters of guarantee (bid and performance)", "LG", 0, 0.0, 0.0, 5.0, 10.0, 1.00, "", None, None, "Up to 24 months", "", "", "")]
    ge = [{"entity_name": "Sanad Smart Facility Services Co. (no group entities)", "funded_existing_mn": 0.0, "total_existing_mn": 0.0,
           "funded_proposed_mn": 3.0, "total_proposed_mn": 8.0, "outstanding_mn": 0.0}]
    return {"cif": "", "proposal_id": pid, "unit": "SME Banking — Central Region", "branch": "Riyadh King Abdulaziz Road Branch", "rm": "Hind Al-Subaie",
            "ro": "Nawaf Al-Otaibi", "opened": "", "industry_code": "N8110 — Combined facilities support activities", "purpose_code": "WC-03 SME working capital",
            "collateral_code": "PG — Personal guarantee", "rating_existing": "—", "rating_proposed": "BB", "review_date": "2027-10-31",
            "limits": common.limit_rows(pid, limits), "group_exposure": ge, "conduct": [], "accounts": []}


def proposal_text(sp: dict, b: dict) -> dict:
    fs = sp["fs"]
    f24, f25, m9 = fs["FY2024"], fs["FY2025"], fs["9M2026"]
    pct = lambda a, t: 100 * a / t
    acc = sp["accounts"][0]
    raw = sum(a for it in acc["credit_items"] for d, a, _ in it if d.startswith(RAWDAT))
    tot = sum(a for it in acc["credit_items"] for d, a, _ in it)
    to_sh = sum(a for it in acc["debit_items"] for d, a, _ in it if "shareholder" in d)
    payroll = sum(a for it in acc["debit_items"] for d, a, _ in it if "Payroll" in d)
    vat12 = sum(v["taxable_sales"] for v in sp["vat"])
    dso25, dso24, dso9 = 365 * f25["trade_receivables"] / f25["revenue"], 365 * f24["trade_receivables"] / f24["revenue"], 273 * m9["trade_receivables"] / m9["revenue"]
    drawn24 = fs["FY2023"]["total_equity"] + f24["net_profit"] - f24["total_equity"]
    drawn25 = f24["total_equity"] + f25["net_profit"] - f25["total_equity"]
    adj_nw = m9["total_equity"] - m9["due_from_related"]
    tib_out = 1.4 + 2.8
    nit = sp["co"]["nitaqat"]
    P = {"header": {"related": "No", "date": "2026-10-14", "type": "New (SME)"}, "cfr": "CFR/SME/2026/1187", "unit_head": "Reem Al-Shehri",
         "action": "Approve new SME facilities of SAR 8.0m to Sanad Smart Facility Services Co. (new to bank): overdraft SAR 3.0m and letters of guarantee SAR 5.0m "
                   "(bid and performance) for the renewal of its main contract and two business-park tenders. Funded SAR 3.0m; facilities at "
                   f"{TIB} (SAR 7.0m) stay in place.",
         "fees": "Arrangement fee SAR 20,000; LG issuance SAR 500 per LG.",
         "security": ["All limits: personal guarantee of Abdulaziz Saleh Al-Mutlaq (90% shareholder); net-worth statement not provided.",
                      "All limits: promissory note SAR 8.0m signed by the General Manager.",
                      "LGs: 10% cash margin per LG, held in a blocked account."],
         "tnc": ["Overdraft for payroll and operating expenses; no transfers to shareholders from the overdraft; reviewed annually.",
                 "LGs for facility-management tenders and contracts in the Kingdom only; single LG not above SAR 2.5m; validity not beyond 24 months plus 3 months claim period.",
                 f"Route the company's collections through the Bank within 3 months, not less than SAR 2.5m a month (12-month credits at {TIB} SAR {tot:,.1f}m).",
                 "Payroll (WPS) for all 182 staff through the Bank within 3 months.",
                 "Audited financial statements within 120 days of year end; half-yearly management accounts within 60 days."],
         "references": ["References: credit file request CFR/SME/2026/1187 (14/10/2026); customer's letter SSFS/GM/2026/19 (11/10/2026)."],
         "background": ["Sanad Smart Facility Services Co. (CR 1010712290, Riyadh, CR valid to 09/03/2027), LLC incorporated 10/03/2019, capital SAR 1.0m; "
                        "Abdulaziz Saleh Al-Mutlaq 90% (General Manager, sole signatory), Fahad Saleh Al-Mutlaq 10% (since 16/01/2022). No group entities.",
                        f"Facility management for business parks and commercial buildings (cleaning, soft services, MEP maintenance); 182 staff, of which "
                        f"{nit['saudi']} Saudi (Nitaqat Low Green, {nit['rate']:.1f}% vs {nit['threshold']:.1f}%). VAT filed quarterly since 01/07/2019.",
                        f"Customers as per business (2025): {RAWDAT} 62.0% (30 days; contract to 30/06/2027), Al Ghadir Business Centre Owners Association 12.0%, "
                        "11 other clients 26.0% (30-60 days). Suppliers: 3 manpower subcontractors 41.0%, cleaning materials 22.0%."],
         "shareholders": [["Abdulaziz Saleh Al-Mutlaq (GM)", "1984", "Saudi", "90.0%", "Yes"], ["Fahad Saleh Al-Mutlaq", "1990", "Saudi", "10.0%", "Yes"]],
         "relationship": [f"New to bank; account to be opened on approval. Banks with {TIB} (SME term loan limit SAR 4.0m, outstanding SAR 1.4m; Murabaha SAR 3.0m, "
                          f"outstanding SAR 2.8m; SIMAH 13/10/2026, no delinquency in 24 months).",
                          f"{TIB} statement Oct 2025 – Sep 2026: credits SAR {tot:,.1f}m, payroll SAR {payroll:,.1f}m, no returned cheques."],
         "justification": [f"Revenue SAR {f25['revenue']:,.1f}m in FY2025 (PY {f24['revenue']:,.1f}m, +{100 * (f25['revenue'] / f24['revenue'] - 1):.0f}%) and SAR "
                           f"{m9['revenue']:,.1f}m in 9M2026; VAT standard-rated sales of the last 4 quarters SAR {vat12:,.1f}m.",
                           "The LG line supports the renewal of the main contract (bid due early 2027 as per RM) and two new tenders; payroll of 182 staff comes to the Bank. "
                           "We recommend approval."]}
    P["credit"] = [
        ("Relationship and other banks", [
            f"New to bank. {TIB} is the only lender: limits SAR 7.0m, outstanding SAR {tib_out:.1f}m (SIMAH company report 13/10/2026, score 671, no overdue), "
            f"guaranteed by the owner (SAR 4.0m). {TIB}'s offer letter and facility statement were not provided; the Murabaha is {100 * 2.8 / 3.0:.0f}% utilised. "
            f"With the request, bank lines would total SAR 15.0m = {15.0 / m9['total_equity']:.1f}x net worth (SAR {m9['total_equity']:,.1f}m at 30/09/2026).",
            f"The {TIB} account received SAR {tot:,.1f}m in 12 months ({tot / 1.15:,.1f}m excluding VAT, {100 * tot / 1.15 / vat12:.0f}% of VAT-filed sales); no returned cheques."]),
        ("Concentration", [
            f"<u>{RAWDAT} is 62% of FY2025 revenue</u> (SAR 21.5m; 2024: 58%) under a contract expiring on 30/06/2027 (audited Note 6); it paid SAR {raw:,.1f}m "
            f"of the SAR {tot:,.1f}m received in the {TIB} account in the 12 months to 09/2026 ({100 * raw / tot:.0f}%). The LG line is mainly for the renewal of "
            "that same contract: if it is not renewed, revenue falls by about 62% from 07/2027. The request letter presents the customers as 'reputable business-park "
            "operators' and does not name Rawdat."]),
        ("Owner's credit record (SIMAH)", [
            "The owner's SIMAH consumer report (13/10/2026, score 541) shows <u>a credit card at Al Rimal Commercial Bank 90+ days past due since 08/2026</u> "
            "(SAR 38,400 overdue of SAR 58,400 outstanding; 30 days in 06/2026, 60 in 07/2026). The AML questionnaire (11/10/2026) declares 'no adverse credit "
            "history of the company or its owners'. The amount is small; the non-disclosure and the guarantor's liquidity are not: the company transferred "
            f"SAR {to_sh:,.1f}m to the owner's personal account in 12 months and the amount due from him rose to SAR {m9['due_from_related']:,.1f}m at 30/09/2026 "
            f"(FY2025 {f25['due_from_related']:,.1f}m; FY2024 {f24['due_from_related']:,.1f}m). The partner's SIMAH report was not obtained (consent not signed).",
            {"table": {"cols": ["Bureau (SIMAH)", "Limits", "Outstanding", "Overdue", "Score", "Status"],
                       "rows": [["Sanad Smart Facility Services Co.", "7.00", "4.20", "0.00", "671", "Current, 24 months"],
                                ["Abdulaziz Saleh Al-Mutlaq (guarantor)", "0.27", "0.15", "0.04", "541", "Credit card 90+ DPD since 08/2026"],
                                ["Fahad Saleh Al-Mutlaq", "—", "—", "—", "—", "Not provided (consent not signed)"]],
                       "widths": [0.32, 0.1, 0.12, 0.1, 0.08, 0.28], "font": 7}}]),
        ("Saudisation", [
            f"Nitaqat Low Green at {nit['rate']:.1f}% against a {nit['threshold']:.1f}% minimum ({nit['saudi']} Saudis of {nit['total']} staff, certificate 01/10/2026): "
            f"one Saudi leaving ({nit['saudi'] - 1} of {nit['total'] - 1} = {100 * (nit['saudi'] - 1) / (nit['total'] - 1):.1f}%) or two more non-Saudi hires "
            f"({nit['saudi']} of {nit['total'] + 2} = {100 * nit['saudi'] / (nit['total'] + 2):.1f}%) drops the company to Yellow, which restricts visas and the new "
            "tenders' manpower."]),
        ("Financials", [{"table": _fin(sp)},
                        [f"Revenue SAR {f25['revenue']:,.1f}m in FY2025 (PY {f24['revenue']:,.1f}m, +{100 * (f25['revenue'] / f24['revenue'] - 1):.1f}%); 9M2026 SAR "
                         f"{m9['revenue']:,.1f}m, annualised SAR {m9['revenue'] / 9 * 12:,.1f}m (+{100 * (m9['revenue'] / 9 * 12 / f25['revenue'] - 1):.1f}%). FY2024 figures "
                         "are compiled, not audited (auditor's other-matter paragraph of the FY2025 report, signed 24/05/2026).",
                         f"Gross margin {pct(f25['gross_profit'], f25['revenue']):.1f}% (PY {pct(f24['gross_profit'], f24['revenue']):.1f}%), net margin "
                         f"{pct(f25['net_profit'], f25['revenue']):.1f}% (PY {pct(f24['net_profit'], f24['revenue']):.1f}%).",
                         f"<u>Profit is not turning into cash</u>: receivables SAR {m9['trade_receivables']:,.1f}m at 30/09/2026 (FY2025 {f25['trade_receivables']:,.1f}m), "
                         f"DSO {dso9:.0f} days (FY2025 {dso25:.0f}, FY2024 {dso24:.0f}) against 30-day terms and 'monthly-paying' customers; operating cash flow SAR "
                         f"{f25['operating_cash_flow']:,.1f}m in FY2025 (PY {f24['operating_cash_flow']:,.1f}m) and SAR {m9['operating_cash_flow']:,.1f}m in 9M2026 against net "
                         f"profit SAR {m9['net_profit']:,.1f}m. Receivables ageing not provided.",
                         f"Equity movements imply distributions of SAR {drawn24:,.1f}m (2024) and SAR {drawn25:,.1f}m (2025) not shown as dividends; not explained.",
                         f"If the amount due from the shareholder (SAR {m9['due_from_related']:,.1f}m) is netted off, adjusted net worth is SAR {adj_nw:,.1f}m and adjusted "
                         f"leverage {m9['total_liabilities'] / adj_nw:.2f}x (reported {m9['total_liabilities'] / m9['total_equity']:.2f}x); the SAR 8.0m ask is "
                         f"{8.0 / adj_nw:.1f}x adjusted net worth."]]),
        ("Effects of the current market situation", [
            f"Payroll is {100 * payroll / tot:.0f}% of the account's outflows; Saudisation fees and the Low Green margin above make labour cost the main sensitivity. "
            "The two new business-park tenders are as per business; tender documents, values and dates were not provided."]),
        ("Exceptions and other observations", [[
            "Exception: single customer above 50% of revenue (62%) for an unsecured SME line; business conveys the contract will be renewed, no evidence provided.",
            "Exception: personal guarantee without a net-worth statement; guarantor with a 90+ DPD record.",
            "Expired: Zakat certificate (valid until 30/04/2026; FY2025 certificate not provided); ID of the partner Fahad Saleh Al-Mutlaq (expired 15/08/2026).",
            f"Not provided: audited FY2024 accounts, owner's net-worth statement, partners' resolution, authorised signatories, receivables and payables ageing, {TIB}'s "
            "offer letter and statement, the partner's SIMAH report; site visit not yet done.",
            "What business says vs what credit could verify: 'customers pay monthly' (DSO 121 days); 'no adverse credit history' (owner 90+ DPD); "
            "'reputable business-park operators' (one operator = 62%)."]])]
    P["strengths"] = [f"Revenue +{100 * (f25['revenue'] / f24['revenue'] - 1):.0f}% in FY2025 confirmed by 4 quarterly VAT filings (SAR {vat12:,.1f}m) and statement receipts.",
                      f"Company bureau clean: {TIB} limits SAR 7.0m, no overdue in 24 months; interest cover {f25['ebitda'] / f25['finance_cost']:.1f}x (FY2025).",
                      f"Low capital intensity: fixed assets SAR {m9['ppe']:,.1f}m = {pct(m9['ppe'], m9['total_assets']):.0f}% of total assets."]
    P["recommendation_lead"] = ("Credit division supports <u>a smaller, partly secured facility of SAR 6.5m</u> (requested SAR 8.0m) after the gaps below are closed: "
                                "one customer at 62%, an undisclosed delinquency of the guarantor and DSO of 121 days do not support an unsecured overdraft of SAR 3.0m.")
    P["recommendation"] = ["Letters of guarantee SAR 5.0m against 25% cash margin (requested 10%), for the Rawdat contract renewal and the two tenders; single LG not above SAR 2.5m.",
                           "Overdraft SAR 1.5m (requested 3.0m) at 3M SAIBOR + 3.00% (floor 7.00%) against assignment of the Rawdat contract proceeds to an account with the Bank.",
                           "Total SAR 6.5m (funded SAR 1.5m); personal guarantee of Abdulaziz Saleh Al-Mutlaq; promissory note SAR 6.5m.",
                           "Approval authority: SME Credit Manager."]
    P["conditions"] = ["Prior to limit loading: credit card settled, with Al Rimal Commercial Bank's clearance letter and an updated SIMAH report.",
                       "Prior to limit loading: Zakat certificate for FY2025; the partner's valid ID; owner's net-worth statement not older than 3 months.",
                       "Prior to limit loading: partners' resolution, authorised signatories, receivables ageing at 30/09/2026, the partner's SIMAH consent and report.",
                       f"Prior to limit loading: {RAWDAT}'s acknowledgement of the assignment and of the Bank's account for payments.",
                       "Prior to limit loading: RM site visit report.",
                       "Undertaking: no transfers to the shareholder while facilities are outstanding; due from shareholder repaid or capitalised by 31/03/2027.",
                       "Monitoring: Nitaqat band checked monthly by the RM; Rawdat renewal status reported by 31/03/2027; no LG beyond 30/06/2027 for Rawdat unless renewed."]
    P["analyst"], P["vp"], P["authority"] = "Sara Al-Dosari", "Reem Al-Shehri", "SME Credit Manager"
    P["ask_summary"] = {"one_line": "New SME facilities SAR 8m: overdraft 3m + LGs 5m.", "requested_total_sar": 8_000_000, "new_money_sar": 8_000_000,
                        "credit_recommends_total_sar": 6_500_000}
    return P


def _fin(sp):
    from ops.r16_customers.proposal import fin_table
    return fin_table(sp)


ASK = f"""# Customer 4 — Sanad Smart Facility Services Co. (new-to-bank SME; optional Part A, shows the checklist gaps)

**Who:** new-to-bank Riyadh facility-management SME (CR 1010712290). **Case:** small ticket, thin file.

## Upload

Everything in `pdf/` (or `word/`, or the photos in `images/`). The checklist should show **expired**: Zakat certificate
(30/04/2026), the partner's national ID (15/08/2026); **missing**: audited FY2024, net-worth statement, resolution,
signatories, ageing, {TIB}'s offer letter and statement, the partner's SIMAH report, site visit.

## The ask (chat box)

> New SME customer Sanad Smart Facility Services: overdraft SAR 3m and LGs SAR 5m for tenders and the renewal of their main contract.

## RM notes

> Fast-growing, revenue up 59% in 2025, VAT filings clean. Main client is Rawdat Business Park, contract renewal bid due early 2027. Owner Abdulaziz is hands-on; will move payroll (182 staff) to us.

## What credit will find (ANSWER_KEY.md §C4)

{RAWDAT} = 62% of revenue on a contract ending 30/06/2027; owner's credit card 90+ days past due (not disclosed);
Nitaqat 0.2 points above the band floor; expired Zakat certificate and partner ID; many documents missing.
Recommendation: SAR 6.5m (LG 5m at 25% margin, OD 1.5m against assigned Rawdat proceeds) after the gaps close.
"""

ANSWER = f"""## C4 — Sanad Smart Facility Services Co. (new-to-bank SME, thin file)

**The story a committee would debate:** clean, fast growth confirmed by VAT, on one customer and one owner.

| # | Twist | Where it is found (join) | What the credit comments say |
|---|---|---|---|
| 1 | Single customer 62% | top customers list × audited FY2025 Note 6 (contract to 30/06/2027) × {TIB} statement (Rawdat receipts ≈ 62% of credits) × request letter ("reputable business-park operators") | the LG is for renewing that same contract |
| 2 | Owner's undisclosed delinquency | owner's SIMAH consumer report (credit card 90+ DPD since 08/2026, SAR 38,400; score 541) × AML questionnaire ("no adverse credit history") × statement (transfers to the shareholder) × due from shareholder 0.6 → 1.2 → 2.1m | settle and clear before loading |
| 3 | Nitaqat at the edge | Nitaqat certificate (Low Green 23.1% vs 22.9%; 42 of 182) | one Saudi leaving or two non-Saudi hires → Yellow |
| 4 | Profit not turning into cash | audited FY2025 / in-house 9M2026 (DSO 103 → 121 days vs 30-day terms; OCF 1.9m, 0.2m in 9M2026) × request letter ("pay monthly") | ageing required before loading |
| 5 | Thin file | checklist: Zakat expired 30/04/2026; partner's ID expired 15/08/2026; FY2024 compiled only (auditor's other matter); 10 documents missing (manifest `missing`) | conditions precedent |

**Reference recommendation** (`c4_sanad_facility/reference/reference_proposal.pdf`): SAR 6.5m — LG 5.0m at 25% cash margin, OD 1.5m
against assignment of the Rawdat proceeds; CPs: card settled and cleared, Zakat FY2025, valid ID, PNW, resolution, signatories,
ageing, partner's SIMAH; no transfers to the shareholder.
"""
