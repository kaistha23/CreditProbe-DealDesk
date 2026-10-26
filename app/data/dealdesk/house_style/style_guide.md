# CreditProbe house style guide

Derived by `python -m backend.dealdesk.house_style.build` from every proposal in the corpus (21 documents). The profile updates incrementally in the app as proposals are uploaded and as RMs edit drafts.

## House style: UAE house (anonymised), all memo types, contractor

Derived from 3 documents (weighted 7.0); primary exemplar: EX-twin_b_gulf_meridian_new_project. 

### Structure

1. **Action requested** (Request; business voice; in 100% of memos; prose).
2. **Security and support** (Security; business voice; in 83% of memos; mostly bullets).
3. **Terms and conditions** (Conditions and covenants; business voice; in 83% of memos; prose). Table: Condition | Committee ref. | Due | Status.
4. **Facilities** (Facilities; business voice; in 100% of memos; prose). Table: Bank | Group entity | Limit (client) | Limit (bureau) | O/s (client) | O/s (bureau) | Difference o/s.
5. **Background and ownership** (Obligor and group; business voice; in 83% of memos; prose). Table: Entity | Relation | Activity | Country.
6. **Credit bureau** (Account conduct and bureau; business voice; in 100% of memos; prose). Table: Entity / UBO | Role | Outstanding | Overdue | Ret. cheques | Cheque dates | Score | Court cases | Report.
7. **Effects of the current geopolitical and market situation** (Business and projects; business voice; in 100% of memos; prose). Table: Item | Value.
8. **Header block** (Other; business voice; in 100% of memos; prose). Table: Item | Value.
9. **Financials** (Financial highlights; business voice; in 100% of memos; prose). Table: Item | FY2023 | FY2024 | FY2025 | H1 2026.
10. **Central bank risk bureau (CBRBR)** (Risks and mitigants; business voice; in 100% of memos; prose). Table: Entity | Funded limit | Funded o/s | Non-funded limit | Non-funded o/s | Total o/s | Banks | Classification.
11. **Financial synopsis** (Executive summary; business voice; in 83% of memos; mostly bullets).
12. **Credit division recommendation** (Recommendation; credit voice; in 100% of memos; prose).

### Numbers

- Money: currency first, unit 'm', 1 decimal(s), thousands separator (e.g. AED 212.4m (1dp)).
- Percentages written with '%'; multiples with 'x'. Round billions as 'bn'.

### Voice and tone

- **Business unit:** 14.56 words a sentence (sd 9.95); hedges 0.238 per 100 words; first person 0.143 per 100 words; passive in 8% of sentences.
- **Credit division:** 14.87 words a sentence (sd 6.27); hedges 0.0 per 100 words; first person 0.0 per 100 words; passive in 18% of sentences.

- Spelling: British.

### Standard phrases and openers

- "# m group exposure"
- "# months late"
- "# months past"
- "# returned cheques"
- "about # months"
- "about # months past"
- "after this request"
- "after this request AED"
- "exposure after this"
- "exposure after this request"
- "exposure cap from"
- "exposure cap from AED"
- "extension of time"
- "extension of time not"
- "group exposure after"
- Action requested: opens with "@ and documentation"; "business requests approval"; "purpose as per"
- Security and support: opens with "security for @"; "as per business"; "assignment of project"
- Terms and conditions: opens with "terms for @"; "# @ LG"; "# @ acknowledgement"
- Facilities: opens with "CC # #"; "# funded line"; "# of #"
- Background and ownership: opens with "@ borrower #"; "@ and key"; "@ dd group"
- Credit bureau: opens with "project limit #"; "# cheques returned"; "@ bureau bureau"
- Effects of the current geopolitical and market situation: opens with "as per business"; "AED # m"; "completion moved from"
- Header block: opens with "CRO review comments"; "backlog of AED"; "credit committee approval"
- Financials: opens with "@ dd obligor"; "# statement scope"; "as per the"
- Central bank risk bureau (CBRBR): opens with "we note that"; "business conveys the"; "# @ above"
- Financial synopsis: opens with "@ cash flow"; "@ due from"; "@ liabilities of"
- Credit division recommendation: opens with "# @ the"; "# @ to"; "# @ as"

### Recommendation wording

- "# @ the reduction of the @ limit #"
- "RM to confirm in writing"
- "# @ as listed in section # # items"
- "# @ as per @ recommended alternative APG and"

### Risks and mitigants

- Markers used: tranche, watch

### Abbreviations

PY, CRM, EOT, KSC, APG, CAR, DMCCM, RM, CIF, H1, CRO, UAE, RAROC, CBRBR, F1, F2, F3, F4, F5, KWD, LG, PB, TL, CBUAE, DPD, EBITDA, SICR

_'@' stands for a name and '#' for a figure: phrases never carry a client name or a number._


## House style: UAE house (anonymised), renewal, trader

Derived from 1 documents (weighted 5.0); primary exemplar: EX-twin_a_al_sahel_renewal. 

### Structure

1. **Action requested** (Request; business voice; in 100% of memos; prose).
2. **Security and support** (Security; business voice; in 100% of memos; mostly bullets).
3. **Terms and conditions** (Conditions and covenants; business voice; in 100% of memos; prose). Table: Condition | Committee ref. | Due | Status.
4. **Facilities** (Facilities; business voice; in 100% of memos; prose). Table: Bank | Group entity | Limit (client) | Limit (bureau) | O/s (client) | O/s (bureau) | Difference o/s.
5. **Background and ownership** (Obligor and group; business voice; in 100% of memos; prose). Table: Entity | Relation | Activity | Country.
6. **Credit bureau** (Account conduct and bureau; business voice; in 100% of memos; prose). Table: Entity / UBO | Role | Outstanding | Overdue | Ret. cheques | Cheque dates | Score | Court cases | Report.
7. **Effects of the current geopolitical and market situation** (Business and projects; business voice; in 100% of memos; prose).
8. **Header block** (Other; business voice; in 100% of memos; mostly bullets). Table: Item | Value.
9. **Central bank risk bureau (CBRBR)** (Risks and mitigants; business voice; in 100% of memos; prose). Table: Entity | Funded limit | Funded o/s | Non-funded limit | Non-funded o/s | Total o/s | Banks | Classification.
10. **Financials** (Financial highlights; business voice; in 100% of memos; prose). Table: Item | FY2023 | FY2024 | FY2025 | H1 2026.
11. **Financial synopsis** (Executive summary; business voice; in 100% of memos; mostly bullets).
12. **Credit division recommendation** (Recommendation; credit voice; in 100% of memos; prose).

### Numbers

- Money: currency first, unit 'm', 1 decimal(s), thousands separator (e.g. AED 212.4m (1dp)).
- Percentages written with '%'; multiples with 'x'.

### Voice and tone

- **Business unit:** 13.97 words a sentence (sd 8.07); hedges 0.115 per 100 words; first person 0.172 per 100 words; passive in 6% of sentences.
- **Credit division:** 14.35 words a sentence (sd 5.95); hedges 0.0 per 100 words; first person 0.0 per 100 words; passive in 30% of sentences.

- Spelling: British.

### Standard phrases and openers

- "# accounts audited"
- "# accounts audited by"
- "# additional conditions"
- "# additional conditions below"
- "# and transit times"
- "# approval of total"
- "# assignment of insurance"
- "# bank lines"
- "# bank lines differ"
- "# bps cash margin"
- "# bureau report"
- "# cheques returned"
- "# cheques returned between"
- "# counterparties account"
- "# counterparties account for"
- Action requested: opens with "@ and documentation"; "business requests approval"; "purpose as per"
- Security and support: opens with "as per business"; "# of #"; "@ UBO for"
- Terms and conditions: opens with "# @ business"; "# @ financials"; "# @ of"
- Facilities: opens with "CC # #"; "# funded line"; "# of #"
- Background and ownership: opens with "@ # of"; "@ borrower #"; "@"
- Credit bureau: opens with "AED # m"; "# cheques returned"; "@ FZE AED"
- Effects of the current geopolitical and market situation: opens with "@ on routes"; "@ shipping disruption"; "@ shock moderate"
- Header block: opens with "# year relationship"; "CRO review comments"; "UBO personal guarantee"
- Central bank risk bureau (CBRBR): opens with "we note that"; "# @ conditions"; "# @ not"
- Financials: opens with "@ dd obligor"; "as per the"; "basis of qualification"
- Financial synopsis: opens with "@ cash flow"; "@ due from"; "@ liabilities of"
- Credit division recommendation: opens with "# @ to"; "# @ as"; "DSCR # x"

### Recommendation wording

- "# @ as listed in section # # items"
- "# @ as per @ recommended alternative @ AED"
- "# @ business turnover of # x the funded"
- "# @ change of auditor to a bank-panel auditor"

### Risks and mitigants

- Markers used: watch

### Abbreviations

PY, CRM, FZE, CBRBR, LC, CIF, DSCR, RM, UBO, CRO, F1, F2, F3, F4, F5, GDP, H1, PDC, RAROC, TL

_'@' stands for a name and '#' for a figure: phrases never carry a client name or a number._


## House style: KSA reference house, new, contractor

Derived from 3 documents (weighted 3.0); 

### Structure

1. **Obligor** (Obligor and group; business voice; in 100% of memos; prose). Table: Field | Value.
2. **Financials (SAR m)** (Financial highlights; business voice; in 100% of memos; prose). Table: Item | 2023 | 2024 | 2025 | 2026 P | 2027 P | 2028 P.
3. **Request** (Request; business voice; in 100% of memos; prose). Table: Term | Requested.
4. **Security** (Security; business voice; in 100% of memos; prose). Table: ID | Type | Guarantor | Rating | Coverage | Offered.
5. **Business case** (Business and projects; business voice; in 100% of memos; prose). Table: Ancillary income (SAR m p.a.) | Amount.
6. **Relationship manager's recommendation** (Recommendation; business voice; in 100% of memos; prose).

### Numbers

- Money: currency first, unit 'm', 1 decimal(s), thousands separator (e.g. AED 212.4m).
- Percentages written with '%'; multiples with 'x'.

### Voice and tone

- **Business unit:** 8.75 words a sentence (sd 7.46); hedges 0.0 per 100 words; first person 0.0 per 100 words; passive in 0% of sentences.

- Spelling: British.

### Standard phrases and openers

- "@ recommends the facility"
- "facility as requested"
- "recommends the facility"
- "recommends the facility as"
- "the facility as requested"
- "collateral none offered"
- "covenant package standard"
- Security: opens with "collateral none offered"; "covenant package standard"; "covenant package none"
- Relationship manager's recommendation: opens with "@ recommends the"

### Recommendation wording

- "@ recommends the facility as requested construction of a"
- "@ recommends the facility as requested performance guarantee for"
- "@ recommends the facility as requested working capital for"

_'@' stands for a name and '#' for a figure: phrases never carry a client name or a number._


## House style: KSA reference house, all memo types, all segments

Derived from 15 documents (weighted 15.0); 

### Structure

1. **Obligor** (Obligor and group; business voice; in 100% of memos; prose). Table: Field | Value.
2. **Financials (SAR m)** (Financial highlights; business voice; in 100% of memos; prose). Table: Item | 2023 | 2024 | 2025 | 2026 P | 2027 P | 2028 P.
3. **Request** (Request; business voice; in 100% of memos; prose). Table: Term | Requested.
4. **Security** (Security; business voice; in 100% of memos; prose). Table: ID | Type | Value | Currency | Valuation date | Offered.
5. **Business case** (Business and projects; business voice; in 100% of memos; prose). Table: Ancillary income (SAR m p.a.) | Amount.
6. **Relationship manager's recommendation** (Recommendation; business voice; in 100% of memos; prose).

### Numbers

- Money: currency first, unit 'm', 1 decimal(s), thousands separator (e.g. AED 212.4m).
- Percentages written with '%'; multiples with 'x'.

### Voice and tone

- **Business unit:** 9.35 words a sentence (sd 7.24); hedges 0.0 per 100 words; first person 0.0 per 100 words; passive in 0% of sentences.

- Spelling: British.

### Standard phrases and openers

- "@ recommends the facility"
- "facility as requested"
- "recommends the facility"
- "recommends the facility as"
- "the facility as requested"
- "covenant package standard"
- "collateral none offered"
- "as requested working"
- "as requested working capital"
- "facility as requested working"
- "requested working capital"
- "as requested ijara"
- "covenant package none"
- "facility as requested ijara"
- "working capital for"
- Security: opens with "covenant package standard"; "collateral none offered"; "covenant package none"
- Relationship manager's recommendation: opens with "@ recommends the"

### Recommendation wording

- "@ recommends the facility as requested construction of a"
- "@ recommends the facility as requested debottlenecking capex at"
- "@ recommends the facility as requested diminishing musharaka for"
- "@ recommends the facility as requested equipment and mobilisation"

_'@' stands for a name and '#' for a figure: phrases never carry a client name or a number._

