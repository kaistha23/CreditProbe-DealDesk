"""R16 i: the Data Domains relations of the customer file (document intake). Pure data, merged into
backend/dealdesk/data/schema.py (one `RELATIONS.update(INTAKE)` line), same pattern as proposal_check/relation.py.

Every uploaded document, every field read from it, every checklist line and every reconciliation result is a row,
so a figure in the business request or the credit response traces to the document line it came from.
"""
from __future__ import annotations

from typing import Any

W = "i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)"


def _rel(rid: str, label: str, grain: str, key: str, desc: str, cols: list[tuple[str, str, str, str]]) -> dict[str, Any]:
    from backend.dealdesk.data.schema import DD_DIR, PERIOD, _r
    return _r("deal_desk", DD_DIR, label, grain, [key, PERIOD], desc, cols, owner="i", writers=W)


def relations() -> dict[str, dict[str, Any]]:
    MN = "SAR mn"
    return {
        "dd_intake_file": _rel("dd_intake_file", "Customer file (intake)", "one row per customer file", "intake_id",
            "A customer file opened on Deal Desk by uploading the customer's documents (R16 i): who the customer is, "
            "whether the Bank already knows them (matched by CR number) and the checklist counts.", [
            ("intake_id", "text", "", "Customer file id (IN-…)."),
            ("proposal_id", "text", "", "Deal the file is attached to (blank until a proposal is created from it)."),
            ("customer_name", "text", "", "Customer legal name as printed on the documents (fictional)."),
            ("cr_number", "text", "", "Commercial registration number read from the documents."),
            ("existing_customer", "flag", "", "1 when the CR number matches a customer of the Bank."),
            ("matched_cif", "text", "", "CIF of the matched customer (blank when new to bank)."),
            ("matched_proposal_id", "text", "", "Deal of the matched customer in Data Domains (bank-side data)."),
            ("case_kind", "text", "", "existing, new_to_bank; contractor when project documents are present."),
            ("as_of", "date", "", "Date the checklist was judged on (validity and expiry)."),
            ("documents_n", "int", "n", "Files read."),
            ("received_n", "int", "n", "Checklist lines received."),
            ("missing_n", "int", "n", "Checklist lines missing."),
            ("expired_n", "int", "n", "Checklist lines expired or stale."),
            ("flags_n", "int", "n", "Reconciliation results that differ or need a question."),
            ("created_by", "text", "", "User who opened the file."),
            ("created_at", "ts", "", "When the file was opened."),
        ]),
        "dd_intake_document": _rel("dd_intake_document", "Customer file documents", "one row per uploaded file", "doc_id",
            "Each uploaded file: how it was read (Word, PDF text, OCR of a photo or scan), what it was classified as and "
            "with what confidence, its dates and its validity status on the as-of date.", [
            ("doc_id", "text", "", "Document id (<intake_id>-Dnn)."),
            ("intake_id", "text", "", "Customer file."),
            ("proposal_id", "text", "", "Deal (blank until attached)."),
            ("file_name", "text", "", "Uploaded file name."),
            ("file_kind", "text", "", "word, pdf, image or text."),
            ("read_method", "text", "", "Word, PDF text, scanned PDF (OCR), photo (OCR), text."),
            ("ocr_engine", "text", "", "rapidocr or tesseract when OCR was used."),
            ("pages", "int", "n", "Pages read."),
            ("doc_type", "text", "", "Document type code (data/dealdesk/demo_customers/CONTRACT.md §4), or unknown."),
            ("doc_label", "text", "", "Document type in words."),
            ("confidence", "float", "0-1", "Classifier confidence (score margin over the runner-up)."),
            ("subject", "text", "", "Owner, bank, account, project, certificate or period the document is about."),
            ("customer_name", "text", "", "Customer name printed on it."),
            ("cr_number", "text", "", "CR number printed on it."),
            ("issue_date", "date", "", "Issue / report / statement date."),
            ("expiry_date", "date", "", "Printed expiry or valid-until date."),
            ("period_from", "date", "", "Period start (statements, filings, accounts)."),
            ("period_to", "date", "", "Period end."),
            ("status", "text", "", "received, expired (printed expiry passed) or stale (older than the validity rule)."),
            ("fields_n", "int", "n", "Fields read from it."),
            ("sha256", "text", "", "Content hash of the file (same file uploaded twice is read once)."),
        ]),
        "dd_intake_field": _rel("dd_intake_field", "Customer file fields", "one row per field read from a document", "field_row_id",
            "Each printed field read from a document, with the line it was read from; list fields (tables) are one row "
            "with the table in value_json.", [
            ("field_row_id", "text", "", "<doc_id>:<field>."),
            ("intake_id", "text", "", "Customer file."),
            ("proposal_id", "text", "", "Deal (blank until attached)."),
            ("doc_id", "text", "", "Document."),
            ("doc_type", "text", "", "Document type code."),
            ("field", "text", "", "Field name (CONTRACT.md §4)."),
            ("label", "text", "", "Label printed on the document."),
            ("value_text", "text", "", "Value as text (dates ISO)."),
            ("value_num", "float", "", "Value as a number (SAR units for amounts, % for percentages; NaN when not numeric)."),
            ("value_mn", "float", MN, "Amount in SAR million (amount fields only)."),
            ("value_json", "json", "", "Rows of a list field (table)."),
            ("line_no", "int", "n", "Line of the document text the value was read from."),
            ("raw_text", "text", "", "The text as read (OCR or file)."),
        ]),
        "dd_intake_check": _rel("dd_intake_check", "Customer file checklist", "one row per required document line", "check_id",
            "The document checklist against the requirements (KYC, company legal, credit bureau, financials, bank "
            "statements and the extras): received, missing, expired or not applicable, with the document that answers it.", [
            ("check_id", "text", "", "<intake_id>:<doc_type>:<subject>."),
            ("intake_id", "text", "", "Customer file."),
            ("proposal_id", "text", "", "Deal (blank until attached)."),
            ("req_group", "text", "", "kyc, company_legal, credit_bureau, financials, bank_statements, extras."),
            ("doc_type", "text", "", "Document type code."),
            ("requirement", "text", "", "What is required, in words."),
            ("subject", "text", "", "For whom / which period, bank or project."),
            ("status", "text", "", "received, missing, expired, not_applicable."),
            ("doc_ids", "text", "", "Documents that answer it (comma separated)."),
            ("reason", "text", "", "Why this status (dates, coverage, rule)."),
            ("valid_until", "date", "", "When the received document stops being valid (blank when it never expires)."),
            ("rule_ref", "text", "", "Deal Desk document rule it maps to (DR-nn), when one exists."),
        ]),
        "dd_intake_reconciliation": _rel("dd_intake_reconciliation", "Customer file reconciliation", "one row per cross-document test",
            "recon_id",
            "Key figures joined across documents and the Bank's data: revenue in the audited accounts vs bank-statement "
            "credits vs VAT filings; owners in the AoA vs CR vs bureau; identity; arithmetic; concentration and other "
            "findings only visible when the documents are read together.", [
            ("recon_id", "text", "", "<intake_id>:<test>."),
            ("intake_id", "text", "", "Customer file."),
            ("proposal_id", "text", "", "Deal (blank until attached)."),
            ("topic", "text", "", "revenue, owners, identity, arithmetic, concentration, bureau, projects, guarantor, saudisation, related_party, conduct."),
            ("title", "text", "", "Test in words."),
            ("status", "text", "", "agrees, differs, flag (needs a question) or info."),
            ("severity", "int", "0-3", "0 info, 1 note, 2 query the RM, 3 key concern."),
            ("value_a", "float", MN, "First figure (SAR mn or %, see unit_note)."),
            ("value_b", "float", MN, "Second figure."),
            ("value_c", "float", MN, "Third figure (when three sources are compared)."),
            ("gap_pct", "float", "%", "Gap between the figures, % of the first."),
            ("unit_note", "text", "", "What value_a/b/c are."),
            ("sentence", "text", "", "The result in the credit voice (facts, numbers, dates)."),
            ("evidence_json", "json", "", "Document ids, fields and bank relations behind each figure."),
        ]),
    }
