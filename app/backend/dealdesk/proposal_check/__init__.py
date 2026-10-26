"""R14 session p: the proposal check (K31, D1) and the batch check (K33, D2).

    relation.py    the dd_proposal_quality relation spec (pure data; registered in backend/dealdesk/data/schema.py)
    demo_deal.py   the fictional demo deal R14-RWQ (built through the R12 build path)
    parse.py       read an RM proposal (Word) into sections, paragraphs and tables
    rules.py       the deterministic checks: completeness, accuracy, consistency, disclosure, voice, policy and T&C
    engine.py      check(pid, document) -> score by section, findings with evidence, queries; deterministic (no model)
    annotate.py    the annotated Word (comments in the margin) and the query list
    batch.py       check every pending proposal; RM view; Excel export; publish to dd_proposal_quality
    api.py         /api/v1/dealdesk/proposal-check/...
"""
