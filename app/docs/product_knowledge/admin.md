id: admin
name: Admin
screen: /workflow
keywords: admin, admin console, administration, maker-checker, maker checker, four eyes
example: admin_overview

## What it is
Admin runs the bank's CreditProbe. Workflow decides who sees what (data access policies) and who approves what (approval workflows); Users and Teams holds the people, their roles and RM portfolios; Agent Operations watches every AI run; AI Studio configures each module's assistant; Settings holds the bank profile, house style and the register of parameter tables; the Audit log records who did what. Every change is maker-checker: drafted, submitted, approved by a second person (an Admin or a CRO), then live, with versions.

## Flow
1. [Open Workflow](/workflow) to set data access policies and approval workflows.
2. Draft a change by hand or ask the Admin assistant ("Ask the Admin assistant", top right) to draft it from your words.
3. Submit it: it waits for approval in the page's "Changes in progress" list.
4. A second approver (Admin or CRO) approves it; it goes live as the next version.
5. Check it in the [Audit log](/audit-log).

## Good to know
- The maker can never approve their own change; the Administrator viewing as another user cannot change anything.
- The Cockpit's own configuration is frozen and shown read-only in AI Studio.
