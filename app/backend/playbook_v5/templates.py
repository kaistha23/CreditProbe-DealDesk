"""The Playbook templates: what each kind of document is, and the sections it starts with.

Two lists: the full product's (committee pack, risk committee report, portfolio review, borrower memo, scenario report,
validation report) and the Deal Desk edition's (the RM's credit request, Credit's proposal, the committee paper and the
credit review opinion). `TEMPLATES` is the list this process serves, chosen by backend.v5common.edition.
"""
from __future__ import annotations

from typing import Any

from backend.v5common.edition import is_dealdesk

FULL_TEMPLATES: list[dict[str, Any]] = [
    {"id": "credit-committee-pack", "name": "Credit committee pack",
     "description": "The quarterly pack for the credit committee: the book, Early Warning, the borrowers for "
                    "decision and the scenarios behind the recommendations.",
     "sections": ["Executive summary", "Portfolio overview", "Early Warning", "Borrowers for decision", "Scenarios",
                  "Recommendations"]},
    {"id": "risk-committee-report", "name": "Risk committee report",
     "description": "The risk committee's view of credit risk against appetite: quality, ECL, concentrations and "
                    "emerging risks, with the actions taken.",
     "sections": ["Executive summary", "Risk appetite", "Credit quality and ECL", "Concentrations", "Emerging risks",
                  "Actions"]},
    {"id": "portfolio-review", "name": "Portfolio review",
     "description": "A review of one book or segment: what it holds, how its quality moved and the outlook.",
     "sections": ["Summary", "Composition", "Credit quality", "Movements", "Outlook"]},
    {"id": "borrower-credit-memo", "name": "Borrower credit memo",
     "description": "The credit memo for one borrower: the request, the analysis, the rating and the conditions.",
     "sections": ["Request and recommendation", "Borrower profile", "Financial analysis", "Facilities and security",
                  "Risk rating", "Early Warning", "Policy compliance", "Conditions"]},
    {"id": "scenario-report", "name": "Scenario report",
     "description": "One or more What-If scenarios: what was assumed, what it does to ECL and capital, and what "
                    "management can do about it.",
     "sections": ["Summary", "Scenario definition", "Results", "Drivers", "Management actions"]},
    {"id": "validation-report", "name": "Model validation report",
     "description": "A scorecard or model validation: scope, data, the tests with their verdicts, and the findings.",
     "sections": ["Summary and verdict", "Scope and data", "Discrimination", "Calibration", "Stability", "Variables",
                  "Overrides", "Findings and actions"]},
]

#: Deal Desk edition (PLAN_DEALDESK_EDITION Round C): the documents of a deal.
DEALDESK_TEMPLATES: list[dict[str, Any]] = [
    {"id": "credit-request", "name": "Credit request",
     "description": "The RM's business request to Credit: what the customer asks for, why the bank should do it, and "
                    "the facilities, security and conditions proposed.",
     "sections": ["Purpose and ask", "Customer and group", "Business case", "Financials", "Facilities requested",
                  "Security", "Conditions and covenants", "Recommendation"]},
    {"id": "credit-proposal", "name": "Credit proposal",
     "description": "Credit's proposal in the bank's form, its twenty sections condensed: the action requested, the "
                    "facilities, security, terms, Credit's comments, the financials, the exceptions and the analysis.",
     "sections": ["Header", "Action requested", "Facilities", "Security and support", "Terms and conditions",
                  "Credit division comments", "Financials", "Exceptions", "CreditProbe analysis", "Signatures"]},
    {"id": "committee-paper", "name": "Committee paper",
     "description": "One deal for the credit committee: the decision sought, the structure and its economics, the "
                    "risks and mitigants, the conditions and how the deal is monitored.",
     "sections": ["Decision sought", "Summary", "Structure and economics", "Risks and mitigants", "Conditions",
                  "Monitoring"]},
    {"id": "credit-review-opinion", "name": "Credit review opinion",
     "description": "Credit's opinion on a request: the findings, the conditions precedent and the covenants.",
     "sections": ["Opinion", "Findings", "Conditions precedent", "Covenants"]},
]



def current() -> list[dict[str, Any]]:
    """The templates this process serves (read on every call, so the edition switch is honoured at any time)."""
    return DEALDESK_TEMPLATES if is_dealdesk() else FULL_TEMPLATES


def __getattr__(name_: str) -> Any:  # TEMPLATES and IDS stay module attributes for their callers
    if name_ == "TEMPLATES":
        return current()
    if name_ == "IDS":
        return [t["id"] for t in current()]
    raise AttributeError(name_)


def _by_id() -> dict[str, dict[str, Any]]:
    return {t["id"]: t for t in FULL_TEMPLATES + DEALDESK_TEMPLATES}


def default() -> str:
    """The template an upload falls back to when nothing in its title or file name names one."""
    return "credit-proposal" if is_dealdesk() else "portfolio-review"


def name(template_id: str) -> str:
    return _by_id().get(template_id, {}).get("name", template_id)


def sections(template_id: str) -> list[str]:
    return list(_by_id()[template_id]["sections"])


def guess(text: str) -> str | None:
    """Which template a sentence asks for ("draft a credit memo for CB01312")."""
    t = text.lower()
    if is_dealdesk():
        for words, tid in ((("committee paper", "committee", "ccp"), "committee-paper"),
                           (("review opinion", "credit review", "opinion", "review"), "credit-review-opinion"),
                           (("credit proposal", "proposal", "bank form"), "credit-proposal"),
                           (("credit request", "business request", "request"), "credit-request")):
            if any(w in t for w in words):
                return tid
        return None
    for words, tid in ((("credit committee", "committee pack", "ccp"), "credit-committee-pack"),
                       (("risk committee",), "risk-committee-report"),
                       (("portfolio review", "sector review", "book review", "review of the"), "portfolio-review"),
                       (("credit memo", "memo"), "borrower-credit-memo"),
                       (("scenario report", "scenario", "what-if", "what if", "stress"), "scenario-report"),
                       (("validation",), "validation-report")):
        if any(w in t for w in words):
            return tid
    return None
