"""Does a module's own data still agree with the books?

Every v5 module keeps its own data (signals, scores, scenarios) keyed to the
books. `alignment` checks one module table against its book and returns a
list of human-readable failures (empty = in sync). The module sync tests call
it; nothing here writes anything.

Checked, per (exposure, period):
  * every module row names an exposure the book has in that period;
  * when `complete`, every book exposure in the module's periods is present;
  * the exposure's customer is the book's customer for that exposure;
  * the module's periods are book periods, and include the book's as-of;
  * each mapped money column equals the book's value (SAR million) within
    `money_tol` -- so a module cannot silently carry pre-rescale amounts.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from backend.spine.books import ID_PATTERNS, book


def read_book(domain_id: str, columns: Iterable[str]) -> pd.DataFrame:
    b = book(domain_id)
    return pd.read_parquet(b.path(b.exposure_relation), columns=list(dict.fromkeys(columns)))


def alignment(frame: pd.DataFrame, domain_id: str, *, period_col: str | None = None,
              exposure_col: str | None = None, customer_col: str | None = None,
              money: dict[str, str] | None = None, complete: bool = True,
              require_as_of: bool = True, money_tol: float = 1e-6) -> list[str]:
    b = book(domain_id)
    period_col = period_col or b.period_column
    exposure_col = exposure_col or b.exposure_key
    customer_col = customer_col or b.customer_key
    money = money or {}
    failures: list[str] = []

    for col, key in ((exposure_col, b.exposure_key), (customer_col, b.customer_key)):
        if col in frame:
            bad = frame.loc[~frame[col].astype(str).str.match(ID_PATTERNS[key]), col]
            if len(bad):
                failures.append(f"{col}: {len(bad)} values not in the book's {key} format, "
                                f"e.g. {bad.iloc[0]!r}")

    periods = set(frame[period_col].astype(str).unique())
    unknown = periods - set(b.periods)
    if unknown:
        failures.append(f"periods not in the book: {sorted(unknown)[:5]}")
    if require_as_of and b.as_of not in periods:
        failures.append(f"the book's as-of {b.as_of} is missing")

    cols = [b.period_column, b.exposure_key, b.customer_key, *money.values()]
    ref = read_book(domain_id, cols)
    ref = ref[ref[b.period_column].isin(periods)].rename(
        columns={b.period_column: period_col, b.exposure_key: exposure_col,
                 b.customer_key: "__book_customer"})
    merged = frame.merge(ref, on=[period_col, exposure_col], how="outer",
                         indicator=True, suffixes=("", "__book"))
    extra = merged[merged._merge == "left_only"]
    if len(extra):
        failures.append(f"{len(extra)} module rows name an exposure the book does not have "
                        f"in that period, e.g. {extra.iloc[0][exposure_col]} {extra.iloc[0][period_col]}")
    if complete:
        missing = merged[merged._merge == "right_only"]
        if len(missing):
            failures.append(f"{len(missing)} book exposures are missing from the module, "
                            f"e.g. {missing.iloc[0][exposure_col]} {missing.iloc[0][period_col]}")
    both = merged[merged._merge == "both"]
    if customer_col in both:
        wrong = both[both[customer_col].astype(str) != both["__book_customer"].astype(str)]
        if len(wrong):
            failures.append(f"{len(wrong)} rows attach an exposure to a different customer than the book")
    for module_col, book_col in money.items():
        book_side = book_col if book_col != module_col else f"{book_col}__book"
        diff = (both[module_col].astype(float) - both[book_side].astype(float)).abs()
        if (diff > money_tol).any():
            worst = both.loc[diff.idxmax()]
            failures.append(f"{module_col} differs from book {book_col} on {int((diff > money_tol).sum())} rows "
                            f"(worst {worst[exposure_col]} {worst[period_col]}: "
                            f"{worst[module_col]} vs {worst[book_side]})")
    return failures
