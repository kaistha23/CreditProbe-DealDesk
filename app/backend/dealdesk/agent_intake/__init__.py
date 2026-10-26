"""Round A (PLAN_DEALDESK_EDITION): the agentic intake. The Credit Request Agent's workflow on every new proposal.

    read.py       step 1: read and classify each document (model reader + R16's rule reader, reconciled)
    checklist.py  step 2: the checklist, the weighted completeness score, what cannot be assessed, the re-run delta
    draft.py      step 3: the business request (prompt, deterministic writer, the figure check)
    model.py      every model call through backend/convo/provider.py, measured
    service.py    the run (three steps with timings), revise, attach
    store.py      runs, texts, files under var/dealdesk/agent_intake
    export.py     Word through R16's bank-form renderer
    sample.py     the Saqr Al Wadi sample pack (data/dealdesk/agent_sample)
    api.py        /api/v1/dealdesk/agent-intake
"""
