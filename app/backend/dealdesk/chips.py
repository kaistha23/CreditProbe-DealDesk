"""PLAN_R12 Session G, I9: Deal Desk follow-up chips in banker language only.

The Ask Deal Desk thread offered chips such as "Run pipeline_optimise…" or "…with pipeline_te…": a model's suggestion
naming an internal tool, cut at 60 characters. `banker()` rewrites a suggestion into the desk's own words (tool names to
the action a banker would ask for), drops whatever still reads as code, and shortens at a word boundary, never mid-word.
`clean()` is applied to every Deal Desk answer's suggestions; when nothing usable is left it offers the intent's defaults.
"""
from __future__ import annotations

import re
from typing import Any

MAX_LABEL = 60

#: internal tool or intent name -> what a banker asks for
TOOL_WORDS: dict[str, str] = {
    "pipeline_optimise": "Optimise the pipeline", "pipeline_optimize": "Optimise the pipeline",
    "pipeline_test": "Test against the pipeline", "stress_lab": "Run the Stress Lab", "stress": "Stress this deal",
    "forward_risk": "Show the forward risk", "ews_deal": "Check early warning on this deal", "committee_sheet": "Draft the committee sheet",
    "review_memo": "Review the memo", "review": "Review the memo", "optimise": "Optimise", "optimize": "Optimise",
    "compute_terms": "Price these terms", "get_proposal": "Show the proposal", "headroom": "How much headroom is left?",
    "explain_constraint": "Explain the binding limit", "compare": "Compare the counter-offers", "alternatives": "Show the alternatives",
    "breakeven": "What margin clears the hurdle?", "portfolio": "Show the portfolio view", "draft": "Draft the credit risk opinion",
}
_SNAKE = sorted((k for k in TOOL_WORDS if "_" in k), key=len, reverse=True)
#: a tool name inside a sentence: any snake_case tool, or a one-word tool in backticks or called with ()
_TOOL_RE = re.compile(r"`(" + "|".join(sorted(map(re.escape, TOOL_WORDS), key=len, reverse=True)) + r")`(\(\))?|\b("
                      + "|".join(_SNAKE) + r")\b(\(\))?|\b(" + "|".join(k for k in TOOL_WORDS if "_" not in k) + r")\(\)", re.I)
#: what still reads as code after the rewrite: snake_case, camelCase, dotted paths, brackets, ids in braces, JSON
_CODE = re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b|\b[a-z]+[A-Z][a-zA-Z]+\b|\b\w+\.\w+\(|[{}\[\]]|\(\)|\b(?:args?|json|tools?|API|endpoint)\b")

DEFAULTS: dict[str, list[str]] = {
    "optimise": ["Compare the counter-offers", "How does this hold if they're downgraded two notches?"],
    "pipeline_optimise": ["Test against the pipeline", "Which proposals breach a hard limit?"],
    "pipeline_test": ["Optimise the pipeline", "What is the chance of Stage 2 next quarter?"],
    "stress_lab": ["What breaks first?", "Test against the pipeline"],
    "": ["Why does the ask fail?", "Optimise", "Draft the credit risk opinion"],
}
NO_PROPOSAL = ["Which proposals breach a hard limit?", "How much sector headroom is left?", "Optimise the pipeline"]


def _shorten(s: str, n: int = MAX_LABEL) -> str:
    if len(s) <= n:
        return s
    cut = s[:n + 1].rsplit(" ", 1)[0].rstrip(" ,;:–-")
    for tail in (" with", " and", " the", " a", " of", " for", " to", " on", " in", " at", " by", " vs"):
        if cut.lower().endswith(tail):
            cut = cut[: -len(tail)]
    return cut.rstrip(" ,;:–-") + "…"


def _phrase(m: re.Match[str], s: str) -> str:
    key = next(g for g in (m.group(1), m.group(3), m.group(5)) if g).lower()
    words = TOOL_WORDS[key]
    if m.start() == 0:
        return words
    prev = s[:m.start()].lower()
    # "test against pipeline_test" -> "test against the pipeline": drop the words the sentence already says
    for w in words.lower().split()[:2]:
        if prev.rstrip().endswith(w):
            return words.lower().split(w, 1)[1].strip() or words.lower()
    if words.endswith("?"):
        return "\x00"  # a question cannot sit inside another sentence: the chip is dropped
    w = words.lower().split(" ", 1)
    # inside a sentence the tool is a thing, not an action: "with stress_lab" -> "with the stress lab"
    return w[1] if len(w) == 2 and w[0] in _VERBS and not w[1].endswith("?") else words.lower()


_VERBS = {"run", "show", "check", "draft", "review", "test", "optimise", "price", "stress", "compare", "explain"}


def banker(text: Any) -> dict[str, str] | None:
    """One suggestion in banker language, as {label, send}; None when it cannot be said without internal names."""
    if isinstance(text, dict):
        text = text.get("send") or text.get("label") or ""
    s = " ".join(str(text or "").split())
    if not s:
        return None
    m = re.fullmatch(r"(?:run|call|use|invoke|execute)\s+`?(\w+)`?(?:\(\))?(.*)", s, re.I)
    if m and m.group(1).lower() in TOOL_WORDS and not m.group(2).strip(" .…"):
        s = TOOL_WORDS[m.group(1).lower()]
    else:
        lead = re.match(r"(?:run|call|use|invoke|execute)\s+", s, re.I)
        if lead and _TOOL_RE.match(s, lead.end()):
            s = s[lead.end():]
        s = _TOOL_RE.sub(lambda x: _phrase(x, s), s).strip()
        s = s[:1].upper() + s[1:]
    s = s.rstrip(" .…")
    if not s.endswith("?") and s.lower().startswith(("why", "what", "how", "which", "who", "when", "can", "does", "is ")):
        s += "?"
    if "\x00" in s or _CODE.search(s) or re.search(r"\w…$|\b\w{1,2}…", s) or len(s) < 4:
        return None
    return {"label": _shorten(s), "send": s}


def clean(suggestions: list[Any] | None, intent: str = "", has_proposal: bool = True, limit: int = 4) -> list[dict[str, str]]:
    """Every suggestion rewritten or dropped; the intent's defaults fill in when nothing usable is left. No duplicates."""
    out, seen = [], set()
    for s in suggestions or []:
        b = banker(s)
        if b and b["send"].lower() not in seen:
            seen.add(b["send"].lower())
            out.append(b)
    if not out:
        for d in (DEFAULTS.get(intent) or DEFAULTS[""]) if has_proposal else NO_PROPOSAL:
            b = banker(d)
            if b and b["send"].lower() not in seen:
                seen.add(b["send"].lower())
                out.append(b)
    return out[:limit]
