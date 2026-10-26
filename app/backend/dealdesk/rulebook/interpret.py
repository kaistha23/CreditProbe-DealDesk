"""Reading an uploaded regulation or internal credit policy: its summary and the thresholds it sets for Deal Desk's checks.

    r = read(text, title)     # {"summary", "issuer", "effective", "changes": [{param, segment, value, display, clause, quote}],
                              #  "unread": [sentences with a requirement Deal Desk has no check for], "method": "rules" | "model"}

A change is kept only if its quote is a sentence of the document and its value is written in that quote: the model reads and
quotes, it never computes. Units are normalised for the check (6 months -> 180 days, 70% -> 0.70), and the display keeps the
document's own words. Without a model key (or when the model's reading fails the check) the deterministic reader below reads it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.dealdesk.rulebook import checks as CK

SEGMENTS = {"construction": "Construction", "contracting": "Construction", "contractor": "Construction", "real estate": "Real Estate",
            "real-estate": "Real Estate", "property development": "Real Estate", "trading": "Wholesale Trade", "hospitality": "Hospitality",
            "manufacturing": "Manufacturing", "healthcare": "Healthcare"}
G = r"[^\d\n.;]{0,70}?"  # the words between the measure and its value: no digit, no sentence end
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("min_dscr", re.compile(rf"(?:\bDSCR\b|debt[- ]service[- ]cover(?:age)?(?: ratio)?){G}(\d+(?:\.\d+)?)\s*(?:x|times)\b", re.I)),
    ("max_leverage", re.compile(rf"(?:debt\s*(?:/|to)\s*EBITDA|\bleverage(?: ratio)?){G}(\d+(?:\.\d+)?)\s*(?:x|times)\b", re.I)),
    ("max_ltv", re.compile(rf"(?:\bLTV\b|loan[- ]to[- ]value|financing[- ]to[- ]value){G}(\d+(?:\.\d+)?)\s*(?:%|per ?cent)", re.I)),
    ("min_collateral_cover", re.compile(rf"(?:collateral|security)\s+cover(?:age)?{G}(\d+(?:\.\d+)?)\s*(?:%|per ?cent)", re.I)),
    ("max_tenor_years", re.compile(rf"(?:\btenor|\bmaturity){G}(\d+)\s*years?\b", re.I)),
    ("max_valuation_age_days", re.compile(r"valuation[^\d\n.;]{0,140}?(?:older than|within|not exceed(?:ing)?|more than)[^\d\n.;]{0,30}?(\d+)\s*(months?|days?)\b", re.I)),
    ("min_raroc", re.compile(rf"(?:\bRAROC\b|\bhurdle(?: rate)?){G}(\d+(?:\.\d+)?)\s*(?:%|per ?cent)", re.I)),
    ("min_rating", re.compile(r"(?:rated|rating|grade)[^\n.;]{0,50}?(?:below|at least|minimum(?: of)?|not lower than|or better than|or above)\s*"
                              r"(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?)(?![\w+-])", re.I)),
]
CLAUSE = re.compile(r"^\s*(?:(Article|Clause|Section|Paragraph|Para\.?)\s+)?(\d{1,2}(?:\.\d{1,2}){0,2})[.)]?\s+(?=\S)", re.I)
REQUIRE = re.compile(r"\b(shall|must|may not|is required|are required|not exceed|at least|minimum|maximum|no older|prohibited)\b", re.I)
ISSUER = re.compile(r"\b(Saudi Central Bank|SAMA|Central Bank of the UAE|CBUAE|Board of Directors|Credit Committee|Chief Risk Officer)\b")
EFFECTIVE = re.compile(r"effective\s+(?:from|on|as of)?\s*(\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})", re.I)


def lc(s: str) -> str:
    """'Minimum DSCR ...' -> 'minimum DSCR ...' (the acronyms kept)."""
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def sentences(text: str) -> list[tuple[str, str]]:
    """(clause, sentence): the clause is the numbered paragraph the sentence sits in ("Article 3.2", "4.1") or "para n"."""
    out: list[tuple[str, str]] = []
    clause, n = "", 0
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        n += 1
        m = CLAUSE.match(line)
        if m:
            clause = f"{(m.group(1) or '').title()} {m.group(2)}".strip().replace("Para.", "Paragraph")
            line = line[m.end():]
        for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])", line):
            s = s.strip()
            if len(s) > 12:
                out.append((clause or f"para {n}", s))
    return out


def _segment(s: str) -> str:
    low = s.lower()
    for w, seg in SEGMENTS.items():
        if re.search(rf"\b{re.escape(w)}", low):
            return seg
    return "all"


def _value(param: str, m: re.Match[str]) -> tuple[Any, str]:
    unit = CK.PARAMS[param]["unit"]
    raw = m.group(0)
    if param == "max_valuation_age_days":
        n = int(m.group(1))
        days = n * 30 if m.group(2).lower().startswith("month") else n
        return days, f"{n} {m.group(2)}" + (f" ({days} days)" if m.group(2).lower().startswith("month") else "")
    if param == "min_rating":
        return m.group(1).upper(), m.group(1).upper()
    v = float(m.group(1))
    if unit == "%":
        return round(v / 100, 6), f"{m.group(1)}%"
    if unit == "x":
        return v, f"{m.group(1)}x"
    if unit == "years":
        return v, f"{m.group(1)} years"
    return v, raw


def rules_read(text: str, title: str = "") -> dict[str, Any]:
    sents = sentences(text)
    changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    unread = []
    for clause, s in sents:
        hit = False
        for param, rx in PATTERNS:
            for m in rx.finditer(s):
                value, disp = _value(param, m)
                seg = _segment(s)
                if (param, seg) in seen:
                    continue
                seen.add((param, seg))
                changes.append({"param": param, "check": CK.PARAMS[param]["check"], "label": CK.PARAMS[param]["label"], "segment": seg,
                                "value": value, "display": disp, "clause": clause, "quote": s})
                hit = True
        if not hit and REQUIRE.search(s) and len(unread) < 8:
            unread.append({"clause": clause, "quote": s})
    return {"changes": changes, "unread": unread, "method": "rules", **_meta(text, title, sents, changes)}


def _meta(text: str, title: str, sents: list[tuple[str, str]], changes: list[dict[str, Any]]) -> dict[str, Any]:
    iss = ISSUER.search(text or "")
    eff = EFFECTIVE.search(text or "")
    first = next((s for _, s in sents if len(s) > 60 and not CLAUSE.match(s) and not s.isupper()), "")
    segs = sorted({c["segment"] for c in changes if c["segment"] != "all"})
    lines = [f"{title or 'This document'}{' (' + iss.group(1) + ')' if iss else ''}: {first[:260]}".strip()]
    if changes:
        lines.append(f"It sets {len(changes)} threshold{'s' if len(changes) != 1 else ''} that Deal Desk checks: "
                     + "; ".join(f"{lc(c['label'])} {c['display']}{' for ' + c['segment'].lower() if c['segment'] != 'all' else ''} ({c['clause']})"
                                 for c in changes[:6]) + ".")
    else:
        lines.append("It sets no threshold that a Deal Desk check reads; it is kept as a reference document.")
    if segs:
        lines.append(f"Deal types named: {', '.join(segs)}.")
    if eff:
        lines.append(f"Effective {eff.group(1)}.")
    return {"summary": " ".join(lines), "issuer": iss.group(1) if iss else "", "effective": eff.group(1) if eff else ""}


# ------------------------------------------------------------------ model path

TOOL = {"name": "read_policy", "description": "Read a bank regulation or credit policy for the thresholds a credit desk checks.",
        "input_schema": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "3-4 plain sentences: who issued it, what it requires, for which deals, from when."},
            "changes": {"type": "array", "items": {"type": "object", "properties": {
                "param": {"type": "string", "enum": list(CK.PARAMS)},
                "segment": {"type": "string", "description": "'all', or the sector it applies to (e.g. Construction, Real Estate)"},
                "value": {"type": "string", "description": "the value exactly as written, e.g. '1.40x', '70%', '6 months', 'BB-'"},
                "clause": {"type": "string"}, "quote": {"type": "string", "description": "the sentence, copied exactly"}},
                "required": ["param", "segment", "value", "quote"]}}},
            "required": ["summary", "changes"]}}
SYSTEM = ("You read a regulation or an internal credit policy for a corporate credit desk. List every threshold it sets that "
          "matches one of the parameters, with the sentence copied exactly and the value exactly as written. Do not compute or "
          "convert anything. Summarise in plain words.")


def _model(text: str, title: str) -> dict[str, Any] | None:
    try:
        from backend.convo import provider as prov
        from backend.convo import telemetry
    except Exception:  # noqa: BLE001
        return None
    p = prov.default()
    if p is None:
        return None
    try:
        with telemetry.use(module="dealdesk", request_path="/api/v1/dealdesk/rulebook/assess"):
            reply = p.step("dealdesk_policy_read", SYSTEM, [{"role": "user", "content": json.dumps({"title": title, "text": text[:60000]})}], [TOOL])
    except Exception:  # noqa: BLE001
        return None
    use = next((u for u in reply.tool_uses() if u.get("name") == "read_policy"), None)
    if not use:
        return None
    x = use.get("input") or {}
    flat = _norm(text).lower()
    clauses = {_norm(s).lower(): c for c, s in sentences(text)}
    out = []
    for c in x.get("changes") or []:
        param, quote, val = c.get("param"), _norm(str(c.get("quote") or "")), str(c.get("value") or "")
        if param not in CK.PARAMS or not quote or quote.lower() not in flat:
            return None  # a quote that is not in the document: the reader's reading stands
        rx = dict(PATTERNS)[param]
        m = rx.search(quote)
        if not m or not re.search(re.escape(re.sub(r"[^\d.A-Z+-]", "", val.upper())[:4] or "?"), quote.upper()):
            return None
        value, disp = _value(param, m)
        seg = str(c.get("segment") or "all")
        seg = "all" if seg.lower() in ("all", "", "*", "all deals") else SEGMENTS.get(seg.lower(), seg.title())
        out.append({"param": param, "check": CK.PARAMS[param]["check"], "label": CK.PARAMS[param]["label"], "segment": seg, "value": value,
                    "display": disp, "clause": str(c.get("clause") or clauses.get(quote.lower(), "")), "quote": quote})
    base = rules_read(text, title)
    return {**base, "changes": out, "summary": str(x.get("summary") or base["summary"])[:1500], "method": "model"}


def read(text: str, title: str = "", use_model: bool = True) -> dict[str, Any]:
    got = _model(text, title) if use_model else None
    return got or rules_read(text, title)
