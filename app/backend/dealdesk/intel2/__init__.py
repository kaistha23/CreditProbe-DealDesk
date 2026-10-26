"""R14 Session i: Deal Desk intelligence D6-D13 (PLAN_R14 "i", the plan doc's Deal Desk table).

    frontier.py     D6  negotiation frontier: what each concession is worth in bps, three counter-offers ranked
    premortem.py    D7  default pre-mortem: the three most likely ways the deal goes bad and the trigger that warns first
    precedent.py    D8  precedent explorer: the five closest past deals, decision, conditions, performance, similarity basis
    pricing.py      D9  pricing benchmark: margin percentile against the book for the same rating/sector/product/tenor; breakeven
    revenue.py      D10 revenue truth check: reported revenue vs account turnover here and at other banks (open banking), VAT
    renewal_diff.py D11 renewal diff: what changed since the last approval
    contagion.py    D12 group contagion on the deal: connected parties in Stage 3 or litigation, exposure, effect on this deal
    rehearsal.py    D13 committee rehearsal (K29): questions, suggested answers and evidence on the selected structure

Every engine is deterministic (N4): same inputs, same output; every number is a figure {value, unit, source} whose
source resolves to a Data Domains row (N3/N5); every panel opens with a plain-words block (common.plain).
"""
from __future__ import annotations

from typing import Any, Callable


def _lazy(mod: str, fn: str) -> Callable[..., dict[str, Any]]:
    def call(*a: Any, **k: Any) -> dict[str, Any]:
        m = __import__(f"backend.dealdesk.intel2.{mod}", fromlist=[fn])
        return getattr(m, fn)(*a, **k)
    return call


#: code -> (url key, engine(pid, which="selected", terms=None))
ENGINES: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
    "D6": ("frontier", _lazy("frontier", "frontier")),
    "D7": ("premortem", _lazy("premortem", "premortem")),
    "D8": ("precedents", _lazy("precedent", "precedent")),
    "D9": ("pricing", _lazy("pricing", "pricing")),
    "D10": ("revenue", _lazy("revenue", "revenue")),
    "D11": ("renewal-diff", _lazy("renewal_diff", "renewal_diff")),
    "D12": ("contagion", _lazy("contagion", "contagion")),
    "D13": ("rehearsal", _lazy("rehearsal", "rehearse")),
}
