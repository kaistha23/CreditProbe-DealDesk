"""R16 v: what Noor actually says, so a neural voice sounds like a person reading a brief, not a screen reader.

    speakable_en("Exposure is SAR 1.48 bn, up 12.5% YoY.")
      -> "Exposure is one point four eight billion riyals, up twelve point five percent year on year."

Rules (pure, tested in tests/v5/voice/test_pacing.py):
  * numbers are spoken as words: amounts with their scale and currency ("SAR 1.48 bn" -> "one point four eight billion
    riyals"), percentages, basis points, multiples ("3.2x" -> "three point two times"), ordinals, years
    ("2026" -> "twenty twenty-six"), negatives ("-3%" -> "minus three percent"), ranges ("3-5" -> "three to five");
  * abbreviations a banker says in full (bn, mn, YoY, vs, e.g.) are expanded; short all-capital acronyms are spelled
    letter by letter ("ECL" -> "E C L") unless they are said as a word (SAMA, RAROC);
  * the text is cut into short sentences (a long one is split at a semicolon, a colon or a dash) and each sentence
    carries the pause that follows it: a full stop, a question, a paragraph. Commas stay in the text, and the
    neural models pause on them;
  * Arabic: digits (Western or Arabic-Indic) become Arabic number words, "%" becomes "بالمئة", "SAR" / "ر.س" becomes
    "ريال".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Bump when the rules change: it is part of the audio cache key, so old audio is not replayed with new rules.
PACING_VERSION = "r16v-2"

#: Pauses after a sentence, in seconds (natural reading: a breath at a full stop, longer at a paragraph).
PAUSE_STOP = 0.42
PAUSE_QUESTION = 0.5
PAUSE_SPLIT = 0.28
PAUSE_PARAGRAPH = 0.7
LONG_SENTENCE_WORDS = 24


@dataclass(frozen=True)
class Sentence:
    text: str
    pause: float


# ---------------------------------------------------------------------------------------------------------- English

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")]
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
        "twelve": "twelfth"}


def _under_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, u = divmod(n, 10)
    return _TENS[t] + (f"-{_ONES[u]}" if u else "")


def _under_1000(n: int) -> str:
    h, r = divmod(n, 100)
    if not h:
        return _under_100(r)
    return f"{_ONES[h]} hundred" + (f" and {_under_100(r)}" if r else "")


def int_words(n: int) -> str:
    """Cardinal in words, British style ("one hundred and twenty")."""
    if n < 0:
        return "minus " + int_words(-n)
    if n < 1000:
        return _under_1000(n)
    parts: list[str] = []
    for size, word in _SCALES:
        if n >= size:
            q, n = divmod(n, size)
            parts.append(f"{int_words(q)} {word}")
    if n:
        parts.append(("and " if n < 100 else "") + _under_1000(n))
    return " ".join(parts)


def number_words(s: str) -> str:
    """'1,480.25' -> 'one thousand four hundred and eighty point two five'; '-0.9' -> 'minus zero point nine'."""
    s = s.replace(",", "").strip()
    neg = s.startswith(("-", "−"))
    s = s.lstrip("-−+")
    whole, _, frac = s.partition(".")
    words = int_words(int(whole or "0"))
    frac = frac.rstrip("0")
    if frac:
        words += " point " + " ".join(_ONES[int(d)] for d in frac)
    return ("minus " if neg else "") + words


def year_words(y: int) -> str:
    """2026 -> 'twenty twenty-six'; 2000 -> 'two thousand'; 2005 -> 'two thousand and five'; 1999 -> 'nineteen ninety-nine'."""
    hi, lo = divmod(y, 100)
    if y % 1000 == 0 or (2000 <= y <= 2009):
        return int_words(y)
    return f"{_under_100(hi)} " + (_under_100(lo) if lo >= 10 else f"oh {_ONES[lo]}" if lo else "hundred")


def ordinal_words(n: int) -> str:
    w = int_words(n)
    head, sep, last = w.rpartition(" ")
    last_head, dash, last_unit = last.rpartition("-")
    unit = last_unit
    if unit in _ORD:
        unit = _ORD[unit]
    elif unit.endswith("y"):
        unit = unit[:-1] + "ieth"
    else:
        unit += "th"
    return f"{head}{sep}{last_head}{dash}{unit}"


_CURRENCY = {"SAR": "riyals", "SR": "riyals", "USD": "dollars", "US$": "dollars", "$": "dollars", "AED": "dirhams",
             "EUR": "euros", "€": "euros", "GBP": "pounds", "£": "pounds", "KWD": "dinars", "QAR": "riyals"}
_SINGULAR = {"riyals": "riyal", "dollars": "dollar", "dirhams": "dirham", "euros": "euro", "pounds": "pound",
             "dinars": "dinar"}
_SCALE_WORD = {"tn": "trillion", "trillion": "trillion", "bn": "billion", "b": "billion", "billion": "billion",
               "mn": "million", "m": "million", "mm": "million", "million": "million", "k": "thousand",
               "thousand": "thousand"}

_NUM = r"[-−]?\d[\d,]*(?:\.\d+)?|[-−]?\.\d+"
_CUR = r"SAR|SR|USD|US\$|\$|AED|EUR|€|GBP|£|KWD|QAR"
_SCALE = r"tn|trillion|bn|billion|b|mn|mm|million|m|k|thousand"

_MONTHS = {"may": "May", "jan": "January", "feb": "February", "mar": "March", "apr": "April", "jun": "June", "jul": "July",
           "aug": "August", "sep": "September", "sept": "September", "oct": "October", "nov": "November",
           "dec": "December"}

#: Said in full by a banker (word boundaries; case-sensitive where the lower-case form is an ordinary word).
_ABBREV = [
    (r"\be\.g\.", "for example"), (r"\bi\.e\.", "that is"), (r"\betc\.", "and so on"), (r"\bvs\.?(?=\s)", "versus"),
    (r"\bapprox\.?(?=\s)", "about"), (r"\bYoY\b", "year on year"), (r"\bQoQ\b", "quarter on quarter"),
    (r"\bMoM\b", "month on month"), (r"\bYTD\b", "year to date"), (r"\bw/o\b", "without"), (r"\bw/(?=\s)", "with"),
    (r"\band/or\b", "and or"), (r"\bMr\.", "Mister"), (r"\bMrs\.", "Missus"), (r"\bDr\.", "Doctor"),
    (r"\bNo\.\s?(?=\d)", "number "), (r"\bp\.?a\.(?=\s|$)", "a year"), (r"\bpp\b", "percentage points"),
    (r"\bbps\b|\bbp\b", "basis points"), (r"\bKSA\b", "the Kingdom"), (r"&", " and "),
]

#: All-capital words said as a word, not spelled.
_SAID_AS_WORD = {"SAMA", "RAROC", "NATO", "OPEC", "LIBOR", "SOFR", "SAIBOR", "COVID", "NEOM", "OK", "I", "A"}


def _amount(num: str, scale: str | None, cur: str | None) -> str:
    words = number_words(num)
    out = words + (f" {_SCALE_WORD[scale.lower()]}" if scale else "")
    if cur:
        name = _CURRENCY.get(cur.upper() if cur[0].isalpha() else cur, "")
        if name:
            one = not scale and re.fullmatch(r"[-−]?1(?:\.0+)?", num.replace(",", ""))
            out += " " + (_SINGULAR.get(name, name) if one else name)
    return out


def _spell(m: re.Match[str]) -> str:
    w = m.group(0)
    if w in _SAID_AS_WORD or len(w) > 6:
        return w
    return " ".join(w)


def speakable_en(text: str) -> str:
    """The English text as it should be spoken (numbers, abbreviations and symbols in words). One line per paragraph."""
    t = str(text or "")
    t = re.sub(r"[*_`#>]+", " ", t)                                   # markdown
    t = re.sub(r"^\s*[•\-–·]\s+", "", t, flags=re.M)                   # bullets
    t = re.sub(r"\s*\([^()]*[÷×=][^()]*\)", "", t)                        # a formula in brackets is not read out
    t = t.replace("÷", " divided by ").replace("×", " times ").replace(" = ", " equals ").replace("≥", " at least ") \
         .replace("≤", " at most ").replace(" > ", " above ").replace(" < ", " below ")
    t = re.sub(r"(?<![\w.])(\d{4})\s?Q([1-4])\b", r"Q\2 \1", t)                # 2026Q3 -> Q3 2026
    t = t.replace("→", ", then ").replace("≈", "about ").replace("~", "about ").replace("±", "plus or minus ")
    t = re.sub(r"\s+[—–]\s+", ", ", t)                                 # a dash between words is a pause
    t = re.sub(r"(?<=\d)\s?[–—-]\s?(?=\d)", " to ", t)                 # ranges 3-5, 2025–2026
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)
    t = re.sub(r"(?<![\w.])([0-3]?\d)\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|"
               r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?",
               lambda m: f"the {ordinal_words(int(m.group(1)))} of {_MONTHS.get(m.group(2).lower()[:4] if m.group(2).lower().startswith('sept') else m.group(2).lower()[:3], m.group(2))}", t)
    t = re.sub(r"(?<![\d.,])360(?![\d.,%]|\s?(?:bn|mn|m|k|million|billion)\b)", " three sixty", t)
    t = re.sub(r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?(?=\s+\d)", lambda m: _MONTHS[m.group(1).lower()], t)
    # amounts: currency first ("SAR 1.48 bn"), currency after ("1.48 bn SAR"), then a bare scale ("640m")
    t = re.sub(rf"(?<![\w.])({_CUR})\s?({_NUM})(?:\s?({_SCALE})\b)?",
               lambda m: _amount(m.group(2), m.group(3), m.group(1)), t)
    t = re.sub(rf"(?<![\w.])({_NUM})\s?({_SCALE})?\s?\b({_CUR})\b",
               lambda m: _amount(m.group(1), m.group(2), m.group(3)), t)
    t = re.sub(rf"(?<![\w.])({_NUM})\s?({_SCALE})\b", lambda m: _amount(m.group(1), m.group(2), None), t)
    t = re.sub(rf"(?<![\w.])({_NUM})\s?%", lambda m: number_words(m.group(1)) + " percent", t)
    t = re.sub(rf"(?<![\w.])({_NUM})x\b", lambda m: number_words(m.group(1)) + " times", t)
    t = re.sub(r"(?<![\w.])(\d+)(st|nd|rd|th)\b", lambda m: ordinal_words(int(m.group(1))), t)
    t = re.sub(r"\bQ([1-4])\b", lambda m: "Q " + _ONES[int(m.group(1))], t)
    t = re.sub(r"\bH([12])\b", lambda m: "H " + _ONES[int(m.group(1))], t)
    t = re.sub(r"\bFY\s?(\d{4})\b", lambda m: "F Y " + year_words(int(m.group(1))), t)
    t = re.sub(r"\bFY\s?(\d{2})\b", lambda m: "F Y " + _under_100(int(m.group(1))), t)
    t = re.sub(r"(?<![\w.,])(19\d\d|20\d\d)(?![\w.,]\d|\d)", lambda m: year_words(int(m.group(1))), t)
    t = re.sub(r"(?<![\w.])(\d{1,2}):(\d{2})\b",
               lambda m: f"{int_words(int(m.group(1)))} " + ("o'clock" if m.group(2) == "00" else
                                                             (f"oh {_ONES[int(m.group(2))]}" if m.group(2)[0] == "0" else _under_100(int(m.group(2))))), t)
    t = re.sub(rf"(?<![\w.])({_NUM})(?![\w])", lambda m: number_words(m.group(1)), t)
    t = re.sub(r"(?<=[A-Za-z])(\d[\d,]*(?:\.\d+)?)", lambda m: " " + number_words(m.group(1)), t)  # B360, X5
    t = re.sub(r"\b(SAR|SR)\b", "riyals", t)
    t = re.sub(r"\b[A-Z]{2,6}\b", _spell, t)
    t = t.replace("/", " ").replace("(", ", ").replace(")", ", ").replace("[", " ").replace("]", " ")
    t = re.sub(r"[\"“”‘’]", "", t).replace(" '", " ").replace("' ", " ")
    t = re.sub(r"\s*,\s*(?:,\s*)+", ", ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",([.;:!?])", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    return "\n".join(line.strip(" ,") for line in t.split("\n") if line.strip(" ,"))


# ---------------------------------------------------------------------------------------------------------- Arabic

_A_ONES = ["صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
_A_TEENS = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر",
            "تسعة عشر"]
_A_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_A_HUNDREDS = ["", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة", "ستمئة", "سبعمئة", "ثمانمئة", "تسعمئة"]
_A_SCALES = [(10**9, ("مليار", "ملياران", "مليارات")), (10**6, ("مليون", "مليونان", "ملايين")),
             (1000, ("ألف", "ألفان", "آلاف"))]
_A_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


def _a_under_1000(n: int) -> str:
    h, r = divmod(n, 100)
    parts = [_A_HUNDREDS[h]] if h else []
    if r:
        if r < 10:
            parts.append(_A_ONES[r])
        elif r < 20:
            parts.append(_A_TEENS[r - 10])
        else:
            t, u = divmod(r, 10)
            parts.append((f"{_A_ONES[u]} و" if u else "") + _A_TENS[t])
    return " و".join(parts) if parts else _A_ONES[0]


def int_words_ar(n: int) -> str:
    if n < 0:
        return "سالب " + int_words_ar(-n)
    if n < 1000:
        return _a_under_1000(n)
    parts: list[str] = []
    for size, (one, two, many) in _A_SCALES:
        if n >= size:
            q, n = divmod(n, size)
            parts.append(one if q == 1 else two if q == 2 else f"{int_words_ar(q)} {many if q <= 10 else one}")
    if n:
        parts.append(_a_under_1000(n))
    return " و".join(parts)


def number_words_ar(s: str) -> str:
    s = s.translate(_A_DIGITS).replace(",", "").strip()
    neg = s.startswith(("-", "−"))
    whole, _, frac = s.lstrip("-−+").partition(".")
    words = int_words_ar(int(whole or "0"))
    if frac:
        words += " فاصلة " + " ".join(_A_ONES[int(d)] for d in frac)
    return ("سالب " if neg else "") + words


def speakable_ar(text: str) -> str:
    t = str(text or "").translate(_A_DIGITS)
    t = re.sub(r"[*_`#>]+", " ", t)
    t = re.sub(r"^\s*[•\-–·]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+[—–]\s+", "، ", t)
    t = re.sub(r"(?<=\d)\s?[–—-]\s?(?=\d)", " إلى ", t)
    scale_ar = {"bn": "مليار", "b": "مليار", "mn": "مليون", "m": "مليون", "k": "ألف"}
    t = re.sub(rf"(?<![\w.])(SAR|SR|ر\.س\.?)\s?({_NUM})\s?(bn|mn|b|m|k)?(?![A-Za-z])",
               lambda m: number_words_ar(m.group(2)) + (f" {scale_ar[m.group(3)]}" if m.group(3) else "") + " ريال", t)
    t = re.sub(rf"(?<![\w.])({_NUM})\s?(bn|mn|b|m|k)(?![A-Za-z])",
               lambda m: number_words_ar(m.group(1)) + f" {scale_ar[m.group(2)]}", t)
    t = re.sub(rf"(?<![\w.])({_NUM})\s?[%٪]", lambda m: number_words_ar(m.group(1)) + " بالمئة", t)
    t = re.sub(rf"(?<![\w.])({_NUM})", lambda m: number_words_ar(m.group(1)), t)
    t = re.sub(r"\b(SAR|SR)\b|ر\.س\.?", "ريال", t)
    t = t.replace("(", "، ").replace(")", "، ").replace("/", " ")
    t = re.sub(r"[\"“”«»]", "", t)
    t = re.sub(r"\s*([،,])\s*(?:[،,]\s*)+", r"\1 ", t)
    t = re.sub(r"\s+([،,.;:!?؟])", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    return "\n".join(line.strip(" ،,") for line in t.split("\n") if line.strip(" ،,"))


# ---------------------------------------------------------------------------------------------------------- sentences

_END = re.compile(r"(?<=[.!?؟])\s+")
_SPLIT_AT = re.compile(r"\s*(?:;|:(?!\d)|؛)\s+")


def sentences(text: str, lang: str = "en") -> list[Sentence]:
    """Short spoken sentences with the pause after each. `text` is raw: it is made speakable here."""
    spoken = speakable_ar(text) if lang.startswith("ar") else speakable_en(text)
    out: list[Sentence] = []
    for para in [p for p in spoken.split("\n") if p.strip()]:
        parts = [p.strip() for p in _END.split(para) if p.strip()]
        for i, s in enumerate(parts):
            pieces = _short(s)
            for j, piece in enumerate(pieces):
                last = j == len(pieces) - 1
                pause = (PAUSE_QUESTION if piece.endswith(("?", "؟", "!")) else PAUSE_STOP) if last else PAUSE_SPLIT
                out.append(Sentence(_finish(piece), pause))
        if out:
            out[-1] = Sentence(out[-1].text, max(out[-1].pause, PAUSE_PARAGRAPH))
    if out:
        out[-1] = Sentence(out[-1].text, 0.0)
    return out


def _short(s: str) -> list[str]:
    """A long sentence is cut at a semicolon or a colon (then at ', and' / ', but') into shorter ones."""
    if len(s.split()) <= LONG_SENTENCE_WORDS:
        return [s]
    parts = _merge_tiny([p for p in _SPLIT_AT.split(s) if p.strip()])
    if len(parts) == 1:
        parts = [p for p in re.split(r",\s+(?=(?:and|but|while|so|whereas|و)\s)", s) if p.strip()]
    if len(parts) == 1:
        return [s]
    out: list[str] = []
    for p in parts:
        out.extend(_short(p) if len(p.split()) > LONG_SENTENCE_WORDS and p != s else [p])
    return out


def _merge_tiny(parts: list[str], least: int = 4) -> list[str]:
    """'First: Stage 3 provision ...' is one thought: a piece under `least` words joins the next with a comma."""
    out: list[str] = []
    carry = ""
    for p in parts:
        p = f"{carry}, {p}" if carry else p
        carry = ""
        if len(p.split()) < least and p is not parts[-1]:
            carry = p
            continue
        out.append(p)
    if carry:
        out.append(carry)
    return out


def _finish(s: str) -> str:
    s = s.strip().rstrip(",;:، ")
    if s and s[-1] not in ".!?؟":
        s += "."
    return s[:1].upper() + s[1:] if s[:1].isascii() else s
