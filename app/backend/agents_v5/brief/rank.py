"""Deterministic ranking across sources (N6): the same facts always give the same brief, in the same order.

score = severity weight × persona weight of the source × (1 + materiality term) × urgency × recency, plus a bonus when
the line is assigned to the reader. Ties break on the line id, so the order never depends on read order.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from backend.agents_v5.brief.items import Item

SEVERITY_W = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}

#: How much each persona cares about each source (0 drops it from that brief).
PERSONA_W: dict[str, dict[str, float]] = {
    "cro": {"regulatory_breach": 1.0, "sector_appetite": 1.0, "cockpit_attention": 0.95, "approval": 1.0,
            "large_exposure": 0.9, "tier_high": 0.9, "ews_triage": 0.85, "dd_queue": 0.7, "deadline": 0.8,
            "lenses_alert": 0.75, "renewal": 0.6, "condition_due": 0.5, "dd_query": 0.2},
    "reviewer": {"dd_queue": 1.0, "approval": 1.0, "dd_query": 0.85, "sector_appetite": 0.8, "tier_high": 0.75,
                 "condition_due": 0.7, "renewal": 0.65, "large_exposure": 0.6, "ews_triage": 0.5,
                 "cockpit_attention": 0.4, "regulatory_breach": 0.3, "deadline": 0.3, "lenses_alert": 0.3},
    "rm": {"dd_query": 1.0, "condition_due": 1.0, "renewal": 0.95, "dd_queue": 0.85, "tier_high": 0.8,
           "sector_appetite": 0.6, "approval": 0.5, "ews_triage": 0.3, "cockpit_attention": 0.0,
           "regulatory_breach": 0.0, "deadline": 0.0, "lenses_alert": 0.0, "large_exposure": 0.2},
    "analyst": {"deadline": 1.0, "ews_triage": 1.0, "condition_due": 0.85, "dd_queue": 0.7, "lenses_alert": 0.75,
                "regulatory_breach": 0.7, "approval": 0.8, "cockpit_attention": 0.6, "tier_high": 0.6,
                "sector_appetite": 0.5, "dd_query": 0.5, "renewal": 0.4, "large_exposure": 0.4},
}


def _days_to(due: str | None, today: date) -> int | None:
    if not due:
        return None
    try:
        return (date.fromisoformat(str(due)[:10]) - today).days
    except ValueError:
        return None


def score(item: Item, persona: str, today: date, me: str = "") -> float:
    w = PERSONA_W.get(persona, PERSONA_W["analyst"]).get(item.source, 0.3)
    if w <= 0 or persona not in item.audiences:
        return 0.0
    s = SEVERITY_W.get(item.severity, 2.0) * w
    m = item.materiality_sar_mn
    if m and m > 0:
        s *= 1.0 + min(1.0, math.log10(1.0 + m) / 4.0)  # 10m -> +0.26, 1bn -> +0.75, capped at 2x
    d = _days_to(item.due, today)
    if d is not None:
        s *= 1.5 if d < 0 else (1.3 if d <= 7 else (1.1 if d <= 30 else 1.0))
    if me and item.owner and item.owner.lower() == me.lower():
        s *= 1.4
    return round(s, 6)


def rank(items: list[Item], persona: str, today: date, me: str = "") -> list[tuple[Item, float]]:
    scored = [(i, score(i, persona, today, me)) for i in items]
    scored = [(i, s) for i, s in scored if s > 0]
    # One line per entity: the Cockpit card and the appetite line about the same sector are the same news.
    seen: dict[str, int] = {}
    out: list[tuple[Item, float]] = []
    for i, s in sorted(scored, key=lambda t: (-t[1], t[0].id)):
        key = f"{i.entity.get('kind')}:{str(i.entity.get('name') or i.entity.get('id') or i.id).lower()}"
        if i.entity.get("kind") in ("sector", "segment"):
            key = f"sector:{str(i.entity.get('name') or '').lower()}"
        if key in seen:
            prev = out[seen[key]][0]
            prev.trace.extend(t for t in i.trace if t)
            if i.source == "cockpit_attention":
                prev.numbers.extend(n for n in i.numbers if n not in prev.numbers)
                prev.entity.setdefault("cockpit_item", i.id.split(":", 1)[1])
            continue
        seen[key] = len(out)
        out.append((i, s))
    return out


def as_rows(ranked: list[tuple[Item, float]]) -> list[dict[str, Any]]:
    return [{**i.to_dict(), "rank": n + 1, "score": s} for n, (i, s) in enumerate(ranked)]
