"""R14 session p: the dd_proposal_quality relation (K31, K33), pure data in the shape of backend/dealdesk/data/schema.py.

One row per (run, check): every check the proposal check ran on an RM proposal, with its result and evidence, plus one
`check = "section_score"` row per anatomy section and one `check = "proposal_score"` row per run.
"""
from __future__ import annotations

DD_DIR = "data/dealdesk/dd-saudi-v1"
PERIOD = "reporting_quarter"

COLUMNS = [
    ("quality_id", "text", "", "Row id: <run_id>:<n>."),
    ("run_id", "text", "", "Check run: PQ-<proposal_id>-<document hash 8> (same document, same run id: deterministic)."),
    ("proposal_id", "text", "", "Deal checked (dd_deal.proposal_id)."),
    ("document", "text", "", "What was checked: the uploaded Word file name, the memo file, or 'submission record' (dd_deal)."),
    ("document_sha", "text", "", "SHA-256 (first 16 hex) of the document checked."),
    ("rm", "text", "", "Relationship manager who wrote the proposal (dd_deal.rm)."),
    ("branch", "text", "", "Branch / business unit of the proposal."),
    ("sector", "text", "", "Obligor sector."),
    ("section_key", "text", "", "Anatomy section key (bankform registry: header, action, facilities ... signatures); '' for the whole proposal."),
    ("section_n", "int", "", "Anatomy section number 1-20 (0 for the whole proposal)."),
    ("section_heading", "text", "", "Anatomy section heading."),
    ("check", "text", "", "Check id (e.g. ACC-RETURNED-CHEQUES, COMP-SECTION, section_score, proposal_score)."),
    ("category", "text", "", "completeness | accuracy | consistency | disclosure | voice | policy | score."),
    ("severity", "text", "", "critical | major | minor | info."),
    ("result", "text", "", "defect | observation | pass | score."),
    ("defect_type", "text", "", "Stable defect type (the answer key's vocabulary), '' for passes and scores."),
    ("title", "text", "", "One line stating the result, with the numbers."),
    ("claim", "text", "", "The proposal's words the check is about (quoted), '' when the defect is an omission."),
    ("evidence", "text", "", "What the bank's data shows, with figures and dates."),
    ("evidence_relation", "text", "", "Data Domains relation the evidence comes from."),
    ("evidence_key", "text", "", "Row key in that relation (k=v;...)."),
    ("query", "text", "", "Query to the RM in plain words ('' when none)."),
    ("score", "float", "points", "Section score 0-100 (section_score rows) or proposal score 0-100 (proposal_score rows); null on check rows."),
    ("defects_n", "int", "", "Defects (critical + major) in the section or proposal (score rows)."),
    ("status", "text", "", "open | sent_to_rm | answered | closed (query workflow)."),
    ("checked_at", "ts", "", "When the check ran (the data build stamps a fixed time)."),
]

RELATION = {
    "dd_proposal_quality": {
        "domain": "deal_desk", "folder": DD_DIR, "label": "Proposal quality checks",
        "grain": "one row per check run and check (plus section and proposal score rows)", "keys": ["quality_id", PERIOD], "period": PERIOD,
        "description": "Quality of the RM's proposal (K31/K33), separate from the quality of the deal: completeness against the 20-section "
                       "bank-form anatomy, accuracy of claims against Data Domains, internal consistency, disclosure, voice and policy/T&C gaps; "
                       "score by section, evidence and the query to the RM. Written by the proposal check (backend/dealdesk/proposal_check).",
        "columns": COLUMNS, "owner": "p", "writers": "p (proposal check, batch check)"},
}
