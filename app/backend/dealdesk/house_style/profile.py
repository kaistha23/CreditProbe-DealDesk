"""P1: the house-style profile, per bank and per memo type.

The profile is a set of additive, weighted counts (a "state"), so it updates incrementally: ingesting a document adds
its counts; an RM edit to a draft adds the edited text's counts, credits the phrases the RM wrote and records the ones
the RM removed (an "avoid" list). The readable profile (`view`) is derived from the counts on demand.

Counts are kept for every group a document belongs to, most specific first:

    bank|kind|segment   bank|*|segment   bank|kind|*   bank|*|*   *|*|segment   *|*|*

and `view(bank, kind, segment)` uses the most specific group that has at least two documents or a primary exemplar.
An exemplar committed to data/dealdesk/house_style/exemplars/ carries weight 5 and is the primary exemplar of its type.

What a view holds (P1): section order and headings, table layouts, standard openers and phrases, how risks and mitigants
are phrased, recommendation wording, hedging/certainty, sentence length, voice (first person, passive), number formats,
abbreviations, spelling, and the business-unit versus credit-division voice.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.dealdesk.house_style import stylo
from backend.dealdesk.house_style.corpus import BANKS, LABEL

MIN_DOCS = 2
TOP = 12


#: common words (lower case) a capitalised sentence opener may be; grows with every lower-case word read in the corpus
VOCAB: set[str] = set("""a an the this that these those it its is are was were be been has have had will would shall should may might
can could must not no nor and or but if as at by for from in into of on onto to with within without over under after before
between above below than then there their they them he she his her we our us you your all any each every both either some
such other more most less least only also further furthermore however therefore accordingly overall subject total group
new existing proposed request requested renew renewal increase reduce raise approve approval approved recommend recommends
recommended recommendation relationship facility facilities limit limits line lines project projects business financial
financials security collateral guarantee guarantees covenant covenants condition conditions conduct account bureau credit
risk risks mitigant mitigants weakness weaknesses exception exceptions stressed stress cash margin pricing advance payment
performance bid bond working capital revenue backlog net debt ebitda deposits returned cheques ownership auditor no yes
none standard sector rating internal tier date purpose amount tenor repayment structure currency obligor borrower customer
quality score opinion review required watch watchlist accepted cap tranche tranched funded unfunded general one-off villa
other banks bank letters letter obtained not formalised past completion planned complete pending certified since about
key main principal strong adequate comfortable satisfactory weak moderate high low significant overdraft receivables finance
company establishment turnover sales profit profitability margins leverage gearing liquidity revenues income expenses dividend
dividends receivable receivables payable payables inventory assets liabilities equity audited unaudited ratio ratios growth decline
decrease reached stood remained improved declined rose fell during while although since following based given against the""".split())


def _learn_vocab(text: str) -> None:
    for w in re.findall(r"(?<![.!?]\s)\b[a-z][a-z'-]+\b", text or ""):
        VOCAB.add(w)


def _tok(sentence: str) -> list[str]:
    """Tokens with figures as '#' and proper names as '@' (so a phrase never carries a name or a number). A capitalised
    word that opens the sentence or follows a colon is a common word when the corpus writes it in lower case."""
    out: list[str] = []
    start = True
    for w in re.findall(r"[A-Za-z][A-Za-z'&-]*|\d[\d,.]*%?|:", sentence):
        if w == ":":
            start = True
            continue
        if w[0].isdigit():
            t = "#"
        elif len(w) > 1 and w.isupper():
            t = w
        elif w[0].isupper() and not (start and w.lower() in VOCAB):
            t = "@"
        else:
            t = w.lower()
        start = False
        if t == "@" and out and out[-1] == "@":
            continue
        out.append(t)
    return out


def phrases_of(text: str, ns: tuple[int, ...] = (3, 4)) -> set[str]:
    grams: set[str] = set()
    for s in stylo.sentences(text) or [text]:
        t = _tok(s)
        for n in ns:
            for i in range(len(t) - n + 1):
                g = t[i:i + n]
                if sum(1 for x in g if x in ("@", "#")) <= 1 and sum(1 for x in g if len(x) > 3 and x not in ("@", "#")) >= 2:
                    grams.add(" ".join(g))
    return grams


def opener_of(s: str, n: int = 3) -> str:
    return " ".join(_tok(s)[:n])


def template_of(s: str) -> str:
    return " ".join(_tok(s)[:9])


def _add(d: dict[str, float], k: str, w: float) -> None:
    d[k] = round(d.get(k, 0.0) + w, 6)


def _addm(d: dict[str, float], m: dict[str, float], w: float) -> None:
    for k, v in m.items():
        d[k] = round(d.get(k, 0.0) + v * w, 6)


def _group(state: dict[str, Any], key: str) -> dict[str, Any]:
    g = state["groups"].get(key)
    if g is None:
        g = state["groups"][key] = {"n": 0, "w": 0.0, "docs": [], "primary": [], "sections": {}, "phrases": {}, "phrase_n": {},
                                    "money": {}, "units": {}, "decimals": {}, "pct": {}, "multiple": {}, "abbrev": {},
                                    "spelling": {}, "numbering": {}, "voices": {}, "recommendation": {}, "risk_markers": {},
                                    "avoid": {}, "prefer": {}, "edits": 0, "bn": {}, "roles": {}}
    return g


def group_keys(bank: str, kind: str, segment: str) -> list[str]:
    return [f"{bank}|{kind}|{segment}", f"{bank}|*|{segment}", f"{bank}|{kind}|*", f"{bank}|*|*", f"*|*|{segment}", "*|*|*"]


RISK_MARKERS = ("mitigated by", "partly mitigated", "mitigant", "mitigants", "comfort is drawn", "comfort from", "offset by",
                "subject to", "condition precedent", "conditions precedent", "covenant", "exception", "deviation", "watch",
                "risk is", "key risk", "concern", "not supported", "supported by", "tranche")


def _section_text(s: dict[str, Any]) -> str:
    return "\n".join(s.get("paragraphs", []) + s.get("bullets", []))


def role_of(doc: dict[str, Any]) -> str:
    """'business' for a proposal written by the business unit, 'credit' for a credit-division opinion."""
    if doc.get("source") == "opinion":
        return "credit"
    secs = [s for s in doc["sections"] if s["key"] != "preamble"]
    return "credit" if secs and all(s.get("voice") == "credit" for s in secs) else "business"


def add_doc(state: dict[str, Any], doc: dict[str, Any]) -> None:
    """Add one document's counts to every group it belongs to (the incremental update)."""
    w = float(doc.get("weight", 1.0))
    secs = [s for s in doc["sections"] if s["key"] != "preamble"] or doc["sections"]
    full = "\n".join(_section_text(s) for s in doc["sections"])
    _learn_vocab(full)
    role = role_of(doc)
    grams = phrases_of(full)
    for key in group_keys(doc["bank"], doc["kind"], doc["segment"]):
        g = _group(state, key)
        if doc["doc_id"] in g["docs"]:
            continue
        g["n"] += 1
        g["w"] = round(g["w"] + w, 6)
        g["docs"].append(doc["doc_id"])
        _add(g["roles"], role, w)
        if role == "business":
            g["nb"] = g.get("nb", 0) + 1
        if doc.get("primary"):
            g["primary"].append(doc["doc_id"])
        for i, s in enumerate(secs):
            sk = s["key"]
            sec = g["sections"].setdefault(role, {}).setdefault(sk, {"w": 0.0, "n": 0, "pos": 0.0, "headings": {}, "tables": {}, "openers": {},
                                                "voice": {}, "bullets": 0.0, "paras": 0.0, "measure": {}})
            sec["w"] = round(sec["w"] + w, 6)
            sec["n"] += 1
            sec["pos"] = round(sec["pos"] + w * (i / max(1, len(secs) - 1)), 6)
            if s.get("heading"):
                _add(sec["headings"], s["heading"], w)
            for t in s.get("tables", []):
                _add(sec["tables"], " | ".join(t["header"]), w)
            _add(sec["voice"], s.get("voice", "business"), w)
            sec["bullets"] = round(sec["bullets"] + w * len(s.get("bullets", [])), 6)
            sec["paras"] = round(sec["paras"] + w * len(s.get("paragraphs", [])), 6)
            text = _section_text(s)
            for sent in stylo.sentences(text) + [b for b in s.get("bullets", []) if not stylo.sentences(b)]:
                op = opener_of(sent)
                if op:
                    _add(sec["openers"], op, w)
                low = sent.lower()
                if sk == "recommendation" and role == "business":
                    _add(g["recommendation"], template_of(sent), w)
                if sk in ("risks", "opinion", "counter"):
                    for mk in RISK_MARKERS:
                        if mk in low:
                            _add(g["risk_markers"], mk, w)
            m = stylo.measure(text)
            _addm(sec["measure"], m, w)
            _addm(g["voices"].setdefault(s.get("voice", "business"), {}), m, w)
            _add(g["numbering"], "numbered" if s.get("numbered") else "plain", w)
        if role == "business":
            for gram in grams:
                _add(g["phrases"], gram, w)
                g["phrase_n"][gram] = g["phrase_n"].get(gram, 0) + 1
        else:
            cp = g.setdefault("credit_phrases", {})
            for gram in grams:
                _add(cp, gram, w)
        for mm in stylo.MONEY.finditer(full):
            _add(g["money"], stylo.money_style(mm), w)
            _add(g["units"], stylo.unit_style(mm), w)
            num = mm.group(2)
            _add(g["decimals"], str(len(num.split(".")[1]) if "." in num else 0), w)
            if (mm.group(3) or "").lower() in ("bn", "billion"):
                _add(g["bn"], "bn", w)
        for pm in stylo.PERCENT.finditer(full):
            _add(g["pct"], "%" if pm.group(2) == "%" else "per cent", w)
        for xm in stylo.MULTIPLE.finditer(full):
            _add(g["multiple"], xm.group(2), w)
        for a in stylo.abbreviations(full):
            _add(g["abbrev"], a, w)
        _addm(g["spelling"], stylo.spelling(full), w)


def clean_sentences(text: str) -> list[str]:
    """Sentences fit to learn from: no hedging and no first person (the house guardrail on what an edit can teach)."""
    out = []
    for sent in stylo.sentences(text):
        low = " " + sent.lower() + " "
        if any(f" {h} " in low for h in stylo.HEDGES) or stylo.FIRST_PERSON.search(sent):
            continue
        out.append(sent)
    return out


def add_edit(state: dict[str, Any], ev: dict[str, Any]) -> None:
    """Learn from an RM edit. Phrases the RM wrote (in sentences that pass the house guardrail) are credited, phrases the
    RM removed are counted against; either takes effect once two edits agree. The clean sentences' measures and openers
    are added to the section and the voice."""
    before, after = ev.get("before", ""), ev.get("after", "")
    clean = "\n".join(clean_sentences(after))
    added = phrases_of(clean) - phrases_of(before) if clean else set()
    removed = phrases_of(before) - phrases_of(after)
    w = float(ev.get("weight", 2.0))
    for key in group_keys(ev["bank"], ev["kind"], ev["segment"]):
        g = _group(state, key)
        g["edits"] += 1
        pn, an = g.setdefault("prefer_n", {}), g.setdefault("avoid_n", {})
        for gram in added:
            _add(g["prefer"], gram, w)
            pn[gram] = pn.get(gram, 0) + 1
        for gram in removed:
            _add(g["avoid"], gram, 1.0)
            an[gram] = an.get(gram, 0) + 1
        if not clean:
            continue
        sec = g["sections"].get(ev.get("role", "business"), {}).get(ev["section"])
        if sec is not None:
            _addm(sec["measure"], stylo.measure(clean), 1.0)
            for sent in clean_sentences(after):
                _add(sec["openers"], opener_of(sent), 1.0)
        _addm(g["voices"].setdefault(ev.get("voice", "business"), {}), stylo.measure(clean), 1.0)


def build(docs: list[dict[str, Any]], events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {"groups": {}, "events": 0}
    for d in docs:  # the common-word list first, so every document is tokenised alike whatever the order
        _learn_vocab("\n".join(_section_text(s) for s in d["sections"]))
    for ev in events or []:
        if ev.get("type") == "doc":
            _learn_vocab("\n".join(_section_text(s) for s in ev["doc"]["sections"]))
    for d in docs:
        add_doc(state, d)
    for ev in events or []:
        apply_event(state, ev)
    return state


def apply_event(state: dict[str, Any], ev: dict[str, Any]) -> None:
    if ev.get("type") == "doc":
        add_doc(state, ev["doc"])
    elif ev.get("type") == "edit":
        add_edit(state, ev)
    state["events"] = state.get("events", 0) + 1


# ---------------------------------------------------------------------------------------------- the readable profile

def _top(d: dict[str, float], n: int = TOP, min_w: float = 0.0) -> list[dict[str, Any]]:
    return [{"text": k, "weight": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n] if v > min_w]


def _argmax(d: dict[str, float], default: str) -> str:
    return max(sorted(d), key=lambda k: d[k]) if d else default


def pick_group(state: dict[str, Any], bank: str, kind: str, segment: str) -> str:
    """The most specific group with two business-unit memos, except that a primary exemplar of the segment (Anne's
    contractor proposal for contractor memos) leads whatever the memo type."""
    keys = group_keys(bank, kind, segment)
    for key in keys[:2]:
        g = state["groups"].get(key)
        if g and g["primary"]:
            return key
    for key in keys:
        g = state["groups"].get(key)
        if g and (g.get("nb", 0) >= MIN_DOCS or g["primary"]):
            return key
    return "*|*|*"


def _sections(g: dict[str, Any], role: str) -> list[dict[str, Any]]:
    rw = g.get("roles", {}).get(role, 0.0)
    secs = []
    for sk, s in g["sections"].get(role, {}).items():
        presence = s["w"] / rw if rw else 0.0
        if presence < 0.3:
            continue
        heading = _argmax(s["headings"], LABEL.get(sk, sk.capitalize()))
        voice = _argmax(s["voice"], role)
        secs.append({"key": sk, "heading": heading, "label": LABEL.get(sk, sk.capitalize()), "position": round(s["pos"] / s["w"], 3),
                     "presence": round(min(1.0, presence), 3), "voice": voice,
                     "tables": [t["text"].split(" | ") for t in _top(s["tables"], 2)],
                     "openers": _top(s["openers"], 6), "bullet_share": round(s["bullets"] / max(1e-9, s["bullets"] + s["paras"]), 3),
                     "paragraphs_per_memo": round(s["paras"] / s["w"], 2), "bullets_per_memo": round(s["bullets"] / s["w"], 2),
                     "style": stylo.rates(s["measure"])})
    secs.sort(key=lambda x: (x["position"], x["key"]))
    return secs


def house_for(state: dict[str, Any], bank: str, segment: str) -> str:
    """The house whose language a memo is drafted in: its own bank's, unless only another house holds a primary exemplar for
    the memo's segment (Anne's anonymised contractor proposal is the model for every contractor proposal)."""
    own = state["groups"].get(f"{bank}|*|{segment}")
    if own and own["primary"]:
        return bank
    for key, g in sorted(state["groups"].items()):
        b, k, sg = key.split("|")
        if b != "*" and k == "*" and sg == segment and g["primary"]:
            return b
    return bank


def view(state: dict[str, Any], bank: str = "house-uae", kind: str = "increase", segment: str = "contractor",
         group: str | None = None) -> dict[str, Any]:
    key = group or pick_group(state, bank, kind, segment)
    g = state["groups"].get(key) or _group({"groups": {}}, key)
    return _view_rest(state, key, g, {r: _sections(g, r) for r in ("business", "credit")})


def _view_rest(state: dict[str, Any], key: str, g: dict[str, Any], by_role: dict[str, list]) -> dict[str, Any]:
    secs = by_role["business"]
    pn, an = g.get("prefer_n", {}), g.get("avoid_n", {})
    prefer = {k: v for k, v in g["prefer"].items() if pn.get(k, 0) >= 2}
    phrases = {k: v for k, v in g["phrases"].items() if g["phrase_n"].get(k, 0) >= MIN_DOCS or (g["primary"] and v >= 5.0)}
    for k, v in prefer.items():
        phrases[k] = phrases.get(k, 0.0) + v
    avoid = {k: v for k, v in g["avoid"].items() if an.get(k, 0) >= 2 and v > prefer.get(k, 0.0)}
    units = g["units"]
    unit = _argmax({k: v for k, v in units.items() if k not in ("none", "bn", "billion")}, "m")
    if unit == "m" and units.get("million", 0) > units.get("m", 0):
        unit = "million"
    dw = g["decimals"]
    tot = sum(dw.values()) or 1.0
    dec = max([int(k) for k, v in dw.items() if v / tot >= 0.2] or [1])
    trim = dw.get("0", 0.0) / tot >= 0.2
    spelling = "British" if g["spelling"].get("british", 0) >= g["spelling"].get("american", 0) else "American"
    abbrev = [a for a in _top(g["abbrev"], 40) if a["weight"] >= 1.0]
    voices = {v: stylo.rates(m) for v, m in g["voices"].items()}
    numbers = {"money_example": _argmax(g["money"], "AED #m"), "unit": unit, "decimals": int(dec), "trim_integers": bool(trim),
               "bn_for_round_billions": bool(g["bn"]), "percent": _argmax(g["pct"], "%"), "multiple": _argmax(g["multiple"], "x"),
               "separator": True}
    return {
        "group": key, "bank": key.split("|")[0], "bank_label": BANKS.get(key.split("|")[0], "All banks"),
        "kind": key.split("|")[1], "segment": key.split("|")[2], "documents": g["n"], "weight": round(g["w"], 2),
        "doc_ids": list(g["docs"]), "primary_exemplars": list(g["primary"]), "edits_learned": g["edits"],
        "sections": secs, "credit_sections": by_role["credit"], "headings_numbered": g["numbering"].get("numbered", 0) >= g["numbering"].get("plain", 0),
        "phrases": _top(phrases, 30), "credit_phrases": _top({k: v for k, v in g.get("credit_phrases", {}).items() if v >= 1.0}, 15),
        "recommendation_wording": _top(g["recommendation"], 6),
        "risk_markers": _top(g["risk_markers"], 10), "numbers": numbers, "abbreviations": abbrev,
        "spelling": spelling, "voices": voices, "style": voices.get("business") or stylo.rates({}),
        "learned": {"preferred": _top(prefer, 10), "avoid": _top(avoid, 20)},
    }


def money_style(v: dict[str, Any]) -> dict[str, Any]:
    n = v["numbers"]
    return {"unit": n["unit"], "decimals": n["decimals"], "trim_integers": n.get("trim_integers", False), "separator": True, "pct_word": n["percent"] == "per cent",
            "pct_decimals": 1, "bn_from": 1000 if n.get("bn_for_round_billions") else None}


def groups(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"group": k, "documents": g["n"], "weight": round(g["w"], 2), "primary": g["primary"], "edits": g["edits"]}
            for k, g in sorted(state["groups"].items())]


# ---------------------------------------------------------------------------------------------- readable style guide

def guide(v: dict[str, Any]) -> str:
    """The profile as a readable style guide (markdown)."""
    n = v["numbers"]
    bank, kind, seg = v["bank_label"], v["kind"], v["segment"]
    lines = [f"# House style: {bank}, {kind if kind != '*' else 'all memo types'}, {seg if seg != '*' else 'all segments'}",
             "",
             f"Derived from {v['documents']} documents (weighted {v['weight']}); "
             + (f"primary exemplar: {', '.join(v['primary_exemplars'])}. " if v["primary_exemplars"] else "")
             + (f"{v['edits_learned']} RM edits learned." if v["edits_learned"] else ""), "",
             "## Structure", ""]
    for i, s in enumerate(v["sections"], start=1):
        tbl = f" Table: {' | '.join(s['tables'][0])}." if s["tables"] else ""
        lines.append(f"{i}. **{s['heading']}** ({s['label']}; {s['voice']} voice; in {round(100 * s['presence'])}% of memos; "
                     f"{'mostly bullets' if s['bullet_share'] > 0.5 else 'prose'}).{tbl}")
    lines += ["", "## Numbers", "",
              f"- Money: currency first, unit '{n['unit']}', {n['decimals']} decimal(s), thousands separator (e.g. {n['money_example'].replace('#', '212.4')}).",
              f"- Percentages written with '{n['percent']}'; multiples with '{n['multiple']}'."
              + (" Round billions as 'bn'." if n["bn_for_round_billions"] else ""), "",
              "## Voice and tone", ""]
    for voice, r in v["voices"].items():
        if r.get("sentence_words") is None:
            continue
        who = "Business unit" if voice == "business" else "Credit division"
        lines.append(f"- **{who}:** {r['sentence_words']} words a sentence (sd {r['sentence_sd']}); hedges {r['hedges_per_100w']} per 100 words; "
                     f"first person {r['first_person_per_100w']} per 100 words; passive in {round(100 * (r['passive_share'] or 0))}% of sentences.")
    lines += ["", f"- Spelling: {v['spelling']}.", "", "## Standard phrases and openers", ""]
    lines += [f"- \"{p['text']}\"" for p in v["phrases"][:15]]
    for s in v["sections"]:
        if s["openers"]:
            lines.append(f"- {s['heading']}: opens with " + "; ".join(f"\"{o['text']}\"" for o in s["openers"][:3]))
    if v["recommendation_wording"]:
        lines += ["", "## Recommendation wording", ""] + [f"- \"{r['text']}\"" for r in v["recommendation_wording"][:4]]
    if v["risk_markers"]:
        lines += ["", "## Risks and mitigants", "", "- Markers used: " + ", ".join(r["text"] for r in v["risk_markers"])]
    if v["abbreviations"]:
        lines += ["", "## Abbreviations", "", ", ".join(a["text"] for a in v["abbreviations"])]
    if v["learned"]["avoid"]:
        lines += ["", "## Learned from RM edits: avoid", ""] + [f"- \"{a['text']}\"" for a in v["learned"]["avoid"][:10]]
    lines += ["", "_'@' stands for a name and '#' for a figure: phrases never carry a client name or a number._", ""]
    return "\n".join(lines)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True)
