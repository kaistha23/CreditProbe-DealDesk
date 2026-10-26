"""Customer 1: Dar Al Naseem Medical Supplies Co. (fictional). Existing customer, renewal + increase (Part A).

Twist: audited revenue rose 38% in FY2025 but credits into the Bank's accounts rose only 9% (CY2025 vs CY2024); a new
distributor, Al Tayf Healthcare Trading Est., took 31% of FY2025 sales, is owned by a shareholder's son (disclosed only as
"an entity owned by a relative of a shareholder" in the audited notes, listed as a "third party" in the top-customers list
and the request letter) and pays slowly (62% of receivables, 59% of it over 90 days); a sister company, Naseem Lab Systems
Co., was classified substandard at another bank in 07/2026 (guarantor's SIMAH report, the Bank's group data), not disclosed;
the warehouse valuation is older than 12 months.
"""
from __future__ import annotations

import random

from ops.r16_customers import fin
from ops.r16_customers.ids import BANK, BY_KEY

RIMAL = "Al Rimal Commercial Bank"
TAYF = "Al Tayf Healthcare Trading Est."
LAB = "Naseem Lab Systems Co."


def spec() -> dict:
    ids = BY_KEY["c1"]
    co = {**ids, "legal_form": "Limited Liability Company", "incorporated": "2009-02-15", "capital_mn": 30.0, "shares_total": 30_000, "share_value": 1_000,
          "address": "Prince Mohammed bin Saad Road, Al Sulay, Riyadh 14322", "phone": "+966 11 255 7130", "email": "accounts@daralnaseem.example",
          "activity": "Wholesale trade in medical consumables, hospital equipment and laboratory supplies; import, storage and distribution.",
          "activity_short": "Wholesale of medical supplies and hospital equipment", "cr_issue": "2009-02-15", "cr_expiry": "2027-06-03",
          "cr_print": "2026-10-02", "aoa_amended": "2021-11-08", "vat_effective": "2018-01-01", "vat_frequency": "Monthly", "vat_cert_issue": "2018-01-09",
          "zakat": {"number": "ZC-2026-0398247", "fy_end": "2025-12-31", "issue": "2026-04-22", "expiry": "2027-04-30"},
          "nitaqat": {"establishment": "1-4471902", "band": "Medium Green", "rate": 27.1, "threshold": 21.0, "total": 214, "saudi": 58,
                      "issue": "2026-10-01", "expiry": "2026-12-31"},
          "shareholders": [{"name": "Naseem Holding Co.", "id_number": "CR 1010298811", "nationality": "Saudi company", "shares": 24_000, "pct": 80.0},
                           {"name": "Fahad Saad Al-Naseem", "id_number": "1012345870", "nationality": "Saudi", "shares": 6_000, "pct": 20.0}],
          "managers": [{"name": "Fahad Saad Al-Naseem", "role": "Chairman and General Manager", "powers": "Sole signatory"},
                       {"name": "Majed Saad Al-Naseem", "role": "Director", "powers": "Jointly with the General Manager above SAR 5m"}],
          "aoa_amendment_text": "Amended on 08/11/2021: transfer of 80% to Naseem Holding Co. (owned 60% by Fahad Saad Al-Naseem and 40% by Majed Saad Al-Naseem)."}
    people = [
        {"key": "fahad", "name": "Fahad Saad Al-Naseem", "id_number": "1012345870", "nationality": "Saudi", "dob": "1965-07-22", "id_issue": "2022-03-10",
         "id_expiry": "2032-03-09", "role": "Chairman and GM; 20% direct and 48% through Naseem Holding", "guarantor": True,
         "simah": {"date": "2026-10-08", "number": "SC-26-8790311", "score": 731, "worst": "Current on own facilities; guaranteed facility substandard",
                   "facilities": [{"lender": BANK, "product": "Credit card", "limit": 0.15, "outstanding": 0.032, "overdue": 0.0, "status": "Current"},
                                  {"lender": RIMAL, "product": "Real-estate finance", "limit": 4.8, "outstanding": 3.1, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Dar Al Naseem Medical Supplies Co.", "lender": BANK, "amount": 95.0, "status": "Current"},
                                  {"beneficiary": "Dar Al Naseem Medical Supplies Co.", "lender": RIMAL, "amount": 45.0, "status": "Current"},
                                  {"beneficiary": LAB, "lender": RIMAL, "amount": 22.0, "status": "Substandard (classified 07/2026)"}],
                   "history": f"Own facilities current for 24 months. Guaranteed facility of {LAB} at {RIMAL}: 90+ days past due from 05/2026, "
                              "classified substandard in 07/2026."},
         "pnw": {"date": "2026-08-31",
                 "assets": [{"asset": "Shares", "description": "60% of Naseem Holding Co. (book value)", "value": 52.8},
                            {"asset": "Shares", "description": "20% of Dar Al Naseem Medical Supplies Co. (book value)", "value": 15.2},
                            {"asset": "Real estate", "description": "Residential compound, Al Narjis, Riyadh (valuation 03/2026)", "value": 28.5},
                            {"asset": "Real estate", "description": "Land, Al Kharj road (2,400 sq m)", "value": 9.6},
                            {"asset": "Cash and deposits", "description": "Current and deposit accounts", "value": 11.9},
                            {"asset": "Listed shares", "description": "Portfolio at market value", "value": 6.3}],
                 "liabilities": [{"liability": "Real-estate finance", "description": RIMAL, "value": 3.1},
                                 {"liability": "Credit card", "description": BANK, "value": 0.032}]}},
        {"key": "majed", "name": "Majed Saad Al-Naseem", "id_number": "1019876543", "nationality": "Saudi", "dob": "1969-01-30", "id_issue": "2020-09-14",
         "id_expiry": "2030-09-13", "role": "Director; 32% through Naseem Holding", "guarantor": True,
         "simah": {"date": "2026-10-08", "number": "SC-26-8790312", "score": 748, "worst": "Current (no delinquency)",
                   "facilities": [{"lender": BANK, "product": "Auto finance", "limit": 0.38, "outstanding": 0.21, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Dar Al Naseem Medical Supplies Co.", "lender": BANK, "amount": 95.0, "status": "Current"}],
                   "history": "24 of 24 months current."},
         "pnw": {"date": "2026-08-31",
                 "assets": [{"asset": "Shares", "description": "40% of Naseem Holding Co. (book value)", "value": 35.2},
                            {"asset": "Real estate", "description": "Villa, Al Malqa, Riyadh", "value": 8.4},
                            {"asset": "Cash and deposits", "description": "Deposit accounts", "value": 4.7}],
                 "liabilities": [{"liability": "Auto finance", "description": BANK, "value": 0.21}]}},
    ]
    fy23 = fin.statement({"revenue": 158.9, "cost_of_sales": 119.5, "operating_expenses": 20.6, "finance_cost": 3.9, "zakat": 1.0, "depreciation": 2.9,
                          "cash": 9.8, "trade_receivables": 41.7, "inventory": 36.5, "due_from_related": 2.2, "other_current_assets": 5.4,
                          "ppe": 24.1, "other_noncurrent_assets": 1.0, "short_term_borrowings": 28.3, "trade_payables": 17.2, "due_to_related": 0.9,
                          "current_portion_ltd": 2.0, "long_term_borrowings": 10.0, "end_of_service": 4.3, "share_capital": 30.0, "statutory_reserve": 6.42, "retained_earnings": 20.38})
    fy24 = fin.statement({"revenue": 182.4, "cost_of_sales": 137.7, "operating_expenses": 23.1, "finance_cost": 4.6, "zakat": 1.2, "depreciation": 3.2,
                          "cash": 11.4, "trade_receivables": 48.5, "inventory": 41.2, "due_from_related": 3.1, "other_current_assets": 6.3,
                          "ppe": 24.8, "other_noncurrent_assets": 1.1, "short_term_borrowings": 32.6, "trade_payables": 18.4, "due_to_related": 1.0,
                          "current_portion_ltd": 2.0, "long_term_borrowings": 8.0, "end_of_service": 4.9, "share_capital": 30.0, "statutory_reserve": 8.0, "retained_earnings": 22.9})
    fy25 = fin.statement({"revenue": 251.7, "cost_of_sales": 193.6, "operating_expenses": 28.4, "finance_cost": 6.9, "zakat": 1.5, "depreciation": 3.6,
                          "cash": 9.2, "trade_receivables": 112.3, "inventory": 52.6, "due_from_related": 4.4, "other_current_assets": 7.9,
                          "ppe": 26.1, "other_noncurrent_assets": 1.2, "short_term_borrowings": 78.4, "trade_payables": 26.9, "due_to_related": 1.2,
                          "current_portion_ltd": 2.0, "long_term_borrowings": 6.0, "end_of_service": 5.6, "share_capital": 30.0, "statutory_reserve": 10.13,
                          "retained_earnings": 36.07, "related_party_sales": 78.0})
    m9 = fin.statement({"revenue": 205.6, "cost_of_sales": 159.5, "operating_expenses": 23.9, "finance_cost": 6.4, "zakat": 0.0, "depreciation": 2.9,
                        "cash": 7.6, "trade_receivables": 148.9, "inventory": 58.3, "due_from_related": 5.0, "other_current_assets": 8.4,
                        "ppe": 26.4, "other_noncurrent_assets": 1.2, "short_term_borrowings": 104.7, "trade_payables": 29.8, "due_to_related": 1.4,
                        "current_portion_ltd": 2.0, "long_term_borrowings": 4.5, "end_of_service": 6.1, "share_capital": 30.0, "statutory_reserve": 10.13,
                        "retained_earnings": 51.87})
    m9["months"] = 9
    fy23["operating_cash_flow"] = 9.6
    fy24["operating_cash_flow"] = fin.ocf(fy23, fy24)
    fy25["operating_cash_flow"] = fin.ocf(fy24, fy25)
    m9["operating_cash_flow"] = fin.ocf(fy25, m9)
    fy25["dividends"] = round(fy24["total_equity"] + fy25["net_profit"] - fy25["total_equity"], 3)
    fs = {"FY2023": fy23, "FY2024": fy24, "FY2025": fy25, "9M2026": m9}
    aud = "Basma & Partners Chartered Accountants"
    audit = {"FY2024": {"auditor": aud, "opinion": "Unqualified", "qawaem": "QW-2025-1010384527", "city": "Riyadh", "partner": "Hani Al-Basma",
                        "licence": "388", "signed": "2025-04-17"},
             "FY2025": {"auditor": aud, "opinion": "Unqualified", "qawaem": "QW-2026-1010384527", "city": "Riyadh", "partner": "Hani Al-Basma",
                        "licence": "388", "signed": "2026-04-21"}}
    notes = {"FY2024": [("Note 8 — Trade receivables", "Trade receivables SAR 48,500,000 (2023: 41,700,000), net of an allowance of SAR 1,900,000; "
                                                       "government hospitals 41%, private hospitals and clinics 52%, pharmacies 7%."),
                        ("Note 15 — Related parties", f"Due from {LAB} (a fellow subsidiary of Naseem Holding Co.) SAR 3,100,000 for equipment servicing."),
                        ("Note 17 — Borrowings", f"Short-term Murabaha and trust receipts with two banks SAR 32,600,000; long-term loan secured by a mortgage "
                                                 f"over the company's warehouse in favour of {BANK}.")],
             "FY2025": [("Note 8 — Trade receivables", "Trade receivables SAR 112,300,000 (2024: 48,500,000), net of an allowance of SAR 2,400,000. "
                                                       "The increase reflects the appointment of a regional distributor in February 2025 on 120-day terms."),
                        ("Note 15 — Related parties", f"Sales to {TAYF}, an entity owned by a relative of a shareholder, SAR 78,000,000 (2024: nil); "
                                                      f"balance receivable SAR 61,400,000 (2024: nil), included in trade receivables. Due from {LAB} "
                                                      "SAR 4,400,000 (2024: 3,100,000)."),
                        ("Note 17 — Borrowings", f"Short-term Murabaha, trust receipts and LC acceptances SAR 78,400,000 ({BANK} SAR 46,200,000; {RIMAL} "
                                                 "SAR 32,200,000). Long-term loan SAR 8,000,000 secured by the warehouse mortgage."),
                        ("Note 22 — Subsequent events", "No adjusting events.")]}
    # ---------------------------------------------------------------- monthly revenue (VAT) and collections
    rnd = random.Random("c1-vat")
    q4 = fin.series(71.2, 3, rnd, noise=0.05)
    rev12 = q4 + fin.series(205.6, 9, rnd, trend=0.12, noise=0.06)
    vat = []
    for ym, r in zip(fin.months("2025-10", 12), rev12):
        ts = round(r * (1 + 0.03 * (rnd.random() - 0.5)), 3)
        vat.append({"period": ym, "from": f"{ym}-01", "to": fin.month_end(ym), "taxable_sales": ts, "zero_rated": 0.0, "output_vat": round(0.15 * ts, 3),
                    "input_vat": round(ts * 0.15 * rnd.uniform(0.72, 0.80), 3), "filed_on": fin.add_days(fin.month_end(ym), 18)})
    mlist = fin.months("2025-10", 12)
    total_rev = sum(rev12)
    tayf_share = [0.31, 0.32, 0.32] + [0.34] * 9
    tayf_rev = [r * s for r, s in zip(rev12, tayf_share)]
    tayf_coll = fin.series(sum(tayf_rev) * 1.15 * 0.42, 12, random.Random("c1-tayf"), trend=-0.2, noise=0.25, nd=6)
    other_coll = fin.series((total_rev - sum(tayf_rev)) * 1.15 * 0.985, 12, random.Random("c1-oth"), trend=0.15, noise=0.08, nd=6)
    rnd = random.Random("c1-stmt")
    shb_cr, rim_cr = [], []
    for i, ym in enumerate(mlist):
        oc = other_coll[i]
        g = fin.split(oc * 0.84, 4, rnd, spread=0.4, nd=6)
        shb_cr.append([("Ministry hospitals cluster — payment", g[0], 6), ("Private hospitals — collections", g[1], 13),
                       ("Clinics and pharmacies — collections", g[2], 20), ("Private hospitals — collections", g[3], 27),
                       (f"{TAYF} — payment", round(tayf_coll[i] * 0.7, 6), 24)])
        r2 = fin.split(oc * 0.16, 2, rnd, spread=0.4, nd=6)
        rim_cr.append([("Private hospitals — collections", r2[0], 9), ("Clinics — collections", r2[1], 22),
                       (f"{TAYF} — payment", round(tayf_coll[i] * 0.3, 6), 15)])

    def debit_items(credits, opening, closing, layout):
        tot_c = [round(sum(a for _, a, _ in c), 6) for c in credits]
        deltas = fin.series(opening - closing, 12, rnd, noise=0.0, nd=6)
        out = []
        for i in range(12):
            target = round(tot_c[i] + deltas[i], 6)
            shares = [s * (1 + 0.15 * (rnd.random() - 0.5)) for _, s, _ in layout]
            ws = sum(shares)
            parts = [round(target * s / ws, 6) for s in shares[:-1]]
            parts.append(round(target - sum(parts), 6))
            out.append([(lab, a, d) for (lab, _, d), a in zip(layout, parts)])
        return out
    shb_layout = [("LC settlement — imported supplies", 0.38, 11), ("Supplier payments (local)", 0.22, 17), ("Payroll transfer (WPS)", 0.09, 27),
                  ("GOSI contribution", 0.01, 15), ("VAT payment", 0.05, 28), ("Murabaha profit and charges", 0.04, 2), ("Warehouse and fleet expenses", 0.06, 8),
                  ("Murabaha repayment (net)", 0.15, 25)]
    rim_layout = [("Supplier payments", 0.62, 12), ("Murabaha repayment (net)", 0.25, 26), ("Profit and charges", 0.05, 2), ("Logistics expenses", 0.08, 19)]
    shb = {"bank": BANK, "number": "0105-220981-001", "iban": "SA5277000001052209810011", "type": "Current account (main operating)", "opening": 6.1,
           "issued": "2026-10-03", "months": mlist, "credit_items": shb_cr, "debit_items": debit_items(shb_cr, 6.1, 5.3, shb_layout),
           "returned": {"2026-02": 1}}
    rim = {"bank": RIMAL, "number": "330-118204-6", "iban": "SA7155000000330118204600", "type": "Current account", "opening": 2.8, "issued": "2026-10-05",
           "months": mlist, "credit_items": rim_cr, "debit_items": debit_items(rim_cr, 2.8, 2.1, rim_layout), "returned": {}}
    coll = sum(tayf_coll) + sum(other_coll)
    # ---------------------------------------------------------------- receivables ageing (30/09/2026 = in-house 148.9)
    rows = [{"customer": TAYF, "b0_90": 37.9, "b91_180": 34.8, "b181_365": 19.9, "over_365": 0.0},
            {"customer": "Ministry hospitals cluster (central region)", "b0_90": 17.6, "b91_180": 8.1, "b181_365": 2.2, "over_365": 0.0},
            {"customer": "Riyadh Care Private Hospitals Co.", "b0_90": 9.7, "b91_180": 1.1, "b181_365": 0.0, "over_365": 0.0},
            {"customer": "Al Shifa Medical Group", "b0_90": 6.2, "b91_180": 0.4, "b181_365": 0.0, "over_365": 0.0}]
    used = sum(r["b0_90"] + r["b91_180"] + r["b181_365"] + r["over_365"] for r in rows)
    rest = round(m9["trade_receivables"] - used, 3)
    rows.append({"customer": "Other hospitals, clinics and pharmacies (212 accounts)", "b0_90": round(rest - 2.1 - 1.3, 3), "b91_180": 2.1, "b181_365": 1.3, "over_365": 0.0})
    rec_ageing = {"as_of": "2026-09-30", "rows": rows}
    pay = [{"supplier": "Nordmed Instruments GmbH", "b0_90": 9.6, "b91_180": 0.0, "over_180": 0.0},
           {"supplier": "Pacific Rim Medical Consumables Ltd", "b0_90": 7.2, "b91_180": 0.8, "over_180": 0.0},
           {"supplier": "Gulf Surgical Supplies Co.", "b0_90": 4.1, "b91_180": 0.6, "over_180": 0.0}]
    pt = sum(r["b0_90"] + r["b91_180"] + r["over_180"] for r in pay)
    pay.append({"supplier": "Other suppliers", "b0_90": round(m9["trade_payables"] - pt - 0.4, 3), "b91_180": 0.4, "over_180": 0.0})
    top = {"year": 2025, "date": "2026-10-05",
           "customers": [{"name": TAYF, "relationship": "Third-party distributor (Eastern and Southern regions)", "sales": 78.0, "share": 31.0, "terms": "120 days"},
                         {"name": "Ministry hospitals cluster (central region)", "relationship": "Government", "sales": 46.3, "share": 18.4, "terms": "90-120 days"},
                         {"name": "Riyadh Care Private Hospitals Co.", "relationship": "Third party", "sales": 24.9, "share": 9.9, "terms": "60 days"},
                         {"name": "Al Shifa Medical Group", "relationship": "Third party", "sales": 17.4, "share": 6.9, "terms": "60 days"},
                         {"name": "Other hospitals, clinics and pharmacies", "relationship": "Third parties", "sales": 85.1, "share": 33.8, "terms": "30-90 days"}],
           "suppliers": [{"name": "Nordmed Instruments GmbH", "country": "Germany", "purchases": 52.3, "share": 26.9, "terms": "LC 90 days usance"},
                         {"name": "Pacific Rim Medical Consumables Ltd", "country": "Malaysia", "purchases": 38.1, "share": 19.6, "terms": "LC at sight"},
                         {"name": "Gulf Surgical Supplies Co.", "country": "KSA", "purchases": 21.7, "share": 11.2, "terms": "45 days"}],
           "notes": ["Sales shares are of FY2025 revenue (SAR 251,700,000)."]}
    simah_company = {"date": "2026-10-08", "number": "SB-26-3297704", "score": 702, "enquiries": 2,
                     "facilities": [{"lender": BANK, "product": "Short-term Murabaha", "limit": 40.0, "outstanding": 39.6, "overdue": 0.0, "status": "Current", "opened": "2017-05-02"},
                                    {"lender": BANK, "product": "Letters of credit (incl. acceptances)", "limit": 30.0, "outstanding": 18.4, "overdue": 0.0, "status": "Current", "opened": "2017-05-02"},
                                    {"lender": BANK, "product": "Trust receipts", "limit": 15.0, "outstanding": 14.8, "overdue": 0.0, "status": "Current", "opened": "2019-06-11"},
                                    {"lender": BANK, "product": "Letters of guarantee", "limit": 10.0, "outstanding": 3.1, "overdue": 0.0, "status": "Current", "opened": "2017-05-02"},
                                    {"lender": BANK, "product": "Term loan (warehouse)", "limit": 6.5, "outstanding": 6.5, "overdue": 0.0, "status": "Current", "opened": "2020-01-15"},
                                    {"lender": RIMAL, "product": "Short-term Murabaha", "limit": 30.0, "outstanding": 29.1, "overdue": 0.0, "status": "Current", "opened": "2022-08-01"},
                                    {"lender": RIMAL, "product": "Letters of credit (incl. acceptances)", "limit": 15.0, "outstanding": 8.7, "overdue": 0.0, "status": "Current", "opened": "2022-08-01"}],
                     "history": "No delinquency on the company's own facilities in the last 24 months.",
                     "enquiry_text": f"2 enquiries in the last 6 months: {BANK} (10/2026), {RIMAL} (07/2026)."}
    other_banks = [{"bank": RIMAL, "offer_date": "2026-02-10", "offer_ref": "ARCB/RUH/26/118", "offer_expiry": "2027-01-31", "offer_signed": "Yousef Al-Harbi",
                    "facilities": [{"facility": "Short-term Murabaha", "limit": 30.0, "pricing": "3M SAIBOR + 1.90%", "tenor": "up to 120 days"},
                                   {"facility": "Letters of credit (sight / usance 90 days)", "limit": 15.0, "pricing": "0.30% per quarter", "tenor": "per LC"}],
                    "security": "Personal guarantee of Fahad Saad Al-Naseem; promissory note SAR 45,000,000.",
                    "statement_date": "2026-09-30",
                    "statement": [{"facility": "Short-term Murabaha", "limit": 30.0, "outstanding": 29.1, "overdue": 0.0, "maturity": "rolling"},
                                  {"facility": "Letters of credit (sight / usance 90 days)", "limit": 15.0, "outstanding": 8.7, "overdue": 0.0, "maturity": "per LC"}]}]
    req = {"date": "2026-10-12", "ref": "DNMS/FIN/2026/77", "by": "Fahad Saad Al-Naseem", "role": "Chairman and General Manager",
           "body": f"Our business grew by 38% in 2025, helped by our new regional distribution partner {TAYF}, which covers the Eastern and Southern "
                   "regions. To support this growth we request the renewal of our facilities of SAR 95,000,000 and their increase to SAR 140,000,000:",
           "facilities": [{"facility": "Short-term Murabaha", "amount": 65.0, "purpose": "Working capital (from SAR 40m)"},
                          {"facility": "Letters of credit (sight / usance)", "amount": 40.0, "purpose": "Imports of medical supplies (from SAR 30m)"},
                          {"facility": "Trust receipts", "amount": 25.0, "purpose": "Financing of LC settlements (from SAR 15m)"},
                          {"facility": "Letters of guarantee", "amount": 10.0, "purpose": "Tender and performance guarantees (unchanged)"}],
           "more": ["The existing mortgage over our warehouse and the personal guarantees of the partners remain in place. We confirm there are no "
                    "changes in ownership and no facilities with other banks other than those disclosed."]}
    resolution = {"date": "2026-10-11", "number": "PR-2026-03", "amount": 190.0, "persons": "Fahad Saad Al-Naseem (Chairman and General Manager)",
                  "text": "The partners resolved to obtain and renew credit facilities from banks up to a total of SAR 190,000,000 and authorised the "
                          "Chairman and General Manager to sign all facility and security documents."}
    signatories = {"as_of": "2026-10-11", "rows": [
        {"name": "Fahad Saad Al-Naseem", "id_number": "1012345870", "role": "Chairman and General Manager", "limit": "Unlimited", "mode": "Single"},
        {"name": "Majed Saad Al-Naseem", "id_number": "1019876543", "role": "Director", "limit": "Up to SAR 5m", "mode": "Single; joint above"},
        {"name": "Rania Yousef Khoury", "id_number": "2410938871", "role": "Finance Manager", "limit": "Up to SAR 0.5m (payments)", "mode": "Joint"}]}
    collateral = [{"key": "warehouse", "property": "Warehouse and offices, plot 18/4, Second Industrial City, Riyadh (6,200 sq m land)",
                   "owner": "Dar Al Naseem Medical Supplies Co.", "deed": "310118004427",
                   "valuation": {"valuer": "Masdar Real Estate Valuation Co.", "date": "2025-08-14", "mv": 31.5, "fsv": 24.0, "signed": "Eng. Sami Al-Rowais",
                                 "text": ["Industrial plot with a 4,800 sq m warehouse (2015) and two-storey offices. Comparable method and cost approach.",
                                          "Market value SAR 31,500,000; forced-sale value SAR 24,000,000 (76%). Valid for 12 months from the valuation date."]},
                   "deed_doc": {"area": 6200, "date": "2014-06-19", "encumbrance": f"First-degree mortgage in favour of {BANK} (2020)",
                                "text": "Industrial land plot with buildings, held freehold by the company."},
                   "insurance": {"number": "PAR-26-551902", "insurer": "Najm Al Khaleej Cooperative Insurance Co.", "sum": 28.0, "loss_payee": BANK,
                                 "from": "2026-03-01", "to": "2027-02-28"}}]
    site = {"date": "2026-10-09", "by": "Nawaf Al-Otaibi", "met": "Fahad Saad Al-Naseem; Rania Yousef Khoury (Finance Manager)",
            "premises": "Head office and warehouse, Second Industrial City, Riyadh (owned)", "staff": 64,
            "summary": "Warehouse well stocked and organised; cold-chain room in use; fleet of 22 delivery vans.",
            "points": ["Warehouse about 85% full; inventory system with batch and expiry tracking; management states slow-moving stock below 3%.",
                       f"Growth since 2025 driven by the regional distributor {TAYF} (Dammam and Abha warehouses, as per management).",
                       "Management plans to add a second warehouse in Dammam in 2027.", "No adverse observation."]}
    aml = {"date": "2026-10-11", "by": "Fahad Saad Al-Naseem", "pep": "No", "countries": "KSA; imports from Germany, Malaysia, USA, China",
           "cash": "No", "rating": "Low",
           "ubos": [{"name": "Fahad Saad Al-Naseem", "pct": 68.0, "pep": "No"}, {"name": "Majed Saad Al-Naseem", "pct": 32.0, "pep": "No"}],
           "notes": [f"Related entities declared: Naseem Holding Co. (parent), {LAB} (sister). No other related parties declared."]}
    return {"key": "c1", "co": co, "people": people, "fs": fs, "audit": audit, "notes": notes, "inhouse_by": "Rania Yousef Khoury", "inhouse_date": "2026-10-10",
            "inhouse_notes": ["Trade receivables include balances from the regional distributor on 120-day terms."],
            "vat": vat, "accounts": [shb, rim], "simah_company": simah_company, "consent": {"by": "Fahad Saad Al-Naseem", "role": "Chairman and General Manager", "on": "2026-10-11"},
            "request": req, "resolution": resolution, "signatories": signatories, "other_banks": other_banks, "rec_ageing": rec_ageing,
            "pay_ageing": {"as_of": "2026-09-30", "rows": pay}, "top": top, "collateral": collateral, "site_visit": site, "aml": aml,
            "missing": [],
            "facts": {"rev12": round(total_rev, 3), "collections_ratio": round(coll / 1.15 / total_rev, 3), "collections_band": [0.70, 0.84],
                      "tayf_rev12": round(sum(tayf_rev), 3), "tayf_collected12": round(sum(tayf_coll), 3)}}


# ==================================================================================================== bank side
def bank(sp: dict) -> dict:
    from ops.r16_customers.docs import statement_lines
    rnd = random.Random("c1-bank")
    cif, pid = "CB09001", "R16-C1"
    _, shb_m = statement_lines(sp["accounts"][0])
    months = fin.months("2024-01", 33)
    cy24 = round(0.83 * 182.4 * 1.15 * 0.99, 3)
    q4_25 = sum(m["credits"] for m in shb_m[:3])
    jan_sep25 = round(cy24 * 1.09 - q4_25, 3)
    s24 = fin.series(cy24, 12, rnd, trend=0.1, noise=0.07, nd=3)
    s25 = fin.series(jan_sep25, 9, rnd, trend=0.05, noise=0.07, nd=3)
    conduct = []
    for i, ym in enumerate(months):
        if i < 12:
            cr = s24[i]
        elif i < 21:
            cr = s25[i - 12]
        else:
            cr = round(shb_m[i - 21]["credits"], 3)
        avg = round(shb_m[i - 21]["avg"], 3) if i >= 21 else round(rnd.uniform(4.0, 7.5), 3)
        dr = round(shb_m[i - 21]["debits"], 3) if i >= 21 else round(cr * rnd.uniform(0.97, 1.03), 3)
        limits = 95.0 if ym >= "2025-03" else 70.0
        util = round((0.58 + 0.30 * i / 32 + 0.03 * (rnd.random() - 0.5)) * limits, 3)
        rc = 1 if ym == "2026-02" else 0
        conduct.append({"obligor_id": cif, "proposal_id": pid, "month": ym, "credit_turnover_mn": cr, "debit_turnover_mn": dr, "avg_balance_mn": avg,
                        "limits_mn": limits, "utilised_mn": util, "utilisation_pct": round(100 * util / limits, 1), "past_due_days_max": 0, "past_due_mn": 0.0,
                        "returned_cheques_n": rc, "returned_cheques_mn": 0.185 if rc else 0.0, "routed_business_mn": cr})
    conduct[-1]["utilised_mn"], conduct[-1]["utilisation_pct"] = 75.9, 79.9
    lab, tayf = "CB09005", "CB09004"
    lab_cheques = [("2026-04-14", 0.27), ("2026-06-22", 0.34)]
    for i, ym in enumerate(fin.months("2024-10", 24)):
        rc = [c for c in lab_cheques if c[0][:7] == ym]
        cr = round(rnd.uniform(0.9, 1.5) * (0.82 if ym >= "2026-03" else 1.0), 3)
        conduct.append({"obligor_id": lab, "proposal_id": pid, "month": ym, "credit_turnover_mn": cr, "debit_turnover_mn": round(cr * rnd.uniform(0.98, 1.08), 3),
                        "avg_balance_mn": round(rnd.uniform(0.02, 0.2), 3), "limits_mn": 5.0, "utilised_mn": 4.2, "utilisation_pct": 84.0,
                        "past_due_days_max": 0, "past_due_mn": 0.0, "returned_cheques_n": len(rc), "returned_cheques_mn": round(sum(a for _, a in rc), 3),
                        "routed_business_mn": cr})
    tay = fin.series(34.2, 12, rnd, trend=0.3, noise=0.2, nd=3)
    for i, ym in enumerate(fin.months("2025-10", 12)):
        conduct.append({"obligor_id": tayf, "proposal_id": pid, "month": ym, "credit_turnover_mn": tay[i], "debit_turnover_mn": round(tay[i] * rnd.uniform(0.97, 1.02), 3),
                        "avg_balance_mn": round(rnd.uniform(0.2, 0.6), 3), "limits_mn": 0.0, "utilised_mn": 0.0, "utilisation_pct": 0.0, "past_due_days_max": 0,
                        "past_due_mn": 0.0, "returned_cheques_n": 0, "returned_cheques_mn": 0.0, "routed_business_mn": tay[i]})
    returned = [{"cheque_id": "RC-C1-1", "obligor_id": cif, "proposal_id": pid, "return_date": "2026-02-17", "amount_mn": 0.185, "reason": "signature", "regularised_flag": 1}]
    returned += [{"cheque_id": f"RC-C1-LAB-{k+1}", "obligor_id": lab, "proposal_id": pid, "return_date": d, "amount_mn": a, "reason": "insufficient_funds",
                  "regularised_flag": 0} for k, (d, a) in enumerate(lab_cheques)]
    limits = [("L0", "", 0, "Total facilities", "", 0, 101.5, 82.4, 146.5, None, None, "", None, None, "", "", "", ""),
              ("W1", "L0", 1, "Short-term Murabaha", "TL", 1, 40.0, 39.6, 65.0, 0.0, None, "3M SAIBOR", 1.75, 5.75, "Up to 120 days per draw", "Bullet per draw", "", ""),
              ("W2", "L0", 1, "Letters of credit (sight / usance 90 days)", "LC_SIGHT", 0, 30.0, 18.4, 40.0, 10.0, 0.25, "", None, None, "Usance up to 90 days", "", "", "0.25% per quarter"),
              ("W3", "L0", 1, "Trust receipts", "TR", 1, 15.0, 14.8, 25.0, 0.0, None, "3M SAIBOR", 1.75, 5.75, "Up to 120 days", "From sale proceeds", "", ""),
              ("W4", "L0", 1, "Letters of guarantee (tender, performance)", "LG", 0, 10.0, 3.1, 10.0, 10.0, 0.60, "", None, None, "Up to 24 months", "", "", ""),
              ("W5", "L0", 1, "Term loan (warehouse), amortising", "TL", 1, 6.5, 6.5, 6.5, 0.0, None, "3M SAIBOR", 2.00, 6.00, "To 01/2030", "Semi-annual SAR 1.0m", "", "Not renewed; runs off")]
    lim_rows = []
    for seq, r in enumerate(limits):
        lim_rows.append(dict(zip(("limit_id", "parent_limit_id", "level", "limit_name", "product_code", "funded_flag", "existing_mn", "outstanding_mn",
                                  "proposed_mn", "cash_margin_pct", "commission_pct_pa", "benchmark", "spread_pct", "floor_pct", "tenor_text",
                                  "repayment_text", "project_id", "particulars"), r)) | {"proposal_id": pid, "seq": seq, "currency": "SAR", "interchangeable_flag": 0})
    security = [
        {"security_id": "S1", "limit_id": "ALL", "kind": "mortgage", "provider": "Dar Al Naseem Medical Supplies Co.", "provider_entity_id": "XE-C1-01",
         "amount_mn": 31.5, "valuation_date": "2025-08-14", "value_mn": 31.5, "insurance_expiry": "2027-02-28", "perfection_status": "perfected", "existing_flag": 1,
         "note": "First-degree mortgage over the warehouse; valuation of 14/08/2025 older than 12 months (FSV SAR 24.0m)"},
        {"security_id": "S2", "limit_id": "ALL", "kind": "personal_guarantee", "provider": "Fahad Saad Al-Naseem", "provider_entity_id": "XP-C1-01",
         "net_worth_mn": 120.268, "net_worth_statement_date": "2026-08-31", "perfection_status": "perfected", "existing_flag": 1, "note": "Existing"},
        {"security_id": "S3", "limit_id": "ALL", "kind": "personal_guarantee", "provider": "Majed Saad Al-Naseem", "provider_entity_id": "XP-C1-02",
         "net_worth_mn": 48.09, "net_worth_statement_date": "2026-08-31", "perfection_status": "perfected", "existing_flag": 1, "note": "Existing"},
        {"security_id": "S4", "limit_id": "ALL", "kind": "corporate_guarantee", "provider": "Naseem Holding Co.", "provider_entity_id": "XE-C1-00",
         "perfection_status": "perfected", "existing_flag": 1, "note": "Existing corporate guarantee of the parent"},
        {"security_id": "S5", "limit_id": "ALL", "kind": "security_cheque", "provider": "Dar Al Naseem Medical Supplies Co.", "provider_entity_id": "XE-C1-01",
         "amount_mn": 146.5, "perfection_status": "pending", "existing_flag": 0, "note": "Promissory note for the total facilities"}]
    for s in security:
        s.update({"proposal_id": pid, "currency": "SAR"})
    tnc = [("T1", "W1", 1, "utilisation", "Murabaha drawn against invoices of hospitals and clinics; each draw up to 120 days.", "complied"),
           ("T2", "W3", 2, "settlement", "Trust receipts settled from the sale proceeds of the goods financed, maximum 120 days.", "complied"),
           ("T3", "ALL", 3, "routing", "Route not less than 75% of turnover through the Bank.", "complied"),
           ("T4", "ALL", 4, "existing_condition", "Inform the Bank before trading with any new related party (CC/2025/031, condition 4).", "not_complied"),
           ("T5", "ALL", 5, "existing_condition", "Renew the warehouse valuation annually (CC/2025/031, condition 5).", "not_complied"),
           ("T6", "ALL", 6, "reporting", "Audited financial statements within 120 days; receivables ageing quarterly.", "complied")]
    tnc_rows = [{"proposal_id": pid, "tnc_id": t, "limit_id": l, "seq": s, "category": c, "text": x, "existing_status": st} for t, l, s, c, x, st in tnc]
    refs = [("R1", "limit_history", "CC/2017/052", "2017-04-25", "Credit Committee", 35.0, 35.0, "First approval: Murabaha and LCs."),
            ("R2", "limit_history", "CC/2021/163", "2021-09-30", "Credit Committee", 70.0, 80.0, "Increase; warehouse term loan."),
            ("R3", "committee_decision", "CC/2025/031", "2025-02-20", "Credit Committee", 95.0, 110.0,
             "Renewal and increase to SAR 95m (+ warehouse loan); group cap SAR 110m; inform the Bank of new related-party trading; annual valuation."),
            ("R4", "credit_file_request", "CFR/RUH/2026/0612", "2026-10-13", "", None, None, "Business request for renewal and increase to SAR 140m.")]
    ref_rows = [dict(zip(("ref_id", "kind", "ref_no", "ref_date", "authority", "amount_mn", "group_cap_mn", "text"), r)) | {"proposal_id": pid} for r in refs]
    ge = [{"proposal_id": pid, "group_id": "CG9001", "entity_id": "XE-C1-01", "entity_name": "Dar Al Naseem Medical Supplies Co.", "funded_existing_mn": 61.5,
           "total_existing_mn": 101.5, "funded_proposed_mn": 96.5, "total_proposed_mn": 146.5, "outstanding_mn": 82.4},
          {"proposal_id": pid, "group_id": "CG9001", "entity_id": "XE-C1-02", "entity_name": LAB, "funded_existing_mn": 0.0, "total_existing_mn": 5.0,
           "funded_proposed_mn": 0.0, "total_proposed_mn": 5.0, "outstanding_mn": 4.2},
          {"proposal_id": pid, "group_id": "CG9001", "entity_id": "XE-C1-00", "entity_name": "Naseem Holding Co.", "funded_existing_mn": 0.0, "total_existing_mn": 0.0,
           "funded_proposed_mn": 0.0, "total_proposed_mn": 0.0, "outstanding_mn": 0.0}]
    entities = [
        {"entity_id": "XE-C1-00", "entity_name": "Naseem Holding Co.", "role": "parent", "parent_entity_id": "", "legal_status": "LLC", "activity": "Holding company",
         "licence_no": "1010298811", "licence_expiry": "2027-11-20", "incorporation_date": "2011-11-20", "incorporation_place": "Riyadh", "staff_count": 4,
         "borrower_id": "", "credit_status": "performing", "credit_status_note": ""},
        {"entity_id": "XE-C1-01", "entity_name": "Dar Al Naseem Medical Supplies Co.", "role": "subject", "parent_entity_id": "XE-C1-00", "legal_status": "LLC",
         "activity": "Wholesale of medical supplies", "licence_no": "1010384527", "licence_expiry": "2027-06-03", "incorporation_date": "2009-02-15",
         "incorporation_place": "Riyadh", "staff_count": 214, "borrower_id": cif, "credit_status": "performing", "credit_status_note": ""},
        {"entity_id": "XE-C1-02", "entity_name": LAB, "role": "sister", "parent_entity_id": "XE-C1-00", "legal_status": "LLC",
         "activity": "Laboratory equipment supply and servicing", "licence_no": "1010455120", "licence_expiry": "2027-03-14", "incorporation_date": "2016-03-14",
         "incorporation_place": "Riyadh", "staff_count": 41, "borrower_id": lab, "credit_status": "classified_substandard",
         "credit_status_note": f"Classified substandard at {RIMAL} in 07/2026 (90+ days past due from 05/2026); 2 cheques returned at the Bank (04, 06/2026)"},
        {"entity_id": "XE-C1-03", "entity_name": TAYF, "role": "associate", "parent_entity_id": "", "legal_status": "Sole proprietorship (establishment)",
         "activity": "Wholesale of medical supplies (distributor)", "licence_no": "1010891234", "licence_expiry": "2027-02-08", "incorporation_date": "2025-02-09",
         "incorporation_place": "Dammam", "staff_count": 12, "borrower_id": tayf, "credit_status": "performing",
         "credit_status_note": "Owned by Sultan Majed Al-Naseem (son of director Majed Saad Al-Naseem); deposit customer since 03/2025, no facilities"},
    ]
    for e in entities:
        e.update({"group_id": "CG9001", "group_name": "Naseem Holding Group", "country": "Saudi Arabia", "listed_flag": 0})
    holders = [("XE-C1-01", "XE-C1-00", "Naseem Holding Co.", "company", "Saudi Arabia", None, 80.0, 0, None, "2021-11-08"),
               ("XE-C1-01", "XP-C1-01", "Fahad Saad Al-Naseem", "person", "Saudi", 1965, 20.0, 1, 68.0, "2009-02-15"),
               ("XE-C1-00", "XP-C1-01", "Fahad Saad Al-Naseem", "person", "Saudi", 1965, 60.0, 1, 68.0, "2011-11-20"),
               ("XE-C1-00", "XP-C1-02", "Majed Saad Al-Naseem", "person", "Saudi", 1969, 40.0, 1, 32.0, "2011-11-20"),
               ("XE-C1-02", "XE-C1-00", "Naseem Holding Co.", "company", "Saudi Arabia", None, 100.0, 0, None, "2016-03-14"),
               ("XE-C1-03", "XP-C1-03", "Sultan Majed Al-Naseem", "person", "Saudi", 1994, 100.0, 1, 100.0, "2025-02-09")]
    holder_rows = [dict(zip(("entity_id", "holder_id", "holder_name", "holder_kind", "nationality", "birth_year", "share_pct", "ubo_flag",
                             "ubo_effective_pct", "since"), h)) | {"nominee_flag": 0} for h in holders]
    edges = [("E-C1-1", "owns", "XE-C1-00", "XE-C1-01", 80.0, None, None, "80% shareholder"),
             ("E-C1-2", "owns", "XP-C1-01", "XE-C1-01", 20.0, None, None, "20% direct"),
             ("E-C1-3", "owns", "XP-C1-01", "XE-C1-00", 60.0, None, None, ""), ("E-C1-4", "owns", "XP-C1-02", "XE-C1-00", 40.0, None, None, ""),
             ("E-C1-5", "owns", "XE-C1-00", "XE-C1-02", 100.0, None, None, "Sister company"),
             ("E-C1-6", "owns", "XP-C1-03", "XE-C1-03", 100.0, None, None, "Sole proprietor; son of Majed Saad Al-Naseem"),
             ("E-C1-7", "buys_from", "XE-C1-03", "XE-C1-01", None, 78.0, None, "Distributor: 31% of FY2025 sales on 120-day terms; receivable SAR 92.6m at 30/09/2026"),
             ("E-C1-8", "related_party", "XP-C1-02", "XP-C1-03", None, None, None, "Father and son"),
             ("E-C1-9", "guarantees", "XP-C1-01", "XE-C1-02", None, None, 22.0, f"Personal guarantee of the sister's facility at {RIMAL} (classified substandard)"),
             ("E-C1-10", "guarantees", "XP-C1-01", "XE-C1-01", None, None, 146.5, "Personal guarantee"),
             ("E-C1-11", "related_party", "XE-C1-01", "XE-C1-02", None, None, 5.0, "Due from sister SAR 5.0m (servicing)")]
    edge_rows = [dict(zip(("edge_id", "rel_type", "source_id", "target_id", "ownership_pct", "annual_value_mn", "amount_mn", "detail"), e)) | {"group_id": "CG9001"} for e in edges]
    board = [("XE-C1-01", "XP-C1-01", "Fahad Saad Al-Naseem", "chairman", "Saudi", "2009-02-15", 1, ""),
             ("XE-C1-01", "XP-C1-02", "Majed Saad Al-Naseem", "director", "Saudi", "2009-02-15", 0, lab),
             ("XE-C1-02", "XP-C1-02", "Majed Saad Al-Naseem", "gm", "Saudi", "2016-03-14", 1, cif),
             ("XE-C1-03", "XP-C1-03", "Sultan Majed Al-Naseem", "authorised_signatory", "Saudi", "2025-02-09", 1, "")]
    board_rows = [dict(zip(("entity_id", "person_id", "person_name", "role", "nationality", "appointed", "key_person_flag", "linked_borrower_ids"), b))
                  | {"other_directorships": "[]"} for b in board]
    accounts = [
        {"obligor_id": cif, "account_no": "0105-220981-001", "iban": "SA5277000001052209810011", "account_type": "current", "label": "Current account (main operating)",
         "opened": "2017-05-02", "balance_mn": round(shb_m[-1]["closing"], 3), "avg_balance_12m_mn": round(sum(m["avg"] for m in shb_m) / 12, 3),
         "credits_12m_mn": round(sum(m["credits"] for m in shb_m), 3), "debits_12m_mn": round(sum(m["debits"] for m in shb_m), 3)},
        {"obligor_id": cif, "account_no": "0105-220981-701", "iban": "SA9477000001052209817011", "account_type": "deposit", "label": "Murabaha time deposit (3 months)",
         "opened": "2023-01-10", "balance_mn": 5.0, "avg_balance_12m_mn": 5.0, "credits_12m_mn": 0.21, "debits_12m_mn": 0.21},
        {"obligor_id": cif, "account_no": "0105-220981-501", "iban": "SA2577000001052209815011", "account_type": "deposit", "label": "Cash-margin deposit (LCs, LGs)",
         "opened": "2017-05-02", "balance_mn": 2.15, "avg_balance_12m_mn": 2.4, "credits_12m_mn": 3.9, "debits_12m_mn": 4.2},
        {"obligor_id": lab, "account_no": "0105-455120-001", "iban": "SA8077000001054551200011", "account_type": "current", "label": "Current account",
         "opened": "2016-04-01", "balance_mn": 0.041, "avg_balance_12m_mn": 0.09, "credits_12m_mn": 11.4, "debits_12m_mn": 11.9},
        {"obligor_id": tayf, "account_no": "0131-891234-001", "iban": "SA3377000001318912340011", "account_type": "current", "label": "Current account",
         "opened": "2025-03-04", "balance_mn": 0.36, "avg_balance_12m_mn": 0.41, "credits_12m_mn": round(sum(tay), 3), "debits_12m_mn": round(sum(tay) * 0.99, 3)},
    ]
    for a in accounts:
        a.update({"proposal_id": pid, "currency": "SAR", "bank_name": BANK, "as_of": "2026-09-30"})
    ratings = {cif: {"2021Q3": "BBB", "2026Q2": "BBB"}, lab: {"2021Q3": "BB", "2025Q4": "BB-", "2026Q2": "B-"}, tayf: {}}
    cy = {"2024": round(sum(r["credit_turnover_mn"] for r in conduct if r["obligor_id"] == cif and r["month"].startswith("2024")), 3),
          "2025": round(sum(r["credit_turnover_mn"] for r in conduct if r["obligor_id"] == cif and r["month"].startswith("2025")), 3)}
    return {"cif": cif, "proposal_id": pid, "unit": "Corporate Banking — Central Region", "branch": "Riyadh Olaya Branch", "rm": "Nawaf Al-Otaibi",
            "ro": "Abeer Al-Omari", "opened": "2017-05-02", "industry_code": "G4646 — Wholesale of pharmaceutical and medical goods",
            "purpose_code": "WC-01 Working capital (trade)", "collateral_code": "RE — Real-estate mortgage", "rating_existing": "BBB", "rating_proposed": "BBB",
            "review_date": "2026-11-30", "conduct": conduct, "returned_cheques": returned, "limits": lim_rows, "security": security, "tnc": tnc_rows,
            "references": ref_rows, "group_exposure": ge, "entities": entities, "holders": holder_rows, "edges": edge_rows, "board": board_rows,
            "accounts": accounts, "ratings": ratings, "credits_cy": cy, "connected": {"cif": lab, "name": LAB}}


# ==================================================================================================== proposal text
def proposal_text(sp: dict, b: dict) -> dict:
    fs = sp["fs"]
    f24, f25, m9 = fs["FY2024"], fs["FY2025"], fs["9M2026"]
    cy = b["credits_cy"]
    g_cred = 100 * (cy["2025"] / cy["2024"] - 1)
    g_rev = 100 * (f25["revenue"] / f24["revenue"] - 1)
    tay = next(r for r in sp["rec_ageing"]["rows"] if r["customer"] == TAYF)
    tay_t = tay["b0_90"] + tay["b91_180"] + tay["b181_365"] + tay["over_365"]
    tay_90 = tay["b91_180"] + tay["b181_365"] + tay["over_365"]
    dso = {"FY2024": 365 * f24["trade_receivables"] / f24["revenue"], "FY2025": 365 * f25["trade_receivables"] / f25["revenue"],
           "9M2026": 273 * m9["trade_receivables"] / m9["revenue"]}
    facts = sp["facts"]
    tay_acc = next(a for a in b["accounts"] if a["obligor_id"] == "CB09004")
    adj = m9["total_equity"] - tay["b181_365"] - m9["due_from_related"]
    tl = m9["total_liabilities"]
    shb12 = b["accounts"][0]["credits_12m_mn"]
    rim12 = sum(sum(a for _, a, _ in it) for it in sp["accounts"][1]["credit_items"])
    route = 100 * shb12 / (shb12 + rim12)
    last12 = [r for r in b["conduct"] if r["obligor_id"] == b["cif"]][-12:]
    pnw = {p["name"].split()[0]: p["pnw"] for p in sp["people"] if p.get("pnw")}
    def nw(k):
        q = pnw[k]
        return sum(a["value"] for a in q["assets"]) - sum(x["value"] for x in q["liabilities"])
    def own_shares(k):
        return sum(a["value"] for a in pnw[k]["assets"] if a["asset"] == "Shares")
    nw_f, nw_m = nw("Fahad"), nw("Majed")
    ta_f = sum(a["value"] for a in pnw["Fahad"]["assets"])
    out_f = nw_f - own_shares("Fahad")
    rows = sp["rec_ageing"]["rows"]
    rec_tot = sum(r["b0_90"] + r["b91_180"] + r["b181_365"] + r["over_365"] for r in rows)
    rec_90 = sum(r["b91_180"] + r["b181_365"] + r["over_365"] for r in rows)
    non_tay = rec_tot - tay_t
    P = {"header": {"related": f"Yes — {LAB} (CIF CB09005, sister company)",
                    "date": "2026-10-13", "type": "Renewal + increase"},
         "cfr": "CFR/RUH/2026/0612", "unit_head": "Hind Al-Subaie",
         "action": ("Renew the working-capital facilities of SAR 95.0m approved under CC/2025/031 dated 20/02/2025 and increase them to SAR 140.0m "
                    "(short-term Murabaha SAR 40.0m to 65.0m, letters of credit SAR 30.0m to 40.0m, trust receipts SAR 15.0m to 25.0m, letters of guarantee "
                    "SAR 10.0m unchanged), with the warehouse term loan (SAR 6.5m) running off; total facilities SAR 146.5m; group cap SAR 110.0m to SAR 155.0m."),
         "fees": "Study fee 0.20% of the increase of SAR 45.0m (SAR 90,000); documentation fee SAR 5,000. Murabaha and trust receipts at 3M SAIBOR + 1.75% "
                 "(floor 5.75%), unchanged; Al Rimal Commercial Bank prices its Murabaha at 3M SAIBOR + 1.90% (offer letter ARCB/RUH/26/118 of 10/02/2026).",
         "security": ["Working-capital limits (SAR 140.0m): personal guarantees of Fahad Saad Al-Naseem (net worth SAR "
                      f"{nw_f:,.1f}m, statement 31/08/2026) and Majed Saad Al-Naseem (SAR {nw_m:,.1f}m, 31/08/2026) — existing; corporate guarantee of Naseem Holding Co. — existing; "
                      "promissory note SAR 146.5m (new, replacing SAR 101.5m).",
                      "Letters of credit and guarantee: cash margin 10%; LCs issued to the order of the Bank, goods insured with the Bank as loss payee — existing.",
                      "Warehouse term loan (SAR 6.5m) and all limits: first-degree mortgage over the warehouse, plot 18/4, Second Industrial City, Riyadh (deed 310118004427; "
                      "market value SAR 31.5m, forced-sale value SAR 24.0m, valuation 14/08/2025); insurance SAR 28.0m to 28/02/2027, the Bank loss payee — existing."],
         "tnc": ["Working-capital limits: Murabaha drawn against invoices of hospitals and clinics, each draw up to 120 days; no draw against invoices of related parties.",
                 "Working-capital limits: trust receipts settled from the sale proceeds of the financed goods, maximum 120 days.",
                 "Letters of credit: for imports of medical goods from the suppliers on the approved list; usance up to 90 days.",
                 "All limits: route not less than 75% of turnover through the Bank (12 months to 30/09/2026: "
                 f"{route:.0f}% of the receipts of both banks).",
                 "All limits: audited financial statements within 120 days of year end; quarterly receivables ageing within 30 days of quarter end.",
                 "Status of existing conditions (CC/2025/031): 1 routing — complied; 2 audited FS — complied (FY2025 signed 21/04/2026); 3 quarterly ageing — complied; "
                 "4 inform the Bank of new related-party trading — not complied; 5 annual warehouse valuation — not complied (last 14/08/2025)."],
         "references": ["References: CC/2017/052 (25/04/2017, SAR 35m), CC/2021/163 (30/09/2021, SAR 70m, cap 80m), CC/2025/031 (20/02/2025, SAR 95m, cap 110m); "
                        "credit file request CFR/RUH/2026/0612 dated 13/10/2026."],
         "background": ["Dar Al Naseem Medical Supplies Co. (CR 1010384527, Riyadh), incorporated 15/02/2009, LLC, capital SAR 30.0m; 80% Naseem Holding Co. "
                        "(Fahad Saad Al-Naseem 60%, Majed Saad Al-Naseem 40%), 20% Fahad Saad Al-Naseem. Imports and distributes medical consumables, hospital "
                        "equipment and laboratory supplies to government and private hospitals; staff 214, of whom 58 Saudi (Nitaqat Medium Green, 27.1% vs 21.0% minimum).",
                        f"Since 02/2025 a regional distributor, {TAYF}, covers the Eastern and Southern regions on 120-day terms (31.0% of FY2025 sales; as per business, a third-party distributor). "
                        f"Group: Naseem Holding Co. (parent), {LAB} (sister, laboratory equipment servicing). Sales FY2025: government hospitals 18.4%, private hospitals "
                        "and clinics 50.6%; purchases: Nordmed Instruments GmbH, Germany 26.9% (LC 90 days usance), Pacific Rim Medical Consumables Ltd, Malaysia 19.6% (LC at sight), "
                        "Gulf Surgical Supplies Co., KSA 11.2% (45 days)."],
         "shareholders": [["Naseem Holding Co.", "—", "Saudi company", "80.0%", "—"], ["Fahad Saad Al-Naseem (Chairman and GM)", "1965", "Saudi", "20.0% (68% look-through)", "Yes"],
                          ["Majed Saad Al-Naseem (Director, via holding)", "1969", "Saudi", "32% look-through", "Yes"]],
         "relationship": [f"Customer since 02/05/2017. Credit turnover in the main account SAR {shb12:,.1f}m in the 12 months to 30/09/2026 (routing about {route:.0f}%); "
                          f"utilisation SAR 75.9m of SAR 95.0m (80%) at 30/09/2026 (Murabaha 99%, trust receipts 99%, LCs 61%, LGs 31%); no past dues in the last 12 months; one cheque "
                          "returned in 02/2026 (signature mismatch, regularised the same week).",
                          "Limit history: SAR 35m (2017), SAR 70m (2021), SAR 95m (2025)."],
         "conduct_table": {"cols": ["Quarter", "Credit turnover", "Average balance", "Average utilisation", "Past dues", "Returned cheques"],
                           "rows": [[q, f"{sum(r['credit_turnover_mn'] for r in rs):,.1f}", f"{sum(r['avg_balance_mn'] for r in rs) / 3:,.1f}",
                                     f"{sum(r['utilisation_pct'] for r in rs) / 3:.0f}%", "Nil", str(sum(r['returned_cheques_n'] for r in rs))]
                                    for q, rs in (("Q4 2025", last12[0:3]), ("Q1 2026", last12[3:6]), ("Q2 2026", last12[6:9]), ("Q3 2026", last12[9:12]))],
                           "widths": [0.16, 0.17, 0.17, 0.17, 0.16, 0.17]},
         "justification": [f"Incorporated 2009; revenue SAR {f25['revenue']:,.1f}m in FY2025 (PY {f24['revenue']:,.1f}m, +{g_rev:.1f}%) and SAR {m9['revenue']:,.1f}m in 9M2026, "
                           f"net profit SAR {f25['net_profit']:,.1f}m (PY {f24['net_profit']:,.1f}m); as per business, the distribution agreement of 02/2025 opens the Eastern and Southern regions.",
                           "Murabaha and trust receipts are 99% utilised at 30/09/2026; as per business, LC demand rises with imports (FY2025 imports 46.5% of purchases). "
                           f"{RIMAL} offers SAR 45.0m today (10/02/2026); the increase keeps the Bank at {route:.0f}% of receipts. Customer since 2017, no past dues, "
                           f"warehouse (FSV SAR 24.0m) mortgaged to the Bank, guarantors' net worth SAR {nw_f + nw_m:,.1f}m. Business recommends approval."]}
    P["credit"] = [
        ("Growth and cash: what the accounts and the Bank's data say", [
            f"Revenue rose to SAR {f25['revenue']:,.1f}m in FY2025 (PY {f24['revenue']:,.1f}m, <b>+{g_rev:.1f}%</b>). <u>Upon checking the Bank's account data, credit "
            f"turnover rose only {g_cred:.0f}%</u> (SAR {cy['2025']:,.1f}m in calendar 2025 vs SAR {cy['2024']:,.1f}m in 2024). Over the 12 months to 30/09/2026 the "
            f"statements of both banks show customer receipts equal to {100 * facts['collections_ratio']:.0f}% of VAT-inclusive sales (normal 95-100%), while the VAT "
            f"returns (standard-rated sales SAR {sum(r['taxable_sales'] for r in sp['vat']):,.1f}m) match booked revenue (SAR {facts['rev12']:,.1f}m) for the same 12 months: the sales are invoiced but not collected.",
            f"Receivable days rose to {dso['FY2025']:.0f} (FY2024 {dso['FY2024']:.0f}) and {dso['9M2026']:.0f} at 30/09/2026; trade receivables SAR {m9['trade_receivables']:,.1f}m "
            f"at 30/09/2026 (FY2025 {f25['trade_receivables']:,.1f}m; FY2024 {f24['trade_receivables']:,.1f}m). Operating cash flow was negative SAR {-f25['operating_cash_flow']:,.1f}m in FY2025 and SAR {-m9['operating_cash_flow']:,.1f}m in 9M2026, "
            f"funded by short-term borrowings (SAR {m9['short_term_borrowings']:,.1f}m at 30/09/2026 vs {f24['short_term_borrowings']:,.1f}m at FY2024)."]),
        ("The distributor", [
            f"{TAYF} took SAR 78.0m or <b>31.0% of FY2025 sales</b> (34% in 2026 per management). It is presented as a 'third-party distributor' in the top-customers list "
            f"and the request letter, but the FY2025 audited accounts (Note 15) disclose it as 'an entity owned by a relative of a shareholder', and the Bank's records show it is "
            f"<u>owned by Sultan Majed Al-Naseem, son of director Majed Saad Al-Naseem</u>, established on 09/02/2025, a week before the agreement. The AML questionnaire declares no "
            "other related parties, and condition 4 of CC/2025/031 (inform the Bank of new related-party trading) was not complied with.",
            f"Its receivable is SAR {tay_t:,.1f}m, <b>{100 * tay_t / m9['trade_receivables']:.0f}% of trade receivables</b>, of which SAR {tay_90:,.1f}m ({100 * tay_90 / tay_t:.0f}%) is over 90 days "
            f"and SAR {tay['b181_365']:,.1f}m over 180 days against 120-day terms. In 12 months it paid SAR {facts['tayf_collected12']:,.1f}m against SAR "
            f"{facts['tayf_rev12'] * 1.15:,.1f}m invoiced (VAT included). Its own account with the Bank received only SAR {tay_acc['credits_12m_mn']:,.1f}m in the same period, "
            "less than half of what it bought: the stock is not visibly being sold on. We cannot exclude that part of the FY2025 growth is goods parked with a family-owned entity."]),
        ("Group: sister company classified at another bank", [
            f"Fahad Saad Al-Naseem's SIMAH report (08/10/2026) shows his guarantee of SAR 22.0m for {LAB} at {RIMAL} <u>classified substandard in 07/2026</u> "
            f"(90+ days past due from 05/2026). The same company has a SAR 5.0m LG line with the Bank (SAR 4.2m outstanding), two cheques returned unpaid in 04/2026 and "
            f"06/2026, and is rated B- (BB in 2021). The business request does not mention it. The borrower is owed SAR {m9['due_from_related']:,.1f}m by the sister "
            "(FY2024 3.1m); the risk is that cash from the borrower supports the sister."]),
        ("Financials and adjusted ratios", [
            "Auditor Basma & Partners Chartered Accountants (unlisted firm, not on the Bank's panel), unqualified opinion on FY2024 (signed 17/04/2025) and FY2025 "
            "(21/04/2026); 9M2026 in-house accounts prepared by the Finance Manager, unaudited. The figures are in the business request (section 8); credit's re-performance:",
            {"table": _cycle(sp)},
            [f"Gross margin {100 * f25['gross_profit'] / f25['revenue']:.1f}% in FY2025 (FY2024 {100 * f24['gross_profit'] / f24['revenue']:.1f}%) and "
             f"{100 * m9['gross_profit'] / m9['revenue']:.1f}% in 9M2026: the distributor is sold at lower margins.",
             f"If the distributor's receivable over 180 days (SAR {tay['b181_365']:,.1f}m) and the amount due from the sister (SAR {m9['due_from_related']:,.1f}m) are netted off, "
             f"adjusted net worth is <b>SAR {adj:,.1f}m</b> (reported {m9['total_equity']:,.1f}m) and adjusted leverage <b>{tl / adj:.2f}x</b> (reported {tl / m9['total_equity']:.2f}x).",
             f"Composition of current assets at 30/09/2026 (SAR {m9['current_assets']:,.1f}m): trade receivables {100 * m9['trade_receivables'] / m9['current_assets']:.0f}%, "
             f"inventory {100 * m9['inventory'] / m9['current_assets']:.0f}%, cash {100 * m9['cash'] / m9['current_assets']:.0f}%. Receivables over 90 days SAR {rec_90:,.1f}m "
             f"({100 * rec_90 / rec_tot:.0f}%); top 2 debtors (the distributor and the Ministry hospitals cluster) {100 * (tay_t + 27.9) / rec_tot:.0f}%.",
             f"9M2026 annualised: revenue SAR {m9['revenue'] * 12 / 9:,.1f}m (FY2025 {f25['revenue']:,.1f}m, +{100 * (m9['revenue'] * 12 / 9 / f25['revenue'] - 1):.0f}%), net profit "
             f"SAR {m9['net_profit'] * 12 / 9:,.1f}m (FY2025 {f25['net_profit']:,.1f}m), while receivables rose SAR {m9['trade_receivables'] - f25['trade_receivables']:,.1f}m in nine months.",
             f"Bank debt SAR {m9['short_term_borrowings'] + m9['current_portion_ltd'] + m9['long_term_borrowings']:,.1f}m at 30/09/2026 (FY2024 {f24['short_term_borrowings'] + f24['current_portion_ltd'] + f24['long_term_borrowings']:,.1f}m). "
             f"With the increase, funded short-term lines would reach SAR 120.0m (the Bank 90.0, {RIMAL} 30.0) against SAR {non_tay + m9['inventory']:,.1f}m of receivables "
             f"outside the distributor plus inventory: <u>the increase is only covered if the distributor's receivable is counted</u>."]]),
        ("Security", [
            "The warehouse valuation dated 14/08/2025 is older than 12 months (condition 5 of CC/2025/031 not complied); market value SAR 31.5m, FSV SAR 24.0m covers "
            f"{100 * 24.0 / 146.5:.0f}% of the proposed facilities. Guarantors' net worth: Fahad SAR {nw_f:,.1f}m (31/08/2026), of which SAR {own_shares('Fahad'):,.1f}m "
            f"({100 * own_shares('Fahad') / ta_f:.0f}% of assets) is shares of the holding and the borrower at book value; outside the group SAR {out_f:,.1f}m (real estate SAR 38.1m at "
            f"owner's valuation, cash SAR 11.9m, listed shares SAR 6.3m). Majed SAR {nw_m:,.1f}m, of which SAR {own_shares('Majed'):,.1f}m "
            f"({100 * own_shares('Majed') / sum(a['value'] for a in pnw['Majed']['assets']):.0f}%) is his 40% of the holding. Real-estate valuations not provided."]),
        ("Credit bureau and other banks", [
            f"SIMAH company report (08/10/2026, score 702, 2 enquiries in 6 months): limits SAR 146.5m with two banks, outstanding SAR 120.2m, no overdue, no defaults.",
            {"table": {"cols": ["Bank (SAR m)", "Facility", "Limit", "Outstanding", "Pricing", "Source"],
                       "rows": [["Sandstone Harbour Bank", "Murabaha, LC, TR, LG, term loan", "101.5", "82.4", "3M SAIBOR + 1.75-2.00%", "Bank records = SIMAH"],
                                [RIMAL, "Short-term Murabaha", "30.0", "29.1", "3M SAIBOR + 1.90%", "Statement 30/09/2026 = SIMAH"],
                                [RIMAL, "Letters of credit", "15.0", "8.7", "0.30% p.q.", "Statement 30/09/2026 = SIMAH"],
                                ["Total", "", "146.5", "120.2", "", "Reconciled"]], "bold_last": True,
                       "widths": [0.22, 0.22, 0.08, 0.13, 0.15, 0.20]}},
            f"Consumer reports (08/10/2026): Fahad 731, own facilities current, <u>guaranteed facility of {LAB} substandard</u>; Majed 748, current. "
            f"{RIMAL}'s offer letter (10/02/2026) is secured by Fahad's guarantee only, with no mortgage: the Bank alone holds the warehouse."]),
        ("Effects of the current market situation", [
            "Imports are 46.5% of FY2025 purchases (Germany 26.9%, Malaysia 19.6%). As per business, sea freight and lead times rose in 2025-26 on the Red Sea "
            f"routing; inventory days are {273 * m9['inventory'] / m9['cost_of_sales']:.0f} at 30/09/2026 (FY2024 {365 * f24['inventory'] / f24['cost_of_sales']:.0f}), so no build-up of stock is visible. "
            "Government hospital clusters (18.4% of sales) pay in 90-120 days; a slowdown in government payments would lengthen the cash cycle further. The SAR peg removes "
            "currency risk on USD purchases; EUR purchases (Germany) are not hedged (not clarified by business)."]),
        ("Exceptions and other observations", [[
            "Exception: group exposure SAR 151.5m above the cap of SAR 110.0m (increase to SAR 155.0m requested).",
            "Existing conditions not complied: related-party trading not reported; valuation not renewed.",
            f"Related-party sales of SAR 78.0m presented as third-party; the distributor's financials and trade licence not provided.",
            "What business says vs what credit could verify: 'growth of 38%' (booked; cash receipts +9%); 'third-party distributor' (owned by a director's son); "
            f"'no changes in ownership and no other facilities' (true for the borrower; the sister is classified at {RIMAL})."]])]
    P["strengths"] = [f"Relationship since 2017; {route:.0f}% of receipts routed through the Bank; no past dues in 12 months; warehouse (FSV SAR 24.0m) mortgaged to the Bank only.",
                      f"Outside the distributor, receivables of SAR {non_tay:,.1f}m are spread over the Ministry cluster (SAR 27.9m), two private groups (SAR 17.4m) and 212 accounts (SAR 11.0m).",
                      "Import suppliers financed through the Bank's LCs (Nordmed 26.9%, Pacific Rim 19.6% of FY2025 purchases); LC line 61% used at 30/09/2026, no past dues.",
                      f"Fahad Saad Al-Naseem's net worth outside the group SAR {out_f:,.1f}m (31/08/2026)."]
    P["recommendation_lead"] = ("Credit division supports the renewal but <u>not the full increase</u>: the growth that justifies it is booked to a family-owned "
                                "distributor that pays less than half of what it buys, and the group has a classified company that the request does not disclose.")
    P["recommendation"] = ["Renew the facilities of SAR 95.0m for 12 months and the warehouse term loan (SAR 6.5m, running off).",
                           "Increase limited to SAR 15.0m: letters of credit SAR 30.0m to 40.0m and short-term Murabaha SAR 40.0m to 45.0m; trust receipts unchanged "
                           "at SAR 15.0m; total facilities SAR 116.5m (requested 146.5).",
                           "Murabaha and trust receipts under a monthly borrowing base: 80% of receivables under 120 days excluding the distributor and related parties, "
                           "plus 50% of inventory.", "Group exposure cap SAR 125.0m (requested 155.0): borrower SAR 116.5m and Naseem Lab Systems Co. SAR 5.0m = SAR 121.5m.",
                           "Security as in section 3 (personal guarantees, corporate guarantee of the holding, warehouse mortgage, promissory note reduced to SAR 116.5m).",
                           "Internal rating: credit proposes BBB- (business: BBB unchanged) for the related-party concentration and the classified sister.",
                           f"{LAB}: freeze the LG line at the outstanding SAR 4.2m; no new issuance; Early Warning watch.",
                           "Approval authority: Credit Committee."]
    P["conditions"] = [f"Prior to limit loading: written disclosure of {TAYF} as a related party with its trade licence, ownership and 2025 accounts; RM to visit its Dammam warehouse.",
                       "Prior to limit loading: new warehouse valuation by a panel valuer.",
                       f"Distributor receivable reduced to SAR 60.0m by 31/03/2027; sales to it beyond that on cash or LC terms; no new related-party customer without the Bank's consent.",
                       f"Group to provide the regularisation plan of {LAB} with {RIMAL} within 60 days; no advances from the borrower to the sister (due from capped at SAR 5.0m).",
                       "Monthly receivables ageing and borrowing-base certificate signed by the Finance Manager; quarterly review by the regional head."]
    P["analyst"], P["vp"], P["authority"] = "Lama Al-Mutairi", "Abdullah Al-Zahrani", "Credit Committee"
    P["ask_summary"] = {"one_line": "Renew SAR 95m working-capital lines and increase to SAR 140m (STL 65, LC 40, TR 25, LG 10) + warehouse loan 6.5 running off.",
                        "requested_total_sar": 146_500_000, "new_money_sar": 45_000_000, "credit_recommends_total_sar": 116_500_000}
    return P


def _fin(sp):
    from ops.r16_customers.proposal import fin_table
    return fin_table(sp)


def _cycle(sp):
    from ops.r16_customers.proposal import cycle_table
    return cycle_table(sp)


ASK = """# Customer 1 — Dar Al Naseem Medical Supplies Co. (Part A: RM side)

**Who:** existing customer since 2017 (CIF CB09001, CR 1010384527), Riyadh medical-supplies distributor, part of Naseem
Holding Group. **Case:** renewal + increase.

## What Anne does

Deal Desk → **New proposal** → upload the documents (any mix of Word, PDF and photos, several at once): everything in
`pdf/` (or `word/`; the photos in `images/` for the key pages). CreditProbe should recognise the CR number as an existing
customer and pull Borrower 360 (accounts, deposits, facilities, conduct, group graph with the sister company and the
distributor, EWS, ratings).

## The ask (type in the chat box)

> Renew Dar Al Naseem's SAR 95m facilities and increase them to SAR 140m: Murabaha 40 to 65, LCs 30 to 40, trust receipts 15 to 25, LGs 10 unchanged.

## RM notes (type or paste in "RM notes")

> Met Fahad Al-Naseem on 12 Oct. Growth of 38% in 2025 comes from the new regional distributor Al Tayf Healthcare (Eastern and Southern regions, since Feb 2025, 120-day terms). Utilisation is at 80% and LC demand is rising. Rimal Bank is offering more lines; we want to stay main banker. Warehouse mortgage and partners' guarantees stay. Keep pricing at SAIBOR + 1.75%.

## What a good business request shows / what credit will find (ANSWER_KEY.md §C1, `reference/reference_proposal.pdf`)

The business request should carry the ask, the facilities table, security, T&Cs, group exposure (SAR 106.5m today vs cap
110m), background, relationship (since 2017, ~82% of receipts routed, 80% utilisation), financials (+38% revenue) and the RM's
justification, every figure traced. Credit will find: Bank credits +9% vs revenue +38%; the distributor (31% of sales) is
owned by a director's son and pays less than half of what it buys (SAR 92.6m receivable, 59% over 90 days); the sister
company is classified substandard at Al Rimal Commercial Bank; the warehouse valuation is stale. Recommendation: renew,
increase only SAR 15m with a borrowing base; cap SAR 125m; conditions.
"""

ANSWER = """## C1 — Dar Al Naseem Medical Supplies Co. (existing, renewal + increase; Part A)

**The story a committee would debate:** a long-standing, well-run distributor posts 38% growth and asks for 47% more
limits. The growth is real on paper (audited, VAT-filed) but the cash is not arriving, because almost a third of sales go to
a new distributor owned by the family, and the group already has a company in trouble at another bank.

| # | Twist | Where it is found (join) | What the credit comments say |
|---|---|---|---|
| 1 | Revenue +38.0% (FY2025) vs Bank credit turnover +9% (CY2025 vs CY2024) | audited FS FY2024/FY2025 × Bank data `dd_account_conduct` (CB09001, Jan 2024 – Sep 2026); statements of both banks Oct 2025–Sep 2026: customer receipts ≈ 80% of VAT-inclusive sales while VAT returns = revenue | sales invoiced, not collected; DSO 97 → 163 → 198 days; OCF −35.0m (FY2025), −23.2m (9M2026) |
| 2 | A related-party distributor presented as third party | top customers list ("Third-party distributor", 31.0%) and request letter × FY2025 audited Note 15 ("entity owned by a relative of a shareholder", SAR 78.0m) × Bank data: Al Tayf (CB09004) owned by Sultan Majed Al-Naseem, son of director Majed (b360 graph), established 09/02/2025 × AML questionnaire (no other related parties) × CC/2025/031 condition 4 not complied | the distributor's receivable SAR 92.6m = 62% of receivables, 59% over 90 days; it paid SAR 44.6m of SAR 106.3m invoiced; its own account received only SAR 34.2m in 12 months |
| 3 | Sister company classified at another bank | Fahad's SIMAH consumer report (guarantee of Naseem Lab Systems at Al Rimal, substandard 07/2026) × Bank data (CB09005: B- rating, 2 returned cheques 04 and 06/2026, LG line 5.0/4.2) × request letter silent | freeze the sister's line; no support from the borrower (due from SAR 5.0m) |
| 4 | Stale collateral | valuation report dated 14/08/2025 (> 12 months at 21/10/2026, checklist `expired`) × CC/2025/031 condition 5 | new valuation before loading |
| 5 | Adjusted ratios | in-house 9M2026: TNW SAR 92.0m less Al Tayf > 180 days (SAR 19.9m) and due from the sister (SAR 5.0m) | adjusted TNW SAR 67.1m, adjusted leverage 2.44x (reported 1.78x) |

**Reference recommendation** (`c1_dar_al_naseem/reference/reference_proposal.pdf`): renew SAR 95.0m (+ term loan 6.5 running
off); increase only SAR 15.0m (LC 30 → 40, Murabaha 40 → 45, TR unchanged); borrowing base excluding the distributor and
related parties; total SAR 116.5m (asked 146.5); cap SAR 125.0m (asked 155.0); CPs: disclose the distributor as related
with its licence and accounts, new valuation; distributor receivable to SAR 60m by 31/03/2027; sister's plan within 60 days.
"""
