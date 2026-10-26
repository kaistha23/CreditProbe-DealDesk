"""R16 session b: the dd_business_request relation (pure data in the shape of backend/dealdesk/data/schema.py).

One row per business request written (request_id is deterministic: same customer, ask and notes -> same id, so a re-write
upserts). The whole paper (sections, figures with sources) is kept in paper_json, so a shared request reopens exactly as written.
"""
from __future__ import annotations

DD_DIR = "data/dealdesk/dd-saudi-v1"
PERIOD = "reporting_quarter"

COLUMNS = [
    ("request_id", "text", "", "BR-<proposal_id>-<hash 8 of customer, ask and notes> (deterministic)."),
    ("proposal_id", "text", "", "Deal / customer file id (R16-C1 ... for the R16 customer packs; dd_deal.proposal_id when one exists)."),
    ("customer_key", "text", "", "Customer key in the R16 customer packs (c1-c4), empty for another customer."),
    ("customer_name", "text", "", "Customer name as on the CR."),
    ("cif", "text", "", "Borrower 360 id; '' for a new-to-bank customer."),
    ("cr_number", "text", "", "Commercial Registration number."),
    ("rm", "text", "", "Relationship manager who wrote the request (signed-in user)."),
    ("ask_text", "text", "", "The ask as typed in the chat box."),
    ("notes_text", "text", "", "The RM notes as typed."),
    ("items_n", "int", "", "Facilities named in the ask."),
    ("total_existing_mn", "float", "SAR m", "Total existing limits with the Bank (dd_facility_limit)."),
    ("total_proposed_mn", "float", "SAR m", "Total proposed limits after the request."),
    ("figures_n", "int", "", "Figures printed, each with its source (paper_json.figures)."),
    ("untraced_n", "int", "", "Figures without a source (must be 0)."),
    ("docs_received_n", "int", "", "Checklist documents received."),
    ("docs_missing_n", "int", "", "Checklist documents missing."),
    ("docs_expired_n", "int", "", "Checklist documents expired."),
    ("disclosures_n", "int", "", "Points disclosed for credit's review."),
    ("origin", "text", "", "Where the documents came from: intake | caller | pack."),
    ("status", "text", "", "written | shared."),
    ("shared_with", "text", "", "Users the request was shared with (comma-separated usernames)."),
    ("paper_json", "json", "", "The whole request: sections of blocks, figures with sources, notes placement, plain words."),
    ("written_at", "ts", "", "When the request was written (UTC)."),
]

RELATION = {
    "dd_business_request": {
        "domain": "deal_desk", "folder": DD_DIR, "label": "RM business requests",
        "grain": "one row per business request written", "keys": ["request_id", PERIOD], "period": PERIOD,
        "description": "The RM's business request in the bank form (action requested, facilities, security, terms, group exposure, background, "
                       "relationship, financials, RM's justification), written by rules from the RM's ask and notes, the uploaded documents and the "
                       "Bank's own data; every figure carries its source. Written by backend/dealdesk/rm_request (R16 b).",
        "columns": COLUMNS, "owner": "b", "writers": "b (business request writer)"},
}
