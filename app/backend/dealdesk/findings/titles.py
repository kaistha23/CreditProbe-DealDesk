"""R14 E (K19 #3): finding titles that state the RESULT, never the rule's pass-statement.

"Pricing clears the hurdle" on a finding that pricing does not clear it becomes "Pricing below hurdle: 14.5% vs 15.0%";
"Account conduct: no returned cheques" on a finding of 4 returned cheques becomes "RM claim contradicted: 4 returned
cheques in 12 months; memo says none".
"""
from __future__ import annotations

import re
from typing import Any


def _pct(x: Any, dp: int = 1) -> str:
    return f"{float(x) * 100:.{dp}f}%" if isinstance(x, (int, float)) else "n/a"


def _num(x: Any) -> str:
    if not isinstance(x, (int, float)):
        return "n/a"
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}"


def _first_clause(text: str, n: int = 96) -> str:
    t = re.split(r"(?<=[.;])\s", str(text or "").strip(), maxsplit=1)[0].rstrip(".;")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _memo_says_none(check: dict[str, Any]) -> bool:
    """A contradicted verdict means the memo (the RM) claimed otherwise."""
    return check.get("verdict") == "contradicted" or bool(check.get("claim_ids"))


def for_check(c: dict[str, Any], m: dict[str, Any] | None = None) -> str:
    """A failed R11 rule check (review_rules) -> a result title."""
    rid, v, thr = c.get("rule_id"), c.get("value"), c.get("threshold")
    m = m or {}
    if rid == "CONS-07":
        r, h = m.get("lifetime_raroc"), m.get("hurdle")
        if isinstance(r, (int, float)) and isinstance(h, (int, float)):
            return f"Pricing below hurdle: {_pct(r)} vs {_pct(h)}"
        found = re.search(r"RAROC ([\d.]+%) against a ([\d.]+%) hurdle", c.get("finding") or "")
        return f"Pricing below hurdle: {found.group(1)} vs {found.group(2)}" if found else "Pricing below hurdle"
    if rid == "DATA-05":
        n = _num(v)
        return (f"RM claim contradicted: {n} returned cheques in 12 months; memo says none" if _memo_says_none(c)
                else f"Returned cheques: {n} in 12 months")
    if rid == "DATA-06":
        return bureau_title(c)
    if rid == "DATA-03":
        return f"Existing exposure differs from the book: {_num(v)} vs {_num(thr)}"
    if rid == "DATA-04":
        return f"Rating differs from the rating system: {v} vs {thr}"
    if rid == "DATA-01":
        return "Memo figures differ from the proposal record"
    if rid == "CONS-05":
        return f"DSCR after the deal below the covenant: {_num(v)}x vs {_num(thr)}x"
    if rid == "CONS-06":
        return f"Leverage after the deal above the covenant: {_num(v)}x vs {_num(thr)}x"
    if rid == "CONS-08":
        return "Collateral valuation out of date"
    if rid == "GOV-05":
        return "CRO review not signed"
    if rid == "CP-05":
        return "Connected party not performing in the book"
    # prepared-case rules: "<title>: not met" with the finding's own first clause
    return f"{c.get('title')}: not met — {_first_clause(c.get('finding') or '', 70)}" if c.get("finding") else f"Not met: {c.get('title')}"


def bureau_title(c: dict[str, Any]) -> str:
    """R15 b (L12): the bureau finding names the flag on record; a missing flag is a data gap, never "not clear: None"."""
    flag = c.get("flag")
    if flag is None:
        found = re.search(r"Bureau flag on record: ([^.]+)\.", str(c.get("finding") or ""))
        flag = found.group(1).strip() if found else None
    if flag is None or str(flag).strip().lower() in ("", "none", "null", "nan", "n/a"):
        return "SIMAH report not on file (a data gap, not a bureau hit)"
    return f"Bureau not clear: SIMAH flag {str(flag).strip().lower()}"


PASS_TITLES = {"Pricing clears the hurdle", "Account conduct: no returned cheques"}


def for_row(r: dict[str, Any], m: dict[str, Any] | None = None) -> str:
    """A dd_review_finding row -> a result title."""
    title = str(r.get("title") or "")
    cat = str(r.get("category") or "")
    code = cat.split(":", 1)[1] if ":" in cat else ""
    if code == "CONS-07" or title == "Pricing clears the hurdle":
        return for_check({"rule_id": "CONS-07", "finding": r.get("finding_text")}, m)
    if title == "Account conduct: no returned cheques":
        return f"Returned cheques: {_num(r.get('evidence_value'))} in 12 months"
    if str(r.get("raised_by") or "") == "Q" and ": " in title:
        signal = title.split(": ", 1)[1]
        ev, thr, unit = r.get("evidence_value"), r.get("claim_value"), r.get("evidence_unit") or ""
        if isinstance(ev, (int, float)) and isinstance(thr, (int, float)):
            if unit == "share":
                return f"{signal}: {_pct(ev)} vs {_pct(thr, 0)} threshold"
            if unit == "x":
                return f"{signal}: {ev:.2f}x vs {thr:.2f}x"
            if unit == "days":
                return f"{signal}: {_num(ev)} days vs {_num(thr)}"
            if unit == "mn":
                return f"{signal}: SAR {ev:,.1f}m"
        clause = _first_clause(r.get("finding_text") or "", 80)
        words = [w for w in re.findall(r"[a-z]+", signal.lower()) if len(w) > 3]
        if clause and words and all(w in clause.lower() for w in words[:2]):
            t = re.sub(r"^The ", "", clause)
            return t[:1].upper() + t[1:]
        return f"{signal}: {clause}" if clause else signal
    if title in PASS_TITLES:
        return _first_clause(r.get("finding_text") or title)
    return title
