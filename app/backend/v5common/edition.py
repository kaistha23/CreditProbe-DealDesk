"""Which edition of CreditProbe this process serves (Deal Desk edition, October 2026).

`V5_EDITION` is the one switch: `dealdesk` (the default, as in ops/v5.sh and the frontend's NEXT_PUBLIC_CP_EDITION) or
`full` (the whole R16 product). The services read it to choose their seed and to filter what they list; nothing in
Deal Desk's own engines reads it.

In the Deal Desk edition the product is Deal Desk; the Cockpit is the landing page with Deal Desk's brief and Ask;
Workspace, Mail, Playbook, Policy Docs, Projects, Investigations, Analyses, Data Domains, Trace and Admin serve Deal
Desk and show nothing of the modules that are not in the product (Early Warning, Borrower 360 as a screen, What-If,
Lenses, Scorecard, BRF, Open Banking).
"""
from __future__ import annotations

import os

DEALDESK = "dealdesk"
FULL = "full"


def edition() -> str:
    e = (os.environ.get("V5_EDITION") or DEALDESK).strip().lower()
    return FULL if e == FULL else DEALDESK


def is_dealdesk() -> bool:
    return edition() == DEALDESK


#: Data Domains in the Deal Desk edition: the domains Deal Desk's engines read, with the labels the RM sees. A domain
#: not listed here is not shown (its data stays on disk for the code that reads it). Relation allow-lists narrow a
#: domain to what Deal Desk reads.
DEALDESK_DOMAINS: dict[str, dict] = {
    "cockpit": {"label": "Credit books", "description": "The two credit books Deal Desk reads: Saudi corporate (20 quarters) and Saudi retail (20 months).",
                "relations": ["corp_borrower_quarter", "corp_facility_quarter", "corp_collateral_quarter", "corp_covenant_quarter"]},
    "borrower_360": {"label": "The Bank's file", "description": "What the bank holds on a customer: relationships, group, conduct, limits and utilisation, from LOS and core banking."},
    "bureau": {"label": "Credit bureau", "description": "Bureau reports, other banks' facilities and the central bank's risk bureau, as Deal Desk reads them.",
               "relations": ["bureau_corp_quarter", "bureau_entity_report", "bureau_cbrbr", "other_bank_facility"]},
    "deal_desk": {"label": "Deal Desk"},
    "deal_desk_products": {"label": "Deal Desk products"},
    "proposals": {"label": "Proposals"},
    "deposits": {"label": "Deposits and account behaviour", "relations": ["dep_account", "dep_month", "dep_derived"]},
    "collateral": {"label": "Collateral and guarantees", "relations": ["col_item", "col_guarantee", "col_related_party"]},
    "origination": {"label": "Origination"},
    "classification": {"label": "Classification"},
    "ecl_runs": {"label": "ECL runs", "relations": ["ecl_facility"]},
    "network_intel": {"label": "Network intelligence"},
    "governance": {"label": "Governance"},
}

#: The order the Data screen lists them.
DEALDESK_DOMAIN_ORDER = list(DEALDESK_DOMAINS)
