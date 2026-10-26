# R16 demo customers: the contract (session d)

**Generated** by `python -m ops.r16_customers.contract` from `ops/r16_customers/doctypes.py` and `ids.py`; do not edit by hand.
Everything here is **fictional** (companies, people, banks other than the demo bank, auditors, employers, numbers). The demo
bank is **Sandstone Harbour Bank** ("the Bank"). Demo day: **2026-10-21**. Currency SAR, fiscal year = calendar year; audited FY2024 and FY2025,
in-house (management accounts) Jan–Sep 2026, bank statements Oct 2025 – Sep 2026, VAT filings for the same 12 months.

## 1. The customers

| key | folder | proposal_id | CIF (bank) | group_id | Customer | CR number | VAT number | City | Case | Demo part |
|---|---|---|---|---|---|---|---|---|---|---|
| c1 | `c1_dar_al_naseem` | R16-C1 | CB09001 | CG9001 | Dar Al Naseem Medical Supplies Co. | 1010384527 | 300384527100003 | Riyadh | Existing customer, renewal + increase | A |
| c2 | `c2_sawaed_al_bina` | R16-C2 | CB09002 | CG9002 | Sawaed Al Bina Contracting Co. | 2050117342 | 302050117300003 | Dammam | Existing customer, new project limit | B |
| c3 | `c3_nukhba_polymer` | R16-C3 | — | — | Nukhba Polymer Industries Co. | 2055104486 | 302055104400003 | Jubail | New-to-bank manufacturer, takeover of another bank's facilities | A (optional) |
| c4 | `c4_sanad_facility` | R16-C4 | — | — | Sanad Smart Facility Services Co. | 1010712290 | 301010712200003 | Riyadh | New-to-bank SME, thin file | A (optional) |

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
2026-10-21) or `missing` (listed under `missing`, no file). Amount fields are SAR units (not millions) in `fields`; Data
Domains rows are SAR million (`_mn`) as everywhere in Deal Desk.

## 4. Document types and printed fields

Validity: `expiry_date` = expired when the printed expiry is before demo day; `months:N` = stale when issued more than
N months before demo day; `none` = never expires. `per` = one document per company / owner / guarantor / bank /
account / project / certificate / period / collateral. `required_for` = which cases need it (all, contractor, secured).
List fields print as a table under the label; their sub-fields are the column keys.

| code | label | group | per | validity | required for | printed fields (field_name = "Label", type) |
|---|---|---|---|---|---|---|
| `national_id` | National ID of owner / signatory | kyc | owner | expiry_date | all | `full_name` = "Name" (text); `id_number` = "ID number" (text); `nationality` = "Nationality" (text); `date_of_birth` = "Date of birth" (date); `issue_date` = "Issue date" (date); `expiry_date` = "Expiry date" (date) |
| `articles_of_association` | Articles of Association | company_legal | company | none | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `legal_form` = "Legal form" (text); `date_of_incorporation` = "Date of incorporation" (date); `share_capital` = "Share capital" (sar); `amendment_date` = "Last amendment date" (date); `shareholders` = "Shareholders" (list:name,id_number,nationality,shares,pct); `managers` = "Managers / authorised signatories" (list:name,role,powers) |
| `commercial_registration` | Commercial Registration (CR) | company_legal | company | expiry_date | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `legal_form` = "Legal form" (text); `city` = "City" (text); `activity` = "Activity" (text); `issue_date` = "Issue date" (date); `expiry_date` = "Expiry date" (date); `share_capital` = "Capital" (sar); `owners` = "Owners" (list:name,pct); `managers` = "Managers" (list:name,role) |
| `vat_certificate` | VAT registration certificate | company_legal | company | none | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `vat_number` = "VAT registration number" (text); `effective_date` = "Effective registration date" (date); `filing_frequency` = "Filing frequency" (text); `issue_date` = "Issue date" (date) |
| `zakat_certificate` | Zakat certificate | company_legal | company | expiry_date | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `certificate_number` = "Certificate number" (text); `fiscal_year` = "For the year ended" (date); `issue_date` = "Issue date" (date); `expiry_date` = "Valid until" (date) |
| `nitaqat_certificate` | Nitaqat (Saudisation) certificate | company_legal | company | expiry_date | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `establishment_number` = "Establishment number" (text); `nitaqat_band` = "Nitaqat band" (text); `saudisation_pct` = "Saudisation rate" (pct); `band_threshold_pct` = "Minimum for this band" (pct); `total_staff` = "Total employees" (int); `saudi_staff` = "Saudi employees" (int); `issue_date` = "Issue date" (date); `expiry_date` = "Valid until" (date) |
| `vat_returns` | VAT filings, last 12 months | company_legal | company | none | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `vat_number` = "VAT registration number" (text); `period_from` = "Period from" (date); `period_to` = "Period to" (date); `filing_frequency` = "Filing frequency" (text); `total_taxable_sales` = "Total standard-rated sales (12 months)" (sar); `total_output_vat` = "Total output VAT" (sar); `returns` = "Returns filed" (list:period,taxable_sales,zero_rated_sales,output_vat,input_vat,net_vat_due,filed_on) |
| `simah_company` | SIMAH company credit report | credit_bureau | company | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `report_date` = "Report date" (date); `report_number` = "Report number" (text); `score` = "Score" (int); `total_limits` = "Total limits" (sar); `total_outstanding` = "Total outstanding" (sar); `total_overdue` = "Total overdue" (sar); `lenders_count` = "Number of lenders" (int); `defaults_count` = "Defaults" (int); `facilities` = "Credit facilities" (list:lender,product,limit,outstanding,overdue,status,opened,remark); `enquiries_6m` = "Enquiries (last 6 months)" (int) |
| `simah_consumer` | SIMAH consumer report (owner / guarantor) | credit_bureau | owner | months:3 | all | `full_name` = "Name" (text); `id_number` = "ID number" (text); `report_date` = "Report date" (date); `report_number` = "Report number" (text); `score` = "Score" (int); `total_outstanding` = "Total outstanding" (sar); `total_overdue` = "Total overdue" (sar); `worst_status_24m` = "Worst status (24 months)" (text); `facilities` = "Credit facilities" (list:lender,product,limit,outstanding,overdue,status,remark); `guarantees` = "Guarantees given" (list:beneficiary,lender,amount,status) |
| `simah_consent` | SIMAH consent form | extras | company | months:12 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `signatory` = "Signed by" (text); `signed_on` = "Signed on" (date) |
| `audited_fs` | Audited financial statements (Qawaem) | financials | period | none | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `fiscal_year` = "Financial year ended" (date); `auditor` = "Auditor" (text); `opinion` = "Audit opinion" (text); `qawaem_reference` = "Qawaem filing reference" (text); `revenue` = "Revenue" (sar); `cost_of_sales` = "Cost of revenue" (sar); `gross_profit` = "Gross profit" (sar); `operating_expenses` = "Operating expenses" (sar); `operating_profit` = "Operating profit" (sar); `finance_cost` = "Finance cost" (sar); `zakat` = "Zakat" (sar); `net_profit` = "Net profit" (sar); `depreciation` = "Depreciation and amortisation" (sar); `cash` = "Cash and bank balances" (sar); `trade_receivables` = "Trade receivables, net" (sar); `retention_receivables` = "Retention receivables" (sar); `contract_assets` = "Contract assets" (sar); `inventory` = "Inventories" (sar); `due_from_related` = "Due from related parties" (sar); `other_current_assets` = "Prepayments and other current assets" (sar); `current_assets` = "Total current assets" (sar); `ppe` = "Property, plant and equipment" (sar); `other_noncurrent_assets` = "Other non-current assets" (sar); `total_assets` = "Total assets" (sar); `short_term_borrowings` = "Short-term borrowings" (sar); `trade_payables` = "Trade payables" (sar); `due_to_related` = "Due to related parties" (sar); `other_current_liabilities` = "Accruals and other current liabilities" (sar); `current_portion_ltd` = "Current portion of long-term borrowings" (sar); `current_liabilities` = "Total current liabilities" (sar); `long_term_borrowings` = "Long-term borrowings" (sar); `end_of_service` = "Employees' end-of-service benefits" (sar); `total_liabilities` = "Total liabilities" (sar); `share_capital` = "Share capital" (sar); `statutory_reserve` = "Statutory reserve" (sar); `retained_earnings` = "Retained earnings" (sar); `total_equity` = "Total equity" (sar); `operating_cash_flow` = "Net cash from operating activities" (sar); `related_party_sales` = "Sales to related parties (note)" (sar) |
| `inhouse_fs` | In-house financial statements, current year | financials | period | months:6 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `period_from` = "Period from" (date); `period_to` = "Period to" (date); `prepared_by` = "Prepared by" (text); `revenue` = "Revenue" (sar); `cost_of_sales` = "Cost of revenue" (sar); `gross_profit` = "Gross profit" (sar); `operating_expenses` = "Operating expenses" (sar); `operating_profit` = "Operating profit" (sar); `finance_cost` = "Finance cost" (sar); `net_profit` = "Net profit" (sar); `cash` = "Cash and bank balances" (sar); `trade_receivables` = "Trade receivables, net" (sar); `inventory` = "Inventories" (sar); `current_assets` = "Total current assets" (sar); `total_assets` = "Total assets" (sar); `short_term_borrowings` = "Short-term borrowings" (sar); `current_liabilities` = "Total current liabilities" (sar); `long_term_borrowings` = "Long-term borrowings" (sar); `total_liabilities` = "Total liabilities" (sar); `total_equity` = "Total equity" (sar) |
| `bank_statement` | Bank statement, 12 months | bank_statements | account | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `bank_name` = "Bank" (text); `account_number` = "Account number" (text); `iban` = "IBAN" (text); `account_type` = "Account type" (text); `period_from` = "Period from" (date); `period_to` = "Period to" (date); `opening_balance` = "Opening balance" (sar); `total_credits` = "Total credits" (sar); `total_debits` = "Total debits" (sar); `closing_balance` = "Closing balance" (sar); `returned_cheques` = "Returned cheques" (int); `monthly` = "Monthly summary" (list:month,credits,debits,closing_balance,avg_balance,returned_cheques); `transactions` = "Transactions" (list:date,description,debit,credit,balance) |
| `facility_request_letter` | Facility request letter (signed) | extras | company | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `letter_date` = "Date" (date); `addressed_to` = "Addressed to" (text); `requested_total` = "Total requested" (sar); `facilities` = "Facilities requested" (list:facility,amount,purpose); `signatory` = "Signed by" (text); `signatory_role` = "Capacity" (text) |
| `board_resolution` | Board / partners' resolution to borrow | extras | company | months:12 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `resolution_date` = "Resolution date" (date); `resolution_number` = "Resolution number" (text); `authorised_amount` = "Borrowing authorised up to" (sar); `authorised_persons` = "Authorised to sign" (text) |
| `authorised_signatories` | Authorised signatory list | extras | company | months:12 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `as_of` = "As of" (date); `signatories` = "Signatories" (list:name,id_number,role,limit,mode) |
| `personal_net_worth` | Personal net-worth statement of guarantor | extras | guarantor | months:12 | all | `full_name` = "Guarantor" (text); `id_number` = "ID number" (text); `statement_date` = "Statement date" (date); `total_assets` = "Total assets" (sar); `total_liabilities` = "Total liabilities" (sar); `net_worth` = "Net worth" (sar); `assets` = "Assets" (list:asset,description,value); `liabilities` = "Liabilities" (list:liability,description,value) |
| `other_bank_offer_letter` | Other bank's facility offer letter | extras | bank | none | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `bank_name` = "Bank" (text); `letter_date` = "Date" (date); `letter_reference` = "Reference" (text); `total_limits` = "Total facilities" (sar); `expiry_date` = "Facilities valid until" (date); `facilities` = "Facilities" (list:facility,limit,pricing,tenor); `security` = "Security" (text) |
| `other_bank_statement` | Other bank's latest facility statement | extras | bank | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `bank_name` = "Bank" (text); `statement_date` = "Statement date" (date); `total_limits` = "Total limits" (sar); `total_outstanding` = "Total outstanding" (sar); `facilities` = "Facilities" (list:facility,limit,outstanding,overdue,maturity) |
| `receivables_ageing` | Receivables ageing | extras | company | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `as_of` = "As of" (date); `total` = "Total receivables" (sar); `bucket_0_90` = "0-90 days" (sar); `bucket_91_180` = "91-180 days" (sar); `bucket_181_365` = "181-365 days" (sar); `bucket_over_365` = "Over 365 days" (sar); `by_customer` = "By customer" (list:customer,b0_90,b91_180,b181_365,over_365,total) |
| `payables_ageing` | Payables ageing | extras | company | months:3 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `as_of` = "As of" (date); `total` = "Total payables" (sar); `bucket_0_90` = "0-90 days" (sar); `bucket_91_180` = "91-180 days" (sar); `bucket_over_180` = "Over 180 days" (sar); `by_supplier` = "By supplier" (list:supplier,b0_90,b91_180,over_180,total) |
| `top_customers_suppliers` | Top customers and suppliers | extras | company | months:12 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `year` = "Year" (int); `customers` = "Top customers" (list:name,relationship,sales,share_pct,terms); `suppliers` = "Top suppliers" (list:name,country,purchases,share_pct,terms) |
| `project_list` | Project list (contractors) | extras | company | months:3 | contractor | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `as_of` = "As of" (date); `projects` = "Projects" (list:project_id,project,employer,contract_value,start,planned_completion,work_done_pct,billed,received,retention_held,status) |
| `project_contract` | Project contract (extract) | extras | project | none | contractor | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `project_id` = "Project" (text); `employer` = "Employer" (text); `consultant` = "Consultant" (text); `contract_date` = "Contract date" (date); `contract_value` = "Contract value" (sar); `advance_pct` = "Advance payment" (pct); `retention_pct` = "Retention" (pct); `payment_terms_days` = "Payment of certified amounts within (days)" (int); `start_date` = "Commencement date" (date); `completion_date` = "Completion date" (date); `performance_bond_pct` = "Performance bond" (pct) |
| `payment_certificate` | Interim payment certificate | extras | certificate | none | contractor | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `project_id` = "Project" (text); `certificate_number` = "Certificate number" (text); `period_to` = "Work up to" (date); `certified_on` = "Certified on" (date); `gross_work_done` = "Cumulative work done" (sar); `this_certificate_gross` = "Gross this certificate" (sar); `retention_this` = "Retention deducted" (sar); `advance_recovery` = "Advance recovery" (sar); `net_payable` = "Net amount payable" (sar); `cumulative_retention` = "Cumulative retention" (sar); `due_date` = "Due date" (date) |
| `valuation_report` | Collateral valuation report | extras | collateral | months:12 | secured | `property` = "Property" (text); `owner` = "Registered owner" (text); `deed_number` = "Title deed number" (text); `valuer` = "Valuer" (text); `valuation_date` = "Valuation date" (date); `market_value` = "Market value" (sar); `forced_sale_value` = "Forced-sale value" (sar) |
| `title_deed` | Title deed | extras | collateral | none | secured | `deed_number` = "Deed number" (text); `owner` = "Owner" (text); `property` = "Property" (text); `area_sqm` = "Area (sq m)" (int); `deed_date` = "Deed date" (date); `encumbrance` = "Encumbrance" (text) |
| `insurance_policy` | Insurance policy (collateral) | extras | collateral | expiry_date | secured | `policy_number` = "Policy number" (text); `insured` = "Insured" (text); `insurer` = "Insurer" (text); `property` = "Property insured" (text); `sum_insured` = "Sum insured" (sar); `loss_payee` = "Loss payee" (text); `issue_date` = "Period from" (date); `expiry_date` = "Period to" (date) |
| `site_visit_report` | Site-visit report (RM) | extras | company | months:6 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `visit_date` = "Visit date" (date); `visited_by` = "Visited by" (text); `met_with` = "Met with" (text); `premises` = "Premises" (text); `staff_seen` = "Staff observed" (int); `observations` = "Observations" (text) |
| `aml_kyc_questionnaire` | AML/KYC questionnaire | extras | company | months:12 | all | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `completed_on` = "Completed on" (date); `ubos` = "Ultimate beneficial owners" (list:name,pct,pep); `pep_flag` = "Politically exposed person" (text); `countries` = "Countries of trade" (text); `cash_intensive` = "Cash-intensive business" (text); `risk_rating` = "Customer risk rating" (text) |
| `business_request` | Business request (bank-form 'Action requested') | proposal | company | none | — | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `cif` = "CIF" (text); `request_date` = "Date" (date); `rm` = "Relationship manager" (text); `action_requested` = "Action requested" (text); `total_existing` = "Total existing limits" (sar); `total_proposed` = "Total proposed limits" (sar); `facilities` = "Facilities" (list:limit,existing,outstanding,proposed,cash_margin_pct,pricing,tenor); `security` = "Security and support" (list:item); `conditions` = "Terms and conditions" (list:item) |
| `reference_proposal` | Reference bank-form proposal (answer) | proposal | company | none | — | `customer_name` = "Customer name" (text); `cr_number` = "CR number" (text); `recommendation` = "Credit recommendation" (text) |

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
