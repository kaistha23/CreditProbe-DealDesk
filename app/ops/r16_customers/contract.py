"""Write data/dealdesk/demo_customers/CONTRACT.md from the registries (python -m ops.r16_customers.contract)."""
from __future__ import annotations

import pathlib

from ops.r16_customers.doctypes import DOC_TYPES
from ops.r16_customers.ids import AS_OF, BANK, CUSTOMERS

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "dealdesk" / "demo_customers" / "CONTRACT.md"

HEAD = f"""# R16 demo customers: the contract (session d)

**Generated** by `python -m ops.r16_customers.contract` from `ops/r16_customers/doctypes.py` and `ids.py`; do not edit by hand.
Everything here is **fictional** (companies, people, banks other than the demo bank, auditors, employers, numbers). The demo
bank is **{BANK}** ("the Bank"). Demo day: **{AS_OF}**. Currency SAR, fiscal year = calendar year; audited FY2024 and FY2025,
in-house (management accounts) Jan–Sep 2026, bank statements Oct 2025 – Sep 2026, VAT filings for the same 12 months.

## 1. The customers

| key | folder | proposal_id | CIF (bank) | group_id | Customer | CR number | VAT number | City | Case | Demo part |
|---|---|---|---|---|---|---|---|---|---|---|
"""

LAYOUT = """
`proposal_id` is the id a deal for this customer carries in Data Domains (the seeded relationship file for C1 and C2; the
id session i/b/c should give the deal they create from the upload, so the bank data joins). `CIF` is the Borrower 360 id
(corporate book, C1 and C2 only: new-to-bank customers have none). **Match an upload to an existing customer by CR number**
(printed on almost every document) → `cr_number` in `customers.json` → `cif` / `proposal_id`.

## 2. Folder layout (`data/dealdesk/demo_customers/`)

```
CONTRACT.md                 this file
ANSWER_KEY.md               the twist of each case, where it is found, what the credit comments must say
customers.json              one object per customer: ids above + the headline numbers (SAR) + the ask
<folder>/                   one per customer, e.g. c2_sawaed_al_bina/
  ASK.md                    the one-line ask and the RM notes Anne types (Part A) / what she uploads (Part B)
  manifest.json             every document: file names, doc_type, subject, dates, and the printed fields (ground truth)
  facts.json                every number the documents print, by document (the reconciliation test reads it)
  word/NN_<doc_type>[__<subject>].docx
  pdf/NN_<doc_type>[__<subject>].pdf          same content as the Word file, page for page in spirit
  images/NN_<doc_type>[__<subject>]_p<k>.jpg  photo-style shots of key pages (rotation, shadow, scanner noise)
  business_request/         C2 only (Part B input): business_request.docx / .pdf / business_request_p<k>.jpg
  reference/                the reference bank-form proposal (business request + credit comments + recommendation):
                            reference_proposal.docx / .pdf  (the answer, never uploaded in the demo)
  bank/                     C1, C2: the bank-side rows seeded into Data Domains (JSON copy, for reading)
bank_b360/                  Borrower 360 overlay parquet files for C1, C2 (see §6)
```

File naming: `NN` is a two-digit order (checklist order), `<doc_type>` is a code from §4, `<subject>` is a slug for
per-owner / per-bank / per-project / per-certificate / per-period documents (e.g. `03_national_id__fahad_al_naseem`,
`12_audited_fs__fy2025`, `14_bank_statement__shb_current`). The file name is a hint only: **classify from content**
(every document prints its title and a "Key details" block of `Label: value` lines with the labels in §4).

## 3. `manifest.json` (per customer)

```json
{"customer_key": "c2", "proposal_id": "R16-C2", "cr_number": "...", "as_of": "2026-10-21",
 "documents": [{"doc_id": "C2-07", "doc_type": "audited_fs", "subject": "fy2025", "title": "...",
                "issuer": "...", "issue_date": "2026-04-28", "expiry_date": null, "period_from": "2025-01-01",
                "period_to": "2025-12-31", "status_expected": "received|expired|missing",
                "files": {"docx": "word/...", "pdf": "pdf/...", "images": ["images/..._p1.jpg"]},
                "fields": {"revenue": 468210000, "...": "..."}}],
 "missing": [{"doc_type": "personal_net_worth", "subject": "...", "why": "not provided by the customer"}]}
```

`status_expected` is what the checklist should show on demo day: `received`, `expired` (validity rule in §4 fails on
{as_of}) or `missing` (listed under `missing`, no file). Amount fields are SAR units (not millions) in `fields`; Data
Domains rows are SAR million (`_mn`) as everywhere in Deal Desk.

## 4. Document types and printed fields

Validity: `expiry_date` = expired when the printed expiry is before demo day; `months:N` = stale when issued more than
N months before demo day; `none` = never expires. `per` = one document per company / owner / guarantor / bank /
account / project / certificate / period / collateral. `required_for` = which cases need it (all, contractor, secured).
List fields print as a table under the label; their sub-fields are the column keys.

| code | label | group | per | validity | required for | printed fields (field_name = "Label", type) |
|---|---|---|---|---|---|---|
"""

TAIL = """
Printed formats: dates `DD/MM/YYYY`; amounts `SAR 12,345,678` (or a bare `12,345,678` inside SAR tables); percentages
`12.3%`. Everything is printed in English (no Arabic script). **Financial statements** (`audited_fs`, `inhouse_fs`) print
only the header fields in "Key details"; their amounts are in the statement tables, one row per field, the row label being
the printed label above (e.g. row "Trade receivables, net"). Bank statements print a monthly summary table and a
transactions table (columns Date, Description, Debit, Credit, Balance). Every page carries the footer "Fictional
document (CreditProbe R16)…" and the issuer in the page header band.

`manifest.json` also carries `business_request` (C2 only: docx, pdf, images, and its `fields` per the `business_request`
type) and `reference` (the reference proposal files, every customer).

## 5. Reconciliation (what the numbers obey; `tests/v5/demo_customers/test_r16_reconcile.py`)

- Balance sheets balance (assets = liabilities + equity) for every audited and in-house statement; P&L arithmetic holds.
- Revenue ≈ VAT standard-rated sales (same 12 months, within ±6%) and statement credits / 1.15 track revenue within a
  normal band (collections ratio 0.85–1.10) **except where the twist says otherwise** (C1: credits grow 9% vs revenue 38%).
- Statement monthly credits sum to the statement total; opening + credits − debits = closing.
- Receivables ageing total = trade receivables in the latest statements; the top-customer shares sum ≤ 100%.
- SIMAH totals = sum of the facility rows; other-bank statement = offer-letter limits; guarantor net worth = assets − liabilities.
- Payment certificates: net = gross this certificate − retention − advance recovery; cumulative retention = retention % × cumulative work.
- Data Domains rows for C1/C2 (accounts, conduct, facilities, group) agree with the documents (same limits, balances, owners).

## 6. Bank-side data for C1 and C2 (Data Domains, seeded by `ops/r16_seed_customers.py`)

Published through the R12 store (`backend.dealdesk.data.store.publish`, actor `R16-d:seed`) as a later version of
the registered relations, keyed by `proposal_id` R16-C1 / R16-C2 and `obligor_id` = CIF:

| Relation | What C1 / C2 rows hold |
|---|---|
| `dd_customer_account` (new, R16) | every current and deposit account with the Bank: number, IBAN, type, opened, balance on 30/09/2026, 12-month average balance, credits and debits |
| `dd_account_conduct` | 24 months (Oct 2024 – Sep 2026) of credit/debit turnover, average balance, limits, utilisation, past dues, returned cheques |
| `dd_returned_cheque` | each returned cheque (C2's connected party carries the weak record) |
| `dd_facility_limit` | existing limits with outstanding (proposed = existing; the ask lives in ASK.md and the uploads) |
| `dd_security`, `dd_tnc`, `dd_reference` | security held, existing conditions with status, limit history with committee references |
| `dd_group_exposure` | the group's exposure with the Bank per entity |
| `b360_entity`, `b360_edge`, `b360_shareholder`, `b360_board` | group graph: parent, sister companies, connected parties, owners |
| `bureau_entity_report`, `bureau_cbrbr`, `other_bank_facility` | bureau and other banks as the Bank holds them (consistent with the SIMAH documents) |
| `dd_financials_detail` | FY2024, FY2025 audited and 9M2026 in-house, as in the documents |

Borrower 360 shows C1 and C2 (with their group, related parties, facilities, collateral, covenants, ratings history,
EWS, bureau and open banking) from the overlay parquet files in `bank_b360/` (same columns as the corporate book; read by
`backend/b360/store.py` beside the book, never written into the Cockpit lake, so Cockpit, What-If and EWS numbers do not move).
They are found by Borrower 360 search (and opened from Deal Desk); they are kept out of Borrower 360's book list and totals.

## 7. API (Deal Desk service, `backend/dealdesk/customer_packs.py`)

| Call | Returns |
|---|---|
| `GET /api/v1/dealdesk/customer-packs` | the four packs: ids, case, the ask and RM notes (from ASK.md), counts |
| `GET /api/v1/dealdesk/customer-packs/by-cr/{cr_number}` | `{found, existing, key, cif, proposal_id}`: **use it to tell an existing customer from a new one after reading the CR number** |
| `GET /api/v1/dealdesk/customer-packs/{key}` | the checklist: every document with `status` received / expired / missing, dates and file paths |
| `GET /api/v1/dealdesk/customer-packs/{key}/file?path=` | one file (Word, PDF, photo) |
| `GET /api/v1/dealdesk/customer-packs/{key}/bank` | the Bank's file (accounts, limits, conduct, group, returned cheques), every row with its `trace` |

UI: Deal Desk → proposal list → "Customer packs: documents to upload and what to type" (`/deal-desk/customer-packs`).
"""


def _fields(d) -> str:
    out = []
    for name, label, typ in d.fields:
        out.append(f"`{name}` = \"{label}\" ({typ})")
    return "; ".join(out)


def main() -> None:
    lines = [HEAD]
    for c in CUSTOMERS:
        lines.append(f"| {c['key']} | `{c['folder']}` | {c['proposal_id']} | {c['cif'] or '—'} | {c['group_id'] or '—'} | {c['name']} | "
                     f"{c['cr_number']} | {c['vat_number']} | {c['city']} | {c['case_label']} | {c['part']} |\n")
    lines.append(LAYOUT.replace("{as_of}", AS_OF))
    for d in DOC_TYPES:
        lines.append(f"| `{d.code}` | {d.label} | {d.group} | {d.per} | {d.validity} | {', '.join(d.required_for) or '—'} | {_fields(d)} |\n")
    lines.append(TAIL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(lines))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
