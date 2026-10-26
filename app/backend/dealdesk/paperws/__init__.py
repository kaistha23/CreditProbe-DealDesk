"""Rounds W and T (Deal Desk edition): the living request and proposal, with provenance.

One workspace per document: the RM's business request (kind "request") or Credit's credit proposal (kind "proposal"), both in
the bank's form (the section/blocks model of backend/dealdesk/house_style/bankform and backend/dealdesk/rm_request). The
document is on the left of the screen, the conversation with Noor on the right. Every instruction edits ONE section in place
and is marked (before / after, accept / undo); every change is a new version (v1, v2, ... who, when, instruction); the
workspace is a thread reopened from Recent work, the deal's Papers and the Workspace; Word and PDF at any time; "Mark final"
sets the committee copy.

Figures are the engine's: a request to change a number is sent to the structure step (bankform/feed.py on new terms for a
proposal; the ask parser for a business request) and the paper is re-rendered; model output with a figure that is not in the
evidence is rejected (figures.py). Without a model key a fixed instruction set is applied by rules (instructions.py).

    store.py         SQLite: workspaces, versions, turns (var/paperws/paperws.sqlite; PAPERWS_STORE overrides)
    sources.py       where a document comes from (the bank-form writer, a saved business request, a paper given by another round)
    figures.py       the evidence numbers of a paper and the figure check
    instructions.py  instruction -> one section edit (rules; the model when a key is present) or a structure change
    structure.py     the structure step: a number change -> new terms -> the engine -> the paper re-rendered
    provenance.py    Round T: every section and point with its evidence (document + page, relation + row, engine, rule, analyst)
    export.py        Word / PDF of any version, with the provenance annex
    hooks.py         integration points: rule providers (Round K), paper sources (Round A)
    service.py       open, instruct, accept, undo, mark final, versions
    api.py           /api/v1/dealdesk/paper-workspaces*  (docs/v5/ROUND_WT.md)
"""
