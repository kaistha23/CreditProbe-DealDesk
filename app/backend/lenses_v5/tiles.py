"""Tile kinds and how each one is computed and drawn (Plotly figure dicts; every number formatted per G5).

A tile spec: {id, type, title, metric?, metrics?, dim?, chart?, column?, top?, custom?}

  kpi           one metric now, change against the prior period, a sparkline (the KPI row)
  trend         metrics over the last 8 quarters / 12 months (line, bar, area)
  breakdown     a metric by a dimension at the as-of period (hbar, bar, donut, treemap); with a comparator lens
                scope, side by side
  mix_trend     EAD split by a dimension (stage, EWS band) over the window, stacked
  top_names     the 20 largest obligors by a metric, with stage, band, rating, EAD, ECL, coverage
  distribution  EAD by bins of a numeric column (DSCR, LTV, PD, utilisation, behaviour score)
  migration     stage migration matrix, prior period -> now, by EAD
  roll_rate     retail: delinquency bucket roll rates, prior month -> now, % of accounts
  vintage       retail: 30+ DPD share by vintage over the window
  concentration top 10 obligors' share of EAD and the HHI
  reasons       the Early Warning reasons behind warned obligors
  compare       one metric over the window: the lens scope against a comparator scope
  appetite      R16 M5: corporate risk-appetite rows the books can measure, utilisation of each limit (CRO lens)
  rating_migration  R16 M5: obligors by rating (corporate) or behaviour score band (retail), prior -> now
  data_quality  R16 M5: missing and stale values of the fields the models read, at the as-of period
  watchlist_movement  R16 M5: obligors added to / removed from the watchlist (retail: the Early Warning watch)
"""
from __future__ import annotations

from typing import Any

from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import BAND_ORDER, DIMS, DISTRIBUTIONS, METRICS
from backend.lenses_v5.engine import (BAND_COLOURS, ENGINE, STAGE_COLOURS, TABLE, V5_PALETTE, LensError, _q, dim_order,
                                      label_of)

TYPES = ("trend", "breakdown", "mix_trend", "top_names", "distribution", "migration", "roll_rate", "vintage",
         "concentration", "reasons", "compare", "pinned", "regulatory",
         "appetite", "rating_migration", "data_quality", "watchlist_movement")
CHARTS = {"pinned": ("bar", "hbar", "line", "stacked", "grouped", "combo", "table"), "trend": ("line", "bar", "area"), "breakdown": ("hbar", "bar", "donut", "treemap"), "mix_trend": ("stacked", "stacked100"),
          "distribution": ("bar", "hbar"), "compare": ("line", "bar"), "vintage": ("line",), "concentration": ("hbar", "bar"),
          "reasons": ("hbar", "bar"), "regulatory": ("hbar", "bar"), "migration": ("heatmap",), "roll_rate": ("heatmap",), "top_names": ("table",),
          "appetite": ("bullet",), "rating_migration": ("heatmap",), "data_quality": ("table",), "watchlist_movement": ("bar",)}


def _layout(x_title: str = "", y_title: str = "", unit: str = "", horizontal: bool = False, **extra: Any) -> dict[str, Any]:
    ax_val = {"title": {"text": y_title}, "tickformat": fmt.tickformat(unit), "ticksuffix": fmt.axis_suffix(unit),
              "gridcolor": "rgba(100,116,139,0.15)", "zeroline": False}
    ax_cat = {"title": {"text": x_title}, "automargin": True, "type": "category"}
    lay = {"margin": {"l": 56, "r": 16, "t": 12, "b": 48}, "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
           "font": {"family": "Inter, system-ui, sans-serif", "size": 11, "color": "#334155"}, "showlegend": False,
           "legend": {"orientation": "h", "y": 1.12, "x": 0}, "hoverlabel": {"bgcolor": "#fff"}}
    if horizontal:
        lay["xaxis"], lay["yaxis"] = ax_val, {**ax_cat, "autorange": "reversed"}
    else:
        lay["xaxis"], lay["yaxis"] = ax_cat, ax_val
    lay.update(extra)
    return lay


def _col(key: str, label: str, unit: str = "text") -> dict[str, str]:
    return {"key": key, "label": fmt.axis_title(label, unit) if unit not in ("text", "count") else label, "unit": unit}


def _metric_unit(key: str, custom: dict[str, Any]) -> tuple[str, str]:
    if key in custom:
        return custom[key]["label"], custom[key].get("unit", "pct")
    m = METRICS[key]
    return m.label, m.unit


class Ctx:
    """What a tile needs from its lens: book, scope filters, period, comparator, custom ratios."""

    def __init__(self, spec: dict[str, Any], period: str = ""):
        self.spec = spec
        self.book = spec["book"]
        self.filters = spec.get("filters") or []
        self.period = period or spec.get("period") or ENGINE.as_of(self.book)
        if self.period not in ENGINE.periods(self.book):
            self.period = ENGINE.as_of(self.book)
        self.window = ENGINE.window(self.book, self.period)
        self.custom = {c["key"]: c for c in spec.get("custom_metrics") or []}
        self.compare = spec.get("compare")       # {label, filters}

    @property
    def T(self) -> str:
        return TABLE[self.book]

    def where(self, filters: list[dict[str, Any]] | None = None) -> str:
        return ENGINE.where(self.book, self.filters if filters is None else filters)


def run_tile(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    t = tile.get("type")
    fn = {"trend": _trend, "breakdown": _breakdown, "mix_trend": _mix_trend, "top_names": _top_names,
          "distribution": _distribution, "migration": _migration, "roll_rate": _roll_rate, "vintage": _vintage,
          "concentration": _concentration, "reasons": _reasons, "compare": _compare, "pinned": _pinned,
          "regulatory": _regulatory, "appetite": _appetite, "rating_migration": _rating_migration,
          "data_quality": _data_quality, "watchlist_movement": _watchlist_movement}.get(t)
    if fn is None:
        raise LensError(f"'{t}' is not a tile type.")
    tf = [f for f in tile.get("filters") or [] if f.get("values")]
    if tf:   # PLAN_R6 L5: a tile's own filters narrow this tile only, on top of the lens scope
        import copy as _copy
        ctx = _copy.copy(ctx)
        ctx.filters = [*ctx.filters, *tf]
    out = fn(tile, ctx)
    if tf:
        out["badges"] = [*(out.get("badges") or []),
                         *({"label": DIMS[f["dim"]].label, "display": ", ".join(str(v) for v in f["values"])} for f in tf if f.get("dim") in DIMS)]
    try:   # PLAN_R6 L3: the (i) explains the tile in plain words with this tile's figures
        from backend.lenses_v5.explain import explain
        out["explain"] = explain(tile, out, ctx)
    except Exception:  # noqa: BLE001 - an explanation never blocks a tile
        out["explain"] = None
    return {"id": tile["id"], "type": t, "title": tile.get("title") or out.pop("default_title", t), "chart": tile.get("chart") or CHARTS[t][0],
            "size": tile.get("size") or ("wide" if t in ("top_names", "migration", "roll_rate", "rating_migration", "data_quality") else "half"), **out}


def _pinned(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    from backend.lenses_v5 import pinned
    return pinned.run(tile, ctx)


# ------------------------------------------------------------------ KPI row
def _kpi_explain(key: str, label: str, unit: str, v: Any, p: Any, ctx: Ctx) -> dict[str, str]:
    from backend.lenses_v5.explain import metric_formula
    prior = ENGINE.prior(ctx.book, ctx.period) or "the prior period"
    return {"shows": f"{label} for {ctx.spec.get('scope_label') or 'the lens scope'} at {ctx.period}, the change on {prior}, and the trend.",
            "formula": metric_formula(key, ctx.custom),
            "read": f"Now {fmt.fmt_value(v, unit)}; at {prior} it was {fmt.fmt_value(p, unit)}. Red means the change is unfavourable, green favourable. "
                    "The small line is the last periods.",
            "look_for": "A change against the trend of the sparkline, or a move that breaks a risk appetite threshold."}

def kpis(ctx: Ctx, keys: list[str]) -> list[dict[str, Any]]:
    keys = [k for k in keys if k in ctx.custom or (k in METRICS and ctx.book in METRICS[k].books)]
    rows, sql = ENGINE.series(ctx.book, ctx.filters, ctx.window, keys, custom=ctx.custom)
    by = {r["period"]: r for r in rows}
    now = by.get(ctx.period, {})
    prev = by.get(ENGINE.prior(ctx.book, ctx.period) or "", {})
    out = []
    for k in keys:
        label, unit = _metric_unit(k, ctx.custom)
        v, p = now.get(k), prev.get(k)
        change = None if v is None or p is None else round(v - p, 2)
        better = ctx.custom[k].get("better", "lower") if k in ctx.custom else METRICS[k].better
        tone = "neutral"
        if change and better in ("lower", "higher"):
            tone = "good" if (change < 0) == (better == "lower") else "bad"
        out.append({"key": k, "label": label, "unit": unit, "value": v, "display": fmt.fmt_value(v, unit),
                    "prior": p, "change": change,
                    "change_display": None if change is None else (("+" if change > 0 else "") + (fmt.fmt_value(change, unit) if unit != "pct" else f"{change:,.2f} pp")),
                    "tone": tone, "spark": [{"period": r["period"], "value": r.get(k)} for r in rows],
                    "source": ctx.custom[k].get("source", "Custom ratio") if k in ctx.custom else METRICS[k].source,
                    "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows)),
                    "explain": _kpi_explain(k, label, unit, v, p, ctx)})
    return out


# ------------------------------------------------------------------ tiles
def _trend(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    keys = tile.get("metrics") or [tile.get("metric", "ecl")]
    rows, sql = ENGINE.series(ctx.book, ctx.filters, ctx.window, keys, custom=ctx.custom)
    chart = tile.get("chart") or "line"
    traces = []
    units = [_metric_unit(k, ctx.custom)[1] for k in keys]
    for i, k in enumerate(keys):
        label, unit = _metric_unit(k, ctx.custom)
        y = [r.get(k) for r in rows]
        tr: dict[str, Any] = {"type": "bar" if chart == "bar" else "scatter", "name": label, "x": [r["period"] for r in rows], "y": y,
                              "hovertemplate": f"%{{x}}<br>{label}: {fmt.hover(unit)}<extra></extra>", "marker": {"color": V5_PALETTE[i % 12]}}
        if chart != "bar":
            tr["mode"] = "lines+markers"
            tr["line"] = {"width": 2.2, "color": V5_PALETTE[i % 12]}
            if chart == "area":
                tr["fill"] = "tozeroy"
        if i == 1 and units[1] != units[0]:
            tr["yaxis"] = "y2"
        traces.append(tr)
    l0, u0 = _metric_unit(keys[0], ctx.custom)
    lay = _layout("", fmt.axis_title(l0, u0), u0, showlegend=len(keys) > 1)
    if len(keys) > 1 and units[1] != units[0]:
        l1, u1 = _metric_unit(keys[1], ctx.custom)
        lay["yaxis2"] = {"overlaying": "y", "side": "right", "title": {"text": fmt.axis_title(l1, u1)}, "tickformat": fmt.tickformat(u1),
                         "ticksuffix": fmt.axis_suffix(u1), "showgrid": False}
        lay["margin"]["r"] = 56
    cols = [_col("period", "Period")] + [_col(k, *_metric_unit(k, ctx.custom)) for k in keys]
    title = " and ".join(_metric_unit(k, ctx.custom)[0] for k in keys) + " trend"
    return {"default_title": title, "figure": {"data": traces, "layout": lay}, "table": {"columns": cols, "rows": rows},
            "unit": u0, "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _ordered(rows: list[dict[str, Any]], dim_key: str, metric: str) -> list[dict[str, Any]]:
    d = DIMS[dim_key]
    if d.order == "rating":
        from backend.v5common import ratings
        return sorted(rows, key=lambda r: ratings.sort_key(r.get("k")))
    if d.order == "band":
        return sorted(rows, key=lambda r: BAND_ORDER.index(r["k"]) if r.get("k") in BAND_ORDER else 9)
    if d.order == "natural":
        return sorted(rows, key=lambda r: str(r.get("k")))
    return sorted(rows, key=lambda r: -(r.get(metric) or 0))


def _breakdown(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    key = tile.get("metric", "ead")
    dim = tile.get("dim", "sector")
    if dim not in DIMS or ctx.book not in DIMS[dim].books:
        raise LensError(f"'{dim}' is not a dimension of the {ctx.book} book.")
    label, unit = _metric_unit(key, ctx.custom)
    rows, sql = ENGINE.series(ctx.book, ctx.filters, [ctx.period], [key], dim=dim, custom=ctx.custom)
    rows = _ordered([r for r in rows if r.get(key) is not None], dim, key)
    top = int(tile.get("top") or 15)
    if DIMS[dim].order == "value" and len(rows) > top:
        rows = rows[:top]
    comp_rows: list[dict[str, Any]] = []
    if ctx.compare and tile.get("compare", True):
        comp_rows, sql2 = ENGINE.series(ctx.book, ctx.compare["filters"], [ctx.period], [key], dim=dim, custom=ctx.custom)
        sql += ";\n" + sql2
    chart = tile.get("chart") or ("hbar" if DIMS[dim].order == "value" else "bar")
    names = [label_of(DIMS[dim], r["k"]) for r in rows]
    vals = [r[key] for r in rows]
    colours = [STAGE_COLOURS.get(n) or BAND_COLOURS.get(n) or V5_PALETTE[0] for n in names]
    if chart == "donut":
        data = [{"type": "pie", "hole": 0.55, "labels": names, "values": vals, "sort": False, "marker": {"colors": [STAGE_COLOURS.get(n) or BAND_COLOURS.get(n) or V5_PALETTE[i % 12] for i, n in enumerate(names)]},
                 "hovertemplate": f"%{{label}}<br>{label}: {fmt.hover(unit, 'value')}<extra></extra>", "textinfo": "percent"}]
        lay = _layout(showlegend=True)
        lay.pop("xaxis"); lay.pop("yaxis")
    elif chart == "treemap":
        data = [{"type": "treemap", "labels": names, "parents": [""] * len(names), "values": vals,
                 "hovertemplate": f"%{{label}}<br>{label}: {fmt.hover(unit, 'value')}<extra></extra>", "marker": {"colors": [V5_PALETTE[i % 12] for i in range(len(names))]}}]
        lay = _layout()
        lay.pop("xaxis"); lay.pop("yaxis")
    else:
        h = chart == "hbar"
        tr = {"type": "bar", "orientation": "h" if h else "v", "name": ctx.spec.get("scope_label") or "This lens",
              ("y" if h else "x"): names, ("x" if h else "y"): vals, "marker": {"color": colours},
              "hovertemplate": f"%{{{'y' if h else 'x'}}}<br>{label}: {fmt.hover(unit, 'x' if h else 'y')}<extra></extra>"}
        data = [tr]
        if comp_rows:
            cm = {label_of(DIMS[dim], r["k"]): r.get(key) for r in comp_rows}
            tr["marker"] = {"color": V5_PALETTE[0]}
            data.append({**tr, "name": ctx.compare.get("label", "Comparator"), ("x" if h else "y"): [cm.get(n) for n in names], "marker": {"color": V5_PALETTE[1]}})
        lay = _layout(DIMS[dim].label, fmt.axis_title(label, unit), unit, horizontal=h, showlegend=bool(comp_rows), barmode="group")
        if h:
            lay["xaxis"]["title"]["text"] = fmt.axis_title(label, unit)
            lay["yaxis"]["title"]["text"] = ""
            lay["margin"]["l"] = 140
    table_rows = [{"k": label_of(DIMS[dim], r["k"]), key: r[key]} for r in rows]
    return {"default_title": f"{label} by {DIMS[dim].label.lower()}", "figure": {"data": data, "layout": lay}, "unit": unit,
            "table": {"columns": [_col("k", DIMS[dim].label), _col(key, label, unit)], "rows": table_rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _mix_trend(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    key = tile.get("metric", "ead")
    dim = tile.get("dim", "stage")
    label, unit = _metric_unit(key, ctx.custom)
    rows, sql = ENGINE.series(ctx.book, ctx.filters, ctx.window, [key], dim=dim, custom=ctx.custom)
    pct = (tile.get("chart") or "stacked100") == "stacked100"
    tot: dict[str, float] = {}
    for r in rows:
        tot[r["period"]] = tot.get(r["period"], 0) + (r.get(key) or 0)
    ks = [x["k"] for x in _ordered([{"k": k} for k in {r["k"] for r in rows}], dim, key)] if DIMS[dim].order != "value" else \
        sorted({r["k"] for r in rows}, key=lambda k: -sum(r.get(key) or 0 for r in rows if r["k"] == k))
    data = []
    for i, k in enumerate(ks):
        name = label_of(DIMS[dim], k)
        pts = {r["period"]: r.get(key) for r in rows if r["k"] == k}
        y = [round((pts.get(p) or 0) / tot[p] * 100, 2) if pct and tot.get(p) else pts.get(p) for p in ctx.window]
        data.append({"type": "bar", "name": name, "x": ctx.window, "y": y, "marker": {"color": STAGE_COLOURS.get(name) or BAND_COLOURS.get(name) or V5_PALETTE[i % 12]},
                     "hovertemplate": f"%{{x}} · {name}<br>{fmt.hover('pct' if pct else unit)}<extra></extra>"})
    lay = _layout("", "Share of " + label + " (%)" if pct else fmt.axis_title(label, unit), "pct" if pct else unit, barmode="stack", showlegend=True)
    return {"default_title": f"{label} mix by {DIMS[dim].label.lower()}", "figure": {"data": data, "layout": lay}, "unit": unit,
            "table": {"columns": [_col("period", "Period"), _col("k", DIMS[dim].label), _col(key, label, unit)],
                      "rows": [{"period": r["period"], "k": label_of(DIMS[dim], r["k"]), key: r.get(key)} for r in rows]},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _top_names(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    key = tile.get("metric", "ead")
    n = int(tile.get("top") or 20)
    label, unit = _metric_unit(key, ctx.custom)
    m = ENGINE.metric(key, ctx.book) if key not in ctx.custom else None
    agg = ENGINE.custom_agg(ctx.custom[key], ctx.book) if m is None else ENGINE.agg(m)
    extra = ", ANY_VALUE(rating_current) AS rating, ANY_VALUE(sector) AS segment" if ctx.book == "corporate" else ", ANY_VALUE(product) AS segment"
    sql = (f"SELECT owner_id, ANY_VALUE(owner_name) AS name{extra}, MAX(stage) AS worst_stage, "
           f"MAX(CASE ews_band WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'moderate' THEN 2 WHEN 'low' THEN 1 ELSE 0 END) AS band_rank, "
           f"SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl, SUM(ecl_sar_mn) / NULLIF(SUM(ead_sar_mn), 0) * 100 AS coverage, "
           f"{agg} AS v FROM {ctx.T} WHERE period = {_q(ctx.period)} AND {ctx.where()} GROUP BY owner_id ORDER BY v DESC NULLS LAST LIMIT {n}")
    raw = ENGINE.q(sql)
    bands = {4: "critical", 3: "high", 2: "moderate", 1: "low", 0: "none"}
    rows = []
    for r in raw:
        row = {"owner_id": r["owner_id"], "name": r["name"], "segment": r.get("segment"), "stage": f"Stage {r['worst_stage']}",
               "band": bands.get(r["band_rank"], "none"), "ead": fmt.round_for(r["ead"], "sar_mn"), "ecl": fmt.round_for(r["ecl"], "sar_mn"),
               "coverage": fmt.round_for(r["coverage"], "pct")}
        if ctx.book == "corporate":
            row["rating"] = r.get("rating")
        if key not in ("ead", "ecl", "coverage"):
            row[key] = fmt.round_for(r["v"], unit)
        rows.append(row)
    cols = [_col("owner_id", "Borrower" if ctx.book == "corporate" else "Customer")]
    if ctx.book == "corporate":
        cols += [_col("name", "Name"), _col("segment", "Sector"), _col("rating", "Rating")]
    else:
        cols += [_col("segment", "Main product")]
    cols += [_col("stage", "Worst stage"), _col("band", "Early Warning band"), _col("ead", "EAD", "sar_mn"), _col("ecl", "ECL", "sar_mn"), _col("coverage", "Coverage", "pct")]
    if key not in ("ead", "ecl", "coverage"):
        cols.append(_col(key, label, unit))
    who = "borrowers" if ctx.book == "corporate" else "customers"
    return {"default_title": f"Top {n} {who} by {label}", "figure": None, "unit": unit, "table": {"columns": cols, "rows": rows},
            "links": {"owner": "/borrower-360?book=" + ctx.book + "&id="}, "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _distribution(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    col = tile.get("column", "dscr_x")
    meta = DISTRIBUTIONS.get(col)
    if meta is None or ctx.book not in meta["books"]:
        raise LensError(f"There is no {col} distribution for the {ctx.book} book.")
    scale = meta.get("scale", 1)
    e = meta["edges"]
    expr = f"({col} * {scale})"
    case = "CASE " + " ".join(f"WHEN {expr} < {e[i + 1]} THEN {i}" for i in range(len(e) - 1)) + f" ELSE {len(e) - 1} END"
    sql = (f"SELECT {case} AS b, COUNT(DISTINCT owner_id) AS obligors, SUM(ead_sar_mn) AS ead FROM {ctx.T} "
           f"WHERE period = {_q(ctx.period)} AND {ctx.where()} AND {col} IS NOT NULL GROUP BY b ORDER BY b")
    raw = {r["b"]: r for r in ENGINE.q(sql)}
    u = meta["unit"]
    sfx = {"pct": "%", "ratio": "x", "days": "", "score": ""}.get(u, "")

    def lab(i: int) -> str:
        if i == len(e) - 1:
            return f"{e[i]:g}{sfx}+"
        return f"{e[i]:g}–{e[i + 1]:g}{sfx}" if i else f"Below {e[1]:g}{sfx}"
    rows = [{"k": lab(i), "obligors": int(raw.get(i, {}).get("obligors") or 0), "ead": fmt.round_for(raw.get(i, {}).get("ead") or 0, "sar_mn")}
            for i in range(len(e))]
    rows = [r for r in rows if r["obligors"] or rows.index(r) < len(e) - 1]
    data = [{"type": "bar", "x": [r["k"] for r in rows], "y": [r["ead"] for r in rows], "name": "EAD", "marker": {"color": V5_PALETTE[0]},
             "customdata": [r["obligors"] for r in rows],
             "hovertemplate": "%{x}<br>EAD: SAR %{y:,.2f} m<br>Obligors: %{customdata:,.0f}<extra></extra>"}]
    lay = _layout(meta["label"], "EAD (SAR m)", "sar_mn")
    return {"default_title": f"{meta['label']} distribution", "figure": {"data": data, "layout": lay}, "unit": "sar_mn",
            "table": {"columns": [_col("k", meta["label"]), _col("obligors", "Obligors", "count"), _col("ead", "EAD", "sar_mn")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _matrix(sql: str, ctx: Ctx, title: str, labels: list[str], value_unit: str, row_title: str, col_title: str,
            normalise: bool) -> dict[str, Any]:
    raw = ENGINE.q(sql)
    cell = {(str(r["a"]), str(r["b"])): r["v"] for r in raw}
    z, rows = [], []
    for a in labels:
        tot = sum(cell.get((a, b)) or 0 for b in labels)
        line = []
        for b in labels:
            v = cell.get((a, b)) or 0
            line.append(round(v / tot * 100, 2) if normalise and tot else fmt.round_for(v, value_unit))
        z.append(line)
        rows.append({"k": a, **{b: line[j] for j, b in enumerate(labels)}})
    u = "pct" if normalise else value_unit
    data = [{"type": "heatmap", "x": labels, "y": labels, "z": z, "colorscale": [[0, "#F1F5F9"], [1, "#10527A"]], "showscale": False,
             "texttemplate": "%{z:,.1f}" + ("%" if normalise else ""), "hovertemplate": f"{row_title}: %{{y}}<br>{col_title}: %{{x}}<br>{fmt.hover(u, 'z')}<extra></extra>"}]
    lay = _layout(col_title, row_title, u)
    lay["xaxis"] = {"title": {"text": col_title}, "type": "category", "automargin": True, "side": "bottom"}
    lay["yaxis"] = {"title": {"text": row_title}, "type": "category", "automargin": True, "autorange": "reversed"}
    lay["margin"]["l"] = 110
    cols = [_col("k", f"{row_title} → {col_title}")] + [_col(b, b, u) for b in labels]
    return {"default_title": title, "figure": {"data": data, "layout": lay}, "unit": u, "table": {"columns": cols, "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(raw))}


def _migration(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    p0 = ENGINE.prior(ctx.book, ctx.period) or ctx.period
    sql = (f"SELECT 'Stage ' || CAST(a.stage AS VARCHAR) AS a, 'Stage ' || CAST(b.stage AS VARCHAR) AS b, SUM(b.ead_sar_mn) AS v "
           f"FROM {ctx.T} a JOIN {ctx.T} b ON a.exposure_id = b.exposure_id AND a.period = {_q(p0)} AND b.period = {_q(ctx.period)} "
           f"WHERE {_alias(ctx, 'b')} GROUP BY 1, 2")
    return _matrix(sql, ctx, f"Stage migration {p0} → {ctx.period} (share of EAD)", ["Stage 1", "Stage 2", "Stage 3"], "sar_mn",
                   f"Stage {p0}", f"Stage {ctx.period}", normalise=True)


def _alias(ctx: Ctx, a: str) -> str:
    """The scope condition on an aliased table (dimensions are plain columns or expressions over them)."""
    parts = []
    for f in ctx.filters:
        d = DIMS[f["dim"]]
        col = d.sql.replace("stage", f"{a}.stage") if d.key == "stage" else (d.sql.replace(d.key, f"{a}.{d.key}") if d.expr else f"{a}.{d.key}")
        parts.append(f"{col} IN ({', '.join(_q(v) for v in f['values'])})")
    return " AND ".join(parts) or "TRUE"


def _roll_rate(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    if ctx.book != "retail":
        raise LensError("Roll rates are a retail view; use the stage migration matrix for corporate.")
    p0 = ENGINE.prior(ctx.book, ctx.period) or ctx.period
    labels = [r["k"] for r in ENGINE.q(f"SELECT DISTINCT delinquency_bucket AS k FROM ret WHERE period = {_q(ctx.period)} ORDER BY 1")]
    order = ["Current", "1-29 DPD", "30-59 DPD", "60-89 DPD", "90+ DPD"]
    labels = sorted(labels, key=lambda x: order.index(x) if x in order else 99)
    sql = (f"SELECT a.delinquency_bucket AS a, b.delinquency_bucket AS b, COUNT(*) AS v FROM ret a JOIN ret b "
           f"ON a.exposure_id = b.exposure_id AND a.period = {_q(p0)} AND b.period = {_q(ctx.period)} WHERE {_alias(ctx, 'b')} GROUP BY 1, 2")
    return _matrix(sql, ctx, f"Roll rates {p0} → {ctx.period} (% of accounts)", labels, "count", f"Bucket {p0}", f"Bucket {ctx.period}", normalise=True)


def _vintage(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    if ctx.book != "retail":
        raise LensError("Vintage curves are a retail view.")
    sql = (f"SELECT period, CAST(vintage_year AS VARCHAR) AS k, SUM(CASE WHEN dpd_days >= 30 THEN ead_sar_mn END) / NULLIF(SUM(ead_sar_mn), 0) * 100 AS v "
           f"FROM ret WHERE period IN ({', '.join(_q(p) for p in ctx.window)}) AND {ctx.where()} GROUP BY 1, 2 ORDER BY 2, 1")
    raw = ENGINE.q(sql)
    ks = sorted({r["k"] for r in raw})[-6:]
    data = []
    for i, k in enumerate(ks):
        pts = {r["period"]: fmt.round_for(r["v"], "pct") for r in raw if r["k"] == k}
        data.append({"type": "scatter", "mode": "lines+markers", "name": f"Vintage {k}", "x": ctx.window, "y": [pts.get(p) for p in ctx.window],
                     "line": {"color": V5_PALETTE[i % 12], "width": 2}, "hovertemplate": f"%{{x}} · {k}<br>30+ DPD: {fmt.hover('pct')}<extra></extra>"})
    rows = [{"period": r["period"], "k": r["k"], "v": fmt.round_for(r["v"], "pct")} for r in raw if r["k"] in ks]
    return {"default_title": "30+ DPD share of EAD by vintage", "figure": {"data": data, "layout": _layout("", "30+ DPD share (%)", "pct", showlegend=True)},
            "unit": "pct", "table": {"columns": [_col("period", "Period"), _col("k", "Vintage"), _col("v", "30+ DPD share", "pct")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(raw))}


def _concentration(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    n = max(5, min(50, int(tile.get("top") or 10)))   # R16 M5: the CRO lens reads the top 20
    sql = (f"WITH o AS (SELECT owner_id, ANY_VALUE(owner_name) AS name, SUM(ead_sar_mn) AS ead FROM {ctx.T} "
           f"WHERE period = {_q(ctx.period)} AND {ctx.where()} GROUP BY owner_id), t AS (SELECT SUM(ead) AS tot FROM o) "
           f"SELECT o.owner_id, o.name, o.ead, o.ead / t.tot * 100 AS share, "
           f"(SELECT SUM(POWER(ead / t.tot * 100, 2)) FROM o) AS hhi FROM o, t ORDER BY o.ead DESC LIMIT {n}")
    raw = ENGINE.q(sql)
    hhi = fmt.round_for(raw[0]["hhi"], "count") if raw else None
    top10 = round(sum(r["share"] or 0 for r in raw), 2)   # the top-n share (n = 10 unless the tile says otherwise)
    names = [str(r["name"] if ctx.book == "corporate" else r["owner_id"]) for r in raw]
    data = [{"type": "bar", "orientation": "h", "y": names, "x": [fmt.round_for(r["share"], "pct") for r in raw], "marker": {"color": V5_PALETTE[3]},
             "hovertemplate": "%{y}<br>Share of EAD: %{x:,.2f}%<extra></extra>"}]
    lay = _layout("", "Share of EAD (%)", "pct", horizontal=True)
    lay["xaxis"]["title"]["text"] = "Share of EAD (%)"
    lay["yaxis"]["title"]["text"] = ""
    lay["margin"]["l"] = 160
    rows = [{"owner_id": r["owner_id"], "name": r["name"], "ead": fmt.round_for(r["ead"], "sar_mn"), "share": fmt.round_for(r["share"], "pct")} for r in raw]
    return {"default_title": f"Concentration: top {n} obligors", "figure": {"data": data, "layout": lay}, "unit": "pct",
            "badges": [{"label": f"Top {n} share", "display": fmt.pct(top10), "value": top10}, {"label": "HHI", "display": fmt.count(hhi), "value": hhi}],
            "table": {"columns": [_col("owner_id", "Obligor"), _col("name", "Name"), _col("ead", "EAD", "sar_mn"), _col("share", "Share of EAD", "pct")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(raw))}


def _reasons(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    sql = (f"SELECT TRIM(r) AS k, COUNT(DISTINCT owner_id) AS obligors, SUM(ead_sar_mn) AS ead FROM "
           f"(SELECT owner_id, ead_sar_mn, UNNEST(STRING_SPLIT(ews_reasons, ';')) AS r FROM {ctx.T} "
           f"WHERE period = {_q(ctx.period)} AND {ctx.where()} AND ews_band IN ('moderate','high','critical') AND ews_reasons IS NOT NULL AND ews_reasons <> '') "
           f"WHERE TRIM(r) <> '' GROUP BY 1 ORDER BY obligors DESC LIMIT 10")
    raw = ENGINE.q(sql)
    rows = [{"k": r["k"], "obligors": int(r["obligors"]), "ead": fmt.round_for(r["ead"], "sar_mn")} for r in raw]
    data = [{"type": "bar", "orientation": "h", "y": [r["k"] for r in rows], "x": [r["obligors"] for r in rows], "marker": {"color": BAND_COLOURS["high"]},
             "customdata": [r["ead"] for r in rows], "hovertemplate": "%{y}<br>Warned obligors: %{x:,.0f}<br>EAD: SAR %{customdata:,.2f} m<extra></extra>"}]
    lay = _layout("", "Warned obligors", "count", horizontal=True)
    lay["xaxis"]["title"]["text"] = "Warned obligors"
    lay["yaxis"]["title"]["text"] = ""
    lay["margin"]["l"] = 200
    return {"default_title": "Early Warning reasons (warned obligors)", "figure": {"data": data, "layout": lay}, "unit": "count",
            "table": {"columns": [_col("k", "Reason"), _col("obligors", "Warned obligors", "count"), _col("ead", "EAD", "sar_mn")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(raw))}


def _regulatory(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    """R7 (C3.3): "Regulatory breaches by article": the CBUAE CRM breach checks on this book at the lens period
    (`backend.regulatory.crm_checks`, the `regulatory` data domain). Book-wide: the checks are not narrowed by the
    lens filters (a badge says so)."""
    from backend.regulatory import crm_checks

    per = {"corporate_period": ctx.period} if ctx.book == "corporate" else {"retail_period": ctx.period}
    res = crm_checks.run(per.get("corporate_period"), per.get("retail_period"))
    checks = [c for c in res["checks"] if c["book"] == ctx.book]
    arts: dict[str, dict[str, Any]] = {}
    for c in checks:
        a = arts.setdefault(c["article"], {"k": c["article"], "title": c["title"], "breaches": 0, "ead": 0.0, "ecl": 0.0,
                                           "shortfall": 0.0})
        a["breaches"] += int(c["breaches"])
        a["ead"] += c["ead_sar_mn"]
        a["ecl"] += c["ecl_sar_mn"]
        a["shortfall"] += c["shortfall_sar_mn"]
    rows = sorted(arts.values(), key=lambda r: (-r["breaches"], r["k"]))
    for r in rows:
        for k in ("ead", "ecl", "shortfall"):
            r[k] = fmt.round_for(r[k], "sar_mn")
    data = [{"type": "bar", "orientation": "h", "y": [f"{r['k'].replace('CBUAE CRM ', '')} {r['title']}" for r in rows],
             "x": [r["breaches"] for r in rows], "marker": {"color": BAND_COLOURS["critical"]},
             "customdata": [r["ead"] for r in rows],
             "hovertemplate": "%{y}<br>Breaches: %{x:,.0f}<br>EAD: SAR %{customdata:,.2f} m<extra></extra>"}]
    lay = _layout("", "Breaches", "count", horizontal=True)
    lay["xaxis"]["title"]["text"] = "Breaching " + ("facilities" if ctx.book == "corporate" else "accounts")
    lay["yaxis"]["title"]["text"] = ""
    lay["margin"]["l"] = 260
    total = sum(r["breaches"] for r in rows)
    trace = ENGINE.trace(ctx.book, f"backend.regulatory.crm_checks.run({ctx.book}={ctx.period!r})", ctx.period, len(rows),
                         relation="regulatory.crm_breach")
    return {"default_title": "Regulatory breaches by article", "figure": {"data": data, "layout": lay}, "unit": "count",
            "badges": [{"label": "Breaches", "display": fmt.count(total), "value": total},
                       {"label": "Scope", "display": "whole book (CBUAE CRM Standards)", "value": None}],
            "table": {"columns": [_col("k", "Article"), _col("title", "Check"), _col("breaches", "Breaches", "count"),
                                  _col("ead", "EAD", "sar_mn"), _col("ecl", "ECL", "sar_mn"),
                                  _col("shortfall", "Provision shortfall", "sar_mn")], "rows": rows},
            "links": [{"label": "CBUAE CRM Standards", "href": crm_checks.HREF}],
            "trace": trace}


def _compare(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    key = tile.get("metric", "coverage")
    label, unit = _metric_unit(key, ctx.custom)
    if not ctx.compare:
        raise LensError("This lens has no comparator; ask to compare with a segment first.")
    a, s1 = ENGINE.series(ctx.book, ctx.filters, ctx.window, [key], custom=ctx.custom)
    b, s2 = ENGINE.series(ctx.book, ctx.compare["filters"], ctx.window, [key], custom=ctx.custom)
    me = ctx.spec.get("scope_label") or "This lens"
    other = ctx.compare.get("label", "Comparator")
    data = []
    for i, (name, rows) in enumerate(((me, a), (other, b))):
        data.append({"type": "scatter", "mode": "lines+markers", "name": name, "x": [r["period"] for r in rows], "y": [r.get(key) for r in rows],
                     "line": {"color": V5_PALETTE[i], "width": 2.2}, "hovertemplate": f"%{{x}} · {name}<br>{label}: {fmt.hover(unit)}<extra></extra>"})
    bm = {r["period"]: r.get(key) for r in b}
    rows = [{"period": r["period"], "a": r.get(key), "b": bm.get(r["period"])} for r in a]
    return {"default_title": f"{label}: {me} against {other}", "figure": {"data": data, "layout": _layout("", fmt.axis_title(label, unit), unit, showlegend=True)},
            "unit": unit, "table": {"columns": [_col("period", "Period"), _col("a", f"{me}: {label}", unit), _col("b", f"{other}: {label}", unit)], "rows": rows},
            "trace": ENGINE.trace(ctx.book, s1 + ";\n" + s2, ctx.period, len(rows))}


# ------------------------------------------------------------------ R16 M5: tiles of the persona lenses
def _appetite(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    """The corporate risk-appetite rows the books can measure (data/dealdesk/params/v1/risk_appetite.json, read-only,
    through the monitoring agent's `sources.appetite`), each measured on the lens engine (`metrics.value`, its SQL kept):
    the value now, the appetite, trigger and limit, and the utilisation of the limit (value / limit). Book-wide."""
    if ctx.book != "corporate":
        raise LensError("The risk-appetite statement covers the corporate book; the retail book has no appetite limits to measure.")
    from backend.agents_v5.lenses import metrics as M
    from backend.agents_v5.lenses import sources as S
    app = S.appetite("corporate")
    rows, sqls = [], []
    for a in app["measurable"]:
        if a["mkind"] == "catalogue":
            d = M.mdef(label=a["label"], unit=a["unit"], book="corporate", kind="catalogue", metric=a["metric"], filters=[])
        else:
            d = M.mdef(label=a["label"], unit=a["unit"], book="corporate", kind=a["mkind"], metric="ead", filters=[], segment=a["segment"])
        v, sql = M.value(d, ctx.period)
        sqls.append(sql)
        if v is None or not a["limit"]:
            continue
        util = v / a["limit"] * 100
        status = "breach" if v >= a["limit"] else "trigger" if v >= a["trigger"] else "within"
        u = a["unit"]
        rows.append({"k": a["label"], "value": fmt.fmt_value(v, u), "unit": u,
                     "appetite": None if a.get("appetite") is None else fmt.fmt_value(a["appetite"], u),
                     "trigger": fmt.fmt_value(a["trigger"], u), "limit": fmt.fmt_value(a["limit"], u),
                     "utilisation": fmt.round_for(util, "pct"), "status": status, "kind": a["kind"], "basis": a["basis"]})
    rows.sort(key=lambda r: -(r["utilisation"] or 0))
    colour = {"breach": BAND_COLOURS["critical"], "trigger": BAND_COLOURS["moderate"], "within": STAGE_COLOURS["Stage 1"]}
    data = [{"type": "bar", "orientation": "h", "y": [r["k"] for r in rows], "x": [r["utilisation"] for r in rows],
             "marker": {"color": [colour[r["status"]] for r in rows]}, "customdata": [r["status"] for r in rows],
             "hovertemplate": "%{y}<br>Utilisation of limit: %{x:,.1f}%<br>%{customdata}<extra></extra>"}]
    lay = _layout("", "Utilisation of limit (%)", "pct", horizontal=True)
    lay["xaxis"]["title"]["text"] = "Utilisation of limit (%)"
    lay["yaxis"]["title"]["text"] = ""
    lay["margin"]["l"] = 220
    lay["shapes"] = [{"type": "line", "x0": 100, "x1": 100, "yref": "paper", "y0": 0, "y1": 1, "line": {"color": BAND_COLOURS["critical"], "dash": "dot", "width": 1.5}}]
    n_b = sum(r["status"] == "breach" for r in rows)
    n_t = sum(r["status"] == "trigger" for r in rows)
    sql = ";\n".join(s for s in sqls if s)
    return {"default_title": "Risk appetite: utilisation of limits", "figure": {"data": data, "layout": lay}, "unit": "pct",
            "badges": [{"label": "Past limit", "display": fmt.count(n_b), "value": n_b}, {"label": "Past trigger", "display": fmt.count(n_t), "value": n_t},
                       {"label": "Scope", "display": "whole corporate book", "value": None}],
            "table": {"columns": [_col("k", "Appetite row"), _col("value", "Now"), _col("appetite", "Appetite"), _col("trigger", "Trigger"),
                                  _col("limit", "Limit"), _col("utilisation", "Utilisation of limit", "pct"), _col("status", "Status")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows), relation="corp + risk_appetite.json")}


def _rating_migration(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    """Obligors by rating at the prior period against now (corporate; retail: accounts by behaviour score band), % of each row."""
    p0 = ENGINE.prior(ctx.book, ctx.period) or ctx.period
    if ctx.book == "corporate":
        col, key, who = "rating_current", "owner_id", "obligors"
    else:
        col, key, who = "score_band", "exposure_id", "accounts"
    sql = (f"WITH a AS (SELECT {key} AS id, ANY_VALUE({col}) AS g FROM {ctx.T} WHERE period = {_q(p0)} GROUP BY 1), "
           f"b AS (SELECT {key} AS id, ANY_VALUE({col}) AS g FROM {ctx.T} WHERE period = {_q(ctx.period)} AND {ctx.where()} GROUP BY 1) "
           f"SELECT a.g AS a, b.g AS b, COUNT(*) AS v FROM a JOIN b USING (id) WHERE a.g IS NOT NULL AND b.g IS NOT NULL GROUP BY 1, 2")
    raw = ENGINE.q(sql)
    labels = sorted({str(r["a"]) for r in raw} | {str(r["b"]) for r in raw})
    if ctx.book == "corporate":
        from backend.v5common import ratings
        labels = sorted(labels, key=ratings.sort_key)
    word = "Rating" if ctx.book == "corporate" else "Score band"
    out = _matrix(sql, ctx, f"{word} migration {p0} → {ctx.period} (% of {who})", labels, "count", f"{word} {p0}", f"{word} {ctx.period}", normalise=True)
    stay = sum(r["v"] for r in raw if r["a"] == r["b"])
    tot = sum(r["v"] for r in raw) or 1
    if ctx.book == "corporate":
        from backend.v5common import ratings
        down = sum(r["v"] for r in raw if ratings.sort_key(str(r["b"])) > ratings.sort_key(str(r["a"])))
    else:
        down = sum(r["v"] for r in raw if str(r["b"]) > str(r["a"]))
    out["badges"] = [{"label": "Unchanged", "display": fmt.pct(stay / tot * 100), "value": round(stay / tot * 100, 2)},
                     {"label": "Moved down", "display": fmt.pct(down / tot * 100), "value": round(down / tot * 100, 2)}]
    return out


#: The fields the PD, LGD and EAD models and the Early Warning score read, per book (data quality tile).
DQ_FIELDS = {"corporate": [("pd_pit_12m", "12-month PD", True), ("lgd_pct", "LGD", True), ("ead_sar_mn", "EAD", False),
                           ("rating_current", "Rating", False), ("dscr_x", "DSCR (borrower financials)", True),
                           ("leverage_x", "Leverage (borrower financials)", True), ("collateral_ltv_pct", "Collateral LTV", False),
                           ("ews_score", "Early Warning score", True), ("sector", "Sector", False)],
             "retail": [("pd_pit_12m", "12-month PD", True), ("lgd_pct", "LGD", True), ("ead_sar_mn", "EAD", False),
                        ("behaviour_score", "Behaviour score", True), ("score_band", "Score band", False),
                        ("collateral_ltv_pct", "Collateral LTV", False), ("ews_score", "Early Warning score", True), ("product", "Product", False)]}
DQ_STALE_PERIODS = 4


def _data_quality(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    """Per model input: missing values at the as-of period, and stale values (the same value on every one of the last four
    periods for an exposure present in all four: a PD, score or financial that did not refresh)."""
    win = ENGINE.window(ctx.book, ctx.period, DQ_STALE_PERIODS)
    pin = ", ".join(_q(p) for p in win)
    parts = []
    for col, label, stale in DQ_FIELDS[ctx.book]:
        st = (f"(SELECT COUNT(*) FROM (SELECT exposure_id FROM {ctx.T} WHERE period IN ({pin}) AND {ctx.where()} GROUP BY exposure_id "
              f"HAVING COUNT(DISTINCT period) = {len(win)} AND COUNT({col}) = {len(win)} AND COUNT(DISTINCT {col}) = 1))") if stale and len(win) > 1 else "NULL"
        parts.append(f"SELECT {_q(col)} AS field, {_q(label)} AS label, COUNT(*) AS n, COUNT(*) - COUNT({col}) AS missing, {st} AS stale "
                     f"FROM {ctx.T} WHERE period = {_q(ctx.period)} AND {ctx.where()}")
    sql = " UNION ALL ".join(parts)
    raw = ENGINE.q(sql)
    rows = []
    for r in raw:
        n = int(r["n"] or 0)
        rows.append({"k": r["label"], "field": r["field"], "rows": n, "missing": int(r["missing"] or 0),
                     "missing_pct": fmt.round_for((r["missing"] or 0) / n * 100 if n else None, "pct"),
                     "stale": None if r["stale"] is None else int(r["stale"]),
                     "stale_pct": None if r["stale"] is None or not n else fmt.round_for(r["stale"] / n * 100, "pct")})
    rows.sort(key=lambda r: -((r["missing_pct"] or 0) + (r["stale_pct"] or 0)))
    worst = rows[0] if rows else None
    unit = "facilities" if ctx.book == "corporate" else "accounts"
    return {"default_title": "Data quality: missing and stale model inputs", "figure": None, "unit": "pct",
            "badges": [{"label": "Rows checked", "display": fmt.count(rows[0]["rows"] if rows else 0), "value": rows[0]["rows"] if rows else 0},
                       {"label": "Stale window", "display": f"{win[0]} to {win[-1]}", "value": None},
                       *([{"label": "Worst field", "display": worst["k"], "value": None}] if worst else [])],
            "table": {"columns": [_col("k", "Field"), _col("field", "Column"), _col("rows", unit.capitalize(), "count"), _col("missing", "Missing", "count"),
                                  _col("missing_pct", "Missing", "pct"), _col("stale", "Stale", "count"), _col("stale_pct", "Stale", "pct")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(rows))}


def _watchlist_movement(tile: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    """Obligors on the watchlist at the prior period, added, removed and on it now (corporate: watchlist_flag; retail, which
    carries no watchlist flag: customers in a warned Early Warning band, moderate or worse)."""
    p0 = ENGINE.prior(ctx.book, ctx.period) or ctx.period
    cond = "watchlist_flag = 1" if ctx.book == "corporate" else "ews_band IN ('moderate','high','critical')"
    sql = (f"WITH a AS (SELECT owner_id, MAX(CASE WHEN {cond} THEN 1 ELSE 0 END) AS w, SUM(ead_sar_mn) AS e FROM {ctx.T} "
           f"WHERE period = {_q(p0)} AND {ctx.where()} GROUP BY 1), "
           f"b AS (SELECT owner_id, MAX(CASE WHEN {cond} THEN 1 ELSE 0 END) AS w, SUM(ead_sar_mn) AS e FROM {ctx.T} "
           f"WHERE period = {_q(ctx.period)} AND {ctx.where()} GROUP BY 1) "
           f"SELECT CASE WHEN COALESCE(a.w, 0) = 1 AND COALESCE(b.w, 0) = 1 THEN 'stayed' WHEN COALESCE(a.w, 0) = 0 AND b.w = 1 THEN 'added' "
           f"WHEN a.w = 1 AND COALESCE(b.w, 0) = 0 THEN 'removed' ELSE 'off' END AS k, COUNT(*) AS obligors, "
           f"SUM(CASE WHEN COALESCE(b.w, 0) = 1 THEN b.e ELSE a.e END) AS ead FROM a FULL OUTER JOIN b USING (owner_id) GROUP BY 1")
    raw = {r["k"]: r for r in ENGINE.q(sql)}

    def n(k: str) -> int:
        return int((raw.get(k) or {}).get("obligors") or 0)

    def e(k: str) -> float | None:
        return fmt.round_for((raw.get(k) or {}).get("ead") or 0, "sar_mn")
    rows = [{"k": f"On at {p0}", "obligors": n("stayed") + n("removed"), "ead": None},
            {"k": "Added", "obligors": n("added"), "ead": e("added")},
            {"k": "Removed", "obligors": n("removed"), "ead": e("removed")},
            {"k": f"On at {ctx.period}", "obligors": n("stayed") + n("added"), "ead": None}]
    cols = [V5_PALETTE[8], BAND_COLOURS["high"], STAGE_COLOURS["Stage 1"], V5_PALETTE[0]]
    data = [{"type": "bar", "x": [r["k"] for r in rows], "y": [r["obligors"] for r in rows], "marker": {"color": cols},
             "hovertemplate": "%{x}<br>Obligors: %{y:,.0f}<extra></extra>"}]
    word = "Watchlist" if ctx.book == "corporate" else "Early Warning watch (moderate or worse)"
    return {"default_title": f"{word} movement {p0} → {ctx.period}", "figure": {"data": data, "layout": _layout("", "Obligors", "count")},
            "unit": "count", "badges": [{"label": "Net change", "display": f"{n('added') - n('removed'):+,d}", "value": n("added") - n("removed")}],
            "table": {"columns": [_col("k", "Movement"), _col("obligors", "Obligors", "count"), _col("ead", "EAD", "sar_mn")], "rows": rows},
            "trace": ENGINE.trace(ctx.book, sql, ctx.period, len(raw))}
