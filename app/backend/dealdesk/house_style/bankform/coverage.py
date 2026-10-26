"""Coverage validator: a paper (or any proposal's list of headings) must hold every anatomy section, and a CreditProbe paper
every CreditProbe section. A missing section fails the check.

    coverage.check(paper)                      # [] or ["missing section 9 Status of financed projects", ...]
    coverage.check_headings(["Action requested", ...], creditprobe=False)
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.house_style.bankform import registry


def _norm(s: str) -> str:
    return re.sub(r"[^a-z&]+", " ", re.sub(r"^\s*\d+[.)]?\s*", "", str(s).lower())).strip()


def match(heading: str) -> str | None:
    """The registry key a heading stands for (exact heading first, then the aliases)."""
    h = _norm(heading)
    for s in registry.SECTIONS:
        if h == _norm(s.heading):
            return s.key
    for s in registry.SECTIONS:
        if any(_norm(a) and _norm(a) in h for a in (s.aliases or ())):
            return s.key
    return None


def check(paper: dict[str, Any], creditprobe: bool = True) -> list[str]:
    have = {s["key"] for s in paper.get("sections", []) if s.get("blocks")}
    want = paper.get("required") or (registry.ANATOMY + (registry.CREDITPROBE if creditprobe else []))
    out = []
    for k in want:
        if k not in have:
            s = registry.BY_KEY[k]
            out.append(f"missing section {s.n or 'CP'} {s.heading}")
    return out


def check_headings(headings: list[str], creditprobe: bool = False) -> list[str]:
    have = {match(h) for h in headings} - {None}
    want = registry.ANATOMY + (registry.CREDITPROBE if creditprobe else [])
    return [f"missing section {registry.BY_KEY[k].n or 'CP'} {registry.BY_KEY[k].heading}" for k in want if k not in have]
