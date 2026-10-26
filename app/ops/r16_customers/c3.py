"""Customer 3: Nukhba Polymer Industries Co. (fictional). New to bank, takeover of another bank's facilities.

Twist: the request asks the Bank to take over Coastal Gulf Bank's facilities at 3M SAIBOR + 1.25% (vs 2.25% there) and
states "no delays or restructuring"; the SIMAH company report shows the Coastal Gulf term loan past due 31-60 days in
01-02/2026 and restructured on 18/03/2026 (four instalments deferred, maturity 31/12/2027 -> 30/09/2028), which the
other bank's statement (new maturity) and the FY2025 audited subsequent-events note confirm; the DSCR covenant there
(1.25x) was breached (FY2025 0.92x) on falling margins; the machinery charge is first-ranking to that bank.

Term-loan schedule (one story across every document): limit SAR 120.0m drawn 2021, SAR 120.0m outstanding at 31/12/2023,
15 quarterly instalments of SAR 8.0m from 30/06/2024 to 31/12/2027 (2024: 3 paid -> 96.0; 2025: 3 paid -> 72.0, the
31/12/2025 instalment unpaid); rescheduled 18/03/2026: the four instalments 31/12/2025 - 30/09/2026 deferred, balance
SAR 72.0m in 8 quarterly instalments of SAR 9.0m from 31/12/2026 to 30/09/2028. The request's 48-month term loan would
stretch that once more (16 x SAR 4.5m to 2030).
"""
from __future__ import annotations

import random

from ops.r16_customers import common, fin
from ops.r16_customers.ids import BANK, BY_KEY

CGB = "Coastal Gulf Bank"
TIB = "Tihama Investment Bank"


def spec() -> dict:
    ids = BY_KEY["c3"]
    co = {**ids, "legal_form": "Limited Liability Company", "incorporated": "2011-09-04", "capital_mn": 100.0, "shares_total": 100_000, "share_value": 1_000,
          "address": "Industrial Area 2, Street 214, Jubail Industrial City 35718", "phone": "+966 13 340 9921", "email": "finance@nukhba-polymer.example",
          "activity": "Manufacture of plastic packaging: PET preforms, HDPE drums and jerrycans, and stretch films; sale in the Kingdom and export to GCC markets.",
          "activity_short": "Manufacture of plastic packaging", "cr_issue": "2011-09-04", "cr_expiry": "2027-09-01", "cr_print": "2026-10-04",
          "aoa_amended": "2019-05-12", "vat_effective": "2018-01-01", "vat_frequency": "Monthly", "vat_cert_issue": "2018-01-11",
          "zakat": {"number": "ZC-2026-0412976", "fy_end": "2025-12-31", "issue": "2026-04-26", "expiry": "2027-04-30"},
          "nitaqat": {"establishment": "3-2290187", "band": "Medium Green", "rate": 26.9, "threshold": 23.0, "total": 386, "saudi": 104,
                      "issue": "2026-10-01", "expiry": "2026-12-31"},
          "shareholders": [{"name": "Saleh Ibrahim Al-Mansour", "id_number": "1027745196", "nationality": "Saudi", "shares": 60_000, "pct": 60.0},
                           {"name": "Khalid Ibrahim Al-Mansour", "id_number": "1031198472", "nationality": "Saudi", "shares": 40_000, "pct": 40.0}],
          "managers": [{"name": "Saleh Ibrahim Al-Mansour", "role": "Chairman and General Manager", "powers": "Sole signatory up to SAR 20m"},
                       {"name": "Khalid Ibrahim Al-Mansour", "role": "Director, Operations", "powers": "Jointly with the Chairman"}],
          "aoa_amendment_text": "Amended on 12/05/2019 to raise the capital from SAR 60m to SAR 100m for the PET preform line."}
    people = [
        {"key": "saleh", "name": "Saleh Ibrahim Al-Mansour", "id_number": "1027745196", "nationality": "Saudi", "dob": "1964-12-03", "id_issue": "2023-01-18",
         "id_expiry": "2033-01-17", "role": "Chairman and GM (60%)", "guarantor": True,
         "simah": {"date": "2026-10-09", "number": "SC-26-8801764", "score": 702, "worst": "Current on own facilities",
                   "facilities": [{"lender": CGB, "product": "Credit card", "limit": 0.2, "outstanding": 0.041, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Nukhba Polymer Industries Co.", "lender": CGB, "amount": 190.0, "status": "Restructured (03/2026)"},
                                  {"beneficiary": "Nukhba Polymer Industries Co.", "lender": TIB, "amount": 15.0, "status": "Current"}],
                   "history": "Own facilities current. Guaranteed term loan of Nukhba Polymer Industries Co. at Coastal Gulf Bank: 31-60 days past due "
                              "in 01-02/2026; restructured 18/03/2026."},
         "pnw": {"date": "2026-07-31",
                 "assets": [{"asset": "Shares", "description": "60% of Nukhba Polymer Industries Co. (book value)", "value": 83.2},
                            {"asset": "Real estate", "description": "Villa, Al Fanateer, Jubail", "value": 6.1},
                            {"asset": "Real estate", "description": "Commercial plot, Dammam (1,200 sq m)", "value": 11.5},
                            {"asset": "Cash and deposits", "description": "Current and deposit accounts", "value": 4.4}],
                 "liabilities": [{"liability": "Credit card", "description": CGB, "value": 0.041}]}},
        {"key": "khalid", "name": "Khalid Ibrahim Al-Mansour", "id_number": "1031198472", "nationality": "Saudi", "dob": "1970-04-19", "id_issue": "2021-08-02",
         "id_expiry": "2031-08-01", "role": "Director (40%)", "guarantor": False,
         "simah": {"date": "2026-10-09", "number": "SC-26-8801765", "score": 736, "worst": "Current (no delinquency)",
                   "facilities": [{"lender": TIB, "product": "Real-estate finance", "limit": 2.4, "outstanding": 1.6, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [], "history": "24 of 24 months current."}},
    ]
    st = fin.statement
    fy23 = st({"revenue": 301.5, "cost_of_sales": 247.8, "operating_expenses": 19.1, "finance_cost": 9.6, "zakat": 1.6, "depreciation": 20.9,
               "cash": 11.2, "trade_receivables": 57.9, "inventory": 48.8, "other_current_assets": 7.6, "ppe": 238.0, "other_noncurrent_assets": 3.9,
               "short_term_borrowings": 51.0, "trade_payables": 44.1, "current_portion_ltd": 24.0, "long_term_borrowings": 96.0, "end_of_service": 8.2,
               "share_capital": 100.0, "statutory_reserve": 16.2, "retained_earnings": 10.7})
    fy24 = st({"revenue": 318.2, "cost_of_sales": 270.2, "operating_expenses": 20.4, "finance_cost": 11.2, "zakat": 1.4, "depreciation": 21.8,
               "cash": 9.1, "trade_receivables": 61.2, "inventory": 52.0, "other_current_assets": 8.1, "ppe": 226.0, "other_noncurrent_assets": 4.0,
               "short_term_borrowings": 58.0, "trade_payables": 47.5, "current_portion_ltd": 32.0, "long_term_borrowings": 64.0, "end_of_service": 8.9,
               "share_capital": 100.0, "statutory_reserve": 17.7, "retained_earnings": 14.2})
    fy25 = st({"revenue": 296.4, "cost_of_sales": 257.3, "operating_expenses": 20.9, "finance_cost": 12.4, "zakat": 1.0, "depreciation": 22.6,
               "cash": 6.2, "trade_receivables": 58.4, "inventory": 49.7, "other_current_assets": 8.8, "ppe": 214.6, "other_noncurrent_assets": 4.1,
               "short_term_borrowings": 62.3, "trade_payables": 44.8, "current_portion_ltd": 40.0, "long_term_borrowings": 32.0, "end_of_service": 9.4,
               "share_capital": 100.0, "statutory_reserve": 18.2, "retained_earnings": 18.5})
    m9 = st({"revenue": 214.1, "cost_of_sales": 187.0, "operating_expenses": 15.6, "finance_cost": 9.6, "zakat": 0.0, "depreciation": 17.1,
             "cash": 4.1, "trade_receivables": 57.0, "inventory": 54.3, "other_current_assets": 9.0, "ppe": 201.5, "other_noncurrent_assets": 4.2,
             "short_term_borrowings": 62.0, "trade_payables": 42.2, "current_portion_ltd": 36.0, "long_term_borrowings": 36.0, "end_of_service": 9.8,
             "share_capital": 100.0, "statutory_reserve": 18.2, "retained_earnings": 20.4})
    m9["months"] = 9
    fy23["operating_cash_flow"] = 34.0
    fy24["operating_cash_flow"] = fin.ocf(fy23, fy24)
    fy25["operating_cash_flow"] = fin.ocf(fy24, fy25)
    m9["operating_cash_flow"] = fin.ocf(fy25, m9)
    fs = {"FY2023": fy23, "FY2024": fy24, "FY2025": fy25, "9M2026": m9}
    aud = "Rawasi Audit & Advisory"
    audit = {"FY2024": {"auditor": aud, "opinion": "Unqualified", "qawaem": "QW-2025-2055104486", "city": "Dammam", "partner": "Majid Al-Ghamdi", "licence": "441",
                        "signed": "2025-04-20"},
             "FY2025": {"auditor": aud, "opinion": "Unqualified", "qawaem": "QW-2026-2055104486", "city": "Dammam", "partner": "Majid Al-Ghamdi", "licence": "441",
                        "signed": "2026-04-15"}}
    notes = {"FY2024": [("Note 16 — Borrowings", f"Term loan from {CGB} SAR 96,000,000 (2023: 120,000,000), repayable in 15 quarterly instalments of SAR 8,000,000 "
                                                  "from 30/06/2024 to 31/12/2027, secured by a first-ranking charge over the machinery; financial covenant DSCR not below 1.25x.")],
             "FY2025": [("Note 16 — Borrowings", f"Term loan from {CGB} SAR 72,000,000, of which SAR 40,000,000 current at 31/12/2025; the instalment "
                                                  "of SAR 8,000,000 due 31/12/2025 was unpaid at the year end. The DSCR covenant (1.25x) was not met at 31/12/2025; the lender has not demanded repayment. Short-term Murabaha and LC acceptances "
                                                  "SAR 62,300,000."),
                        ("Note 9 — Revenue", "Export sales to GCC customers 24% (2024: 26%). Prices of PET resin rose 18% in 2025; selling prices lagged."),
                        ("Note 24 — Subsequent events", f"On 18/03/2026 the Company and {CGB} agreed to reschedule the term loan: the four instalments due "
                                                         "31/12/2025 to 30/09/2026 (SAR 32,000,000) were deferred; the balance of SAR 72,000,000 is repayable in 8 quarterly "
                                                         "instalments of SAR 9,000,000 from 31/12/2026, final maturity extended from 31/12/2027 to 30/09/2028.")]}
    rnd = random.Random("c3-vat")
    q4 = fin.series(74.6, 3, rnd, noise=0.05)
    rev12 = q4 + fin.series(214.1, 9, rnd, trend=0.04, noise=0.06)
    vat = []
    for ym, r in zip(fin.months("2025-10", 12), rev12):
        tot = r * (1 + 0.03 * (rnd.random() - 0.5))
        zr = round(tot * rnd.uniform(0.21, 0.27), 3)
        std = round(tot - zr, 3)
        vat.append({"period": ym, "from": f"{ym}-01", "to": fin.month_end(ym), "taxable_sales": std, "zero_rated": zr, "output_vat": round(0.15 * std, 3),
                    "input_vat": round(0.15 * tot * rnd.uniform(0.70, 0.78), 3), "filed_on": fin.add_days(fin.month_end(ym), 17)})
    gross = [v["taxable_sales"] * 1.15 + v["zero_rated"] for v in vat]
    coll = fin.series(sum(gross) * 0.975, 12, random.Random("c3-coll"), noise=0.06, nd=6)
    mlist = fin.months("2025-10", 12)
    r2 = random.Random("c3-stmt")
    cgb_cr = common.credit_items([c * 0.82 for c in coll], [("Gulf Beverage Bottling Co. — payment", 5, 3), ("Eastern Dairy Foods Co. — payment", 12, 2),
                                                            ("Export proceeds (GCC customers)", 18, 3), ("Local customers — collections", 25, 3)], r2)
    tib_cr = common.credit_items([c * 0.18 for c in coll], [("Local customers — collections", 9, 1), ("Export proceeds (GCC customers)", 22, 1)], r2)
    cgb_lay = [("LC settlement — PET resin imports", 0.36, 10), ("Local resin and masterbatch suppliers", 0.18, 16), ("Payroll transfer (WPS)", 0.10, 27),
               ("GOSI contribution", 0.01, 15), ("Electricity and utilities (factory)", 0.07, 8), ("VAT payment", 0.03, 28),
               ("Term loan instalment and profit", 0.11, 30), ("Murabaha repayment (net)", 0.14, 20)]
    tib_lay = [("Supplier payments", 0.7, 12), ("Freight and logistics", 0.3, 24)]
    cgb = {"bank": CGB, "number": "2201-558190-01", "iban": "SA6640000002201558190010", "type": "Current account (main operating)", "opening": 4.9,
           "issued": "2026-10-04", "months": mlist, "credit_items": cgb_cr, "debit_items": common.debit_items(cgb_cr, 4.9, 3.0, cgb_lay, r2), "returned": {}, "floor": 0.4}
    tib = {"bank": TIB, "number": "077-4410552-3", "iban": "SA2185000000774410552300", "type": "Current account", "opening": 1.5, "issued": "2026-10-06",
           "months": mlist, "credit_items": tib_cr, "debit_items": common.debit_items(tib_cr, 1.5, 1.0, tib_lay, r2), "returned": {}, "floor": 0.2}
    simah = {"date": "2026-10-09", "number": "SB-26-3301190", "score": 598, "enquiries": 3, "defaults": 0,
             "facilities": [{"lender": CGB, "product": "Term loan", "limit": 120.0, "outstanding": 72.0, "overdue": 0.0, "status": "Restructured", "opened": "2021-04-01",
                             "remark": "Rescheduled 18/03/2026; maturity 30/09/2028"},
                            {"lender": CGB, "product": "Short-term Murabaha", "limit": 40.0, "outstanding": 38.4, "overdue": 0.0, "status": "Current", "opened": "2021-04-01"},
                            {"lender": CGB, "product": "Letters of credit (incl. acceptances)", "limit": 30.0, "outstanding": 23.6, "overdue": 0.0, "status": "Current", "opened": "2021-04-01"},
                            {"lender": TIB, "product": "Letters of guarantee", "limit": 15.0, "outstanding": 9.2, "overdue": 0.0, "status": "Current", "opened": "2022-02-14"}],
             "history": f"Term loan with {CGB}: 31-60 days past due in 01/2026 and 02/2026 (instalment of SAR 8.0m due 31/12/2025 unpaid); "
                        "restructured on 18/03/2026 (four instalments deferred; maturity 30/09/2028). Other facilities current.",
             "enquiry_text": f"3 enquiries in the last 6 months: {BANK} (10/2026), Al Rimal Commercial Bank (07/2026), Arabian Crescent Bank (05/2026)."}
    other_banks = [{"bank": CGB, "offer_date": "2023-06-12", "offer_ref": "CGB/IND/23/0611", "offer_expiry": "2027-12-31", "offer_signed": "Faris Al-Shammari",
                    "facilities": [{"facility": "Term loan (machinery), quarterly SAR 8.0m", "limit": 120.0, "pricing": "3M SAIBOR + 2.25%", "tenor": "15 quarterly from 30/06/2024 to 31/12/2027"},
                                   {"facility": "Short-term Murabaha", "limit": 40.0, "pricing": "3M SAIBOR + 2.25%", "tenor": "up to 180 days"},
                                   {"facility": "Letters of credit (sight / usance 120 days)", "limit": 30.0, "pricing": "0.30% per quarter", "tenor": "per LC"}],
                    "security": "First-ranking charge over the machinery; personal guarantee of Saleh Ibrahim Al-Mansour; promissory note SAR 190,000,000.",
                    "offer_terms": ["Financial covenant: DSCR not below 1.25x, tested annually on audited accounts.", "Assignment of insurance over the machinery."],
                    "statement_date": "2026-09-30",
                    "statement": [{"facility": "Term loan (machinery) — rescheduled", "limit": 120.0, "outstanding": 72.0, "overdue": 0.0, "maturity": "30/09/2028"},
                                  {"facility": "Short-term Murabaha", "limit": 40.0, "outstanding": 38.4, "overdue": 0.0, "maturity": "rolling"},
                                  {"facility": "Letters of credit (incl. acceptances)", "limit": 30.0, "outstanding": 23.6, "overdue": 0.0, "maturity": "per LC"}],
                    "statement_notes": ["Term loan schedule as amended on 18/03/2026: 8 quarterly instalments of SAR 9.0m from 31/12/2026 to 30/09/2028."]},
                   {"bank": TIB, "offer_date": "2025-12-01", "offer_ref": "TIB/CORP/25/2290", "offer_expiry": "2026-11-30", "offer_signed": "Mazen Al-Qurashi",
                    "facilities": [{"facility": "Letters of guarantee", "limit": 15.0, "pricing": "0.80% p.a.", "tenor": "per LG"}],
                    "security": "Personal guarantee of Saleh Ibrahim Al-Mansour; 15% cash margin.", "statement_date": "2026-09-30",
                    "statement": [{"facility": "Letters of guarantee", "limit": 15.0, "outstanding": 9.2, "overdue": 0.0, "maturity": "per LG"}]}]
    req = {"date": "2026-10-08", "ref": "NPI/CEO/2026/41", "by": "Saleh Ibrahim Al-Mansour", "role": "Chairman and General Manager",
           "body": f"We would like to move our main banking relationship to {BANK}. We request the following facilities to take over our facilities "
                   f"with {CGB} (outstanding SAR 134,000,000 at 30/09/2026) and support our growth, at 3M SAIBOR + 1.25%:",
           "facilities": [{"facility": "Term loan (takeover), 48 months", "amount": 72.0, "purpose": f"Repayment of the {CGB} term loan"},
                          {"facility": "Short-term Murabaha", "amount": 45.0, "purpose": f"Working capital; takeover of the {CGB} Murabaha"},
                          {"facility": "Letters of credit (sight / usance 120 days)", "amount": 40.0, "purpose": "PET resin imports"}],
           "more": [f"We have an excellent track record with {CGB} with no delays or restructuring, and we are moving only because of pricing.",
                    "We offer a first-ranking charge over our machinery (to be released by the current bank on takeover) and the personal guarantee of the undersigned."]}
    resolution = {"date": "2026-10-07", "number": "PR-2026-05", "amount": 180.0, "persons": "Saleh Ibrahim Al-Mansour (Chairman and General Manager)",
                  "text": f"The partners resolved to obtain facilities from {BANK} up to SAR 180,000,000, to repay the facilities of {CGB}, and to grant a "
                          "charge over the machinery."}
    signatories = {"as_of": "2026-10-07", "rows": [
        {"name": "Saleh Ibrahim Al-Mansour", "id_number": "1027745196", "role": "Chairman and General Manager", "limit": "Up to SAR 20m alone", "mode": "Single / joint above"},
        {"name": "Khalid Ibrahim Al-Mansour", "id_number": "1031198472", "role": "Director, Operations", "limit": "Jointly", "mode": "Joint"}]}
    ag = [{"customer": "Gulf Beverage Bottling Co.", "b0_90": 13.9, "b91_180": 0.8, "b181_365": 0.0, "over_365": 0.0},
          {"customer": "Eastern Dairy Foods Co.", "b0_90": 8.2, "b91_180": 0.0, "b181_365": 0.0, "over_365": 0.0},
          {"customer": "GCC export customers (14)", "b0_90": 14.6, "b91_180": 1.9, "b181_365": 0.4, "over_365": 0.0}]
    used = sum(sum(r[k] for k in ("b0_90", "b91_180", "b181_365", "over_365")) for r in ag)
    ag.append({"customer": "Local customers (96)", "b0_90": round(m9["trade_receivables"] - used - 1.8 - 0.9, 3), "b91_180": 1.8, "b181_365": 0.9, "over_365": 0.0})
    top = {"year": 2025, "date": "2026-10-06",
           "customers": [{"name": "Gulf Beverage Bottling Co.", "relationship": "Third party", "sales": 65.2, "share": 22.0, "terms": "60 days"},
                         {"name": "Eastern Dairy Foods Co.", "relationship": "Third party", "sales": 41.5, "share": 14.0, "terms": "45 days"},
                         {"name": "GCC export customers (14)", "relationship": "Third parties", "sales": 71.1, "share": 24.0, "terms": "60-90 days, LC / open account"},
                         {"name": "Local customers (96)", "relationship": "Third parties", "sales": 118.6, "share": 40.0, "terms": "30-60 days"}],
           "suppliers": [{"name": "Orient Polymers Trading FZE", "country": "UAE", "purchases": 98.4, "share": 38.2, "terms": "LC 120 days usance"},
                         {"name": "Jubail Petrochemical Marketing Co.", "country": "KSA", "purchases": 61.0, "share": 23.7, "terms": "30 days"}]}
    collateral = [{"key": "machinery", "property": "Production machinery: 6 PET preform lines, 4 blow-moulding lines, 2 film extruders (Jubail plant, leased land)",
                   "owner": "Nukhba Polymer Industries Co.", "deed": "Leasehold — industrial lease JIC/IA2/214 (no title deed)",
                   "valuation": {"valuer": "Al Bunyan Asset Valuation Co.", "date": "2026-07-22", "mv": 162.0, "fsv": 105.0, "signed": "Eng. Talal Al-Juhani",
                                 "text": ["Machinery valued on depreciated replacement cost; average age 6.5 years; good condition.",
                                          f"Market value SAR 162,000,000; forced-sale value SAR 105,000,000. A first-ranking charge in favour of {CGB} is registered."]},
                   "deed_doc": None,
                   "insurance": {"number": "IAR-26-330871", "insurer": "Najm Al Khaleej Cooperative Insurance Co.", "sum": 175.0, "loss_payee": CGB,
                                 "from": "2026-01-01", "to": "2026-12-31", "text": "Industrial all risks including machinery breakdown."}}]
    site = {"date": "2026-10-14", "by": "Abeer Al-Omari", "met": "Saleh Ibrahim Al-Mansour; Eng. Ravi Menon (Plant Manager)",
            "premises": "Factory in Jubail Industrial City (leased land, own buildings and machinery)", "staff": 240,
            "summary": "Plant running two shifts; one of six PET lines idle for lack of orders.",
            "points": ["Two shifts instead of three since 2025; one PET preform line idle (management: temporary, awaiting a new beverage contract).",
                       "Raw-material stock adequate; finished goods for about 5 weeks.",
                       "Management explains the move by pricing; asked about the current bank's covenants, it said 'all in order'."]}
    aml = {"date": "2026-10-07", "by": "Saleh Ibrahim Al-Mansour", "pep": "No", "countries": "KSA, UAE, Kuwait, Bahrain, Oman, China (resin)", "cash": "No",
           "rating": "Medium", "ubos": [{"name": "Saleh Ibrahim Al-Mansour", "pct": 60.0, "pep": "No"}, {"name": "Khalid Ibrahim Al-Mansour", "pct": 40.0, "pep": "No"}]}
    return {"key": "c3", "co": co, "people": people, "fs": fs, "audit": audit, "notes": notes, "inhouse_by": "Fadi Nabil Haddad", "inhouse_date": "2026-10-11",
            "vat": vat, "accounts": [cgb, tib], "simah_company": simah, "consent": {"by": "Saleh Ibrahim Al-Mansour", "role": "Chairman and General Manager", "on": "2026-10-07"},
            "request": req, "resolution": resolution, "signatories": signatories, "other_banks": other_banks,
            "rec_ageing": {"as_of": "2026-09-30", "rows": ag}, "top": top, "collateral": collateral, "site_visit": site, "aml": aml,
            "skip": [{"doc_type": "title_deed", "subject": "*"}],
            "missing": [{"doc_type": "payables_ageing", "subject": None, "why": "Not provided"},
                        {"doc_type": "title_deed", "subject": "machinery", "why": "Leasehold land: no title deed; industrial lease agreement not provided"}],
            "facts": {"rev12": round(sum(rev12), 3)}}


def bank(sp: dict) -> dict:
    pid = "R16-C3"
    limits = [("L0", "", 0, "Total facilities", "", 0, 0.0, 0.0, 157.0, None, None, "", None, None, "", "", "", ""),
              ("T1", "L0", 1, f"Term loan (takeover of {CGB})", "TL", 1, 0.0, 0.0, 72.0, 0.0, None, "3M SAIBOR", 1.25, 5.25, "48 months", "16 quarterly instalments of SAR 4.5m", "", ""),
              ("T2", "L0", 1, "Short-term Murabaha", "TL", 1, 0.0, 0.0, 45.0, 0.0, None, "3M SAIBOR", 1.25, 5.25, "Up to 180 days per draw", "Bullet per draw", "", ""),
              ("T3", "L0", 1, "Letters of credit (sight / usance 120 days)", "LC_USANCE", 0, 0.0, 0.0, 40.0, 10.0, 0.20, "", None, None, "Usance up to 120 days", "", "", "0.20% per quarter")]
    ge = [{"entity_name": "Nukhba Polymer Industries Co. (no group entities)", "funded_existing_mn": 0.0, "total_existing_mn": 0.0,
           "funded_proposed_mn": 117.0, "total_proposed_mn": 157.0, "outstanding_mn": 0.0}]
    return {"cif": "", "proposal_id": pid, "unit": "Corporate Banking — Eastern Province", "branch": "Jubail Branch", "rm": "Abeer Al-Omari", "ro": "Hisham Al-Qahtani",
            "opened": "", "industry_code": "C2220 — Manufacture of plastics products", "purpose_code": "TO-02 Takeover of facilities",
            "collateral_code": "MC — Charge over machinery", "rating_existing": "—", "rating_proposed": "BB-", "review_date": "2027-10-31",
            "limits": common.limit_rows(pid, limits), "group_exposure": ge, "conduct": [], "accounts": []}


SAIBOR = 5.50  # 3M SAIBOR assumed for the debt-service test (stated in the comments)


def proposal_text(sp: dict, b: dict) -> dict:
    fs = sp["fs"]
    f24, f25, m9 = fs["FY2024"], fs["FY2025"], fs["9M2026"]
    pct = lambda a, t: 100 * a / t
    dscr25 = f25["ebitda"] / (f25["finance_cost"] + 32.0)          # 2025: 4 instalments of 8.0 due
    dscr24 = f24["ebitda"] / (f24["finance_cost"] + 24.0)          # 2024: 3 instalments of 8.0 due
    ann_e = m9["ebitda"] / 9 * 12
    funded = 72.0 + 38.4                                             # funded outstanding taken over
    ds_cur = 36.0 + funded * (SAIBOR + 2.25) / 100                   # CGB schedule: 4 x 9.0 in the next 12 months
    ds_new = 18.0 + funded * (SAIBOR + 1.25) / 100                   # requested: 16 x 4.5 over 48 months
    cl_ias1 = f25["current_liabilities"] + f25["long_term_borrowings"]
    cgb, tib = sp["accounts"]
    cr = lambda a: sum(x for mth in a["credit_items"] for _, x, _ in mth)
    rec = sp["rec_ageing"]["rows"]
    b90 = sum(r["b0_90"] for r in rec)
    tr = m9["trade_receivables"]
    pnw = sp["people"][0]["pnw"]
    pnw_a = sum(x["value"] for x in pnw["assets"])
    pnw_nw = pnw_a - sum(x["value"] for x in pnw["liabilities"])
    sh = pnw["assets"][0]["value"]
    dso = lambda f, d=365: d * f["trade_receivables"] / f["revenue"]
    dio = lambda f, d=365: d * f["inventory"] / f["cost_of_sales"]
    P = {"header": {"related": "No", "date": "2026-10-15", "type": "New (takeover)"}, "cfr": "CFR/EP/2026/0402", "unit_head": "Khalid Al-Otaibi",
         "action": (f"Approve new facilities of SAR 157.0m to Nukhba Polymer Industries Co. (new to bank) to take over its facilities with {CGB} "
                    "(outstanding SAR 134.0m at 30/09/2026): term loan SAR 72.0m (48 months), short-term Murabaha SAR 45.0m and letters of credit SAR 40.0m, "
                    "priced at 3M SAIBOR + 1.25% (floor 5.25%). Funded SAR 117.0m; the LG line of SAR 15.0m at Tihama Investment Bank stays there."),
         "fees": "Arrangement fee 0.50% on the term loan (SAR 360,000); study and documentation fee SAR 25,000.",
         "security": ["All limits: first-ranking charge over the machinery (market value SAR 162.0m, FSV SAR 105.0m, valuation 22/07/2026), to be released by "
                      f"{CGB} on takeover and registered to the Bank within 30 days of disbursement.",
                      f"All limits: personal guarantee of Saleh Ibrahim Al-Mansour (60%; net worth SAR {pnw_nw:,.1f}m as per statement of 31/07/2026).",
                      "All limits: promissory note SAR 157.0m signed by the authorised signatory.",
                      "Term loan: assignment of the machinery insurance (sum insured SAR 175.0m) with the Bank as loss payee.",
                      "LCs: title documents to order of the Bank; 10% cash margin."],
         "tnc": ["Term loan disbursed only to the current bank against its payoff letter and the release of its charge; no part to the customer.",
                 "Murabaha draws against supplier invoices for resin and masterbatch; maximum tenor 180 days per draw.",
                 "LCs for PET resin and masterbatch imports only; usance settled from own funds or Murabaha.",
                 "Route not less than 70% of turnover (about SAR 220m a year, 12-month statement credits SAR 312.7m) through the Bank within 6 months.",
                 "Financial covenant: DSCR not below 1.20x, tested on audited accounts.",
                 "Audited financial statements within 120 days of year end; quarterly management accounts within 45 days."],
         "references": [f"References: credit file request CFR/EP/2026/0402 (15/10/2026); customer's letter NPI/CEO/2026/41 (08/10/2026); partners' resolution "
                        "PR-2026-05 (07/10/2026, borrowing up to SAR 180.0m)."],
         "background": ["Nukhba Polymer Industries Co. (CR 2055104486, Jubail, CR valid to 01/09/2027), LLC incorporated 04/09/2011, capital SAR 100.0m "
                        "(raised from SAR 60.0m on 12/05/2019 for the PET preform line). Saleh Ibrahim Al-Mansour 60%, Khalid Ibrahim Al-Mansour 40%; no group entities.",
                        "Manufactures PET preforms, HDPE drums and jerrycans and stretch films on 12 lines (6 PET, 4 blow-moulding, 2 film); 386 staff "
                        "(Nitaqat Medium Green, 26.9% vs 23.0%). Exports 24% to GCC (2024: 26%) (Note 9).",
                        "Sales terms as per business: Gulf Beverage Bottling 22.0% (60 days), Eastern Dairy Foods 14.0% (45 days), 14 GCC customers 24.0% "
                        "(60-90 days, LC / open account), 96 local customers 40.0% (30-60 days). Purchases: Orient Polymers Trading FZE (UAE) 38.2% on "
                        "LC 120 days usance; Jubail Petrochemical Marketing 23.7% on 30 days."],
         "shareholders": [["Saleh Ibrahim Al-Mansour (Chairman and GM)", "1964", "Saudi", "60.0%", "Yes"], ["Khalid Ibrahim Al-Mansour", "1970", "Saudi", "40.0%", "Yes"]],
         "relationship": [f"New to bank; account to be opened on approval. Banks with {CGB} since 04/2021 (limits SAR 190.0m, outstanding SAR 134.0m at "
                          f"30/09/2026) and {TIB} since 02/2022 (LGs SAR 15.0m, outstanding SAR 9.2m).",
                          f"Statements Oct 2025 – Sep 2026: {CGB} credits SAR {cr(cgb):,.1f}m, {TIB} SAR {cr(tib):,.1f}m; no returned cheques. "
                          "The customer approached the Bank on pricing grounds (as per business)."],
         "justification": ["Jubail manufacturer since 2011 with revenue SAR 296.4m (FY2025), machinery valued at SAR 162.0m (average age 6.5 years) and two "
                           "beverage and dairy customers at 36% of sales.",
                           "The takeover brings payroll for 386 staff, resin imports (SAR 98.4m from one supplier on LC) and export proceeds (24% of sales).",
                           f"As per the customer the record with {CGB} has no delays or restructuring and the move is for pricing (2.25% there); "
                           "we recommend approval at 3M SAIBOR + 1.25%."]}
    P["credit"] = [
        ("Bureau and the current bank: undisclosed restructuring", [
            f"The request states 'an excellent track record with {CGB} with no delays or restructuring'. <u>Upon checking the SIMAH company report (09/10/2026), "
            f"the {CGB} term loan is reported as 'Restructured'</u>: the SAR 8.0m instalment of 31/12/2025 was not paid, 31-60 days past due in 01/2026 and 02/2026, "
            "rescheduled on 18/03/2026. The FY2025 audited accounts confirm it (Note 24: four instalments of 31/12/2025 – 30/09/2026, SAR 32.0m, deferred; maturity "
            f"extended from 31/12/2027 to 30/09/2028), {CGB}'s statement of 30/09/2026 shows the new schedule (8 x SAR 9.0m from 31/12/2026) and the guarantor's "
            "SIMAH report shows his guarantee of SAR 190.0m as 'Restructured (03/2026)'. The offer letter supplied is dated 12/06/2023, before the rescheduling.",
            f"The rescheduling followed a covenant breach: DSCR {dscr25:.2f}x in FY2025 against 1.25x required (FY2024 {dscr24:.2f}x; Note 16). Three bureau "
            f"enquiries in six months ({BANK} 10/2026, Al Rimal Commercial Bank 07/2026, Arabian Crescent Bank 05/2026) indicate that the customer approached "
            "at least two other banks for the same takeover; business did not mention them.",
            {"table": {"cols": ["Bureau (SIMAH, 09/10/2026)", "Limits", "Outstanding", "Overdue", "Score", "Status / remark"],
                       "rows": [["Nukhba Polymer Industries Co.", "205.0", "143.2", "0.0", "598", "CGB term loan restructured 18/03/2026; others current"],
                                ["Saleh Ibrahim Al-Mansour (guarantor)", "0.2", "0.04", "0.0", "702", "Own current; guarantee SAR 190.0m restructured"],
                                ["Khalid Ibrahim Al-Mansour", "2.4", "1.6", "0.0", "736", "24 of 24 months current; no guarantee offered"]],
                       "widths": [0.3, 0.09, 0.11, 0.09, 0.08, 0.33], "font": 7}}]),
        ("Other banks' facilities", [
            {"table": {"cols": ["Bank (SAR m)", "Facility", "Limit", "Outstanding 30/09/2026", "Pricing", "Maturity"],
                       "rows": [[CGB, "Term loan (rescheduled)", "120.0", "72.0", "3M SAIBOR + 2.25%", "30/09/2028 (was 31/12/2027)"],
                                [CGB, "Short-term Murabaha", "40.0", "38.4", "3M SAIBOR + 2.25%", "rolling, 180 days"],
                                [CGB, "LCs incl. acceptances", "30.0", "23.6", "0.30% p.q.", "per LC"],
                                [TIB, "Letters of guarantee", "15.0", "9.2", "0.80% p.a.; 15% margin", "offer valid to 30/11/2026"],
                                ["Total", "", "205.0", "143.2", "", ""]], "bold_last": True,
                       "widths": [0.2, 0.22, 0.09, 0.14, 0.17, 0.18], "font": 7}},
            f"Client-declared figures agree with SIMAH and the banks' statements (SAR 143.2m). Not clarified: the {TIB} LG line (SAR 15.0m) stays outside the "
            "takeover, so total bank lines after approval would be SAR 172.0m; the request is silent on it."]),
        ("Financials", [
            {"table": _fin(sp)},
            [f"Revenue fell to SAR {f25['revenue']:,.1f}m in FY2025 (PY {f24['revenue']:,.1f}m, {100 * (f25['revenue'] / f24['revenue'] - 1):+.1f}%); 9M2026 "
             f"SAR {m9['revenue']:,.1f}m, annualised SAR {m9['revenue'] / 9 * 12:,.1f}m ({100 * (m9['revenue'] / 9 * 12 / f25['revenue'] - 1):+.1f}%). VAT filings "
             f"Oct 2025 – Sep 2026 SAR {sum(v['taxable_sales'] + v['zero_rated'] for v in sp['vat']):,.1f}m (standard and zero-rated) agree with the accounts.",
             f"Gross margin {pct(f25['gross_profit'], f25['revenue']):.1f}% (PY {pct(f24['gross_profit'], f24['revenue']):.1f}%; 9M2026 "
             f"{pct(m9['gross_profit'], m9['revenue']):.1f}%): PET resin up 18% in 2025, selling prices lagged (Note 9). Net profit SAR {f25['net_profit']:,.1f}m "
             f"(PY {f24['net_profit']:,.1f}m), SAR {m9['net_profit']:,.1f}m in 9M2026 (net margin {pct(m9['net_profit'], m9['revenue']):.1f}%); one of six PET lines idle "
             "and two shifts instead of three (site visit 14/10/2026).",
             f"Current assets SAR {f25['current_assets']:,.1f}m: receivables {pct(f25['trade_receivables'], f25['current_assets']):.0f}%, inventory "
             f"{pct(f25['inventory'], f25['current_assets']):.0f}%, cash {pct(f25['cash'], f25['current_assets']):.0f}%. DSO {dso(f25):.0f} days (PY {dso(f24):.0f}); "
             f"inventory {dio(f25):.0f} days (PY {dio(f24):.0f}). Receivables at 30/09/2026 SAR {tr:,.1f}m, {pct(b90, tr):.0f}% within 90 days; top 2 customers "
             f"{pct(13.9 + 0.8 + 8.2, tr):.0f}% of receivables.",
             f"Current ratio {f25['current_assets'] / f25['current_liabilities']:.2f}x (PY {f24['current_assets'] / f24['current_liabilities']:.2f}x): short-term "
             "Murabaha funds part of the plant. <u>The DSCR breach at 31/12/2025 made the whole term loan callable; the accounts still show SAR "
             f"{f25['long_term_borrowings']:,.1f}m as non-current.</u> If it is reclassified, current liabilities are SAR {cl_ias1:,.1f}m and the current ratio "
             f"{f25['current_assets'] / cl_ias1:.2f}x (reported {f25['current_assets'] / f25['current_liabilities']:.2f}x); the auditor's opinion is unqualified.",
             f"Operating cash flow SAR {f25['operating_cash_flow']:,.1f}m (PY {f24['operating_cash_flow']:,.1f}m) and SAR {m9['operating_cash_flow']:,.1f}m in "
             f"9M2026 against EBITDA SAR {m9['ebitda']:,.1f}m: accruals and other liabilities fell SAR {f25['other_current_liabilities'] - m9['other_current_liabilities']:,.1f}m "
             f"and inventory rose SAR {m9['inventory'] - f25['inventory']:,.1f}m; not explained by business.",
             f"Re-performed debt service (3M SAIBOR assumed at {SAIBOR:.2f}%): annualised 9M2026 EBITDA SAR {ann_e:,.1f}m. On the {CGB} schedule now in force "
             f"(4 x SAR 9.0m in the next 12 months plus profit on SAR {funded:,.1f}m) DSCR is <u>{ann_e / ds_cur:.2f}x</u>; under the requested structure "
             f"(16 x SAR 4.5m over 48 months, SAIBOR + 1.25%) it is {ann_e / ds_new:.2f}x. The proposed 1.20x covenant is met only because the request stretches "
             "a loan already rescheduled once to 30/09/2028 by a further two years: the takeover is, in effect, a second rescheduling."]]),
        ("Effects of the current market situation", [
            f"Purchases from the two resin suppliers (SAR 159.4m in 2025) are {pct(159.4, f25['cost_of_sales']):.0f}% of cost of sales; PET resin prices rose 18% in 2025 (Note 9) and the main supplier (38.2% of purchases) is in the UAE "
            "on 120-day usance LCs, so shipping delays lengthen the cash cycle. A further 1 point fall in gross margin removes about SAR 3.0m of EBITDA "
            f"(DSCR on the current schedule {(ann_e - 3.0) / ds_cur:.2f}x). Export proceeds (24% of sales) are on 60-90 day terms."]),
        ("Pricing", [
            f"3M SAIBOR + 1.25% for a borrower that breached its covenant and was restructured on 18/03/2026 is 1.00% below the {CGB} price (2.25%) and below the "
            "Bank's grid of 2.50% for a new-to-bank BB- term loan; taking over a restructured facility at a discount transfers the risk without being paid for it."]),
        ("Security", [
            f"Machinery FSV SAR 105.0m covers {100 * 105.0 / 157.0:.0f}% of the proposed facilities and {100 * 105.0 / 117.0:.0f}% of the funded SAR 117.0m. The land is "
            f"leased (no title deed; the industrial lease and landlord's consent were not provided) and the charge is registered to {CGB} until released. Insurance "
            f"(SAR 175.0m, to 31/12/2026) names {CGB} as loss payee.",
            f"Guarantor net worth SAR {pnw_nw:,.1f}m (31/07/2026), of which SAR {sh:,.1f}m ({pct(sh, pnw_a):.0f}% of his assets) is his 60% of the borrower; outside "
            f"the borrower SAR {pnw_nw - sh:,.1f}m = {pct(pnw_nw - sh, 157.0):.0f}% of the facilities. Khalid Ibrahim Al-Mansour (40%) offers no guarantee."]),
        ("Exceptions and other observations", [[
            "Exception: takeover of a facility restructured within the last 24 months (policy: CRO concurrence). Business gives no reason beyond pricing.",
            "Exception: pricing 1.25% below the risk-based grid; business conveys it matches a competing offer, copy not provided.",
            "Exception: tenor of the takeover term loan (48 months) beyond the current maturity of 30/09/2028.",
            f"Not provided: industrial lease; payables ageing; {CGB}'s rescheduling agreement and current facility letter (the 2023 offer letter was given instead).",
            "Staff: 386 on the Nitaqat certificate, 240 seen on site in two shifts (site visit 14/10/2026); not reconciled.",
            "What business says vs what credit could verify: 'no delays or restructuring' (SIMAH, Note 24, the bank statement and the guarantor's report: restructured "
            "03/2026 after 31-60 DPD); 'moving for pricing' (covenant breached at the current bank; two other banks approached); asked at the site visit "
            "(14/10/2026) about the current bank's covenants, management said 'all in order'."]])]
    P["strengths"] = [f"Machinery market value SAR 162.0m (FSV 105.0m), average age 6.5 years; plant operating since 2011.",
                      "Customer base: 14 GCC export customers (24% of sales) and 96 local customers (40%); top 2 = 36%.",
                      f"Receivables {pct(b90, tr):.0f}% within 90 days at 30/09/2026; DSO {dso(f25):.0f} days (FY2025).",
                      "Revenue confirmed by 12 months of VAT filings and statement credits."]
    P["recommendation_lead"] = ("Credit division <u>does not support the takeover as proposed</u>. A restructuring not disclosed in the request, a covenant "
                                f"breach (DSCR {dscr25:.2f}x) and a gross margin down 2.4 points do not justify a price below the current bank's or a tenor beyond its rescheduled maturity.")
    P["recommendation"] = ["Decline the request as proposed (SAR 157.0m at 3M SAIBOR + 1.25%, term loan 48 months).",
                           "Credit would reconsider a takeover of SAR 132.0m: term loan SAR 72.0m on the rescheduled schedule (8 quarterly instalments of SAR 9.0m to "
                           "30/09/2028, no extension), Murabaha SAR 30.0m and LCs SAR 30.0m against 15% margin, at 3M SAIBOR + 2.75% (floor 6.25%), classified "
                           "'restructured — watch' for 12 months.",
                           "Group exposure SAR 132.0m (funded SAR 102.0m); security as proposed plus the guarantee of Khalid Ibrahim Al-Mansour.",
                           "Approval authority: Credit Committee with CRO concurrence (restructured facility)."]
    P["conditions"] = [f"Prior to limit loading: {CGB}'s rescheduling agreement of 18/03/2026, its current facility letter and a payoff letter with the release of the machinery charge.",
                       "Prior to limit loading: customer's written explanation of the statement 'no delays or restructuring' in letter NPI/CEO/2026/41.",
                       "Prior to limit loading: industrial lease and the landlord's consent to the charge; valuation by a Bank panel valuer.",
                       "Prior to limit loading: cash-flow projection 2027-2029 with resin +10% and price lag stress, showing DSCR not below 1.20x on the schedule above.",
                       "Prior to limit loading: personal guarantees of both shareholders with net-worth statements not older than 3 months.",
                       "Within 30 days of disbursement: charge over the machinery registered to the Bank; insurance loss payee changed to the Bank.",
                       "Monitoring: DSCR and margin tested semi-annually on management accounts; RM to report the PET line utilisation quarterly, reviewed by the regional head."]
    P["analyst"], P["vp"], P["authority"] = "Omar Al-Ghamdi", "Abdullah Al-Zahrani", "Credit Committee with CRO concurrence"
    P["ask_summary"] = {"one_line": f"Take over {CGB} (SAR 134m outstanding) with SAR 157m: TL 72 + Murabaha 45 + LC 40 at SAIBOR + 1.25%.",
                        "requested_total_sar": 157_000_000, "new_money_sar": 157_000_000, "credit_recommends_total_sar": 0}
    return P


def _fin(sp):
    from ops.r16_customers.proposal import fin_table
    return fin_table(sp)


ASK = f"""# Customer 3 — Nukhba Polymer Industries Co. (new to bank; optional Part A)

**Who:** new-to-bank Jubail plastics manufacturer (CR 2055104486). **Case:** takeover of {CGB}'s facilities.

## Upload

Everything in `pdf/` (or `word/`, or the photos in `images/`). Not provided on purpose: payables ageing, industrial lease.

## The ask (chat box)

> New-to-bank takeover for Nukhba Polymer: SAR 157m (term loan 72m over 48 months, Murabaha 45m, LCs 40m) to take over {CGB} at SAIBOR + 1.25%.

## RM notes

> Saleh Al-Mansour wants to move the whole relationship to us; {CGB} charges 2.25%. Excellent track record there, no delays. Machinery charge will be released on takeover. Payroll of 386 staff and export proceeds come with it.

## What credit will find (ANSWER_KEY.md §C3)

SIMAH shows the {CGB} term loan restructured on 18/03/2026 after 31-60 days past due (also FY2025 Note 24 and the {CGB}
statement's new maturity), following a DSCR covenant breach (0.92x vs 1.25x); margins falling; pricing below the current
bank's. Recommendation: decline as proposed; reconsider a smaller takeover at SAIBOR + 2.75% with full disclosure.
"""

ANSWER = f"""## C3 — Nukhba Polymer Industries Co. (new to bank, takeover)

**The story a committee would debate:** an attractive full-relationship takeover at a sharp price. The customer says it is
moving for pricing; the bureau says it was restructured six months ago at the bank it is leaving.

| # | Twist | Where it is found (join) | What the credit comments say |
|---|---|---|---|
| 1 | Undisclosed restructuring | request letter ("no delays or restructuring") × SIMAH company report (term loan "Restructured", remark "Rescheduled 18/03/2026; maturity 30/09/2028"; 31-60 DPD 01-02/2026) × FY2025 audited Note 24 (subsequent event) × {CGB} statement (maturity 30/09/2028) × {CGB} offer letter (2023, maturity 31/12/2027) × guarantor's SIMAH (guaranteed facility restructured) | the request is contradicted by three documents |
| 2 | Covenant breach behind it | FY2025 Note 16 (DSCR 1.25x not met) × audited FS (EBITDA 40.8m / (finance cost 12.4m + instalments 32.0m) = 0.92x; FY2024 1.40x) | rescheduling followed the breach; the whole loan was callable at 31/12/2025 (current ratio 0.63x if reclassified, reported 0.75x) |
| 3 | Falling margins, idle line, a second rescheduling | audited FY2024/FY2025, in-house 9M2026 (GM 15.1% → 13.2% → 12.7%), Note 9 (resin +18%) × site visit (one PET line idle) × CGB statement (8 × 9.0m to 30/09/2028) × request (48 months) | DSCR 0.86x on the schedule in force; 1.50x only because the 48-month loan stretches it again |
| 4 | Pricing below the bank it leaves | request (SAIBOR + 1.25%) × {CGB} offer letter (2.25%) | risk transferred without being paid |
| 5 | Security gaps | valuation (leasehold, charge registered to {CGB}) × insurance (loss payee {CGB}) × missing lease | FSV 67% of the ask |

**Reference recommendation** (`c3_nukhba_polymer/reference/reference_proposal.pdf`): decline as proposed; reconsider a SAR 132m
takeover (TL 72 + Murabaha 30 + LC 30) at SAIBOR + 2.75%, classified restructured-watch, with {CGB}'s rescheduling agreement,
payoff and release letters, both shareholders' guarantees, the lease and a stressed projection.
"""
