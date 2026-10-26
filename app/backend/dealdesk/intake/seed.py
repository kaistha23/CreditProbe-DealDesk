"""R16 i: demo rows of the customer-file relations (fictional; one small new-to-bank file, not attached to a deal).

Hand-written so `python -m backend.dealdesk.data.build --check` never depends on OCR or on another session's files; the
real rows are written at run time by backend/dealdesk/intake/service.py when documents are uploaded.
"""
from __future__ import annotations

import json
from typing import Any

IID = "IN-SEED-0001"
NAME = "Rawdat Al Khair Trading Est."
CR = "4030998877"


def build(_rows: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, list[dict[str, Any]]]:
    nan = float("nan")
    docs = [
        ("D01", "cr_rawdat.docx", "word", "Word", "", 1, "commercial_registration", "Commercial Registration (CR)", 0.92, "company",
         "2024-02-11", "2027-02-10", "", "", "received", 9),
        ("D02", "audited_fs_fy2025.pdf", "pdf", "PDF text", "", 4, "audited_fs", "Audited financial statements (Qawaem)", 0.88, "FY2025",
         "2025-12-31", "", "", "", "received", 38),
        ("D03", "zakat_photo.jpg", "image", "photo (OCR)", "rapidocr", 1, "zakat_certificate", "Zakat certificate", 0.81, "company",
         "2025-04-30", "2026-04-30", "", "", "expired", 6),
    ]
    out: dict[str, list[dict[str, Any]]] = {
        "dd_intake_file": [{"intake_id": IID, "proposal_id": "", "customer_name": NAME, "cr_number": CR, "existing_customer": 0, "matched_cif": "",
                            "matched_proposal_id": "", "case_kind": "new_to_bank", "as_of": "2026-10-21", "documents_n": 3, "received_n": 2,
                            "missing_n": 21, "expired_n": 1, "flags_n": 1, "created_by": "seed", "created_at": "2026-10-21T16:00:00Z"}],
        "dd_intake_document": [{"doc_id": f"{IID}-{d[0]}", "intake_id": IID, "proposal_id": "", "file_name": d[1], "file_kind": d[2], "read_method": d[3],
                                "ocr_engine": d[4], "pages": d[5], "doc_type": d[6], "doc_label": d[7], "confidence": d[8], "subject": d[9],
                                "customer_name": NAME, "cr_number": CR, "issue_date": d[10], "expiry_date": d[11], "period_from": d[12], "period_to": d[13],
                                "status": d[14], "fields_n": d[15], "sha256": f"seed-{d[0].lower()}"} for d in docs],
        "dd_intake_field": [
            {"field_row_id": f"{IID}-D01:cr_number", "intake_id": IID, "proposal_id": "", "doc_id": f"{IID}-D01", "doc_type": "commercial_registration",
             "field": "cr_number", "label": "CR number", "value_text": CR, "value_num": nan, "value_mn": nan, "value_json": "", "line_no": 4, "raw_text": CR},
            {"field_row_id": f"{IID}-D01:owners", "intake_id": IID, "proposal_id": "", "doc_id": f"{IID}-D01", "doc_type": "commercial_registration",
             "field": "owners", "label": "Owners", "value_text": "", "value_num": nan, "value_mn": nan,
             "value_json": json.dumps([{"name": "Hamad Al Rawdan", "pct": 100.0}]), "line_no": 12, "raw_text": "1 rows"},
            {"field_row_id": f"{IID}-D02:revenue", "intake_id": IID, "proposal_id": "", "doc_id": f"{IID}-D02", "doc_type": "audited_fs",
             "field": "revenue", "label": "Revenue", "value_text": "41250000.0", "value_num": 41250000.0, "value_mn": 41.25, "value_json": "", "line_no": 14,
             "raw_text": "SAR 41,250,000"},
            {"field_row_id": f"{IID}-D03:expiry_date", "intake_id": IID, "proposal_id": "", "doc_id": f"{IID}-D03", "doc_type": "zakat_certificate",
             "field": "expiry_date", "label": "Valid until", "value_text": "2026-04-30", "value_num": nan, "value_mn": nan, "value_json": "", "line_no": 7,
             "raw_text": "30/04/2026"},
        ],
        "dd_intake_check": [
            {"check_id": f"{IID}:commercial_registration:company", "intake_id": IID, "proposal_id": "", "req_group": "company_legal",
             "doc_type": "commercial_registration", "requirement": "Commercial Registration (CR)", "subject": "company", "status": "received",
             "doc_ids": f"{IID}-D01", "reason": "valid until 10/02/2027", "valid_until": "2027-02-10", "rule_ref": "DR-01"},
            {"check_id": f"{IID}:zakat_certificate:company", "intake_id": IID, "proposal_id": "", "req_group": "company_legal",
             "doc_type": "zakat_certificate", "requirement": "Zakat certificate", "subject": "company", "status": "expired",
             "doc_ids": f"{IID}-D03", "reason": "expired on 30/04/2026", "valid_until": "2026-04-30", "rule_ref": ""},
            {"check_id": f"{IID}:audited_fs:fy2025", "intake_id": IID, "proposal_id": "", "req_group": "financials", "doc_type": "audited_fs",
             "requirement": "Audited financial statements FY2025", "subject": "FY2025", "status": "received", "doc_ids": f"{IID}-D02",
             "reason": "", "valid_until": "", "rule_ref": "DR-03"},
            {"check_id": f"{IID}:bank_statement:12monthsallaccounts", "intake_id": IID, "proposal_id": "", "req_group": "bank_statements",
             "doc_type": "bank_statement", "requirement": "Bank statement, 12 months", "subject": "12 months, all accounts", "status": "missing",
             "doc_ids": "", "reason": "no bank statement uploaded", "valid_until": "", "rule_ref": "DR-26"},
        ],
        "dd_intake_reconciliation": [
            {"recon_id": f"{IID}:identity_cr", "intake_id": IID, "proposal_id": "", "topic": "identity", "title": "Same company on every document",
             "status": "agrees", "severity": 0, "value_a": 3.0, "value_b": nan, "value_c": nan, "gap_pct": nan, "unit_note": "documents",
             "sentence": f"All 3 documents that print a CR number carry {CR} ({NAME}).", "evidence_json": "[]"},
            {"recon_id": f"{IID}:revenue_sources", "intake_id": IID, "proposal_id": "", "topic": "revenue",
             "title": "Revenue: audited accounts vs VAT filings vs bank-statement credits", "status": "flag", "severity": 2, "value_a": 41.25,
             "value_b": nan, "value_c": nan, "gap_pct": nan, "unit_note": "SAR mn",
             "sentence": "Revenue for the last 12 months is SAR 41.2m (FY2025 audited); VAT filings not provided; bank statements not provided.",
             "evidence_json": json.dumps([{"doc_id": f"{IID}-D02", "field": "revenue", "value": 41250000.0}])},
        ],
    }
    return out
