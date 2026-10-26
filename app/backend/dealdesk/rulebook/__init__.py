"""Round P (PLAN_DEALDESK_EDITION): Policy Docs as the rulebook.

"Upload a regulation or policy: instantly summarise, say where it is used, what deal types and pending deals are affected; the
user approves; then it is applied continuously. Gold-standard proposals: compare, propose changes, apply on yes. A fourth
section: global rules, seeded from the SIB proposals." (Anne, 23 Oct 2026)

    checks.py     the Deal Desk policy checks a regulation or policy can move (DSCR, leverage, collateral cover, tenor,
                  valuation age, hurdle, rating): each threshold's value in force and the Deal Desk table it lives in
    facts.py      the facts of every pending deal the checks read (Deal Desk engine on the proposal record), cached
    interpret.py  an upload -> its summary and the thresholds it sets, each with its clause and quote (model through the
                  provider, validated against the text; deterministic reader without a key)
    impact.py     the checks run on the pending deals with and without the change: who would fail, by deal type
    store.py      assessments, threshold versions (with provenance), deal flags, gold-standard comparisons
                  (SQLite under var/dealdesk/rulebook/)
    gold.py       a gold-standard proposal against how the system writes today; "Apply these?" -> rules and house style
    hook.py       the proposal check reads the approved thresholds: every later deal is checked, the clause cited
    api.py        /api/v1/dealdesk/rulebook
The Global rules section is Round K's store (backend/dealdesk/rules), scope = the bank.
"""
