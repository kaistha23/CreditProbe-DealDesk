"""One chart style for every Scorecard Validation figure (PLAN_R4 B3).

The engine builds plain Plotly figure dicts; `style_result` puts every figure of a result into the house
chart style, so the browser, Playbook and the Word report (report_docx.figure_png) all draw the same spec:

  * variable and category charts (IV, VIF, CSI by variable, WoE bins, Gini by segment, override outcome)
    are horizontal bars, so a variable name reads on one line or wraps, never rotated or clipped;
  * long category labels wrap (ticktext with line breaks; the data keeps the full name for hover);
  * every axis has automargin, so the left margin grows to fit the labels;
  * the legend sits above the plot area, under the title, so it never overlaps tick labels;
  * a threshold line on a horizontal chart is a vertical line spanning the full plot height;
  * one height rule (more categories, taller chart) and one colour per sample (development grey,
    monitoring blue).

Idempotent: styling a styled figure changes nothing, so stored results are styled again when read.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

GREY, BLUE = "#8A94A6", "#2F80ED"

# Charts whose categories are variables, bins, segments or decisions: drawn as horizontal bars.
HORIZONTAL = {"iv_bar", "vif", "csi_bar", "gini_segment", "ks_segment", "ovr_outcome"}
# Horizontal charts whose category order is meaningful (bins, decisions): kept as built. WoE bins too.
KEEP_ORDER = {"ovr_outcome"}
HEATMAPS = {"csi_heat", "corr"}
# Titles that carried an explanation in brackets: the explanation belongs in the chart's (i) note.
TITLES = {"gini_trend": ("Gini by period", "Grey bars are development periods."),
          "ks_trend": ("KS by period", "Grey bars are development periods."),
          "csi_heat": ("CSI by variable and period", "Development periods are the reference, so their CSI is zero.")}
# Notes that explain a chart's colours: shown behind the chart's (i), and in the Word caption.
NOTES = {"gini_segment": "Bar colour is the verdict; grey segments have fewer than 30 defaults and carry no verdict.",
         "ks_segment": "Grey segments have fewer than 30 defaults; their KS is shown for reference only.",
         "csi_bar": "Bar colour is the verdict: green up to 0.10, amber up to 0.25, red above.",
         "vif": "Bar colour is the verdict: green up to 5, amber up to 10, red above."}
PERIOD = re.compile(r"^\d{4}(-\d{2}|Q\d)$")
BASE_HEIGHT = 320
WRAP_Y = 24     # characters per line for category labels on the y axis
WRAP_X = 14     # characters per line for category labels on the x axis of a heatmap


def is_horizontal(chart_id: str) -> bool:
    return chart_id in HORIZONTAL or chart_id.startswith("woe_")


def wrap(label: Any, width: int) -> str:
    """Break a label into lines of at most `width` characters at spaces (a long word stays whole)."""
    text = str(label)
    if "<br>" in text or len(text) <= width:
        return text
    lines, cur = [], ""
    for word in re.split(r"\s+", text.strip()):
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return "<br>".join(lines)


def _is_threshold(t: dict[str, Any]) -> bool:
    if t.get("type") != "scatter" or t.get("hoverinfo") != "skip":
        return False
    x, y = t.get("x") or [], t.get("y") or []
    return len(x) == 2 and len(y) == 2 and (y[0] == y[1] or x[0] == x[1])


def _cats(fig: dict[str, Any]) -> list[Any]:
    bars = [t for t in fig["data"] if t.get("type") == "bar"]
    if not bars:
        return []
    b = bars[0]
    return list(b.get("y") if b.get("orientation") == "h" else b.get("x")) or []


def _to_horizontal(chart_id: str, fig: dict[str, Any]) -> None:
    """Bars along the y axis, first category at the top (a reversed axis, so in a group the first trace,
    development, sits above the second, monitoring, as in the legend)."""
    data, lay = fig["data"], fig["layout"]
    bars = [t for t in data if t.get("type") == "bar"]
    if not bars or (lay.get("yaxis") or {}).get("autorange") == "reversed":
        return
    was_h = all(t.get("orientation") == "h" for t in bars)
    for t in bars:
        if t.get("orientation") != "h":
            t["x"], t["y"] = t.get("y"), t.get("x")
            t["orientation"] = "h"
            if "hovertemplate" in t:
                t["hovertemplate"] = t["hovertemplate"].replace("%{x", "%{_X").replace("%{y", "%{x").replace("%{_X", "%{y")
    n = len(bars[0]["y"])
    if was_h:
        # built bottom-up (largest last): the reversed axis wants the order flipped
        order = list(range(n))[::-1]
    elif chart_id.startswith("woe_") or chart_id in KEEP_ORDER:
        order = list(range(n))
    else:
        # ranked: the largest value of the last bar trace (monitoring where there are two) at the top
        key = bars[-1]
        order = sorted(range(n), key=lambda i: -(key["x"][i] or 0))
    for t in bars:
        for k in ("x", "y"):
            t[k] = [t[k][i] for i in order]
        mk = t.get("marker") or {}
        if isinstance(mk.get("color"), list) and len(mk["color"]) == n:
            mk["color"] = [mk["color"][i] for i in order]
    for t in data:
        if _is_threshold(t) and t.get("yaxis") != "y2":
            v = t["y"][0] if t["y"][0] == t["y"][1] else t["x"][0]
            t["x"], t["y"], t["yaxis"] = [v, v], [0, 1], "y2"
    xa, ya = dict(lay.get("xaxis") or {}), dict(lay.get("yaxis") or {})
    # The value axis keeps the value format and title; the category axis has no title (the labels say it).
    if was_h:
        vfmt, vtitle = xa.get("tickformat"), (xa.get("title") or {}).get("text") or ""
    else:
        vfmt, vtitle = ya.get("tickformat"), (ya.get("title") or {}).get("text") or ""
    if chart_id.startswith("woe_"):
        vtitle = "WoE"
    lay["xaxis"] = {"title": {"text": vtitle}, **({"tickformat": vfmt} if vfmt else {})}
    lay["yaxis"] = {"title": {"text": ""}, "autorange": "reversed"}
    lay["yaxis2"] = {"overlaying": "y", "range": [0, 1], "visible": False, "fixedrange": True}


def style_figure(chart_id: str, fig: dict[str, Any]) -> dict[str, Any]:
    """The figure in the house chart style (a new dict; the input is not changed)."""
    fig = copy.deepcopy(fig)
    data, lay = fig["data"], fig["layout"]
    if is_horizontal(chart_id):
        _to_horizontal(chart_id, fig)
    # one colour per sample
    for t in data:
        if t.get("name") == "Monitoring" and t.get("type") in ("bar", "scatter"):
            if t["type"] == "bar":
                t.setdefault("marker", {})["color"] = BLUE
            else:
                t.setdefault("line", {})["color"] = BLUE
    # title: short, the explanation moves to the chart note
    title = (lay.get("title") or {}).get("text", "")
    if chart_id in TITLES:
        title = TITLES[chart_id][0]
    xa = {**(lay.get("xaxis") or {}), "automargin": True}
    ya = {**(lay.get("yaxis") or {}), "automargin": True, "zeroline": False}
    xa.pop("tickangle", None)
    ya.pop("tickangle", None)
    cats = _cats(fig)
    heat = next((t for t in data if t.get("type") == "heatmap"), None)
    if is_horizontal(chart_id) and cats:
        ya.update({"tickmode": "array", "tickvals": cats, "ticktext": [wrap(c, WRAP_Y) for c in cats]})
        xa["zeroline"] = True
        ngroups = max(1, len([t for t in data if t.get("type") == "bar"]) if lay.get("barmode") == "group" else 1)
        lines = max(len(t.split("<br>")) for t in ya["ticktext"])
        # each category row fits its bars and its wrapped label (about 15px a line at 11px)
        height = max(BASE_HEIGHT, len(cats) * max(14 * ngroups + 10, 15 * lines + 8) + 120)
    elif heat is not None:
        # first row at the top, as in a table (and in the Word report): the correlation diagonal runs top-left to bottom-right
        ya.update({"tickmode": "array", "tickvals": list(heat["y"]), "ticktext": [wrap(c, WRAP_Y) for c in heat["y"]], "autorange": "reversed"})
        if chart_id == "corr":
            xa.update({"tickmode": "array", "tickvals": list(heat["x"]), "ticktext": [wrap(c, WRAP_X) for c in heat["x"]], "tickangle": 0})
        height = max(BASE_HEIGHT + 40, len(heat["y"]) * 34 + 140)
    else:
        height = BASE_HEIGHT
    # periods (2025-01, 2024Q3) read as the tables write them, not as Plotly dates
    if not is_horizontal(chart_id) and any(isinstance(t.get("x"), list) and t["x"] and all(isinstance(v, str) and PERIOD.match(v) for v in t["x"]) for t in data):
        xa["type"] = "category"
        n = max(len(t["x"]) for t in data if isinstance(t.get("x"), list))
        if n > 8:
            # every k-th period, upright, so the labels never collide on a half-width card
            xa.update({"dtick": math.ceil(n / 7), "tickangle": 0})
    shown = [t for t in data if t.get("showlegend", True) and t.get("name") and t.get("type") != "heatmap"]
    legend = len(shown) > 1
    lay.update({
        "title": {"text": title, "x": 0, "xref": "paper", "xanchor": "left", "y": 1, "yref": "container", "yanchor": "top",
                  "pad": {"t": 10}, "font": {"size": 14}},
        "height": height,
        "margin": {"l": 8, "r": 16, "t": 76 if legend else 48, "b": 44, "pad": 4},
        "xaxis": xa, "yaxis": ya,
        "showlegend": legend,
        "legend": {"orientation": "h", "x": 0, "xanchor": "left", "y": 1.02, "yanchor": "bottom", "font": {"size": 11}, "bgcolor": "rgba(0,0,0,0)"},
        "hovermode": "closest",
    })
    if "yaxis2" in lay:
        lay["yaxis2"] = {"overlaying": "y", "range": [0, 1], "visible": False, "fixedrange": True}
    return fig


def style_chart(chart: dict[str, Any]) -> dict[str, Any]:
    out = {**chart, "figure": style_figure(chart["id"], chart["figure"])}
    why = NOTES.get(chart["id"], "")
    if chart["id"] in TITLES:
        title, why = TITLES[chart["id"]]
        out["title"] = title
    if why and why not in (out.get("note") or ""):
        out["note"] = f"{out.get('note') or ''} {why}".strip()
    return out


def style_result(result: dict[str, Any]) -> dict[str, Any]:
    """Every chart of a validation result in the house chart style (in place; returns the result)."""
    for sec in result.get("sections") or []:
        sec["charts"] = [style_chart(c) for c in sec.get("charts") or []]
    return result
