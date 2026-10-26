"""PLAN_R11 Session P: proposal drafting in the bank's house language.

    corpus.py    every proposal in the system read into sections (memos, prepared cases, opinions, uploads, exemplars)
    profile.py   the house-style profile per bank and memo type, built from additive counts (incremental, learns from RM edits)
    retrieve.py  nearest exemplar sections (TF-IDF, pure Python)
    facts.py     a section's facts from the books and the proposal, each with its source (the only figures a draft may use)
    draft.py     section-by-section drafting: model path with figure validation, deterministic template fallback
    fidelity.py  style score against the profile and the "differs from house style" lint
    store.py     drafts and learning events under var/dealdesk/house_style
    export.py    Word export in house style (the report_docx pattern)
"""
