"""The interpretation at the top of a lens (R13 L, J8; N3: a deterministic writer, the model only polishes).

Three to five lines, every one with its numbers and period:
  1. where the scope stands: EAD, ECL and coverage at the as-of period;
  2-4. the two or three movements that matter, ranked by materiality (size of the move against its own level,
       weighted by how much the metric matters to a credit committee), each with the value now, the change on the
       prior period and, where the window has it, the change on a year before; the ECL line names the segment that
       drove the move and its share;
  5. when nothing moved materially, one line that says so with the largest move.
Every figure is a KPI the lens already shows (traced) or the driver query, whose SQL is returned as `trace`.
"""
from __future__ import annotations

from typing import Any

from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import DIMS
from backend.lenses_v5.engine import ENGINE, PPY

#: How much a move of each metric matters (a committee reads ECL, staging and cost of risk first).
WEIGHT = {"ecl": 1.3, "cost_of_risk": 1.2, "stage3_share": 1.2, "stage2_share": 1.1, "coverage": 1.0, "high_critical": 1.0,
          "high_critical_ead": 1.0, "dpd30_share": 1.0, "dpd90_share": 1.0, "npl_ratio": 1.0, "warned": 0.8, "dscr": 0.9,
          "leverage": 0.8, "pd": 0.9, "write_offs": 0.9, "ead": 0.6, "obligors": 0.3, "exposures": 0.3}
#: The smallest level a relative move is measured against (a 0.1% share doubling is not a story).
FLOOR = {"pct": 1.0, "bps": 50.0, "ratio": 0.25, "count": 10.0, "score": 10.0, "days": 5.0}
#: Below this materiality a move is not named.
MATERIAL = 0.03
#: Plain names where the strip's short label needs its noun.
LABEL = {"high_critical": "High or critical obligors", "warned": "Warned obligors", "obligors": "Obligors"}
#: Metrics that repeat another one on the strip (NPL ratio is Stage 3 share by definition).
SAME_AS = {"npl_ratio": "stage3_share"}


def _delta(v: float, unit: str) -> str:
    s = "+" if v > 0 else "−" if v < 0 else ""
    a = abs(v)
    if unit == "pct":
        return f"{s}{a:,.2f} pp"
    if unit == "sar_mn":
        return s + fmt.amount(a)
    if unit == "bps":
        return f"{s}{round(a):,} bps"
    return s + fmt.fmt_value(a, unit)


def _rel(v: float, p: float) -> str:
    return f" ({'+' if v - p > 0 else '−'}{abs(v - p) / abs(p) * 100:,.1f}%)" if p else ""


def _score(k: dict[str, Any]) -> float:
    v, p, unit = k.get("value"), k.get("prior"), k.get("unit", "")
    if v is None or p is None:
        return 0.0
    if unit == "sar_mn":
        base = max(abs(p), 0.01)
    else:
        base = max(abs(p), FLOOR.get(unit, 1.0))
    return abs(v - p) / base * WEIGHT.get(k["key"], 0.7)


def _year_ago(k: dict[str, Any], book: str) -> tuple[str, float] | None:
    sp = [s for s in k.get("spark") or [] if s.get("value") is not None]
    n = PPY[book]
    if len(sp) > n:
        s = sp[-1 - n]
        return s["period"], s["value"]
    return None


def _driver(ctx: Any, prior: str) -> tuple[dict[str, Any] | None, str]:
    """The segment that moved ECL most between prior and now, and its share of the book's ECL move."""
    dims = {f["dim"] for f in ctx.filters}
    if ctx.book == "corporate":
        seg = "sub_sector" if "sector" in dims else "sector"
    else:
        seg = "sub_product" if "product" in dims else "product"
    rows, sql = ENGINE.series(ctx.book, ctx.filters, [prior, ctx.period], ["ecl"], dim=seg)
    by: dict[Any, dict[str, float]] = {}
    for r in rows:
        by.setdefault(r.get("k"), {})[r["period"]] = r.get("ecl") or 0.0
    moves = {k: v.get(ctx.period, 0.0) - v.get(prior, 0.0) for k, v in by.items()}
    total = sum(moves.values())
    if len(moves) < 2 or not total:
        return None, sql
    k, d = max(moves.items(), key=lambda kv: kv[1] * (1 if total > 0 else -1))
    share = d / total
    if share < 0.25:
        return None, sql
    return {"dim": DIMS[seg].label.lower(), "name": str(k), "change": d, "share": share, "total": total}, sql


def _line(k: dict[str, Any], period: str, prior: str, book: str) -> str:
    v, p, unit = k["value"], k["prior"], k["unit"]
    verb = "rose" if v > p else "fell"
    s = f"{LABEL.get(k['key'], k['label'])} {verb} {_delta(abs(v - p), unit).lstrip('+')} to {fmt.fmt_value(v, unit)} in {period}"
    if unit in ("sar_mn", "count"):
        s += _rel(v, p)
    s += f", from {fmt.fmt_value(p, unit)} in {prior}"
    ya = _year_ago(k, book)
    if ya and ya[1] is not None and ya[1] != v:
        s += f"; {_delta(v - ya[1], unit)} on {ya[0]}"
    return s


def interpret(spec: dict[str, Any], ctx: Any, kpis: list[dict[str, Any]]) -> dict[str, Any]:
    by = {k["key"]: k for k in kpis}
    prior = ENGINE.prior(ctx.book, ctx.period) or ""
    who = spec.get("scope_label") or ""
    if not who or who.endswith(" book"):
        who = "Corporate book" if ctx.book == "corporate" else "Retail book"
    lines: list[dict[str, Any]] = []
    head = None
    if "ead" in by and "ecl" in by and by["ead"].get("value") is not None:
        head = f"{who}, {ctx.period}: EAD {by['ead']['display']}, ECL {by['ecl']['display']}"
        if "coverage" in by and by["coverage"].get("value") is not None:
            head += f", coverage {by['coverage']['display']}"
        head += "."
    cands = [k for k in kpis if k["key"] not in SAME_AS or SAME_AS[k["key"]] not in by]
    ranked = sorted((k for k in cands if _score(k) > 0), key=_score, reverse=True)
    material = [k for k in ranked if _score(k) >= MATERIAL][:3]
    trace_sql = ""
    if prior:
        for k in material:
            text = _line(k, ctx.period, prior, ctx.book)
            if k["key"] == "ecl":
                try:
                    drv, trace_sql = _driver(ctx, prior)
                except Exception:  # noqa: BLE001 - the driver clause never blocks the reading
                    drv = None
                if drv:
                    text += (f"; {drv['name']} accounts for {drv['share'] * 100:,.0f}% of the move "
                             f"({_delta(drv['change'], 'sar_mn')} by {drv['dim']})")
            lines.append({"metric": k["key"], "tone": k.get("tone", "neutral"), "text": text + "."})
        if not material and ranked:
            k = ranked[0]
            lines.append({"metric": k["key"], "tone": "neutral",
                          "text": f"Nothing moved materially on {prior}: the largest move is {k['label']} at "
                                  f"{_delta(k['value'] - k['prior'], k['unit'])} ({fmt.fmt_value(k['value'], k['unit'])} in {ctx.period})."})
    # a fifth line: what the Early Warning book says next, when it is not already one of the movements
    named = {x["metric"] for x in lines}
    hc = by.get("high_critical")
    if len(lines) < 4 and hc and hc.get("value") is not None and "high_critical" not in named and hc.get("change"):
        lines.append({"metric": "high_critical", "tone": hc.get("tone", "neutral"),
                      "text": f"Early Warning: {hc['display']} obligors high or critical in {ctx.period} ({hc['change_display']} on {prior})."})
    md = ((f"**{head}**\n\n" if head else "") + "\n".join(f"- {x['text']}" for x in lines)).strip()
    return {"headline": head or "", "lines": lines, "period": ctx.period, "prior": prior, "markdown": md, "source": "deterministic",
            "trace": {"sql": trace_sql, "note": "Figures are the KPI strip's values; the ECL driver line runs the query shown."}}
