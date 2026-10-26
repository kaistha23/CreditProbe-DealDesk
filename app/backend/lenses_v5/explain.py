"""The (i) on every lens tile explains it fully (PLAN_R6 L3, the D4 standard), in plain words for a non-specialist:

  shows     what the chart shows
  formula   how each series is calculated, with the formula
  read      how to read it, with an example from the tile's current figures
  look_for  what to look for and what to do with it

Built from the tile's own output, so the example always carries the figures on screen (formatted per G5).
"""
from __future__ import annotations

from typing import Any

from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import DIMS, DISTRIBUTIONS, METRICS

_COND = {"stage = 2": "only Stage 2 facilities", "stage = 3": "only Stage 3 (non-performing) facilities",
         "dpd_days >= 30": "only facilities 30 or more days past due", "dpd_days >= 90": "only facilities 90 or more days past due"}


def metric_formula(key: str, custom: dict[str, Any] | None = None) -> str:
    """One metric's formula in plain words."""
    custom = custom or {}
    if key in custom:
        c = custom[key]
        return f"{c.get('label', key)} = {c.get('num', 'numerator')} ÷ {c.get('den', 'denominator')} × {c.get('scale', 100):g} (a ratio you built)."
    m = METRICS.get(key)
    if m is None:
        return key
    what = m.description or m.label
    where = ""
    if m.cond:
        where = " — " + _COND.get(m.cond, "counting only " + ("warned obligors (Early Warning band moderate, high or critical)" if "moderate" in m.cond
                                                              else "high or critical Early Warning names" if "critical" in m.cond else m.cond.replace("_", " ")))
    if m.kind == "sum":
        return f"{m.label} = the sum over every facility in the lens scope ({what}){where}, in SAR millions." if m.unit == "sar_mn" \
            else f"{m.label} = a count over every facility or account in the lens scope ({what}){where}."
    if m.kind == "ratio":
        num, den = METRICS.get(m.num), METRICS.get(m.den)
        return (f"{m.label} = {num.label if num else m.num} ÷ {den.label if den else m.den}"
                f"{' × 100' if m.scale == 100 else ''}{' (' + m.description + ')' if m.description else ''}.")
    if m.kind == "wavg":
        return f"{m.label} = Σ(value × EAD) ÷ Σ EAD — {what}: large exposures weigh more than small ones."
    if m.kind == "distinct":
        return f"{m.label} = the number of distinct obligors{where} ({what})." if m.description else f"{m.label} = the number of distinct obligors{where}."
    if m.kind == "cor":
        return (f"{m.label} = over the last 12 months, (ECL build + new write-offs) ÷ average EAD, in basis points (1 bp = 0.01%); "
                "flows are taken exposure by exposure, so moves in and out of the scope are not charged.")
    return f"{m.label}: {what}."


def _val(v: Any, unit: str) -> str:
    return fmt.fmt_value(v, unit)


def _first(out: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    t = out.get("table") or {}
    return t.get("columns") or [], t.get("rows") or []


def explain(tile: dict[str, Any], out: dict[str, Any], ctx: Any) -> dict[str, str]:
    t = tile.get("type", "")
    custom = getattr(ctx, "custom", {}) or {}
    cols, rows = _first(out)
    scope = (ctx.spec.get("scope_label") if getattr(ctx, "spec", None) else "") or "the lens scope"
    period = getattr(ctx, "period", "")
    key = tile.get("metric") or (tile.get("metrics") or ["ead"])[0]
    m = METRICS.get(key)
    label = custom[key]["label"] if key in custom else (m.label if m else key)
    unit = custom[key].get("unit", "pct") if key in custom else (m.unit if m else "")
    f = metric_formula(key, custom)
    ex = ""
    if t == "trend":
        keys = tile.get("metrics") or [key]
        last = rows[-1] if rows else {}
        first = rows[0] if rows else {}
        if last and first and keys[0] in last:
            ex = (f"For example, {label} was {_val(first.get(keys[0]), unit)} in {first.get('period')} and is {_val(last.get(keys[0]), unit)} "
                  f"in {last.get('period')}.")
        return {"shows": f"How {' and '.join((METRICS[k].label if k in METRICS else k) for k in keys)} moved over the last "
                         f"{len(rows) or 8} periods for {scope}.",
                "formula": " ".join(metric_formula(k, custom) for k in keys) + " Each point is one period-end.",
                "read": "Time runs left to right; each point is the value at that period-end. " + ex,
                "look_for": "A steady climb in a loss or warning measure, or a sudden step in one period. A step usually means a few large "
                            "names moved: open the top names tile or ask the assistant which names drove it."}
    if t == "breakdown":
        dim = DIMS.get(tile.get("dim", ""))
        dl = dim.label.lower() if dim else "segment"
        if rows:
            top = max(rows, key=lambda r: r.get(key) or 0)
            ex = f"For example, {top.get('k')} has {label} of {_val(top.get(key), unit)} at {period}, the largest bar."
        order = "best grade (AAA) to worst (D)" if dim and dim.order == "rating" else "natural order" if dim and dim.order in ("natural", "band") \
            else "largest first"
        return {"shows": f"{label} split by {dl} for {scope} at {period}.",
                "formula": f + f" Each bar applies it to the facilities of one {dl}.",
                "read": f"One bar per {dl}, in {order}; the bar length is the value. " + ex,
                "look_for": f"The few {dl}s that carry most of the {label}. If one bar dominates, that is a concentration to discuss; "
                            f"click (⋯) to switch the metric or show it by another dimension."}
    if t == "mix_trend":
        dim = DIMS.get(tile.get("dim", "stage"))
        return {"shows": f"How {label} is split by {dim.label.lower() if dim else 'segment'} in each period: the mix, not the total.",
                "formula": f + " Each coloured block is that segment's share of the period's total.",
                "read": "Each column is one period; the coloured blocks stack to the period's total. A growing block is a segment taking more "
                        "of the book." + (f" The latest period is {rows[-1].get('period')}." if rows else ""),
                "look_for": "Stage 2 or high/critical blocks growing period after period: an early sign of rising loss before ECL shows it."}
    if t == "top_names":
        if rows:
            r0 = rows[0]
            ex = f"For example, the largest is {r0.get('name') or r0.get('owner_id')} with EAD {fmt.amount(r0.get('ead'))} and coverage {fmt.pct(r0.get('coverage'))}."
        return {"shows": f"The largest names in {scope} by {label} at {period}, with stage, Early Warning band and rating.",
                "formula": f + " Coverage = ECL ÷ EAD × 100. Worst stage = the highest stage among the name's facilities.",
                "read": "One row per obligor, largest first. Click an ID to open Borrower 360. " + ex,
                "look_for": "Large names in Stage 2 or with a high/critical band: they move the book's ECL most. Low coverage on a weak name "
                            "may mean under-provisioning."}
    if t == "distribution":
        meta = DISTRIBUTIONS.get(tile.get("column", ""), {"label": "value"})
        if rows:
            top = max(rows, key=lambda r: r.get("ead") or 0)
            ex = f"For example, the {top.get('k')} band holds {fmt.amount(top.get('ead'))} of EAD across {fmt.count(top.get('obligors'))} obligors."
        return {"shows": f"How the exposure of {scope} spreads across {meta['label']} bands at {period}.",
                "formula": f"Each facility is placed in a {meta['label']} band; bar = Σ EAD of the facilities in that band. Obligors = distinct names in the band.",
                "read": "Bands run from low to high left to right; the bar height is the EAD in that band. " + ex,
                "look_for": f"Exposure piling into the weak end (for example DSCR below 1.0×, LTV above 100%, PD above 5%): those names cannot "
                            f"carry their debt or are under-secured."}
    if t in ("migration", "roll_rate"):
        what = "stage" if t == "migration" else "delinquency bucket"
        return {"shows": f"How exposure moved between {what}s from the prior period to {period}.",
                "formula": ("Cell (row, column) = Σ EAD that was in the row stage last period and is in the column stage now; "
                            "row shares = cell ÷ row total × 100." if t == "migration" else
                            "Cell (row, column) = accounts in the row bucket last month now in the column bucket ÷ accounts in the row bucket × 100."),
                "read": "Rows are where exposure was, columns where it is now. The diagonal stayed put; right of the diagonal got worse, left got better.",
                "look_for": "Large values right of the diagonal (Stage 1 → 2, current → 30+): that is the flow into loss. Compare with last period."}
    if t == "vintage":
        return {"shows": "The 30+ days-past-due share of EAD for each origination year, period by period.",
                "formula": "30+ DPD share = Σ EAD of accounts 30+ days past due ÷ Σ EAD of the vintage × 100.",
                "read": "One line per vintage year. A line above the others is a weaker year of lending." + (f" Latest period: {rows[-1].get('period')}." if rows else ""),
                "look_for": "Recent vintages rising faster than older ones did at the same age: a sign underwriting loosened."}
    if t == "concentration":
        b = {x["label"]: x["display"] for x in out.get("badges") or []}
        return {"shows": f"The ten largest obligors' share of EAD in {scope}, and the Herfindahl-Hirschman Index (HHI).",
                "formula": "Share = obligor EAD ÷ total EAD × 100. HHI = Σ (share in %)² over every obligor: 10,000 is one name, "
                           "below 1,500 is unconcentrated, above 2,500 highly concentrated.",
                "read": f"One bar per name, largest first. Here the top 10 hold {b.get('Top 10 share', '–')} of EAD and the HHI is {b.get('HHI', '–')}.",
                "look_for": "One or two names far above the rest, or a top-10 share rising over time: single-name risk against the "
                            "single-obligor limit."}
    if t == "reasons":
        if rows:
            ex = f"For example, '{rows[0].get('k')}' is behind {fmt.count(rows[0].get('obligors'))} warned obligors with {fmt.amount(rows[0].get('ead'))} of EAD."
        return {"shows": f"Why obligors in {scope} are on Early Warning at {period}: the triggered reasons.",
                "formula": "Bar = the number of distinct warned obligors (band moderate, high or critical) with that reason; EAD = Σ their EAD. "
                           "A name with two reasons counts under both.",
                "read": "One bar per reason, most frequent first. " + ex,
                "look_for": "One reason dominating (for example DSCR below covenant): a common driver worth a sector-wide action."}
    if t == "regulatory":
        if rows:
            ex = (f"For example, {rows[0].get('k')} ({rows[0].get('title')}) has {fmt.count(rows[0].get('breaches'))} "
                  f"breaches with {fmt.amount(rows[0].get('ead'))} of EAD.")
        return {"shows": f"Breaches of the CBUAE Credit Risk Management Standards on the whole book at {period}, by article.",
                "formula": "Bar = the number of facilities or accounts that fail the article's check (for example 90+ days past "
                           "due not in Stage 3, a Stage 3 provision below the floor, a collateral valuation out of date); EAD and "
                           "ECL = Σ over the breaching exposures; shortfall = Σ (floor − ECL) for the provision checks.",
                "read": "One bar per article, most breaches first; an article with no bar is compliant. " + ex,
                "look_for": "A provision shortfall (Art. 9.23, 9.24) or a staging breach (Art. 6.4, 7.8, 6.12): these change ECL "
                            "and the Stage 3 ratio the Board reports under Art. 12.3."}
    if t == "compare":
        cmp_label = (ctx.compare or {}).get("label", "the comparator") if getattr(ctx, "compare", None) else "the comparator"
        if rows:
            r = rows[-1]
            ex = f"For example, at {r.get('period')} this lens is {_val(r.get('a'), unit)} against {_val(r.get('b'), unit)} for {cmp_label}."
        return {"shows": f"{label} for this lens against {cmp_label}, period by period.",
                "formula": f + " Both lines use the same formula on their own scope.",
                "read": "Two lines over time; the gap is the difference between the two scopes. " + ex,
                "look_for": "A gap that widens: this lens is drifting away from its peer group."}
    if t == "pinned":
        src = tile.get("source") or {}
        ys = src.get("y") or []
        return {"shows": f"A chart or table placed from the lens assistant's answer to: \"{src.get('question') or 'a question'}\".",
                "formula": "The figures are the answer's own query results (the queries are below). "
                           + (f"Series: {', '.join((src.get('labels') or {}).get(y, y) for y in ys)}." if ys else ""),
                "read": f"It is a snapshot taken on {(src.get('added_at') or '')[:10] or 'the day it was added'}; ratings run AAA to D. "
                        "Ask the assistant again to refresh it.",
                "look_for": "The point the assistant made in its answer; delete the tile from (⋯) when it is no longer needed."}
    return {"shows": out.get("default_title") or tile.get("title") or t, "formula": f, "read": "", "look_for": ""}
