"""P3: how close a memo is to the house style, and where it differs.

Score (0-100) = 30% structure + 35% phrase use + 35% stylometrics, each 0-1:
  structure      share of the house sections present x 0.6 + order agreement (concordant pairs) x 0.4, less 0.1 per foreign section
  phrase use     share of sentences that open like the house or use a house phrase, less phrases the RM removed before
  stylometrics   sentence length against the house mean and spread, hedging and first person not above the house, the house
                 number format, abbreviations the house uses (not their spelled-out forms), the house's spelling

The band is the bank's own memos scored leave-one-out (each memo against a profile built without it): a draft "reads
like the house" when it scores at or above the band's low end. The lint lists each place a draft differs from the house.
"""
from __future__ import annotations

import math
import re
from typing import Any

from backend.dealdesk.house_style import profile as prof
from backend.dealdesk.house_style import stylo

WEIGHTS = {"structure": 0.30, "phrase": 0.35, "stylometrics": 0.35}
_BAND_CACHE: dict[str, dict[str, Any]] = {}


def _business_sections(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in doc["sections"] if s["key"] not in ("preamble",) and s.get("voice", "business") == "business"] \
        or [s for s in doc["sections"] if s["key"] != "preamble"]


def _text(s: dict[str, Any]) -> str:
    return "\n".join(s.get("paragraphs", []) + s.get("bullets", []))


def structure(doc: dict[str, Any], view: dict[str, Any]) -> float:
    house = [s["key"] for s in view["sections"]]
    if not house:
        return 1.0
    keys = []
    for s in _business_sections(doc):
        if s["key"] not in keys:
            keys.append(s["key"])
    common = [k for k in keys if k in house]
    cover = len(set(common)) / len(house)
    pairs = [(i, j) for i in range(len(common)) for j in range(i + 1, len(common))]
    order = 1.0 if not pairs else sum(1 for i, j in pairs if house.index(common[i]) < house.index(common[j])) / len(pairs)
    foreign = len([k for k in keys if k not in house and k != "other"])
    return max(0.0, min(1.0, 0.6 * cover + 0.4 * order - 0.1 * foreign))


def phrase_use(doc: dict[str, Any], view: dict[str, Any]) -> float:
    phr = {p["text"] for p in view.get("phrases", [])} | {p["text"] for p in view["learned"]["preferred"]}
    avoid = {p["text"] for p in view["learned"]["avoid"]}
    ops = {s["key"]: {o["text"] for o in s.get("openers", [])} for s in view["sections"]}
    all_ops = set().union(*ops.values()) if ops else set()
    hits = n = bad = 0
    for s in _business_sections(doc):
        for sent in stylo.sentences(_text(s)) + [b for b in s.get("bullets", []) if not stylo.sentences(b)]:
            n += 1
            grams = prof.phrases_of(sent)
            op = prof.opener_of(sent)
            if op in ops.get(s["key"], set()) or op in all_ops or grams & phr:
                hits += 1
            if grams & avoid:
                bad += 1
    if not n:
        return 0.0
    return max(0.0, min(1.0, hits / n - 0.5 * bad / n))


def _money_ok(text: str, view: dict[str, Any]) -> tuple[int, int]:
    unit = view["numbers"]["unit"]
    ok = n = 0
    for m in stylo.MONEY.finditer(text):
        n += 1
        u = stylo.unit_style(m)
        if u == unit or u in ("bn", "billion") or (u == "none" and unit in ("none",)):
            ok += 1
    return ok, n


def _spelled_out(text: str, view: dict[str, Any]) -> list[tuple[str, str]]:
    used = {a["text"] for a in view.get("abbreviations", [])}
    house = " ".join(p["text"] for p in view.get("phrases", []))
    low = text.lower()
    return [(abbr, full) for abbr, full in stylo.GLOSSARY.items()
            if abbr in used and full.lower() in low and full.lower() not in house]


def stylometrics(doc: dict[str, Any], view: dict[str, Any]) -> tuple[float, dict[str, float]]:
    text = "\n".join(_text(s) for s in _business_sections(doc))
    r = stylo.rates(stylo.measure(text))
    h = view.get("style") or {}
    parts: dict[str, float] = {}
    if r["sentence_words"] is not None and h.get("sentence_words"):
        z = abs(r["sentence_words"] - h["sentence_words"]) / max(3.0, h.get("sentence_sd") or 3.0)
        parts["sentence_length"] = math.exp(-z * z / 2)
    if r["hedges_per_100w"] is not None:
        parts["hedging"] = math.exp(-max(0.0, r["hedges_per_100w"] - (h.get("hedges_per_100w") or 0.0)) / 1.0)
        parts["first_person"] = math.exp(-max(0.0, r["first_person_per_100w"] - (h.get("first_person_per_100w") or 0.0)) / 0.5)
    ok, n = _money_ok(text, view)
    if n:
        parts["number_format"] = ok / n
    so = _spelled_out(text, view)
    parts["abbreviations"] = math.exp(-0.5 * len(so))
    sp = stylo.spelling(text)
    if sp["british"] + sp["american"]:
        house_uk = view.get("spelling", "British") == "British"
        parts["spelling"] = (sp["british"] if house_uk else sp["american"]) / (sp["british"] + sp["american"])
    val = sum(parts.values()) / len(parts) if parts else 0.0
    return val, {k: round(v, 3) for k, v in parts.items()}


def score_doc(doc: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    st = structure(doc, view)
    ph = phrase_use(doc, view)
    sy, parts = stylometrics(doc, view)
    total = 100 * (WEIGHTS["structure"] * st + WEIGHTS["phrase"] * ph + WEIGHTS["stylometrics"] * sy)
    return {"total": round(total, 1), "structure": round(100 * st, 1), "phrase": round(100 * ph, 1), "stylometrics": round(100 * sy, 1),
            "stylometric_parts": parts}


def band(state_docs: list[dict[str, Any]], bank: str | None = None, key: str = "") -> dict[str, Any]:
    """The house's own memos scored leave-one-out: each memo against the profile built without it."""
    ck = f"{key}|{bank}"
    if key and ck in _BAND_CACHE:
        return _BAND_CACHE[ck]
    pool = [d for d in state_docs if prof.role_of(d) == "business" and d["source"] not in ("draft", "rm_edit")]
    mine = [d for d in pool if d["bank"] == bank] if bank else pool
    if len(mine) < 2:
        mine = pool
    scores = []
    for d in mine:
        rest = [x for x in state_docs if x["doc_id"] != d["doc_id"]]
        st = prof.build(rest)
        v = prof.view(st, d["bank"], d["kind"], d["segment"])
        scores.append({"doc_id": d["doc_id"], "score": score_doc(d, v)["total"]})
    vals = sorted(s["score"] for s in scores)
    if not vals:
        out = {"low": 0.0, "high": 100.0, "mean": None, "n": 0, "scores": []}
    else:
        low = vals[0] if len(vals) < 10 else vals[int(0.1 * (len(vals) - 1))]
        out = {"low": round(low, 1), "high": round(vals[-1], 1), "mean": round(sum(vals) / len(vals), 1), "n": len(vals), "scores": scores,
               "basis": f"{len(vals)} house memos scored leave-one-out" + (f" ({bank})" if bank and all(d['bank'] == bank for d in mine) else " (all banks)")}
    if key:
        _BAND_CACHE[ck] = out
    return out


# ---------------------------------------------------------------------------------------------- lint

def lint(doc: dict[str, Any], view: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    house = [s["key"] for s in view["sections"]]
    keys = [s["key"] for s in _business_sections(doc)]

    def add(rule: str, severity: str, section: str, message: str, excerpt: str = "", suggestion: str = "") -> None:
        out.append({"id": f"L{len(out) + 1}", "rule": rule, "severity": severity, "section": section, "message": message,
                    "excerpt": excerpt[:160], "suggestion": suggestion})

    for k in house:
        if k not in keys:
            sec = next(s for s in view["sections"] if s["key"] == k)
            add("missing_section", "major" if sec["presence"] >= 0.8 else "minor", k,
                f"The house includes '{sec['heading']}' in {round(100 * sec['presence'])}% of memos; this draft has none.")
    common = [k for k in keys if k in house]
    for i in range(len(common) - 1):
        if house.index(common[i]) > house.index(common[i + 1]):
            add("section_order", "minor", common[i + 1], f"House order puts '{common[i + 1]}' before '{common[i]}'.")
    h = view.get("style") or {}
    mean, sd = h.get("sentence_words") or 14.0, max(3.0, h.get("sentence_sd") or 3.0)
    unit = view["numbers"]["unit"]
    for s in _business_sections(doc):
        text = _text(s)
        for sent in stylo.sentences(text):
            n = len(stylo.words(sent))
            if n > mean + 2 * sd and n > 18:
                add("sentence_length", "minor", s["key"], f"{n} words; the house averages {mean:.0f} (sd {sd:.0f}).", sent,
                    "Split into two sentences.")
            low = " " + sent.lower() + " "
            hedges = [x for x in stylo.HEDGES if f" {x} " in low]
            if hedges and (h.get("hedges_per_100w") or 0) < 0.5:
                add("hedging", "minor", s["key"], f"Hedged wording ('{hedges[0]}'); the house states findings plainly.", sent,
                    "State the fact and its source, or move the view to the RM's judgement.")
            if stylo.FIRST_PERSON.search(sent) and (h.get("first_person_per_100w") or 0) < 0.3:
                add("voice", "minor", s["key"], "First person; the house writes in the third person (the relationship, the RM, the bank).", sent)
            if s.get("voice", "business") == "business" and re.search(r"credit (risk|division) (does not|cannot) support|we do not support", low):
                add("voice", "major", s["key"], "Credit-division wording in a business-unit section.", sent)
        for m in stylo.MONEY.finditer(text):
            u = stylo.unit_style(m)
            if u not in (unit, "bn", "billion") and not (u == "none" and unit == "none"):
                want = stylo.fmt_money(float(m.group(2).replace(",", "")), m.group(1), {"unit": unit, "decimals": 1, "trim_integers": True})
                add("number_format", "minor", s["key"], f"'{m.group(0)}' differs from the house format ('{want}').", m.group(0), want)
        for abbr, full in _spelled_out(text, view):
            add("abbreviation", "minor", s["key"], f"The house writes '{abbr}' for '{full}'.", full, abbr)
        if view.get("spelling", "British") == "British":
            for us, uk in stylo.US_UK.items():
                if us.strip() in text.lower():
                    add("spelling", "minor", s["key"], f"American spelling '{us.strip()}'; the house writes '{uk.strip()}'.", us.strip(), uk.strip())
        avoid = {p["text"] for p in view["learned"]["avoid"]}
        for g in sorted(prof.phrases_of(text) & avoid)[:3]:
            add("rm_avoids", "minor", s["key"], f"An RM removed '{g}' from an earlier draft.", g)
    return out


def assess(d: dict[str, Any], view: dict[str, Any], state: dict[str, Any] | None = None, band_docs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from backend.dealdesk.house_style import draft as dr
    from backend.dealdesk.house_style import store
    doc = dr.as_doc(d)
    sc = score_doc(doc, view)
    b = band(band_docs if band_docs is not None else store.corpus_docs(), view["bank"] if view["bank"] != "*" else None,
             key=store.corpus_key())
    sc["band"] = {k: b[k] for k in ("low", "high", "mean", "n") if k in b} | {"basis": b.get("basis", "")}
    sc["within_band"] = b["n"] == 0 or sc["total"] >= b["low"]
    for s in d["sections"]:
        one = {**doc, "sections": [x for x in doc["sections"] if x["key"] == s["key"]]}
        hs = next((x for x in view["sections"] if x["key"] == s["key"]), None)
        if not stylo.sentences(dr.section_text(s)):
            # no prose: right when the house writes this section as a table only
            s["score"] = 100.0 if hs and hs.get("paragraphs_per_memo", 1) <= 0.5 and s.get("table") else 50.0
        else:
            s["score"] = round(100 * (0.5 * phrase_use(one, view) + 0.5 * stylometrics(one, view)[0]), 1)
    return {"score": sc, "lint": lint(doc, view)}
