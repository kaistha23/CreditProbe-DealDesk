"""The global rating order, one module for every v5 module (INBOX Item 3, A2).

Best to worst: AAA, AA+, AA, AA-, A+, A, A-, BBB+, BBB, BBB-, BB+, BB, BB-,
B+, B, B-, CCC, CC, C, D. The standard scale runs CCC, CC, C (best to worst);
Anne's note had C, CC, CCC, so the choice is recorded in docs/STATUS.md for
her to confirm. Every chart, table, axis, legend and export that shows
ratings sorts with `rank` / `sort_key`. The frontend mirror is
frontend/src/lib/v5/ratings.ts; tests/v5/test_ratings.py keeps them equal.
"""
from __future__ import annotations

from typing import Any, Iterable

RATING_ORDER: tuple[str, ...] = (
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
    "B+", "B", "B-", "CCC", "CC", "C", "D",
)
_RANK = {r: i for i, r in enumerate(RATING_ORDER)}


def rank(rating: Any) -> int:
    """0 for AAA ... 19 for D; anything unknown sorts after D."""
    return _RANK.get(str(rating).strip().upper() if rating is not None else "", len(RATING_ORDER))


def sort_key(rating: Any) -> tuple[int, str]:
    return rank(rating), str(rating)


def ordered(ratings: Iterable[Any]) -> list[Any]:
    return sorted(ratings, key=sort_key)


def notches(frm: Any, to: Any) -> int:
    """Positive when `to` is worse than `frm`."""
    return rank(to) - rank(frm)


def sql_rank(column: str) -> str:
    """A DuckDB expression giving the rank of `column`, for ORDER BY."""
    whens = " ".join(f"WHEN '{r}' THEN {i}" for r, i in _RANK.items())
    return f"(CASE {column} {whens} ELSE {len(RATING_ORDER)} END)"


# ------------------------------------------------------------------ tables and axes (PLAN_R6 E3)
# The shared sort for every table, axis and legend whose category is a rating grade. The frontend
# mirror is `orderRatingTable` / `ratingAxis` in frontend/src/lib/v5/ratings.ts.

import re as _re

_RATING_NAME = _re.compile(r"rating|grade", _re.I)
# Rows a rating table may carry beside its grades; they keep their place after D.
_TOTAL_LIKE = _re.compile(r"^\s*(total|overall|all|book|portfolio|unrated|not rated|n/?a|other|others|—|-)?\s*$", _re.I)


def is_grade(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() in _RANK


def is_rating_name(name: Any) -> bool:
    """A column key or label that names a rating (rating, grade, internal_rating, rating_current ...)."""
    return bool(name) and bool(_RATING_NAME.search(str(name)))


def is_rating_values(values: Iterable[Any]) -> bool:
    """True when the values read as a rating category: at least two grades, and anything else a
    total-like row (Total, Overall, Unrated, blank)."""
    vals = list(values)
    grades = [v for v in vals if is_grade(v)]
    return len(grades) >= 2 and all(is_grade(v) or v is None or (isinstance(v, str) and _TOTAL_LIKE.match(v))
                                    for v in vals)


def in_order(sequence: Iterable[Any]) -> bool:
    """The grades of a label sequence appear best to worst (non-grades ignored)."""
    ranks = [rank(v) for v in sequence if is_grade(v)]
    return all(a <= b for a, b in zip(ranks, ranks[1:]))


def _key_of(col: Any) -> Any:
    return col.get("key") if isinstance(col, dict) else col


def rating_column(columns: list[Any], rows: list[Any]) -> Any:
    """The key (or index, for list rows) of the table's category column when it is a rating column, else None.

    The category column is the first one; a table sorts by rating only when that column holds grades, so a
    borrower list that merely shows a rating column keeps its own order."""
    if not columns or not rows:
        return None
    first = columns[0]
    key = _key_of(first)
    idx: Any = 0 if isinstance(rows[0], (list, tuple)) else key
    return idx if is_rating_values(r[idx] if isinstance(r, (list, tuple)) else r.get(idx) for r in rows) else None


def sort_rows(rows: list[Any], key: Any) -> list[Any]:
    """A copy of `rows` (dicts or lists) ordered by the grade in `key`, best first; stable; non-grades last."""
    def get(r: Any) -> Any:
        return r[key] if isinstance(r, (list, tuple)) else r.get(key)
    return sorted(rows, key=lambda r: rank(get(r)))


def order_table(columns: list[Any], rows: list[Any]) -> list[Any]:
    """`rows` in the global rating order when the table's first column is a rating column, else unchanged."""
    col = rating_column(columns, rows)
    return sort_rows(rows, col) if col is not None else list(rows)


def order_chart_rows(x: Any, rows: list[dict]) -> list[dict]:
    """Chart rows in the global rating order when the category (x) holds grades, else unchanged."""
    if rows and is_rating_values(r.get(x) for r in rows):
        return sort_rows(rows, x)
    return list(rows)


def axis_order(values: Iterable[Any]) -> list[Any]:
    """The category array for a rating axis or legend: the grades present, AAA to D, then anything else."""
    seen = list(dict.fromkeys(values))
    return sorted(seen, key=lambda v: (rank(v), seen.index(v)))
