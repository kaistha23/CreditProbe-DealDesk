"""The v5 shared spine: one definition of the books every module keys to.

The frozen Cockpit publishes two books (corporate, quarterly; retail,
monthly). Every module (Early Warning, Borrower 360, What-If) reads those
books read-only and keys its own data to their IDs, periods, units and
tenant. This package is that contract, in one place, so no module invents a
second version of it. It imports from the frozen Cockpit and never changes it.
"""
from backend.spine.books import (  # noqa: F401
    BOOKS,
    COMMON_QUARTER_END,
    Book,
    ID_PATTERNS,
    book,
    month_to_quarter,
    quarter_end_month,
    quarter_label,
    month_label,
)
