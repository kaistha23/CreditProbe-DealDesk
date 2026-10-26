"""The proposal voice as checkable rules (PROPOSAL_ANATOMY.md §3; PLAN_R12 §1.3 point 3).

    problems = check_paper(paper)    # [] when every prose sentence of every section keeps the voice

Rules on each prose sentence (split at '.' or '?'; a ';' joins clauses of one sentence) (paragraphs and bullets; tables, signature blocks and key-value header lines are exempt):
  V1 fact     a figure and a date (or period), or an explicit attribution / evidence status ("as per business", "not provided" ...)
  V2 PY       a movement ("rose", "fell", "increased" ...) carries the prior-year comparative in brackets: "(PY ...)"
  V3 share    a component of a total (receivables, related parties, backlog, top-n concentration, current assets) with an
              amount also gives its share in %
  V4 plain    no marketing adjective ("robust", "excellent", "reputed" ...); "strong"/"healthy"/"comfortable" only with a figure
  V5 voice    the business voice (Action requested) never uses the credit division's markers ("We note", "Upon checking");
              the credit voice never asks for approval in the first person ("we request", "kindly approve")
Section rules:
  S1 adjusted the financial synopsis restates at least one adjusted figure, or says the adjustment data was not provided
  S2 gaps     a section whose data contract is not met says so ("not provided", "not available", "not clarified")
"""
from __future__ import annotations

import re
from typing import Any

MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE = re.compile(rf"\b\d{{1,2}} {MONTH} (?:19|20)\d\d\b|\b{MONTH} (?:19|20)\d\d\b|\b(?:FY|H[12] ?|Q[1-4] ?|YTD ?)?(?:19|20)\d\d(?:Q[1-4])?\b"
                  rf"|\b\d{{4}}-\d\d(?:-\d\d)?\b", re.I)
NUM = re.compile(r"\d")
ATTRIB = re.compile(r"as per (?:business|the business|the client|the customer|management|the bureau|the CBRBR|the audited|the auditor|the "
                    r"valuation|the trade licence|the facility letters?|the RM|policy|the committee|the deposit|the account|CreditProbe|the agent|"
                    r"the facility agreement|the escrow agreement|the scorecard decision)"
                    r"|business conveys|business confirms|business states|business advises|business attributes|reportedly|not provided|not shared|"
                    r"not clarified|not explained|not available|not obtained|not complied|copies not provided|attributed to|"
                    r"not applicable|no record|none recorded|nil\b|source:|"
                    r"\b(?:as )?per (?:the )?(?:Borrower 360|bureau|CBRBR|monitoring plan|stress|engine|optimiser|Deal Desk|Deposits|"
                    r"Early Warning|section \d+|dd_\w+|b360_\w+|rel_\w+|bureau_\w+|other_bank_\w+|dep_\w+)", re.I)
CHANGE = re.compile(r"\b(rose|fell|increased|decreased|declined|grew|improved|deteriorated|dropped|up from|down from|contracted|expanded)\b", re.I)
PY = re.compile(r"\(PY ", re.I)
SHARE_WORDS = re.compile(r"\b(receivables?|related[- ]part(?:y|ies)|backlog|top[- ]\d|concentration|current assets)\b", re.I)
AMOUNT = re.compile(r"\b(?:AED|SAR|USD|QAR|KWD|OMR|BHD)\s?-?[\d,]+(?:\.\d+)?\s?(?:m|bn|k)?\b")
MARKETING = re.compile(r"\b(robust|excellent|impressive|reputed|renowned|world[- ]class|well[- ]established|leading|"
                       r"best[- ]in[- ]class|prestigious|stellar)\b", re.I)
SOFT = re.compile(r"\b(strong|healthy|comfortable|solid|sound|significant)\b", re.I)
CREDIT_MARKERS = re.compile(r"\b(we note|upon checking|credit division (?:notes|observes)|which clearly indicates)\b", re.I)
BUSINESS_MARKERS = re.compile(r"\b(we request|we propose|kindly approve|we seek approval|we recommend approval as requested)\b", re.I)
GAP = re.compile(r"not provided|not available|not clarified|not shared|not obtained|no record", re.I)

ABBREV = re.compile(r"(?:\b(?:No|Co|Ltd|LLC|Inc|vs|approx|e\.g|i\.e|Ref|Nos|St|Dr|Mr|Ms|incl|p\.a|cf|Art|Cl)\.)$")


def sentences(text: str) -> list[str]:
    """Sentences of a prose line, split at '.' or '?' followed by a space and a capital, digit or bracket (an initial such as
    'Rashid K. Al Sahel' or an abbreviation such as 'No.' does not end a sentence)."""
    out, start = [], 0
    t = text.strip()
    for m in re.finditer(r"[.?](?=\s+[A-Z(\d\"'])", t):
        piece = t[start:m.end()]
        if ABBREV.search(piece.rstrip("?")) or re.search(r"\b[A-Z]\.$", piece):
            continue
        out.append(piece.strip())
        start = m.end()
    tail = t[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def sentence_problems(s: str, voice: str) -> list[str]:
    out = []
    plain = re.sub(r"\*\*", "", s)
    has_attr = bool(ATTRIB.search(plain))
    undated = DATE.sub(" ", plain)
    has_num = bool(NUM.search(undated))
    dates = DATE.findall(plain)
    has_date = bool(dates)
    if len(set(dates)) >= 2:  # 'moved from 31 Mar 2026 to 31 Dec 2026': the figures are the dates
        has_num = True
    if not ((has_num and has_date) or has_attr):
        why = "no figure" if not has_num else "no date or period"
        out.append(f"V1 fact ({why} and no attribution): {plain[:110]}")
    if CHANGE.search(plain) and not PY.search(plain) and not has_attr:
        out.append(f"V2 PY (movement without the prior-year comparative in brackets): {plain[:110]}")
    if SHARE_WORDS.search(plain) and AMOUNT.search(plain) and "%" not in plain and not re.search(r"\d\.\d+x\b", plain) and not has_attr \
            and not re.search(r"assignment of receivables", plain, re.I):  # a security item, not a component of a total
        out.append(f"V3 share (component of a total without its %): {plain[:110]}")
    m = MARKETING.search(plain)
    if m:
        out.append(f"V4 plain (marketing adjective {m.group(0)!r}): {plain[:110]}")
    m = SOFT.search(plain)
    if m and not has_num:
        out.append(f"V4 plain ({m.group(0)!r} without a figure): {plain[:110]}")
    if voice == "business" and CREDIT_MARKERS.search(plain):
        out.append(f"V5 voice (credit marker in the business voice): {plain[:110]}")
    if voice == "credit" and BUSINESS_MARKERS.search(plain):
        out.append(f"V5 voice (business ask in the credit voice): {plain[:110]}")
    return out


def prose(section: dict[str, Any]) -> list[str]:
    """The prose lines of a section (paragraphs and bullet items)."""
    out: list[str] = []
    for b in section.get("blocks", []):
        if b["t"] == "p" and not b.get("exempt"):
            out.append(b["text"])
        elif b["t"] in ("bullets", "numbered"):
            out += [x for x in b["items"]]
    return out


def check_section(section: dict[str, Any]) -> list[str]:
    if section.get("voice") == "form":
        return []
    out: list[str] = []
    for line in prose(section):
        for s in sentences(line):
            out += [f"{section['key']}: {p}" for p in sentence_problems(s, section.get("voice", "credit"))]
    text = " ".join(prose(section))
    if section["key"] == "synopsis" and not re.search(r"\badjusted\b", text, re.I) and not GAP.search(text):
        out.append("synopsis: S1 adjusted (no adjusted figure and no 'not provided')")
    if section.get("gaps") and not GAP.search(text + " " + " ".join(" ".join(map(str, r)) for b in section.get("blocks", [])
                                                                   if b["t"] == "table" for r in b["rows"])):
        out.append(f"{section['key']}: S2 gaps (contract not met: {', '.join(section['gaps'][:3])}; the section does not say so)")
    return out


def check_paper(paper: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for s in paper["sections"]:
        out += check_section(s)
    return out


def score(paper: dict[str, Any]) -> dict[str, Any]:
    """Sentence-level density: how many prose sentences keep the voice."""
    n = bad = 0
    for s in paper["sections"]:
        if s.get("voice") == "form":
            continue
        for line in prose(s):
            for x in sentences(line):
                n += 1
                bad += bool(sentence_problems(x, s.get("voice", "credit")))
    return {"sentences": n, "failing": bad, "share_ok": round(1 - bad / n, 4) if n else 1.0}
