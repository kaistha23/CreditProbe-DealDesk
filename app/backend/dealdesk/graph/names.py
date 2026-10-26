"""Round G: names → one entity. Normalisation, the person/company test, aggregates, and a cheap local embedding.

The embedding is a hashed character-trigram vector (256 floats, unit length) computed here, offline, in microseconds: no
model, no network. It is used only to resolve a name read from a document to an entity the graph already knows when the
normalised spellings differ slightly (OCR, "Co." vs "Company", a dropped "Al"). Two names resolve to the same entity when
their normalised forms are equal, or when the cosine of their vectors is at least MATCH (and the first word agrees, so
"Al Kharj Contracting" never becomes "Al Jouf Contracting").
"""
from __future__ import annotations

import hashlib
import math
import re
import struct

DIM = 256
MATCH = 0.92

# words that carry no identity: legal forms and fillers
_LEGAL = re.compile(r"\b(co|company|companies|llc|ltd|limited|est|establishment|inc|corp|corporation|the|plc|fze|fzco|gmbh|jsc|cjsc|sjsc|"
                    r"wll|l\.l\.c)\b")
_COMPANY_WORDS = re.compile(r"(?i)\b(co\.?|company|llc|ltd|limited|est\.?|establishment|holding|holdings|group|trading|contracting|bank|"
                            r"industries|industrial|factory|services|systems|development|developments|projects|properties|hospitals?|"
                            r"medical|logistics|consultants|subcontracting|gmbh|fze|corporation|corp|inc|plc|ministry|cluster|association|"
                            r"authority|partners|international|enterprises|supplies|concrete|rebar|polymers?|petrochemical|marketing|"
                            r"bottling|foods|dairy|park|centre|center|estates?|management|works|rental|beverage|consumables|instruments)\b")
_AGGREGATE = re.compile(r"(?i)^\s*(other|others|various|sundry|misc)\b|\(\d+\)|\b(other|local|export|gcc) (customers|suppliers|clients)\b|"
                        r"\bcustomers \(|\bsuppliers \(|\bsubcontractors \(\d|\bmaterials and tools\b|^total\b")


def norm(name: str) -> str:
    """'Sharqiya Logistics Development Co. (SLDC)' → 'sharqiya logistics development'; 'Al-Naseem' → 'al naseem'."""
    s = str(name or "").lower()
    s = re.sub(r"\((?:related|sldc|[a-z]{2,6}|ksa|uae|subject|sister|parent)\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = _LEGAL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_person(name: str) -> bool:
    n = str(name or "").strip()
    return bool(n) and not _COMPANY_WORDS.search(n) and not re.search(r"\d", n)


def is_aggregate(name: str) -> bool:
    """'Other suppliers', 'Local customers (96)', 'GCC export customers (14)': not one counterparty."""
    return bool(_AGGREGATE.search(str(name or "")))


def related_marker(name: str) -> bool:
    return bool(re.search(r"(?i)\(related\)|related party", str(name or "")))


def clean_display(name: str) -> str:
    """The name as shown: the document's spelling without the '(related)' marker."""
    return re.sub(r"\s*\((?i:related)\)\s*", " ", str(name or "")).strip()


def vector(name: str) -> list[float]:
    """Hashed character-trigram embedding of the normalised name (unit length)."""
    s = f"  {norm(name)}  "
    v = [0.0] * DIM
    for i in range(len(s) - 2):
        h = int.from_bytes(hashlib.blake2b(s[i:i + 3].encode(), digest_size=4).digest(), "little")
        v[h % DIM] += 1.0 if (h >> 31) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def pack(v: list[float]) -> bytes:
    return struct.pack(f"{DIM}f", *v)


def unpack(b: bytes | None) -> list[float] | None:
    if not b or len(b) != DIM * 4:
        return None
    return list(struct.unpack(f"{DIM}f", b))


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def first_word(name: str) -> str:
    w = norm(name).split(" ")
    if w and w[0] in ("al", "el", "dar", "bin", "abu") and len(w) > 1:
        return w[0] + " " + w[1]
    return w[0] if w else ""


def same(a: str, b: str, va: list[float] | None = None, vb: list[float] | None = None) -> tuple[bool, float]:
    """(same entity?, score): equal normalised names, or close vectors with the same first word."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False, 0.0
    if na == nb:
        return True, 1.0
    if first_word(a) != first_word(b):
        return False, 0.0
    c = cosine(va or vector(a), vb or vector(b))
    return c >= MATCH, round(c, 4)
