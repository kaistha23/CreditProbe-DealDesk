"""Tiles placed from the lens assistant (PLAN_R6 L2): "Add to lens" under a chart or table in an assistant answer.

The tile keeps the answer's rows as a snapshot (the assistant reads relations built for the conversation, not the
engine's lens table, so the query cannot simply be re-run against the lens scope) together with the queries behind
the answer, which become the tile's trace. Every number is drawn and tabled through the G5 formatter, and a rating
axis or first column is put in the global order AAA ... D (L4).
"""
from __future__ import annotations

import copy
import re
import time
from typing import Any

from backend.lenses_v5 import fmt
from backend.lenses_v5.engine import V5_PALETTE, LensError
from backend.v5common import ratings

MAX_ROWS = 200
KINDS = ("bar", "hbar", "line", "stacked", "grouped", "combo", "table")


def unit_of(key: str, label: str = "") -> str:
    """The G5 unit of an answer column, from its name (the convo layer names columns ead_sar_mn, coverage_pct, ...)."""
    k = f"{key} {label}".lower()
    if re.search(r"bps|basis", k):
        return "bps"
    if re.search(r"pct|percent|share|coverage|ratio_pct|rate|%|ltv|npl", k):
        return "pct"
    if re.search(r"sar|ead|ecl|exposure|amount|balance|limit|_mn|outstanding", k):
        return "sar_mn"
    if re.search(r"dscr|leverage|_x\b|multiple", k):
        return "ratio"
    if re.search(r"days|dpd", k):
        return "days"
    if re.search(r"count|number|^n_|obligors|names|customers|accounts|borrowers|warned", k):
        return "count"
    return "score"


def is_rating_scale(values: list[Any]) -> bool:
    xs = [str(v) for v in values if v not in (None, "")]
    return len(xs) > 1 and sum(1 for v in xs if ratings.rank(v) < len(ratings.RATING_ORDER)) / len(xs) >= 0.8


def rating_sorted(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    if key and is_rating_scale([r.get(key) for r in rows]):
        return sorted(rows, key=lambda r: ratings.sort_key(r.get(key)))
    return rows


def make_tile(block: dict[str, Any], sql: str = "", question: str = "", period: str = "") -> dict[str, Any]:
    """The tile spec for an answer block (type chart or table)."""
    btype = block.get("type")
    if btype not in ("chart", "table"):
        raise LensError("Only a chart or a table from an answer can be added to the lens.")
    rows = [dict(r) for r in (block.get("rows") or [])[:MAX_ROWS] if isinstance(r, dict)]
    if not rows:
        raise LensError("That answer block has no rows to place.")
    src: dict[str, Any] = {"rows": rows, "sql": str(sql or "")[:8000], "question": str(question or "")[:300],
                           "period": str(period or ""), "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if btype == "chart":
        x = str(block.get("x") or "")
        ys = [str(y) for y in (block.get("y") or []) if y]
        if not x or not ys:
            raise LensError("That chart has no axis to place.")
        src.update(x=x, y=ys, y2=str(block.get("y2") or ""), labels=dict(block.get("labels") or {}))
        chart = str(block.get("kind") or "bar")
    else:
        cols = block.get("columns") or [{"key": k, "label": k} for k in rows[0]]
        src.update(columns=[{"key": str(c.get("key")), "label": str(c.get("label") or c.get("key"))} for c in cols if isinstance(c, dict)])
        chart = "table"
    return {"type": "pinned", "title": str(block.get("title") or "From the assistant")[:120], "chart": chart if chart in KINDS else "bar",
            "source": src}


def run(tile: dict[str, Any], ctx: Any) -> dict[str, Any]:
    src = tile.get("source") or {}
    rows = copy.deepcopy(src.get("rows") or [])
    trace = {"sql": src.get("sql") or "-- snapshot of an assistant answer (no query recorded)",
             "relations": ["lens assistant answer"], "sources": ["lens assistant"], "period": src.get("period") or ctx.period,
             "row_count": len(rows), "engine": "duckdb", "at": src.get("added_at") or ""}
    badge = [{"label": "From the assistant", "display": (src.get("added_at") or "")[:10] or "snapshot"}]
    if tile.get("chart") == "table" or not src.get("x"):
        cols = src.get("columns") or [{"key": k, "label": k} for k in (rows[0] if rows else {})]
        first = cols[0]["key"] if cols else ""
        rows = rating_sorted(rows, first)
        out_cols = []
        for i, c in enumerate(cols):
            numeric = any(isinstance(r.get(c["key"]), (int, float)) and not isinstance(r.get(c["key"]), bool) for r in rows)
            unit = unit_of(c["key"], c["label"]) if numeric and i else "text"
            out_cols.append({"key": c["key"], "label": fmt.axis_title(c["label"], unit) if unit not in ("text", "count") else c["label"], "unit": unit})
        table_rows = [{c["key"]: (fmt.round_for(r.get(c["key"]), c["unit"]) if c["unit"] != "text" else r.get(c["key"])) for c in out_cols} for r in rows]
        return {"default_title": "From the assistant", "figure": None, "table": {"columns": out_cols, "rows": table_rows}, "trace": trace,
                "badges": badge, "size": "wide" if len(out_cols) > 4 else "half", "unit": ""}
    x, ys, y2 = src["x"], list(src.get("y") or []), src.get("y2") or ""
    labels = src.get("labels") or {}
    rows = rating_sorted(rows, x)
    names = [str(r.get(x)) for r in rows]
    kind = tile.get("chart") or "bar"
    h = kind == "hbar"
    unit0 = unit_of(ys[0], labels.get(ys[0], "")) if ys else "score"
    data = []
    for i, y in enumerate(ys):
        u = unit_of(y, labels.get(y, ""))
        vals = [fmt.round_for(r.get(y), u) for r in rows]
        lab = labels.get(y) or y
        if kind == "line":
            tr: dict[str, Any] = {"type": "scatter", "mode": "lines+markers", "x": names, "y": vals, "line": {"color": V5_PALETTE[i % 12]}}
        else:
            tr = {"type": "bar", "orientation": "h" if h else "v", ("y" if h else "x"): names, ("x" if h else "y"): vals,
                  "marker": {"color": V5_PALETTE[i % 12]}}
        tr.update(name=lab, hovertemplate=f"%{{{'y' if h else 'x'}}}<br>{lab}: {fmt.hover(u, 'x' if h else 'y')}<extra></extra>")
        data.append(tr)
    lay: dict[str, Any] = {"margin": {"l": 140 if h else 56, "r": 48 if y2 else 16, "t": 12, "b": 48}, "paper_bgcolor": "rgba(0,0,0,0)",
                           "plot_bgcolor": "rgba(0,0,0,0)", "font": {"family": "Inter, system-ui, sans-serif", "size": 11, "color": "#334155"},
                           "showlegend": len(ys) > 1 or bool(y2), "legend": {"orientation": "h", "y": 1.12, "x": 0},
                           "barmode": "stack" if kind == "stacked" else "group", "hoverlabel": {"bgcolor": "#fff"}}
    val_ax = {"title": {"text": fmt.axis_title(labels.get(ys[0]) or ys[0], unit0)}, "tickformat": fmt.tickformat(unit0),
              "ticksuffix": fmt.axis_suffix(unit0), "gridcolor": "rgba(100,116,139,0.15)", "zeroline": False}
    cat_ax = {"title": {"text": labels.get(x) or x}, "automargin": True, "type": "category", "categoryorder": "array", "categoryarray": names}
    if h:
        lay["xaxis"], lay["yaxis"] = val_ax, {**cat_ax, "autorange": "reversed", "title": {"text": ""}}
    else:
        lay["xaxis"], lay["yaxis"] = cat_ax, val_ax
    if y2 and not h:
        u2 = unit_of(y2, labels.get(y2, ""))
        lab2 = labels.get(y2) or y2
        data.append({"type": "scatter", "mode": "lines+markers", "x": names, "y": [fmt.round_for(r.get(y2), u2) for r in rows], "yaxis": "y2",
                     "name": lab2, "line": {"color": V5_PALETTE[len(ys) % 12]},
                     "hovertemplate": f"%{{x}}<br>{lab2}: {fmt.hover(u2, 'y')}<extra></extra>"})
        lay["yaxis2"] = {"title": {"text": fmt.axis_title(lab2, u2)}, "overlaying": "y", "side": "right", "tickformat": fmt.tickformat(u2),
                         "ticksuffix": fmt.axis_suffix(u2), "showgrid": False}
    cols = [{"key": x, "label": labels.get(x) or x, "unit": "text"}] + [
        {"key": y, "label": fmt.axis_title(labels.get(y) or y, unit_of(y, labels.get(y, ""))), "unit": unit_of(y, labels.get(y, ""))}
        for y in [*ys, *([y2] if y2 else [])]]
    table_rows = [{c["key"]: (fmt.round_for(r.get(c["key"]), c["unit"]) if c["unit"] != "text" else r.get(c["key"])) for c in cols} for r in rows]
    return {"default_title": "From the assistant", "figure": {"data": data, "layout": lay}, "table": {"columns": cols, "rows": table_rows},
            "trace": trace, "badges": badge, "unit": unit0}


def add(spec: dict[str, Any], op: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """apply_op for {"op": "add_block", "block": {...}, "sql"?, "question"?, "after"?: tile_id | "end" | "start"}."""
    s = copy.deepcopy(spec)
    tile = make_tile(op.get("block") or {}, str(op.get("sql") or ""), str(op.get("question") or ""), str(s.get("period") or ""))
    after = str(op.get("after") or "end")
    tiles = s.get("tiles") or []
    if after == "start":
        pos = 0
    elif after == "end":
        pos = len(tiles)
    else:
        idx = next((i for i, t in enumerate(tiles) if t.get("id") == after), None)
        if idx is None:
            raise LensError(f"{after} is not a tile of this lens.")
        pos = idx + 1
    tiles.insert(pos, tile)
    s["tiles"] = tiles
    return s, f"Added {tile['title']} from the assistant"
