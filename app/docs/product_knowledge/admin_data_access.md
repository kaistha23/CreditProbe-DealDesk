id: admin_data_access
name: Data access
screen: /workflow?tab=access
keywords: data access, access policy, access policies, view as, who sees what, column masking, mask names, rm portfolio
example: admin_view_as

## What it is
Data access policies say who sees what: by book (corporate, retail), sector, region, branch, RM portfolio and segment; which modules a user may open; which actions they may take (export, send, approve, run models); and whether obligor names or IDs are masked. A policy is assigned to users, roles or teams. One shared module (backend/access) applies it in every v5 service and in every AI answer, so lists, counts, totals, exports and assistant answers never include rows outside it.

## Flow
1. [Open Workflow, Data access](/workflow?tab=access): the live policies are cards with their scope, modules, actions and members.
2. Press New policy (or Edit on a card), choose books, the rows, modules, actions and masking, and who it applies to; the preview shows how many customers and how much EAD a chosen user would see.
3. Save and submit it; another Admin or CRO approves it.
4. In View as user, pick a person to see exactly what they see, then "Open CreditProbe as this user" to walk the screens as them.

## Good to know
- A user with several policies sees the union of what they allow; masking applies only if every policy masks.
- "Their own portfolio" resolves to the user's RM ID, so one policy serves every RM.
- The frozen Cockpit is restricted at book level by the v5 shell; row-level restriction inside the Cockpit would need a registered exception.
