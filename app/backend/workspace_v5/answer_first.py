"""R10 Session Q (Q2, Anne's item 17): a saved analysis reads as the answer to its question.

"This analysis doesn't look like an analysis of the user's question." Every analysis is shown as:
  title     = the question;
  headline  = the answer, with its key figure in bold, first;
  then one chart and one table that answer it;
  then the method and the Trace (source, period, steps).

`headline_for` writes the answer line from the computed result (book cut, What-If run) or, for a Cockpit answer the
Workspace cannot recompute, from the Cockpit's own narrative (its first sentence, key figure in bold). `view` applies
this to any stored analysis at read time, so analyses saved before R10 read the same way without a migration.
No figure is invented: every number in a headline is a figure, a row or the narrative of the saved result.
"""
from __future__ import annotations

import re
from typing import Any

from backend.workspace_v5.book import mn, pct

_FIG = re.compile(r"(SAR\s?[\d,.]+\s?(?:billion|million|bn|mn|m)?\b|[+-]?[\d,]+(?:\.\d+)?\s?%|[\d,]{2,}(?:\.\d+)?)")


def _fmt(v: Any, unit: str) -> str:
    if v is None:
        return "n/a"
    if unit == "sar_mn":
        return mn(float(v))
    if unit == "pct":
        return pct(float(v), 2)
    if unit == "int":
        return f"{int(round(float(v))):,}"
    return f"{float(v):,.1f}" if isinstance(v, (int, float)) else str(v)


def _signed(v: float, unit: str) -> str:
    return ("+" if v > 0 else "−" if v < 0 else "") + _fmt(abs(v), unit)


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    m = re.match(r"^(.+?[.!?])(\s|$)", text, re.S)
    return (m.group(1) if m else text).strip()


def _bold_first_figure(sentence: str) -> str:
    if "**" in sentence:
        return sentence
    return _FIG.sub(lambda m: f"**{m.group(1).strip()}**", sentence, count=1)


def _col(table: dict[str, Any], key: str) -> dict[str, Any]:
    return next((c for c in table.get("columns") or [] if c.get("key") == key), {"key": key, "label": key, "unit": "num"})


def headline_for(question: str, answer: dict[str, Any], period: str | None = None) -> str:
    """The answer to the question, key figure bold, in one sentence."""
    if answer.get("headline"):
        return str(answer["headline"])
    period = answer.get("period") or period or ""
    figs = {f["key"]: f for f in answer.get("figures") or [] if isinstance(f, dict) and "key" in f}
    table = answer.get("table") or {}
    chart = answer.get("chart") or {}
    if answer.get("engine") == "whatif" and {"reported_ecl", "scenario_ecl", "change"} <= figs.keys():
        ch = figs["change"]["value"]
        verb = "rise" if ch > 0 else "fall" if ch < 0 else "stay"
        cp = figs.get("change_pct", {}).get("value")
        rows = table.get("rows") or []
        lead = f"; {rows[0]['segment']} moves most ({_signed(float(rows[0]['change']), 'sar_mn')})" if rows and "segment" in rows[0] else ""
        return (f"ECL would {verb} by **{_fmt(abs(ch), 'sar_mn')}**"
                + (f" (**{_signed(float(cp), 'pct')}**)" if cp is not None else "")
                + f", from {_fmt(figs['reported_ecl']['value'], 'sar_mn')} to {_fmt(figs['scenario_ecl']['value'], 'sar_mn')}"
                + f" at {period}{lead}.")
    rows = table.get("rows") or []
    dim, y = chart.get("x") or table.get("key"), chart.get("y")
    if answer.get("engine") == "book" and rows and dim and y and y in figs:
        ycol = _col(table, y)
        top = max(rows, key=lambda r: float(r.get(y) or 0))
        share = top.get("share_pct")
        total = figs[y]
        return (f"{total['label']} is **{_fmt(total['value'], total['unit'])}** at {period} across {len(rows):,} "
                f"{_col(table, dim)['label'].lower()}s; the largest is **{top[dim]}** at "
                f"**{_fmt(top[y], ycol.get('unit', 'num'))}**" + (f" ({pct(float(share))} of the total)." if share is not None else "."))
    return _bold_first_figure(_first_sentence(str(answer.get("narrative") or "")))


def method_for(a: dict[str, Any]) -> str:
    """One line on how the answer was computed (the Trace carries the steps)."""
    ans = a.get("answer") or {}
    spec = a.get("spec") or {}
    if ans.get("engine") == "whatif":
        return (f"Scenario run by the What-If engine ({ans.get('source') or 'What-If'}); scenario ECL is the "
                f"probability-weighted ECL over the scenario paths, by segment.")
    if spec.get("engine") == "book" or ans.get("engine") == "book":
        by = str(spec.get("by") or (ans.get("chart") or {}).get("x") or "segment").replace("_", " ")
        return (f"Recomputed from the {a.get('book') or spec.get('book') or ''} book ({ans.get('source') or a.get('source') or ''}) "
                f"at {ans.get('period') or a.get('period')}: facility-level figures summed by {by}.").replace("  ", " ")
    return ans.get("recompute_note") or "As the Cockpit published it, from the queries its Trace records."


def view(a: dict[str, Any]) -> dict[str, Any]:
    """A stored analysis as an answer: title = question, headline first, method. Original title kept as `label`."""
    if not isinstance(a, dict):
        return a
    out = dict(a)
    q = str(a.get("question") or "").strip()
    if q:
        out["label"] = a.get("title")
        out["title"] = q
    ans = dict(a.get("answer") or {})
    if ans:
        ans["headline"] = headline_for(q, ans, a.get("period"))
        out["answer"] = ans
        out["headline"] = ans["headline"]
        out["method"] = method_for(out)
    elif a.get("description"):
        out["headline"] = _bold_first_figure(_first_sentence(str(a["description"])))
    return out
