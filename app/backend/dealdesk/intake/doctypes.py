"""R16 i: copy of session d's document-type registry (ops/r16_customers/doctypes.py), so the engine never imports ops/.

`tests/v5/intake/test_r16_intake.py::test_doctypes_match_d` fails when the two drift; refresh with
`cp ops/r16_customers/doctypes.py` and re-apply this header.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# requirement groups (Anne's list in PLAN_R16 §Required documents)
KYC, LEGAL, BUREAU, FIN, STMT, EXTRA = "kyc", "company_legal", "credit_bureau", "financials", "bank_statements", "extras"


@dataclass(frozen=True)
class DocType:
    code: str
    label: str
    group: str
    per: str                      # company | owner | guarantor | bank | account | project | certificate | period | collateral
    validity: str                 # how expiry is judged: "expiry_date", "months:N" (age from issue date), "none"
    fields: tuple[tuple[str, str, str], ...]   # (field_name, printed label, type)
    required_for: tuple[str, ...] = ("all",)   # all | contractor | existing | takeover | secured
    keywords: tuple[str, ...] = field(default_factory=tuple)   # words printed in the title / header (classifier hints)


def F(*items: tuple[str, str, str]) -> tuple[tuple[str, str, str], ...]:
    return tuple(items)


COMMON = (("customer_name", "Customer name", "text"), ("cr_number", "CR number", "text"))

DOC_TYPES: list[DocType] = [
    # ---------------------------------------------------------------- KYC
    DocType("national_id", "National ID of owner / signatory", KYC, "owner", "expiry_date", F(
        ("full_name", "Name", "text"), ("id_number", "ID number", "text"), ("nationality", "Nationality", "text"),
        ("date_of_birth", "Date of birth", "date"), ("issue_date", "Issue date", "date"), ("expiry_date", "Expiry date", "date")),
        keywords=("NATIONAL IDENTITY CARD", "ID number")),
    # ---------------------------------------------------------------- company legal
    DocType("articles_of_association", "Articles of Association", LEGAL, "company", "none", F(
        *COMMON, ("legal_form", "Legal form", "text"), ("date_of_incorporation", "Date of incorporation", "date"),
        ("share_capital", "Share capital", "sar"), ("amendment_date", "Last amendment date", "date"),
        ("shareholders", "Shareholders", "list:name,id_number,nationality,shares,pct"),
        ("managers", "Managers / authorised signatories", "list:name,role,powers")),
        keywords=("ARTICLES OF ASSOCIATION", "Shareholders")),
    DocType("commercial_registration", "Commercial Registration (CR)", LEGAL, "company", "expiry_date", F(
        *COMMON, ("legal_form", "Legal form", "text"), ("city", "City", "text"), ("activity", "Activity", "text"),
        ("issue_date", "Issue date", "date"), ("expiry_date", "Expiry date", "date"), ("share_capital", "Capital", "sar"),
        ("owners", "Owners", "list:name,pct"), ("managers", "Managers", "list:name,role")),
        keywords=("COMMERCIAL REGISTRATION", "CR number")),
    DocType("vat_certificate", "VAT registration certificate", LEGAL, "company", "none", F(
        *COMMON, ("vat_number", "VAT registration number", "text"), ("effective_date", "Effective registration date", "date"),
        ("filing_frequency", "Filing frequency", "text"), ("issue_date", "Issue date", "date")),
        keywords=("VAT REGISTRATION CERTIFICATE", "Tax Identification")),
    DocType("zakat_certificate", "Zakat certificate", LEGAL, "company", "expiry_date", F(
        *COMMON, ("certificate_number", "Certificate number", "text"), ("fiscal_year", "For the year ended", "date"),
        ("issue_date", "Issue date", "date"), ("expiry_date", "Valid until", "date")),
        keywords=("ZAKAT CERTIFICATE",)),
    DocType("nitaqat_certificate", "Nitaqat (Saudisation) certificate", LEGAL, "company", "expiry_date", F(
        *COMMON, ("establishment_number", "Establishment number", "text"), ("nitaqat_band", "Nitaqat band", "text"),
        ("saudisation_pct", "Saudisation rate", "pct"), ("band_threshold_pct", "Minimum for this band", "pct"),
        ("total_staff", "Total employees", "int"), ("saudi_staff", "Saudi employees", "int"),
        ("issue_date", "Issue date", "date"), ("expiry_date", "Valid until", "date")),
        keywords=("NITAQAT", "Saudisation")),
    DocType("vat_returns", "VAT filings, last 12 months", LEGAL, "company", "none", F(
        *COMMON, ("vat_number", "VAT registration number", "text"), ("period_from", "Period from", "date"),
        ("period_to", "Period to", "date"), ("filing_frequency", "Filing frequency", "text"),
        ("total_taxable_sales", "Total standard-rated sales (12 months)", "sar"), ("total_output_vat", "Total output VAT", "sar"),
        ("returns", "Returns filed", "list:period,taxable_sales,zero_rated_sales,output_vat,input_vat,net_vat_due,filed_on")),
        keywords=("VAT RETURN", "Output VAT")),
    # ---------------------------------------------------------------- credit bureau
    DocType("simah_company", "SIMAH company credit report", BUREAU, "company", "months:3", F(
        *COMMON, ("report_date", "Report date", "date"), ("report_number", "Report number", "text"), ("score", "Score", "int"),
        ("total_limits", "Total limits", "sar"), ("total_outstanding", "Total outstanding", "sar"), ("total_overdue", "Total overdue", "sar"),
        ("lenders_count", "Number of lenders", "int"), ("defaults_count", "Defaults", "int"),
        ("facilities", "Credit facilities", "list:lender,product,limit,outstanding,overdue,status,opened,remark"),
        ("enquiries_6m", "Enquiries (last 6 months)", "int")),
        keywords=("SIMAH", "COMMERCIAL CREDIT REPORT")),
    DocType("simah_consumer", "SIMAH consumer report (owner / guarantor)", BUREAU, "owner", "months:3", F(
        ("full_name", "Name", "text"), ("id_number", "ID number", "text"), ("report_date", "Report date", "date"),
        ("report_number", "Report number", "text"), ("score", "Score", "int"), ("total_outstanding", "Total outstanding", "sar"),
        ("total_overdue", "Total overdue", "sar"), ("worst_status_24m", "Worst status (24 months)", "text"),
        ("facilities", "Credit facilities", "list:lender,product,limit,outstanding,overdue,status,remark"),
        ("guarantees", "Guarantees given", "list:beneficiary,lender,amount,status")),
        keywords=("SIMAH", "CONSUMER CREDIT REPORT")),
    DocType("simah_consent", "SIMAH consent form", EXTRA, "company", "months:12", F(
        *COMMON, ("signatory", "Signed by", "text"), ("signed_on", "Signed on", "date")),
        keywords=("CONSENT", "SIMAH")),
    # ---------------------------------------------------------------- financials
    DocType("audited_fs", "Audited financial statements (Qawaem)", FIN, "period", "none", F(
        *COMMON, ("fiscal_year", "Financial year ended", "date"), ("auditor", "Auditor", "text"), ("opinion", "Audit opinion", "text"),
        ("qawaem_reference", "Qawaem filing reference", "text"),
        ("revenue", "Revenue", "sar"), ("cost_of_sales", "Cost of revenue", "sar"), ("gross_profit", "Gross profit", "sar"),
        ("operating_expenses", "Operating expenses", "sar"), ("operating_profit", "Operating profit", "sar"),
        ("finance_cost", "Finance cost", "sar"), ("zakat", "Zakat", "sar"), ("net_profit", "Net profit", "sar"),
        ("depreciation", "Depreciation and amortisation", "sar"),
        ("cash", "Cash and bank balances", "sar"), ("trade_receivables", "Trade receivables, net", "sar"),
        ("retention_receivables", "Retention receivables", "sar"), ("contract_assets", "Contract assets", "sar"),
        ("inventory", "Inventories", "sar"), ("due_from_related", "Due from related parties", "sar"),
        ("other_current_assets", "Prepayments and other current assets", "sar"), ("current_assets", "Total current assets", "sar"),
        ("ppe", "Property, plant and equipment", "sar"), ("other_noncurrent_assets", "Other non-current assets", "sar"),
        ("total_assets", "Total assets", "sar"),
        ("short_term_borrowings", "Short-term borrowings", "sar"), ("trade_payables", "Trade payables", "sar"),
        ("due_to_related", "Due to related parties", "sar"), ("other_current_liabilities", "Accruals and other current liabilities", "sar"),
        ("current_portion_ltd", "Current portion of long-term borrowings", "sar"), ("current_liabilities", "Total current liabilities", "sar"),
        ("long_term_borrowings", "Long-term borrowings", "sar"), ("end_of_service", "Employees' end-of-service benefits", "sar"),
        ("total_liabilities", "Total liabilities", "sar"),
        ("share_capital", "Share capital", "sar"), ("statutory_reserve", "Statutory reserve", "sar"),
        ("retained_earnings", "Retained earnings", "sar"), ("total_equity", "Total equity", "sar"),
        ("operating_cash_flow", "Net cash from operating activities", "sar"),
        ("related_party_sales", "Sales to related parties (note)", "sar")),
        keywords=("INDEPENDENT AUDITOR'S REPORT", "STATEMENT OF FINANCIAL POSITION")),
    DocType("inhouse_fs", "In-house financial statements, current year", FIN, "period", "months:6", F(
        *COMMON, ("period_from", "Period from", "date"), ("period_to", "Period to", "date"), ("prepared_by", "Prepared by", "text"),
        ("revenue", "Revenue", "sar"), ("cost_of_sales", "Cost of revenue", "sar"), ("gross_profit", "Gross profit", "sar"),
        ("operating_expenses", "Operating expenses", "sar"), ("operating_profit", "Operating profit", "sar"),
        ("finance_cost", "Finance cost", "sar"), ("net_profit", "Net profit", "sar"),
        ("cash", "Cash and bank balances", "sar"), ("trade_receivables", "Trade receivables, net", "sar"),
        ("inventory", "Inventories", "sar"), ("current_assets", "Total current assets", "sar"), ("total_assets", "Total assets", "sar"),
        ("short_term_borrowings", "Short-term borrowings", "sar"), ("current_liabilities", "Total current liabilities", "sar"),
        ("long_term_borrowings", "Long-term borrowings", "sar"), ("total_liabilities", "Total liabilities", "sar"),
        ("total_equity", "Total equity", "sar")),
        keywords=("MANAGEMENT ACCOUNTS", "UNAUDITED")),
    # ---------------------------------------------------------------- bank statements
    DocType("bank_statement", "Bank statement, 12 months", STMT, "account", "months:3", F(
        *COMMON, ("bank_name", "Bank", "text"), ("account_number", "Account number", "text"), ("iban", "IBAN", "text"),
        ("account_type", "Account type", "text"), ("period_from", "Period from", "date"), ("period_to", "Period to", "date"),
        ("opening_balance", "Opening balance", "sar"), ("total_credits", "Total credits", "sar"), ("total_debits", "Total debits", "sar"),
        ("closing_balance", "Closing balance", "sar"), ("returned_cheques", "Returned cheques", "int"),
        ("monthly", "Monthly summary", "list:month,credits,debits,closing_balance,avg_balance,returned_cheques"),
        ("transactions", "Transactions", "list:date,description,debit,credit,balance")),
        keywords=("ACCOUNT STATEMENT", "IBAN")),
    # ---------------------------------------------------------------- extras
    DocType("facility_request_letter", "Facility request letter (signed)", EXTRA, "company", "months:3", F(
        *COMMON, ("letter_date", "Date", "date"), ("addressed_to", "Addressed to", "text"), ("requested_total", "Total requested", "sar"),
        ("facilities", "Facilities requested", "list:facility,amount,purpose"), ("signatory", "Signed by", "text"),
        ("signatory_role", "Capacity", "text")),
        keywords=("REQUEST FOR CREDIT FACILITIES",)),
    DocType("board_resolution", "Board / partners' resolution to borrow", EXTRA, "company", "months:12", F(
        *COMMON, ("resolution_date", "Resolution date", "date"), ("resolution_number", "Resolution number", "text"),
        ("authorised_amount", "Borrowing authorised up to", "sar"), ("authorised_persons", "Authorised to sign", "text")),
        keywords=("RESOLUTION",)),
    DocType("authorised_signatories", "Authorised signatory list", EXTRA, "company", "months:12", F(
        *COMMON, ("as_of", "As of", "date"), ("signatories", "Signatories", "list:name,id_number,role,limit,mode")),
        keywords=("AUTHORISED SIGNATORIES",)),
    DocType("personal_net_worth", "Personal net-worth statement of guarantor", EXTRA, "guarantor", "months:12", F(
        ("full_name", "Guarantor", "text"), ("id_number", "ID number", "text"), ("statement_date", "Statement date", "date"),
        ("total_assets", "Total assets", "sar"), ("total_liabilities", "Total liabilities", "sar"), ("net_worth", "Net worth", "sar"),
        ("assets", "Assets", "list:asset,description,value"), ("liabilities", "Liabilities", "list:liability,description,value")),
        keywords=("PERSONAL NET WORTH STATEMENT",)),
    DocType("other_bank_offer_letter", "Other bank's facility offer letter", EXTRA, "bank", "none", F(
        *COMMON, ("bank_name", "Bank", "text"), ("letter_date", "Date", "date"), ("letter_reference", "Reference", "text"),
        ("total_limits", "Total facilities", "sar"), ("expiry_date", "Facilities valid until", "date"),
        ("facilities", "Facilities", "list:facility,limit,pricing,tenor"), ("security", "Security", "text")),
        keywords=("OFFER LETTER", "FACILITY LETTER")),
    DocType("other_bank_statement", "Other bank's latest facility statement", EXTRA, "bank", "months:3", F(
        *COMMON, ("bank_name", "Bank", "text"), ("statement_date", "Statement date", "date"),
        ("total_limits", "Total limits", "sar"), ("total_outstanding", "Total outstanding", "sar"),
        ("facilities", "Facilities", "list:facility,limit,outstanding,overdue,maturity")),
        keywords=("STATEMENT OF FACILITIES", "LIABILITY STATEMENT")),
    DocType("receivables_ageing", "Receivables ageing", EXTRA, "company", "months:3", F(
        *COMMON, ("as_of", "As of", "date"), ("total", "Total receivables", "sar"),
        ("bucket_0_90", "0-90 days", "sar"), ("bucket_91_180", "91-180 days", "sar"), ("bucket_181_365", "181-365 days", "sar"),
        ("bucket_over_365", "Over 365 days", "sar"),
        ("by_customer", "By customer", "list:customer,b0_90,b91_180,b181_365,over_365,total")),
        keywords=("RECEIVABLES AGEING",)),
    DocType("payables_ageing", "Payables ageing", EXTRA, "company", "months:3", F(
        *COMMON, ("as_of", "As of", "date"), ("total", "Total payables", "sar"),
        ("bucket_0_90", "0-90 days", "sar"), ("bucket_91_180", "91-180 days", "sar"), ("bucket_over_180", "Over 180 days", "sar"),
        ("by_supplier", "By supplier", "list:supplier,b0_90,b91_180,over_180,total")),
        keywords=("PAYABLES AGEING",)),
    DocType("top_customers_suppliers", "Top customers and suppliers", EXTRA, "company", "months:12", F(
        *COMMON, ("year", "Year", "int"), ("customers", "Top customers", "list:name,relationship,sales,share_pct,terms"),
        ("suppliers", "Top suppliers", "list:name,country,purchases,share_pct,terms")),
        keywords=("TOP CUSTOMERS",)),
    DocType("project_list", "Project list (contractors)", EXTRA, "company", "months:3", F(
        *COMMON, ("as_of", "As of", "date"),
        ("projects", "Projects", "list:project_id,project,employer,contract_value,start,planned_completion,work_done_pct,billed,received,retention_held,status")),
        required_for=("contractor",), keywords=("PROJECT LIST", "WORK IN HAND")),
    DocType("project_contract", "Project contract (extract)", EXTRA, "project", "none", F(
        *COMMON, ("project_id", "Project", "text"), ("employer", "Employer", "text"), ("consultant", "Consultant", "text"),
        ("contract_date", "Contract date", "date"), ("contract_value", "Contract value", "sar"),
        ("advance_pct", "Advance payment", "pct"), ("retention_pct", "Retention", "pct"),
        ("payment_terms_days", "Payment of certified amounts within (days)", "int"),
        ("start_date", "Commencement date", "date"), ("completion_date", "Completion date", "date"),
        ("performance_bond_pct", "Performance bond", "pct")),
        required_for=("contractor",), keywords=("CONTRACT AGREEMENT",)),
    DocType("payment_certificate", "Interim payment certificate", EXTRA, "certificate", "none", F(
        *COMMON, ("project_id", "Project", "text"), ("certificate_number", "Certificate number", "text"),
        ("period_to", "Work up to", "date"), ("certified_on", "Certified on", "date"),
        ("gross_work_done", "Cumulative work done", "sar"), ("this_certificate_gross", "Gross this certificate", "sar"),
        ("retention_this", "Retention deducted", "sar"), ("advance_recovery", "Advance recovery", "sar"),
        ("net_payable", "Net amount payable", "sar"), ("cumulative_retention", "Cumulative retention", "sar"),
        ("due_date", "Due date", "date")),
        required_for=("contractor",), keywords=("INTERIM PAYMENT CERTIFICATE",)),
    DocType("valuation_report", "Collateral valuation report", EXTRA, "collateral", "months:12", F(
        ("property", "Property", "text"), ("owner", "Registered owner", "text"), ("deed_number", "Title deed number", "text"),
        ("valuer", "Valuer", "text"), ("valuation_date", "Valuation date", "date"), ("market_value", "Market value", "sar"),
        ("forced_sale_value", "Forced-sale value", "sar")),
        required_for=("secured",), keywords=("VALUATION REPORT",)),
    DocType("title_deed", "Title deed", EXTRA, "collateral", "none", F(
        ("deed_number", "Deed number", "text"), ("owner", "Owner", "text"), ("property", "Property", "text"),
        ("area_sqm", "Area (sq m)", "int"), ("deed_date", "Deed date", "date"), ("encumbrance", "Encumbrance", "text")),
        required_for=("secured",), keywords=("TITLE DEED",)),
    DocType("insurance_policy", "Insurance policy (collateral)", EXTRA, "collateral", "expiry_date", F(
        ("policy_number", "Policy number", "text"), ("insured", "Insured", "text"), ("insurer", "Insurer", "text"),
        ("property", "Property insured", "text"), ("sum_insured", "Sum insured", "sar"), ("loss_payee", "Loss payee", "text"),
        ("issue_date", "Period from", "date"), ("expiry_date", "Period to", "date")),
        required_for=("secured",), keywords=("POLICY SCHEDULE", "INSURANCE")),
    DocType("site_visit_report", "Site-visit report (RM)", EXTRA, "company", "months:6", F(
        *COMMON, ("visit_date", "Visit date", "date"), ("visited_by", "Visited by", "text"), ("met_with", "Met with", "text"),
        ("premises", "Premises", "text"), ("staff_seen", "Staff observed", "int"), ("observations", "Observations", "text")),
        keywords=("SITE VISIT REPORT",)),
    DocType("aml_kyc_questionnaire", "AML/KYC questionnaire", EXTRA, "company", "months:12", F(
        *COMMON, ("completed_on", "Completed on", "date"), ("ubos", "Ultimate beneficial owners", "list:name,pct,pep"),
        ("pep_flag", "Politically exposed person", "text"), ("countries", "Countries of trade", "text"),
        ("cash_intensive", "Cash-intensive business", "text"), ("risk_rating", "Customer risk rating", "text")),
        keywords=("AML", "KYC QUESTIONNAIRE")),
    # ---------------------------------------------------------------- the business request (Part B input) and the reference
    DocType("business_request", "Business request (bank-form 'Action requested')", "proposal", "company", "none", F(
        *COMMON, ("cif", "CIF", "text"), ("request_date", "Date", "date"), ("rm", "Relationship manager", "text"),
        ("action_requested", "Action requested", "text"), ("total_existing", "Total existing limits", "sar"),
        ("total_proposed", "Total proposed limits", "sar"),
        ("facilities", "Facilities", "list:limit,existing,outstanding,proposed,cash_margin_pct,pricing,tenor"),
        ("security", "Security and support", "list:item"), ("conditions", "Terms and conditions", "list:item")),
        required_for=(), keywords=("ACTION REQUESTED", "CREDIT PROPOSAL")),
    DocType("reference_proposal", "Reference bank-form proposal (answer)", "proposal", "company", "none", F(
        *COMMON, ("recommendation", "Credit recommendation", "text")), required_for=(),
        keywords=("CREDIT DIVISION COMMENTS",)),
]

BY_CODE = {d.code: d for d in DOC_TYPES}
