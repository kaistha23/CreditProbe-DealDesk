"""A gold-standard proposal (an example the bank considers ideal) against how CreditProbe writes today.

    cmp = compare(text, sections)   # {"differences": [...], "today": {...}, "gold": {...}}

"Today" is the bank-form credit proposal as the system writes it now, with the bank's rules in force applied (a sample deal,
R12-TWA, drafted deterministically), so a difference already covered by a rule does not come back. Each difference names
what the system does, what the gold standard does, and the rule that would close it:
    order      a section the gold standard places elsewhere            -> section_order rule
    missing    a section the gold standard has and the system lacks     -> include_section rule
    heading    a section the gold standard heads differently            -> heading rule
    units      how millions and percentages are written                 -> units rule
    wording    a term the gold standard uses where the system uses another -> wording rule
    tone       sentence length, hedges, first person                    -> instruction rule
"Apply these?" stores the chosen rules for the bank (origin gold:<id>) and adds the document to the house-style corpus as an
exemplar, so the house profile learns from it too.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.rules import apply as AP

SAMPLE = "R12-TWA"
_TODAY: dict[str, Any] = {}
TERMS = [("obligor", "borrower"), ("obligor", "client"), ("obligor", "customer"), ("facility", "loan"), ("the Bank", "we"),
         ("Credit Committee", "committee")]
HEDGES = re.compile(r"\b(may|might|could|appears?|seems?|possibly|perhaps|likely)\b", re.I)
FIRST = re.compile(r"\b(we|our|us|I)\b")
MONEY = re.compile(r"\b(?:SAR|AED|USD)\s?\d[\d,]*(?:\.\d+)?\s?(mn|million|m|bn)\b")


def _an(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "")) if len(s.split()) >= 4]


def _style(text: str) -> dict[str, Any]:
    sents = _sentences(text)
    words = sum(len(s.split()) for s in sents) or 1
    money = [m.group(1) for m in MONEY.finditer(text)]
    style = max(set(money), key=money.count) if money else None
    pct_word = len(re.findall(r"\d\s?per ?cent", text, re.I))
    pct_sign = len(re.findall(r"\d\s?%", text))
    return {"sentence_words": round(words / max(1, len(sents)), 1), "sentences": len(sents),
            "hedges_per_1000": round(1000 * len(HEDGES.findall(text)) / words, 1), "first_person": len(FIRST.findall(text)),
            "money_style": style, "money_counts": {k: money.count(k) for k in set(money)},
            "percent_style": ("per cent" if pct_word > pct_sign else "%") if (pct_word or pct_sign) else None,
            "terms": {t: len(re.findall(rf"\b{re.escape(t)}\b", text, re.I if t not in ("we",) else 0)) for pair in TERMS for t in pair}}


def today() -> dict[str, Any]:
    """The system's proposal today (structure and style), with the bank's rules applied."""
    if _TODAY:
        return _TODAY
    import json

    from backend.dealdesk import paths
    from backend.dealdesk.house_style.bankform import paper as bf
    from backend.dealdesk.rules import hook
    from backend.dealdesk.rules import store as rstore
    sig = "|".join(f"{r['id']}:{r['version']}" for r in rstore.for_document("", "proposal"))
    cache = paths.VAR / "rulebook" / "today.json"
    try:  # the sample drafted once per set of bank rules (the bank form is heavy to draft)
        c = json.loads(cache.read_text())
        if c.get("sig") == sig:
            _TODAY.update(c["today"])
            return _TODAY
    except (OSError, ValueError, KeyError):
        pass
    p = hook.apply_to(bf.write(SAMPLE), "", "proposal")
    secs = [s for s in p["sections"] if s["key"] not in ("header", "signatures")]
    text = "\n".join(AP.Prose(s).text() for s in secs)
    _TODAY.update({"sections": [{"key": s["key"], "heading": s["heading"]} for s in secs], "style": _style(text), "sample": SAMPLE,
                   "doc": {"sections": [{"key": s["key"], "heading": s["heading"], "blocks": []} for s in secs]}})
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"sig": sig, "today": _TODAY}))
    except OSError:
        pass
    return _TODAY


def _case(h: str) -> str:
    """'KEY STRENGTHS' -> 'Key strengths'."""
    return h[:1].upper() + h[1:].lower() if h.isupper() else h


def _lis(seq: list[int]) -> set[int]:
    """Positions of a longest increasing subsequence (the sections already in the gold standard's order)."""
    n = len(seq)
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    if not n:
        return set()
    i = max(range(n), key=lambda k: best[k])
    out = set()
    while i != -1:
        out.add(i)
        i = prev[i]
    return out


def compare(text: str, sections: list[tuple[str, str]]) -> dict[str, Any]:
    t = today()
    doc = t["doc"]
    diffs: list[dict[str, Any]] = []

    def add(area: str, finding: str, now: str, gold: str, kind: str, params: dict[str, Any], rule: str, section: str = "", label: str = "") -> None:
        diffs.append({"id": f"G{len(diffs) + 1}", "area": area, "finding": finding, "today": now, "gold": gold,
                      "rule": {"kind": kind, "params": params, "text": rule, "document": "proposal", "section": section, "section_label": label}})

    heads = [h.strip() for h, b in sections if h and h.strip() and len(h.strip()) <= 80 and (b or "").strip()]  # a title line has no body
    heads = [re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVX]+\.)\s*", "", h).strip() for h in heads]
    matched: list[tuple[int, int, str]] = []
    for h in dict.fromkeys(heads):
        i = AP.find(doc, h)
        if i is None:
            add("missing", f"The gold standard has {_an(_case(h))} “{_case(h)}” section; CreditProbe does not write one.", "Not written",
                "A section of its own", "include_section", {"heading": _case(h)},
                f"Always include {_an(_case(h))} “{_case(h)}” section.")
        elif i not in [m[1] for m in matched]:
            matched.append((len(matched), i, h))
    seq = [m[1] for m in matched]
    if seq != sorted(seq):
        keep = _lis(seq)
        names = [t["sections"][i]["heading"] for _, i, _ in matched]
        moved = [names[k] for k in range(len(matched)) if k not in keep]
        add("order", f"The gold standard orders the sections differently: {', '.join(moved)} sit{'s' if len(moved) == 1 else ''} elsewhere.",
            " → ".join(t["sections"][i]["heading"] for i in sorted(seq)), " → ".join(names), "section_order", {"order": names},
            "Order the sections as the gold standard does: " + ", then ".join(names) + ".")
    renamed = 0
    for _, i, h in matched:
        cur = t["sections"][i]["heading"]
        hh = _case(h)
        if renamed < 4 and AP._words(cur) and not (AP._words(hh) & AP._words(cur)):  # noqa: SLF001
            renamed += 1
            add("heading", f"The gold standard heads {cur} “{hh}”.", cur, hh, "heading", {"section": t["sections"][i]["key"], "heading": hh},
                f"Head the {cur} section “{hh}”.", t["sections"][i]["key"], cur)
    g, s = _style(text), t["style"]
    if g["money_style"] and s["money_style"] and g["money_style"] != s["money_style"] and g["money_style"] != "bn":
        add("units", f"The gold standard writes millions as “SAR 12.5{'' if g['money_style'] == 'm' else ' '}{g['money_style']}”.",
            f"SAR 12.5{'' if s['money_style'] == 'm' else ' '}{s['money_style']}", f"SAR 12.5{'' if g['money_style'] == 'm' else ' '}{g['money_style']}",
            "units", {"money_suffix": g["money_style"]}, f"Write amounts in millions as SAR 12.5{'' if g['money_style'] == 'm' else ' '}{g['money_style']}.")
    if g["percent_style"] and s["percent_style"] and g["percent_style"] != s["percent_style"]:
        add("units", f"The gold standard writes percentages as 12.5{'%' if g['percent_style'] == '%' else ' per cent'}.", s["percent_style"],
            g["percent_style"], "units", {"percent": g["percent_style"]}, f"Write percentages as 12.5{'%' if g['percent_style'] == '%' else ' per cent'}.")
    for use, old in TERMS:
        if g["terms"].get(use, 0) >= 2 and g["terms"].get(old, 0) == 0 and s["terms"].get(old, 0) > 0 and old != "we":
            add("wording", f"The gold standard says “{use}” and never “{old}”; CreditProbe wrote “{old}” {s['terms'][old]} time{'s' if s['terms'][old] != 1 else ''}.", old, use,
                "wording", {"use": use, "instead_of": old}, f"Say “{use}”, not “{old}”.")
    if g["sentences"] >= 5 and g["sentence_words"] and s["sentence_words"] and g["sentence_words"] < 0.8 * s["sentence_words"]:
        add("tone", f"The gold standard's sentences average {g['sentence_words']:.0f} words; CreditProbe's {s['sentence_words']:.0f}.",
            f"{s['sentence_words']:.0f} words a sentence", f"{g['sentence_words']:.0f} words a sentence", "instruction", {},
            f"Keep sentences short, about {g['sentence_words']:.0f} words, one fact or judgement each.")
    if g["sentences"] >= 5 and g["hedges_per_1000"] + 2 < s["hedges_per_1000"]:
        add("tone", f"The gold standard states facts plainly ({g['hedges_per_1000']:.0f} hedges per 1,000 words against {s['hedges_per_1000']:.0f}).",
            f"{s['hedges_per_1000']:.0f} hedges per 1,000 words", f"{g['hedges_per_1000']:.0f} per 1,000 words", "instruction", {},
            "State facts plainly; avoid hedges (may, might, appears) unless the evidence is uncertain, and say why.")
    tab = bool(re.search(r"\brisks?\b[^\n]{0,20}\|[^\n]{0,20}\bmitigants?\b", text, re.I))
    return {"differences": diffs, "today": {"sample": t["sample"], "sections": [x["heading"] for x in t["sections"]], "style": s},
            "gold": {"sections": heads, "style": g, "risk_table": tab},
            "summary": (f"{len(diffs)} difference{'s' if len(diffs) != 1 else ''} from how CreditProbe writes the credit proposal today "
                        f"({', '.join(sorted({d['area'] for d in diffs}))})." if diffs else
                        "CreditProbe already writes the proposal as this gold standard does (with the bank's rules in force).")}
