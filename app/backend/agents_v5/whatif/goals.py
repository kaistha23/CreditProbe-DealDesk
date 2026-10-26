"""Goal detection for the What-If chat (PLAN_R11_AGENTS W1, W3).

A *goal* asks for judgement over several scenarios ("what would a regional slowdown do to us and what should we
do?", "are we provisioned enough for an oil shock?", "what management overlay is defensible for construction?").
A *single scenario* names its shocks ("oil -40%", "PD +30% for Construction") or asks about the data; it keeps the
existing What-If flow untouched. Detection is deterministic and mirrored in the UI
(`frontend/src/components/v5/whatif/agent-goal.ts`); both are tested on the same corpus
(`tests/v5/agents_whatif/goal_corpus.json`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.whatif_v5.chat.language import PRODUCT_SYNONYMS, SECTOR_SYNONYMS

# Strong goal phrases: these are goals even when a shock size is given.
STRONG = [
    r"\bwhat should (we|i|the bank)\b",
    r"\bhow should (we|the bank) (respond|react|prepare|mitigate|act)\b",
    r"\bwhat (management )?actions?\b",
    r"\bwhat can we do\b",
    r"\b(management|post[- ]model|judg(e)?mental)\s+overlays?\b",
    r"\boverlays?\b.{0,40}\b(defensible|justif\w*|appropriate|warranted|size|how (much|big))\b",
    r"\b(provision\w*|reserv\w*|cover\w*)\s+(enough|adequate\w*|sufficient\w*)\b",
    r"\b(enough|adequate|sufficient)\s+(provision\w*|reserves?|ecl|coverage)\b",
    r"\b(adequacy|sufficiency) of (our |the )?(provision\w*|ecl|coverage|reserves?)\b",
    r"\bsensitivity (set|analysis|pack)\b",
]
# Weak goal phrases: goals only when no explicit shock size is given.
WEAK = [
    r"\bwhat (would|will|could|might|does|do)\b.{0,80}\b(do to|mean for|cost)\s+(us|the bank|our\b|the book|the portfolio)",
    r"\bhow (badly )?(would|will|could) .{0,60}\b(hit|affect|impact|hurt)\s+(us|the bank|our\b|the book|the portfolio)",
    r"\bstress[- ]test (the|our) (book|portfolio|bank)\b",
    r"\bhow resilient\b",
    r"\b(range|set) of scenarios\b",
]
SIZE = re.compile(r"[-+−–]?\s?\d+(?:\.\d+)?\s*(%|pp\b|bps\b|bp\b|notch\w*|sd\b|percent|basis points|x\b)|\b[x×]\s?\d", re.I)

THEMES: dict[str, str] = {
    "oil": r"\b(oil|brent|crude|opec)\b",
    "rates": r"\b(rates? (hike|hikes|rise|rises|shock|up|stay)|interest rates?|policy rates?|repo|saibor|tightening|higher rates|higher for longer)\b",
    "real_estate": r"\b(real estate|property|house prices?|housing|re prices?)\b",
    "slowdown": r"\b(slowdown|slow ?down|recession|downturn|contraction|gdp|growth shock|regional|gcc|economic)\b",
    "unemployment": r"\b(unemployment|job losses|layoffs)\b",
}
KINDS = ("impact_and_actions", "provision_adequacy", "overlay", "sensitivity")


@dataclass
class Goal:
    text: str
    is_goal: bool
    kind: str = ""                         # one of KINDS
    themes: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    has_size: bool = False
    why: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _find(patterns: list[str], text: str) -> str:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return ""


def segments_in(text: str, domain: str = "corporate") -> list[str]:
    low = f" {text.lower()} "
    syn = SECTOR_SYNONYMS if domain == "corporate" else PRODUCT_SYNONYMS
    out: list[str] = []
    for word, seg in sorted(syn.items(), key=lambda kv: -len(kv[0])):
        if word == "it":
            continue                      # "it" is a pronoun far more often than the IT sector
        if re.search(rf"\b{re.escape(word)}\b", low) and seg not in out:
            out.append(seg)
    return out


def detect(text: str, domain: str = "corporate") -> Goal:
    t = (text or "").strip()
    if not t or t.startswith("::"):
        return Goal(text=t, is_goal=False)
    has_size = bool(SIZE.search(t))
    strong = _find(STRONG, t)
    weak = "" if has_size else _find(WEAK, t)
    if not (strong or weak):
        return Goal(text=t, is_goal=False, has_size=has_size)
    low = t.lower()
    themes = [k for k, p in THEMES.items() if re.search(p, low)]
    segs = segments_in(t, domain)
    if "real_estate" in themes and segs == ["Real Estate"]:
        segs = []                          # "a real-estate correction" is a theme; the book is in scope
    if re.search(r"overlay", low):
        kind = "overlay"
    elif re.search(r"provision|reserv|cover|adequa|sufficien|enough", low):
        kind = "provision_adequacy"
    elif re.search(r"sensitivity", low):
        kind = "sensitivity"
    else:
        kind = "impact_and_actions"
    return Goal(text=t, is_goal=True, kind=kind, themes=themes or ([] if segs else ["slowdown"]), segments=segs,
                has_size=has_size, why=(strong or weak))


__all__ = ["Goal", "KINDS", "THEMES", "detect", "segments_in"]
