"""An instruction to the document -> one section edit, or a structure change.

    it = parse("Shorten the financial synopsis", paper, focus="synopsis")
    it  -> {"op": "shorten", "section": "synopsis", ...}
    new_blocks, note = apply(it, section)          # deterministic (no model): the fixed instruction set below

The fixed instruction set (works with no model key; the tests and the walk use it):

    shorten / tighten <section>                       each paragraph to its first sentence, each list to its first 3 points
    add to <section>: <text>                          a paragraph (or a point, when the section ends in a list) at the end
    start <section> with: <text>                      a paragraph at the top
    replace "<old>" with "<new>" [in <section>]       wording only
    remove the sentence about <phrase> [from <section>]
    underline / flag <phrase> as a key concern [in <section>]   the sentence underlined (the bank form's key-concern mark)
    make <section> bullet points | ... a paragraph    the form of the prose
    set / increase / reduce the amount | tenor | margin | cash margin | upfront fee to <value>
                                                      a number: sent to the structure step (structure.py), never typed in

Any other instruction goes to the model when a key is present (edit_section tool, one section, figures checked); without a key,
Noor says what she can do. The section is the one the instruction names (heading, alias or "section 15"), else the section in
focus (the one clicked on the left).
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from backend.dealdesk.paperws import figures as FG

PROSE = ("p", "bullets", "numbered")
SENT = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\"'“])")
QUOTE = r"[\"'“”‘’]"
#: aliases too generic to name a section inside an instruction
GENERIC = {"proposal", "request", "approval", "account", "the ask", "facility", "conditions", "header", "obligor", "limits", "projects",
           "stress", "raroc", "sva", "precedent"}


class NotUnderstood(ValueError):
    pass


# ------------------------------------------------------------------------------------------- sections named in an instruction

def aliases(paper: dict[str, Any]) -> list[tuple[str, str]]:
    """(alias, section key), longest first."""
    reg: dict[str, tuple[str, ...]] = {}
    if paper.get("doc_kind") == "proposal":
        try:
            from backend.dealdesk.house_style.bankform import registry
            reg = {k: s.aliases for k, s in registry.BY_KEY.items()}
        except Exception:  # noqa: BLE001
            reg = {}
    out: list[tuple[str, str]] = []
    for s in paper.get("sections") or []:
        k = s["key"]
        h = str(s.get("heading") or "").lower()
        names = {h, re.sub(r"\s*\(creditprobe\)\s*", "", h).strip(), k.replace("_", " ").replace("cp ", "").strip()}
        names |= {a for a in reg.get(k, ()) if a not in GENERIC}
        for a in names:
            if a and len(a) >= 4:
                out.append((a, k))
    return sorted(set(out), key=lambda x: -len(x[0]))


def head_of(instruction: str) -> str:
    """The part of an instruction that may name a section: before a colon, without quoted text."""
    t = instruction.split(":", 1)[0]
    return re.sub(rf"{QUOTE}[^\"'“”‘’]*{QUOTE}", " ", t)


def find_section(instruction: str, paper: dict[str, Any]) -> str | None:
    h = head_of(instruction).lower()
    m = re.search(r"\bsection\s+(\d{1,2})\b", h)
    if m:
        n = int(m.group(1))
        for s in paper.get("sections") or []:
            if s.get("n") == n:
                return s["key"]
    for a, k in aliases(paper):
        if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", h):
            return k
    return None


def section_by_key(paper: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((s for s in paper.get("sections") or [] if s["key"] == key), None)


# ------------------------------------------------------------------------------------------- parse

STRUCT_FIELDS = [
    ("cash_margin_pct", r"cash\s+margin", "%"),
    ("upfront_fee_bps", r"(?:upfront|arrangement|front[- ]end)\s+fee", "bps"),
    ("margin_bps", r"(?:margin|pricing|spread|profit\s+rate)", "bps"),
    ("tenor_years", r"(?:tenor|tenure|maturity)", "years"),
    ("amount", r"(?:amount|limit|facility\s+amount|facility|exposure|ask)", "SAR m"),
]
VERB = r"(?:set|change|increase|raise|reduce|lower|cut|decrease|make|move|put|bring|take|revise|amend|update)"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_structure(instruction: str) -> list[dict[str, Any]]:
    """[{field, value, unit, mode: to|by, sign}] for a number change on the structure; [] when the instruction names no term."""
    t = instruction.lower()
    if not re.search(rf"\b{VERB}\b", t):
        return []
    out = []
    taken: list[tuple[int, int]] = []
    for field, rx, unit in STRUCT_FIELDS:
        for m in re.finditer(rf"\b{rx}\b(?P<mid>[^\d;]{{0,40}}?)\b(?P<mode>to|at|of|by)\s*(?:sar|aed|usd)?\s*(?P<n>\d[\d,]*(?:\.\d+)?)\s*(?P<u>bps|bp|basis points|%|percent|years?|yrs?|months?|m\b|mn|million|bn)?", t):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            v, u, mode = _num(m.group("n")), (m.group("u") or "").strip(), m.group("mode")
            if field in ("margin_bps", "upfront_fee_bps"):
                if u in ("%", "percent"):
                    v = v * 100
                elif not u and v < 20:   # "margin to 2.5" reads as percent
                    v = v * 100
            if field == "tenor_years" and u.startswith("month"):
                v = v / 12
            if field == "amount" and u == "bn":
                v = v * 1000
            sign = -1 if re.search(r"\b(reduce|lower|cut|decrease)\b", t[: m.start() + 1] + t[m.start():m.end()]) else 1
            out.append({"field": field, "value": v, "unit": unit, "mode": "by" if mode == "by" else "to", "sign": sign, "text": m.group(0)})
            break
    return out


def parse(instruction: str, paper: dict[str, Any], focus: str | None = None) -> dict[str, Any]:
    ins = " ".join(str(instruction or "").split())
    if not ins:
        raise NotUnderstood("Type an instruction, e.g. “Shorten the financial synopsis”.")
    low = ins.lower()
    named = find_section(ins, paper)
    sec = named or focus
    body = ins.split(":", 1)[1].strip().strip("\"'“”") if ":" in ins else ""
    quoted = re.findall(rf"{QUOTE}([^\"'“”‘’]+){QUOTE}", ins)

    # a number on the structure: the structure step, never a text edit
    fields = parse_structure(ins) if not body else []
    if fields:
        return {"op": "structure", "section": named or "", "fields": fields, "instruction": ins}
    m = re.match(rf"^(?:replace|change)\s+{QUOTE}(?P<old>[^\"'“”‘’]+){QUOTE}\s+(?:with|to|by|into)\s+{QUOTE}(?P<new>[^\"'“”‘’]*){QUOTE}", ins, re.I)
    if m:
        old, new = m.group("old"), m.group("new")
        op = "figure" if FG.numbers(old) and FG.numbers(old) != FG.numbers(new) else "replace"
        return {"op": op, "section": sec, "old": old, "new": new, "named": bool(named), "instruction": ins}
    if re.match(r"^(?:add|insert|append|include|mention|note)\b", low) and body:
        return {"op": "add", "section": sec, "text": body, "instruction": ins}
    if re.match(r"^(?:start|open|begin|lead)\b", low) and body:
        return {"op": "lead", "section": sec, "text": body, "instruction": ins}
    m = re.match(r"^(?:remove|delete|drop|take out)\s+(?:the\s+)?(?:sentence|point|line|bullet|paragraph|mention|reference)?s?\s*(?:about|on|mentioning|containing|that mentions|with|of)?\s*(?P<p>.+?)(?:\s+(?:from|in)\s+(?:the\s+)?[a-z' ]+(?:section)?)?$", ins, re.I)
    if m and not re.match(r"^(?:remove|delete|drop)\s+(?:the\s+)?(?:whole\s+)?section\b", low):
        phrase = quoted[0] if quoted else m.group("p")
        if named:  # "remove the sentence about X from the synopsis": the phrase stops before the section name
            phrase = re.split(r"\s+(?:from|in)\s+(?:the\s+)?", phrase)[0]
        return {"op": "remove", "section": sec, "phrase": phrase.strip(" .\"'“”"), "named": bool(named), "instruction": ins}
    m = re.search(r"(?:underline|flag|emphasi[sz]e|highlight|mark)\s+(?:the\s+)?(?:sentence\s+(?:about|on)\s+)?(?P<p>.+?)\s+as\s+(?:a\s+)?key\s+concern", ins, re.I)
    if m:
        phrase = quoted[0] if quoted else m.group("p")
        return {"op": "emphasise", "section": sec, "phrase": phrase.strip(" .\"'“”"), "named": bool(named), "instruction": ins}
    if re.search(r"\b(shorten|shorter|tighten|tighter|concise|condense|cut down|trim|briefer|more brief)\b", low):
        return {"op": "shorten", "section": sec, "instruction": ins}
    if re.search(r"\b(bullet|bullets|bullet points|bulleted|as a list|into a list|as points)\b", low):
        return {"op": "bullets", "section": sec, "instruction": ins}
    if re.search(r"\b(as a paragraph|into a paragraph|as prose|into prose|paragraph form)\b", low):
        return {"op": "prose", "section": sec, "instruction": ins}
    return {"op": "model", "section": sec, "instruction": ins}


# ------------------------------------------------------------------------------------------- deterministic edits

def sentences(text: str) -> list[str]:
    return [x for x in SENT.split(str(text).strip()) if x.strip()]


def _end(t: str) -> str:
    t = t.strip()
    return t if not t or t[-1] in ".;:!?" else t + "."


def _contains(text: str, phrase: str) -> bool:
    return phrase.lower() in str(text).replace("**", "").replace("__", "").lower()


def find_phrase_section(paper: dict[str, Any], phrase: str) -> str | None:
    for s in paper.get("sections") or []:
        for b in s.get("blocks") or []:
            if b.get("t") in PROSE and any(_contains(t, phrase) for t in FG.block_texts(b)):
                return s["key"]
    return None


def apply(it: dict[str, Any], section: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """The section's new blocks and a one-line note of what changed. Raises NotUnderstood when nothing would change."""
    blocks = copy.deepcopy(section.get("blocks") or [])
    op = it["op"]
    head = section.get("heading") or section["key"]
    if op == "shorten":
        out, prose_n = [], 0
        for b in blocks:
            if b["t"] == "p":
                ss = sentences(b["text"])
                b = {**b, "text": ss[0] if ss else b["text"]}
            elif b["t"] in ("bullets", "numbered"):
                b = {**b, "items": b["items"][:3]}
            if b["t"] in PROSE:
                prose_n += 1
                if prose_n > 4:
                    continue
            out.append(b)
        if out == blocks:  # already terse: two points per list, the first two prose blocks
            out, prose_n = [], 0
            for b in blocks:
                if b["t"] in ("bullets", "numbered"):
                    b = {**b, "items": b["items"][:2]}
                if b["t"] in PROSE:
                    prose_n += 1
                    if prose_n > 2:
                        continue
                out.append(b)
        if out == blocks:
            raise NotUnderstood(f"{head} is already as short as it can be without losing a point.")
        return out, f"shortened ({_words(blocks)} → {_words(out)} words)"
    if op in ("add", "lead"):
        text = _end(it["text"])
        if op == "add" and blocks and blocks[-1]["t"] in ("bullets", "numbered") and re.search(r"\b(point|bullet|item)\b", it["instruction"], re.I):
            blocks[-1]["items"].append(text)
        elif op == "add":
            blocks.append({"t": "p", "text": text})
        else:
            blocks.insert(0, {"t": "p", "text": text})
        return blocks, ("added a point at the end" if op == "add" else "added an opening line")
    if op == "replace":
        n = 0
        rx = re.compile(re.escape(it["old"]), re.I)
        for b in blocks:
            if b["t"] == "p":
                b["text"], k = rx.subn(it["new"], b["text"])
                n += k
            elif b["t"] in ("bullets", "numbered"):
                new = []
                for x in b["items"]:
                    y, k = rx.subn(it["new"], x)
                    n += k
                    new.append(y)
                b["items"] = new
        if not n:
            raise NotUnderstood(f"“{it['old']}” is not in the text of {head}.")
        return blocks, f"replaced “{it['old']}” with “{it['new']}” ({n}×)"
    if op == "remove":
        n, out = 0, []
        for b in blocks:
            if b["t"] == "p":
                keep = [x for x in sentences(b["text"]) if not _contains(x, it["phrase"])]
                n += len(sentences(b["text"])) - len(keep)
                if not keep:
                    continue
                b["text"] = " ".join(keep)
            elif b["t"] in ("bullets", "numbered"):
                keep = [x for x in b["items"] if not _contains(x, it["phrase"])]
                n += len(b["items"]) - len(keep)
                if not keep:
                    continue
                b["items"] = keep
            out.append(b)
        if not n:
            raise NotUnderstood(f"No sentence in {head} mentions “{it['phrase']}”.")
        return out, f"removed {n} sentence{'s' if n != 1 else ''} about “{it['phrase']}”"
    if op == "emphasise":
        n = 0
        for b in blocks:
            if b["t"] == "p":
                ss = sentences(b["text"])
                new = [f"__{x.strip('_')}__" if _contains(x, it["phrase"]) and not x.startswith("__") else x for x in ss]
                n += sum(1 for a, c in zip(ss, new) if a != c)
                b["text"] = " ".join(new)
            elif b["t"] in ("bullets", "numbered"):
                new = [f"__{x.strip('_')}__" if _contains(x, it["phrase"]) and not x.startswith("__") else x for x in b["items"]]
                n += sum(1 for a, c in zip(b["items"], new) if a != c)
                b["items"] = new
        if not n:
            raise NotUnderstood(f"No sentence in {head} mentions “{it['phrase']}”.")
        return blocks, f"underlined {n} sentence{'s' if n != 1 else ''} as a key concern"
    if op == "bullets":
        out, items, at = [], [], None
        for b in blocks:
            if b["t"] == "p" and not b.get("exempt"):
                if at is None:
                    at = len(out)
                    out.append(None)
                items += sentences(b["text"])
            else:
                out.append(b)
        if not items:
            raise NotUnderstood(f"{head} has no paragraph to turn into points.")
        out[at] = {"t": "bullets", "items": items}
        return out, f"{len(items)} sentences as bullet points"
    if op == "prose":
        out, n = [], 0
        for b in blocks:
            if b["t"] in ("bullets", "numbered"):
                out.append({"t": "p", "text": " ".join(_end(x) for x in b["items"])})
                n += 1
            else:
                out.append(b)
        if not n:
            raise NotUnderstood(f"{head} has no list to write as a paragraph.")
        return out, "points written as a paragraph"
    raise NotUnderstood("model")


def _words(blocks: list[dict[str, Any]]) -> int:
    return sum(len(t.split()) for b in blocks if b["t"] in PROSE for t in FG.block_texts(b))


# ------------------------------------------------------------------------------------------- the model (when a key is present)

TOOL = {"name": "edit_section", "description": "Rewrite ONE section of the bank-form paper as the instruction asks.",
        "input_schema": {"type": "object", "properties": {
            "blocks": {"type": "array", "description": "The section's blocks in order. Prose: {t:'p', text} or {t:'bullets'|'numbered', items}. "
                                                       "To keep a table or form block unchanged: {t:'keep', index:<its index>}.",
                       "items": {"type": "object"}},
            "note": {"type": "string", "description": "One line: what you changed."}}, "required": ["blocks", "note"]}}
SYSTEM = ("You edit one section of a bank credit paper in the bank's own form, as the analyst instructs. Formal banker English, one "
          "fact per sentence, the section's voice kept (business: what business asks; credit: the credit division's independent view). "
          "FIGURES ARE THE ENGINE'S: never add, change or compute a number; use only the figures already printed in the section or the "
          "evidence list. If the instruction asks to change a number, return the section unchanged and say so in the note. Keep tables "
          "and form blocks with {t:'keep', index}. **bold** and __underlined key concern__ marks are allowed.")


def _provider():
    try:
        from backend.convo import provider as prov
        return prov.default()
    except Exception:  # noqa: BLE001
        return None


def model_available() -> bool:
    return _provider() is not None


def model_edit(it: dict[str, Any], section: dict[str, Any], allowed: set[float], context: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """The model's edit of one section, accepted only if every figure is in the evidence. Raises NotUnderstood otherwise."""
    p = _provider()
    if p is None:
        raise NotUnderstood("no model")
    blocks = section.get("blocks") or []
    user = json.dumps({"instruction": it["instruction"], "section": {"key": section["key"], "heading": section.get("heading"),
                       "voice": section.get("voice"), "blocks": [dict(b, index=i) for i, b in enumerate(blocks)]},
                       "customer": context.get("customer"), "document": context.get("kind")}, ensure_ascii=False, default=str)
    from backend.convo import telemetry
    try:
        with telemetry.use(module="dealdesk", stage="paperws_edit", thread_id=context.get("ws_id")):
            reply = p.step("dealdesk_paperws_edit", SYSTEM, [{"role": "user", "content": user}], [TOOL])
    except Exception as e:  # noqa: BLE001
        raise NotUnderstood(f"the model is not available ({type(e).__name__})") from None
    use = next((u for u in reply.tool_uses() if u.get("name") == "edit_section"), None)
    if not use:
        raise NotUnderstood(reply.text() or "the model gave no edit")
    out: list[dict[str, Any]] = []
    for b in use["input"].get("blocks") or []:
        if not isinstance(b, dict):
            continue
        if b.get("t") == "keep" and isinstance(b.get("index"), int) and 0 <= b["index"] < len(blocks):
            out.append(copy.deepcopy(blocks[b["index"]]))
        elif b.get("t") == "p" and isinstance(b.get("text"), str):
            out.append({"t": "p", "text": b["text"]})
        elif b.get("t") in ("bullets", "numbered") and isinstance(b.get("items"), list):
            out.append({"t": b["t"], "items": [str(x) for x in b["items"]]})
        elif b.get("t") == "h" and isinstance(b.get("text"), str):
            out.append({"t": "h", "text": b["text"]})
    # tables and form blocks the model dropped silently are kept (a table is the engine's)
    kept = {json.dumps(b, sort_keys=True) for b in out}
    for b in blocks:
        if b["t"] not in PROSE + ("h",) and json.dumps(b, sort_keys=True) not in kept:
            out.append(copy.deepcopy(b))
    bad = FG.blocks_unknown(out, allowed)
    if bad:
        raise FigureRejected(bad)
    if out == blocks:
        raise NotUnderstood(str(use["input"].get("note") or "No change was needed."))
    return out, str(use["input"].get("note") or "edited")


class FigureRejected(ValueError):
    def __init__(self, figures: list[float]):
        self.figures = figures
        super().__init__(", ".join(_fmt(x) for x in figures))


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,}"
