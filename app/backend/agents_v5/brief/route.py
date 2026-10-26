"""Where a typed question goes (PLAN_R13 Session H, R12_FEEDBACK J2 (b)): Noor answers any question.

Noor used to answer only about lines in its brief and refused everything else ("I could not tie that to a line in
today's brief"). Now every question goes to an engine that already exists, and nothing is refused:

    brief     Why? / What should we do? / Who drives it? / Show me on a line of today's brief (Noor's own answers)
    whatif    a scenario or stress question: the What-If engine opens a thread on it
    lenses    a request to build a dashboard or lens: the Lenses engine builds it
    dealdesk  a question about a deal, proposal or the pipeline: Deal Desk's desk thread answers it
    cockpit   everything else: the Cockpit engine (ECL decomposition, staging, movements, early warning, policy,
              "who are you?", auditor and regulator queries through the Cockpit's own queries hand-off)

Deterministic (N3): a cue table, the same one the browser uses (`frontend/src/components/noor/noor-route.ts`, kept
equal by `tests/v5/noor/test_route.py`). The order of the table is the order of precedence.
"""
from __future__ import annotations

import re
from typing import Any

#: (engine, cue patterns). First engine with a matching cue wins; no match is the Cockpit.
ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lenses", (
        r"\b(build|create|make|design|set up)\b.{0,40}\b(dashboard|lens)\b",
        r"\blens(es)? (for|on|of)\b",
        r"\bdashboard (for|on|of)\b",
    )),
    ("whatif", (
        r"\bwhat[- ]if\b",
        r"\bstress(ed|ing)?\b",
        r"\bscenarios?\b",
        r"\bshock(s|ed)?\b",
        r"\b(oil|brent) (price )?(falls?|drops?|declines?|crash(es)?)\b",
        r"\b(gdp|unemployment|rates?) (falls?|rises?|drops?|contracts?|shocks?)\b",
        r"\b(mild|moderate|severe) (downturn|recession|scenario)\b",
        r"\bsensitivity\b",
    )),
    ("dealdesk", (
        r"\bdeal desk\b",
        r"\b(proposal|proposals|credit application|term sheet)\b",
        r"\b(pipeline|new deals?|this deal|the deal)\b",
        r"\braroc\b.{0,30}\b(deal|proposal|pricing|price)\b",
        r"\b(price|pricing) (this|the|a) (deal|facility|loan)\b",
        r"\bcommittee paper\b",
    )),
)

ENGINES: dict[str, dict[str, str]] = {
    "cockpit": {"label": "the Cockpit", "verb": "Answering in the Cockpit"},
    "whatif": {"label": "What-If", "verb": "Running it in What-If"},
    "lenses": {"label": "Lenses", "verb": "Building it in Lenses"},
    "dealdesk": {"label": "Deal Desk", "verb": "Asking Deal Desk"},
    "brief": {"label": "today's brief", "verb": "Answering from today's brief"},
}

_COMPILED = tuple((e, tuple(re.compile(p, re.I) for p in pats)) for e, pats in ROUTES)

#: What a question asks of a brief line (the same words as `intentOf` in noor-model.ts).
INTENTS: tuple[tuple[str, str], ...] = (
    ("drivers", r"\b(who drives|who is behind|which (names|borrowers)|names behind)\b"),
    ("options", r"\b(what should|what do we|options?|recommend|do about)\b"),
    ("why", r"\b(why|explain|how come|what drove|driver)\b"),
    ("show", r"\b(show|open|take me|go to|list)\b"),
    ("brief", r"\b(brief|today|morning|what's new|whats new|since yesterday)\b"),
)


def intent_of(text: str) -> str:
    t = text.lower()
    for name, pat in INTENTS:
        if re.search(pat, t):
            return name
    return "unknown"


#: Words every book question shares with every line; they do not tie a question to a line (equal to noor-route.ts).
STOP = frozenset({"stage", "stages", "sector", "sectors", "limit", "limits", "book", "books", "today",
                  "borrower", "borrowers", "coverage", "quarter", "month", "what", "which", "about", "with", "this", "that",
                  "there", "their", "from", "have", "does", "into", "more", "much", "many", "show", "open", "please",
                  "brief", "should", "would", "could", "drives", "driving", "explain"})
BOOK_WORDS = re.compile(r"\b(ecl|stage|pd|lgd|ead|provision|exposure)\b", re.I)


def _words(s: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if len(w) > 3 and w not in STOP}


def match_line(text: str, lines: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int, bool]:
    """The brief line sharing most words (over three letters, not in STOP) with the question, how many it shares, and
    whether the line's name (a sector, a borrower) is among them."""
    q = _words(text)
    best, score, named = None, 0, False
    for it in lines:
        name = str((it.get("entity") or {}).get("name", "") or "")
        w = _words(f"{it.get('title', '')} {name} {it.get('source_label', '')}")
        s = len(q & w)
        has_name = bool(q & _words(name))
        if s > score or (s == score and s > 0 and has_name and not named):
            best, score, named = it, s, has_name
    return best, score, named


def engine_for(text: str) -> str:
    for engine, pats in _COMPILED:
        if any(p.search(text) for p in pats):
            return engine
    return "cockpit"


def route(question: str, lines: list[dict[str, Any]] | None = None, *, domain: str = "corporate",
          context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Where `question` is answered. Never a refusal: an empty question is the only thing that is not routed.

    R15 a (L9): with a page `context` (a deal page), the page comes first: a question about the deal or the stress run on
    screen is answered there (engine "here", POST /api/v1/noor/here); a book question goes on as before, with `away`
    saying why it left the page."""
    q = " ".join(str(question or "").split())
    if not q:
        return {"engine": "none", "question": "", "reason": "Nothing was asked."}
    if context:
        from backend.agents_v5.brief import here
        h = here.route_here(q, context)
        if h["here"]:
            return {"engine": "here", "intent": h["topic"], "item_id": None, "question": q, "label": "this page",
                    "verb": "Answering on the page", "reason": h["reason"], "context": context}
        if h["reason"]:
            out = route(q, lines, domain=domain)
            return {**out, "away": h["reason"]}
    intent = intent_of(q)
    hit, shared, named = match_line(q, lines or [])
    # A brief line answers only when the question is plainly about it: an action word (Why?, What should we do?, Who
    # drives it?, Show me) with the line's name or two of its words, or three of its words and no book measure.
    action = intent in ("why", "options", "drivers", "show")
    if hit is not None and ((action and (named or shared >= 2)) or (shared >= 3 and not BOOK_WORDS.search(q))) \
            and engine_for(q) == "cockpit":
        return {"engine": "brief", "intent": intent if intent != "unknown" else "why", "item_id": hit.get("id"),
                "question": q, **ENGINES["brief"],
                "reason": f"About the brief line “{str(hit.get('title', ''))[:80]}”."}
    if intent == "brief" and not BOOK_WORDS.search(q):
        return {"engine": "brief", "intent": "brief", "item_id": None, "question": q, **ENGINES["brief"],
                "reason": "Asks for today's brief."}
    engine = engine_for(q)
    book = "retail" if domain == "retail" else "corporate"
    href = {"cockpit": f"/?tab=ask&q={_qs(q)}", "whatif": f"/what-if?domain={book}",
            "lenses": "/lenses" + ("?book=retail" if book == "retail" else ""),
            "dealdesk": f"/deal-desk?thread=desk&q={_qs(q)}"}[engine]
    return {"engine": engine, "intent": intent, "item_id": None, "question": q, "href": href, **ENGINES[engine],
            "reason": {"cockpit": "The Cockpit engine answers any question on the book, with a Trace.",
                       "whatif": "A scenario or stress question: What-If runs it on the book.",
                       "lenses": "A request for a dashboard: Lenses builds it.",
                       "dealdesk": "About a deal or the pipeline: Deal Desk answers it."}[engine]}


def _qs(q: str) -> str:
    from urllib.parse import quote
    return quote(q, safe="")
