"""The section registry of the bank-form credit proposal: 20 anatomy sections (PROPOSAL_ANATOMY.md §2) plus the CreditProbe
sections, each with its data contract (the Data Domains relations it reads; `needs` must have rows, `uses` may be empty) and
its writer.

    for s in SECTIONS: s.key, s.n, s.heading, s.voice, s.part, s.needs, s.uses, s.writer
    PROPOSAL_ORDER / COMMITTEE_ORDER    the keys in the order of each paper

Voices: "form" (header, signatures: no prose rules), "business" (page 1: what business asks), "credit" (the credit division's
comments and recommendation), "creditprobe" (CreditProbe analytics, written in the credit voice).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.dealdesk.house_style.bankform import cp_writers as C
from backend.dealdesk.house_style.bankform import r14 as R14
from backend.dealdesk.house_style.bankform.book import augment as _book
from backend.dealdesk.house_style.bankform import writers as W


@dataclass(frozen=True)
class Section:
    key: str
    n: int | None             # the anatomy number (1-20); None for a CreditProbe section
    heading: str
    voice: str
    part: str                 # anatomy | creditprobe
    needs: tuple[str, ...]    # relations that must have rows for the contract to be met
    uses: tuple[str, ...]     # relations read when present
    writer: Callable[[Any], tuple[list[dict[str, Any]], list[str]]]
    aliases: tuple[str, ...] = field(default=())


SECTIONS: list[Section] = [
    Section("header", 1, "Header block", "form", "anatomy", ("dd_proposal",), (), W.w_header, ("header", "customer details")),
    Section("action", 2, "Action requested", "business", "anatomy", ("dd_proposal",), ("dd_facility_limit", "dd_reference"), R14.w_action,
            ("action requested", "request", "the ask", "proposal")),
    Section("facilities", 3, "Facilities", "business", "anatomy", ("dd_facility_limit",), ("dd_proposal_facility",), R14.w_facilities,
            ("facilities", "facility", "limits")),
    Section("security", 4, "Security and support", "business", "anatomy", ("dd_security",), (), _book("security", W.w_security), ("security", "collateral", "support")),
    Section("terms", 5, "Terms and conditions", "business", "anatomy", ("dd_tnc",), ("dd_condition",), _book("terms", W.w_terms), ("terms", "conditions", "t&c")),
    Section("group_exposure", 6, "Group exposure and references", "credit", "anatomy", ("dd_proposal",), ("b360_entity", "dd_reference", "dd_workflow_event"),
            _book("group_exposure", W.w_group_exposure), ("group exposure", "references")),
    Section("background", 7, "Background and ownership", "credit", "anatomy", ("b360_shareholder",), ("b360_board", "b360_ownership_change", "b360_entity", "dd_business_profile"),
            _book("background", W.w_background), ("background", "ownership", "shareholders", "obligor")),
    Section("relationship", 8, "Relationship with the bank", "credit", "anatomy", ("dd_account_conduct",), ("dd_reference", "dd_promise"), _book("relationship", W.w_relationship),
            ("relationship", "conduct", "account")),
    Section("projects", 9, "Status of financed projects", "credit", "anatomy", (), ("dd_project",), W.w_projects, ("financed projects", "projects")),
    Section("syndication", None, "Syndication: our share, role and sell-down", "credit", "product", ("dd_syndication",), (), C.w_syndication, ("syndication",)),
    Section("escrow", None, "Escrow account and release waterfall", "credit", "product", ("dd_escrow_account",), ("dd_escrow",), C.w_escrow, ("escrow",)),
    Section("sme_decision", None, "SME scorecard decision", "credit", "product", ("dd_sme_application",), (), C.w_sme_decision, ("sme", "scorecard")),
    Section("cbrbr", 10, "Central bank risk bureau (CBRBR)", "credit", "anatomy", ("bureau_cbrbr",), (), _book("cbrbr", W.w_cbrbr), ("cbrbr", "risk bureau")),
    Section("bureau", 11, "Credit bureau", "credit", "anatomy", ("bureau_entity_report",), (), _book("bureau", W.w_bureau), ("aecb", "simah", "credit bureau", "bureau")),
    Section("other_banks", 12, "Other banks' facilities", "credit", "anatomy", ("other_bank_facility",), (), _book("other_banks", W.w_other_banks), ("other banks", "other bank")),
    Section("new_project", 13, "New project details and cash flow", "credit", "anatomy", (), ("dd_project", "dd_project_cashflow"), W.w_new_project,
            ("new project", "project details", "project cash flow")),
    Section("financials", 14, "Financials", "credit", "anatomy", ("dd_financials_detail",), (), _book("financials", W.w_financials), ("financials", "financial statements")),
    Section("synopsis", 15, "Financial synopsis", "credit", "anatomy", ("dd_financials_detail",), (), W.w_synopsis, ("synopsis", "financial analysis")),
    Section("geopolitical", 16, "Effects of the current geopolitical and market situation", "credit", "anatomy", (), ("dd_stress_scenario", "dd_stress_result", "dd_business_profile"),
            R14.w_geopolitical, ("geopolitical", "market situation")),
    Section("exceptions", 17, "Exceptions and other observations", "credit", "anatomy", ("dd_review_finding",), ("dd_document", "b360_insider_link"), W.w_exceptions,
            ("exceptions", "observations", "deviations")),
    Section("cp_group", None, "Group and governance (CreditProbe)", "creditprobe", "creditprobe", ("b360_shareholder",),
            ("b360_board", "b360_insider_link", "b360_entity", "rel_shared_collateral"), C.w_group, ("group and governance",)),
    # Round G: counterparties in difficulty or in other deals, from the Deal Desk graph (optional: never required by coverage)
    Section("cp_counterparty", None, "Counterparty exposure (CreditProbe)", "creditprobe", "optional", (), (),
            lambda D: __import__("backend.dealdesk.graph.section", fromlist=["w"]).w_counterparty_proposal(D), ("counterparty exposure",)),
    Section("cp_selected", None, "Selected structure, approval authority, capacity and pipeline fit (CreditProbe)", "creditprobe", "creditprobe", ("dd_proposal",), ("dd_structure_set", "dd_stress_proof"),
            R14.w_selected, ("selected structure",)),
    Section("cp_findings", None, "Findings register, RAROC bridge and capacity (CreditProbe)", "creditprobe", "creditprobe", ("dd_proposal",), ("dd_review_finding",),
            R14.w_findings, ("findings register",)),
    Section("cp_raroc", None, "RAROC and SVA on the selected structure (CreditProbe)", "creditprobe", "creditprobe", ("dd_proposal",), ("dd_result",), R14.w_raroc,
            ("raroc", "sva")),
    Section("cp_forward", None, "Forward risk (CreditProbe)", "creditprobe", "creditprobe", (), ("dd_forward_risk",), C.w_forward, ("forward risk",)),
    Section("cp_stress", None, "Stress verdict and monitoring tier (CreditProbe)", "creditprobe", "creditprobe", ("dd_stress_result", "dd_monitoring_plan"), (),
            C.w_stress, ("stress", "monitoring tier")),
    Section("cp_precedent", None, "Precedent (CreditProbe)", "creditprobe", "creditprobe", (), ("dd_precedent",), C.w_precedent, ("precedent",)),
    Section("cp_swot", None, "SWOT and weakness-to-mitigant map (CreditProbe)", "creditprobe", "creditprobe", ("dd_swot",), (), C.w_swot, ("swot",)),
    Section("strengths", 18, "Key strengths", "credit", "anatomy", (), ("dd_swot",), W.w_strengths, ("key strengths", "strengths")),
    Section("recommendation", 19, "Credit division recommendation", "credit", "anatomy", ("dd_proposal",), ("dd_monitoring_plan", "dd_result"),
            R14.w_recommendation, ("recommendation",)),
    Section("signatures", 20, "Signatures and approval", "form", "anatomy", (), (), R14.w_signatures, ("signatures", "approval", "committee instructions")),
]

BY_KEY = {s.key: s for s in SECTIONS}
ANATOMY = [s.key for s in SECTIONS if s.part == "anatomy"]
CREDITPROBE = [s.key for s in SECTIONS if s.part == "creditprobe"]
PRODUCT = [s.key for s in SECTIONS if s.part == "product"]
#: the product template's section ids (backend/dealdesk/products/templates.py) -> this registry's keys
TEMPLATE_KEYS = {"action_requested": "action", "financed_projects": "projects", "project_details": "new_project", "raroc": "cp_raroc",
                 "forward_risk": "cp_forward", "stress": "cp_stress", "precedent": "cp_precedent"}
PROPOSAL_ORDER = [s.key for s in SECTIONS]
COMMITTEE_ORDER = ["header", "action", "facilities", "security", "terms", "group_exposure", "cp_group", "cp_counterparty", "background", "relationship", "projects",
                   "new_project", "syndication", "escrow", "sme_decision", "cbrbr", "bureau", "other_banks", "financials", "synopsis", "geopolitical", "cp_selected", "cp_findings", "cp_raroc", "cp_forward", "cp_stress",
                   "cp_precedent", "exceptions", "cp_swot", "strengths", "recommendation", "signatures"]

assert len(ANATOMY) == 20 and sorted(s.n for s in SECTIONS if s.n) == list(range(1, 21))
assert sorted(COMMITTEE_ORDER) == sorted(PROPOSAL_ORDER)


def for_template(template: dict[str, Any] | None, order: list[str]) -> tuple[list[str], list[str]]:
    """(keys to write, keys required by coverage) for a deal's product template. A full-lane product keeps every anatomy and
    CreditProbe section (a section the template leaves out says 'not applicable') and adds its product section; the SME fast-track
    lane writes only its template's short paper."""
    if not template:
        keys = [k for k in order if k not in PRODUCT]
        return keys, ANATOMY + CREDITPROBE
    tk = [TEMPLATE_KEYS.get(x, x) for x in template.get("sections", [])]
    if template.get("lane") == "fast_track":
        keys = [k for k in order if k in tk]
        return keys, keys
    keys = [k for k in order if k not in PRODUCT or k in tk]
    return keys, ANATOMY + CREDITPROBE + [k for k in PRODUCT if k in tk]


def contract() -> list[dict[str, Any]]:
    """The registry as data (API and docs)."""
    return [{"key": s.key, "n": s.n, "heading": s.heading, "voice": s.voice, "part": s.part, "needs": list(s.needs), "uses": list(s.uses)} for s in SECTIONS]
