"""Portfolio RAROC at origination -> the Book's **RAROC drift** view (PLAN_R12 §1.6, I7; was PLAN_R9 E4).

Kept for the existing `/portfolio_raroc` endpoint (additive only, N1): the same fields as before, now computed by the
Book (`backend.dealdesk.book.drift`) from registered Data Domains relations only (origination, Early Warning,
ECL runs, deposits). The R9 deterministic fixture fallback is gone (PLAN_R12 §0): if a domain is not readable the
endpoint fails rather than inventing numbers.

The RM cut: relationship managers are not in Data Domains; `by_rm` is cut by region (the RM teams are regional) and
says so in `rm_basis`.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.book import drift


def run(ref: str | None = None) -> dict[str, Any]:
    s = drift.summary(ref)
    f = drift.frame(ref)
    f = f[~f.defaulted]
    out = dict(s)
    out["source"] = "Data Domains: origination.orig_facility, ews.corp_exposure, ecl_runs.ecl_facility, deposits (Book RAROC drift)"
    out["by_rm"] = drift._cut(f, "region")  # noqa: SLF001
    out["rm_basis"] = "region (relationship managers are not in Data Domains; RM teams are regional)"
    out["title"] = "RAROC drift"
    out["powered_by"] = {"pack": "P7", "rule": "P7-PRO-01"}
    return out
