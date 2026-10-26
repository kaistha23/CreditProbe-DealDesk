"""R16 b: a small fictional customer file in the R16 contract shape (data/dealdesk/demo_customers/CONTRACT.md): the demo seed of
dd_business_request (one request written by the build, deterministic) and the unit tests' customer. "Wadi Qamar Trading Co." and
every person, bank and number here are invented."""
from __future__ import annotations

from typing import Any

CUST = {"key": "tq", "proposal_id": "R16-TQ", "cif": "CB0TEST1", "group_id": "CGTEST", "name": "Wadi Qamar Trading Co.", "short": "Wadi Qamar",
        "cr_number": "1010999001", "vat_number": "300999001100003", "city": "Riyadh", "sector": "Wholesale Trade", "sub_sector": "Building Materials",
        "case": "existing", "group_name": "Qamar Holding"}


def fs(year: int, rev: float, np_: float, eq: float, tl: float, related_sales: float = 0.0) -> dict[str, Any]:
    return {"customer_name": CUST["name"], "fiscal_year": f"{year}-12-31", "auditor": "Fictional Audit & Co.", "opinion": "Unqualified",
            "revenue": rev, "cost_of_sales": rev * 0.78, "gross_profit": rev * 0.22, "operating_expenses": rev * 0.12, "operating_profit": rev * 0.10,
            "finance_cost": rev * 0.015, "net_profit": np_, "depreciation": rev * 0.01, "cash": 8e6, "trade_receivables": rev * 0.25,
            "inventory": rev * 0.12, "due_from_related": 4e6, "current_assets": rev * 0.42, "total_assets": eq + tl, "short_term_borrowings": 30e6,
            "long_term_borrowings": 5e6, "current_liabilities": rev * 0.30, "total_liabilities": tl, "total_equity": eq, "due_to_related": 2e6,
            "operating_cash_flow": np_ * 0.8, "related_party_sales": related_sales}


def documents() -> list[dict[str, Any]]:
    d = []
    add = lambda i, t, sub, f, **k: d.append({"doc_id": f"TQ-{i:02d}", "doc_type": t, "subject": sub, "title": "", "fields": f, **k})  # noqa: E731
    add(1, "commercial_registration", "", {"customer_name": CUST["name"], "cr_number": CUST["cr_number"], "legal_form": "Limited liability company", "city": "Riyadh",
                                           "activity": "Wholesale of building materials", "share_capital": 10e6}, issue_date="2025-05-01", expiry_date="2026-05-01")
    add(2, "articles_of_association", "", {"date_of_incorporation": "2009-03-15", "legal_form": "Limited liability company",
                                           "shareholders": [{"name": "Hamad Al Qamari", "nationality": "Saudi", "shares": 600, "pct": 60},
                                                            {"name": "Qamar Holding Co.", "nationality": "Saudi", "shares": 400, "pct": 40}],
                                           "managers": [{"name": "Hamad Al Qamari", "role": "General Manager"}]}, issue_date="2020-01-01")
    add(3, "audited_fs", "fy2024", fs(2024, 200e6, 10e6, 60e6, 90e6), period_to="2024-12-31")
    add(4, "audited_fs", "fy2025", fs(2025, 276e6, 14e6, 70e6, 110e6, related_sales=85e6), period_to="2025-12-31")
    add(5, "inhouse_fs", "9m2026", {"period_from": "2026-01-01", "period_to": "2026-09-30", "revenue": 210e6, "net_profit": 9e6, "total_equity": 76e6,
                                    "total_liabilities": 118e6, "prepared_by": "Finance department"}, period_from="2026-01-01", period_to="2026-09-30", issue_date="2026-10-10")
    add(6, "vat_returns", "", {"total_taxable_sales": 280e6, "period_from": "2025-10-01", "period_to": "2026-09-30"}, issue_date="2026-10-05")
    add(7, "bank_statement", "shb_current", {"bank_name": "Sandstone Harbour Bank", "account_type": "current", "period_from": "2025-10-01",
                                             "period_to": "2026-09-30", "total_credits": 250e6, "closing_balance": 6e6, "returned_cheques": 0}, issue_date="2026-10-02")
    add(8, "facility_request_letter", "", {"letter_date": "2026-10-12", "requested_total": 60e6, "signatory": "Hamad Al Qamari", "signatory_role": "General Manager"},
        issue_date="2026-10-12")
    add(9, "top_customers_suppliers", "", {"year": 2025, "customers": [{"name": "Qamar Distribution LLC", "relationship": "related party", "sales": 85e6, "share_pct": 31, "terms": "120 days"},
                                                                       {"name": "Fictional Builders", "relationship": "third party", "sales": 30e6, "share_pct": 11, "terms": "60 days"}],
                                           "suppliers": [{"name": "Gulf Steel Mill", "country": "KSA", "share_pct": 40}]}, issue_date="2026-02-01")
    add(10, "personal_net_worth", "hamad_al_qamari", {"full_name": "Hamad Al Qamari", "statement_date": "2026-06-30", "total_assets": 50e6, "total_liabilities": 5e6,
                                                     "net_worth": 45e6, "assets": [{"asset": "Shares in Wadi Qamar", "value": 30e6}]}, issue_date="2026-06-30")
    add(11, "simah_consumer", "hamad_al_qamari", {"full_name": "Hamad Al Qamari", "report_date": "2026-09-20", "total_overdue": 0, "worst_status_24m": "Current",
                                                 "facilities": []}, issue_date="2026-09-20")
    add(12, "nitaqat_certificate", "", {"nitaqat_band": "Medium Green", "saudisation_pct": 23.5, "band_threshold_pct": 22.0, "total_staff": 120, "saudi_staff": 28},
        issue_date="2026-01-01", expiry_date="2026-12-31")
    return d


MISSING = [{"doc_type": "receivables_ageing", "subject": "", "why": "not provided by the customer"}]


def bank_rows() -> dict[str, list[dict[str, Any]]]:
    pid, cif = CUST["proposal_id"], CUST["cif"]
    months = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)][9:33]  # Oct 2024 - Sep 2026
    cond = [{"obligor_id": cif, "proposal_id": pid, "month": m, "credit_turnover_mn": 19.0 if i < 12 else 20.7, "debit_turnover_mn": 18.5,
             "avg_balance_mn": 5.0, "limits_mn": 45.0, "utilised_mn": 30.0, "utilisation_pct": 66.7, "past_due_days_max": 0, "past_due_mn": 0,
             "returned_cheques_n": 0, "returned_cheques_mn": 0, "routed_business_mn": 19} for i, m in enumerate(months)]
    return {
        "dd_facility_limit": [{"proposal_id": pid, "limit_id": "L1", "level": 1, "seq": 1, "limit_name": "Overdraft", "funded_flag": True, "existing_mn": 15.0,
                               "outstanding_mn": 9.0, "benchmark": "SAIBOR", "spread_pct": 2.5, "reporting_quarter": "2026Q3"},
                              {"proposal_id": pid, "limit_id": "L2", "level": 1, "seq": 2, "limit_name": "Letters of credit", "funded_flag": False, "existing_mn": 30.0,
                               "outstanding_mn": 21.0, "commission_pct_pa": 1.0, "cash_margin_pct": 10, "reporting_quarter": "2026Q3"}],
        "dd_account_conduct": cond,
        "dd_customer_account": [{"obligor_id": cif, "proposal_id": pid, "account_number": "SA0012345678901234", "account_type": "current", "opened": "2016-04-10",
                                 "balance_mn": 6.0, "avg_balance_12m_mn": 5.0, "credits_12m_mn": 248.4},
                                {"obligor_id": cif, "proposal_id": pid, "account_number": "SA0012345678909999", "account_type": "deposit", "opened": "2019-01-05",
                                 "balance_mn": 12.0, "avg_balance_12m_mn": 11.0, "credits_12m_mn": 0.0}],
        "dd_reference": [{"proposal_id": pid, "ref_id": "R1", "kind": "committee_approval", "ref_no": "CC-2025-118", "ref_date": "2025-11-02", "authority": "Credit committee",
                          "amount_mn": 45.0}],
        "dd_group_exposure": [{"proposal_id": pid, "group_id": "CGTEST", "entity_id": cif, "entity_name": CUST["name"], "funded_existing_mn": 15.0, "total_existing_mn": 45.0,
                               "outstanding_mn": 30.0},
                              {"proposal_id": pid, "group_id": "CGTEST", "entity_id": "CB0TEST2", "entity_name": "Qamar Distribution LLC", "funded_existing_mn": 5.0,
                               "total_existing_mn": 5.0, "outstanding_mn": 4.8}],
        "b360_entity": [{"entity_id": "CB0TEST2", "entity_name": "Qamar Distribution LLC", "group_id": "CGTEST", "role": "sister", "activity": "Distribution",
                         "credit_status": "Watchlist", "credit_status_note": "classified Stage 2 in Aug 2026"}],
        "dd_security": [{"proposal_id": pid, "security_id": "S1", "kind": "personal_guarantee", "provider": "Hamad Al Qamari", "amount_mn": 45.0,
                         "net_worth_mn": 45.0, "net_worth_statement_date": "2026-06-30", "perfection_status": "perfected", "existing_flag": True}],
    }


def cf(as_of: str = "2026-10-21") -> dict[str, Any]:
    from backend.dealdesk.house_style.bankform import source as S
    from backend.dealdesk.rm_request import inputs as I
    with S.use(bank_rows()):
        return I.load("R16-TQ", documents=documents(), missing=MISSING, customer=CUST, as_of=as_of)


SEED_ASK = ("Renew all existing facilities, increase the overdraft to SAR 25m and add a new SAR 20m short-term murabaha for 6 months at "
            "SAIBOR + 2%; secured by personal guarantee of the owner")
SEED_NOTES = "Hamad is second generation and hands-on. The group expects SAR 40m of orders from the new airport project."


def build_rows(stamp: str) -> list[dict[str, Any]]:
    """The demo row of dd_business_request: the seed customer's request, written by the same writer the API uses."""
    from backend.dealdesk.rm_request import paper as PA
    from backend.dealdesk.rm_request import store as ST
    p = PA.write(cf(), SEED_ASK, SEED_NOTES, rm="Relationship manager")
    p["written_at"] = stamp
    r = ST.row(p)
    r["proposal_id"] = ""  # the seed customer is not a Deal Desk deal (every proposal_id in Data Domains resolves to dd_deal)
    return [r]
