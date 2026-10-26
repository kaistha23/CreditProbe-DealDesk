"""Round E for the Deal Desk conversation: which questions go engine first, and the worked examples for the rest.

Engine first (backend/convo/efficiency.py): a question the deterministic planner recognises -- every intent of
`convo.intent_of` reached by its own phrasing (optimise, explain, what-if, compare, stress, alternatives, breakeven,
draft, the R11 intents, portfolio headroom, a summary asked for as such) -- runs the planner's engine calls without
the model and gets one writing call. Anything else (the planner would only fall back to a summary or to sector
headroom) goes to the model's analysis loop, with the worked examples below in the cached head of its prompt.
"""
from __future__ import annotations

import re
from typing import Any

from backend.convo import efficiency

PORTFOLIO = re.compile(r"headroom|portfolio|concentration|rwa budget|which proposals|pipeline|how many proposals|breach a hard", re.I)
SUMMARY = re.compile(r"\bsummar|\boverview\b|tell me about (?:this|the) (?:deal|proposal)|brief me|what is this (?:deal|proposal)", re.I)

EXAMPLES = """\
1. "Why does the ask fail?" (a proposal open) -> get_proposal, compute_terms {terms_from: "ask"}, why_fails, then \
finalize_answer: the verdict in one line (lifetime RAROC against the hurdle, the binding limit), then the critical \
findings and the approval level, each figure as the tool returned it.
2. "What if the margin is 320 bps and the tenor 5 years?" -> compute_terms {changes: {margin_bps: 320, tenor_years: 5}} \
(one call; the engine merges the changes onto the thread's terms), then finalize_answer comparing RAROC, SVA and the \
approval level with the ask.
3. "Which pending construction deals clear the hurdle and what is their total ask?" (the desk) -> run_query \
"SELECT c.proposal_id, c.obligor_name, p.amount_sar_mn, c.lifetime_raroc, c.approval FROM proposal_checks c JOIN \
proposals p USING (proposal_id) WHERE p.sector ILIKE '%construct%' AND c.clears_hurdle ORDER BY p.amount_sar_mn DESC", \
then finalize_answer with the table; the total comes from the result's column summary, never added by hand.
4. "Which levers get it through on their own?" -> alternatives {} \
(never optimise unless asked to optimise or restructure), then finalize_answer naming the structures that clear and \
the single levers that clear alone."""


def known(question: str, ctx: Any) -> bool:
    """True when the deterministic planner recognises this question type (not merely its fallback)."""
    from backend.dealdesk_thread import convo

    has = bool((ctx.scope or {}).get("proposal_id"))
    intent = convo.intent_of(question, has)
    if intent == "portfolio":
        return bool(PORTFOLIO.search(question or ""))
    if intent == "summary":
        return bool(SUMMARY.search(question or ""))
    return True


efficiency.register("dealdesk", fast=known, examples=EXAMPLES)
