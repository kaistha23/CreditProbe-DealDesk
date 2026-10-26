"""R13 Session Q: the financial-quality detector (PLAN_R13 §Q, R12_FEEDBACK J11).

    from backend.dealdesk import fin_quality as FQ
    r = FQ.assess("R12-TWA")          # a deal: {subject, grade, signals, families, headline, lines, coverage, sources}
    r = FQ.assess_book("CF000011")    # a back-book facility up for renewal (the Book renewal row)
    FQ.publish("R12-TWA")             # flagged signals + the grade row -> dd_review_finding (category financial_quality)
    FQ.paragraph("R12-TWA")           # the "Financial quality" paragraph of the synopsis and the committee paper

Every signal carries its number, threshold, source relation and period (signals.py); the grade rule is in grade.py and
the statistical screens (Beneish M-score, Benford first digits) with their reliability notes in stats.py. Inputs come
from Data Domains only (inputs.py, through backend.dealdesk.data).
"""
from __future__ import annotations

from backend.dealdesk.fin_quality.engine import assess, assess_book, headline, paragraph, summary  # noqa: F401
from backend.dealdesk.fin_quality.publishing import publish, published  # noqa: F401
