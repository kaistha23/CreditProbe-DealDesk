"""R12 Session E: product templates (PLAN_R12 §1.8, I28). Session P owns the analytics in backend/dealdesk/products/**.

A template decides, for one product: the deal-page steps, the fields the Proposal step shows, the review checks
that apply, the document rules (dd_document_rule ids), the proposal sections in PROPOSAL_ANATOMY order (plus the
CreditProbe sections), the analytics panels and the Data Domains relations the product reads.

    from backend.dealdesk.products import templates
    templates.for_deal("R12-TWB")["sections"]       # contracting: includes financed_projects and project_cashflow
    templates.applies("R12-SME1", "section", "group_exposure")  -> False (SME short paper)
    templates.TEMPLATES["sme"]["lane"]              -> "fast_track"
"""
from __future__ import annotations

import copy
from typing import Any

STEPS_FULL = ["proposal", "review", "analysis", "stress", "structure", "recommendation"]   # I15 order
STEPS_FAST = ["proposal", "recommendation"]                                                # SME fast-track (one screen)

#: PROPOSAL_ANATOMY §2 sections (ids used by F's section registry) and the CreditProbe sections (I25)
ANATOMY = [
    ("header", "Header block"), ("action_requested", "Action requested"), ("facilities", "Facilities"),
    ("security", "Security and support"), ("terms", "Terms and conditions"), ("group_exposure", "Group exposure and references"),
    ("background", "Background"), ("relationship", "Relationship with the bank"), ("financed_projects", "Status of financed projects"),
    ("cbrbr", "Central-bank risk bureau"), ("bureau", "Credit bureau"), ("other_banks", "Other banks' facilities"),
    ("project_details", "New project details and project cash flow"), ("financials", "Financials"),
    ("synopsis", "Financial synopsis"), ("geopolitical", "Effects of the geopolitical and market situation"),
    ("exceptions", "Exceptions and other observations"), ("strengths", "Key strengths"), ("recommendation", "Recommendation"),
    ("signatures", "Signature blocks"),
]
CREDITPROBE = [("raroc", "RAROC, SVA and the optimiser's alternatives"), ("forward_risk", "Forward risk"),
               ("stress", "Stress verdict and monitoring tier"), ("precedent", "Precedent")]
PRODUCT_SECTIONS = [("syndication", "Syndication: our share, role and sell-down"), ("escrow", "Escrow account and release waterfall"),
                    ("sme_decision", "SME scorecard decision")]
SECTION_LABEL = dict(ANATOMY + CREDITPROBE + PRODUCT_SECTIONS)

#: review checks (I16 points; the product decides which sub-checks run)
CHECKS_CORE = ["completeness", "claims_vs_evidence", "consistency", "reperformed_analysis", "policy_and_regulation",
               "group_and_connected", "collateral_and_legal", "track_record", "precedent_and_peers", "language", "versions", "outputs",
               "adjusted_ratios", "receivables_quality", "auditor_quality", "bureau_other_bank_matrix", "earlier_conditions", "insider_links"]

_CORE_REL = ["dd_deal", "dd_facility_limit", "dd_security", "dd_tnc", "dd_group_exposure", "dd_reference", "dd_business_profile",
             "dd_financials_detail", "dd_obligor_financials", "dd_document", "dd_condition", "dd_review_finding", "dd_monitoring_plan",
             "bureau_entity_report", "bureau_cbrbr", "other_bank_facility", "b360_entity", "b360_shareholder", "b360_board",
             "b360_insider_link", "b360_ownership_change", "b360_edge", "dd_account_conduct", "dd_returned_cheque", "dd_promise"]

_CORE_FIELDS = ["facility_type", "structure", "amount", "tenor_years", "grace_years", "amortisation", "margin_bps", "upfront_fee_bps",
                "commission_bps", "utilisation_pct", "funded_share_pct", "cash_margin_pct", "covenant_package", "guarantee_coverage_pct"]

TEMPLATES: dict[str, dict[str, Any]] = {
    "corporate": {
        "label": "Corporate term, revolver and trade",
        "lane": "full", "steps": STEPS_FULL,
        "limit_products": ["TL", "RCF", "OD", "LC_SIGHT", "LC_USANCE", "LCM", "TR", "LG", "LG_CASH"],
        "fields": _CORE_FIELDS + ["limit_tree", "sub_limits", "cash_margin_by_limit", "rate_floor"],
        "checks": CHECKS_CORE,
        "document_rules": ["DR-01", "DR-02", "DR-03", "DR-04", "DR-05", "DR-06", "DR-07", "DR-08", "DR-09", "DR-10"],
        "sections": [s for s, _ in ANATOMY if s not in ("financed_projects", "project_details")] + [s for s, _ in CREDITPROBE],
        "analytics": ["raroc", "optimiser", "forward_risk", "stress_ladder", "reverse_stress", "precedent", "group_cap", "conduct", "swot"],
        "stress_families": ["macro", "borrower", "collateral", "rating", "combined"],
        "relations": _CORE_REL,
    },
    "contracting": {
        "label": "Contracting and project limits",
        "lane": "full", "steps": STEPS_FULL,
        "limit_products": ["BB", "APG", "PB", "RB", "LC_SIGHT", "LC_USANCE", "LCM", "DMCCM_PC", "DMCCM_SUP", "OD", "LG", "LG_CASH", "VHM"],
        "fields": _CORE_FIELDS + ["limit_tree", "project_limits", "pct_financed_of_certificate", "last_certificates_not_financed",
                                  "retention_pct", "cover_ratio_min", "apg_pct", "pb_pct"],
        "checks": CHECKS_CORE + ["backlog_vs_revenue", "backlog_concentration", "project_delays", "payment_delays", "eot_formalised",
                                 "lg_wording", "employer_credit", "cover_ratio"],
        "document_rules": ["DR-01", "DR-02", "DR-03", "DR-04", "DR-05", "DR-06", "DR-07", "DR-08", "DR-09", "DR-11", "DR-12", "DR-13", "DR-14"],
        "sections": [s for s, _ in ANATOMY] + [s for s, _ in CREDITPROBE],
        "analytics": ["raroc", "optimiser", "forward_risk", "stress_ladder", "reverse_stress", "precedent", "group_cap", "conduct", "swot",
                      "project_cashflow", "delay_stress", "cover_ratio", "employer_credit", "financed_projects"],
        "stress_families": ["macro", "borrower", "collateral", "rating", "project", "combined"],
        "relations": _CORE_REL + ["dd_project", "dd_project_cashflow"],
    },
    "escrow": {
        "label": "Escrow / project-account financing",
        "lane": "full", "steps": STEPS_FULL,
        "limit_products": ["ESCROW_TL"],
        "fields": _CORE_FIELDS + ["escrow_account", "release_rules", "retention_pct", "cover_ratio_min", "units_sold", "collections"],
        "checks": CHECKS_CORE + ["escrow_cover", "sales_progress", "construction_progress", "release_compliance"],
        "document_rules": ["DR-01", "DR-02", "DR-03", "DR-04", "DR-05", "DR-06", "DR-08", "DR-09", "DR-15", "DR-16"],
        "sections": [s for s, _ in ANATOMY if s not in ("financed_projects",)] + ["escrow"] + [s for s, _ in CREDITPROBE],
        "analytics": ["raroc", "optimiser", "forward_risk", "stress_ladder", "precedent", "escrow_waterfall", "escrow_cover", "sales_stress"],
        "stress_families": ["macro", "borrower", "collateral", "rating", "combined"],
        "relations": _CORE_REL + ["dd_escrow_account", "dd_escrow"],
    },
    "syndicated": {
        "label": "Syndicated participation",
        "lane": "full", "steps": STEPS_FULL,
        "limit_products": ["SYND_TL"],
        "fields": _CORE_FIELDS + ["hold_pct", "role", "agent_bank", "sell_down", "pari_passu", "majority_lenders_pct"],
        "checks": [c for c in CHECKS_CORE if c not in ("bureau_other_bank_matrix", "insider_links")] + ["agent_information", "our_share_of_covenants",
                                                                                                         "sell_down_feasibility"],
        "document_rules": ["DR-01", "DR-03", "DR-05", "DR-09", "DR-17"],   # lighter documents for participants
        "sections": [s for s, _ in ANATOMY if s not in ("financed_projects", "project_details", "other_banks", "cbrbr")] + ["syndication"] +
                    [s for s, _ in CREDITPROBE],
        "analytics": ["raroc_on_our_share", "optimiser", "forward_risk", "stress_ladder", "precedent", "sell_down"],
        "stress_families": ["macro", "borrower", "rating", "combined"],
        "relations": _CORE_REL + ["dd_syndication"],
    },
    "sme": {
        "label": "SME programme lending",
        "lane": "fast_track", "steps": STEPS_FAST,
        "limit_products": ["SME_TL"],
        "fields": ["amount", "tenor_years", "facility_type", "margin_bps", "programme"],
        "checks": ["completeness", "scorecard", "policy_rules", "doa", "bureau", "conduct"],
        "document_rules": ["DR-01", "DR-05", "DR-06", "DR-08", "DR-18"],
        "sections": ["header", "action_requested", "facilities", "security", "sme_decision", "bureau", "relationship", "recommendation", "signatures"],
        "analytics": ["sme_decision", "raroc"],
        "stress_families": [],
        "relations": ["dd_deal", "dd_sme_application", "dd_facility_limit", "dd_document", "bureau_entity_report", "dd_account_conduct",
                      "b360_entity", "b360_shareholder"],
        #: an SME application leaves the lane for the full flow when the scorecard refers it or a rule is excepted
        "exit_to_full_flow": {"decision": ["refer"], "exception_flag": 1},
        "doa_by_amount_mn": [(1.0, "SME Credit Officer"), (5.0, "SME Credit Manager"), (10.0, "Head of SME Credit"), (None, "Full flow")],
    },
}


def template(product: str) -> dict[str, Any]:
    t = copy.deepcopy(TEMPLATES.get(product) or TEMPLATES["corporate"])
    t["product"] = product if product in TEMPLATES else "corporate"
    t["section_labels"] = {s: SECTION_LABEL[s] for s in t["sections"]}
    return t


def for_deal(pid: str) -> dict[str, Any]:
    """The template of a deal, by its dd_deal.product (DD and PL deals: corporate, contracting or sme)."""
    from backend.dealdesk.data import deals
    t = template(deals.product_of(pid))
    t["proposal_id"] = pid
    return t


def applies(pid: str, kind: str, item: str) -> bool:
    """Does a step / section / check / analytic / document rule apply to this deal?"""
    key = {"step": "steps", "section": "sections", "check": "checks", "analytic": "analytics", "document_rule": "document_rules"}[kind]
    return item in for_deal(pid)[key]


def doa_for_sme(amount_mn: float) -> str:
    for cap, level in TEMPLATES["sme"]["doa_by_amount_mn"]:
        if cap is None or amount_mn <= cap:
            return level
    return "Full flow"


def catalogue() -> list[dict[str, Any]]:
    """One row per product for the UI and Noor: label, lane, steps, sections and documents counts."""
    return [{"product": k, "label": v["label"], "lane": v["lane"], "steps": v["steps"], "sections": len(v["sections"]),
             "document_rules": len(v["document_rules"]), "analytics": v["analytics"]} for k, v in TEMPLATES.items()]
