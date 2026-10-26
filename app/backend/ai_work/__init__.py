"""Domain-scoped conversations for Playbook, Projects and Cockpit help (Session A2, PLAN_R4).

A fork of the frozen Cockpit's conversational stages (understand, plan, query, answer, validate, publish), scoped
to one data domain per conversation. The deterministic engines are tools the conversation calls. When the shared
layer `backend/convo` (docs/v5/CONVO_API.md) is on the branch, `adapter` hands the model step to it.
"""
