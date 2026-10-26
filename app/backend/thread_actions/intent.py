"""The "write a memo" intent (R16 t, M7), deterministic.

A request for a written document in any thread ("prepare a memo", "write a note to the CRO on this",
"draft a committee paper", "give me this as a Word document") is not answered in prose: CreditProbe writes the
Word document and offers the download. The same rule lives in frontend/src/lib/v5/thread-actions.ts
(`memoIntent`); tests/v5/thread_actions/test_intent.py and the frontend test share the case list.

    memo_intent(text) -> None | {"kind", "scope", "to", "question", "subject"}

kind      memo | note | paper (the word the user used; "word document", "docx" -> memo)
scope     thread (default) | answer ("this answer", "the last answer", "above answer")
to        the addressee if named ("to the CRO" -> "CRO")
question  what is left to ask first when the request also carries a question
          ("prepare a memo on which proposals breach a hard limit" -> "which proposals breach a hard limit");
          None when the request points at the thread ("on this", "of the above", "this thread")
subject   the subject words, for the memo title
"""
from __future__ import annotations

import re
from typing import Any

VERBS = r"(?:write|prepare|draft|make|create|produce|compose|put\s+together|turn\s+(?:this|it|that)\s+into|give\s+me|send\s+me|generate|do|need|want)"
NOUN = (r"(?P<noun>memo(?:randum)?|briefing\s+note|credit\s+note|board\s+note|note|paper|committee\s+paper|board\s+paper|"
        r"position\s+paper|word\s+(?:doc(?:ument)?|file|version|report)|docx)")
# "write a memo", "prepare me a short note", "draft the committee paper", "give me this as a word document"
_RX = re.compile(rf"\b{VERBS}\b(?:\s+(?:me|us|up))?(?:\s+(?:a|an|the|this|that|it|one|my|our))?"
                 rf"(?:\s+(?:as|in(?:to)?|into))?(?:\s+(?:a|an|the))?"
                 rf"(?:\s+(?:short|brief|quick|one[- ]page|formal|credit|risk|internal|full|detailed|summary|cro|board|committee|house[- ]style))*"
                 rf"\s+{NOUN}\b", re.I)
# "memo on X", "a note to the CRO", "word document of this" (no verb, but the request IS the document)
_BARE = re.compile(rf"^\s*(?:please\s+)?(?:a|an|the)?\s*(?:short\s+|brief\s+|quick\s+)?{NOUN}\s+(?:on|about|of|for|to|summari[sz]ing)\b", re.I)
_EXPORT = re.compile(r"\b(?:export|download|save)\b.{0,30}\b(?:as|to|in)\s+(?:a\s+)?(?:word|docx)\b", re.I)
# questions about an existing note are not a request to write one
_NOT = re.compile(r"^\s*(?:what|which|who|why|how|when|where|does|do|is|are|was|were|did|can\s+you\s+explain|explain|summari[sz]e\s+the)\b"
                  r"(?!.*\b(?:write|prepare|draft)\b)", re.I)
_ANSWER = re.compile(r"\b(?:this|that|the\s+last|the\s+above|above|previous|latest)\s+(?:answer|reply|response|result|table)\b", re.I)
_TO = re.compile(r"\b(?:to|for|addressed\s+to)\s+(?:the\s+)?(?P<to>cro|cfo|ceo|cco|cio|board(?:\s+risk\s+committee)?|credit\s+committee|"
                 r"risk\s+committee|committee|head\s+of\s+credit|chief\s+risk\s+officer|management|alco|rm|relationship\s+manager)\b", re.I)
_REFERS = re.compile(r"^\s*(?:(?:on|about|of|for|summari[sz]ing|covering)\s+)?(?:this|that|it|the\s+above|above|the\s+thread|this\s+thread|"
                     r"the\s+conversation|this\s+conversation|the\s+answers?|these\s+answers|what\s+we\s+(?:found|discussed)|"
                     r"(?:this|that|the\s+last|the\s+above|above|previous|latest)\s+(?:answer|reply|response|result|table))\b[\s.!?]*$", re.I)
_LEAD = re.compile(r"^\s*(?:on|about|of|for|summari[sz]ing|covering|explaining|showing|setting\s+out|that\s+(?:shows|explains|sets\s+out))\s+", re.I)
_TAIL = re.compile(r"\b(?:as\s+(?:a\s+)?word(?:\s+document)?|in\s+word|in\s+house\s+style|please|thanks?(?:\s+you)?)\b[\s.!?]*$", re.I)

KIND = {"memo": "memo", "memorandum": "memo", "note": "note", "paper": "paper", "docx": "memo"}


def _kind(noun: str) -> str:
    n = re.sub(r"\s+", " ", noun.lower())
    if n.startswith("word") or n == "docx":
        return "memo"
    last = n.split(" ")[-1]
    return KIND.get(last, "memo")


def memo_intent(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t or len(t) > 600:
        return None
    m = _RX.search(t) or _BARE.search(t)
    export = None if m else _EXPORT.search(t)
    if not m and not export:
        return None
    if m and _NOT.match(t) and not re.match(r"^\s*(?:can|could|would|will)\s+you\b", t, re.I):
        return None
    kind = _kind(m.group("noun")) if m else "memo"
    scope = "answer" if _ANSWER.search(t) else "thread"
    to_m = _TO.search(t)
    to = _addressee(to_m.group("to")) if to_m else ""
    rest = t[m.end():] if m else ""
    rest = _TO.sub(" ", rest, count=1) if to_m and to_m.start() >= (m.end() if m else 0) else rest
    rest = _TAIL.sub("", rest).strip(" ,.;:-")
    question: str | None = None
    subject = ""
    if rest and not _REFERS.match(rest):
        body = _LEAD.sub("", rest).strip(" ,.;:-?")
        body = re.sub(r"^(?:and\s+)?(?:the\s+)?(?:question\s+)?", "", body, flags=re.I).strip()
        if len(body.split()) >= 2:
            question = body[0].upper() + body[1:]
            if not question.endswith("?") and re.match(r"^(?:which|what|who|why|how|when|where|is|are|does|do|can|show|list|rank|compare)\b", body, re.I):
                question += "?"
            subject = body
    return {"kind": kind, "scope": scope, "to": to, "question": question, "subject": subject}


def _addressee(raw: str) -> str:
    r = re.sub(r"\s+", " ", raw.strip()).lower()
    caps = {"cro": "CRO", "cfo": "CFO", "ceo": "CEO", "cco": "CCO", "cio": "CIO", "alco": "ALCO", "rm": "RM"}
    if r in caps:
        return caps[r]
    if r == "chief risk officer":
        return "CRO"
    return " ".join(w.capitalize() if w not in ("of",) else w for w in r.split())
