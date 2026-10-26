# CreditProbe functionalities (current)

The current functionalities of CreditProbe, grouped as the navigation groups them. `backend/ai_work/knowledge.py` reads this file into the pack's `overview` (it has no module header, so it is not a module topic); the Cockpit's synopsis lists it when the v5 pack is present (registered exception FX-A4).

Note: This list supersedes the deck's seven-module list. There is no AI Project Planner: Projects (with Investigations and Analyses) replaced it. Deal Desk is a functionality. Borrower 360, Data Domains (formerly Data Builder) and Workflow, which the deck listed as supporting capabilities, are functionalities.

Absorbs: Data Builder, Borrower 360, Workflow

The Arc column places each functionality on the Detect → Diagnose → Decide → Drive Alignment arc (a shared operating story, not one module per stage).

## Intelligence

| Name | Screen | Arc | Does | Owns |
|---|---|---|---|---|
| Cockpit | / | Detect, Diagnose | Ask the corporate and retail books in plain language: what moved, why, and who to look at next, with checked figures, tables, charts and the trace. | historical and recorded credit analysis on the books, what needs attention this period, the ECL panel, and product help |
| Early Warning | /early-warning?domain=corporate | Detect | Scores every corporate facility and retail account against a published rule set and bands each name with the reasons that fired. | emerging deterioration, the warning bands and the names to review |
| What-If | /what-if?domain=corporate | Decide | Runs macro, parameter, rating, sector and stage-migration scenarios on IFRS 9 ECL and shows before and after, the waterfall and the capital impact. | prospective and hypothetical shocks and scenarios |
| Deal Desk | /deal-desk | Decide | Prices and structures a corporate facility before approval: risk, capital, lifetime RAROC and SVA, portfolio limits, and counter-offers that clear the hurdle. | pre-deal pricing, structuring and the approval route of a new facility |
| Borrower 360 | /borrower-360 | Diagnose | The single view of one borrower or customer: rating, facilities, exposure, ECL and stage, collateral, covenants, Early Warning and the relationship graph. | the borrower-level view and its relationships |
| Scorecard Validation | /scorecard-validation | Diagnose | Tests the retail and SME scorecards for discrimination, calibration, stability, variables and overrides, each with a red, amber or green verdict. | model-validation diagnostics |
| Lenses | /lenses | Detect | Builds a live dashboard from a plain-words request: a KPI row, charts, the top names and a short commentary, every figure a query on the books. | dashboards and executive indicators |
| Playbook | /playbook | Drive Alignment | Writes committee packs, risk reports, credit memos and validation reports, every section drafted from the books with its own assistant. | committee narrative, reports and decision questions |

## Work

| Name | Screen | Arc | Does | Owns |
|---|---|---|---|---|
| Projects (with Investigations and Analyses) | /projects | Drive Alignment | A workspace for one piece of work with its documents, instructions, data domains and members; saved investigations (whole threads) and analyses (one refreshable question) live alongside. | project work, saved threads and refreshable analyses |
| Policy Docs | /policy-docs | Decide | Holds the credit policy, the circulars and the regulation in force (the CBUAE Credit Risk Management Standards, with breach checks on the books); the assistant reads a new document, lists its clauses and, once approved, adds them to the pack the Cockpit cites. | the active credit policy pack and CBUAE CRM compliance |
| My workspace | /workspace | Drive Alignment | Each user's home: tasks, mentions, unread mail, reports to review and critical names on your books, plus your analyses, investigations and projects. | what is waiting on each user |
| Mail | /messages | Drive Alignment | Internal mail: share any object (an answer, a report, a scenario, a borrower page) with colleagues as a live card. | sharing between colleagues |

## Data

| Name | Screen | Arc | Does | Owns |
|---|---|---|---|---|
| Data Domains | /data-builder | — | Builds an extract from the books without SQL (book, period, columns, filters), previews it and exports a house-styled Excel file. | extracts and exports of the books |

## Admin

| Name | Screen | Arc | Does | Owns |
|---|---|---|---|---|
| Workflow and data access | /workflow | — | Approval workflows route work to the right approver with SLAs and escalation; data access policies decide who sees which rows, modules and actions. | who approves what and who sees what |
| Users & Teams | /users | — | Everyone who signs in: role, team, RM ID, the access policies that apply and the RM and branch hierarchy. | users, roles, teams and RM portfolios |
| Agent Operations | /agent-operations | — | The live log of every AI run with its steps, tools, cost and outcome, a refusal queue, evaluation suites and a kill switch per module. | monitoring and control of the AI runs |
| AI Studio | /ai-studio | — | Configures each module's assistant: model, instructions and house tone, glossary, knowledge sources, tools and guardrails. | assistant configuration |
| Settings | /settings | — | The bank profile, house style, the register of parameter tables, notifications, data feeds and retention. | bank-wide settings and parameter tables |
| Audit log | /audit-log | — | Records who did what and when: sign-ins, exports, approvals, configuration changes, kill switches and every AI run. | the audit trail |
