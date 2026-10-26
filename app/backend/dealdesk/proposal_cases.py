"""P7 Proposal Intelligence: the two prepared UAE proposal cases (PLAN_R9 §Proposals).

Fictional, anonymised names only. Amounts are AED million. The facility breakdown inside the
stated totals (AED 476.6m -> 656.8m for Case A) is an illustrative split recorded in
docs/STATUS_R9_DEALDESK.md; every figure named in the plan is used exactly as stated.
"""
from __future__ import annotations

from typing import Any

AS_OF = "2026-10-13"

CASE_A: dict[str, Any] = {
    "case_id": "PRP-A-GMC",
    "file_name": "Gulf_Meridian_Contracting_credit_proposal.docx",
    "borrower": "Gulf Meridian Contracting LLC",
    "group": "Meridian Holding",
    "profile": "UAE branch of a Kuwaiti contracting group (Meridian Holding)",
    "sector": "Construction",
    "segment": "Corporate Banking",
    "currency": "AED",
    "rating": "BB-",
    "pd": 0.0185,
    "tier": "Tier 1",
    "rm": "Corporate Banking, Contracting Unit",
    "request_summary": [
        "Renew the AED 50m bid bond line",
        "Reduce project limits 1-3",
        "New AED 212.4m one-off limit for the villa project of Arwa Developments",
        "Raise the group exposure cap from AED 822m to AED 1bn",
        "Total limits AED 476.6m -> AED 656.8m",
    ],
    # name, kind (funded / performance_lg / bid_bond / financial_lg), existing, proposed, margin or commission (bps)
    "facilities": [
        {"name": "Bid bond line", "kind": "performance_lg", "existing": 50.0, "proposed": 50.0, "bps": 75},
        {"name": "Project 1 guarantees", "kind": "performance_lg", "existing": 110.0, "proposed": 95.0, "bps": 90},
        {"name": "Project 2 guarantees", "kind": "performance_lg", "existing": 96.6, "proposed": 88.0, "bps": 90},
        {"name": "Project 3 guarantees", "kind": "performance_lg", "existing": 70.0, "proposed": 61.4, "bps": 90},
        {"name": "General guarantee line", "kind": "performance_lg", "existing": 70.0, "proposed": 70.0, "bps": 85},
        {"name": "Overdraft and receivables finance (funded)", "kind": "funded", "existing": 80.0, "proposed": 80.0, "bps": 275},
        {"name": "Arwa villa project one-off limit (advance payment and performance)", "kind": "performance_lg",
         "existing": 0.0, "proposed": 212.4, "bps": 95},
    ],
    "stated_totals": {"existing": 476.6, "proposed": 656.8},
    "fees_upfront": 1.6,
    "group_cap": {"existing": 822.0, "proposed": 1000.0, "group_exposure_after": 978.2},
    "deposits": {"avg_balance": 38.0, "profit_paid": 0.0050, "flow_fees": 0.9, "turnover_to_revenue": 0.62,
                 "routing_required": None, "routing_achieved": None, "returned_cheques": 50,
                 "returned_cheque_note": "50 returned cheques for insufficient funds at the Dubai affiliate (Jan-Jul 2026, bureau)"},
    "financials": {"revenue": 2050.0, "ebitda": 96.0, "debt_service": 41.0, "net_debt": 214.0,
                   "backlog": 8200.0, "backlog_prior": 3416.7, "backlog_growth_stated": 1.40,
                   "backlog_share": {"Arwa Developments": 0.44, "Emirates Logistics City": 0.25},
                   "working_capital": 5.8, "working_capital_prior": 42.5, "noncore_property": 105.0,
                   "retentions_not_due": 79.0, "parent_related_party_share": 0.39},
    "projects": [
        {"name": "Project 1", "status": "About 23 months past planned completion"},
        {"name": "Project 2", "status": "No payments since 30 Apr 2026; 4 certified payments (AED 23m) pending; extension of time not formalised"},
        {"name": "Project 3", "status": "Past completion at 71.7% complete"},
    ],
    "stress": {"peak_deficit": 84.6, "peak_month": 18, "funded_lines": 80.0},
    "other_banks": {"new_facilities": 1570.0, "banks": 3, "facility_letters": 0},
    "recommendation": "Approve all",
    "cro_box": "",
    "conclusion": "Watchlist (Accepted Risk Watch), not Stage 2: no payment default, the deterioration is concentrated in "
                  "named projects with dated cures, and the counter-proposal ties new exposure to those cures. Rationale recorded.",
    "stage_view": {"stage": 1, "watch": "Accepted Risk Watch",
                   "rationale": "No DPD and no forbearance; the indicators (project delays, related-party dues, unexplained new facilities) "
                                "are watch triggers under CBUAE CRM SICR guidance but none meets a mandatory Stage 2 criterion today."},
}

CASE_B: dict[str, Any] = {
    "case_id": "PRP-B-ASB",
    "file_name": "Al_Sahel_Building_Materials_credit_proposal.docx",
    "borrower": "Al Sahel Building Materials Trading LLC",
    "group": "Al Sahel group",
    "profile": "UAE building materials trader",
    "sector": "Trading",
    "segment": "SME Banking",
    "currency": "AED",
    "rating": "B+",
    "pd": 0.0420,
    "tier": "Tier 2",
    "rm": "Commercial Banking, Trade Unit",
    "request_summary": [
        "Renew the AED 15m working capital limit",
        "New AED 10m 5-year vehicle finance limit with a 10% cash margin",
        "Lower the routing undertaking from 2x to 1.5x the limit",
    ],
    "facilities": [
        {"name": "Working capital (funded)", "kind": "funded", "existing": 15.0, "proposed": 15.0, "bps": 325},
        {"name": "Vehicle finance, 5 years (10% cash margin)", "kind": "funded", "existing": 0.0, "proposed": 10.0, "bps": 300,
         "cash_margin": 0.10},
    ],
    "stated_totals": {"existing": 15.0, "proposed": 25.0},
    "fees_upfront": 0.15,
    "group_cap": None,
    "deposits": {"avg_balance": 4.2, "profit_paid": 0.0100, "flow_fees": 0.08, "turnover_to_revenue": 0.33,
                 "routing_required": 2.0, "routing_achieved": 0.66, "returned_cheques": 0, "returned_cheque_note": ""},
    "financials": {"revenue": 92.0, "ebitda": 7.9, "debt_service": 5.2, "net_debt": 31.0,
                   "current_assets": 173.0, "related_party_receivable": 117.65, "related_party_share_ca": 0.68,
                   "goodwill_internal": 14.4, "receivables_over_1y": 0.505, "cash_cycle_days": 231,
                   "shareholder_withdrawals": 4.87},
    "network": [
        {"from": "Al Sahel Building Materials Trading LLC", "to": "Sahel Transport", "kind": "receivable", "label": "AED 71.6m receivable"},
        {"from": "Sahel Transport", "to": "Sahel Transport 51% sponsor", "kind": "ownership", "label": "51% sponsor"},
        {"from": "Sahel Transport 51% sponsor", "to": "Marwan Steel General Trading", "kind": "link", "label": "linked; Doubtful at another bank, AED 36m litigation"},
        {"from": "Al Sahel group", "to": "Marwan Steel General Trading", "kind": "ownership", "label": "25% through nominees"},
        {"from": "Marwan Steel General Trading", "to": "Two group entities at Loss (CBRBR)", "kind": "bureau", "label": "about AED 10m and AED 31m at Loss"},
        {"from": "Bank staff member", "to": "Corporate guarantor", "kind": "ownership", "label": "owns 51% of the guarantor"},
    ],
    "recommendation": "Approve renewal and new vehicle limit",
    "cro_box": "",
    "conclusion": "Renew only with the counter-proposal; decline the vehicle limit as structured; cross-default review before renewal.",
    "stage_view": {"stage": 2, "watch": "Bank Watchlist",
                   "rationale": "Qualified audit (Art 7.11f.ii) and connected-obligor default (Art 6.12) are SICR indicators; "
                                "the economic-dependency assessment decides whether UTP applies."},
}

CASES = {CASE_A["case_id"]: CASE_A, CASE_B["case_id"]: CASE_B}

#: Words in an uploaded file that identify each prepared case.
FINGERPRINTS = {CASE_A["case_id"]: ("gulf meridian", "meridian holding"),
                CASE_B["case_id"]: ("al sahel", "sahel transport")}
