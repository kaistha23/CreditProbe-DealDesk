"""Read-only access to the What-If data domain (`data/whatif_v5`).

    var/whatif_v5/<book>/<period>.parquet    one row per facility (corporate) or account (retail);
                                             rebuilt deterministically from the books and the MEVs
                                             (ops/whatif_build_domain.py, ~1 minute; too large to commit)
    data/whatif_v5/<book>/manifest.json      fields, provenance and per-period control totals (committed)
    data/whatif_v5/<book>/cycle_model.json   the credit-cycle model fitted on the books' history
    data/whatif_v5/mev/                      the Saudi MEVs (see `mev`)
"""
from __future__ import annotations

import functools
import json
import logging
import os
import pathlib
import threading
from typing import Any

import pandas as pd

from backend.whatif_v5 import paths

_log = logging.getLogger(__name__)

ROOT = pathlib.Path(os.environ.get("WHATIF_DOMAIN_META") or (paths.V5 / "data" / "whatif_v5")).resolve()
FILES = pathlib.Path(os.environ.get("WHATIF_DOMAIN") or (paths.V5 / "var" / "whatif_v5")).resolve()
BOOKS = ("corporate", "retail")
SCENARIOS = ("base", "upturn", "downturn")
YEARS = (1, 2, 3, 4, 5)
_LOCK = threading.Lock()


class DomainError(ValueError):
    pass


def book_dir(domain: str) -> pathlib.Path:
    if domain not in BOOKS:
        raise DomainError(f"'{domain}' is not a book. The books are corporate and retail.")
    return ROOT / domain


def files_dir(domain: str) -> pathlib.Path:
    book_dir(domain)
    return FILES / domain


@functools.lru_cache(maxsize=4)
def manifest(domain: str) -> dict[str, Any]:
    path = book_dir(domain) / "manifest.json"
    if not path.exists():
        _log.warning("What-If domain not built: %s missing (ops/whatif_build_domain.py builds it)", path)
        raise DomainError(f"The What-If {domain} data is still being prepared. Please try again in a moment.")
    return json.loads(path.read_text())


def periods(domain: str) -> list[str]:
    return list(manifest(domain)["periods"])


def as_of(domain: str) -> str:
    return periods(domain)[-1]


def resolve_period(domain: str, period: str = "") -> str:
    known = periods(domain)
    said = str(period or "").strip()
    if not said:
        return known[-1]
    if said not in known:
        raise DomainError(f"{said} is not a period of the {domain} What-If domain. It runs {known[0]} to {known[-1]}.")
    return said


@functools.lru_cache(maxsize=12)
def _frame(domain: str, period: str) -> pd.DataFrame:
    path = files_dir(domain) / f"{period}.parquet"
    if not path.exists():
        _log.warning("What-If domain file missing: %s (ops/whatif_build_domain.py builds it)", path)
        raise DomainError(f"The What-If {domain} data for {period} is still being prepared. Please try again in a moment.")
    with _LOCK:
        return pd.read_parquet(path)


def frame(domain: str, period: str = "") -> pd.DataFrame:
    """A private copy of the domain at a period."""
    return _frame(domain, resolve_period(domain, period)).copy()


def history(domain: str, columns: list[str]) -> pd.DataFrame:
    """Selected columns over every period (for likelihood and model training)."""
    out = []
    for p in periods(domain):
        f = _frame(domain, p)
        out.append(f[[c for c in columns if c in f.columns]].assign(period=p))
    return pd.concat(out, ignore_index=True)


def pd_cols(scenario: str) -> list[str]:
    return [f"pd_{scenario}_y{t}" for t in YEARS]


def lgd_cols(scenario: str) -> list[str]:
    return [f"lgd_{scenario}_y{t}" for t in YEARS]
