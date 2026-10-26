"""From what the user types to what the What-If thread does.

`read(text, ctx)` returns a Reading:
  intent      scenario | stack | new | intensify | other_model | compare | choose_method
              | undo | likelihood | explain | save | report | help | brainstorm | unclear
  steps       the structured shocks, grouped into steps by scope
  method      a method the user named ("delta" / "xgboost"), if any
  factor      the intensity factor for "intensify"
  assumptions every default the reading made, said plainly
  unread      what could not be read (a measure with no size, a size with no measure)

Binding rules (the 5318 reader took the first % in the sentence for every
measure; this one does not):
  * every measure mention (PD, LGD, CCF/EAD, rating, sector stress, stage
    migration, each MEV) takes the NEAREST unclaimed magnitude with no other
    measure between them, preferring the one after it;
  * the direction comes from a sign on the number, else the direction word
    nearest the magnitude inside that measure's own clause;
  * a scope (sector, sub-sector, product, borrower, facility, customer,
    account, stage) binds to the measure it follows; a scope before the first
    measure, or a single scope at the very end, covers every measure;
  * no scope named = the whole book (or Early Warning cohort) in scope.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.whatif_v5.domain import mev
from backend.whatif_v5.models.scenario import Scope, Shocks, Step, describe_shocks

# ------------------------------------------------------------------ vocabulary

NUM = r"[-+−–]?\s?\d+(?:\.\d+)?"
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a": 1, "an": 1, "single": 1}
UP = r"\b(increase[sd]?|increasing|rise[sn]?|rising|rose|up|higher|hike[sd]?|worsen(?:s|ed|ing)?|deteriorat\w*|grow\w*|jump\w*|spike[sd]?|widen\w*|stress\w*|shock\w*|worse|plus|add(?:ed|ing)?|raise[sd]?)\b"
DOWN = r"\b(decrease[sd]?|decreasing|fall[s]?|falling|fell|drop[s]?|dropp\w*|down|lower|declin\w*|cut[s]?|cutting|reduc\w*|shrink\w*|contract\w*|crash\w*|slump\w*|plunge[sd]?|collapse[sd]?|less|minus|ease[sd]?|improv\w*|tighten\w*)\b"

MEASURES: list[tuple[str, str]] = [
    ("stage", r"\b(\d+(?:\.\d+)?\s?%|half|a quarter|a third|all)\s+of\s+(?:the\s+)?stage\s?([123])\b[^.;]*?\b(?:to|into)\s+stage\s?([123])\b"),
    ("pd", r"\b(PDs?|probabilit(?:y|ies) of default|default probabilit(?:y|ies)|default rates?)\b"),
    ("haircut", r"\b((?:collateral\s+)?haircuts?)\b"),
    ("collateral", r"\b((?:the\s+)?(?:value\s+of\s+(?:the\s+)?)?(?:collateral|security|securities\s+held|pledged\s+assets?)(?:\s+(?:values?|cover(?:age)?|held))?)\b"),
    ("lgd", r"\b(LGDs?|loss(?:es)? given default|recovery rates?|recoveries)\b"),
    ("ccf", r"\b(CCFs?|credit conversion factors?|drawdowns?|utili[sz]ation)\b"),
    ("ead", r"\b(EADs?|exposure at default|exposures?)\b(?!\s+(?:to|in|of)\b)"),
    ("rating", r"\b(downgrad\w*|upgrad\w*|rating(?:s)?\s+(?:cut|migration|move|fall|drop|deteriorat\w*)|(?:cut|lower)\s+(?:the\s+)?ratings?|behaviou?r\s+scores?|score bands?)\b"),
    ("sector", r"\b(sector(?:al)?\s+(?:stress|shock|downturn|crisis|deterioration)|(?:mild|moderate|severe|extreme)\s+(?:sector\s+)?stress|(?:mild|moderate|severe|extreme)\s+(?:[A-Za-z]+\s+){1,2}?(?:sector\s+)?(?:stress|downturn|crisis|shock)|stress\s+(?:in|on|for)\s+the\s+\w+(?:\s\w+)?\s+sector)\b"),
    ("mev:gdp_nonoil", r"\b(non[-\s]?oil\s+(?:real\s+)?(?:GDP|growth|economy|activity))\b"),
    ("mev:gdp_real", r"\b((?:real\s+)?GDP(?:\s+growth)?|economic growth|recession)\b"),
    ("mev:brent", r"\b(oil(?:\s+prices?)?|brent|crude)\b"),
    ("mev:cpi", r"\b(inflation|CPI)\b"),
    ("mev:unemployment", r"\b(unemployment(?:\s+rate)?|jobless(?:ness)?)\b"),
    ("mev:saibor_3m", r"\b(SAIBOR|interbank\s+rates?)\b"),
    ("mev:repo", r"\b(repo(?:\s+rate)?|policy\s+rates?|interest\s+rates?|rates)\b"),
    ("mev:gov_spend", r"\b(government\s+(?:spending|expenditure)|fiscal\s+(?:spending|consolidation|cuts?|stimulus)|public\s+spending)\b"),
    ("mev:re_price", r"\b((?:real[-\s]estate|property|house|housing|home)\s+(?:prices?|values?)|REPI)\b"),
    ("mev:current_account", r"\b(current\s+account(?:\s+balance)?)\b"),
    ("mev:credit_growth", r"\b((?:private\s+)?credit\s+growth|(?:loan|lending)\s+growth)\b"),
]
INTENT_WORDS = {
    "undo": r"^\s*(undo|go back|remove the last( step| shock)?|drop the last( step| shock)?|take (that|the last) (back|out))\b",
    "other_model": r"\b(other|the other|another|alternative|second)\s+(model|method)\b|\brerun\b.*\b(xgboost|xgb|delta|machine learning|ml)\b|\b(re-?run|run|try|redo)\s+(it|this|that|the same(?: one| scenario)?)?\s*(with|using|on|under)\s+(xgboost|xgb|delta|machine learning|ml|the delta method)\b",
    "compare": r"\b(compare|comparison|side[-\s]by[-\s]side|both models|both methods|versus|vs\.?)\b",
    "likelihood": r"\b(how likely|likelihood|plausib\w*|probability of (this|the|such)|has (this|that|it) (ever )?happened|how (often|rare|extreme|severe) is|historically|in history|ever been)\b",
    "explain": r"^\s*(why|explain|what drove|what drives|break (it )?down|which (components?|drivers?)|walk me through|how did)\b",
    "save": r"^\s*(please\s+)?save\b|\bsave (this|it|the scenario)\b",
    "report": r"\b(word report|report in word|\.docx|generate (a |the )?report|download (the )?report)\b",
    "help": r"^\s*(help|what can you do|how does this work|what can i (ask|do))\b",
    "brainstorm": r"\b(brainstorm|ideas?|suggest\w*|recommend\w*|what (scenario|scenarios|stress) should|realistic|how severe should|what would be a (good|reasonable|plausible)|propose)\b",
    "new": r"\b(instead|new scenario|start (over|again|afresh)|now try|replace (it|the scenario)|from scratch|separately)\b",
    "stack": r"\b(also|on top|in addition|additionally|add (a|an|another)?|stack\w*|as well|combined? with|plus|layer)\b",
    "intensify": r"\b(intensity|intensify|more severe|less severe|harsher|milder|worse|double|triple|halve|half as|twice|three times|\d+(?:\.\d+)?\s?[x×]|[x×]\s?\d+(?:\.\d+)?|scale (it|this|the scenario)|ramp (it )?up)\b",
}
METHOD_WORDS = {"xgboost": r"\b(xgboost|xgb|machine[-\s]learning|\bml\b|gradient[-\s]boost\w*|the model-based)\b",
                "delta": r"\b(delta(?:\s+method)?|deterministic\s+method|parameter\s+delta)\b"}
SEVERITY = {"mild": 0.5, "moderate": 1.0, "severe": 2.0, "extreme": 3.0}
SECTOR_SYNONYMS = {
    "construction": "Construction", "contracting": "Construction", "contractors": "Construction",
    "real estate": "Real Estate", "property developers": "Real Estate", "property": "Real Estate",
    "hotels": "Hospitality", "hospitality": "Hospitality", "tourism": "Hospitality",
    "retail trade": "Retail Trade", "retailers": "Retail Trade", "wholesale": "Wholesale Trade",
    "manufacturing": "Manufacturing", "manufacturers": "Manufacturing", "transport": "Transport and Logistics",
    "logistics": "Transport and Logistics", "shipping": "Transport and Logistics",
    "agriculture": "Agriculture and Agri-processing", "chemicals": "Chemicals", "petrochemicals": "Chemicals",
    "healthcare": "Healthcare", "health care": "Healthcare", "it": "Information Technology",
    "information technology": "Information Technology", "technology": "Information Technology",
    "mining": "Metals and Mining", "metals": "Metals and Mining", "utilities": "Power and Utilities",
    "power": "Power and Utilities", "telecoms": "Telecommunications", "telecom": "Telecommunications",
    "telecommunications": "Telecommunications",
}
PRODUCT_SYNONYMS = {
    "credit cards": "Credit Card", "credit card": "Credit Card", "cards": "Credit Card",
    "mortgages": "Mortgage", "mortgage": "Mortgage", "home loans": "Mortgage", "home finance": "Mortgage",
    "personal finance": "Personal Finance", "personal loans": "Personal Finance", "personal loan": "Personal Finance",
    "auto finance": "Auto Finance", "auto loans": "Auto Finance", "car loans": "Auto Finance", "auto": "Auto Finance",
    "bnpl": "Buy Now Pay Later", "buy now pay later": "Buy Now Pay Later",
}
ID_RE = {"exposures": r"\b(CF\d{6}|CFN\d{5}|RA\d{7}|RA\d{6}[BM]\d)\b", "owners": r"\b(CB\d{5}|RC\d{6})\b"}


@dataclass
class Mention:
    kind: str
    start: int
    end: int
    text: str
    groups: tuple = ()


@dataclass
class Magnitude:
    value: float
    unit: str          # pct | pp | bps | notch | sd | points | bare
    signed: bool
    start: int
    end: int
    claimed: bool = False


@dataclass
class Reading:
    intent: str
    steps: list[Step] = field(default_factory=list)
    method: str = ""
    factor: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)
    period: str = ""
    name: str = ""
    horizon: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"horizon": self.horizon, "intent": self.intent, "steps": [s.to_dict() for s in self.steps], "method": self.method,
                "factor": self.factor, "assumptions": self.assumptions, "unread": self.unread, "period": self.period,
                "name": self.name}


# ------------------------------------------------------------------ scanning

def _norm(text: str) -> str:
    t = text.replace("−", "-").replace("–", "-").replace("’", "'").replace("×", "x")
    return re.sub(r"\s+", " ", t).strip()


def _magnitudes(text: str) -> list[Magnitude]:
    out: list[Magnitude] = []
    pat = re.compile(r"(?<![\w.])([-+]?\s?\d+(?:\.\d+)?)\s*(%|per\s?cent\w*|pp\b|ppt\b|percentage points?|bps\b|bp\b|basis points?|"
                     r"notch(?:es)?|bands?|sd\b|standard deviations?|sigma|points?\b|pts\b)?", re.I)
    # R10 C1: multipliers ("PD x1.5", "1.2 times", "by a factor of 1.3", "multiply LGD by 1.1") are read first
    mult_pat = re.compile(r"(?<![\w.])[x]\s?(\d+(?:\.\d+)?)\b|(?<![\w.])(\d+(?:\.\d+)?)\s?(?:x|times)\b|"
                          r"\bfactor\s+of\s+(\d+(?:\.\d+)?)\b|\bmultipl\w*\s+(?:[A-Za-z]+\s+){0,4}?by\s+(\d+(?:\.\d+)?)\b", re.I)
    mult_spans: list[tuple[int, int]] = []
    for m in mult_pat.finditer(text):
        val = next(g for g in m.groups() if g is not None)
        gi = next(i for i, g in enumerate(m.groups(), 1) if g is not None)
        out.append(Magnitude(value=float(val), unit="mult", signed=False, start=m.start(gi), end=m.end()))
        mult_spans.append((m.start(), m.end()))
    for m in pat.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        if any(m.start() < e and m.end() > s0 for s0, e in mult_spans) and not unit:
            continue
        if any(s0 <= m.start() < e for s0, e in mult_spans):
            continue
        # skip periods and ids: 2026Q2, 2025-06, CF000123, years (only a letter touching the number
        # marks an id; "by 1.2" is a size: the R9 reader skipped every bare number after a word)
        after = text[m.end():m.end() + 2]
        before = text[max(0, m.start() - 1):m.start()]
        if re.match(r"[Qq]\d|-\d", after) or (re.match(r"[A-Za-z]", before) and not unit):
            continue
        v = float(raw.replace(" ", ""))
        if not unit and 1990 <= abs(v) <= 2100 and float(v).is_integer():
            continue
        if not unit and re.match(r"\s*(stage)", text[m.end():m.end() + 7], re.I):
            continue
        if re.search(r"stage\s?$", text[max(0, m.start() - 7):m.start()], re.I):
            continue
        if unit.startswith("%") or unit.startswith("per"):
            u = "pct"
        elif unit.startswith("pp") or unit.startswith("ppt") or unit.startswith("percentage"):
            u = "pp"
        elif unit.startswith("bp") or unit.startswith("basis"):
            u = "bps"
        elif unit.startswith("notch") or unit.startswith("band"):
            u = "notch"
        elif unit in ("sd", "sigma") or unit.startswith("standard"):
            u = "sd"
        elif unit.startswith("point") or unit == "pts":
            u = "points"
        else:
            u = "bare"
        out.append(Magnitude(value=v, unit=u, signed=raw.strip()[0] in "+-", start=m.start(), end=m.end()))
    # word numbers before "notch": "two notches", "a notch"
    for m in re.finditer(r"\b(one|two|three|four|five|six|a|an|single)\s+(notch(?:es)?|bands?)\b", text, re.I):
        out.append(Magnitude(value=float(WORD_NUMBERS[m.group(1).lower()]), unit="notch", signed=False,
                             start=m.start(), end=m.end()))
    for m in re.finditer(r"\b(halve[sd]?|halving|doubl\w+)\b", text, re.I):
        word = m.group(1).lower()
        out.append(Magnitude(value=-50.0 if word.startswith("halv") else 100.0, unit="pct", signed=True,
                             start=m.start(), end=m.end()))
    out.sort(key=lambda g: g.start)
    return out


def _mentions(text: str) -> list[Mention]:
    found: list[Mention] = []
    taken: list[tuple[int, int]] = []
    for kind, pat in MEASURES:
        for m in re.finditer(pat, text, re.I):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            word = m.group(0).lower()
            if kind == "mev:repo" and word == "rates" and re.search(r"(default|recovery)\s+$", text[:m.start()].lower()):
                continue
            if kind == "rating" and word.startswith("band") and not re.search(r"score|behaviou?r|retail|\d\s*bands?|one|two|three|a band", text, re.I):
                continue
            found.append(Mention(kind=kind, start=m.start(), end=m.end(), text=m.group(0), groups=m.groups()))
            taken.append((m.start(), m.end()))
    found.sort(key=lambda x: x.start)
    return found


def _rating_from_notches(text: str, found: list[Mention], mags: list[Magnitude]) -> list[Mention]:
    """'2 notches' with no rating verb is still a rating shock; two rating words in one phrase are one shock."""
    out: list[Mention] = []
    for m in found:
        if m.kind == "rating" and out and out[-1].kind == "rating" and m.start - out[-1].end < 30:
            continue
        out.append(m)
    if not any(m.kind == "rating" for m in out):
        for g in mags:
            if g.unit == "notch":
                out.append(Mention(kind="rating", start=g.start, end=g.end, text=text[g.start:g.end]))
                break
    out.sort(key=lambda x: x.start)
    return out


def _direction(text: str, lo: int, hi: int, anchor: int, prefer: tuple[int, int] | None = None) -> int:
    """+1 / -1 from a direction word: first the one nearest `anchor` inside `prefer` (the stretch
    between the measure and its size, where the governing verb sits), else the nearest in [lo, hi)."""
    for a, b in ([prefer] if prefer else []) + [(lo, max(lo, anchor + 1)), (lo, hi)]:
        seg = text[a:b]
        best, dist = 0, 10 ** 9
        for pat, sign in ((UP, 1), (DOWN, -1)):
            for m in re.finditer(pat, seg, re.I):
                d = abs(a + m.start() - anchor)
                if d < dist:
                    best, dist = sign, d
        if best:
            return best
    return 0


# ------------------------------------------------------------------ scopes

@dataclass
class ScopeMention:
    start: int
    scope: Scope
    text: str


def _scopes(text: str, ctx: dict[str, Any], avoid: list[tuple[int, int]] | None = None) -> list[ScopeMention]:
    out: list[ScopeMention] = []
    low = text.lower()
    domain = ctx.get("domain", "corporate")
    names = {s.lower(): s for s in ctx.get("segments", [])}
    subs = {s.lower(): s for s in ctx.get("subsegments", [])}
    taken: list[tuple[int, int]] = list(avoid or [])

    def add(start, end, scope, said):
        if any(start < e and end > s for s, e in taken):
            return
        taken.append((start, end))
        out.append(ScopeMention(start, scope, said))

    for name, real in sorted(subs.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(r"\b" + re.escape(name) + r"\b", low):
            add(m.start(), m.end(), Scope(subsegments=[real]), real)
    if domain == "corporate":
        vocab = {**{k: v for k, v in SECTOR_SYNONYMS.items()}, **names}
        for name, real in sorted(vocab.items(), key=lambda kv: -len(kv[0])):
            if real not in ctx.get("segments", [real]):
                continue
            for m in re.finditer(r"\b" + re.escape(name) + r"\b", low):
                if name == "it" and not re.search(r"\bIT\b", text[m.start():m.end()]):
                    continue
                if name in ("property",) and re.match(r"\s+(prices?|values?)", low[m.end():m.end() + 8]):
                    continue
                add(m.start(), m.end(), Scope(segments=[real]), real)
    else:
        vocab = {**PRODUCT_SYNONYMS, **names}
        for name, real in sorted(vocab.items(), key=lambda kv: -len(kv[0])):
            for m in re.finditer(r"\b" + re.escape(name) + r"\b", low):
                if name == "auto" and not re.match(r"\s*(finance|loans?)", low[m.end():m.end() + 9]):
                    continue
                add(m.start(), m.end(), Scope(segments=[real]), real)
    for key, pat in ID_RE.items():
        for m in re.finditer(pat, text, re.I):
            sc = Scope(**{key: [m.group(1).upper()]})
            add(m.start(), m.end(), sc, m.group(1).upper())
    for m in re.finditer(r"\b(?:for|in|on|of|only|across)\s+(?:the\s+)?stage\s?([123])\b(?!\s*(?:to|into))", text, re.I):
        add(m.start(), m.end(), Scope(stages=[int(m.group(1))]), f"Stage {m.group(1)}")
    return out


def _merge_scope(a: Scope, b: Scope) -> Scope:
    return Scope(segments=a.segments + [x for x in b.segments if x not in a.segments],
                 subsegments=a.subsegments + [x for x in b.subsegments if x not in a.subsegments],
                 products=a.products + b.products, owners=a.owners + b.owners, exposures=a.exposures + b.exposures,
                 stages=a.stages + b.stages, grades=a.grades + b.grades)


# ------------------------------------------------------------------ shocks

def _share(word: str) -> float:
    w = word.lower().strip()
    if w.endswith("%"):
        return float(w[:-1])
    return {"half": 50.0, "a quarter": 25.0, "a third": 100 / 3, "all": 100.0}.get(w, 0.0)


def _shock_for(kind: str, mag: Magnitude | None, sign: int, said: str, ctx: dict, notes: list[str],
               unread: list[str], mention: Mention) -> Shocks | None:
    sh = Shocks()
    domain = ctx.get("domain", "corporate")
    if kind == "stage":
        frm, to = int(mention.groups[1]), int(mention.groups[2])
        sh.stage = [{"from": frm, "to": to, "share": _share(mention.groups[0])}]
        return sh
    if kind == "sector" and mag is None:
        sev = next((v for k, v in SEVERITY.items() if k in said.lower()), 1.0)
        sh.sector = sev
        notes.append(f"'{said}' read as a sector stress of {sev:g} standard deviation{'s' if sev != 1 else ''} of the "
                     "cycle index (mild 0.5, moderate 1, severe 2, extreme 3).")
        return sh
    if mag is None:
        if kind == "rating":
            word = said.lower()
            sh.rating = -1 if word.startswith("upgrad") else 1
            notes.append(f"'{said}' with no size read as one {'band' if domain == 'retail' else 'notch'}.")
            return sh
        if kind == "mev:gdp_real" and "recession" in said.lower():
            sh.mev = {"gdp_real": -2.0}
            notes.append("'recession' with no size read as real GDP growth -2pp on every year of the path.")
            return sh
        label = mention.text
        unread.append(f"{label}: no size given (say, for example, '{label} +20%' or '{label} +2pp').")
        return None
    if kind in ("pd", "lgd", "ccf", "ead", "collateral") and (
            mag.unit == "mult" or (mag.unit == "bare" and not mag.signed and 1.0 < mag.value <= 3.0
                                   and not float(mag.value).is_integer())):
        # R10 C1 (img07): "increase PD by 1.2" / "PD x1.5" is a multiplier, "reduce LGD by 1.2" divides by it.
        f = abs(mag.value)
        if f <= 0:
            unread.append(f"{mention.text}: a multiplier must be above zero.")
            return None
        down = sign < 0 and f >= 1.0
        rel = round(((1.0 / f) if down else f) * 100.0 - 100.0, 2)
        name = {"pd": "PD", "lgd": "LGD", "ccf": "CCF", "ead": "EAD", "collateral": "Collateral value"}[kind]
        notes.append(f"{name} {'divided' if down else 'multiplied'} by {f:g}, read as a relative change of {rel:+g}%"
                     + (" (a bare decimal between 1 and 3 is read as a multiplier; say 'pp' or '%' for points or percent)."
                        if mag.unit == "bare" else "."))
        if kind == "pd":
            sh.pd = {"mode": "relative", "value": rel}
        elif kind == "lgd":
            sh.lgd = {"mode": "relative", "value": rel}
        elif kind == "ccf":
            sh.ccf = {"mode": "relative", "value": rel}
        elif kind == "ead":
            sh.ead = rel
        else:
            sh.collateral = rel
        return sh
    if mag.unit == "mult":
        unread.append(f"{mention.text}: a multiplier ('x{mag.value:g}') applies to PD, LGD, CCF, EAD or collateral only.")
        return None
    v = abs(mag.value) if not mag.signed else mag.value
    if not mag.signed:
        v = v * (sign if sign else 1)
        if not sign and kind != "rating":
            notes.append(f"{mention.text} {abs(mag.value):g}: no direction word, read as an increase.")
    if kind == "pd":
        if mag.unit in ("pct", "bare"):
            sh.pd = {"mode": "relative", "value": v}
            if mag.unit == "bare":
                notes.append(f"PD {v:+g} read as a relative change of {v:+g}%.")
        elif mag.unit == "pp":
            sh.pd = {"mode": "pp", "value": v}
        elif mag.unit == "bps":
            sh.pd = {"mode": "bps", "value": v}
        else:
            unread.append(f"PD: '{mag.value:g} {mag.unit}' is not a PD unit (use %, pp or bps).")
            return None
        return sh
    if kind == "lgd":
        recovery = re.search(r"recover", said, re.I)
        if recovery:
            v = -v
            notes.append("A recovery-rate move is read as the opposite LGD move.")
        if mag.unit in ("pp", "bare"):
            sh.lgd = {"mode": "pp", "value": v}
            if mag.unit == "bare":
                notes.append(f"LGD {v:+g} read as percentage points.")
        elif mag.unit == "pct":
            sh.lgd = {"mode": "relative", "value": v}
        else:
            unread.append(f"LGD: '{mag.value:g} {mag.unit}' is not an LGD unit (use pp or %).")
            return None
        return sh
    if kind == "collateral":
        if mag.unit in ("pct", "bare"):
            sh.collateral = v
            if mag.unit == "bare":
                notes.append(f"Collateral {v:+g} read as a {v:+g}% change in collateral value.")
            return sh
        unread.append("Collateral: give the move in % of its value (for example collateral -20%).")
        return None
    if kind == "haircut":
        if mag.unit in ("pp", "bare", "pct"):
            sh.haircut = v
            if mag.unit != "pp":
                notes.append(f"Haircut {v:+g}{'%' if mag.unit == 'pct' else ''} read as {v:+g} percentage points on the haircut.")
            return sh
        unread.append("Haircut: give the move in percentage points (for example haircuts +10pp).")
        return None
    if kind == "ead":
        if mag.unit in ("pct", "bare"):
            sh.ead = v
            return sh
        unread.append("EAD: give the move in % (for example EAD +5%).")
        return None
    if kind == "ccf":
        if mag.unit in ("pp", "bare"):
            sh.ccf = {"mode": "pp", "value": v}
        elif mag.unit == "pct":
            sh.ccf = {"mode": "relative", "value": v}
            notes.append(f"{mention.text} {v:+g}% read as a relative change in the CCF (say 'pp' for points).")
        else:
            return None
        return sh
    if kind == "rating":
        if mag.unit == "points" and domain == "retail":
            bands = round(abs(mag.value) / 80.0) or 1
            fall = (mag.signed and mag.value < 0) or (not mag.signed and sign <= 0)
            sh.rating = bands if fall else -bands
            notes.append(f"{abs(mag.value):g} score points read as {bands} score band{'s' if bands > 1 else ''} (80 points each).")
            return sh
        n = int(round(abs(mag.value)))
        down_word = re.search(r"downgrad|\bcut\b|\blower\b|fall|drop|deteriorat", said, re.I)
        up = re.search(r"upgrad", said, re.I) or (sign < 0 and not down_word)
        sh.rating = -n if up else n
        return sh
    if kind == "sector":
        sh.sector = abs(mag.value) if mag.unit in ("sd", "bare") else 1.0
        return sh
    if kind.startswith("mev:"):
        key = kind.split(":")[1]
        s = mev.BY_KEY[key]
        unit = s.shock_unit
        if unit == "pct":
            if mag.unit in ("pct", "bare"):
                sh.mev = {key: v}
            else:
                unread.append(f"{s.name}: give the move in % (for example -40%).")
                return None
        elif unit == "bps":
            if mag.unit == "bps":
                sh.mev = {key: v}
            elif mag.unit in ("pp", "pct", "bare"):
                sh.mev = {key: v * 100.0}
                if mag.unit != "pp":
                    notes.append(f"{s.name} {v:+g}{'%' if mag.unit == 'pct' else ''} read as {v:+g} percentage points "
                                 f"({v * 100:+g}bps).")
            if re.fullmatch(r"(interest\s+)?rates", mention.text.strip(), re.I):
                sh.mev["saibor_3m"] = sh.mev[key]
                notes.append("'rates' moves both the SAMA repo rate and 3-month SAIBOR.")
        else:
            if mag.unit in ("pp", "pct", "bare"):
                sh.mev = {key: v}
                if mag.unit == "pct":
                    notes.append(f"{s.name} {v:+g}% read as {v:+g} percentage points.")
            else:
                unread.append(f"{s.name}: give the move in percentage points.")
                return None
        return sh
    return None


def _combine(a: Shocks, b: Shocks) -> Shocks:
    out = Shocks(pd=a.pd or b.pd, lgd=a.lgd or b.lgd, ccf=a.ccf or b.ccf, ead=a.ead + b.ead, rating=a.rating + b.rating,
                 sector=a.sector + b.sector, mev={**a.mev}, stage=a.stage + b.stage,
                 collateral=a.collateral + b.collateral, haircut=a.haircut + b.haircut,
                 horizon=max(a.horizon, b.horizon))
    for k, v in b.mev.items():
        out.mev[k] = out.mev.get(k, 0.0) + v
    return out


HORIZON_RE = re.compile(
    r"\b(?:over|for|across|within|in|during|lasting)\s+(?:the\s+)?(?:next\s+|first\s+|coming\s+)?"
    r"(\d+|one|two|three|four|five|six)\s*(?:-\s*)?(years?|yrs?|months?|quarters?)\b"
    r"|\b(\d+|one|two|three|four|five)[-\s](year|month|quarter)\s+(?:horizon|period|stress|scenario|shock)\b"
    r"|\bhorizon\s+(?:of\s+)?(\d+|one|two|three|four|five)\s*(years?|months?|quarters?)\b", re.I)


def _horizon(t: str, notes: list[str]) -> tuple[int, str]:
    """R10 C1: 'over 3 years', 'for 18 months', 'a 2-year horizon' -> (years, text with the span blanked)."""
    m = HORIZON_RE.search(t)
    if not m:
        return 0, t
    g = [x for x in m.groups() if x is not None]
    num = g[0].lower()
    n = float(WORD_NUMBERS.get(num, 0) or num)
    unit = g[1].lower()
    years = n if unit.startswith("y") else n / 12.0 if unit.startswith("m") else n / 4.0
    h = int(min(5, max(1, -(-years // 1))))
    if years > 5:
        notes.append(f"Horizon '{m.group(0).strip()}' is longer than the 5-year macro paths: read as 5 years.")
    elif not float(years).is_integer():
        notes.append(f"Horizon '{m.group(0).strip()}' rounded up to {h} year{'s' if h != 1 else ''} (the paths are annual).")
    notes.append(f"Horizon {h} year{'s' if h != 1 else ''}: macro shocks apply for the first {h} year{'s' if h != 1 else ''} "
                 "of the 5-year paths, then revert to base; PD, LGD, rating, sector and collateral shocks are lifetime.")
    return h, t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]


def _is_new_scenario_text(t: str) -> bool:
    return bool(re.search(r"\b(what if|what happens if|suppose|assume|assuming|imagine|scenario|stress|shock)\b", t, re.I))


# ------------------------------------------------------------------ the reader

def read(text: str, ctx: dict[str, Any]) -> Reading:
    """ctx: domain, segments, subsegments, has_scenario (bool), labels."""
    t = _norm(text)
    low = t.lower()
    has = bool(ctx.get("has_scenario"))
    method = next((k for k, p in METHOD_WORDS.items() if re.search(p, t, re.I)), "")
    period = ""
    pm = re.search(r"\b(20\d\dQ[1-4]|20\d\d-(?:0[1-9]|1[0-2]))\b", t)
    if pm:
        period = pm.group(1)

    def plain(intent: str, **kw) -> Reading:
        return Reading(intent=intent, method=method, period=period, **kw)

    if re.search(INTENT_WORDS["undo"], low):
        return plain("undo")
    if re.search(INTENT_WORDS["help"], low):
        return plain("help")
    save = re.search(r"\bsave\b(?:\s+(?:this(?:\s+scenario)?|it|the\s+scenario))?(?:\s+as\s+['\"]?(.+?)['\"]?\s*$)?", t, re.I)
    if save and re.search(INTENT_WORDS["save"], low):
        return plain("save", name=(save.group(1) or "").strip())
    if re.search(INTENT_WORDS["report"], low) and not _mentions(t):
        return plain("report")

    notes: list[str] = []
    horizon, t_full = _horizon(t, notes)
    if horizon:
        t = t_full
    mags = _magnitudes(t)
    mentions = _rating_from_notches(t, _mentions(t), mags)
    # "recession with real GDP -3pp": the sized GDP move is the recession, not a second -2pp on top
    if any(m.kind == "mev:gdp_real" and "recession" not in m.text.lower() for m in mentions):
        mentions = [m for m in mentions if not (m.kind == "mev:gdp_real" and m.text.lower() == "recession")]
    unread: list[str] = []

    if has and not mentions:
        if re.search(INTENT_WORDS["likelihood"], low):
            return plain("likelihood")
        if re.search(INTENT_WORDS["compare"], low) or re.search(INTENT_WORDS["other_model"], low):
            return plain("other_model" if re.search(INTENT_WORDS["other_model"], low) and not re.search(r"\bcompare|side", low) else "compare")
        if re.search(INTENT_WORDS["intensify"], low) or re.search(r"\b(more|less)\s+(severe|intense|extreme)\b|\bincrease (the |its )?(intensity|severity)\b", low):
            return plain("intensify", factor=_factor(low, notes), assumptions=notes)
        if method and len(low.split()) <= 8:
            return plain("choose_method")
        if re.search(INTENT_WORDS["explain"], low):
            return plain("explain")
    if not has and method and not mentions and len(low.split()) <= 8:
        return plain("choose_method")
    if not mentions:
        if re.search(INTENT_WORDS["likelihood"], low):
            return plain("likelihood")
        if re.search(INTENT_WORDS["brainstorm"], low) or re.search(r"\?\s*$", t) or re.search(INTENT_WORDS["help"], low):
            return plain("brainstorm")
        if mags:
            g0 = mags[0]
            return plain("unclear", unread=[f"'{t[g0.start:g0.end]}': I could not tell which measure this size applies to "
                                             "(PD, LGD, CCF, EAD, rating, sector stress or a macro variable)."])
        return plain("brainstorm")

    # --- bind magnitudes to measures
    bounds = [m.start for m in mentions] + [len(t)]
    clause_of: list[tuple[int, int]] = []
    for i, m in enumerate(mentions):
        lo = mentions[i - 1].end if i else 0
        clause_of.append((lo, bounds[i + 1]))
    assigned: dict[int, Magnitude | None] = {}
    for i, m in enumerate(mentions):
        if m.kind == "stage":
            assigned[i] = None
            continue
        lo, hi = clause_of[i]
        after = [g for g in mags if not g.claimed and m.end <= g.start < hi]
        before = [g for g in mags if not g.claimed and lo <= g.end <= m.start]
        pick = None
        if m.kind == "rating":
            notchy = [g for g in after + before if g.unit in ("notch", "points")]
            pick = min(notchy, key=lambda g: abs(g.start - m.end)) if notchy else (after[0] if after and after[0].unit in ("bare",) else None)
        elif m.kind == "sector":
            sds = [g for g in after + before if g.unit == "sd"]
            pick = sds[0] if sds else None
        else:
            cands = [g for g in after if g.unit != "notch"] or [g for g in reversed(before) if g.unit != "notch"]
            pick = cands[0] if cands else None
        if pick:
            pick.claimed = True
        assigned[i] = pick
    # --- directions and shocks
    parts: list[tuple[int, Shocks, str]] = []
    for i, m in enumerate(mentions):
        lo, hi = clause_of[i]
        g = assigned[i]
        anchor = g.start if g else m.start
        if g is None:
            prefer = (m.start, m.end)
        elif g.start >= m.end:
            prefer = (m.start, g.end)
        else:
            prefer = (g.start, m.end + 12)
        sign = _direction(t, lo, hi, anchor, prefer)
        sh = _shock_for(m.kind, g, sign, m.text, ctx, notes, unread, m)
        if sh is not None:
            parts.append((i, sh, m.text))
    for g in mags:
        if not g.claimed and g.unit not in ("notch",) and not any(m.kind == "stage" and m.start <= g.start <= m.end for m in mentions):
            if not any(m.kind in ("sector", "rating") for m in mentions) or g.unit not in ("sd", "bare"):
                unread.append(f"'{t[g.start:g.end].strip()}': not attached to any measure.")
    # --- scopes
    scopes = _scopes(t, ctx, avoid=[(m.start, m.end) for m in mentions if m.kind.startswith("mev:")])
    first = mentions[0].start
    last_end = max(max(m.end, assigned[i].end if assigned.get(i) else 0) for i, m in enumerate(mentions))
    scope_of: dict[int, Scope] = {}
    global_scope = Scope()
    bound = []
    for sm in scopes:
        if sm.start < first:
            global_scope = _merge_scope(global_scope, sm.scope)
            continue
        owner = max((i for i, m in enumerate(mentions) if m.start <= sm.start), default=None)
        if owner is None:
            global_scope = _merge_scope(global_scope, sm.scope)
        else:
            bound.append((owner, sm))
    if len(bound) == 1 and len(mentions) > 1 and bound[0][1].start >= last_end and \
            not re.search(r"\b(and|but)\b[^.;]*\b(for|in)\b", t[mentions[bound[0][0]].end:bound[0][1].start], re.I):
        global_scope = _merge_scope(global_scope, bound[0][1].scope)
        bound = []
    # R10 C1: one sector/product/name in the whole sentence scopes every lever ("severe stress in real estate with
    # PD up 30% and LGD up 5pp" = all of it on Real Estate), unless the user says the rest is book-wide.
    if len(bound) == 1 and len(scopes) == 1 and len(mentions) > 1 and bound[0][0] == 0 and \
            not re.search(r"\b(whole|entire|rest of the|all other|across the|everywhere|book[-\s]wide)\b", t, re.I):
        global_scope = _merge_scope(global_scope, bound[0][1].scope)
        bound = []
    if re.search(r"\bonly\b", t, re.I) and len(bound) == 1:
        global_scope = _merge_scope(global_scope, bound[0][1].scope)
        bound = []
    for owner, sm in bound:
        scope_of[owner] = _merge_scope(scope_of.get(owner, Scope()), sm.scope)
    # sector stress named "stress in the X sector" carries its own scope
    # --- group into steps by scope
    groups: dict[str, tuple[Scope, Shocks, list[str]]] = {}
    for i, sh, said in parts:
        sc = _merge_scope(global_scope, scope_of.get(i, Scope()))
        key = repr(sc.to_dict())
        if key in groups:
            s0, sh0, words = groups[key]
            groups[key] = (s0, _combine(sh0, sh), words + [said])
        else:
            groups[key] = (sc, sh, [said])
    labels = ctx.get("labels", {})
    steps = []
    for sc, sh, _ in groups.values():
        if horizon:
            sh.horizon = horizon
        rest = "; ".join(describe_shocks(sh, labels)) + f" on {sc.describe(labels)}"
        steps.append(Step(instruction=text.strip(), restatement=rest, shocks=sh, scope=sc))
    for sc in [s for s in scopes]:
        if not ctx.get("segments") or not (sc.scope.segments or sc.scope.subsegments):
            continue
    if horizon and not any(st.shocks.mev for st in steps):
        notes[:] = [n for n in notes if not n.startswith("Horizon ")] + [
            f"Horizon {horizon} year{'s' if horizon != 1 else ''} noted: this scenario has no macro shock, and PD, LGD, "
            "rating, sector and collateral shocks act on lifetime ECL, so the horizon does not change the result."]
    if not steps:
        return plain("unclear", unread=unread or ["I could not read a shock in that."], assumptions=notes)
    if has:
        if re.search(INTENT_WORDS["new"], low):
            intent = "new"
        elif re.search(INTENT_WORDS["stack"], low):
            intent = "stack"
        elif _is_new_scenario_text(t):
            intent = "new"
        else:
            intent = "new"
    else:
        intent = "scenario"
    return Reading(intent=intent, steps=steps, method=method, assumptions=notes, unread=unread, period=period,
                   horizon=horizon)


def _factor(low: str, notes: list[str]) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s?x\b|\bx\s?(\d+(?:\.\d+)?)\b", low)
    if m:
        return float(m.group(1) or m.group(2))
    m = re.search(r"\bby\s+(\d+(?:\.\d+)?)\s?%", low)
    if m:
        f = 1 + float(m.group(1)) / 100.0
        return 1 / f if re.search(r"\b(less|reduce|lower|milder)\b", low) else f
    if re.search(r"\b(double|twice)\b", low):
        return 2.0
    if re.search(r"\b(triple|three times)\b", low):
        return 3.0
    if re.search(r"\b(halve|half as)\b", low):
        return 0.5
    if re.search(r"\b(less severe|milder|soften|lighter)\b", low):
        notes.append("'less severe' with no size read as two thirds of the current intensity (x0.67).")
        return 2 / 3
    notes.append("'more severe' with no size read as 1.5 times the current intensity.")
    return 1.5
