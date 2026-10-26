# R12 data contract (Session E)

**Generated from `backend/dealdesk/data/schema.py`** by `python3 -m backend.dealdesk.data.contract`; do not edit by hand.
PLAN_R12 §0: every business fact is read from a relation registered in Data Domains through the shared readers, and
every decision is published back as a relation.

## How to read and write

```python
from backend.dealdesk.data import dd_read, dd_frame, publish, trace

dd_read("dd_document", proposal_id="R12-TWA", status=["pending", "expired"])   # list[dict], json columns parsed
dd_frame("bureau_cbrbr", proposal_id="R12-TWB")                               # pandas DataFrame
dd_read("rel_group_quarter", borrower_id="CB00001")                           # any registered relation works
publish("dd_review_finding", rows, mode="upsert", actor="B")                 # new version, manifest updated
trace("dd_document", row)   # {"domain", "relation", "key", "period", "version"} for (i) / Trace / Open in Data Domains
```

- `dd_read(relation, columns=None, parse_json=True, **filters)`: a filter is equality (scalar), membership (list, tuple,
  set) or `None` (is null). Unknown relations raise `KeyError`; an R12 relation not yet written reads as empty.
- `publish(relation, rows, mode="upsert"|"append"|"replace"|"replace_where", actor=..., where=None)`: only the relations below.
  `replace_where` drops the rows matching `where` (e.g. `{"proposal_id": "R12-TWA"}`) and adds yours: use it when you
  recompute one deal's findings, SWOT or stress results, so the rows Session E seeded for that deal are replaced. Rows are conformed
  to the contract (unknown columns raise `SchemaError`, missing ones are null, types coerced); `reporting_quarter`
  defaults to the as-of; `rel_version` and `published_at` are stamped. Upsert replaces rows with the same key. Each
  publish increments the version in the folder manifest (rows, columns, sha, last 50 history entries) and archives
  the previous parquet under `var/dealdesk/r12_history/<relation>/v<n>.parquet`.
- Tests set `DEALDESK_R12_ROOT` to a scratch copy of the checkout's `data/` so they never write committed files
  (see `backend/tests/test_r12_lineage.py`, fixture `r12_root`).
- Types: text, int, float, flag (0/1 integer), date (ISO `YYYY-MM-DD` text), ts (ISO UTC timestamp text), json (JSON
  text; `dd_read` parses it).
- Every relation ends with the lineage columns `reporting_quarter`, `rel_version`, `published_at`.
- Amounts in R12 demo deals are SAR million (the Deal Desk engine's currency), labelled `_mn`.

## Shared schemas other sessions write

| Relation | Writers | Use |
|---|---|---|
| `dd_review_finding` | B (review), C (governance and conduct flags), D (stress), I (book) | one row per finding; `review_point` 1..12, `severity`, evidence as relation + key + value, `rating_notch`, links to `condition_id` / `query_id` |
| `dd_monitoring_plan` | D at approval, I on a tier change | tier High / Medium / Standard from the stress verdict, `drivers`, `named_triggers` (json list of {metric, operator, threshold, label}), `ews_threshold_overrides` (json object), review frequency; a change writes a new active row and marks the old one superseded |
| `dd_condition` | B, D, I | conditions with status, due, trigger; `source = prior_approval` rows are the earlier conditions and their compliance |
| `dd_workflow_event`, `dd_query`, `dd_document` | U, B | workflow history, RM queries, the document checklist |
| `dd_stress_*`, `dd_swot`, `dd_promise`, `dd_raroc_drift`, `dd_policy*`, `dd_parameter_provenance` | D, T, C, I, G | as described per relation |

## Who reads what

| Session | Reads | Writes |
|---|---|---|
| U shell | `dd_deal` (landing cards: workflow_state, product, committee_date), `dd_workflow_event`, `dd_document` (badge), `dd_condition` (due), `deals.get` | `dd_workflow_event` (`bridge.publish_workflow`) |
| B review | `dd_financials_detail` (adjusted ratios, ageing, auditor), `bureau_*`, `other_bank_facility`, `dd_condition` (prior_approval), `dd_promise`, `b360_insider_link`, `dd_document_rule`, `dd_security`, `dd_tnc` | `dd_review_finding`, `dd_query`, `dd_document`, `dd_condition` |
| C group | `rel_*` (book borrowers), `b360_*` (R12 deals), `dd_group_exposure`, `dd_deal.group_cap_*`, `dd_account_conduct` / `dep_month`, `dd_returned_cheque`, `bureau_cbrbr` | `dd_review_finding` (governance, conduct), `dd_swot` |
| D stress | `dd_stress_scenario`, `dd_stress_sensitivity`, `dd_project_cashflow`, `dd_business_profile` (deal facts) | `dd_stress_result`, `dd_monitoring_plan` (`bridge.publish_monitoring_plan`), `dd_stress_scenario` (editor) |
| F papers | every relation in the product template's `relations` (`products/templates.py`), `dd_reference`, `dd_business_profile` | — |
| G parameters | `dd_policy`, `dd_policy_clause`, `dd_parameter_provenance` | the same |
| I book | `dd_raroc_drift`, `dd_promise`, `dd_monitoring_plan`, `dd_condition`, `orig_facility`, `cls_exposure`, `ecl_facility` | `dd_raroc_drift`, `dd_promise`, `dd_monitoring_plan` |
| P products | `dd_project`, `dd_project_cashflow`, `dd_syndication`, `dd_escrow_account`, `dd_escrow`, `dd_sme_application`, `dd_facility_limit` | — |
| T calibration | `dd_obligor_financials`, `dd_financials_detail`, book relations | `dd_stress_sensitivity` (new versions) |

## The R12 demo deals (all fictional)

| proposal_id | Deal | Product |
|---|---|---|
| R12-TWA | Twin A: Al Sahel Building Materials Group, trading group renewal | corporate (trade) |
| R12-TWB | Twin B: Gulf Meridian Contracting, new project limit (employer Saadiyat Crest Developments) | contracting |
| R12-SYN | Najd Petrochem Syndicate Participation | syndicated |
| R12-ESC | Marina Vista Off-plan Escrow | escrow |
| R12-SME1..3 | Three SME fast-track applications | sme |

Seeded rows that writers will replace: `dd_review_finding` (`E-…` ids, prior-review findings), `dd_swot` (R12-SYN),
`dd_stress_result` (the rating −1/−2/−3 family per R12 deal, engine-computed), `dd_monitoring_plan` (twin A's 2025 plan),
`dd_raroc_drift` (twin A), `dd_condition` (earlier approval conditions, `source = prior_approval`).

Product templates: `backend/dealdesk/products/templates.py` (`for_deal(pid)`, `applies(pid, kind, item)`).
Lineage and no-side-door harness: `backend/tests/test_r12_lineage.py` (add cases to `LINEAGE_CASES`, `SCOPED_SOURCES`,
`RUNTIME_CASES`), helpers in `backend/dealdesk/data/lineage.py` (`figure`, `untraced`, `watch_opens`, `side_doors`).
Rebuild the data: `python3 -m backend.dealdesk.data.build` (`--check` compares with the committed manifests).

`dd_deal` lists every deal (DD-01..15, PL-01..27, R12-*) with its product template; `backend.dealdesk.data.deals.get(pid)`
returns the engine-ready proposal record for any of them.

## Borrower 360 (now live)

Registered as-is from `data/relationships/rel-saudi-v1` (read-only, built by `backend/rel_domains/build.py`; columns in its manifest):

| Relation | Keys | Period | Meaning |
|---|---|---|---|
| `rel_edge_quarter` | edge_id, reporting_quarter | reporting_quarter | Typed links between book borrowers: ownership, supplier and customer shares, guarantees, shared collateral. |
| `rel_group_quarter` | group_id, borrower_id, reporting_quarter | reporting_quarter | Each book borrower's economic group, role and ownership share, by quarter. |
| `rel_person_role` | person_id, borrower_id, role | valid_from_quarter | Shareholders, directors and guarantors (persons) of book borrowers, with validity quarters. |
| `rel_shared_collateral` | collateral_id, borrower_id, reporting_quarter | reporting_quarter | Collateral items pledged for more than one borrower, with claims and allocation. |

## Deal Desk (extended)

### `dd_deal` — Deal register

Every deal Deal Desk can open, with its product template, workflow state and the bank-form header block (PROPOSAL_ANATOMY §2.1). The R12 fictional deals carry their full proposal record in proposal_json.

- File: `data/dealdesk/dd-saudi-v1/dd_deal.parquet`
- Keys: proposal_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal (DD, PL and R12 fictional deals)
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | Deal identifier: DD-nn (seeded), PL-nn (pipeline set), R12-xxx (R12 fictional deals). |
| `source` | text |  | deal_desk (proposals.json), pipeline (dd_pipeline) or r12_demo (this relation's proposal_json). |
| `product` | text |  | Product template id: corporate, contracting, escrow, syndicated or sme (backend/dealdesk/products/templates.py). |
| `deal_name` | text |  | Short deal title shown on lists. |
| `obligor_id` | text |  | Obligor (borrower) id: book CB…, new-to-bank DN…/DP…, or R12 fictional entity XE-…. |
| `obligor_name` | text |  | Obligor legal name (fictional). |
| `group_id` | text |  | Economic / connected group id. |
| `group_name` | text |  | Economic / connected group name. |
| `case_type` | text |  | new, renewal, additional, amendment or renewal_and_new (the header ticks). |
| `status` | text |  | Deal Desk status: new, in_review, counter_offered, approved, declined. |
| `workflow_state` | text |  | Latest workflow state (dd_workflow_event): draft, submitted, in_review, queries, recommended, committee, approved, declined. |
| `rm` | text |  | Relationship manager (fictional). |
| `credit_analyst` | text |  | Credit analyst assigned (fictional). |
| `business_unit` | text |  | Business unit. |
| `branch` | text |  | Branch or unit on the header block. |
| `received_date` | date |  | Date the proposal reached credit. |
| `committee_date` | date |  | Planned or held committee date (blank if not scheduled). |
| `approval_authority` | text |  | Approval authority required (e.g. CC level 2, Board Credit Committee). |
| `currency` | text |  | Deal currency. |
| `existing_limits_mn` | float | million (deal currency, SAR) | Total existing limits. |
| `proposed_limits_mn` | float | million (deal currency, SAR) | Total proposed limits. |
| `group_exposure_mn` | float | million (deal currency, SAR) | Group exposure after the proposal (funded + non-funded). |
| `group_cap_existing_mn` | float | million (deal currency, SAR) | Approved group exposure cap today (0 when none). |
| `group_cap_proposed_mn` | float | million (deal currency, SAR) | Group exposure cap asked for (equal to existing when no change). |
| `rating_existing` | text |  | Existing internal rating. |
| `rating_proposed` | text |  | Proposed internal rating. |
| `cif` | text |  | CIF / base number (fictional). |
| `group_no` | text |  | Group number (fictional). |
| `account_opened_date` | date |  | Date the relationship account was opened. |
| `related_party_flag` | flag |  | 1 when the obligor is a related or connected party of the bank. |
| `related_party_cif` | text |  | CIF of the related party, when flagged. |
| `purpose_code` | text |  | Purpose code. |
| `industry_code` | text |  | Industry code (ISIC). |
| `collateral_code` | text |  | Collateral code. |
| `review_date` | date |  | Next review date of the limits. |
| `ao` | text |  | Account officer. |
| `ro` | text |  | Relationship officer. |
| `proposal_json` | json |  | Full proposal record in the proposals.json shape (R12 fictional deals only; empty for DD and PL rows). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_pipeline` — Pipeline set

The fictional pending applications PL-01..27 (moved out of data/dealdesk/pipeline/pipeline.json). backend.dealdesk.pipeline reads them through dd_read; proposal_json is the full record.

- File: `data/dealdesk/dd-saudi-v1/dd_pipeline.parquet`
- Keys: proposal_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per pending pipeline application
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | Pipeline application id PL-nn. |
| `status` | text |  | Application status (new, in_review, counter_offered). |
| `rm` | text |  | Relationship manager. |
| `business_unit` | text |  | Business unit. |
| `received_date` | date |  | Date received. |
| `purpose` | text |  | Purpose of the facility asked. |
| `obligor_id` | text |  | Obligor id (book CB… or new-to-bank DP…). |
| `obligor_name` | text |  | Obligor name (fictional). |
| `existing_flag` | flag |  | 1 for an existing borrower of the corporate book. |
| `sector` | text |  | Sector of the obligor. |
| `sub_sector` | text |  | Sub-sector (sub sector). |
| `region` | text |  | Region of the obligor. |
| `internal_rating` | text |  | Internal rating. |
| `group_id` | text |  | Connected group id. |
| `group_name` | text |  | Connected group name. |
| `facility_type` | text |  | Facility type asked. |
| `structure` | text |  | Structure asked (conventional, murabaha, tawarruq, ijara, musharaka). |
| `currency` | text |  | Currency of the ask. |
| `amount` | float | million (ask currency) | Amount asked. |
| `tenor_years` | int | years | Tenor asked (tenor years). |
| `margin_bps` | float | bps | Margin asked. |
| `existing_ead_sar_mn` | float | SAR million | Existing exposure of the obligor in the book. |
| `proposal_json` | json |  | The full application record (proposals.json shape) the engine prices. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_workflow_event` — Workflow events

Every handover on a deal file: Draft → Submitted → In review ⇄ Queries → Recommended → Committee → Approved with conditions (I17), who and when.

- File: `data/dealdesk/dd-saudi-v1/dd_workflow_event.parquet`
- Keys: event_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per state change
- Owner: U · Writers: U (workflow.py) at runtime; E fictional history

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `event_id` | text |  | Event id (event id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `seq` | int |  | Order of the event within the deal. |
| `from_state` | text |  | State before (blank for the first event). |
| `to_state` | text |  | State after: draft, submitted, in_review, queries, recommended, committee, approved, declined, renewal_opened. |
| `actor` | text |  | Who made the change (fictional user name). |
| `actor_role` | text |  | Role: rm, credit_reviewer, credit_head, cro, committee, system. |
| `at` | ts |  | When it happened (UTC). |
| `note` | text |  | Handover note. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_document_rule` — Document rules

The checklist generator: which document each product and segment requires, for which entity scope, how long it stays valid and the policy clause that requires it (I26).

- File: `data/dealdesk/dd-saudi-v1/dd_document_rule.parquet`
- Keys: rule_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per required document rule
- Owner: B · Writers: B (documents.py) / E seed

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `rule_id` | text |  | Rule id (rule id). |
| `product` | text |  | Product template id or * for every product. |
| `segment` | text |  | Segment (corporate, sme, *). |
| `case_type` | text |  | Case types it applies to (new, renewal, * …), separated by semicolons. |
| `doc_type` | text |  | Document type code (trade_licence, moa, audited_fs, interim_fs, bureau_entity, bureau_ubo, other_bank_fal, guarantor_nw, valuation, insurance, legal_opinion, project_contract, payment_certificate, escrow_agreement, syndication_ia, sme_application …). |
| `doc_label` | text |  | Document name as shown on the checklist. |
| `scope` | text |  | subject, each_group_entity, each_ubo, each_guarantor, each_bank, each_project, each_collateral. |
| `validity_days` | int | days | Days the document stays valid after its date (0 = no expiry). |
| `mandatory_flag` | flag |  | 1 when missing blocks completeness; 0 when it can be waived by the reviewer. |
| `policy_id` | text |  | Policy that requires it (dd_policy). |
| `clause` | text |  | Clause of the policy. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_document` — Deal documents

The document checklist of each deal with status received / pending / expired / waived (I26).

- File: `data/dealdesk/dd-saudi-v1/dd_document.parquet`
- Keys: document_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per required document of a deal
- Owner: B · Writers: B at runtime; E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `document_id` | text |  | Document id (document id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `rule_id` | text |  | Rule that requires it (dd_document_rule). |
| `doc_type` | text |  | Document type code. |
| `doc_label` | text |  | Document name. |
| `entity_id` | text |  | Entity, person, project or collateral it is for. |
| `entity_name` | text |  | Its name (entity name). |
| `status` | text |  | received, pending, expired or waived. |
| `doc_date` | date |  | Date of the document (blank when pending). |
| `expiry_date` | date |  | Date it expires (blank when no expiry). |
| `received_date` | date |  | Date credit received it. |
| `waived_by` | text |  | Who waived it, when waived. |
| `note` | text |  | Note, e.g. 'not provided as per business'. |
| `file_ref` | text |  | Reference of the stored file (fictional). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_review_finding` — Review findings

THE SHARED FINDING SCHEMA (B, C, D, I): every review finding with its 12-point review area, severity, evidence (relation + key + value) and what it led to (condition, query, rating notch).

- File: `data/dealdesk/dd-saudi-v1/dd_review_finding.parquet`
- Keys: finding_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per finding
- Owner: B · Writers: B, C, D, I via publish(); E seeds twin findings

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `finding_id` | text |  | Finding id (prefix by writer: B-, C-, D-, I-, E- for seeded). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `review_point` | int |  | I16 review point 1..12 (1 completeness, 2 claims vs evidence, 3 consistency, 4 re-performed analysis, 5 policy and regulation, 6 group and connected parties, 7 collateral and legal, 8 track record, 9 precedent and peers, 10 language, 11 versions, 12 outputs). |
| `category` | text |  | Sub-area: e.g. adjusted_ratios, receivables_quality, auditor_quality, bureau_reconciliation, earlier_conditions, insider_link, governance, conduct, stress, drift, promise. |
| `severity` | text |  | critical, high, medium, low or info. |
| `title` | text |  | One-line finding. |
| `finding_text` | text |  | The finding in the credit voice (fact, number, date, attribution). |
| `claim_text` | text |  | What the proposal or business claims (blank when none). |
| `claim_value` | float |  | Claimed value, when numeric. |
| `evidence_value` | float |  | Evidenced value, when numeric. |
| `evidence_unit` | text |  | Unit of claim and evidence values. |
| `evidence_domain` | text |  | Data Domains domain of the evidence. |
| `evidence_relation` | text |  | Relation of the evidence. |
| `evidence_key` | text |  | Key of the evidence row(s), as col=value pairs separated by semicolons. |
| `status` | text |  | open, resolved, accepted (risk accepted) or superseded. |
| `rating_notch` | int | notches | Rating overlay this finding carries (0, or −1 per red flag; C). |
| `condition_id` | text |  | Condition it created (dd_condition), if any. |
| `query_id` | text |  | Query it created (dd_query), if any. |
| `raised_by` | text |  | Writer session or user. |
| `raised_at` | ts |  | When raised (raised at). |
| `resolved_at` | ts |  | When resolved (blank while open). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_query` — RM queries

Credit's queries to the RM and the replies, threaded (I16-1, I17), sent through Mail.

- File: `data/dealdesk/dd-saudi-v1/dd_query.parquet`
- Keys: query_id, seq, reporting_quarter · Period: `reporting_quarter` · Grain: one row per message in a query thread
- Owner: B · Writers: B at runtime; E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `query_id` | text |  | Query (thread) id. |
| `seq` | int |  | Message number within the thread (1 = the query). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `finding_id` | text |  | Finding that raised it (blank when ad hoc). |
| `document_id` | text |  | Missing document it asks for (blank when none). |
| `direction` | text |  | to_rm or from_rm. |
| `author` | text |  | Author of the message. |
| `author_role` | text |  | rm or credit_reviewer. |
| `sent_at` | ts |  | When sent (sent at). |
| `subject` | text |  | Subject line. |
| `body` | text |  | Message text. |
| `status` | text |  | Thread status after this message: open, answered or closed. |
| `mail_ref` | text |  | Mail message reference. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_condition` — Conditions and covenants

Conditions precedent, covenants, undertakings, reporting and monitoring conditions with status, due date and trigger (moved out of var/dealdesk/dealdesk.sqlite), including the status of earlier approval conditions.

- File: `data/dealdesk/dd-saudi-v1/dd_condition.parquet`
- Keys: condition_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per condition
- Owner: B · Writers: B, D, I via publish(); E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `condition_id` | text |  | Condition id. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `limit_id` | text |  | Limit it applies to (dd_facility_limit), or ALL. |
| `kind` | text |  | cp (prior to limit loading), covenant, undertaking, reporting, monitoring, routing, security. |
| `text` | text |  | The condition in operational words (who, what, by when, measured how). |
| `owner` | text |  | Who must deliver or monitor it (e.g. RM and regional head). |
| `due_date` | date |  | Due date (blank for continuing covenants). |
| `frequency` | text |  | once, monthly, quarterly, semi_annual, annual. |
| `trigger_metric` | text |  | Metric that tests it (e.g. dscr_x, routing_multiple, largest_customer_share_pct). |
| `trigger_operator` | text |  | <, <=, >, >= or =. |
| `trigger_threshold` | float |  | Threshold (trigger threshold). |
| `measured_value` | float |  | Last measured value. |
| `measured_at` | date |  | When last measured. |
| `status` | text |  | open, met, not_complied, breached, waived. |
| `source` | text |  | prior_approval (earlier committee), review (B), approval (recommendation), stress (D), r11. |
| `prior_committee_ref` | text |  | Committee decision reference that set it (earlier conditions). |
| `set_by` | text |  | Who set it (set by). |
| `set_at` | ts |  | When set (set at). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_monitoring_plan` — Monitoring plans

THE SHARED MONITORING PLAN SCHEMA (D, I, EWS link): the monitoring tier set at approval from the stress verdict (§1.5), its drivers, named triggers, EWS threshold overrides and review frequency. A tier change writes a new row (status active) and supersedes the previous one; the reason is required.

- File: `data/dealdesk/dd-saudi-v1/dd_monitoring_plan.parquet`
- Keys: plan_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal plan version
- Owner: D · Writers: D at approval; I on tier change; E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `plan_id` | text |  | Plan id (one per version). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `obligor_id` | text |  | Obligor the EWS customer page shows it on. |
| `facility_ref` | text |  | Facility or limit id, or ALL. |
| `tier` | text |  | High, Medium or Standard. |
| `stress_verdict` | text |  | restructure, approve_enhanced, approve_standard or approve. |
| `worst_breaking_severity` | text |  | mild, moderate, severe or none. |
| `drivers` | json |  | Stressed drivers watched, e.g. ["largest_customer_share", "payment_delay"]. |
| `named_triggers` | json |  | List of {metric, operator, threshold, label} named triggers. |
| `ews_threshold_overrides` | json |  | Object {ews_rule: lowered threshold} for tier High names. |
| `review_frequency` | text |  | quarterly, semi_annual or annual. |
| `next_review_date` | date |  | Next review date. |
| `set_by` | text |  | Who set it (Deal Desk user or system). |
| `set_at` | ts |  | When it happened (UTC). |
| `reason` | text |  | Why this tier (required on every change). |
| `status` | text |  | active or superseded. |
| `previous_tier` | text |  | Tier before this version (blank on the first). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_stress_scenario` — Stress scenarios

Versioned stress scenarios by family and severity (macro, borrower, collateral, rating, project) with source and maker-checker (moved out of params/v1/stress_scenarios.json).

- File: `data/dealdesk/dd-saudi-v1/dd_stress_scenario.parquet`
- Keys: scenario_id, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per scenario version
- Owner: D · Writers: D (editor) via publish(); E seed

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `scenario_id` | text |  | Scenario id (scenario id). |
| `version` | int |  | Scenario version. |
| `family` | text |  | macro, borrower, collateral, rating, project, combined or custom. |
| `severity` | text |  | mild, moderate or severe (combined for the combined case). |
| `label` | text |  | Scenario name. |
| `scope` | text |  | bank or deal. |
| `proposal_id` | text |  | Deal, for deal-scope scenarios. |
| `shocks_json` | json |  | The shocks as an object (e.g. {"oil_pct": -30, "notches": 2}). |
| `source` | text |  | seed, icaap, sama, cbuae, cbo or user. |
| `owner` | text |  | Owner of this row's value. |
| `status` | text |  | draft, approved or retired. |
| `maker` | text |  | Maker (maker). |
| `checker` | text |  | Checker (blank until approved). |
| `effective_date` | date |  | Effective date. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_stress_sensitivity` — Stress sensitivities

Sector sensitivities of revenue to macro drivers, versioned, with method, confidence band and source (T).

- File: `data/dealdesk/dd-saudi-v1/dd_stress_sensitivity.parquet`
- Keys: sensitivity_id, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per sector, driver and version
- Owner: T · Writers: T via publish(); E seed from stress_scenarios.json

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `sensitivity_id` | text |  | Sensitivity id (sector:driver). |
| `version` | int |  | Version of this row's object. |
| `sector` | text |  | Sector of the obligor. |
| `driver` | text |  | oil, non_oil_gdp, rates, fixed_cost_share, largest_customer_share, project_share. |
| `beta` | float |  | Sensitivity (revenue % change per 1% driver change, or the share). |
| `band_low` | float |  | Lower confidence bound (blank for expert values). |
| `band_high` | float |  | Upper confidence bound. |
| `method` | text |  | expert or regression. |
| `n_obs` | int | count | Observations (regression). |
| `r2` | float |  | R-squared (regression). |
| `source` | text |  | Where the value came from. |
| `owner` | text |  | Owner of this row's value. |
| `effective_date` | date |  | Effective date. |
| `model_card_ref` | text |  | Model card reference. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_stress_result` — Stress results

Stressed outcome of each scenario on each deal: the chain from shock to RAROC, and what breaks.

- File: `data/dealdesk/dd-saudi-v1/dd_stress_result.parquet`
- Keys: result_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal, scenario and run
- Owner: D · Writers: D via publish()

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `result_id` | text |  | Result id (result id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `run_id` | text |  | Run id (one per Stress Lab run). |
| `scenario_id` | text |  | Scenario id (dd_stress_scenario). |
| `scenario_version` | int |  | Scenario version. |
| `family` | text |  | Family of the scenario. |
| `severity` | text |  | Severity of the scenario. |
| `applicable_flag` | flag |  | 0 when the scenario does not apply to this deal (shown 'not applicable'). |
| `revenue_change_pct` | float | % | Revenue change. |
| `ebitda_mn` | float | million (deal currency, SAR) | Stressed EBITDA. |
| `dscr_x` | float | x | Stressed DSCR. |
| `leverage_x` | float | x | Stressed debt / EBITDA. |
| `ltv_pct` | float | % | Stressed LTV (blank without collateral). |
| `rating` | text |  | Stressed rating. |
| `pd_12m` | float | probability (0-1) | Stressed 12-month PD. |
| `stage` | int |  | Stressed IFRS 9 stage. |
| `ecl_mn` | float | million (deal currency, SAR) | Stressed ECL. |
| `raroc_pct` | float | % | Stressed lifetime RAROC (repriced at the stressed rating, O4). |
| `covenant_breach_flag` | flag |  | 1 when a covenant breaks. |
| `breaks` | text |  | What breaks, separated by semicolons (dscr, covenant, stage2, hurdle, limit). |
| `run_at` | ts |  | When run (run at). |
| `param_version` | text |  | Parameter version. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_swot` — SWOT

Strengths, weaknesses, opportunities and threats per deal, each with its evidence and, for weaknesses, the mitigant that answers it (I24).

- File: `data/dealdesk/dd-saudi-v1/dd_swot.parquet`
- Keys: swot_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per SWOT point
- Owner: C · Writers: C via publish(); E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `swot_id` | text |  | Point id (swot id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `quadrant` | text |  | S, W, O or T. |
| `kind` | text |  | financial or qualitative. |
| `topic` | text |  | management, ownership, governance, track_record, conduct, market_position, concentration, geopolitics, leverage, liquidity, profitability, collateral … |
| `text` | text |  | The point, with its number. |
| `evidence_relation` | text |  | Relation of the evidence. |
| `evidence_key` | text |  | Key of the evidence row. |
| `finding_id` | text |  | Finding behind it (dd_review_finding). |
| `mitigant_text` | text |  | Structure or condition that answers a weakness. |
| `mitigant_ref` | text |  | Condition or limit id of the mitigant. |
| `covered_flag` | flag |  | 1 when a weakness is covered by a mitigant (uncovered shows red). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_promise` — Promises

Cross-sell and business-routing commitments from approved deals, measured against the account data (I8).

- File: `data/dealdesk/dd-saudi-v1/dd_promise.parquet`
- Keys: promise_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per commitment
- Owner: I · Writers: I via publish(); E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `promise_id` | text |  | Promise id (promise id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `obligor_id` | text |  | Obligor id (obligor id). |
| `kind` | text |  | routing, deposits, cross_sell, payroll, fx, trade. |
| `text` | text |  | The undertaking as approved. |
| `promised_mn` | float | million (deal currency, SAR) | Promised amount (per year). |
| `multiple_of_limit` | float | x | Promised multiple of the limit (routing undertakings). |
| `delivered_mn` | float | million (deal currency, SAR) | Delivered over the measurement window. |
| `delivered_pct` | float | % | Delivered as % of promised. |
| `window_from` | date |  | Measurement window start. |
| `window_to` | date |  | Measurement window end. |
| `measure_relation` | text |  | Relation it is measured from (dd_account_conduct, dep_month …). |
| `status` | text |  | met, partly_met, unmet or open. |
| `committee_ref` | text |  | Committee decision that took the promise. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_raroc_drift` — RAROC drift

RAROC at origination against now per booked facility, with the drift attribution (I7, I8).

- File: `data/dealdesk/dd-saudi-v1/dd_raroc_drift.parquet`
- Keys: drift_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per facility
- Owner: I · Writers: I via publish()

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `drift_id` | text |  | Row id (drift id). |
| `facility_id` | text |  | Facility name. |
| `proposal_id` | text |  | Deal it was approved under (blank for back book). |
| `obligor_id` | text |  | Obligor id (obligor id). |
| `origination_date` | date |  | Origination date. |
| `raroc_orig_pct` | float | % | RAROC at origination. |
| `raroc_now_pct` | float | % | RAROC now (raroc now pct). |
| `hurdle_pct` | float | % | Hurdle rate (hurdle pct). |
| `drift_pp` | float | pp | Now minus origination. |
| `attr_pd_pp` | float | pp | Drift from PD migration. |
| `attr_lgd_pp` | float | pp | Drift from LGD. |
| `attr_funding_pp` | float | pp | Drift from funding cost. |
| `attr_fees_pp` | float | pp | Drift from fees. |
| `attr_utilisation_pp` | float | pp | Drift from utilisation. |
| `attr_cross_sell_pp` | float | pp | Drift from unrealised cross-sell. |
| `renewal_date` | date |  | Next renewal. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_policy` — Policy library

Every credit policy uploaded or seeded, with version, effective date and uploader (I3).

- File: `data/dealdesk/dd-saudi-v1/dd_policy.parquet`
- Keys: policy_id, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per policy version
- Owner: G · Writers: G via publish(); E seed

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `policy_id` | text |  | Policy id (policy id). |
| `version` | int |  | Version of this row's object. |
| `title` | text |  | Title of the policy. |
| `effective_date` | date |  | Effective date. |
| `uploaded_by` | text |  | Uploaded by (uploaded by). |
| `uploaded_at` | ts |  | Uploaded at (uploaded at). |
| `status` | text |  | active, superseded, rejected or trial (a trial-only version, I18). |
| `source_file` | text |  | Original file reference. |
| `docx_file` | text |  | Word (.docx) rendition reference. |
| `clauses_n` | int | count | Number of clauses learned. |
| `summary` | text |  | One-line summary. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_policy_clause` — Policy clauses

The clauses of each policy version, with the parameter or rule each sets.

- File: `data/dealdesk/dd-saudi-v1/dd_policy_clause.parquet`
- Keys: policy_id, version, clause, reporting_quarter · Period: `reporting_quarter` · Grain: one row per clause
- Owner: G · Writers: G via publish(); E seed

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `policy_id` | text |  | Policy id (dd_policy). |
| `version` | int |  | Policy version. |
| `clause` | text |  | Clause number. |
| `heading` | text |  | Clause heading. |
| `quote` | text |  | Clause text (short quote). |
| `sets_table` | text |  | Parameter table it sets (blank when none). |
| `sets_key` | text |  | Parameter key it sets. |
| `sets_value` | text |  | Value it sets. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_parameter_provenance` — Parameter provenance

The provenance columns of dd_parameter (I4): the policy, version and clause that set each value, or the manual owner and date. Joins dd_parameter on (table_name, param_key).

- File: `data/dealdesk/dd-saudi-v1/dd_parameter_provenance.parquet`
- Keys: table_name, param_key, reporting_quarter · Period: `reporting_quarter` · Grain: one row per parameter value
- Owner: G · Writers: G via publish(); E seed

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `table_name` | text |  | Parameter table. |
| `param_key` | text |  | Parameter key. |
| `param_version` | text |  | Parameter table version. |
| `source_kind` | text |  | policy, manual or seed. |
| `policy_id` | text |  | Policy (when source_kind = policy). |
| `policy_version` | int |  | Policy version. |
| `clause` | text |  | Clause of the policy. |
| `quote` | text |  | Clause quote. |
| `set_by` | text |  | Owner who set the value. |
| `set_on` | date |  | Date set (set on). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_facility_limit` — Facility limit tree

The multi-limit facility table of the bank-form proposal (anatomy §2.3): general limit, project limits and sub-limits with existing, outstanding and proposed amounts, cash margin, pricing with floor, tenor.

- File: `data/dealdesk/dd-saudi-v1/dd_facility_limit.parquet`
- Keys: proposal_id, limit_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per limit or sub-limit
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `limit_id` | text |  | Limit id (unique within the deal). |
| `parent_limit_id` | text |  | Parent limit (blank for a top limit). |
| `level` | int |  | 0 total / umbrella, 1 limit, 2 sub-limit. |
| `seq` | int |  | Display order. |
| `limit_name` | text |  | Name as on the proposal. |
| `product_code` | text |  | BB bid bond, APG, PB, RB, LC_SIGHT, LC_USANCE, LCM, DMCCM_PC, DMCCM_SUP, OD, TL, RCF, TR, LG, LG_CASH, VHM, ESCROW_TL, SYND_TL, SME_TL. |
| `funded_flag` | flag |  | 1 funded, 0 non-funded. |
| `currency` | text |  | Currency of the amounts. |
| `existing_mn` | float | million (deal currency, SAR) | Existing limit. |
| `outstanding_mn` | float | million (deal currency, SAR) | Outstanding (utilised). |
| `proposed_mn` | float | million (deal currency, SAR) | Proposed limit. |
| `cash_margin_pct` | float | % | Cash margin (cash margin pct). |
| `commission_pct_pa` | float | % p.a. | Commission (non-funded). |
| `benchmark` | text |  | Profit benchmark (e.g. 3M SAIBOR). |
| `spread_pct` | float | % | Spread over the benchmark. |
| `floor_pct` | float | % | Profit-rate floor. |
| `tenor_text` | text |  | Tenor and validity. |
| `repayment_text` | text |  | Repayment (repayment text). |
| `project_id` | text |  | Project the limit is dedicated to (dd_project). |
| `interchangeable_flag` | flag |  | 1 when interchangeable within its parent. |
| `particulars` | text |  | Other particulars. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_security` — Security and support

Security and support per limit group with perfection status, deadline and legal-opinion date (anatomy §2.4; collateral and legal review).

- File: `data/dealdesk/dd-saudi-v1/dd_security.parquet`
- Keys: proposal_id, security_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per security item
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `security_id` | text |  | Item id (security id). |
| `limit_id` | text |  | Limit it secures, or ALL. |
| `kind` | text |  | personal_guarantee, corporate_guarantee, security_cheque, assignment_receivables, assignment_insurance, assignment_project_proceeds, hypothecation, subordination, mortgage, cash_margin, pledge_shares, noc, undertaking. |
| `provider` | text |  | Provider (guarantor, assignor). |
| `provider_entity_id` | text |  | Provider's entity or person id (b360_entity / b360_shareholder). |
| `amount_mn` | float | million (deal currency, SAR) | Amount covered (blank when unlimited). |
| `currency` | text |  | Currency of the amounts. |
| `net_worth_mn` | float | million (deal currency, SAR) | Guarantor's declared net worth. |
| `net_worth_statement_date` | date |  | Date of the net-worth statement. |
| `perfection_status` | text |  | perfected, pending, not_perfected or not_applicable. |
| `perfection_deadline` | date |  | Deadline to perfect. |
| `legal_opinion_date` | date |  | Date of the legal opinion on enforceability. |
| `valuation_date` | date |  | Valuation date (collateral). |
| `value_mn` | float | million (deal currency, SAR) | Market value (collateral). |
| `insurance_expiry` | date |  | Insurance expiry (collateral). |
| `pari_passu_flag` | flag |  | 1 when pari passu with other banks. |
| `existing_flag` | flag |  | 1 already held, 0 new. |
| `note` | text |  | Free-text note on this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_tnc` — Terms and conditions

The numbered terms and conditions per limit group (anatomy §2.5), with the status of existing conditions.

- File: `data/dealdesk/dd-saudi-v1/dd_tnc.parquet`
- Keys: proposal_id, tnc_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per numbered term
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `tnc_id` | text |  | Term id (tnc id). |
| `limit_id` | text |  | Limit group, or ALL. |
| `seq` | int |  | Number within the limit group. |
| `category` | text |  | utilisation, cap, purpose, disbursement, settlement, cover_ratio, reporting, routing, auditor, existing_condition. |
| `text` | text |  | The term (text). |
| `existing_status` | text |  | new, complied or not_complied (existing terms). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_group_exposure` — Group exposure

Group exposure with the bank per entity, funded and total, before and after the proposal (anatomy §2.6).

- File: `data/dealdesk/dd-saudi-v1/dd_group_exposure.parquet`
- Keys: proposal_id, entity_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per group entity
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `group_id` | text |  | Group id (group id). |
| `entity_id` | text |  | Entity (b360_entity). |
| `entity_name` | text |  | Entity name (entity name). |
| `funded_existing_mn` | float | million (deal currency, SAR) | Funded limits today. |
| `total_existing_mn` | float | million (deal currency, SAR) | Total limits today. |
| `funded_proposed_mn` | float | million (deal currency, SAR) | Funded limits proposed. |
| `total_proposed_mn` | float | million (deal currency, SAR) | Total limits proposed. |
| `outstanding_mn` | float | million (deal currency, SAR) | Outstanding today. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_reference` — References and limit history

Committee decisions, credit file requests, revisions and emails cited by a proposal, with the limit history.

- File: `data/dealdesk/dd-saudi-v1/dd_reference.parquet`
- Keys: proposal_id, ref_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per reference
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `ref_id` | text |  | Reference id. |
| `kind` | text |  | committee_decision, credit_file_request, revision, email, limit_history. |
| `ref_no` | text |  | Reference number (fictional). |
| `ref_date` | date |  | Date of the event. |
| `authority` | text |  | Approving authority (committee decisions). |
| `amount_mn` | float | million (deal currency, SAR) | Total limits approved (limit history). |
| `group_cap_mn` | float | million (deal currency, SAR) | Group cap approved (limit history). |
| `text` | text |  | What it says. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_account_conduct` — Account conduct

Relationship conduct of the R12 fictional obligors: credit turnover, average balance, limit utilisation, past dues and returned cheques by month. Book obligors read the Deposits domain (dep_month) instead.

- File: `data/dealdesk/dd-saudi-v1/dd_account_conduct.parquet`
- Keys: obligor_id, month, reporting_quarter · Period: `reporting_quarter` · Grain: one row per obligor per month
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `obligor_id` | text |  | Obligor id (obligor id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `month` | text |  | Calendar month, YYYY-MM. |
| `credit_turnover_mn` | float | million (deal currency, SAR) | Credit turnover (inflows) in the month. |
| `debit_turnover_mn` | float | million (deal currency, SAR) | Debit turnover. |
| `avg_balance_mn` | float | million (deal currency, SAR) | Average credit balance. |
| `limits_mn` | float | million (deal currency, SAR) | Total limits. |
| `utilised_mn` | float | million (deal currency, SAR) | Average utilisation. |
| `utilisation_pct` | float | % | Utilisation of limits. |
| `past_due_days_max` | int | days | Worst days past due in the month. |
| `past_due_mn` | float | million (deal currency, SAR) | Amount past due at month end. |
| `returned_cheques_n` | int | count | Cheques returned unpaid in the month. |
| `returned_cheques_mn` | float | million (deal currency, SAR) | Value of cheques returned. |
| `routed_business_mn` | float | million (deal currency, SAR) | Business routed through the bank (trade and collections) in the month. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_returned_cheque` — Returned cheques

Each cheque returned unpaid on the R12 fictional obligors' accounts, with reason.

- File: `data/dealdesk/dd-saudi-v1/dd_returned_cheque.parquet`
- Keys: cheque_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per returned cheque
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `cheque_id` | text |  | Cheque event id. |
| `obligor_id` | text |  | Account holder. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `return_date` | date |  | Date returned. |
| `amount_mn` | float | million (deal currency, SAR) | Amount of the cheque. |
| `reason` | text |  | insufficient_funds, signature, stopped, technical. |
| `regularised_flag` | flag |  | 1 when later paid. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_customer_account` — Customer accounts (R16)

R16 d: every current and deposit account the Bank holds for the R16 customers' groups (Borrower 360 and the existing-customer pull on Deal Desk): balance at the as-of date, 12-month average balance and turnover.

- File: `data/dealdesk/dd-saudi-v1/dd_customer_account.parquet`
- Keys: account_no, reporting_quarter · Period: `reporting_quarter` · Grain: one row per account
- Owner: R16-d · Writers: R16 d (ops/r16_seed_customers.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `account_no` | text |  | Account number (fictional). |
| `iban` | text |  | IBAN (fictional). |
| `obligor_id` | text |  | Account holder: book borrower id (CB…) or group entity id (XE-…). |
| `proposal_id` | text |  | Deal (customer file) the account is read for. |
| `bank_name` | text |  | Bank (the Bank itself). |
| `account_type` | text |  | current or deposit. |
| `label` | text |  | Account name as shown (e.g. 'Cash-margin deposit (LGs)'). |
| `currency` | text |  | Currency of the amounts. |
| `opened` | date |  | Date opened (opened). |
| `as_of` | date |  | Balance date. |
| `balance_mn` | float | million (deal currency, SAR) | Balance at the as-of date. |
| `avg_balance_12m_mn` | float | million (deal currency, SAR) | Average balance over the last 12 months. |
| `credits_12m_mn` | float | million (deal currency, SAR) | Credits (inflows) over the last 12 months. |
| `debits_12m_mn` | float | million (deal currency, SAR) | Debits (outflows) over the last 12 months. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_business_profile` — Business profile

The background facts of the bank-form proposal (anatomy §2.7, §2.16): activity mix, sales terms (PDC / LC / open account), purchase terms, main suppliers and customers, and the effects of the geopolitical and market situation, each with its attribution (as per business, audited, verified).

- File: `data/dealdesk/dd-saudi-v1/dd_business_profile.parquet`
- Keys: proposal_id, item_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per profile item
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `item_id` | text |  | Item id (item id). |
| `entity_id` | text |  | Entity it describes (b360_entity). |
| `item_kind` | text |  | activity_mix, sales_terms, purchase_terms, top_customer, top_supplier, geopolitical, market, staff. |
| `label` | text |  | What the item is (e.g. 'Steel and rebar', 'Post-dated cheques', 'Red Sea shipping routes'). |
| `share_pct` | float | % | Share of revenue, sales or purchases. |
| `value_mn` | float | million (deal currency, SAR) | Amount, when given. |
| `year` | int |  | Financial year the share refers to. |
| `text` | text |  | The fact in proposal voice. |
| `attribution` | text |  | as_per_business, audited, verified, not_provided. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_financials_detail` — Financials detail

Extends dd_obligor_financials (joined on proposal_id and year): audited and interim statements per entity and scope with auditor, opinion and qualification basis, the full P&L and balance-sheet lines, receivables ageing and concentration, related-party balances, intangibles and shareholder accounts.

- File: `data/dealdesk/dd-saudi-v1/dd_financials_detail.parquet`
- Keys: proposal_id, entity_id, period_label, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal, entity and period
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `entity_id` | text |  | Entity (subject, combined group or parent). |
| `entity_name` | text |  | Entity name (entity name). |
| `entity_scope` | text |  | standalone, branch, combined or consolidated. |
| `period_label` | text |  | FY2023, FY2024, FY2025, 6M2026 … |
| `year` | int |  | Financial year (joins dd_obligor_financials.year). |
| `period_kind` | text |  | audited, interim or projection. |
| `period_end` | date |  | Period end date. |
| `months` | int | months | Months in the period. |
| `currency` | text |  | Currency of the amounts. |
| `auditor` | text |  | Auditor (fictional). |
| `auditor_panel` | text |  | listed (on the bank's approved panel) or unlisted. |
| `opinion` | text |  | clean, qualified, adverse, disclaimer or unaudited. |
| `qualification_basis` | text |  | Basis of qualification, summarised. |
| `revenue_mn` | float | million (deal currency, SAR) | Revenue for the period. |
| `gross_profit_mn` | float | million (deal currency, SAR) | Gross profit for the period. |
| `operating_profit_mn` | float | million (deal currency, SAR) | Operating profit. |
| `net_profit_mn` | float | million (deal currency, SAR) | Net profit for the period. |
| `ebitda_mn` | float | million (deal currency, SAR) | EBITDA for the period. |
| `finance_cost_mn` | float | million (deal currency, SAR) | Finance cost. |
| `total_assets_mn` | float | million (deal currency, SAR) | Total assets. |
| `current_assets_mn` | float | million (deal currency, SAR) | Current assets. |
| `cash_mn` | float | million (deal currency, SAR) | Cash and bank. |
| `receivables_mn` | float | million (deal currency, SAR) | Trade receivables (net). |
| `retention_receivables_mn` | float | million (deal currency, SAR) | Retention receivables. |
| `contract_assets_mn` | float | million (deal currency, SAR) | Contract assets / unbilled work. |
| `inventory_mn` | float | million (deal currency, SAR) | Inventory at period end. |
| `due_from_related_mn` | float | million (deal currency, SAR) | Due from related parties. |
| `current_liabilities_mn` | float | million (deal currency, SAR) | Current liabilities. |
| `due_to_related_mn` | float | million (deal currency, SAR) | Due to related parties. |
| `intangibles_mn` | float | million (deal currency, SAR) | Intangible assets and goodwill. |
| `shareholder_accounts_mn` | float | million (deal currency, SAR) | Shareholders' current accounts (in equity or receivable). |
| `noncore_investments_mn` | float | million (deal currency, SAR) | Non-core investments (property, associates). |
| `bank_debt_st_mn` | float | million (deal currency, SAR) | Short-term bank debt. |
| `bank_debt_lt_mn` | float | million (deal currency, SAR) | Long-term bank debt. |
| `total_liabilities_mn` | float | million (deal currency, SAR) | Total liabilities. |
| `net_worth_mn` | float | million (deal currency, SAR) | Tangible-unadjusted net worth as reported. |
| `contingent_liabilities_mn` | float | million (deal currency, SAR) | Contingent liabilities (LGs and LCs outstanding). |
| `operating_cash_flow_mn` | float | million (deal currency, SAR) | Cash flow from operations. |
| `cash_cycle_days` | int | days | Cash conversion cycle. |
| `ageing_0_90_mn` | float | million (deal currency, SAR) | Receivables aged 0-90 days. |
| `ageing_91_180_mn` | float | million (deal currency, SAR) | Receivables aged 91-180 days. |
| `ageing_181_365_mn` | float | million (deal currency, SAR) | Receivables aged 181-365 days. |
| `ageing_over_365_mn` | float | million (deal currency, SAR) | Receivables aged over 365 days. |
| `top1_receivable_pct` | float | % | Largest debtor share of receivables. |
| `top2_receivable_pct` | float | % | Top 2 debtors' share of receivables. |
| `top5_receivable_pct` | float | % | Top 5 debtors' share of receivables. |
| `backlog_mn` | float | million (deal currency, SAR) | Order backlog (contractors). |
| `staff_count` | int | count | Staff count (staff count). |
| `source` | text |  | Source document (audited FS, interim management accounts, projections as per business). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_scenario_calibration` — Scenario severity calibration

Mild, moderate and severe for every stress driver, from the empirical distribution of its one-year move (mild P75, moderate P92 within P90-P93, severe max(P96, worst observed episode)), with the observed frequency, the rule-of-thumb cross-check, and the labelled expert fallback when the data cannot support a severity (PLAN_R13 §S.1).

- File: `data/dealdesk/dd-saudi-v1/dd_scenario_calibration.parquet`
- Keys: driver, severity, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per driver, severity and version
- Owner: S · Writers: R13 S (backend/scenarios/publish.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `driver` | text |  | Driver key (brent, gdp_real, gdp_nonoil, saibor, sector_cycle, pd_multiplier, revenue, margin, rating, utilisation, collateral, re_price, lgd, customer, payment_delay, project_delay). |
| `severity` | text |  | mild, moderate or severe. |
| `version` | int |  | Calibration version (1 = engine r13-s1). |
| `label` | text |  | Driver name and the adverse move it measures. |
| `unit` | text |  | Unit of the adverse move (%, pp, bps, sd, x, notches, days, months, share). |
| `value` | float |  | The severity in force (adverse direction, in the driver's unit). |
| `method` | text |  | empirical (percentile of history) or fallback (labelled expert value). |
| `percentile` | text |  | The rule that gave the value (P75, P92, max(P96, worst episode), or the fallback label). |
| `estimate` | float |  | The empirical estimate at this severity (kept beside a fallback; blank when no data). |
| `n_obs` | int | count | Observed one-year moves used (overlapping quarterly windows for bank history). |
| `n_independent` | int | count | Independent (non-overlapping) one-year observations; fewer than 15 forces the fallback. |
| `freq_count` | int | count | Observations at least this adverse. |
| `freq_share` | float |  | Share of observations at least this adverse (0-1). |
| `freq_labels` | json |  | The years (or sector quarters) at least this adverse, most recent last (up to 12). |
| `worst_episode` | text |  | The worst observed episode and its move. |
| `window` | text |  | Data window of the distribution. |
| `source` | text |  | The relation(s) the distribution is read from. |
| `fallback_reason` | text |  | Why the data cannot support the severity (blank when empirical). |
| `rule_check` | text |  | Cross-check against the rule of thumb: mild 10-20% beyond the average adverse move. |
| `engine_version` | text |  | Scenario engine version. |
| `fingerprint` | text |  | Hash of the input files and the engine code that produced the row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_scenario_joint` — Joint macro scenarios

Joint macro scenarios (Gaussian copula on the observed rank correlation, and the historical analogues 2009, 2015, 2016, 2020): the drivers move together as they did in history; the independent tails are kept for comparison only.

- File: `data/dealdesk/dd-saudi-v1/dd_scenario_joint.parquet`
- Keys: scenario_id, driver, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per joint scenario, driver and version
- Owner: S · Writers: R13 S (backend/scenarios/publish.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `scenario_id` | text |  | joint_mild, joint_moderate, joint_severe, analogue_<year> or independent_<severity>. |
| `driver` | text |  | brent, gdp_real, gdp_nonoil or saibor. |
| `version` | int |  | Version (1 = engine r13-s1). |
| `kind` | text |  | copula, analogue or independent. |
| `severity` | text |  | mild, moderate or severe (blank for an analogue). |
| `value` | float |  | The driver's adverse one-year move in this scenario. |
| `unit` | text |  | Unit of the move (%, pp, bps). |
| `composite_percentile` | float |  | Percentile of the scenario on the composite stress index (0-1). |
| `basis` | text |  | How the scenario was formed. |
| `engine_version` | text |  | Scenario engine version. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_satellite_model` — Satellite models

Sector PD and Stage 1 to 2 migration on the macro drivers (pooled sector x quarter panel, sector effects, ridge), with standard errors clustered by quarter, fit, n and the out-of-sample error.

- File: `data/dealdesk/dd-saudi-v1/dd_satellite_model.parquet`
- Keys: model, term, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per model, term and version
- Owner: S · Writers: R13 S (backend/scenarios/publish.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `model` | text |  | pd (probit of the sector's 12-month PD) or migration (logit of the quarterly Stage 1 to 2 rate). |
| `term` | text |  | const, sector:<name>, or a macro driver (brent_yoy, gdp_real, gdp_nonoil, saibor_3m). |
| `version` | int |  | Version (1 = engine r13-s1). |
| `estimate` | float |  | Coefficient (per unit of the driver; sector effects on the y scale). |
| `std_error` | float |  | Cluster-robust standard error (by quarter; blank for sector effects). |
| `band_low` | float |  | Lower end of the 90% band. |
| `band_high` | float |  | Upper end of the 90% band. |
| `identified_flag` | flag |  | 1 when the sign is as expected and the 90% band excludes zero (used in translation). |
| `note` | text |  | Why the term is or is not used. |
| `n_obs` | int | count | Sector-quarters in the fit. |
| `r2` | float |  | R-squared (overall). |
| `r2_within` | float |  | R-squared within sector. |
| `lambda` | float |  | Ridge penalty on the macro terms (leave-one-year-out cross-validation). |
| `oos_rmse` | float |  | Out-of-sample RMSE on the last four quarters (bps of PD, or pp of migration). |
| `oos_rmse_naive` | float |  | The same for the naive forecast (last in-sample value held). |
| `window` | text |  | Estimation window. |
| `engine_version` | text |  | Scenario engine version. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_scenario_result` — Scenario results (corporate book)

The corporate book under the calibrated joint scenarios: ECL, Stage 2, PD, RWA and capital, by severity and sector (sector * = the book), with the 90% band from the satellite coefficients.

- File: `data/dealdesk/dd-saudi-v1/dd_scenario_result.parquet`
- Keys: severity, sector, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per severity, sector and version
- Owner: S · Writers: R13 S (backend/scenarios/publish.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `severity` | text |  | mild, moderate or severe. |
| `sector` | text |  | Sector, or * for the whole book. |
| `version` | int |  | Version (1 = engine r13-s1). |
| `ead_mn` | float | SAR million | EAD at the start. |
| `ecl_start_mn` | float | SAR million | Reported ECL at the start. |
| `ecl_stressed_mn` | float | SAR million | ECL under the scenario. |
| `ecl_change_mn` | float | SAR million | ECL change (ecl change mn). |
| `ecl_change_low_mn` | float | SAR million | ECL change, low end of the 90% band (book row only). |
| `ecl_change_high_mn` | float | SAR million | ECL change, high end of the 90% band (book row only). |
| `pd_start` | float |  | EAD-weighted 12-month PD of performing exposure at the start (0-1). |
| `pd_stressed` | float |  | The same under the scenario (0-1). |
| `stage2_share_start` | float |  | Stage 2 share of EAD at the start (0-1). |
| `stage2_share_stressed` | float |  | Stage 2 share of EAD under the scenario (0-1). |
| `rwa_change_mn` | float | SAR million | RWA change (book row only). |
| `capital_impact_mn` | float | SAR million | ECL change plus 15% of the RWA change (book row only). |
| `as_of` | text |  | Book quarter the scenario starts from. |
| `engine_version` | text |  | Scenario engine version. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_macro_regime` — Current macro regime

The current-regime block every scenario answer opens with (R14 K12): the latest Brent price (dated), its 3- and 12-month change, the percentile of the level over 35 years of EIA monthly averages, the latest real GDP, non-oil GDP, CPI and PMI vintages, the regime label and rule, and the oil reversal sizes measured on the post-spike reversals (2008-09, 2014-15, 2022-23).

- File: `data/dealdesk/dd-saudi-v1/dd_macro_regime.parquet`
- Keys: measure, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per measure and version
- Owner: m · Writers: R14 m (backend/scenarios/regime.py, revenue.py; backend/whatif_v5/backtest.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `measure` | text |  | brent_latest, brent_change_3m, brent_change_12m, brent_percentile_35y, pre_shock_level, gdp_real, gdp_nonoil, cpi, gdp_real_quarter, pmi_nonoil, reversal_mild, reversal_moderate, reversal_severe, regime. |
| `version` | int |  | Version (1 = R14 m). |
| `value` | float |  | The measure's value (blank for the regime row). |
| `unit` | text |  | Unit (USD/bbl, %, % y/y, percentile, index). |
| `as_of` | text |  | Date or period the value refers to. |
| `label` | text |  | The measure in plain words. |
| `regime` | text |  | Regime key (supply_shock_high_oil, high_oil_rising, high_oil, oil_slump, low_oil, normal). |
| `regime_label` | text |  | Regime in plain words. |
| `source` | text |  | Publisher of the figure. |
| `source_url` | text |  | URL of the figure. |
| `vintage` | text |  | Vintage (e.g. IMF WEO October 2026, EIA STEO 2026-10-06). |
| `relation` | text |  | The store relation the figure is read from (whatif.mev_latest, whatif.brent_monthly_eia, whatif.mev_annual). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_revenue_channel` — Revenue channel by sector

Is the book's stress coming from falling revenue (R14 K12 (3))? Account credit turnover (deposits.dep_month, last three months against a year earlier) and reported revenue (cockpit.corp_borrower_quarter, latest quarter against a year earlier) by sector, with the sector's EAD and the revenue shock the recommender offers.

- File: `data/dealdesk/dd-saudi-v1/dd_revenue_channel.parquet`
- Keys: sector, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per sector and version
- Owner: m · Writers: R14 m (backend/scenarios/regime.py, revenue.py; backend/whatif_v5/backtest.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `sector` | text |  | Sector of the obligor. |
| `version` | int |  | Version (1 = R14 m). |
| `ead_mn` | float | SAR million | Sector EAD in the latest quarter. |
| `ead_share_pct` | float | % | Share of the book's EAD. |
| `turnover_yoy_pct` | float | % | Credit turnover on the sector's accounts, last 3 months against the same months a year earlier. |
| `borrowers_down_pct` | float | % | Share of the sector's borrowers whose turnover fell at least 10%. |
| `reported_revenue_yoy_pct` | float | % | Reported revenue, latest quarter against the same quarter a year earlier. |
| `gap_pp` | float | pp | Reported revenue growth minus turnover growth (positive: the financials lag the accounts). |
| `falling_flag` | flag |  | 1 when turnover fell at least 10%. |
| `shock_mild_pct` | float | % | Revenue shock offered, mild (the measured fall). |
| `shock_moderate_pct` | float | % | Revenue shock offered, moderate (1.5x). |
| `shock_severe_pct` | float | % | Revenue shock offered, severe (2x, capped at 60%). |
| `window` | text |  | Turnover and revenue windows. |
| `revenue_led_flag` | flag |  | 1 when the book's stress comes from revenue (the falling sectors hold at least 15% of EAD). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `whatif_mev_annual` — What-If MEV (Saudi macro, annual)

The Saudi macroeconomic variables the What-If engine, the scenario engine and the Deal Desk forward-looking PD read (data/whatif_v5/mev/mev_annual.csv): history and IMF projections with the source, URL, vintage (IMF WEO October 2026 where refreshed in R14) and retrieval date of every row (K13).

- File: `data/dealdesk/dd-saudi-v1/whatif_mev_annual.parquet`
- Keys: series, year, kind, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per series, year, kind and version
- Owner: m · Writers: R14 m (backend/scenarios/regime.py, revenue.py; backend/whatif_v5/backtest.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `series` | text |  | gdp_real, gdp_nonoil, brent, cpi, unemployment, repo, saibor_3m, gov_spend, re_price, current_account, credit_growth. |
| `year` | int |  | Calendar year. |
| `kind` | text |  | history or projection. |
| `version` | int |  | Version (1 = R14 m). |
| `value` | float |  | The published value in the series' unit. |
| `unit` | text |  | Unit (unit). |
| `source` | text |  | Publisher and table. |
| `source_url` | text |  | URL of the figure. |
| `vintage` | text |  | Vintage (e.g. IMF WEO October 2026). |
| `retrieved` | text |  | Date the figure was retrieved. |
| `note` | text |  | How the figure was obtained (official page, press report of the IMF table, derived). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `whatif_mev_latest` — What-If MEV (latest dated observations)

The dated observations the current-regime block reads (data/whatif_v5/mev/latest_observations.csv): Brent spot, EIA STEO, GASTAT flash GDP and CPI, the non-oil PMI, the MoF deficit and the dated market context.

- File: `data/dealdesk/dd-saudi-v1/whatif_mev_latest.parquet`
- Keys: series, date, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per series, date and version
- Owner: m · Writers: R14 m (backend/scenarios/regime.py, revenue.py; backend/whatif_v5/backtest.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `series` | text |  | brent_spot, brent_spot_yoy_pct, brent_eia_quarter, brent_eia_year, brent_eia_month, gdp_real_q_yoy, gdp_nonoil_q_yoy, gdp_oil_q_yoy, cpi_m_yoy, pmi_nonoil, fiscal_balance_mof, context. |
| `date` | text |  | Date the value refers to (YYYY-MM-DD). |
| `version` | int |  | Version (1 = R14 m). |
| `value` | float |  | Value (blank for the context row). |
| `unit` | text |  | Unit (unit). |
| `frequency` | text |  | daily, monthly, quarterly or annual. |
| `kind` | text |  | observation, forecast or context. |
| `source` | text |  | Publisher (source). |
| `source_url` | text |  | URL (source url). |
| `vintage` | text |  | Vintage (vintage). |
| `retrieved` | text |  | Retrieval date. |
| `note` | text |  | Note (the quoted text for the context row). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `whatif_backtest` — What-If accuracy back-test

The What-If ECL estimate (Delta method, the macro moves realised over the quarter) against the full ECL engine's final ECL at the next quarter on the same facilities, for every pair of consecutive quarters (PLAN_R14 §m (7); docs/v5/WHATIF_BACKTEST.md).

- File: `data/dealdesk/dd-saudi-v1/whatif_backtest.parquet`
- Keys: from_quarter, version, reporting_quarter · Period: `reporting_quarter` · Grain: one row per quarter step and version
- Owner: m · Writers: R14 m (backend/scenarios/regime.py, revenue.py; backend/whatif_v5/backtest.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `from_quarter` | text |  | Quarter t the What-If runs from. |
| `to_quarter` | text |  | Quarter t+1 the full engine is read at. |
| `version` | int |  | Version (1 = R14 m). |
| `book` | text |  | corporate (book). |
| `method` | text |  | What-If method (delta). |
| `facilities` | int | count | Facilities present in both quarters. |
| `brent_move_pct` | float | % | Brent quarterly-average move t to t+1 (EIA monthly). |
| `gdp_nonoil_move_pp` | float | pp | Change of the four-quarter-ending non-oil real GDP growth. |
| `saibor_move_bps` | float | bps | Change of the four-quarter-ending 3-month SAIBOR. |
| `ecl_start_mn` | float | SAR million | Full-engine ECL at t. |
| `ecl_start_whatif_mn` | float | SAR million | What-If starting ECL at t (reconciles to the full engine). |
| `ecl_estimate_mn` | float | SAR million | What-If estimate of the ECL at t+1. |
| `ecl_actual_mn` | float | SAR million | Full-engine ECL at t+1, same facilities. |
| `error_mn` | float | SAR million | Estimate minus actual. |
| `error_pct` | float | % | Error as % of the actual. |
| `abs_error_pct` | float | % | Absolute error as % of the actual. |
| `naive_error_mn` | float | SAR million | Naive benchmark (ECL held at t) minus actual. |
| `naive_abs_error_pct` | float | % | Naive absolute error as % of the actual. |
| `beats_naive_flag` | flag |  | 1 when the What-If error is smaller than the naive one. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_structure_set` — Structure set

The structures a deal is judged on (K23, K25): the ask, the recommended structure (the Review counter-proposal), the optimiser's alternatives, the user's own and the stress-proofed ones, each with its base RAROC, SVA (one basis), DSCR, covenant headroom, capacity check and approval authority; the selected structure feeds Stress and Recommendation.

- File: `data/dealdesk/dd-saudi-v1/dd_structure_set.parquet`
- Keys: structure_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal and structure
- Owner: F · Writers: R14 F (backend/dealdesk/stressproof)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `structure_id` | text |  | Structure id: <proposal_id>:<structure_key>. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `structure_key` | text |  | ask, recommended, alternative_n, user_n or proofed_<severity>_n. |
| `label` | text |  | Name shown on the row (Ask, Recommended, Stress-proofed (moderate), ...). |
| `role` | text |  | ask, recommended, alternative, user or stress_proofed. |
| `origin` | text |  | Where the structure came from (client request, Review counter-proposal CP-.., optimiser, user, stress-proof run). |
| `terms_json` | json |  | The engine term set of the structure. |
| `covenants_json` | json |  | Covenant set when it differs from the proposal's (a covenant reset), else blank. |
| `raroc_pct` | float | % | Base lifetime RAROC. |
| `hurdle_pct` | float | % | Hurdle rate (hurdle pct). |
| `sva_mn` | float | million (deal currency, SAR) | SVA on the basis in sva_basis. |
| `sva_basis` | text |  | lifetime or one_year (one basis for every Deal Desk tile, Session E). |
| `dscr_x` | float | x | DSCR after the deal. |
| `covenant_headroom_pct` | float | % | Smallest covenant headroom at base (negative = breached). |
| `capacity_method` | text |  | Capacity method by product (borrowing base, leverage, DSCR). |
| `capacity_mn` | float | million (deal currency, SAR) | Capacity for this product. |
| `capacity_pass_flag` | flag |  | 1 when the funded ask is within capacity. |
| `approval_level` | text |  | Approval authority (one DoA engine). |
| `approval_rule` | text |  | The rule that set the level. |
| `clears_hurdle_flag` | flag |  | 1 when base RAROC clears the hurdle. |
| `hard_breaches` | text |  | Hard limits breached at base, separated by semicolons. |
| `recommendable_flag` | flag |  | 1 when the structure can be recommended (clears the hurdle, no hard breach, within capacity). |
| `not_recommendable_reason` | text |  | Why Recommend is disabled for this structure. |
| `selected_flag` | flag |  | 1 for the structure selected on the deal (one per deal). |
| `created_by` | text |  | User or system. |
| `created_at` | ts |  | When it happened (UTC). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_stress_proof` — Stress-proofing runs

Each stress-proofing run (K23 (4)-(6)): the structure it started from, the target severity, the smallest change set the reverse solver found (amount to capacity, amortisation, cash sweep, covenant reset, receivables assignment, cash margin, margin ratchet, guarantee), whether the result survives, and what it costs in RAROC and SVA.

- File: `data/dealdesk/dd-saudi-v1/dd_stress_proof.parquet`
- Keys: proof_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per stress-proofing run
- Owner: F · Writers: R14 F (backend/dealdesk/stressproof)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proof_id` | text |  | Stress run id. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `from_structure_key` | text |  | Structure the run started from. |
| `new_structure_key` | text |  | Structure it added to the set. |
| `target_severity` | text |  | mild, moderate or severe. |
| `changes_json` | json |  | List of {lever, from, to, text} changes, in the order applied. |
| `survives_flag` | flag |  | 1 when the new structure survives every applicable scenario up to the target severity. |
| `first_break_before` | text |  | What broke first on the starting structure (scenario and test). |
| `raroc_before_pct` | float | % | Base RAROC before. |
| `raroc_after_pct` | float | % | Base RAROC after. |
| `sva_before_mn` | float | million (deal currency, SAR) | SVA before (sva before mn). |
| `sva_after_mn` | float | million (deal currency, SAR) | SVA after (sva after mn). |
| `cost_text` | text |  | What the proofed structure costs the bank and asks of the client. |
| `interpretation` | text |  | The interpreter text (deterministic writer). |
| `regime_label` | text |  | Current macro regime the run was judged in. |
| `sensitivity_version` | text |  | dd_stress_sensitivity version used. |
| `run_by` | text |  | User or system. |
| `run_at` | ts |  | When it happened (UTC). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_monitoring_proposal` — Monitoring proposals

Propose for monitoring (K35): a deal, facility or borrower proposed for a monitoring tier with the reason prefilled from the evidence, review frequency, named triggers, owner and due date; approved or rejected by a checker (maker-checker). Active rows are shown in Early Warning and Borrower 360.

- File: `data/dealdesk/dd-saudi-v1/dd_monitoring_proposal.parquet`
- Keys: monitoring_proposal_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per monitoring proposal
- Owner: F · Writers: R14 F (backend/dealdesk/stressproof)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `monitoring_proposal_id` | text |  | Proposal id (MP-...). |
| `subject_kind` | text |  | deal, facility or borrower. |
| `proposal_id` | text |  | Deal (blank for a book borrower). |
| `obligor_id` | text |  | Obligor or book borrower id (the EWS and Borrower 360 key). |
| `obligor_name` | text |  | Obligor name. |
| `facility_ref` | text |  | Facility or limit id, or ALL. |
| `source_screen` | text |  | deal, going_bad, renewals, book, ews or brief. |
| `tier` | text |  | High, Medium or Standard. |
| `previous_tier` | text |  | Tier before (blank when none). |
| `reason` | text |  | Why (prefilled from the evidence, editable). |
| `evidence_json` | json |  | List of {label, value, relation} evidence items behind the reason. |
| `review_frequency` | text |  | monthly, quarterly, semi_annual or annual. |
| `triggers_json` | json |  | List of {metric, operator, threshold, label} named triggers. |
| `owner` | text |  | Owner of the monitoring. |
| `due_date` | date |  | Date the first review is due. |
| `status` | text |  | proposed, active, rejected or closed. |
| `maker` | text |  | Who proposed. |
| `made_at` | ts |  | When proposed. |
| `checker` | text |  | Who approved or rejected (must differ from the maker). |
| `decided_at` | ts |  | When decided. |
| `decision_note` | text |  | Checker's note. |
| `triggers_hit_json` | json |  | Triggers hit since activation: list of {label, value, at}. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_proposal_quality` — Proposal quality checks

Quality of the RM's proposal (K31/K33), separate from the quality of the deal: completeness against the 20-section bank-form anatomy, accuracy of claims against Data Domains, internal consistency, disclosure, voice and policy/T&C gaps; score by section, evidence and the query to the RM. Written by the proposal check (backend/dealdesk/proposal_check).

- File: `data/dealdesk/dd-saudi-v1/dd_proposal_quality.parquet`
- Keys: quality_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per check run and check (plus section and proposal score rows)
- Owner: p · Writers: p (proposal check, batch check)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `quality_id` | text |  | Row id: <run_id>:<n>. |
| `run_id` | text |  | Check run: PQ-<proposal_id>-<document hash 8> (same document, same run id: deterministic). |
| `proposal_id` | text |  | Deal checked (dd_deal.proposal_id). |
| `document` | text |  | What was checked: the uploaded Word file name, the memo file, or 'submission record' (dd_deal). |
| `document_sha` | text |  | SHA-256 (first 16 hex) of the document checked. |
| `rm` | text |  | Relationship manager who wrote the proposal (dd_deal.rm). |
| `branch` | text |  | Branch / business unit of the proposal. |
| `sector` | text |  | Obligor sector. |
| `section_key` | text |  | Anatomy section key (bankform registry: header, action, facilities ... signatures); '' for the whole proposal. |
| `section_n` | int |  | Anatomy section number 1-20 (0 for the whole proposal). |
| `section_heading` | text |  | Anatomy section heading. |
| `check` | text |  | Check id (e.g. ACC-RETURNED-CHEQUES, COMP-SECTION, section_score, proposal_score). |
| `category` | text |  | completeness / accuracy / consistency / disclosure / voice / policy / score. |
| `severity` | text |  | critical / major / minor / info. |
| `result` | text |  | defect / observation / pass / score. |
| `defect_type` | text |  | Stable defect type (the answer key's vocabulary), '' for passes and scores. |
| `title` | text |  | One line stating the result, with the numbers. |
| `claim` | text |  | The proposal's words the check is about (quoted), '' when the defect is an omission. |
| `evidence` | text |  | What the bank's data shows, with figures and dates. |
| `evidence_relation` | text |  | Data Domains relation the evidence comes from. |
| `evidence_key` | text |  | Row key in that relation (k=v;...). |
| `query` | text |  | Query to the RM in plain words ('' when none). |
| `score` | float | points | Section score 0-100 (section_score rows) or proposal score 0-100 (proposal_score rows); null on check rows. |
| `defects_n` | int |  | Defects (critical + major) in the section or proposal (score rows). |
| `status` | text |  | open / sent_to_rm / answered / closed (query workflow). |
| `checked_at` | ts |  | When the check ran (the data build stamps a fixed time). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_external_turnover` — External turnover (open banking, VAT)

Credit inflows into the obligor's accounts at other banks (open-banking account information, monthly, by bank) and taxable sales declared in the quarterly VAT return, for the last 12 months of account conduct. Fictional seed (backend/dealdesk/intel2/seed.py).

- File: `data/dealdesk/dd-saudi-v1/dd_external_turnover.parquet`
- Keys: turnover_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal, provider and period
- Owner: i · Writers: i (backend/dealdesk/intel2/seed.py, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `turnover_id` | text |  | Row id XT-<deal>-<provider>-<period>. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `obligor_id` | text |  | Obligor id (obligor id). |
| `source_kind` | text |  | open_banking (inflows at another bank) or vat_return (declared taxable sales). |
| `provider` | text |  | Other bank (fictional) or 'VAT return (tax authority)'. |
| `period` | text |  | Month YYYY-MM (open banking) or quarter YYYYQn (VAT). |
| `period_start` | date |  | First day of the period. |
| `period_end` | date |  | Last day of the period. |
| `credit_inflows_mn` | float | million (deal currency, SAR) | Credit inflows in the period (open banking). |
| `own_account_transfers_mn` | float | million (deal currency, SAR) | Inflows that are transfers between the obligor's own accounts (excluded from sales). |
| `taxable_sales_mn` | float | million (deal currency, SAR) | Taxable sales declared (VAT return). |
| `consent_ref` | text |  | Open-banking consent or VAT authorisation reference (fictional). |
| `retrieved_at` | ts |  | When the data was retrieved. |
| `note` | text |  | Free-text note on this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_deal_intel` — Deal intelligence results (D6-D13)

The results of the R14 deal-intelligence engines: negotiation frontier, default pre-mortem, precedent explorer, pricing benchmark, revenue truth check, renewal diff, group contagion on the deal and committee rehearsal; one catalogue row per feature (proposal_id blank) and one row per deal, feature and headline item.

- File: `data/dealdesk/dd-saudi-v1/dd_deal_intel.parquet`
- Keys: result_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal, feature and item
- Owner: i · Writers: i (build: catalogue; ops/r14_i_publish.py: results)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `result_id` | text |  | Row id: CAT-<feature> (catalogue) or <deal>:<feature>:<seq>. |
| `proposal_id` | text |  | Deal (blank on catalogue rows). |
| `feature` | text |  | D6 .. D13 (feature). |
| `feature_label` | text |  | Feature name. |
| `item_seq` | int |  | Item order within the feature (0 = headline). |
| `item_kind` | text |  | catalogue, headline, offer, path, precedent, percentile, coverage, change, party, question. |
| `label` | text |  | What the item is. |
| `value` | float |  | The item's main number (see unit). |
| `unit` | text |  | Unit of value. |
| `text` | text |  | The item in words (deterministic writer). |
| `structure` | text |  | Structure the engine read: ask, recommended, selected or terms. |
| `basis_json` | json |  | Relations and engine calls the item is computed from. |
| `where` | text |  | Where the panel lives in Deal Desk. |
| `engine_version` | text |  | Engine version. |
| `run_at` | ts |  | When the engine ran. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_business_request` — RM business requests

The RM's business request in the bank form (action requested, facilities, security, terms, group exposure, background, relationship, financials, RM's justification), written by rules from the RM's ask and notes, the uploaded documents and the Bank's own data; every figure carries its source. Written by backend/dealdesk/rm_request (R16 b).

- File: `data/dealdesk/dd-saudi-v1/dd_business_request.parquet`
- Keys: request_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per business request written
- Owner: b · Writers: b (business request writer)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `request_id` | text |  | BR-<proposal_id>-<hash 8 of customer, ask and notes> (deterministic). |
| `proposal_id` | text |  | Deal / customer file id (R16-C1 ... for the R16 customer packs; dd_deal.proposal_id when one exists). |
| `customer_key` | text |  | Customer key in the R16 customer packs (c1-c4), empty for another customer. |
| `customer_name` | text |  | Customer name as on the CR. |
| `cif` | text |  | Borrower 360 id; '' for a new-to-bank customer. |
| `cr_number` | text |  | Commercial Registration number. |
| `rm` | text |  | Relationship manager who wrote the request (signed-in user). |
| `ask_text` | text |  | The ask as typed in the chat box. |
| `notes_text` | text |  | The RM notes as typed. |
| `items_n` | int |  | Facilities named in the ask. |
| `total_existing_mn` | float | SAR m | Total existing limits with the Bank (dd_facility_limit). |
| `total_proposed_mn` | float | SAR m | Total proposed limits after the request. |
| `figures_n` | int |  | Figures printed, each with its source (paper_json.figures). |
| `untraced_n` | int |  | Figures without a source (must be 0). |
| `docs_received_n` | int |  | Checklist documents received. |
| `docs_missing_n` | int |  | Checklist documents missing. |
| `docs_expired_n` | int |  | Checklist documents expired. |
| `disclosures_n` | int |  | Points disclosed for credit's review. |
| `origin` | text |  | Where the documents came from: intake / caller / pack. |
| `status` | text |  | written / shared. |
| `shared_with` | text |  | Users the request was shared with (comma-separated usernames). |
| `paper_json` | json |  | The whole request: sections of blocks, figures with sources, notes placement, plain words. |
| `written_at` | ts |  | When the request was written (UTC). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_intake_file` — Customer file (intake)

A customer file opened on Deal Desk by uploading the customer's documents (R16 i): who the customer is, whether the Bank already knows them (matched by CR number) and the checklist counts.

- File: `data/dealdesk/dd-saudi-v1/dd_intake_file.parquet`
- Keys: intake_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per customer file
- Owner: i · Writers: i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `intake_id` | text |  | Customer file id (IN-…). |
| `proposal_id` | text |  | Deal the file is attached to (blank until a proposal is created from it). |
| `customer_name` | text |  | Customer legal name as printed on the documents (fictional). |
| `cr_number` | text |  | Commercial registration number read from the documents. |
| `existing_customer` | flag |  | 1 when the CR number matches a customer of the Bank. |
| `matched_cif` | text |  | CIF of the matched customer (blank when new to bank). |
| `matched_proposal_id` | text |  | Deal of the matched customer in Data Domains (bank-side data). |
| `case_kind` | text |  | existing, new_to_bank; contractor when project documents are present. |
| `as_of` | date |  | Date the checklist was judged on (validity and expiry). |
| `documents_n` | int | n | Files read (documents n). |
| `received_n` | int | n | Checklist lines received. |
| `missing_n` | int | n | Checklist lines missing. |
| `expired_n` | int | n | Checklist lines expired or stale. |
| `flags_n` | int | n | Reconciliation results that differ or need a question. |
| `created_by` | text |  | User who opened the file. |
| `created_at` | ts |  | When the file was opened. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_intake_document` — Customer file documents

Each uploaded file: how it was read (Word, PDF text, OCR of a photo or scan), what it was classified as and with what confidence, its dates and its validity status on the as-of date.

- File: `data/dealdesk/dd-saudi-v1/dd_intake_document.parquet`
- Keys: doc_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per uploaded file
- Owner: i · Writers: i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `doc_id` | text |  | Document id (<intake_id>-Dnn). |
| `intake_id` | text |  | Customer file. |
| `proposal_id` | text |  | Deal (blank until attached). |
| `file_name` | text |  | Uploaded file name. |
| `file_kind` | text |  | word, pdf, image or text. |
| `read_method` | text |  | Word, PDF text, scanned PDF (OCR), photo (OCR), text. |
| `ocr_engine` | text |  | rapidocr or tesseract when OCR was used. |
| `pages` | int | n | Pages read (pages). |
| `doc_type` | text |  | Document type code (data/dealdesk/demo_customers/CONTRACT.md §4), or unknown. |
| `doc_label` | text |  | Document type in words. |
| `confidence` | float | 0-1 | Classifier confidence (score margin over the runner-up). |
| `subject` | text |  | Owner, bank, account, project, certificate or period the document is about. |
| `customer_name` | text |  | Customer name printed on it. |
| `cr_number` | text |  | CR number printed on it. |
| `issue_date` | date |  | Issue / report / statement date. |
| `expiry_date` | date |  | Printed expiry or valid-until date. |
| `period_from` | date |  | Period start (statements, filings, accounts). |
| `period_to` | date |  | Period end (period to). |
| `status` | text |  | received, expired (printed expiry passed) or stale (older than the validity rule). |
| `fields_n` | int | n | Fields read from it. |
| `sha256` | text |  | Content hash of the file (same file uploaded twice is read once). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_intake_field` — Customer file fields

Each printed field read from a document, with the line it was read from; list fields (tables) are one row with the table in value_json.

- File: `data/dealdesk/dd-saudi-v1/dd_intake_field.parquet`
- Keys: field_row_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per field read from a document
- Owner: i · Writers: i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `field_row_id` | text |  | <doc_id>:<field>. |
| `intake_id` | text |  | Customer file. |
| `proposal_id` | text |  | Deal (blank until attached). |
| `doc_id` | text |  | Document (doc id). |
| `doc_type` | text |  | Document type code. |
| `field` | text |  | Field name (CONTRACT.md §4). |
| `label` | text |  | Label printed on the document. |
| `value_text` | text |  | Value as text (dates ISO). |
| `value_num` | float |  | Value as a number (SAR units for amounts, % for percentages; NaN when not numeric). |
| `value_mn` | float | SAR mn | Amount in SAR million (amount fields only). |
| `value_json` | json |  | Rows of a list field (table). |
| `line_no` | int | n | Line of the document text the value was read from. |
| `raw_text` | text |  | The text as read (OCR or file). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_intake_check` — Customer file checklist

The document checklist against the requirements (KYC, company legal, credit bureau, financials, bank statements and the extras): received, missing, expired or not applicable, with the document that answers it.

- File: `data/dealdesk/dd-saudi-v1/dd_intake_check.parquet`
- Keys: check_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per required document line
- Owner: i · Writers: i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `check_id` | text |  | <intake_id>:<doc_type>:<subject>. |
| `intake_id` | text |  | Customer file. |
| `proposal_id` | text |  | Deal (blank until attached). |
| `req_group` | text |  | kyc, company_legal, credit_bureau, financials, bank_statements, extras. |
| `doc_type` | text |  | Document type code. |
| `requirement` | text |  | What is required, in words. |
| `subject` | text |  | For whom / which period, bank or project. |
| `status` | text |  | received, missing, expired, not_applicable. |
| `doc_ids` | text |  | Documents that answer it (comma separated). |
| `reason` | text |  | Why this status (dates, coverage, rule). |
| `valid_until` | date |  | When the received document stops being valid (blank when it never expires). |
| `rule_ref` | text |  | Deal Desk document rule it maps to (DR-nn), when one exists. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_intake_reconciliation` — Customer file reconciliation

Key figures joined across documents and the Bank's data: revenue in the audited accounts vs bank-statement credits vs VAT filings; owners in the AoA vs CR vs bureau; identity; arithmetic; concentration and other findings only visible when the documents are read together.

- File: `data/dealdesk/dd-saudi-v1/dd_intake_reconciliation.parquet`
- Keys: recon_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per cross-document test
- Owner: i · Writers: i (backend/dealdesk/intake/service.py at run time; backend/dealdesk/intake/seed.py seed rows, fictional)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `recon_id` | text |  | <intake_id>:<test>. |
| `intake_id` | text |  | Customer file. |
| `proposal_id` | text |  | Deal (blank until attached). |
| `topic` | text |  | revenue, owners, identity, arithmetic, concentration, bureau, projects, guarantor, saudisation, related_party, conduct. |
| `title` | text |  | Test in words. |
| `status` | text |  | agrees, differs, flag (needs a question) or info. |
| `severity` | int | 0-3 | 0 info, 1 note, 2 query the RM, 3 key concern. |
| `value_a` | float | SAR mn | First figure (SAR mn or %, see unit_note). |
| `value_b` | float | SAR mn | Second figure. |
| `value_c` | float | SAR mn | Third figure (when three sources are compared). |
| `gap_pct` | float | % | Gap between the figures, % of the first. |
| `unit_note` | text |  | What value_a/b/c are. |
| `sentence` | text |  | The result in the credit voice (facts, numbers, dates). |
| `evidence_json` | json |  | Document ids, fields and bank relations behind each figure. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_credit_request` — Business requests read

What CreditProbe read from a business request uploaded for a credit response (Word, PDF or photos): the header fields, every limit line with existing, outstanding and proposed amounts, every security item and every term, with the document, the reading method and the deal (proposal_id) it set up. The request as received, before credit's view.

- File: `data/dealdesk/credit-response-v1/dd_credit_request.parquet`
- Keys: line_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per line read from an uploaded business request
- Owner: c · Writers: c (backend/dealdesk/credit_response, at runtime; seed: ops/r16_c_publish_seed.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `line_id` | text |  | Row id <case_id>:<kind>:<seq>. |
| `case_id` | text |  | Credit-response case (CRS-...). |
| `proposal_id` | text |  | Deal the request set up (dd_deal.proposal_id). |
| `document` | text |  | File the request was read from (or the photos of its pages). |
| `document_sha` | text |  | SHA-256 (first 16 hex) of the text read. |
| `method` | text |  | How it was read: word, pdf text (layout), pdf scan (OCR), image (OCR). |
| `line_kind` | text |  | header, action, facility, total, security or term. |
| `seq` | int |  | Order within its kind. |
| `label` | text |  | Field label, limit name, security kind or term category. |
| `group_label` | text |  | Limit group the security item or term belongs to ('All limits' when general). |
| `value_text` | text |  | The line as read (text). |
| `existing_mn` | float | million (deal currency, SAR) | Existing limit (facility lines). |
| `outstanding_mn` | float | million (deal currency, SAR) | Outstanding (facility lines). |
| `proposed_mn` | float | million (deal currency, SAR) | Proposed limit (facility lines) or the amount of a security item. |
| `status` | text |  | Perfection status (security), existing-condition status (terms), level (facilities). |
| `read_at` | ts |  | When the request was read. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_credit_response` — Credit responses

The credit division's response to a business request, item by item: the outcome of each Deal Desk step run on it (proposal check, review, analysis, structure, stress, stress-proof, recommendation), each query of the feedback brief to the RM with the bank's evidence, each numbered recommendation and each condition precedent 'prior to limit loading'. The full paper is rendered from these and the deal's relations (Word and PDF).

- File: `data/dealdesk/credit-response-v1/dd_credit_response.parquet`
- Keys: item_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per item of a credit division response
- Owner: c · Writers: c (backend/dealdesk/credit_response, at runtime; seed: ops/r16_c_publish_seed.py)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `item_id` | text |  | Row id <case_id>:<kind>:<seq>. |
| `case_id` | text |  | Credit-response case (CRS-...). |
| `proposal_id` | text |  | Deal (dd_deal.proposal_id). |
| `customer` | text |  | Customer name. |
| `item_kind` | text |  | step, query, observation, recommendation, condition or decision. |
| `seq` | int |  | Order within its kind. |
| `label` | text |  | Step name, query section, recommendation number or condition owner. |
| `text` | text |  | The item in words (deterministic writer). |
| `severity` | text |  | critical, major, minor or info (queries and observations); blank otherwise. |
| `status` | text |  | done or error (steps); open (queries); proposed (recommendations, conditions). |
| `value` | float |  | The item's main number when it has one (score, RAROC %, amount SAR m). |
| `unit` | text |  | Unit of value. |
| `evidence_relation` | text |  | Data Domains relation or uploaded document the item rests on. |
| `due_date` | date |  | Reply-by date (queries) or deadline (conditions). |
| `created_at` | ts |  | When the response was written. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

## Deal Desk products (new domain)

### `dd_project` — Financed and new projects

Contractors' financed projects and new projects: employer, consultant, contract values, dates, work done, billing, receipts, retention, extensions of time and payment delays (anatomy §2.9, §2.13).

- File: `data/dealdesk/dd-saudi-v1/dd_project.parquet`
- Keys: project_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per project
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `project_id` | text |  | Project id (project id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `obligor_id` | text |  | Contractor (obligor id). |
| `project_name` | text |  | Project (fictional). |
| `status` | text |  | new, ongoing, delayed, completed. |
| `financed_flag` | flag |  | 1 when financed or guaranteed by the bank. |
| `limit_id` | text |  | Dedicated limit (dd_facility_limit). |
| `employer` | text |  | Employer (project owner). |
| `employer_entity_id` | text |  | Employer's entity id (b360_entity). |
| `main_contractor` | text |  | Main contractor (when we are sub-contractor). |
| `consultant` | text |  | Consultant / engineer (fictional). |
| `scope` | text |  | Scope of works. |
| `location` | text |  | Location of the project. |
| `contract_value_original_mn` | float | million (deal currency, SAR) | Original contract value. |
| `contract_value_revised_mn` | float | million (deal currency, SAR) | Revised contract value (variations). |
| `start_date` | date |  | Start date (start date). |
| `completion_original` | date |  | Original completion date. |
| `completion_revised` | date |  | Revised / expected completion date. |
| `eot_days` | int | days | Extension of time requested or granted. |
| `eot_formalised_flag` | flag |  | 1 when the EOT is formalised by the employer. |
| `work_done_pct` | float | % | Work done (work done pct). |
| `planned_pct` | float | % | Planned progress at the as-of date. |
| `billed_mn` | float | million (deal currency, SAR) | Billed to date (certified). |
| `received_mn` | float | million (deal currency, SAR) | Received to date. |
| `due_mn` | float | million (deal currency, SAR) | Certified and due, not received. |
| `retention_mn` | float | million (deal currency, SAR) | Retention held by the employer. |
| `advance_mn` | float | million (deal currency, SAR) | Advance received (unrecovered). |
| `last_cert_no` | int |  | Last payment certificate number. |
| `last_cert_date` | date |  | Last payment certificate date. |
| `last_payment_date` | date |  | Last payment received. |
| `payment_delay_days` | int | days | Days since the oldest certified amount fell due. |
| `pending_certs_n` | int | count | Certified payments pending. |
| `demand_letter_flag` | flag |  | 1 when a demand or claim letter was received or issued. |
| `lg_requirements` | text |  | LG requirements (APG %, PB %, RB). |
| `payment_terms` | text |  | Payment terms. |
| `expected_margin_pct` | float | % | Expected project margin as per business. |
| `backlog_mn` | float | million (deal currency, SAR) | Remaining contract value (revised minus billed). |
| `narrative` | text |  | Status paragraph: delays, EOT, payment delays, letters. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_project_cashflow` — Project cash flow

Monthly project cash flow: costs by category, receipts, advance and retention, net and cumulative (deficit negative). The base case is data; P computes the delay stress from it.

- File: `data/dealdesk/dd-saudi-v1/dd_project_cashflow.parquet`
- Keys: project_id, scenario, month_no, reporting_quarter · Period: `reporting_quarter` · Grain: one row per project, scenario and month
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `project_id` | text |  | Project id (dd_project). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `scenario` | text |  | base (as per business) or a stored stress case. |
| `month_no` | int |  | Month number from start (1..n). |
| `month` | text |  | Calendar month YYYY-MM. |
| `cost_materials_mn` | float | million (deal currency, SAR) | Materials cost in the month. |
| `cost_subcontract_mn` | float | million (deal currency, SAR) | Subcontractor cost in the month. |
| `cost_labour_mn` | float | million (deal currency, SAR) | Labour cost in the month. |
| `cost_overheads_mn` | float | million (deal currency, SAR) | Site and overheads. |
| `cost_total_mn` | float | million (deal currency, SAR) | Total cost in the month. |
| `billing_mn` | float | million (deal currency, SAR) | Certified billing (gross). |
| `advance_in_mn` | float | million (deal currency, SAR) | Advance received. |
| `advance_recovery_mn` | float | million (deal currency, SAR) | Advance recovered from billing. |
| `retention_held_mn` | float | million (deal currency, SAR) | Retention withheld from billing. |
| `receipts_mn` | float | million (deal currency, SAR) | Cash received (billing − advance recovery − retention + advance, lagged by payment terms). |
| `net_mn` | float | million (deal currency, SAR) | Receipts minus costs. |
| `cumulative_mn` | float | million (deal currency, SAR) | Cumulative net (deficit when negative). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_syndication` — Syndication

Our participation in a syndicated facility: hold and sell-down, role, agent, pari passu and the information from the agent.

- File: `data/dealdesk/dd-saudi-v1/dd_syndication.parquet`
- Keys: proposal_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per syndicated deal
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `facility_name` | text |  | Facility name. |
| `borrower` | text |  | Borrower of the facility. |
| `total_facility_mn` | float | million (deal currency, SAR) | Total facility. |
| `our_commitment_mn` | float | million (deal currency, SAR) | Our commitment at signing. |
| `final_hold_mn` | float | million (deal currency, SAR) | Target final hold after sell-down. |
| `our_share_pct` | float | % | Our share of the facility at commitment. |
| `role` | text |  | agent, mla, lead or participant. |
| `agent_bank` | text |  | Facility agent (fictional). |
| `mla_banks` | text |  | Mandated lead arrangers, separated by semicolons (fictional). |
| `lenders_n` | int | count | Lenders in the syndicate. |
| `sell_down_mn` | float | million (deal currency, SAR) | Planned sell-down. |
| `sell_down_by` | date |  | Date the sell-down must be done by. |
| `pari_passu_flag` | flag |  | 1 when pari passu with the other lenders. |
| `security_text` | text |  | Security shared through the security agent. |
| `info_from_agent` | text |  | Information memorandum and agent reports received. |
| `covenants_text` | text |  | Financial covenants of the facility. |
| `majority_lenders_pct` | float | % | Majority-lender threshold for waivers. |
| `margin_bps` | float | bps | Margin over the benchmark. |
| `upfront_fee_bps` | float | bps | Participation fee. |
| `tenor_years` | float | years | Tenor of the facility. |
| `signing_date` | date |  | Date the facility was signed. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_escrow_account` — Escrow accounts

Off-plan development escrow accounts: project, developer, escrow agent, units and sales, the release waterfall and rules.

- File: `data/dealdesk/dd-saudi-v1/dd_escrow_account.parquet`
- Keys: escrow_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per escrow account
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `escrow_id` | text |  | Escrow account id. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `account_no` | text |  | Account number (fictional). |
| `project_name` | text |  | Development (fictional). |
| `developer` | text |  | Developer (fictional). |
| `escrow_agent` | text |  | Escrow agent (the bank). |
| `units_total` | int | count | Units in the project. |
| `units_sold` | int | count | Units sold off-plan. |
| `sales_value_mn` | float | million (deal currency, SAR) | Value of units sold. |
| `collected_mn` | float | million (deal currency, SAR) | Collected to date. |
| `receivable_mn` | float | million (deal currency, SAR) | Instalments still to collect from buyers. |
| `construction_cost_mn` | float | million (deal currency, SAR) | Total construction cost. |
| `construction_pct` | float | % | Construction completion certified. |
| `retention_pct` | float | % | Share of each collection retained until handover. |
| `waterfall_json` | json |  | Ordered release waterfall: list of {seq, use, rule}. |
| `release_rules` | text |  | Release rules in words. |
| `cover_ratio_min_x` | float | x | Minimum cover: (escrow balance + receivables) / (loan + cost to complete). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_escrow` — Escrow movements

Monthly escrow collections, releases by waterfall step, retention and balance.

- File: `data/dealdesk/dd-saudi-v1/dd_escrow.parquet`
- Keys: escrow_id, month, reporting_quarter · Period: `reporting_quarter` · Grain: one row per escrow account per month
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `escrow_id` | text |  | Escrow account. |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `month` | text |  | Calendar month, YYYY-MM. |
| `collections_mn` | float | million (deal currency, SAR) | Buyer collections in the month. |
| `release_construction_mn` | float | million (deal currency, SAR) | Released to the contractor against certified progress. |
| `release_debt_service_mn` | float | million (deal currency, SAR) | Released to service the bank's facility. |
| `release_developer_mn` | float | million (deal currency, SAR) | Released to the developer (surplus). |
| `retention_added_mn` | float | million (deal currency, SAR) | Retained until handover. |
| `closing_balance_mn` | float | million (deal currency, SAR) | Escrow balance at month end. |
| `loan_outstanding_mn` | float | million (deal currency, SAR) | Facility outstanding at month end. |
| `construction_pct` | float | % | Construction completion at month end. |
| `units_sold_cum` | int | count | Units sold to date. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `dd_sme_application` — SME applications

SME programme applications for the fast-track lane: score, policy rules, DoA level and decision.

- File: `data/dealdesk/dd-saudi-v1/dd_sme_application.parquet`
- Keys: proposal_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per SME application
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | Application (deal) id. |
| `applicant` | text |  | Applicant (fictional). |
| `obligor_id` | text |  | Obligor id (obligor id). |
| `programme` | text |  | Programme (e.g. SME working capital, SME equipment). |
| `product` | text |  | Product of the application. |
| `amount_mn` | float | million (deal currency, SAR) | Amount asked. |
| `tenor_months` | int | months | Tenor of the facility. |
| `sector` | text |  | Sector of the obligor. |
| `years_in_business` | int | years | Years in business. |
| `annual_sales_mn` | float | million (deal currency, SAR) | Annual sales. |
| `scorecard_id` | text |  | Scorecard (SME-ANN). |
| `score` | int | points | Scorecard points. |
| `grade` | int |  | Score grade (1 best). |
| `pd` | float | probability (0-1) | Grade PD (pd). |
| `rules_json` | json |  | Policy rule results: list of {rule, value, limit, pass}. |
| `rules_failed` | int | count | Rules failed. |
| `decision` | text |  | approve, refer (to the full flow) or decline. |
| `doa_level` | text |  | Approval authority by amount. |
| `conditions_text` | text |  | Conditions (conditions text). |
| `exception_flag` | flag |  | 1 when an exception sends it to the full flow. |
| `submitted_date` | date |  | Date submitted. |
| `decided_date` | date |  | Decided (blank when pending). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

## Bureau (additions)

### `bureau_entity_report` — Bureau report per entity and UBO

Credit bureau (SIMAH-style) report per group entity, guarantor and UBO of a deal: outstanding, overdue, returned cheques, score, court cases; reports not provided are rows with provided_flag 0 and the reason.

- File: `data/external/bureau-r12-v1/bureau_entity_report.parquet`
- Keys: report_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal and entity or person
- Owner: E · Writers: E fictional data; B reads

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `report_id` | text |  | Report id (report id). |
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `entity_id` | text |  | Entity or person (b360_entity / b360_shareholder holder_id). |
| `entity_name` | text |  | Name of the entity or person. |
| `entity_kind` | text |  | company, ubo or guarantor. |
| `bureau` | text |  | Bureau (SIMAH). |
| `report_date` | date |  | Report date (report date). |
| `provided_flag` | flag |  | 1 when the report is on file. |
| `not_provided_reason` | text |  | Why not, as per business. |
| `facilities_n` | int | count | Facilities reported. |
| `outstanding_mn` | float | million (deal currency, SAR) | Outstanding across lenders. |
| `overdue_mn` | float | million (deal currency, SAR) | Overdue (overdue mn). |
| `overdue_days_max` | int | days | Worst days overdue. |
| `returned_cheques_n` | int | count | Returned cheques reported (last 12 months). |
| `returned_cheques_mn` | float | million (deal currency, SAR) | Value of returned cheques. |
| `returned_cheque_dates` | text |  | Dates of returned cheques, separated by semicolons. |
| `score` | int | points | Bureau score (300-900). |
| `court_cases_n` | int | count | Court cases reported. |
| `court_cases_mn` | float | million (deal currency, SAR) | Amount claimed in court cases. |
| `worst_status` | text |  | Worst repayment status. |
| `note` | text |  | Free-text note on this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `bureau_cbrbr` — Central-bank risk bureau (CBRBR)

The central-bank risk bureau view of the subject and every related entity: funded and non-funded limits and outstandings across all banks, number of banks and classification (anatomy §2.10).

- File: `data/external/bureau-r12-v1/bureau_cbrbr.parquet`
- Keys: proposal_id, entity_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal and entity
- Owner: E · Writers: E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `entity_id` | text |  | Entity id (b360_entity). |
| `entity_name` | text |  | Name of the entity or person. |
| `report_date` | date |  | Report date (report date). |
| `funded_limit_mn` | float | million (deal currency, SAR) | Funded limits, all banks. |
| `funded_outstanding_mn` | float | million (deal currency, SAR) | Funded outstanding. |
| `non_funded_limit_mn` | float | million (deal currency, SAR) | Non-funded limits. |
| `non_funded_outstanding_mn` | float | million (deal currency, SAR) | Non-funded outstanding. |
| `total_limit_mn` | float | million (deal currency, SAR) | Total limits. |
| `total_outstanding_mn` | float | million (deal currency, SAR) | Total outstanding. |
| `banks_n` | int | count | Banks reporting. |
| `classification` | text |  | Worst classification: regular, watch, substandard, doubtful, loss. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `other_bank_facility` — Other banks' facilities

The other-bank matrix (bank × group entity): client-declared facilities against the bureau, with the reconciliation and whether it was clarified (anatomy §2.12).

- File: `data/external/bureau-r12-v1/other_bank_facility.parquet`
- Keys: proposal_id, bank_name, entity_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per deal, bank and entity
- Owner: E · Writers: E fictional data

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `proposal_id` | text |  | The deal (proposal_id) this row belongs to. |
| `bank_name` | text |  | Other bank (fictional). |
| `entity_id` | text |  | Entity id (b360_entity). |
| `entity_name` | text |  | Entity name (entity name). |
| `facility_types` | text |  | Facility types, separated by semicolons. |
| `declared_limit_mn` | float | million (deal currency, SAR) | Limit as declared by the client. |
| `declared_outstanding_mn` | float | million (deal currency, SAR) | Outstanding as declared. |
| `bureau_limit_mn` | float | million (deal currency, SAR) | Limit as per bureau / CBRBR. |
| `bureau_outstanding_mn` | float | million (deal currency, SAR) | Outstanding as per bureau. |
| `difference_mn` | float | million (deal currency, SAR) | Bureau outstanding minus declared outstanding. |
| `fal_provided_flag` | flag |  | 1 when the bank's facility offer letter (FAL) is on file. |
| `fal_date` | date |  | FAL date (fal date). |
| `security_text` | text |  | Security given to that bank (pari passu check). |
| `reconciliation_note` | text |  | Reconciliation in words. |
| `clarified_flag` | flag |  | 1 when the difference was explained. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

## Borrower 360 (new relations)

### `b360_entity` — Group entities

Every company in the R12 fictional groups (subject, parent, subsidiaries, sisters, guarantors, employers): licence, activity, legal status, place in the group and credit status. Book borrowers keep their CB ids in borrower_id.

- File: `data/relationships/b360-saudi-v1/b360_entity.parquet`
- Keys: entity_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per entity
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `entity_id` | text |  | Entity id (XE-…). |
| `entity_name` | text |  | Legal name (fictional). |
| `group_id` | text |  | Group id (group id). |
| `group_name` | text |  | Group name (group name). |
| `role` | text |  | subject, parent, subsidiary, sister, associate, guarantor, employer, borrower. |
| `parent_entity_id` | text |  | Direct parent (blank at the top). |
| `country` | text |  | Country of incorporation. |
| `legal_status` | text |  | LLC, JSC, sole proprietorship, branch … |
| `activity` | text |  | Activity as per licence. |
| `licence_no` | text |  | Trade licence / CR number (fictional). |
| `licence_expiry` | date |  | Licence expiry. |
| `incorporation_date` | date |  | Incorporation date. |
| `incorporation_place` | text |  | Incorporation place. |
| `staff_count` | int | count | Staff count (staff count). |
| `listed_flag` | flag |  | 1 when listed. |
| `borrower_id` | text |  | Corporate book borrower id when the entity is a book borrower. |
| `credit_status` | text |  | performing, past_due, classified_substandard, classified_doubtful, litigation. |
| `credit_status_note` | text |  | Why (e.g. 'classified doubtful at another bank since 2025-11'). |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `b360_edge` — Group edges

Links between R12 fictional entities and persons (ownership, guarantee, supplier, customer, employer, shared collateral, common director), in the rel_edge_quarter vocabulary.

- File: `data/relationships/b360-saudi-v1/b360_edge.parquet`
- Keys: edge_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per link
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `edge_id` | text |  | Edge id (edge id). |
| `rel_type` | text |  | owns, guarantees, supplies, buys_from, employer_of, shared_collateral, common_director, related_party. |
| `source_id` | text |  | From entity or person. |
| `target_id` | text |  | To entity (target id). |
| `group_id` | text |  | Group id (group id). |
| `ownership_pct` | float | % | Ownership share (owns). |
| `annual_value_mn` | float | million (deal currency, SAR) | Annual flow (supplies / buys_from). |
| `amount_mn` | float | million (deal currency, SAR) | Guarantee or collateral amount. |
| `detail` | text |  | Detail of the link. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `b360_shareholder` — Shareholders and UBOs

Shareholders of every entity, with %, nationality, age and the ultimate-beneficial-owner flag.

- File: `data/relationships/b360-saudi-v1/b360_shareholder.parquet`
- Keys: entity_id, holder_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per entity and holder
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `entity_id` | text |  | Entity held (entity id). |
| `holder_id` | text |  | Holder (person XP-… or entity XE-…). |
| `holder_name` | text |  | Holder name (fictional). |
| `holder_kind` | text |  | person or company. |
| `nationality` | text |  | Nationality (persons) or country (companies). |
| `birth_year` | int |  | Year of birth (persons). |
| `share_pct` | float | % | Shareholding. |
| `ubo_flag` | flag |  | 1 when the holder is an ultimate beneficial owner (≥ 25% look-through, or control). |
| `ubo_effective_pct` | float | % | Look-through effective ownership of the subject. |
| `nominee_flag` | flag |  | 1 when held as nominee. |
| `since` | date |  | Holder since. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `b360_board` — Board and key persons

Board members, managers and authorised signatories, with their other directorships and links to other borrowers.

- File: `data/relationships/b360-saudi-v1/b360_board.parquet`
- Keys: entity_id, person_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per entity and person
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `entity_id` | text |  | Entity id (b360_entity). |
| `person_id` | text |  | Person (person id). |
| `person_name` | text |  | Name (fictional). |
| `role` | text |  | chairman, director, ceo, gm, cfo, authorised_signatory, manager. |
| `nationality` | text |  | Nationality (nationality). |
| `appointed` | date |  | Appointed (appointed). |
| `key_person_flag` | flag |  | 1 for a key person (management depends on them). |
| `other_directorships` | json |  | List of {entity_id, entity_name, role} elsewhere. |
| `linked_borrower_ids` | text |  | Other borrowers of the bank linked through this person, separated by semicolons. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `b360_insider_link` — Insider and staff links

Staff, insider and related-party links of the bank to group entities and guarantors (connected-lending check).

- File: `data/relationships/b360-saudi-v1/b360_insider_link.parquet`
- Keys: link_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per link
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `link_id` | text |  | Link id (link id). |
| `entity_id` | text |  | Entity linked (e.g. the guarantor). |
| `person_id` | text |  | Person on the bank side or holder. |
| `person_name` | text |  | Name (fictional). |
| `link_kind` | text |  | staff_shareholding, staff_relative, board_member_of_bank, related_party. |
| `bank_staff_id` | text |  | Bank staff id (fictional) of the insider. |
| `staff_role` | text |  | Insider's role at the bank. |
| `relationship` | text |  | Relationship (self, spouse, sibling …). |
| `share_pct` | float | % | Shareholding in the entity. |
| `disclosed_flag` | flag |  | 1 when disclosed in the proposal. |
| `detected_by` | text |  | How it was found (staff register match, related-party register). |
| `note` | text |  | Free-text note on this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `b360_ownership_change` — Ownership changes

Recent changes in shareholding of group entities.

- File: `data/relationships/b360-saudi-v1/b360_ownership_change.parquet`
- Keys: change_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per change
- Owner: E · Writers: E (fictional deal data)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `change_id` | text |  | Change id (change id). |
| `entity_id` | text |  | Entity id (b360_entity). |
| `change_date` | date |  | Date of the event. |
| `holder_id` | text |  | Holder id (holder id). |
| `holder_name` | text |  | Holder name (holder name). |
| `from_pct` | float | % | Share before. |
| `to_pct` | float | % | Share after (to pct). |
| `kind` | text |  | entry, exit, transfer, capital_increase. |
| `disclosed_flag` | flag |  | 1 when the proposal discloses it. |
| `note` | text |  | Free-text note on this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

## Governance (R13 IE, new domain; fictional history)

### `gov_decision` — Credit decisions (history)

Past credit decisions on book borrowers: who proposed it (RM, branch), the level that had to approve it under the DoA, the decision, exceptions, proposal quality, review queries, conditions and promises. Fictional seed.

- File: `data/governance/gov-saudi-v1/gov_decision.parquet`
- Keys: decision_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per credit decision
- Owner: IE · Writers: IE (ops/r13_seed_governance.py, fictional history)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `decision_id` | text |  | Decision id GD-nnnnn. |
| `borrower_id` | text |  | Book borrower (corp_borrower_quarter). |
| `borrower_name` | text |  | Borrower name (fictional). |
| `decision_quarter` | text |  | Book quarter the decision was taken in (YYYYQn). |
| `decided_on` | date |  | Date of the final decision. |
| `case_type` | text |  | new, renewal or increase. |
| `sector` | text |  | Borrower sector at the decision. |
| `rm_id` | text |  | RM at the decision (branch_corporate_quarter). |
| `rm_name` | text |  | RM name (fictional). |
| `branch_id` | text |  | Branch id (branch id). |
| `branch_name` | text |  | Branch name (branch name). |
| `region` | text |  | Region of the obligor. |
| `limit_sar_mn` | float | SAR million | Total limits decided. |
| `rating_at_decision` | text |  | Internal rating at the decision quarter. |
| `pd_at_decision` | float |  | 12-month PD at the decision quarter (0-1). |
| `dscr_at_decision` | float | x | DSCR at the decision quarter. |
| `leverage_at_decision` | float | x | Debt to EBITDA at the decision quarter. |
| `required_level_rank` | int |  | DoA rank required (dd_parameter doa: 1 Corporate Credit Manager .. 5 Board Credit Committee). |
| `required_level` | text |  | DoA level required. |
| `decision` | text |  | approved, approved_with_conditions or declined. |
| `exception_count` | int |  | Policy exceptions approved with the decision (gov_policy_exception). |
| `exception_types` | json |  | List of exception types. |
| `proposal_quality_score` | float | 0-100 | Review score of the proposal as submitted (completeness, accuracy, analysis). |
| `review_queries` | int |  | Queries the reviewer sent back to the RM. |
| `conditions_set` | int |  | Conditions set with the approval. |
| `conditions_met` | int |  | Conditions met by their due date. |
| `conditions_breached` | int |  | Conditions breached or not complied. |
| `promises_made` | int |  | Commitments made in the proposal (business routing, deposits, cross-sell). |
| `promises_delivered` | int |  | Commitments delivered in their window. |
| `turnaround_days` | float | days | Calendar days from submission to final decision. |
| `seed_basis` | text |  | What is seeded and what is read from the book for this row. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `gov_approval_step` — Approval steps (history)

Each level a past decision passed through, in order, with time spent and whether the level changed the decision or its terms. Fictional seed.

- File: `data/governance/gov-saudi-v1/gov_approval_step.parquet`
- Keys: step_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per decision per approval level
- Owner: IE · Writers: IE (ops/r13_seed_governance.py, fictional history)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `step_id` | text |  | Step id (step id). |
| `decision_id` | text |  | Decision (gov_decision). |
| `seq` | int |  | Order of the step. |
| `level_rank` | int |  | DoA rank of the level (1-5). |
| `level_name` | text |  | DoA level (level name). |
| `received_on` | date |  | Date the file reached the level. |
| `decided_on` | date |  | Date the level decided. |
| `days` | float | days | Calendar days at the level. |
| `input` | text |  | Recommendation the level received: approve or decline. |
| `output` | text |  | What the level did: concur, amend (terms changed), decline, overturn (reversed the recommendation). |
| `changed_flag` | flag |  | 1 when the level changed the decision or its terms. |
| `queries_raised` | int |  | Queries the level raised. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

### `gov_policy_exception` — Policy exceptions (history)

Every policy exception approved with a past decision, with the clause, the measured value and the limit. Financial exceptions are measured on the borrower's book financials at the decision quarter; the others are seeded.

- File: `data/governance/gov-saudi-v1/gov_policy_exception.parquet`
- Keys: exception_id, reporting_quarter · Period: `reporting_quarter` · Grain: one row per approved exception
- Owner: IE · Writers: IE (ops/r13_seed_governance.py, fictional history)

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `exception_id` | text |  | Exception id. |
| `decision_id` | text |  | Decision (gov_decision). |
| `borrower_id` | text |  | Book borrower. |
| `decision_quarter` | text |  | Quarter of the decision. |
| `exception_type` | text |  | dscr, leverage, current_ratio, rating, collateral_cover, pricing, late_financials, perfection_deferral. |
| `policy_id` | text |  | Policy (dd_policy). |
| `clause` | text |  | Clause (dd_policy_clause). |
| `measured` | float |  | Measured value at the decision. |
| `threshold` | float |  | Policy limit. |
| `unit` | text |  | Unit of measured and threshold. |
| `basis` | text |  | book (measured on corp_borrower_quarter) or seeded. |
| `approved_by_level` | text |  | Level that approved the exception. |
| `mitigant` | text |  | Mitigant recorded with the approval. |
| `reporting_quarter` | text |  | Reporting quarter the row belongs to (the Deal Desk book quarter, 2026Q2). |
| `rel_version` | int |  | Version of the relation that published this row (publish() increments it). |
| `published_at` | ts |  | UTC time the row's version was published. |

