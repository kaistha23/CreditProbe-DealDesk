"""The rules applied to a document.

Two document shapes are read alike:
    house-style draft   sections [{key, heading, paragraphs, bullets, table{header, rows, cites}}]
    bank-form paper     sections [{key, heading, blocks: [{t: p | bullets | numbered | table | kv | h | sign | box, ...}]}]
                        (the credit proposal and the RM's credit request)

    doc, applied = apply(doc, rules, model_used=False)

Each rule gives one line under "Rules applied": {rule_id, text, kind, scope, author_name, status, effect, count}, status one of
    applied        the rule changed the document (effect says how, count how often)
    in_place       the document already follows it
    flagged        the rule cannot be applied without inventing content; the line says what the analyst has to add or reword
    model          an instruction the model followed while writing (the model wrote at least one section)
    noted          an instruction for the model; the template wrote this document, so the analyst checks it
    not_applicable the document has nothing the rule is about (no such section)
Figures are never changed: the units rule rewrites the unit word around a number, never the number; wording rules skip
citations, tables and the form lines (header block, signatures).
"""
from __future__ import annotations

import copy
import re
from typing import Any, Callable, Iterator

STOP = {"the", "a", "an", "and", "of", "for", "to", "in", "on", "with", "section", "part", "its", "by", "this", "that", "is", "be"}
#: words the analysts use for a section -> the section keys of the two shapes, in order of preference
ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary",), "executive summary": ("summary",), "financial analysis": ("financials", "synopsis"),
    "conduct of account": ("conduct", "relationship", "bureau"), "account conduct": ("conduct", "relationship", "bureau"),
    "action": ("action", "request"), "action requested": ("action", "request"), "request": ("request", "action"),
    "risks": ("risks", "cp_swot", "exceptions"), "risk": ("risks", "cp_swot", "exceptions"), "key risks": ("risks", "cp_swot"),
    "risks and mitigants": ("risks", "cp_swot"), "mitigants": ("risks", "cp_swot"), "swot": ("cp_swot",),
    "recommendation": ("recommendation", "justification"), "justification": ("justification", "recommendation"),
    "bureau": ("bureau", "conduct", "cbrbr"), "credit bureau": ("bureau", "conduct", "cbrbr"), "simah": ("bureau", "conduct"),
    "conduct": ("conduct", "relationship", "bureau"), "strengths": ("strengths",), "key strengths": ("strengths",),
    "signatures": ("signatures",), "approvals": ("signatures",), "financials": ("financials", "synopsis"),
    "security": ("security",), "collateral": ("security",), "facilities": ("facilities",), "terms": ("terms", "conditions"),
    "conditions": ("conditions", "terms"), "background": ("background", "obligor", "business"), "obligor": ("obligor", "background"),
    "business": ("business", "background"), "group exposure": ("group_exposure",), "relationship": ("relationship", "conduct"),
}
PROSE = ("p", "bullets", "numbered")
FIXED_TOP = ("header",)
FIXED_END = ("signatures",)


def _words(s: str) -> set[str]:
    return {(w[:-1] if len(w) > 4 and w.endswith("s") else w) for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP}


# ------------------------------------------------------------------ the document, read alike in both shapes

def shape(doc: dict[str, Any]) -> str:
    secs = doc.get("sections") or []
    return "blocks" if secs and "blocks" in secs[0] else "draft"


def find(doc: dict[str, Any], wanted: str) -> int | None:
    """The index of the section an analyst means by `wanted` (a key, a heading or a word for it)."""
    secs = doc.get("sections") or []
    w = (wanted or "").strip().lower().replace("_", " ")
    if not w:
        return None
    keys = [s["key"] for s in secs]
    for cand in (w.replace(" ", "_"), w):
        if cand in keys:
            return keys.index(cand)
    for name in (w, re.sub(r"\s+section$", "", w)):
        for k in ALIASES.get(name, ()):
            if k in keys:
                return keys.index(k)
    for i, s in enumerate(secs):
        if (s.get("heading") or "").strip().lower() == w:
            return i
    ww = _words(w)
    if not ww:
        return None
    best, best_sc = None, 0.0
    for i, s in enumerate(secs):
        hw = _words(s.get("heading") or "") | _words(s["key"].replace("_", " "))
        if not hw:
            continue
        sc = len(ww & hw) / len(ww)
        if sc > best_sc:
            best, best_sc = i, sc
    return best if best_sc >= 0.5 else None


class Prose:
    """Every prose string of a section, readable and rewritable (paragraphs and bullets, or p / bullets / numbered blocks)."""

    def __init__(self, sec: dict[str, Any]):
        self.sec = sec

    def items(self) -> Iterator[tuple[Callable[[], str], Callable[[str], None]]]:
        s = self.sec
        if "blocks" in s:
            for b in s["blocks"]:
                if b.get("t") == "p" and not b.get("exempt"):
                    yield (lambda b=b: b["text"]), (lambda v, b=b: b.__setitem__("text", v))
                elif b.get("t") in ("bullets", "numbered"):
                    for i in range(len(b.get("items") or [])):
                        yield (lambda b=b, i=i: b["items"][i]), (lambda v, b=b, i=i: b["items"].__setitem__(i, v))
        else:
            for name in ("paragraphs", "bullets"):
                for i in range(len(s.get(name) or [])):
                    yield (lambda n=name, i=i: s[n][i]), (lambda v, n=name, i=i: s[n].__setitem__(i, v))

    def text(self) -> str:
        return "\n".join(g() for g, _ in self.items())

    def all_text(self) -> str:
        """Prose and table cells (a fact may sit in a table)."""
        out = [self.text()]
        s = self.sec
        tables = [b for b in s.get("blocks", []) if b.get("t") in ("table", "kv")] if "blocks" in s else ([s["table"]] if s.get("table") else [])
        for t in tables:
            rows = t.get("rows") or t.get("pairs") or []
            out += [" ".join(str(c) for c in r) for r in rows]
            out.append(" ".join(str(c) for c in t.get("header") or []))
        return "\n".join(out)

    def rewrite(self, fn: Callable[[str], tuple[str, int]]) -> int:
        n = 0
        for g, st in self.items():
            new, k = fn(g())
            if k:
                st(new)
                n += k
        return n


def _sections_for(doc: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    secs = doc.get("sections") or []
    if rule.get("section"):
        i = find(doc, rule["section"])
        return [secs[i]] if i is not None else []
    return [s for s in secs if s["key"] not in FIXED_TOP + FIXED_END]


def _names(doc: dict[str, Any]) -> list[str]:
    """The proper names of the document (customer, group, obligor): never reworded."""
    m = doc.get("meta") or {}
    out = [doc.get("customer"), doc.get("group"), m.get("name"), m.get("group"), m.get("customer")]
    return sorted({str(x) for x in out if x and len(str(x)) > 3}, key=len, reverse=True)


def _protect(text: str, names: list[str] | None = None) -> tuple[str, list[str]]:
    """Citations ([F3], [D2], [RM]) and the document's proper names out of reach of a wording rule."""
    held: list[str] = []

    def keep(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"\x00{len(held) - 1}\x00"
    pats = [r"\[[A-Za-z]{1,4}\d*\]"] + [re.escape(n) for n in (names or [])]
    return re.sub("|".join(pats), keep, text), held


def _restore(text: str, held: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)


def _case_like(src: str, word: str) -> str:
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


# ------------------------------------------------------------------ the kinds

def _wording(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    p = rule["params"]
    use, old = p.get("use", ""), p.get("instead_of", "")
    if not use or not old:
        return "not_applicable", "The rule names no wording.", 0
    rx = re.compile(rf"\b({re.escape(old)})(s?)\b", re.I)
    names = _names(doc)

    def fn(t: str) -> tuple[str, int]:
        body, held = _protect(t, names)
        k = 0

        def sub(m: re.Match[str]) -> str:
            nonlocal k
            before = body[:m.start()].rstrip()
            prev = re.search(r"([A-Za-z][\w&'-]*)$", before)
            # part of a proper name ("Al Rayyan Medical Supply Company"): a capitalised word glued to a capitalised word
            if m.group(1)[:1].isupper() and prev and prev.group(1)[:1].isupper() and not re.search(r"[.:;!?]\s*$", body[:m.start()]):
                return m.group(0)
            k += 1
            return _case_like(m.group(1), use) + (m.group(2) if not use.endswith("s") else "")
        new = rx.sub(sub, body)
        return _restore(new, held), k
    n = sum(Prose(s).rewrite(fn) for s in _sections_for(doc, rule))
    if n:
        return "applied", f"“{old}” replaced by “{use}” {n} time{'s' if n != 1 else ''}.", n
    return "in_place", f"No “{old}” in the document.", 0


def _avoid(doc: dict[str, Any], rule: dict[str, Any], model_used: bool) -> tuple[str, str, int]:
    ph = rule["params"].get("phrase", "")
    rx = re.compile(rf"\b{re.escape(ph)}\b", re.I)
    hits = [(s["heading"], len(rx.findall(Prose(s).text()))) for s in _sections_for(doc, rule)]
    n = sum(k for _, k in hits)
    if not n:
        return ("model" if model_used else "in_place"), f"No “{ph}” in the document.", 0
    where = ", ".join(h for h, k in hits if k)
    return "flagged", f"“{ph}” appears {n} time{'s' if n != 1 else ''} ({where}): reword it, the rule gives no replacement.", n


MONEY = re.compile(r"\b(SAR|AED|USD|EUR|QAR|KWD|BHD|OMR)\s?(-?\d[\d,]*(?:\.\d+)?)\s?(m|mn|million)\b(?!\w)")
PCT_WORD = re.compile(r"(\d(?:[\d,]*\d)?(?:\.\d+)?)\s?per ?cent\b", re.I)
PCT_SIGN = re.compile(r"(\d(?:[\d,]*\d)?(?:\.\d+)?)\s?%")


def _units(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    p = rule["params"]
    suf, pct = p.get("money_suffix"), p.get("percent")
    n = 0
    sep = {"m": "", "mn": " ", "million": " "}

    def fn(t: str) -> tuple[str, int]:
        k = 0
        if suf:
            def money(m: re.Match[str]) -> str:
                nonlocal k
                out = f"{m.group(1)} {m.group(2)}{sep[suf]}{suf}"
                if out != m.group(0):
                    k += 1
                return out
            t = MONEY.sub(money, t)
        if pct == "%":
            t, j = PCT_WORD.subn(lambda m: f"{m.group(1)}%", t)
            k += j
        elif pct == "per cent":
            t, j = PCT_SIGN.subn(lambda m: f"{m.group(1)} per cent", t)
            k += j
        return t, k
    for s in _sections_for(doc, rule):
        n += Prose(s).rewrite(fn)
        n += _table_cells(s, fn)
    what = " and ".join(x for x in ((f"amounts as SAR 12.5{sep[suf]}{suf}" if suf else ""), (f"percentages as 12.5{'%' if pct == '%' else ' per cent'}" if pct else "")) if x)
    if n:
        return "applied", f"{n} figure{'s' if n != 1 else ''} rewritten with {what}; no number changed.", n
    return "in_place", f"Every figure already reads {what}.", 0


def _table_cells(sec: dict[str, Any], fn: Callable[[str], tuple[str, int]]) -> int:
    tables = [b for b in sec.get("blocks", []) if b.get("t") == "table"] if "blocks" in sec else ([sec["table"]] if sec.get("table") else [])
    n = 0
    for t in tables:
        for r in t.get("rows") or []:
            for j, c in enumerate(r):
                if isinstance(c, str):
                    new, k = fn(c)
                    if k:
                        r[j] = new
                        n += k
    return n


def _new_section(doc: dict[str, Any], heading: str, rule: dict[str, Any]) -> dict[str, Any]:
    key = "rule_" + re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")[:40]
    line = (f"{heading}: to be written by the analyst. This section is here because of the rule “{rule['text']}” "
            f"({rule.get('scope_label') or rule['scope']}, {rule.get('author_name') or rule['author']}).")
    if shape(doc) == "blocks":
        return {"key": key, "n": None, "heading": heading, "voice": "business", "part": "business", "blocks": [{"t": "p", "text": line, "exempt": False}],
                "gaps": ["written by the analyst (rule)"], "method": f"rule {rule['id']}", "rule_id": rule["id"]}
    return {"key": key, "heading": heading, "voice": "business", "judgement": False, "paragraphs": [line], "bullets": [], "table": None,
            "citations": [], "exemplars": [], "method": f"rule {rule['id']}", "status": "draft", "edited": False, "version": 1, "rule_id": rule["id"]}


def _insert_at(doc: dict[str, Any]) -> int:
    keys = [s["key"] for s in doc["sections"]]
    for k in ("recommendation", "justification", "signatures"):
        if k in keys:
            return keys.index(k)
    return len(keys)


def _include(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    h = rule["params"].get("heading", "")
    i = find(doc, h)
    if i is not None:
        return "in_place", f"The document has it: “{doc['sections'][i]['heading']}”.", 0
    doc["sections"].insert(_insert_at(doc), _new_section(doc, h, rule))
    return "applied", f"Section “{h}” added before the recommendation, for the analyst to write.", 1


def _move(doc: dict[str, Any], i: int, j: int) -> None:
    s = doc["sections"].pop(i)
    doc["sections"].insert(j if j <= i else j - 1, s)


def _order(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    p = rule["params"]
    secs = doc["sections"]
    if p.get("order"):  # a whole order (a gold standard's): the named sections take the slots they hold now, in that order
        idx = list(dict.fromkeys(i for i in (find(doc, n) for n in p["order"]) if i is not None))
        if len(idx) < 2:
            return "not_applicable", "The document has too few of the named sections.", 0
        slots = sorted(idx)
        if idx == slots:
            return "in_place", "The sections already follow that order.", 0
        moved = [secs[i] for i in idx]
        new = list(secs)
        for slot, sec in zip(slots, moved):
            new[slot] = sec
        names = [sec["heading"] for a, b, sec in zip(slots, idx, moved) if a != b]
        doc["sections"][:] = new
        return "applied", f"{len(names)} section{'s' if len(names) != 1 else ''} moved to follow the order: " + ", ".join(names) + ".", len(names)
    i = find(doc, p.get("section", ""))
    if i is None:
        return "not_applicable", f"The document has no {p.get('section')} section.", 0
    name = secs[i]["heading"]
    keys = [s["key"] for s in secs]
    if p.get("position") == "first":
        j = 0
        while j < len(keys) and keys[j] in FIXED_TOP:
            j += 1
        if i <= j:
            return "in_place", f"{name} already comes first.", 0
        _move(doc, i, j)
        return "applied", f"{name} moved to the top.", 1
    if p.get("position") == "last":
        j = next((k for k in range(len(keys)) if keys[k] in FIXED_END), len(keys))
        if i == j - 1:
            return "in_place", f"{name} already comes last.", 0
        _move(doc, i, j)
        return "applied", f"{name} moved to the end.", 1
    rel = "before" if p.get("before") else "after"
    o = find(doc, p.get(rel, ""))
    if o is None:
        return "not_applicable", f"The document has no {p.get(rel)} section.", 0
    other = secs[o]["heading"]
    target = o if rel == "before" else o + 1
    if (rel == "before" and i == o - 1) or (rel == "after" and i == o + 1):
        return "in_place", f"{name} already comes {rel} {other}.", 0
    _move(doc, i, target)
    return "applied", f"{name} moved {rel} {other}.", 1


def _heading(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    p = rule["params"]
    i = find(doc, p.get("section", "") or rule.get("section", ""))
    if i is None:
        return "not_applicable", f"The document has no {p.get('section')} section.", 0
    s = doc["sections"][i]
    if s["heading"] == p["heading"]:
        return "in_place", f"Already headed “{p['heading']}”.", 0
    old = s["heading"]
    s["heading"] = p["heading"]
    return "applied", f"“{old}” headed “{p['heading']}”.", 1


SPLIT = re.compile(r"\s*(?:[–—-]\s*mitigant:|;\s*mitigant:|\bmitigant:|\bmitigated by\b|\bmitigation:)\s*", re.I)
GENERIC = re.compile(r"^(?:the rm to state|mitigants to be set|mitigants:? to be)", re.I)


def _table(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    p = rule["params"]
    header = list(p.get("header") or ["Risk", "Mitigant"])
    i = find(doc, p.get("section") or rule.get("section") or "risks")
    if i is None:
        return "not_applicable", "The document has no risks section.", 0
    s = doc["sections"][i]
    tables = [b for b in s.get("blocks", []) if b.get("t") == "table"] if "blocks" in s else ([s["table"]] if s.get("table") else [])
    if any(any("mitig" in str(h).lower() for h in (t.get("header") or [])) for t in tables):
        return "in_place", f"{s['heading']} already tabulates risks against mitigants.", 0
    items: list[str] = []
    for g, _ in Prose(s).items():
        t = g().strip()
        if not t or GENERIC.match(t):
            continue
        m = re.match(r"^(Points? for the RM to assess|Risks?):\s*(.+)$", t, re.I)
        if m:
            items += [x.strip().rstrip(".") for x in m.group(2).split(";") if x.strip()]
        else:
            items.append(t)
    if not items:
        return "not_applicable", f"{s['heading']} names no risk to tabulate.", 0
    rows = []
    for it in items:
        parts = SPLIT.split(it, maxsplit=1)
        risk = parts[0].strip().rstrip(".")
        mit = parts[1].strip().rstrip(".") if len(parts) > 1 and parts[1].strip() else "Not stated: the analyst sets the mitigant"
        rows.append([risk[:1].upper() + risk[1:], mit[:1].upper() + mit[1:]])
    cites = sorted(set(re.findall(r"\[(F\d+)\]", " ".join(items))))
    if "blocks" in s:
        s["blocks"] = [b for b in s["blocks"] if b.get("t") not in PROSE or b.get("exempt")] + \
                      [{"t": "table", "header": header, "rows": rows, "source": f"Rule {rule['id']}: risks and mitigants tabulated", "widths": None, "size": 7.5}]
    else:
        s["paragraphs"], s["bullets"] = [], []
        s["table"] = {"header": header, "rows": rows, "cites": cites}
    return "applied", f"{len(rows)} risk{'s' if len(rows) != 1 else ''} tabulated as {' | '.join(header)}.", len(rows)


def _mention(doc: dict[str, Any], rule: dict[str, Any]) -> tuple[str, str, int]:
    ph = rule["params"].get("phrase", "")
    acr = [w for w in re.findall(r"\b[A-Z]{3,}\b", ph)]
    need = set(w.lower() for w in acr) or _words(ph)
    secs = _sections_for(doc, rule)
    if rule.get("section") and not secs:
        secs = [s for s in doc["sections"] if s["key"] not in FIXED_TOP]
    text = " ".join(Prose(s).all_text() for s in secs).lower()
    if need and all(re.search(rf"\b{re.escape(w)}", text) for w in need):
        return "in_place", f"{ph} is stated.", 0
    i = find(doc, rule.get("section") or "")
    where = doc["sections"][i]["heading"] if i is not None else "the document"
    return "flagged", f"{ph} is not stated in {where}: add it before the document goes on.", 1


def apply(doc: dict[str, Any], rules: list[dict[str, Any]], model_used: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A copy of the document with the rules applied, and one line per rule."""
    doc = copy.deepcopy(doc)
    out = []
    for r in rules:
        k = r["kind"]
        try:
            if k == "wording":
                st, eff, n = _wording(doc, r)
            elif k == "avoid":
                st, eff, n = _avoid(doc, r, model_used)
            elif k == "units":
                st, eff, n = _units(doc, r)
            elif k == "include_section":
                st, eff, n = _include(doc, r)
            elif k == "section_order":
                st, eff, n = _order(doc, r)
            elif k == "heading":
                st, eff, n = _heading(doc, r)
            elif k == "table":
                st, eff, n = _table(doc, r)
            elif k == "must_mention":
                st, eff, n = _mention(doc, r)
            else:
                st = "model" if model_used else "noted"
                eff = ("Given to the model as an instruction while it wrote." if model_used else
                       "An instruction for the model; the template wrote this document, so check it yourself.")
                n = 0
        except Exception as e:  # noqa: BLE001 - one rule's problem never stops a document
            st, eff, n = "not_applicable", f"Not applied ({type(e).__name__}).", 0
        out.append({"rule_id": r["id"], "text": r["text"], "kind": k, "scope": r["scope"], "scope_label": r.get("scope_label") or r["scope"],
                    "author": r["author"], "author_name": r.get("author_name") or r["author"], "document": r["document"],
                    "section": r.get("section") or "", "origin": r.get("origin") or "", "created_at": r.get("created_at") or "",
                    "status": st, "effect": eff, "count": n})
    return doc, out


def summary(applied: list[dict[str, Any]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for a in applied:
        c[a["status"]] = c.get(a["status"], 0) + 1
    c["total"] = len(applied)
    return c


def instructions(rules: list[dict[str, Any]], section: str = "") -> list[str]:
    """The rules as instructions for the model (a section's own rules and the document-wide ones)."""
    out = []
    for r in rules:
        if r.get("section") and section and find({"sections": [{"key": section, "heading": section}]}, r["section"]) is None \
                and r["section"] != section:
            continue
        out.append(r["text"])
    return out
