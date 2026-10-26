id: admin_workflow
name: Approval workflows
screen: /workflow?tab=workflows
keywords: workflow, approval workflow, approval workflows, escalation, sla, doa, delegation of authority, simulate a workflow
example: admin_workflow_ews

## What it is
Approval workflows route work to people: Deal Desk proposals to the approver their exposure, rating and soft breaches require under the DOA table; Playbook reports to review and sign-off; What-If scenarios to Model Validation and the CRO before official use; Critical Early Warning names to their RM for an action plan; parameter-table changes through validation and approval. Each workflow is a chain of step cards with an assignee, an SLA in days, escalation, delegation and conditions.

## Flow
1. [Open Workflow, Approval workflows](/workflow?tab=workflows).
2. Read a workflow as step cards; press Simulate to walk it on a real object (a Critical name, a Deal Desk proposal) and see who gets each step and when it is due or escalates.
3. Press Edit or New workflow, change the steps, simulate again, then save and submit for approval.
4. Or ask the Admin assistant: "Create a workflow so Critical Early Warning names need an RM action plan within 5 days, escalate to the Head of Credit after 10".
5. [Live items](/workflow?tab=items) lists the open items and which are overdue.

## Good to know
- The DOA levels come from the Deal Desk parameter table (Corporate Credit Manager up to SAR 25 m, Head of Credit 100 m, CRO 175 m, Executive Credit Committee 250 m, Board above).
