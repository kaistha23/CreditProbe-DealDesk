"""Customer 2: Sawaed Al Bina Contracting Co. (fictional). Existing customer, new project limit (Part B).

Twist: the marquee government-linked project (Package B, employer SLDC) is paid ~4 months late (IPC-8..IPC-11 paid
110-130 days after due; IPC-12..IPC-17 unpaid), retention is building, the extension of time is claimed but not
formalised, the new ask is a second package for the same slow-paying employer, the guarantor's net worth is mostly
shares of the borrower itself, and the connected equipment company (owned by the other partner) has a weak record
with the Bank (returned cheques, 60+ DPD) and owes the borrower a growing related-party balance.
"""
from __future__ import annotations

import random

from ops.r16_customers import fin
from ops.r16_customers.ids import BANK, BY_KEY

ACB = "Arabian Crescent Bank"
SLDC = "Sharqiya Logistics Development Co. (SLDC)"
CONSULT = "Dar Al Mimar Engineering Consultants"


def _ipcs() -> list[dict]:
    """Package B interim payment certificates IPC-1..IPC-17 (work to 30/04/2025 .. 31/08/2026)."""
    rnd = random.Random("c2-ipc")
    gross = fin.series(187.16, 17, rnd, trend=0.9, noise=0.06, nd=3)
    pay_lag = {1: 4, 2: 6, 3: 9, 4: 12, 5: 38, 6: 47, 7: 63, 8: 118, 9: 124, 10: 129, 11: 125}
    out, cum, cumret = [], 0.0, 0.0
    for k in range(1, 18):
        ym = fin.months("2025-04", 17)[k - 1]
        pto = fin.month_end(ym)
        cert = fin.add_days(pto, 19 + (k % 3))
        due = fin.add_days(cert, 56)
        g = gross[k - 1]
        cum = round(cum + g, 3)
        ret = round(0.10 * g, 3)
        adv = round(0.10 * g, 3)
        cumret = round(cumret + ret, 3)
        net = round(g - ret - adv, 3)
        paid = fin.add_days(due, pay_lag[k]) if k in pay_lag else None
        out.append({"k": k, "no": f"IPC-{k:02d}", "period_to": pto, "certified": cert, "due": due, "gross": g, "cum_gross": cum,
                    "retention": ret, "advance": adv, "net": net, "cum_retention": cumret, "paid": paid,
                    "receipt": round(net * 1.15, 3)})
    return out


def spec() -> dict:
    ids = BY_KEY["c2"]
    ipcs = _ipcs()
    co = {**ids, "legal_form": "Limited Liability Company", "incorporated": "2008-05-12", "capital_mn": 50.0, "shares_total": 50_000,
          "share_value": 1_000, "address": "King Saud Street, Al Faisaliyah, Dammam 32272", "phone": "+966 13 800 4412",
          "email": "finance@sawaed-bina.example", "activity": "General contracting for buildings, roads, infrastructure and logistics facilities; "
          "civil, structural and MEP works; maintenance of the same.", "activity_short": "General contracting (buildings, roads, logistics facilities)",
          "cr_issue": "2008-05-12", "cr_expiry": "2027-02-18", "cr_print": "2026-09-28", "aoa_amended": "2023-06-20",
          "vat_effective": "2018-01-01", "vat_frequency": "Monthly", "vat_cert_issue": "2018-01-14",
          "zakat": {"number": "ZC-2026-0451183", "fy_end": "2025-12-31", "issue": "2026-04-29", "expiry": "2027-04-30"},
          "nitaqat": {"establishment": "7-1182346", "band": "Medium Green", "rate": 16.9, "threshold": 15.2, "total": 1846, "saudi": 312,
                      "issue": "2026-10-01", "expiry": "2026-12-31"},
          "shareholders": [{"name": "Turki Hamad Al-Sawaed", "id_number": "1034578210", "nationality": "Saudi", "shares": 32_500, "pct": 65.0},
                           {"name": "Nasser Hamad Al-Sawaed", "id_number": "1046723985", "nationality": "Saudi", "shares": 17_500, "pct": 35.0}],
          "managers": [{"name": "Turki Hamad Al-Sawaed", "role": "Chairman and General Manager", "powers": "Sole signatory up to SAR 10m; jointly above"},
                       {"name": "Nasser Hamad Al-Sawaed", "role": "Partner, Deputy General Manager", "powers": "Jointly with the General Manager"}],
          "aoa_amendment_text": "Amended on 20/06/2023 to raise the capital from SAR 30m to SAR 50m by capitalising retained earnings."}
    people = [
        {"key": "turki", "name": "Turki Hamad Al-Sawaed", "id_number": "1034578210", "nationality": "Saudi", "dob": "1968-03-14",
         "id_issue": "2021-06-01", "id_expiry": "2031-05-31", "role": "Chairman and General Manager (65%)", "guarantor": True,
         "simah": {"date": "2026-10-11", "number": "SC-26-8812450", "score": 706, "worst": "Current (no delinquency)",
                   "facilities": [{"lender": BANK, "product": "Personal finance", "limit": 3.0, "outstanding": 2.1, "overdue": 0.0, "status": "Current"},
                                  {"lender": ACB, "product": "Credit card", "limit": 0.1, "outstanding": 0.024, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Sawaed Al Bina Contracting Co.", "lender": BANK, "amount": 160.0, "status": "Current"},
                                  {"beneficiary": "Sawaed Al Bina Contracting Co.", "lender": ACB, "amount": 140.3, "status": "Current"}],
                   "history": "24 of 24 months current on own facilities and on guaranteed facilities."},
         "pnw": {"date": "2026-06-30",
                 "assets": [{"asset": "Shares", "description": "65% of Sawaed Al Bina Contracting Co. (owner's valuation)", "value": 118.0},
                            {"asset": "Real estate", "description": "Villa, Al Shati district, Dammam (own valuation)", "value": 9.5},
                            {"asset": "Real estate", "description": "Land plot, Al Khobar (1,850 sq m)", "value": 14.2},
                            {"asset": "Shares", "description": "Sawaed Real Estate Co. (100%)", "value": 8.0},
                            {"asset": "Listed shares", "description": "Portfolio at market value", "value": 5.4},
                            {"asset": "Cash and deposits", "description": "Current and deposit accounts", "value": 6.8},
                            {"asset": "Vehicles", "description": "Two vehicles", "value": 0.5}],
                 "liabilities": [{"liability": "Personal finance", "description": BANK, "value": 2.1},
                                 {"liability": "Credit card", "description": ACB, "value": 0.024}]}},
        {"key": "nasser", "name": "Nasser Hamad Al-Sawaed", "id_number": "1046723985", "nationality": "Saudi", "dob": "1973-11-02",
         "id_issue": "2019-02-10", "id_expiry": "2029-02-09", "role": "Partner (35%); owner of Sawaed Heavy Equipment Rental Co.", "guarantor": True,
         "simah": {"date": "2026-10-11", "number": "SC-26-8812451", "score": 588, "worst": "60-89 days past due (07/2026, as guarantor)",
                   "facilities": [{"lender": ACB, "product": "Auto lease", "limit": 0.42, "outstanding": 0.188, "overdue": 0.0, "status": "Current"}],
                   "guarantees": [{"beneficiary": "Sawaed Al Bina Contracting Co.", "lender": BANK, "amount": 160.0, "status": "Current"},
                                  {"beneficiary": "Sawaed Heavy Equipment Rental Co.", "lender": BANK, "amount": 18.0,
                                   "status": "Past due 60-89 days in 07/2026; 30 days at 09/2026"}],
                   "history": "Own facilities current. Guaranteed facility of Sawaed Heavy Equipment Rental Co. past due 31-59 days in 05-06/2026, "
                              "60-89 days in 07/2026, 30 days at 30/09/2026."}},
    ]
    # ------------------------------------------------------------ financial statements (SAR m)
    fy23 = fin.statement({"revenue": 351.8, "cost_of_sales": 306.4, "operating_expenses": 19.2, "finance_cost": 7.9, "zakat": 1.4, "depreciation": 10.1,
                          "cash": 17.2, "trade_receivables": 79.5, "retention_receivables": 21.4, "contract_assets": 48.8, "inventory": 9.7,
                          "due_from_related": 4.1, "other_current_assets": 10.6, "ppe": 66.2, "other_noncurrent_assets": 2.8,
                          "short_term_borrowings": 58.0, "trade_payables": 47.2, "due_to_related": 1.5, "current_portion_ltd": 9.0,
                          "long_term_borrowings": 36.0, "end_of_service": 9.6, "share_capital": 30.0, "statutory_reserve": 11.6, "retained_earnings": 46.1})
    fy24 = fin.statement({"revenue": 402.6, "cost_of_sales": 352.3, "operating_expenses": 21.4, "finance_cost": 9.8, "zakat": 1.6, "depreciation": 11.2,
                          "cash": 19.8, "trade_receivables": 88.1, "retention_receivables": 27.9, "contract_assets": 61.2, "inventory": 10.9,
                          "due_from_related": 9.6, "other_current_assets": 12.0, "ppe": 70.3, "other_noncurrent_assets": 3.0,
                          "short_term_borrowings": 71.4, "trade_payables": 51.0, "due_to_related": 1.8, "current_portion_ltd": 9.0,
                          "long_term_borrowings": 18.0, "end_of_service": 11.0, "share_capital": 50.0, "statutory_reserve": 13.3, "retained_earnings": 39.3})
    fy25 = fin.statement({"revenue": 468.2, "cost_of_sales": 413.0, "operating_expenses": 23.9, "finance_cost": 12.6, "zakat": 1.8, "depreciation": 12.4,
                          "cash": 14.6, "trade_receivables": 96.4, "retention_receivables": 41.8, "contract_assets": 88.7, "inventory": 12.3,
                          "due_from_related": 18.9, "other_current_assets": 14.1, "ppe": 74.5, "other_noncurrent_assets": 3.2,
                          "short_term_borrowings": 98.6, "trade_payables": 71.2, "due_to_related": 2.1, "current_portion_ltd": 9.0,
                          "long_term_borrowings": 18.0, "end_of_service": 12.7, "share_capital": 50.0, "statutory_reserve": 15.0, "retained_earnings": 49.5})
    # 9M2026: retention and SLDC receivables from the project schedule (below)
    m9 = fin.statement({"revenue": 352.4, "cost_of_sales": 314.0, "operating_expenses": 18.6, "finance_cost": 11.1, "zakat": 0.0, "depreciation": 9.6,
                        "cash": 9.8, "trade_receivables": 104.6, "retention_receivables": 55.436, "contract_assets": 97.3, "inventory": 13.0,
                        "due_from_related": 24.6, "other_current_assets": 15.2, "ppe": 76.0, "other_noncurrent_assets": 3.3,
                        "short_term_borrowings": 109.0, "trade_payables": 74.1, "due_to_related": 2.3, "current_portion_ltd": 9.0,
                        "long_term_borrowings": 11.25, "end_of_service": 13.6, "share_capital": 50.0, "statutory_reserve": 15.0, "retained_earnings": 58.2})
    m9["months"] = 9
    fy24["operating_cash_flow"] = fin.ocf(fy23, fy24)
    fy25["operating_cash_flow"] = fin.ocf(fy24, fy25)
    fy23["operating_cash_flow"] = 21.3
    m9["operating_cash_flow"] = fin.ocf(fy25, m9)
    fs = {"FY2023": fy23, "FY2024": fy24, "FY2025": fy25, "9M2026": m9}
    ye = "2025-12-31"
    ye_unpaid = round(sum(i["net"] for i in ipcs if i["certified"] <= ye and (not i["paid"] or i["paid"] > ye)), 3)
    ye_overdue = round(sum(i["net"] for i in ipcs if i["due"] < ye and (not i["paid"] or i["paid"] > ye)), 3)
    auditor = "Qimam Al Sharq Certified Accountants"
    audit = {"FY2024": {"auditor": auditor, "opinion": "Unqualified", "qawaem": "QW-2025-2050117342", "city": "Dammam", "partner": "Saleh Al-Dossary",
                        "licence": "512", "signed": "2025-04-24"},
             "FY2025": {"auditor": auditor, "opinion": "Unqualified, with emphasis of matter", "qawaem": "QW-2026-2050117342", "city": "Dammam",
                        "partner": "Saleh Al-Dossary", "licence": "512", "signed": "2026-04-27",
                        "opinion_text": f"In our opinion, the financial statements present fairly, in all material respects, the financial position of "
                                        "Sawaed Al Bina Contracting Co. as at 31/12/2025 and its financial performance and cash flows for the year then ended "
                                        f"in accordance with IFRS as endorsed in the Kingdom. Emphasis of matter: we draw attention to Note 9, which describes "
                                        f"that certified amounts of SAR {fin.sar(ye_unpaid):,} due from a government-linked employer were unpaid at the reporting date, "
                                        f"of which SAR {fin.sar(ye_overdue):,} beyond the contractual payment terms, and that the Company's claim for an extension of time on the related project is "
                                        "pending the employer's approval. Our opinion is not modified in respect of this matter."}}
    notes = {"FY2024": [("Note 9 — Trade receivables and retention", "Trade receivables SAR 88,100,000 (2023: 79,500,000), net of an allowance of SAR 2,300,000. "
                                                                    "Retention receivables SAR 27,900,000 are recoverable on completion and expiry of the defects liability periods."),
                        ("Note 14 — Related parties", "Due from Sawaed Heavy Equipment Rental Co. (an entity owned by a partner) SAR 9,600,000 (2023: 4,100,000), "
                                                      "being advances for equipment hire. Equipment hire charged by the related party: SAR 14,200,000."),
                        ("Note 18 — Contingent liabilities", "Letters of guarantee outstanding SAR 96,300,000 (2023: 81,000,000) and letters of credit SAR 4,100,000.")],
             "FY2025": [("Note 9 — Trade receivables and retention", f"Trade receivables SAR 96,400,000 (2024: 88,100,000) include SAR {fin.sar(ye_unpaid):,} certified by the "
                                                                    f"Engineer on the Eastern Corridor Logistics Hub — Package B for {SLDC} and unpaid at 31/12/2025, of which "
                                                                    f"SAR {fin.sar(ye_overdue):,} beyond the 56-day payment term. The Company submitted a claim for an extension of time of five months; "
                                                                    "the employer has not yet approved it. Retention receivables SAR 41,800,000 (2024: 27,900,000)."),
                        ("Note 11 — Contract assets", "Work performed not yet certified SAR 88,700,000 (2024: 61,200,000), including variation claims of "
                                                      "SAR 12,400,000 not yet acknowledged by the employers."),
                        ("Note 14 — Related parties", "Due from Sawaed Heavy Equipment Rental Co. SAR 18,900,000 (2024: 9,600,000): equipment-hire advances, "
                                                      "unsecured, no fixed repayment date. Equipment hire charged: SAR 17,800,000."),
                        ("Note 18 — Contingent liabilities", f"Letters of guarantee SAR 119,600,000 (2024: 96,300,000): {BANK} SAR 60,600,000, {ACB} SAR 59,000,000. "
                                                             "Letters of credit SAR 6,300,000."),
                        ("Note 22 — Borrowings", f"Short-term Murabaha and overdraft {BANK} SAR 57,200,000, {ACB} SAR 41,400,000; equipment term loan "
                                                 f"({ACB}) SAR 27,000,000 repayable quarterly to 2028, of which SAR 9,000,000 current.")]}
    # ------------------------------------------------------------ projects
    pkgb = {"id": "P1", "name": "Eastern Corridor Logistics Hub — Package B", "employer": SLDC, "consultant": CONSULT, "engineer": "Eng. Waleed Mansour",
            "value": 486.0, "start": "2025-03-01", "completion_contract": "2027-08-31", "completion_shown": "2028-01-31", "done_pct": 41.0,
            "billed": ipcs[-1]["cum_gross"], "received": round(sum(i["net"] for i in ipcs if i["paid"]), 3),
            "retention": ipcs[-1]["cum_retention"], "status": "In progress (revised completion per EOT request)",
            "contract": {"number": "SLDC/ECLH/B/2025-014", "date": "2025-02-10", "advance_pct": 10.0, "retention_pct": 10.0, "pay_days": 56, "pb_pct": 10.0,
                         "employer_sig": "Eng. Fahd Al-Otaishan, Projects Director", "contractor_sig": "Turki Hamad Al-Sawaed",
                         "clauses": [f"The Employer, {SLDC}, a company owned by the Eastern Province Development Fund, engages the Contractor to construct "
                                     "Package B (warehouse blocks W1-W6, internal roads and utilities) of the Eastern Corridor Logistics Hub.",
                                     "Contract price SAR 486,000,000 (lump sum, excluding VAT). Time for completion: 30 months from 01/03/2025, i.e. 31/08/2027.",
                                     "Advance payment 10% against an advance payment guarantee, recovered at 10% of each interim certificate.",
                                     "Retention 10% of each interim certificate; half released at taking-over, half at the end of the 12-month defects liability period.",
                                     "Interim certificates are paid within 56 days of certification by the Engineer. Late payment does not entitle the Contractor "
                                     "to suspend work before 90 days of delay (clause 16.1).",
                                     "Extensions of time are valid only when approved in writing by the Employer (clause 8.4). Delay damages 0.1% of the "
                                     "contract price per day, capped at 10%.",
                                     "Performance security 10% of the contract price, valid until the end of the defects liability period."]}}
    p2 = {"id": "P2", "name": "Al Khobar Waterfront Residential Towers (2 towers)", "employer": "Qamar Al Khaleej Real Estate Development Co.",
          "value": 212.0, "start": "2024-01-15", "completion_shown": "2026-12-31", "done_pct": 88.0, "billed": 186.56, "received": 160.9, "retention": 18.656,
          "status": "In progress"}
    p3 = {"id": "P3", "name": "Second Industrial Estate — Roads Package 4", "employer": "Eastern Industrial Estates Co.", "value": 164.0,
          "start": "2024-06-01", "completion_shown": "2026-09-15", "done_pct": 97.0, "billed": 159.08, "received": 141.0, "retention": 15.908,
          "status": "Substantially complete; defects liability period"}
    p4 = {"id": "P4", "name": "Jubail School Complex (3 schools)", "employer": "Sahil Education Projects Co.", "value": 98.0, "start": "2025-09-01",
          "completion_shown": "2027-03-31", "done_pct": 22.0, "billed": 21.56, "received": 15.3, "retention": 2.156, "status": "In progress"}
    projects = {"as_of": "2026-09-30", "rows": [pkgb, p2, p3, p4],
                "notes": ["Package B: revised completion 31/01/2028 reflects the extension of time requested on 14/04/2026 (five months).",
                          "New award (subject of the facility request): Eastern Corridor Logistics Hub — Package C, SAR 312,000,000, letter of award "
                          "dated 22/09/2026, commencement expected 01/12/2026, 24 months."]}
    ret_total = round(sum(p["retention"] for p in projects["rows"]), 3)
    assert abs(ret_total - m9["retention_receivables"]) < 0.01, ret_total
    sldc_unpaid = round(sum(i["net"] for i in ipcs if not i["paid"]), 3)
    # ------------------------------------------------------------ receivables ageing at 30/09/2026 (= in-house trade receivables 104.6)
    def bucket(i):
        age = fin.days_between(i["due"], "2026-09-30")
        return "b0_90" if age <= 90 else ("b91_180" if age <= 180 else "b181_365")
    sl = {"b0_90": 0.0, "b91_180": 0.0, "b181_365": 0.0, "over_365": 0.0}
    for i in ipcs:
        if not i["paid"]:
            sl[bucket(i) if fin.days_between(i["due"], "2026-09-30") > 0 else "b0_90"] += i["net"]
    sl = {k: round(v, 3) for k, v in sl.items()}
    rows = [{"customer": SLDC, **sl},
            {"customer": "Qamar Al Khaleej Real Estate Development Co.", "b0_90": 5.2, "b91_180": 1.8, "b181_365": 0.0, "over_365": 0.0},
            {"customer": "Eastern Industrial Estates Co.", "b0_90": 2.2, "b91_180": 0.0, "b181_365": 0.0, "over_365": 0.0},
            {"customer": "Sahil Education Projects Co.", "b0_90": 4.1, "b91_180": 0.0, "b181_365": 0.0, "over_365": 0.0}]
    other = round(m9["trade_receivables"] - sum(sum(r[k] for k in ("b0_90", "b91_180", "b181_365", "over_365")) for r in rows), 3)
    rows.append({"customer": "Closed projects and variation claims (various)", "b0_90": round(other - 14.2 - 6.3, 3), "b91_180": 0.0,
                 "b181_365": 6.3, "over_365": 14.2})
    rec_ageing = {"as_of": "2026-09-30", "rows": rows,
                  "notes": ["Retention receivables (SAR 55,436,000) are shown separately in the project list and are not included above."]}
    pay_ageing = {"as_of": "2026-09-30", "rows": [
        {"supplier": "Gulf Rebar Trading Co.", "b0_90": 14.2, "b91_180": 3.1, "over_180": 0.0},
        {"supplier": "Eastern Ready Mix Concrete Co.", "b0_90": 11.6, "b91_180": 2.4, "over_180": 0.0},
        {"supplier": "Sawaed Heavy Equipment Rental Co. (related)", "b0_90": 0.0, "b91_180": 0.0, "over_180": 0.0},
        {"supplier": "Al Bayan MEP Subcontracting", "b0_90": 9.8, "b91_180": 4.2, "over_180": 1.1},
        {"supplier": "Other suppliers and subcontractors", "b0_90": 21.5, "b91_180": 4.6, "over_180": 1.6}]}
    pt = sum(r["b0_90"] + r["b91_180"] + r["over_180"] for r in pay_ageing["rows"])
    pay_ageing["rows"][-1]["b0_90"] = round(pay_ageing["rows"][-1]["b0_90"] + (m9["trade_payables"] - pt), 3)
    top = {"year": 2025, "date": "2026-10-05",
           "customers": [{"name": SLDC, "relationship": "Third party (government-linked)", "sales": 128.4, "share": 27.4, "terms": "56 days from certification"},
                         {"name": "Qamar Al Khaleej Real Estate Development Co.", "relationship": "Third party", "sales": 112.6, "share": 24.0, "terms": "45 days from certification"},
                         {"name": "Eastern Industrial Estates Co.", "relationship": "Third party", "sales": 96.1, "share": 20.5, "terms": "60 days from certification"},
                         {"name": "Sahil Education Projects Co.", "relationship": "Third party", "sales": 21.6, "share": 4.6, "terms": "60 days from certification"},
                         {"name": "Other (closed projects, maintenance)", "relationship": "Third parties", "sales": 109.5, "share": 23.4, "terms": "various"}],
           "suppliers": [{"name": "Gulf Rebar Trading Co.", "country": "KSA", "purchases": 61.8, "share": 15.0, "terms": "60 days, LC / open account"},
                         {"name": "Eastern Ready Mix Concrete Co.", "country": "KSA", "purchases": 49.4, "share": 12.0, "terms": "45 days"},
                         {"name": "Sawaed Heavy Equipment Rental Co.", "country": "KSA", "purchases": 17.8, "share": 4.3, "terms": "advance"},
                         {"name": "Al Bayan MEP Subcontracting", "country": "KSA", "purchases": 44.6, "share": 10.8, "terms": "back-to-back with certificates"}],
           "notes": ["Sales shares are of FY2025 revenue (SAR 468,200,000)."]}
    # ------------------------------------------------------------ VAT (monthly; 12 months Oct 2025 - Sep 2026)
    rnd = random.Random("c2-vat")
    q4 = fin.series(121.6, 3, rnd, noise=0.05)
    rev12 = q4 + fin.series(352.4, 9, rnd, trend=0.1, noise=0.07)
    vat = []
    for ym, r in zip(fin.months("2025-10", 12), rev12):
        ts = round(r * (1 + 0.04 * (rnd.random() - 0.5)), 3)
        inp = round(ts * 0.15 * rnd.uniform(0.62, 0.74), 3)
        vat.append({"period": ym, "from": f"{ym}-01", "to": fin.month_end(ym), "taxable_sales": ts, "zero_rated": 0.0, "output_vat": round(0.15 * ts, 3),
                    "input_vat": inp, "filed_on": fin.add_days(fin.month_end(ym), 19)})
    # ------------------------------------------------------------ bank accounts (statements Oct 2025 - Sep 2026)
    mlist = fin.months("2025-10", 12)
    sldc_by_month = {ym: [] for ym in mlist}
    for i in ipcs:
        if i["paid"] and i["paid"][:7] in sldc_by_month:
            sldc_by_month[i["paid"][:7]].append((f"SLDC payment {i['no']} incl. VAT (assigned proceeds)", i["receipt"], int(i["paid"][-2:])))
    # collections target incl. VAT, net of SLDC receipts
    rnd = random.Random("c2-stmt")
    total_rev = sum(rev12)
    collections = round(0.875 * total_rev * 1.15, 3)
    sldc_in = round(sum(a for v in sldc_by_month.values() for _, a, _ in v), 3)
    rest = collections - sldc_in
    shb_other = fin.series(rest * 0.62, 12, rnd, trend=0.15, noise=0.12, nd=6)
    acb_other = fin.series(rest * 0.38, 12, rnd, trend=0.1, noise=0.12, nd=6)
    def credit_items(amounts, payers, extra):
        out = []
        for i, ym in enumerate(mlist):
            items = list(extra.get(ym, []))
            parts = fin.split(amounts[i], len(payers), rnd, spread=0.5, nd=6)
            for (p, d), a in zip(payers, parts):
                items.append((p, a, d))
            out.append(items)
        return out
    shb_cr = credit_items(shb_other, [("Eastern Industrial Estates Co. — certificate payment", 9), ("Sahil Education Projects Co. — certificate payment", 16),
                                      ("Receipts from other customers (maintenance contracts)", 24)], sldc_by_month)
    acb_cr = credit_items(acb_other, [("Qamar Al Khaleej Real Estate Dev. — certificate payment", 7), ("Qamar Al Khaleej Real Estate Dev. — certificate payment", 21),
                                      ("Receipts, closed projects and claims", 26)], {})
    def debit_items(credits, opening, closing, layout):
        tot_c = [round(sum(a for _, a, _ in c), 6) for c in credits]
        deltas = fin.series(opening - closing, 12, rnd, noise=0.0) if abs(opening - closing) > 0.001 else [0.0] * 12
        out = []
        for i, ym in enumerate(mlist):
            target = round(tot_c[i] + deltas[i], 6)
            shares = [s * (1 + 0.15 * (rnd.random() - 0.5)) for _, s, _ in layout]
            ws = sum(shares)
            parts = [round(target * s / ws, 6) for s in shares[:-1]]
            parts.append(round(target - sum(parts), 6))
            out.append([(lab, a, d) for (lab, _, d), a in zip(layout, parts)])
        return out
    shb_layout = [("Payroll transfer (WPS)", 0.17, 27), ("GOSI contribution", 0.02, 15), ("Subcontractor payments", 0.30, 12),
                  ("Supplier payments (rebar, concrete)", 0.30, 20), ("VAT payment", 0.06, 28), ("Murabaha profit and LG commission", 0.03, 1),
                  ("Equipment hire — Sawaed Heavy Equipment Rental Co.", 0.04, 5), ("Rent and utilities", 0.08, 3)]
    acb_layout = [("Supplier payments", 0.48, 10), ("Subcontractor payments", 0.30, 18), ("Term loan instalment and profit", 0.08, 1),
                  ("Transfers to related party — Sawaed Heavy Equipment Rental Co.", 0.06, 22), ("Site expenses", 0.08, 25)]
    shb = {"bank": BANK, "number": "0112-345678-001", "iban": "SA4377000001123456789001", "type": "Current account (main operating)",
           "opening": 8.9, "issued": "2026-10-04", "months": mlist, "credit_items": shb_cr,
           "debit_items": debit_items(shb_cr, 8.9, 6.2, shb_layout), "returned": {}}
    acb = {"bank": ACB, "number": "6081-220193-07", "iban": "SA0961000000608122019307", "type": "Current account",
           "opening": 4.1, "issued": "2026-10-06", "months": mlist, "credit_items": acb_cr,
           "debit_items": debit_items(acb_cr, 4.1, 3.4, acb_layout), "returned": {}}
    # ------------------------------------------------------------ bureau and other banks
    shb_fac = [("Advance payment guarantees", 25.0, 19.4), ("Performance bonds", 45.0, 41.2), ("Letters of credit", 20.0, 6.3),
               ("Murabaha against payment certificates", 50.0, 47.8), ("Overdraft", 20.0, 14.9)]
    acb_fac = [("Short-term Murabaha (working capital)", 50.0, 46.3), ("Letters of guarantee", 70.0, 58.4), ("Term loan (equipment)", 20.25, 20.25)]
    simah_company = {"date": "2026-10-11", "number": "SB-26-3301872", "score": 655, "enquiries": 3,
                     "facilities": [{"lender": BANK, "product": n, "limit": l, "outstanding": o, "overdue": 0.0, "status": "Current", "opened": "2016-03-20"} for n, l, o in shb_fac]
                     + [{"lender": ACB, "product": n, "limit": l, "outstanding": o, "overdue": 0.0, "status": "Current", "opened": "2019-09-01"} for n, l, o in acb_fac],
                     "history": "No delinquency on the company's own facilities in the last 24 months. Related entity reporting is not part of this report.",
                     "enquiry_text": f"3 enquiries in the last 6 months: {BANK} (10/2026), {ACB} (08/2026), Coastal Gulf Bank (06/2026)."}
    other_banks = [{"bank": ACB, "offer_date": "2026-03-15", "offer_ref": "ACB/CB/EP/26/0412", "offer_expiry": "2027-02-28", "offer_signed": "Majid Al-Rasheed",
                    "facilities": [{"facility": "Short-term Murabaha (working capital)", "limit": 50.0, "pricing": "3M SAIBOR + 2.25%", "tenor": "up to 180 days"},
                                   {"facility": "Letters of guarantee (bid, performance, advance)", "limit": 70.0, "pricing": "0.75% p.a.", "tenor": "per LG"},
                                   {"facility": "Term loan (equipment), amortising", "limit": 20.25, "pricing": "3M SAIBOR + 2.00%", "tenor": "to 2028, quarterly"}],
                    "security": "Personal guarantee of Turki Hamad Al-Sawaed; promissory note; assignment of proceeds of the Al Khobar Waterfront project.",
                    "offer_terms": ["Business routing: not less than 30% of turnover.", "Financial covenant: leverage (total liabilities / net worth) not above 2.5x."],
                    "statement_date": "2026-09-30",
                    "statement": [{"facility": n, "limit": l, "outstanding": o, "overdue": 0.0, "maturity": m} for (n, l, o), m in
                                  zip(acb_fac, ["rolling", "per LG", "2028-06-30"])]}]
    # ------------------------------------------------------------ letters
    req = {"date": "2026-10-05", "ref": "SAB/FIN/2026/118", "by": "Turki Hamad Al-Sawaed", "role": "Chairman and General Manager",
           "body": f"We refer to our long relationship with {BANK} since 2016. We have been awarded Package C of the Eastern Corridor Logistics Hub by "
                   f"{SLDC} (letter of award dated 22/09/2026, contract value SAR 312,000,000, 24 months from 01/12/2026). We request a dedicated project "
                   "limit as follows, in addition to our existing general limit of SAR 160,000,000:",
           "facilities": [{"facility": "Advance payment guarantee (10%)", "amount": 31.2, "purpose": "Advance payment of Package C"},
                          {"facility": "Performance bond (10%)", "amount": 31.2, "purpose": "Performance security of Package C"},
                          {"facility": "Murabaha against payment certificates", "amount": 45.0, "purpose": "Working capital of Package C"},
                          {"facility": "Letters of credit (sight / usance)", "amount": 12.6, "purpose": "Imported MEP equipment for Package C"}],
           "more": ["Package B is progressing well and the employer has agreed in principle to our extension of time request. Our receivables are current "
                    "and the employer is a government-linked entity with assured funding.",
                    "We offer the assignment of Package C contract proceeds to the Bank and the personal guarantee of the undersigned."]}
    resolution = {"date": "2026-10-04", "number": "PR-2026-07", "amount": 300.0, "persons": "Turki Hamad Al-Sawaed (Chairman and General Manager)",
                  "text": "The partners resolved to obtain credit facilities from banks up to a total of SAR 300,000,000 (including the existing facilities), "
                          f"to assign contract proceeds of Package C to {BANK}, and to authorise the Chairman and General Manager to sign all documents."}
    signatories = {"as_of": "2026-10-04", "rows": [
        {"name": "Turki Hamad Al-Sawaed", "id_number": "1034578210", "role": "Chairman and General Manager", "limit": "Up to SAR 10m alone", "mode": "Single / joint above"},
        {"name": "Nasser Hamad Al-Sawaed", "id_number": "1046723985", "role": "Deputy General Manager", "limit": "Jointly with GM", "mode": "Joint"},
        {"name": "Omar Khalil Haddad", "id_number": "2398145672", "role": "Finance Manager", "limit": "Up to SAR 1m (payments)", "mode": "Joint with GM"}]}
    site = {"date": "2026-09-24", "by": "Hisham Al-Qahtani", "met": "Turki Hamad Al-Sawaed; Eng. Ahmed Fawzi (Project Manager, Package B)",
            "premises": "Head office (Dammam, rented) and Package B site (Eastern Corridor Logistics Hub)", "staff": 420,
            "summary": "Package B site active; warehouse blocks W1-W3 structure complete, W4-W6 foundations; progress behind the original programme.",
            "points": ["About 420 workers and 38 items of heavy equipment on site, most of it hired from Sawaed Heavy Equipment Rental Co.",
                       "Structure of W1-W3 complete; W4-W6 at foundation stage. Management attributes the delay to design changes by the employer.",
                       "Extension of time of five months submitted on 14/04/2026; management says the employer's response is awaited.",
                       "Management confirms certificates are being paid 'with some delay' by the employer; it expects payment of the outstanding "
                       "certificates before the year end.",
                       "Package C site (adjacent plot) not yet mobilised; mobilisation planned for December 2026."]}
    aml = {"date": "2026-10-04", "by": "Turki Hamad Al-Sawaed", "pep": "No", "countries": "KSA only (imports of MEP equipment from UAE, Italy, China)",
           "cash": "No", "rating": "Medium",
           "ubos": [{"name": "Turki Hamad Al-Sawaed", "pct": 65.0, "pep": "No"}, {"name": "Nasser Hamad Al-Sawaed", "pct": 35.0, "pep": "No"}],
           "notes": ["Related entities: Sawaed Heavy Equipment Rental Co. (100% Nasser Hamad Al-Sawaed), Sawaed Real Estate Co. (100% Turki Hamad Al-Sawaed)."]}
    return {"key": "c2", "br_alone": True, "co": co, "people": people, "fs": fs, "audit": audit, "notes": notes, "inhouse_by": "Omar Khalil Haddad", "inhouse_date": "2026-10-12",
            "inhouse_notes": ["Retention receivables and contract assets per the project schedule. Package B certificates IPC-12 to IPC-17 "
                              f"(SAR {fin.sar(sldc_unpaid):,} net) were outstanding at 30/09/2026."],
            "vat": vat, "accounts": [shb, acb], "simah_company": simah_company, "consent": {"by": "Turki Hamad Al-Sawaed", "role": "Chairman and General Manager", "on": "2026-10-04"},
            "request": req, "resolution": resolution, "signatories": signatories, "other_banks": other_banks, "rec_ageing": rec_ageing,
            "pay_ageing": pay_ageing, "top": top, "projects": projects, "ipcs": ipcs, "ipc_docs": [f"IPC-{k:02d}" for k in range(11, 18)],
            "site_visit": site, "aml": aml, "collateral": [],
            "missing": [{"doc_type": "personal_net_worth", "subject": "nasser_al_sawaed", "why": "Net-worth statement of the second guarantor not provided"},
                        {"doc_type": "project_contract", "subject": "p5_package_c", "why": "Package C contract not yet signed (letter of award only)"}],
            "facts": {"sldc_unpaid_net": sldc_unpaid, "collections_ratio": round(collections / 1.15 / total_rev, 3), "rev12": round(total_rev, 3)}}


# ==================================================================================================== bank side
def bank(sp: dict) -> dict:
    """What the Bank holds on C2 and its group (seeded into Data Domains and the Borrower 360 overlay)."""
    from ops.r16_customers.docs import statement_lines
    rnd = random.Random("c2-bank")
    cif, pid = "CB09002", "R16-C2"
    _, shb_m = statement_lines(sp["accounts"][0])
    months24 = fin.months("2024-10", 24)
    early = [round(m["credits"] * rnd.uniform(0.80, 0.92), 3) for m in shb_m]
    conduct = []
    lim_hist = {m: (120.0 if m < "2024-11" else 160.0) for m in months24}
    for i, ym in enumerate(months24):
        if i < 12:
            cr, avg = early[i], round(shb_m[i]["avg"] * rnd.uniform(0.9, 1.15), 3)
            dr = round(cr * rnd.uniform(0.97, 1.03), 3)
        else:
            m = shb_m[i - 12]
            cr, dr, avg = round(m["credits"], 3), round(m["debits"], 3), round(m["avg"], 3)
        util = round((0.66 + 0.15 * i / 23 + 0.03 * (rnd.random() - 0.5)) * lim_hist[ym], 3)
        conduct.append({"obligor_id": cif, "proposal_id": pid, "month": ym, "credit_turnover_mn": cr, "debit_turnover_mn": dr, "avg_balance_mn": avg,
                        "limits_mn": lim_hist[ym], "utilised_mn": util, "utilisation_pct": round(100 * util / lim_hist[ym], 1), "past_due_days_max": 0,
                        "past_due_mn": 0.0, "returned_cheques_n": 0, "returned_cheques_mn": 0.0, "routed_business_mn": cr})
    conduct[-1]["utilised_mn"], conduct[-1]["utilisation_pct"] = 129.6, 81.0
    # connected party: Sawaed Heavy Equipment Rental Co. (weak record)
    he = "CB09003"
    cheques = [("2026-03-11", 0.42), ("2026-05-19", 0.61), ("2026-07-08", 0.38)]
    dpd = {"2026-04": 12, "2026-05": 38, "2026-06": 45, "2026-07": 64, "2026-08": 41, "2026-09": 30}
    for i, ym in enumerate(months24):
        cr = round(rnd.uniform(1.6, 2.4) * (0.8 if ym >= "2026-03" else 1.0), 3)
        rc = [c for c in cheques if c[0][:7] == ym]
        pdue = dpd.get(ym, 0)
        conduct.append({"obligor_id": he, "proposal_id": pid, "month": ym, "credit_turnover_mn": cr, "debit_turnover_mn": round(cr * rnd.uniform(0.98, 1.06), 3),
                        "avg_balance_mn": round(rnd.uniform(0.05, 0.4), 3), "limits_mn": 18.0, "utilised_mn": round(15.2 + 0.4 * rnd.random(), 3) if ym >= "2026-01" else round(rnd.uniform(12, 15), 3),
                        "utilisation_pct": 0.0, "past_due_days_max": pdue, "past_due_mn": round(0.0 if not pdue else (0.31 if pdue < 40 else 0.78), 3),
                        "returned_cheques_n": len(rc), "returned_cheques_mn": round(sum(a for _, a in rc), 3), "routed_business_mn": cr})
        conduct[-1]["utilisation_pct"] = round(100 * conduct[-1]["utilised_mn"] / 18.0, 1)
    returned = [{"cheque_id": f"RC-C2-HE-{k+1}", "obligor_id": he, "proposal_id": pid, "return_date": d, "amount_mn": a, "reason": "insufficient_funds",
                 "regularised_flag": 1 if k < 2 else 0} for k, (d, a) in enumerate(cheques)]
    limits = [  # (id, parent, level, name, code, funded, existing, outstanding, proposed, cm, comm, bench, spread, floor, tenor, repay, project, particulars)
        ("L0", "", 0, "Total facilities", "", 0, 160.0, 129.6, 280.0, None, None, "", None, None, "", "", "", ""),
        ("G", "L0", 1, "General limit (renewal)", "", 0, 160.0, 129.6, 160.0, None, None, "", None, None, "12 months, review 30/11/2027", "", "", "Interchangeable within the general limit"),
        ("G1", "G", 2, "Advance payment guarantees", "APG", 0, 25.0, 19.4, 25.0, 10.0, 0.75, "", None, None, "Per LG, max 30 months", "", "", ""),
        ("G2", "G", 2, "Performance bonds", "PB", 0, 45.0, 41.2, 45.0, 10.0, 0.60, "", None, None, "Per LG, max 36 months", "", "", ""),
        ("G3", "G", 2, "Letters of credit (sight / usance)", "LC_SIGHT", 0, 20.0, 6.3, 20.0, 15.0, 0.25, "", None, None, "Usance up to 120 days", "", "", "0.25% per quarter"),
        ("G4", "G", 2, "Murabaha against payment certificates (DMCCM)", "DMCCM_PC", 1, 50.0, 47.8, 50.0, 0.0, None, "3M SAIBOR", 2.50, 6.25, "Up to 180 days per draw", "From certificate proceeds", "", "Up to 80% of certified net amounts"),
        ("G5", "G", 2, "Overdraft", "OD", 1, 20.0, 14.9, 20.0, 0.0, None, "3M SAIBOR", 2.75, 6.50, "12 months", "On demand", "", ""),
        ("C", "L0", 1, "Project limit — Eastern Corridor Logistics Hub Package C (new)", "", 0, 0.0, 0.0, 120.0, None, None, "", None, None, "Project life, 24 months + DLP", "", "P5", "Dedicated to Package C"),
        ("C1", "C", 2, "Advance payment guarantee (10%)", "APG", 0, 0.0, 0.0, 31.2, 10.0, 0.75, "", None, None, "Until full recovery of the advance", "", "P5", ""),
        ("C2", "C", 2, "Performance bond (10%)", "PB", 0, 0.0, 0.0, 31.2, 10.0, 0.60, "", None, None, "Until end of DLP (36 months)", "", "P5", ""),
        ("C3", "C", 2, "Murabaha against Package C certificates (DMCCM)", "DMCCM_PC", 1, 0.0, 0.0, 45.0, 0.0, None, "3M SAIBOR", 2.50, 6.25, "Up to 180 days per draw", "From Package C certificate proceeds", "P5", "Up to 80% of certified net amounts"),
        ("C4", "C", 2, "Letters of credit (MEP imports)", "LC_USANCE", 0, 0.0, 0.0, 12.6, 15.0, 0.25, "", None, None, "Usance up to 120 days, settled by DMCCM", "", "P5", "0.25% per quarter"),
    ]
    lim_rows = []
    for seq, r in enumerate(limits):
        lim_rows.append(dict(zip(("limit_id", "parent_limit_id", "level", "limit_name", "product_code", "funded_flag", "existing_mn", "outstanding_mn",
                                  "proposed_mn", "cash_margin_pct", "commission_pct_pa", "benchmark", "spread_pct", "floor_pct", "tenor_text",
                                  "repayment_text", "project_id", "particulars"), r)) | {"proposal_id": pid, "seq": seq, "currency": "SAR", "interchangeable_flag": 1 if r[1] == "G" else 0})
    security = [
        {"security_id": "S1", "limit_id": "ALL", "kind": "personal_guarantee", "provider": "Turki Hamad Al-Sawaed", "provider_entity_id": "XP-C2-01",
         "amount_mn": None, "net_worth_mn": 160.276, "net_worth_statement_date": "2026-06-30", "perfection_status": "perfected", "existing_flag": 1,
         "note": "Existing; 73.6% of declared assets are his 65% of the borrower (owner's valuation SAR 118.0m vs book SAR 80.1m)"},
        {"security_id": "S2", "limit_id": "G", "kind": "personal_guarantee", "provider": "Nasser Hamad Al-Sawaed", "provider_entity_id": "XP-C2-02",
         "amount_mn": None, "net_worth_mn": None, "net_worth_statement_date": None, "perfection_status": "perfected", "existing_flag": 1,
         "note": "Existing on the general limit; net-worth statement not provided; not offered for the project limit"},
        {"security_id": "S3", "limit_id": "G", "kind": "assignment_project_proceeds", "provider": "Sawaed Al Bina Contracting Co.", "provider_entity_id": "XE-C2-01",
         "amount_mn": 486.0, "perfection_status": "perfected", "existing_flag": 1, "note": "Package B proceeds assigned; SLDC acknowledgement 02/05/2025"},
        {"security_id": "S4", "limit_id": "C", "kind": "assignment_project_proceeds", "provider": "Sawaed Al Bina Contracting Co.", "provider_entity_id": "XE-C2-01",
         "amount_mn": 312.0, "perfection_status": "pending", "perfection_deadline": "2027-01-31", "existing_flag": 0, "note": "Package C proceeds; contract not yet signed"},
        {"security_id": "S5", "limit_id": "ALL", "kind": "security_cheque", "provider": "Sawaed Al Bina Contracting Co.", "provider_entity_id": "XE-C2-01",
         "amount_mn": 280.0, "perfection_status": "pending", "existing_flag": 0, "note": "Promissory note for total facilities"},
        {"security_id": "S6", "limit_id": "ALL", "kind": "cash_margin", "provider": "Sawaed Al Bina Contracting Co.", "provider_entity_id": "XE-C2-01",
         "amount_mn": 6.06, "perfection_status": "perfected", "existing_flag": 1, "note": "10% cash margin on LGs, held in deposit account 0112-345678-501"},
    ]
    for s in security:
        s.setdefault("currency", "SAR")
        s["proposal_id"] = pid
    tnc = [("T1", "G", 1, "utilisation", "DMCCM drawn only against Engineer-certified payment certificates, up to 80% of the net certified amount.", "complied"),
           ("T2", "G", 2, "settlement", "Proceeds of assigned projects credited to the Bank first settle the related DMCCM.", "complied"),
           ("T3", "G", 3, "routing", "Route not less than 60% of turnover through the Bank.", "complied"),
           ("T4", "ALL", 4, "existing_condition", "Due from related parties not to exceed SAR 10m (CC/2024/207, condition 6).", "not_complied"),
           ("T5", "ALL", 5, "reporting", "Audited financial statements within 120 days of year end.", "complied"),
           ("T6", "C", 1, "disbursement", "Package C DMCCM only against certified Package C certificates; last 10% of contract value not financed.", "new"),
           ("T7", "C", 2, "cover_ratio", "Funded outstanding under the project limit covered at least 1.5x by remaining Package C contract proceeds.", "new"),
           ("T8", "C", 3, "purpose", "No transfer of project-limit proceeds to related parties.", "new")]
    tnc_rows = [{"proposal_id": pid, "tnc_id": t, "limit_id": l, "seq": s, "category": c, "text": x, "existing_status": st} for t, l, s, c, x, st in tnc]
    refs = [("R1", "limit_history", "CC/2016/031", "2016-03-14", "Credit Committee", 40.0, 40.0, "First approval: LG and OD lines."),
            ("R2", "limit_history", "CC/2019/044", "2019-04-02", "Credit Committee", 85.0, 85.0, "Increase for Al Khobar and roads projects."),
            ("R3", "limit_history", "CC/2022/118", "2022-10-19", "Credit Committee", 120.0, 130.0, "Renewal and increase."),
            ("R4", "committee_decision", "CC/2024/207", "2024-11-12", "Credit Committee", 160.0, 185.0,
             "Renewal and increase to SAR 160m for Package B; group cap SAR 185m; related-party balances capped at SAR 10m."),
            ("R5", "credit_file_request", "CFR/EP/2026/0391", "2026-10-06", "", None, None, "Business request for the Package C project limit.")]
    ref_rows = [dict(zip(("ref_id", "kind", "ref_no", "ref_date", "authority", "amount_mn", "group_cap_mn", "text"), r)) | {"proposal_id": pid} for r in refs]
    ge = [{"proposal_id": pid, "group_id": "CG9002", "entity_id": "XE-C2-01", "entity_name": "Sawaed Al Bina Contracting Co.", "funded_existing_mn": 70.0,
           "total_existing_mn": 160.0, "funded_proposed_mn": 115.0, "total_proposed_mn": 280.0, "outstanding_mn": 129.6},
          {"proposal_id": pid, "group_id": "CG9002", "entity_id": "XE-C2-02", "entity_name": "Sawaed Heavy Equipment Rental Co.", "funded_existing_mn": 18.0,
           "total_existing_mn": 18.0, "funded_proposed_mn": 18.0, "total_proposed_mn": 18.0, "outstanding_mn": 15.2},
          {"proposal_id": pid, "group_id": "CG9002", "entity_id": "XE-C2-03", "entity_name": "Sawaed Real Estate Co.", "funded_existing_mn": 0.0,
           "total_existing_mn": 0.0, "funded_proposed_mn": 0.0, "total_proposed_mn": 0.0, "outstanding_mn": 0.0}]
    entities = [
        {"entity_id": "XE-C2-01", "entity_name": "Sawaed Al Bina Contracting Co.", "role": "subject", "parent_entity_id": "", "legal_status": "LLC",
         "activity": "General contracting", "licence_no": "2050117342", "licence_expiry": "2027-02-18", "incorporation_date": "2008-05-12",
         "incorporation_place": "Dammam", "staff_count": 1846, "borrower_id": cif, "credit_status": "performing", "credit_status_note": ""},
        {"entity_id": "XE-C2-02", "entity_name": "Sawaed Heavy Equipment Rental Co.", "role": "sister", "parent_entity_id": "", "legal_status": "LLC",
         "activity": "Heavy equipment rental", "licence_no": "2050139981", "licence_expiry": "2027-08-30", "incorporation_date": "2014-09-01",
         "incorporation_place": "Dammam", "staff_count": 96, "borrower_id": he, "credit_status": "past_due",
         "credit_status_note": "3 returned cheques (SAR 1.41m) in 03-07/2026; 64 days past due in 07/2026, 30 days at 30/09/2026; on watchlist since 08/2026"},
        {"entity_id": "XE-C2-03", "entity_name": "Sawaed Real Estate Co.", "role": "sister", "parent_entity_id": "", "legal_status": "LLC",
         "activity": "Real estate investment", "licence_no": "2050158804", "licence_expiry": "2028-01-12", "incorporation_date": "2017-01-12",
         "incorporation_place": "Dammam", "staff_count": 6, "borrower_id": "", "credit_status": "performing", "credit_status_note": "Deposit customer only"},
        {"entity_id": "XE-C2-04", "entity_name": SLDC, "role": "employer", "parent_entity_id": "", "legal_status": "Closed JSC",
         "activity": "Logistics infrastructure development (owned by the Eastern Province Development Fund)", "licence_no": "2050200177",
         "licence_expiry": "2029-03-01", "incorporation_date": "2021-03-01", "incorporation_place": "Dammam", "staff_count": 240, "borrower_id": "",
         "credit_status": "performing", "credit_status_note": "Government-linked; pays Package B certificates 110-130 days after due"},
    ]
    for e in entities:
        e.update({"group_id": "CG9002", "group_name": "Sawaed Group", "country": "Saudi Arabia", "listed_flag": 0})
    holders = [("XE-C2-01", "XP-C2-01", "Turki Hamad Al-Sawaed", "person", "Saudi", 1968, 65.0, 1, 65.0, "2008-05-12"),
               ("XE-C2-01", "XP-C2-02", "Nasser Hamad Al-Sawaed", "person", "Saudi", 1973, 35.0, 1, 35.0, "2008-05-12"),
               ("XE-C2-02", "XP-C2-02", "Nasser Hamad Al-Sawaed", "person", "Saudi", 1973, 100.0, 1, 100.0, "2014-09-01"),
               ("XE-C2-03", "XP-C2-01", "Turki Hamad Al-Sawaed", "person", "Saudi", 1968, 100.0, 1, 100.0, "2017-01-12")]
    holder_rows = [dict(zip(("entity_id", "holder_id", "holder_name", "holder_kind", "nationality", "birth_year", "share_pct", "ubo_flag",
                             "ubo_effective_pct", "since"), h)) | {"nominee_flag": 0} for h in holders]
    edges = [("E-C2-1", "owns", "XP-C2-01", "XE-C2-01", 65.0, None, None, "65% shareholder"),
             ("E-C2-2", "owns", "XP-C2-02", "XE-C2-01", 35.0, None, None, "35% shareholder"),
             ("E-C2-3", "owns", "XP-C2-02", "XE-C2-02", 100.0, None, None, "Sole owner"),
             ("E-C2-4", "owns", "XP-C2-01", "XE-C2-03", 100.0, None, None, "Sole owner"),
             ("E-C2-5", "buys_from", "XE-C2-01", "XE-C2-02", None, 17.8, None, "Equipment hire FY2025; advances due from the sister SAR 24.6m at 30/09/2026"),
             ("E-C2-6", "related_party", "XE-C2-01", "XE-C2-02", None, None, 24.6, "Due from related party (unsecured, no repayment date)"),
             ("E-C2-7", "guarantees", "XP-C2-01", "XE-C2-01", None, None, 280.0, "Personal guarantee (all facilities)"),
             ("E-C2-8", "guarantees", "XP-C2-02", "XE-C2-02", None, None, 18.0, "Personal guarantee of the sister's facilities"),
             ("E-C2-9", "supplies", "XE-C2-01", "XE-C2-04", None, 128.4, None, "Package B (and Package C requested): SLDC is the largest employer")]
    edge_rows = [dict(zip(("edge_id", "rel_type", "source_id", "target_id", "ownership_pct", "annual_value_mn", "amount_mn", "detail"), e)) | {"group_id": "CG9002"} for e in edges]
    board = [("XE-C2-01", "XP-C2-01", "Turki Hamad Al-Sawaed", "chairman", "Saudi", "2008-05-12", 1, "CB09002"),
             ("XE-C2-01", "XP-C2-02", "Nasser Hamad Al-Sawaed", "director", "Saudi", "2008-05-12", 0, "CB09003"),
             ("XE-C2-01", "XP-C2-03", "Omar Khalil Haddad", "cfo", "Jordanian", "2019-02-01", 0, ""),
             ("XE-C2-02", "XP-C2-02", "Nasser Hamad Al-Sawaed", "gm", "Saudi", "2014-09-01", 1, "CB09002")]
    board_rows = [dict(zip(("entity_id", "person_id", "person_name", "role", "nationality", "appointed", "key_person_flag", "linked_borrower_ids"), b))
                  | {"other_directorships": "[]"} for b in board]
    accounts = [
        {"obligor_id": cif, "account_no": "0112-345678-001", "iban": "SA4377000001123456789001", "account_type": "current", "label": "Current account (main operating)",
         "opened": "2016-03-20", "balance_mn": round(shb_m[-1]["closing"], 3), "avg_balance_12m_mn": round(sum(m["avg"] for m in shb_m) / 12, 3),
         "credits_12m_mn": round(sum(m["credits"] for m in shb_m), 3), "debits_12m_mn": round(sum(m["debits"] for m in shb_m), 3)},
        {"obligor_id": cif, "account_no": "0112-345678-501", "iban": "SA1677000001123456785011", "account_type": "deposit", "label": "Cash-margin deposit (LGs)",
         "opened": "2016-04-02", "balance_mn": 6.06, "avg_balance_12m_mn": 5.71, "credits_12m_mn": 1.42, "debits_12m_mn": 0.98},
        {"obligor_id": he, "account_no": "0112-778812-001", "iban": "SA6577000001127788120011", "account_type": "current", "label": "Current account",
         "opened": "2019-06-10", "balance_mn": 0.214, "avg_balance_12m_mn": 0.188, "credits_12m_mn": 22.6, "debits_12m_mn": 23.1},
        {"obligor_id": "XE-C2-03", "account_no": "0112-801144-001", "iban": "SA2877000001128011440011", "account_type": "current", "label": "Current account",
         "opened": "2017-02-01", "balance_mn": 0.85, "avg_balance_12m_mn": 0.91, "credits_12m_mn": 1.9, "debits_12m_mn": 2.0},
    ]
    for a in accounts:
        a.update({"proposal_id": pid, "currency": "SAR", "bank_name": BANK, "as_of": "2026-09-30"})
    ratings = {cif: {"2021Q3": "BBB-", "2024Q4": "BBB-", "2025Q4": "BB+", "2026Q2": "BB+"}, he: {"2021Q3": "BB", "2025Q2": "BB-", "2026Q2": "B"}}
    return {"cif": cif, "proposal_id": pid, "unit": "Corporate Banking — Eastern Province", "branch": "Dammam Main Branch", "rm": "Hisham Al-Qahtani",
            "ro": "Lama Al-Mutairi", "opened": "2016-03-20", "industry_code": "F41 — Construction of buildings", "purpose_code": "PF-03 Project finance (contracting)",
            "collateral_code": "AS — Assignment of proceeds", "rating_existing": "BB+", "rating_proposed": "BB", "review_date": "2026-11-30",
            "conduct": conduct, "returned_cheques": returned, "limits": lim_rows, "security": security, "tnc": tnc_rows, "references": ref_rows,
            "group_exposure": ge, "entities": entities, "holders": holder_rows, "edges": edge_rows, "board": board_rows, "accounts": accounts, "ratings": ratings,
            "connected": {"cif": he, "name": "Sawaed Heavy Equipment Rental Co.", "cheques": cheques, "dpd": dpd, "limits": 18.0, "outstanding": 15.2}}


# ==================================================================================================== proposal text
def proposal_text(sp: dict, b: dict) -> dict:
    fs, ipcs = sp["fs"], sp["ipcs"]
    f24, f25, m9 = fs["FY2024"], fs["FY2025"], fs["9M2026"]
    asof = "2026-09-30"
    late = [i for i in ipcs if i["paid"] and i["k"] >= 8]
    lag = [fin.days_between(i["due"], i["paid"]) for i in late]
    unpaid = [i for i in ipcs if not i["paid"]]
    overdue = [i for i in unpaid if i["due"] < asof]
    ov_amt = sum(i["net"] for i in overdue)
    un_amt = sum(i["net"] for i in unpaid)
    ov_days = max(fin.days_between(i["due"], asof) for i in overdue)
    elapsed = 100 * fin.days_between("2025-03-01", asof) / fin.days_between("2025-03-01", "2027-08-31")
    pk = sp["projects"]["rows"]
    backlog = {p["id"]: p["value"] * (1 - p["done_pct"] / 100) for p in pk}
    backlog["P5"] = 312.0
    sldc_backlog = backlog["P1"] + backlog["P5"]
    tot_backlog = sum(backlog.values())
    pnw = sp["people"][0]["pnw"]
    ta = sum(a["value"] for a in pnw["assets"])
    nw = ta - sum(x["value"] for x in pnw["liabilities"])
    own = pnw["assets"][0]["value"]
    book = 0.65 * m9["total_equity"]
    rp_transfers = sum(a for items in sp["accounts"][1]["debit_items"] for d, a, _ in items if "related party" in d)
    tl9 = m9["total_liabilities"]
    adj_tnw = m9["total_equity"] - m9["due_from_related"] - 12.4
    ret = m9["retention_receivables"]
    he = b["connected"]
    ann = m9["revenue"] / 9 * 12
    shb12 = sum(a["credits_12m_mn"] for a in b["accounts"] if a["account_no"] == "0112-345678-001")
    stm = [sum(a for _, a, _ in it) for it in sp["accounts"][1]["credit_items"]]
    acb12 = sum(stm)
    route = 100 * shb12 / (shb12 + acb12)
    lim = {L["limit_id"]: L for L in b["limits"]}
    conduct = [r for r in b["conduct"] if r["obligor_id"] == b["cif"]]
    last12 = conduct[-12:]
    P = {"header": {"related": "Yes — Sawaed Heavy Equipment Rental Co. (CIF CB09003, owned by partner Nasser Hamad Al-Sawaed); Sawaed Real Estate Co.",
                    "date": "2026-10-06", "type": "Renewal + additional (new project limit)"},
         "cfr": "CFR/EP/2026/0391", "unit_head": "Khalid Al-Otaibi",
         "action": ("Renew the general limit of SAR 160.0m approved under CC/2024/207 dated 12/11/2024 for a further 12 months with the same structure, "
                    "and approve a new project limit of SAR 120.0m dedicated to the Eastern Corridor Logistics Hub — Package C awarded by "
                    f"{SLDC} (letter of award 22/09/2026, contract value SAR 312.0m, 24 months from 01/12/2026), taking total facilities from "
                    "SAR 160.0m to SAR 280.0m and the Sawaed Group exposure cap from SAR 185.0m to SAR 300.0m."),
         "fees": "Study and documentation fee: 0.25% of the new limit (SAR 300,000). Pricing of the general limit unchanged.",
         "security": [{"group": "For the general limit (SAR 160.0m)", "items": [
                          "Personal guarantee of Turki Hamad Al-Sawaed (65% shareholder), net worth SAR 160.3m as per statement dated 30/06/2026 (existing; extended to the project limit).",
                          "Personal guarantee of Nasser Hamad Al-Sawaed (35%), net-worth statement to follow (existing).",
                          "Assignment of Package B proceeds (existing, acknowledged by SLDC on 02/05/2025).",
                          "Promissory note for SAR 280.0m covering both limits (new, replacing SAR 160.0m).",
                          "Cash margin 10% on letters of guarantee, 15% on letters of credit (existing deposit SAR 6.06m)."]},
                      {"group": "For the Package C project limit (SAR 120.0m)", "items": [
                          "Assignment of Package C contract proceeds to the Bank, to be acknowledged by SLDC within 60 days of contract signature (new).",
                          "Personal guarantee of Turki Hamad Al-Sawaed (above), extended to the project limit (new).",
                          "Cash margin 10% on the APG and PB (SAR 6.24m), 15% on LCs (new)."]}],
         "tnc": [{"group": "For the general limit", "items": [
                     "DMCCM only against Engineer-certified payment certificates, up to 80% of the net certified amount, repaid from the certificate proceeds.",
                     "Proceeds of assigned projects credited to the Bank first settle the related DMCCM outstanding."]},
                 {"group": "For the Package C project limit", "items": [
                     "Package C limit used only for Package C; LGs in the employer's standard format, open-ended wording not accepted.",
                     "DMCCM against Package C certificates certified by the Engineer, up to 80% of the net certified amount; the last 10% of contract value not financed.",
                     "Funded outstanding under the project limit covered at least 1.5x by remaining Package C contract proceeds."]},
                 {"group": "For both limits", "items": [
                     "Route not less than 60% of turnover through the Bank (existing; complied).",
                     "Audited financial statements within 120 days and in-house statements within 60 days of each half year.",
                     "Status of existing conditions (CC/2024/207): assignment of Package B proceeds — complied; routing — complied; audited FS — complied; "
                     "related-party balances capped at SAR 10m — not complied (SAR 24.6m at 30/09/2026)."]}],
         "references": ["References: CC/2016/031 (14/03/2016, SAR 40m), CC/2019/044 (02/04/2019, SAR 85m), CC/2022/118 (19/10/2022, SAR 120m, cap SAR 130m), "
                        "CC/2024/207 (12/11/2024, SAR 160m, cap SAR 185m); credit file request CFR/EP/2026/0391 dated 06/10/2026."],
         "background": [f"Sawaed Al Bina Contracting Co. (CR 2050117342, Dammam) was incorporated on 12/05/2008 as a limited liability company with capital "
                        "SAR 50.0m (raised from SAR 30.0m on 20/06/2023 by capitalising retained earnings). Activity: general contracting for buildings, roads, "
                        "infrastructure and logistics facilities. Staff 1,846 (312 Saudis, Nitaqat Medium Green, 16.9% vs 15.2% minimum).",
                        "The group (Sawaed Group) comprises the company, Sawaed Heavy Equipment Rental Co. (100% Nasser Hamad Al-Sawaed; supplies equipment hire "
                        "to the company, SAR 17.8m in FY2025) and Sawaed Real Estate Co. (100% Turki Hamad Al-Sawaed; deposit customer).",
                        f"Work in hand at 30/09/2026: four projects with remaining value SAR {tot_backlog - 312.0:,.1f}m plus Package C (SAR 312.0m) = "
                        f"SAR {tot_backlog:,.1f}m, i.e. {tot_backlog / ann:.1f}x annualised 2026 revenue. Sales terms: monthly certificates, 45-60 days; "
                        "purchases: 45-60 days, rebar against LCs."],
         "shareholders": [["Turki Hamad Al-Sawaed (Chairman and GM)", "1968", "Saudi", "65.0%", "Yes"], ["Nasser Hamad Al-Sawaed (Deputy GM)", "1973", "Saudi", "35.0%", "Yes"]],
         "relationship": [f"Customer since 20/03/2016. Credit turnover in the main account SAR {shb12:,.1f}m in the 12 months to 30/09/2026 "
                          f"(average balance SAR {sum(r['avg_balance_mn'] for r in last12) / 12:,.1f}m); routing {route:.0f}% of collections against 60% required. "
                          f"Limits utilised SAR 129.6m of SAR 160.0m (81%) at 30/09/2026; no past dues and no returned cheques in the last 12 months on the company's accounts.",
                          "History of limits: SAR 40m (2016), SAR 85m (2019), SAR 120m (2022), SAR 160m (2024)."],
         "conduct_table": {"cols": ["Quarter", "Credit turnover", "Average balance", "Average utilisation", "Past dues", "Returned cheques"],
                           "rows": [[f"{q}", f"{sum(r['credit_turnover_mn'] for r in rs):,.1f}", f"{sum(r['avg_balance_mn'] for r in rs) / 3:,.1f}",
                                     f"{sum(r['utilisation_pct'] for r in rs) / 3:.0f}%", "Nil", "Nil"]
                                    for q, rs in (("Q4 2025", last12[0:3]), ("Q1 2026", last12[3:6]), ("Q2 2026", last12[6:9]), ("Q3 2026", last12[9:12]))],
                           "widths": [0.16, 0.17, 0.17, 0.17, 0.16, 0.17]},
         "projects_table": {"cols": ["Project", "Employer", "Value", "Done", "Billed", "Received", "Retention", "Completion"],
                            "rows": [[p["name"], p["employer"], f"{p['value']:,.1f}", f"{p['done_pct']:.0f}%", f"{p['billed']:,.1f}", f"{p['received']:,.1f}",
                                      f"{p['retention']:,.1f}", D(p["completion_shown"])] for p in pk],
                            "widths": [0.22, 0.2, 0.08, 0.07, 0.09, 0.09, 0.1, 0.15], "font": 7},
         "projects": ["Package B (SAR 486.0m) progresses with 41% of work done; the employer has agreed in principle to the five-month extension of time "
                      "requested on 14/04/2026 and the revised completion date is 31/01/2028. The employer is government-linked and payments are assured.",
                      "Al Khobar Waterfront (88%) and Jubail schools (22%) progress to programme; Roads Package 4 was substantially completed in 09/2026."],
         "justification": ["Incorporated 2008; Roads Package 4 (SAR 164.0m) completed in 09/2026; revenue SAR 468.2m in FY2025 (PY 402.6m, +16.3%), "
                           "net profit SAR 16.9m (PY 17.5m).",
                           f"Package C (SAR 312.0m) is the second package from the same employer and takes work in hand to SAR {tot_backlog:,.1f}m, to 2028; the limit is "
                           "repaid from certified works and backed by the assignment of proceeds.",
                           f"Customer since 2016; {route:.0f}% routing against 60% required, no past dues and no returned cheques in 12 months; personal "
                           "guarantee of the main shareholder, net worth SAR 160.3m (30/06/2026). Business recommends approval."]}
    p1 = pk[0]
    D_ = fin.fmt_date
    P["credit"] = [
        ("Status of financed projects — Package B (SLDC)", [
            f"Contract SAR 486.0m signed 10/02/2025, 30 months from 01/03/2025 to <b>31/08/2027</b>. At 30/09/2026 {elapsed:.0f}% of the contract period has "
            f"elapsed against 41% of work done; the site visit of 24/09/2026 notes W4-W6 still at foundation stage (as per business, design changes by the employer).",
            f"<u>Payment delays.</u> Upon checking the payment certificates against the Bank's account statement, IPC-08 to IPC-11 (SAR {sum(i['net'] for i in late[-4:]):,.1f}m net) "
            f"were paid {min(lag)}-{max(lag)} days after their due dates (56 days from certification); IPC-12 to IPC-17 (SAR {un_amt:,.1f}m net) are unpaid, of which "
            f"IPC-12 to IPC-{overdue[-1]['k']} (SAR {ov_amt:,.1f}m) overdue up to {ov_days} days at 30/09/2026. The business request states that 'receivables are current', "
            "which the documents do not support. The FY2025 auditor drew attention to the same matter (emphasis of matter, Note 9). "
            f"The customer's receivables ageing ages from the due date (SLDC 91-180 days SAR {sp['rec_ageing']['rows'][0]['b91_180']:,.1f}m); aged from certification, "
            f"IPC-12 to IPC-14 (SAR {sum(i['net'] for i in unpaid if fin.days_between(i['certified'], asof) > 90):,.1f}m) are more than 90 days old.",
            f"<u>Extension of time not formalised.</u> The project list and the business request show completion on 31/01/2028 'as per EOT'; the contract (clause 8.4) "
            "recognises an extension only when approved in writing by the employer and no approval is on file (management says the response is awaited). "
            f"Until approved, delay damages of 0.1% per day apply from 01/09/2027, capped at 10% = <b>SAR 48.6m</b>, i.e. {48.6 / m9['total_equity'] * 100:.0f}% of net worth.",
            f"<u>Retention building.</u> Retention receivables SAR {ret:,.1f}m at 30/09/2026 (FY2025: 41.8; FY2024: 27.9), {100 * ret / m9['current_assets']:.0f}% of current assets; "
            f"Package B alone holds SAR {p1['retention']:,.1f}m, released half at taking-over and half after a 12-month defects period, i.e. not before 2028."]),
        ("New project — Package C", [
            f"Same employer, same consultant, contract SAR 312.0m (letter of award only; contract not signed, cash flow not provided). With Package C, SLDC would account "
            f"for SAR {sldc_backlog:,.1f}m or <b>{100 * sldc_backlog / tot_backlog:.0f}% of the backlog</b> while paying Package B about four months late. "
            "Credit's re-performance of the project cash flow (business did not provide one): SAR 13.0m of work per month over 24 months, costs at 89.1% "
            "(9M2026 gross margin 10.9%) paid the following month, 10% advance received at start against the APG, 10% retention and 10% advance recovery deducted, "
            "certificates paid 56 days after certification as per contract (base) or 2 and 4 months later (stressed, as on Package B):",
            {"table": cash_flow_table()},
            f"<u>A four-month delay, the pattern of Package B, gives a peak deficit of SAR {_cf(4)[0]:,.1f}m, more than the DMCCM of SAR 45.0m requested</u>; on time the deficit is "
            f"SAR {_cf(0)[0]:,.1f}m. Credit does not propose to finance the delay itself: a DMCCM of SAR 30.0m covers the two-month stress (SAR {_cf(2)[0]:,.1f}m); "
            "a longer delay is for the shareholders to fund (condition d). About the employer: {SLDC} is a closed joint-stock company incorporated 01/03/2021, owned by the Eastern Province Development Fund; "
            "financials and SIMAH report not provided (as per business, government-linked with assured funding)."]),
        ("Financials and adjusted ratios", [
            f"Auditor {sp['audit']['FY2025']['auditor']}, unqualified on FY2024 (signed 24/04/2025); FY2025 unqualified <u>with emphasis of matter</u> (signed 27/04/2026) on "
            "SLDC certificates unpaid at the reporting date (Note 9). 9M2026 in-house, unaudited. Figures in the business request (section 9); credit's re-performance:",
            {"table": cycle_table_ref(sp)},
            [f"Revenue rose to SAR 468.2m in FY2025 (PY 402.6m, +16.3%); 9M2026 SAR {m9['revenue']:,.1f}m, annualised SAR {ann:,.1f}m, i.e. flat. Gross margin fell to "
             f"{100 * m9['gross_profit'] / m9['revenue']:.1f}% (FY2025 {100 * f25['gross_profit'] / f25['revenue']:.1f}%; FY2024 {100 * f24['gross_profit'] / f24['revenue']:.1f}%).",
             f"Operating cash flow was negative SAR {-f25['operating_cash_flow']:,.1f}m in FY2025 (FY2024 {f24['operating_cash_flow']:+,.1f}m) and SAR {m9['operating_cash_flow']:+,.1f}m in 9M2026: "
             "growth is funded by short-term borrowings (SAR 109.0m at 30/09/2026 vs 71.4m at FY2024, excluding the current portion of long-term debt).",
             f"Current assets SAR {m9['current_assets']:,.1f}m at 30/09/2026: trade receivables {100 * m9['trade_receivables'] / m9['current_assets']:.0f}%, contract assets "
             f"{100 * m9['contract_assets'] / m9['current_assets']:.0f}%, retention {100 * ret / m9['current_assets']:.0f}%, due from related parties {100 * m9['due_from_related'] / m9['current_assets']:.0f}%, "
             f"cash {100 * m9['cash'] / m9['current_assets']:.0f}%. SLDC is {100 * sp['rec_ageing']['rows'][0]['b0_90'] / m9['trade_receivables'] + 100 * sp['rec_ageing']['rows'][0]['b91_180'] / m9['trade_receivables']:.0f}% of trade receivables; "
             "closed projects and variation claims SAR 21.5m, of which SAR 20.5m over 180 days.",
             "Contingent liabilities: LGs outstanding SAR 119.0m (the Bank 60.6, Arabian Crescent Bank 58.4) against work in hand of SAR 393.5m before Package C (30%).",
             f"Due from related parties SAR {m9['due_from_related']:,.1f}m (FY2025 18.9; FY2024 9.6), all from Sawaed Heavy Equipment Rental Co., unsecured with no repayment date; "
             f"a further SAR {rp_transfers:,.1f}m was transferred to it from the {ACB} account in the 12 months to 09/2026.",
             f"If the related-party balance and the unacknowledged variation claims (SAR 12.4m, FY2025 Note 11) are netted off, adjusted net worth is "
             f"<b>SAR {adj_tnw:,.1f}m</b> (reported {m9['total_equity']:,.1f}m) and adjusted leverage <b>{tl9 / adj_tnw:.2f}x</b> (reported {tl9 / m9['total_equity']:.2f}x), "
             f"above the 2.5x covenant in the {ACB} offer letter."]]),
        ("Guarantor", [
            f"Turki Hamad Al-Sawaed declares a net worth of SAR {nw:,.1f}m (30/06/2026), of which <b>SAR {own:,.1f}m ({100 * own / ta:.0f}% of assets) is his 65% of the borrower</b> "
            f"at his own valuation (65% of book net worth at 30/09/2026 = SAR {book:,.1f}m). Excluding the borrower's own shares, the net worth is SAR {nw - own:,.1f}m, "
            f"{100 * (nw - own) / 280.0:.0f}% of the proposed facilities. Real estate is at owner's valuation (no valuation reports). Nasser Hamad Al-Sawaed's "
            "net-worth statement was not provided and his guarantee is not offered on the project limit."]),
        ("Connected party — Sawaed Heavy Equipment Rental Co. (CIF CB09003)", [
            f"Limits SAR {he['limits']:.1f}m with the Bank (OD and term loan), outstanding SAR {he['outstanding']:.1f}m. <u>Three cheques returned for insufficient funds</u> "
            f"(11/03/2026 SAR 0.42m, 19/05/2026 SAR 0.61m, 08/07/2026 SAR 0.38m); past due 38 days in 05/2026, <b>64 days in 07/2026</b>, 30 days at 30/09/2026; "
            "downgraded to B and on the watchlist since 08/2026. Nasser Hamad Al-Sawaed's SIMAH report (score 588) shows the same delinquency as guarantor. "
            "The business request does not mention it. The equipment company depends on the borrower (equipment hire SAR 17.8m in FY2025) and the borrower "
            "funds it (SAR 24.6m due), so the two must be read together."]),
        ("Credit bureau and other banks", [
            f"SIMAH company report (11/10/2026, score 655): limits SAR 300.3m with two banks, outstanding SAR 254.6m, no overdue, no defaults. "
            "Three enquiries in six months, including Coastal Gulf Bank (06/2026), not explained by business.",
            {"table": {"cols": ["Bank (SAR m)", "Facility", "Limit", "Outstanding", "Pricing", "Source"],
                       "rows": [[BANK, "General limit (APG, PB, LC, DMCCM, OD)", "160.0", "129.6", "SAIBOR + 2.50-2.75%", "Bank records = SIMAH"],
                                [ACB, "Short-term Murabaha", "50.0", "46.3", "SAIBOR + 2.25%", "Statement 30/09/2026 = SIMAH"],
                                [ACB, "Letters of guarantee", "70.0", "58.4", "0.75% p.a.", "Statement 30/09/2026 = SIMAH"],
                                [ACB, "Term loan (equipment), to 06/2028", "20.3", "20.3", "SAIBOR + 2.00%", "Statement 30/09/2026 = SIMAH"],
                                ["Total", "", "300.3", "254.6", "", "Reconciled"]], "bold_last": True,
                       "widths": [0.2, 0.26, 0.08, 0.12, 0.15, 0.19]}},
            f"{ACB} holds the assignment of the Al Khobar Waterfront proceeds and a leverage covenant of 2.5x (offer letter ACB/CB/EP/26/0412 of 15/03/2026).",
            f"SIMAH consumer reports: Turki Hamad Al-Sawaed score 706, current; Nasser Hamad Al-Sawaed score 588, 60-89 days past due as guarantor (07/2026)."]),
        ("Effects of the current market situation", [
            "Rebar and ready-mix are 27.0% of FY2025 purchases (Gulf Rebar Trading Co. 15.0%, Eastern Ready Mix Concrete Co. 12.0%); the Package C contract is not on file, so "
            "price-escalation terms are not known; a 10% rise in rebar prices would cost about 1.3% of revenue against a 10.9% gross margin (9M2026). "
            "Eastern Province logistics projects compete for the same subcontractors and Saudi staff (Nitaqat Medium Green, 16.9% vs 15.2% minimum: 32 Saudi "
            "leavers out of 312 would take the company to the lower band)."]),
        ("Exceptions and other observations", [[
            "Exception: group exposure SAR 298.0m above the approved cap of SAR 185.0m (increase to SAR 300.0m requested).",
            "Exception: existing condition on related-party balances (SAR 10m cap) not complied: SAR 24.6m.",
            "Not provided: Package C contract and cash flow; Nasser Hamad Al-Sawaed's net-worth statement; valuations of the guarantor's real estate.",
            "What business says vs what credit could verify: 'receivables current' (not verified: SAR {:.1f}m overdue); 'EOT agreed in principle' (not verified: no written approval); "
            "'guarantor net worth SAR 160.3m' (SAR {:.1f}m excluding the borrower's own shares).".format(ov_amt, nw - own)]])
    ]
    P["strengths"] = ["Incorporated 2008; Roads Package 4 (SAR 164.0m) 97% done, substantially completed 09/2026 (as per business); Al Khobar Waterfront 88% done, completion 31/12/2026.",
                      f"Relationship since 2016 with {route:.0f}% routing, no past dues and no returned cheques on the company's accounts.",
                      "Employer of Packages B and C is government-linked (low risk of non-payment, high risk of late payment).",
                      "DMCCM repaid from Engineer-certified works; Package B proceeds assigned and acknowledged (02/05/2025); LGs and LCs carry 10-15% cash margin."]
    P["recommendation_lead"] = ("Credit division supports the renewal and the Package C limit <u>with a reduced and staged funded line and conditions precedent</u>, "
                                "given the payment delays on Package B, the unformalised extension of time and the connected party's record.")
    P["recommendation"] = ["Renew the general limit of SAR 160.0m for 12 months, structure and pricing unchanged.",
                           "Approve the Package C project limit at SAR 105.0m: APG SAR 31.2m, PB SAR 31.2m, LC SAR 12.6m and DMCCM <b>SAR 30.0m</b> (requested 45.0), "
                           "DMCCM released only when no Package B certificate is more than 60 days overdue.",
                           "Total facilities SAR 265.0m; Sawaed Group exposure cap SAR 285.0m (requested 300.0): borrower SAR 265.0m and Sawaed Heavy Equipment Rental Co. SAR 18.0m = SAR 283.0m.",
                           "Security as in section 3, with Nasser Hamad Al-Sawaed's guarantee extended to the project limit and the promissory note at SAR 265.0m.",
                           "Internal rating BB, as proposed by business (BB+ before).",
                           "Sawaed Heavy Equipment Rental Co.: keep on watchlist; no new limits; regularise and reduce outstanding to SAR 12.0m by 31/03/2027.",
                           "Approval authority: Credit Committee (group exposure above SAR 250m)."]
    P["conditions"] = ["Prior to limit loading: SLDC's written approval of the Package B extension of time, or a written undertaking not to apply delay damages pending determination.",
                       "Prior to limit loading: signed Package C contract and the assignment of its proceeds to the Bank, acknowledged by SLDC within 60 days of signature.",
                       "Prior to limit loading: personal guarantee of Nasser Hamad Al-Sawaed on the project limit with his net-worth statement; valuation of the guarantors' real estate within 3 months.",
                       "Prior to DMCCM utilisation: Package C cash-flow forecast with a 4-month payment-delay stress showing the peak deficit and how it is funded.",
                       "Due from related parties reduced to SAR 15.0m by 31/03/2027 and SAR 10.0m by 30/09/2027; no further advances or transfers to related parties (all banks).",
                       "Monthly certificate-ageing report by the RM; regional head and RM to visit Package B quarterly until certificates are paid within 60 days.",
                       "Business to explain the Coastal Gulf Bank enquiry of 06/2026 and confirm no new facilities elsewhere."]
    P["analyst"], P["vp"], P["authority"] = "Reem Al-Shehri", "Abdullah Al-Zahrani", "Credit Committee"
    P["ask_summary"] = {"one_line": "Renew SAR 160m general limit and add a SAR 120m project limit for Package C (SLDC, SAR 312m); total SAR 280m; group cap to SAR 300m.",
                        "requested_total_sar": 280_000_000, "new_money_sar": 120_000_000, "credit_recommends_total_sar": 265_000_000}
    return P


def fin_table_ref(sp):
    from ops.r16_customers.proposal import fin_table
    return fin_table(sp)


def cycle_table_ref(sp):
    from ops.r16_customers.proposal import cycle_table
    return cycle_table(sp)


def _cf(delay: int, value: float = 312.0, months: int = 24, gm: float = 0.109, adv: float = 0.10) -> tuple[float, int]:
    """Credit's Package C cash flow: (peak cumulative deficit SAR m, month of the peak) for a payment delay in months beyond the contract's 56 days."""
    g = value / months
    cum, peak, pm = value * adv, 0.0, 0
    for t in range(1, months + 12):
        cost = (1 - gm) * g if 1 <= t - 1 <= months else 0.0
        rec = 0.8 * g if 1 <= t - (2 + delay) <= months else 0.0
        cum += rec - cost
        if cum < peak:
            peak, pm = cum, t
    return round(-peak, 1), pm


def cash_flow_table() -> dict:
    rows = []
    for d, lab in ((0, "Base: paid 56 days after certification"), (2, "Stressed: paid 2 months late"), (4, "Stressed: paid 4 months late (Package B pattern)")):
        pk, mo = _cf(d)
        rows.append([lab, f"{pk:,.1f}", f"Month {mo} (end of works)" if mo >= 25 else f"Month {mo}",
                     "nil" if pk <= 45.0 else f"{pk - 45.0:,.1f}", "nil" if pk <= 30.0 else f"{pk - 30.0:,.1f}"])
    return {"cols": ["Scenario (SAR m)", "Peak deficit", "When", "Not covered by DMCCM 45.0 (asked)", "Not covered by DMCCM 30.0 (recommended)"], "rows": rows,
            "widths": [0.38, 0.13, 0.13, 0.18, 0.18]}


def D(x):
    return fin.fmt_date(x)


ASK = """# Customer 2 — Sawaed Al Bina Contracting Co. (Part B: credit side)

**Who:** existing customer since 2016 (CIF CB09002, CR 2050117342), Dammam contractor. **Case:** renewal + new project limit.

## What Anne uploads (Deal Desk → New proposal → Upload, several files at once)

1. The **business request** — any one of: `business_request/business_request.pdf`, `business_request/business_request.docx`,
   or the photos `business_request/business_request_p1.jpg` … (all pages).
2. The **documents** available (any mix of Word, PDF and photos): everything in `pdf/` (or `word/`, or `images/` for the
   key pages). Not provided on purpose: Nasser Al-Sawaed's net-worth statement; the Package C contract (letter of award only).

## What Anne types in the chat box

> Review this business request and write the credit division's response.

Optional follow-ups (Noor / thread):

> Why are we cutting the DMCCM to SAR 30m?
> Show me the payment certificates against the account statement.
> What does the guarantor's net worth look like without his shares in the company?

## The ask (as the RM wrote it)

Renew the general limit SAR 160.0m (CC/2024/207) and add a **SAR 120.0m project limit for Package C** of the Eastern
Corridor Logistics Hub (employer SLDC, contract SAR 312.0m): APG 31.2, PB 31.2, DMCCM 45.0, LC 12.6. Total SAR 280.0m;
group cap SAR 185.0m → 300.0m.

## What a good credit response finds (see ANSWER_KEY.md §C2 and `reference/reference_proposal.pdf`)

Package B certificates paid 118–129 days late and SAR 44.8m overdue (contradicts "receivables current"); the extension of
time is not approved in writing (delay damages up to SAR 48.6m); retention SAR 55.4m; Package C puts 85% of the backlog
on the same slow payer; the guarantor's net worth is 73% the borrower's own shares; the connected equipment company has
three returned cheques and 64 days past due and owes the borrower SAR 24.6m (cap SAR 10m not complied). Recommendation:
renew SAR 160m; Package C at SAR 105m with DMCCM cut to 30m and staged; cap SAR 285m; conditions precedent.
"""

ANSWER = """## C2 — Sawaed Al Bina Contracting Co. (existing, new project limit; Part B)

**The story a committee would debate:** an 18-year contractor with a marquee government-linked project asks for a second
package from the same employer. The employer is creditworthy but pays four months late, the delay on Package B is not
covered by an approved extension of time, and the guarantor and the connected equipment company are weaker than they look.

| # | Twist | Where it is found (join) | What the credit comments say |
|---|---|---|---|
| 1 | Package B certificates paid 118–129 days after due; IPC-12..IPC-15 (SAR 44.8m) overdue up to 108 days at 30/09/2026; IPC-12..17 unpaid SAR 69.8m | payment certificates IPC-11..17 (due dates) × SHB account statement (SLDC receipt dates and amounts = net × 1.15) × receivables ageing (SLDC 91–180 bucket) × FY2025 audit emphasis of matter | contradicts the business request's "receivables are current" |
| 2 | Extension of time claimed, not approved | project list (completion 31/01/2028 "per EOT request") and request letter ("agreed in principle") × contract clause 8.4 (written approval required; completion 31/08/2027) × site visit ("response awaited") × FY2025 Note 9 | delay damages up to 10% = SAR 48.6m (39% of net worth) |
| 3 | Retention building | project list retention SAR 55.4m = in-house retention receivables; FY2024 27.9 → FY2025 41.8 → 9M2026 55.4 | 17% of current assets, not released before 2028 |
| 4 | New ask on the same slow payer | request letter / business request (Package C, SLDC) × project list (Package B, SLDC) | SLDC = 85% of backlog with Package C |
| 5 | Guarantor's net worth mostly the borrower's own shares | Turki's PNW (SAR 118.0m of SAR 162.4m assets = 73% is 65% of the borrower) × in-house equity (65% of SAR 123.2m = SAR 80.1m book) | net worth excluding own shares SAR 42.3m = 15% of facilities |
| 6 | Connected party with a weak record | Bank data only: Sawaed Heavy Equipment Rental Co. (CB09003) — 3 returned cheques SAR 1.41m (03, 05, 07/2026), 64 DPD 07/2026, B rating, watchlist; Nasser's SIMAH (588, 60–89 DPD as guarantor) × FY2025 Note 14 and in-house due from related SAR 24.6m (cap 10m in CC/2024/207 not complied) × ACB statement transfers to the related party | adjusted net worth SAR 86.2m, adjusted leverage 3.20x vs 2.5x ACB covenant |
| 7 | Gaps | manifest `missing`: Nasser's PNW, Package C contract; no Package C cash flow | conditions precedent |

**Reference recommendation** (`c2_sawaed_al_bina/reference/reference_proposal.pdf`): renew SAR 160.0m; Package C at SAR 105.0m
(DMCCM cut 45.0 → 30.0, released only when no Package B certificate is > 60 days overdue); total SAR 265.0m; group cap SAR 285.0m;
CPs: written EOT approval or no-damages undertaking, signed contract + acknowledged assignment, Nasser's PG and PNW, stressed
cash flow before DMCCM, related-party balance to SAR 15m / 10m, monthly certificate ageing, explain the Coastal Gulf Bank enquiry.
"""
