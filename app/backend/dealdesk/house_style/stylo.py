"""Text measures shared by the profile, the drafter and the fidelity check (pure Python, deterministic)."""
from __future__ import annotations

import re
from typing import Any

HEDGES = ("may", "might", "could", "appears", "appear", "seems", "seem", "likely", "possibly", "potentially", "expected to",
          "should be able", "believed", "broadly", "largely", "we understand", "is understood")
CERTAIN = ("will", "must", "shall", "confirmed", "clearly", "certainly", "is required", "are required", "does not", "do not")
FIRST_PERSON = re.compile(r"\b(we|our|us|i)\b", re.I)
PASSIVE = re.compile(r"\b(is|are|was|were|be|been|being)\s+(\w+ed|\w+en|paid|held|made|met|set|kept|sought)\b", re.I)
MONEY = re.compile(r"\b(AED|SAR|USD)\s?(-?[\d,]+(?:\.\d+)?)\s?(bn|billion|mn|million|m)?\b(?!\w)")
PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s?(%|per cent|percent)")
MULTIPLE = re.compile(r"\b(\d+(?:\.\d+)?)\s?(x|times)\b")
ABBREV = re.compile(r"\b(?:[A-Z][A-Z0-9&]{1,6}(?:-[A-Z0-9]{1,4})?|CC Level \d)\b")
NOT_ABBREV = {"I", "A", "AED", "SAR", "USD", "LLC", "PJSC", "II", "III", "IV", "FY", "Q1", "Q2", "Q3", "Q4", "AND", "THE", "OF", "CR"}

#: spelled-out forms the house abbreviates (P1: CC Level 1, CBRBR, AECB, EOT, APG and the usual)
GLOSSARY = {
    "AECB": "Al Etihad Credit Bureau", "CBRBR": "Central Bank Risk Bureau Report", "EOT": "extension of time",
    "APG": "advance payment guarantee", "PBG": "performance bond guarantee", "CC Level 1": "Credit Committee Level 1",
    "CC Level 2": "Credit Committee Level 2", "CRO": "Chief Risk Officer", "CBUAE": "Central Bank of the UAE",
    "CRM": "Credit Risk Management", "RM": "relationship manager", "DSCR": "debt service coverage ratio",
    "LTV": "loan to value", "LG": "letter of guarantee", "LC": "letter of credit", "TNW": "tangible net worth",
    "DPD": "days past due", "SICR": "significant increase in credit risk", "RAROC": "risk-adjusted return on capital",
    "SIMAH": "Saudi Credit Bureau", "EBITDA": "earnings before interest, tax, depreciation and amortisation",
}
US_UK = {"organization": "organisation", "authorized": "authorised", "realize": "realise", "utilization": "utilisation",
         "amortization": "amortisation", "favorable": "favourable", "behavior": "behaviour", "analyze": "analyse",
         "center": "centre", "program ": "programme ", "prioritize": "prioritise", "minimize": "minimise",
         "recognized": "recognised", "capitalization": "capitalisation", "labor": "labour"}


def sentences(text: str) -> list[str]:
    text = re.sub(r"\[F\d+\]", "", text or "")
    parts = [x for line in text.strip().splitlines() for x in re.split(r"(?<=[.;!?])\s+(?=[A-Z(])", line.strip())]
    return [p.strip() for p in parts if len(re.findall(r"[A-Za-z]{2,}", p)) >= 2]


def words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z'-]*", re.sub(r"\[F\d+\]", "", (text or "").lower()))


def ngrams(text: str, n: int) -> list[str]:
    w = [x for x in words(re.sub(r"[\d,.]+", " # ", text))]
    return [" ".join(w[i:i + n]) for i in range(len(w) - n + 1)]


def opener(sentence: str, n: int = 3) -> str:
    w = words(re.sub(r"[\d,.]+", " # ", sentence))
    return " ".join(w[:n])


def money_style(m: re.Match) -> str:
    """'AED #m', 'AED # million', 'AED #mn', 'AED #bn' ... and decimals."""
    unit = (m.group(3) or "").lower()
    unit = {"million": " million", "billion": " billion", "m": "m", "mn": "mn", "bn": "bn"}.get(unit, "")
    num = m.group(2)
    dec = len(num.split(".")[1]) if "." in num else 0
    sep = "," in num
    return f"{m.group(1)} #{unit}" + ("" if not dec else f" ({dec}dp)") + (" (,)" if sep else "")


def unit_style(m: re.Match) -> str:
    return {"m": "m", "mn": "mn", "million": "million", "bn": "bn", "billion": "billion"}.get((m.group(3) or "").lower(), "none")


def measure(text: str) -> dict[str, float]:
    """Additive counts for one text: sentences, words, length sum/sumsq, hedges, certainty, first person, passive."""
    ss = sentences(text)
    out = {"sentences": 0.0, "words": 0.0, "len_sum": 0.0, "len_sq": 0.0, "hedge": 0.0, "certain": 0.0, "first": 0.0, "passive": 0.0}
    for s in ss:
        n = len(words(s))
        low = " " + s.lower() + " "
        out["sentences"] += 1
        out["words"] += n
        out["len_sum"] += n
        out["len_sq"] += n * n
        out["hedge"] += sum(low.count(f" {h} ") for h in HEDGES)
        out["certain"] += sum(low.count(f" {c} ") for c in CERTAIN)
        out["first"] += len(FIRST_PERSON.findall(s))
        out["passive"] += 1 if PASSIVE.search(s) else 0
    return out


def rates(m: dict[str, float]) -> dict[str, float | None]:
    n, w = m.get("sentences", 0.0), m.get("words", 0.0)
    if not n:
        return {"sentence_words": None, "sentence_sd": None, "hedges_per_100w": None, "certainty_per_100w": None,
                "first_person_per_100w": None, "passive_share": None}
    mean = m["len_sum"] / n
    var = max(0.0, m["len_sq"] / n - mean * mean)
    return {"sentence_words": round(mean, 2), "sentence_sd": round(var ** 0.5, 2),
            "hedges_per_100w": round(100 * m["hedge"] / w, 3) if w else 0.0,
            "certainty_per_100w": round(100 * m["certain"] / w, 3) if w else 0.0,
            "first_person_per_100w": round(100 * m["first"] / w, 3) if w else 0.0,
            "passive_share": round(m["passive"] / n, 3)}


def abbreviations(text: str) -> list[str]:
    return [a for a in ABBREV.findall(text or "") if a not in NOT_ABBREV and not re.fullmatch(r"[A-Z]{2}\d{2,}.*|\d.*", a)
            and not re.fullmatch(r"(DD|PRP|CG|CB|CF|CC)\d.*", a) and not re.fullmatch(r"(AAA|AA|A|BBB|BB|B|CCC|CC|C)|P\d+", a)]


def spelling(text: str) -> dict[str, float]:
    low = (text or "").lower()
    uk = sum(low.count(v) for v in US_UK.values()) + len(re.findall(r"\w(isation|ised|ising)\b", low))
    us = sum(low.count(k) for k in US_UK) + len(re.findall(r"\w(ization|ized|izing)\b", low))
    return {"british": float(uk), "american": float(us)}


def fmt_money(value: float, ccy: str, style: dict[str, Any] | None = None) -> str:
    """A money figure in the house format (unit suffix, decimals, thousands separator); millions in, as the books."""
    style = style or {}
    unit = style.get("unit", "m")
    dp = int(style.get("decimals", 1))
    v = float(value)
    if unit in ("bn", "billion") or (style.get("bn_from") and abs(v) >= float(style["bn_from"]) and abs(v) % 1000 == 0):
        b = v / 1000.0
        num = f"{b:,.{0 if b.is_integer() else 2}f}".rstrip("0").rstrip(".") if not b.is_integer() else f"{int(b):,}"
        return f"{ccy} {num}{'bn' if unit != 'billion' else ' billion'}"
    if dp < 1 and round(v, 1) != round(v):
        dp = 1  # never round a figure away: the house's whole-number style applies to whole numbers
    if style.get("trim_integers") and round(v, dp) == round(v):
        dp = 0
    num = f"{v:,.{dp}f}" if style.get("separator", True) else f"{v:.{dp}f}"
    suffix = {"m": "m", "mn": "mn", "million": " million", "none": "m"}.get(unit, "m")
    return f"{ccy} {num}{suffix}"


def fmt_pct(value: float, style: dict[str, Any] | None = None, ratio: bool = True) -> str:
    style = style or {}
    v = value * 100 if ratio else value
    dp = int(style.get("pct_decimals", 1))
    s = f"{v:.{dp}f}"
    return s + (" per cent" if style.get("pct_word") else "%")
