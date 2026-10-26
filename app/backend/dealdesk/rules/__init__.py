"""Round K (PLAN_DEALDESK_EDITION): the analysts' rules.

"Every analyst has their own tone. A comment should be saved so they don't repeat it. CreditProbe asks 'shall I save
this?'; yes makes it a rule." (Anne, 23 Oct 2026)

    store.py     the rules store (SQLite under var/dealdesk/rules/): text, kind, parameters, scope (me / my team / the bank),
                 document (credit request / credit proposal / both), section, author, date, source instruction, status,
                 and every change as an event (who, when, what)
    seed.py      the bank's global rules seeded from the style of the two SIB proposals (synthetic stand-ins, no SIB text)
    classify.py  an instruction or a typed rule -> a rule kind with parameters (model through the provider, validated;
                 deterministic parser without a key)
    apply.py     the rules applied to a document (house-style draft or bank-form paper): the simple kinds deterministically
                 (wording, units, include a section, section order, heading, risks-and-mitigants table, must mention), the
                 rest passed to the model as instructions; every rule's effect listed under "Rules applied"
    hook.py      the seams the drafting paths call (house-style draft, the credit request, the bank-form credit proposal)
    api.py       /api/v1/dealdesk/rules
"""
