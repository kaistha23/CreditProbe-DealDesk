"""PLAN_R12 Session F: the bank-form credit proposal (I25) on the anatomy in docs/v5/house_style/PROPOSAL_ANATOMY.md.

    source.py      the one door to Data Domains (Session E's dd_read; the registered parquet before R12); lineage on every row
    ctx.py         a deal's relations and the figure formats
    registry.py    the section registry: 20 anatomy sections + CreditProbe sections, each with its data contract and writer
    writers.py     deterministic writers for the 20 anatomy sections (N6)
    cp_writers.py  deterministic writers for the CreditProbe sections (RAROC/SVA and alternatives, forward risk, stress verdict and
                   tier, precedent, SWOT, group and governance)
    voice.py       the voice validator (fact + figure + date or attribution; PY in brackets; shares; adjusted; plain words; two voices)
    coverage.py    the coverage validator (a missing section fails)
    polish.py      optional model polish that may never change a figure
    paper.py       assembly: write(pid) -> the paper with coverage, voice and gaps
    render.py      the paper in Word (house style) and PDF
"""
