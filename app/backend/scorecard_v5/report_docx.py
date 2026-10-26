"""The Word validation report, in the CreditProbe house style (backend/house_style, docs/v5/HOUSE_STYLE.md).

Cover page; 1 Executive summary; 2 Scope, data and method; 3 Discrimination; 4 Calibration and accuracy;
5 Stability; 6 Variables; 7 Overrides; 8 Findings and recommended actions; 9 Review and sign-off;
Appendix A Thresholds. Every figure and verdict is the validation's own; charts are drawn from the same
figure dicts the browser plots.
"""
from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from backend.house_style import Meta, docx as hd  # noqa: E402
from backend.scorecard_v5 import charts, engine  # noqa: E402

CONCLUSIONS = {"fit": "Fit for use", "conditions": "Fit for use with conditions", "not_fit": "Not fit for use"}
VERDICT_WORD = {"green": "GREEN", "amber": "AMBER", "red": "RED", "na": "N/A"}


def fmtv(value: Any, fmt: str) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return VERDICT_WORD.get(value, value) if fmt == "rag" else value
    v = float(value)
    return {"pct": f"{v:.1%}", "pct2": f"{v:.2%}", "num": f"{v:,.2f}", "num4": f"{v:.4f}", "int": f"{v:,.0f}"}.get(fmt, f"{v:,.2f}")


def _wrap_tick(label: Any, width: int) -> str:
    return charts.wrap(label, width).replace("<br>", "\n")


def figure_png(fig: dict[str, Any], width_in: float = 6.4, height_in: float | None = None) -> bytes:
    """Draw a figure dict (bar, scatter, heatmap) as a PNG, following the same layout rules as the browser:
    horizontal bars for variable charts with wrapped labels, thresholds as full-height or full-width lines,
    the legend above the plot."""
    hd.chart_style()
    traces = fig["data"]
    lay = fig["layout"]
    bars = [t for t in traces if t["type"] == "bar"]
    horiz = any(t.get("orientation") == "h" for t in bars)
    heat = next((t for t in traces if t["type"] == "heatmap"), None)
    if height_in is None:
        n = len(bars[0]["y"]) if horiz else len(heat["y"]) if heat else 0
        height_in = max(3.1, min(6.0, 0.9 + n * (0.24 if len(bars) > 1 and lay.get("barmode") == "group" else 0.2))) if (horiz or heat) else 3.1
    f, ax = plt.subplots(figsize=(width_in, height_in), dpi=170)
    title = (lay.get("title") or {}).get("text", "")
    if heat:
        z = np.asarray(heat["z"], dtype=float)
        im = ax.imshow(z, aspect="auto", cmap="RdYlGn_r" if heat.get("zmin") == 0 else "RdBu_r", vmin=heat.get("zmin"), vmax=heat.get("zmax"))
        ax.set_xticks(range(len(heat["x"])))
        many = len(heat["x"]) > 8
        ax.set_xticklabels([_wrap_tick(x, 14) for x in heat["x"]], rotation=45 if many else 0, ha="right" if many else "center", fontsize=6)
        ax.set_yticks(range(len(heat["y"])))
        ax.set_yticklabels([_wrap_tick(y, 24) for y in heat["y"]], fontsize=6.5)
        ax.grid(False)
        f.colorbar(im, ax=ax, shrink=0.8)
    else:
        group = lay.get("barmode") == "group" and len(bars) > 1
        cats: list[str] = []
        for k, t in enumerate(bars):
            cats = [str(c) for c in (t["y"] if horiz else t["x"])]
            vals = [np.nan if v is None else v for v in (t["x"] if horiz else t["y"])]
            idx = np.arange(len(cats))
            w = 0.8 / len(bars) if group else 0.7
            off = (k - (len(bars) - 1) / 2) * w if group else 0
            col = t.get("marker", {}).get("color") or f"C{k}"
            (ax.barh if horiz else ax.bar)(idx + off, vals, w, color=col, label=t.get("name"))
            if k == 0 or group:
                if horiz:
                    ax.set_yticks(idx)
                    ax.set_yticklabels([_wrap_tick(c, 24) for c in cats], fontsize=6.5)
                else:
                    ax.set_xticks(idx)
                    ax.set_xticklabels([_wrap_tick(c, 16) for c in cats], fontsize=6.5,
                                       rotation=45 if len(cats) > 8 else 0, ha="right" if len(cats) > 8 else "center")
        cat_axis = bool(bars)
        bar_x = [str(c) for c in bars[0]["x"]] if bars and not horiz else []
        for t in traces:
            if t["type"] != "scatter":
                continue
            line = t.get("line", {})
            kw = {"color": line.get("color"), "label": t.get("name"), "linewidth": 1.4}
            if line.get("dash"):
                kw["linestyle"] = "--"
            x, y = t["x"], t["y"]
            if t.get("hoverinfo") == "skip" and len(x) == 2 and len(y) == 2 and (x[0] == x[1] or y[0] == y[1]):
                # a threshold: a full-height line on a horizontal chart, a full-width line otherwise
                (ax.axvline(x[0], **kw) if x[0] == x[1] and not isinstance(x[0], str) else ax.axhline(y[0], **kw))
                continue
            mode = t.get("mode", "lines")
            xs = x
            if cat_axis and x and isinstance(x[0], str) and not horiz:
                xs = np.array([bar_x.index(str(v)) if str(v) in bar_x else i for i, v in enumerate(x)])
            elif x and isinstance(x[0], str):
                xs = np.arange(len(x))
            if "lines" in mode:
                ax.plot(xs, y, **kw)
            if "markers" in mode:
                mk = t.get("marker", {})
                ax.scatter(xs, y, c=mk.get("color"), s=18, zorder=3)
                ey = t.get("error_y")
                if ey:
                    ax.errorbar(xs, y, yerr=[ey["arrayminus"], ey["array"]], fmt="none", ecolor="#0B2A4A", elinewidth=0.8, capsize=2, zorder=2)
            if not cat_axis and x and isinstance(x[0], str):
                step = max(len(x) // 10, 1)
                ax.set_xticks(xs[::step])
                ax.set_xticklabels([str(x[i]) for i in range(0, len(x), step)], rotation=45, ha="right", fontsize=6.5)
        if horiz:
            # Plotly draws the first category at the bottom unless the axis is reversed; matplotlib does the same.
            if (lay.get("yaxis") or {}).get("autorange") == "reversed":
                ax.invert_yaxis()
            ax.grid(axis="y", visible=False)
        xaxis, yaxis = lay.get("xaxis") or {}, lay.get("yaxis") or {}
        for axis, fmt in ((ax.yaxis, yaxis.get("tickformat", "")), (ax.xaxis, xaxis.get("tickformat", ""))):
            if fmt.endswith("%"):
                axis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0 if ".0" in fmt else 1))
        ax.set_xlabel((xaxis.get("title") or {}).get("text", ""), fontsize=7)
        ax.set_ylabel((yaxis.get("title") or {}).get("text", ""), fontsize=7)
        named = [t for t in traces if t.get("name") and t["type"] != "heatmap"]
        if len(named) > 1:
            ax.legend(fontsize=6.5, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=min(len(named), 4), frameon=False, borderaxespad=0.3)
    ax.set_title(title, loc="left", fontsize=8.5, pad=18 if not heat and len([t for t in traces if t.get("name")]) > 1 else 6)
    f.tight_layout()
    buf = io.BytesIO()
    f.savefig(buf, format="png")
    plt.close(f)
    return buf.getvalue()


def _tests_table(doc, sec: dict[str, Any]) -> None:
    rows = [[x["label"], fmtv(x["value"], x["format"]) if x["format"] != "text" else x["value"], x["threshold"], VERDICT_WORD[x["status"]], x["comment"]] for x in sec["tests"]]
    hd.table(doc, ["Test", "Value", "Threshold", "Verdict", "Reading"], rows, widths=[3.6, 2.0, 3.6, 1.6, 6.2], right_from=99, size=8)


def _table(doc, t: dict[str, Any], limit: int = 40) -> None:
    cols = t["columns"]
    rows = [[fmtv(r.get(c["key"]), c["format"]) if c["format"] != "text" else r.get(c["key"], "") for c in cols] for r in t["rows"][:limit]]
    hd.para(doc, f"**{t['title']}**", size=9.5)
    hd.table(doc, [c["label"] for c in cols], rows, right_from=None)
    if t.get("note"):
        hd.note(doc, t["note"])


def build(v: dict[str, Any], *, generated_by: str = "", reference: str = "") -> bytes:
    res = v["result"]
    sc = res["scorecard"]
    plan = res["plan"]
    s = res["summary"]
    smp = res["sample"]
    meta = Meta(title=f"{sc['name']} v{sc['version']}: validation", book=sc["book"], period=plan["as_of"],
                subject=f"{sc['segment']} · {sc['type']} scorecard", generated_by=generated_by, reference=reference or v["validation_id"])
    doc = hd.document(meta, kind="Scorecard validation report", subtitle=f"{sc['name']} v{sc['version']} · as of {plan['as_of']}",
                      details=[("Scorecard", f"{sc['scorecard_id']} · {sc['name']} v{sc['version']}"), ("Monitoring window", f"{plan['monitoring'][0]} to {plan['monitoring'][1]}"),
                               ("Outcome", "Default within 12 months")])
    review = v["review"]
    concl = CONCLUSIONS.get(review.get("conclusion", ""), "")
    hd.heading(doc, "1. Executive summary")
    overall = VERDICT_WORD[s["overall"]]
    hd.key_figures(doc, [("Overall verdict", overall), ("Green", str(s["counts"]["green"])), ("Amber", str(s["counts"]["amber"])), ("Red", str(s["counts"]["red"])),
                         ("Tests run", str(s["tests"])), ("Reviewer conclusion", concl or "Pending")], per_row=3)
    heads = {x["id"]: x for sec in res["sections"] for x in sec["tests"]}
    para = [f"The {sc['name']} (version {sc['version']}) was validated as of {plan['as_of']} against its development sample ({smp['development']['from']} to {smp['development']['to']}) "
            f"and a monitoring sample of {smp['monitoring']['n']:,} observations with {smp['monitoring']['defaults']:,} defaults ({smp['monitoring']['from']} to {smp['monitoring']['to']}). "
            f"{s['counts']['green']} tests are green, {s['counts']['amber']} amber and {s['counts']['red']} red."]
    if "gini" in heads:
        para.append(f"Discrimination is {heads['gini']['status']}: {heads['gini']['comment']}")
    if "oe_ratio" in heads:
        para.append(f"Calibration is {heads['oe_ratio']['status']} on the overall rate: {heads['oe_ratio']['comment']}")
    if "psi" in heads:
        para.append(f"Stability: {heads['psi']['comment']}")
    for p in para:
        hd.para(doc, p)
    if res["findings"]:
        hd.para(doc, "**Findings that need action**", size=10)
        hd.bullets(doc, [f"**{f['label']}** ({VERDICT_WORD[f['status']]}). {f['text']}" for f in res["findings"][:8]])
    else:
        hd.para(doc, "No test is amber or red.")
    hd.para(doc, f"**Reviewer conclusion:** {concl or 'pending review'}." + (f" {review.get('note', '')}" if review.get("note") else ""))
    hd.heading(doc, "2. Scope, data and method")
    hd.table(doc, ["Item", "Detail"], [
        ["Scorecard", f"{sc['name']} v{sc['version']} ({sc['scorecard_id']}), {sc['type']} scorecard for the {sc['segment']} segment"],
        ["Purpose", sc["description"]], ["Book and key", f"{sc['book']} book; keyed to {sc['unit_key'].replace('_', ' ')} and {sc['owner_key'].replace('_', ' ')}"],
        ["Outcome", "Default within 12 months of the scoring period"],
        ["Development sample", f"{smp['development']['from']} to {smp['development']['to']}: {smp['development']['n']:,} observations, {smp['development']['defaults']:,} defaults"],
        ["Monitoring sample", f"{smp['monitoring']['from']} to {smp['monitoring']['to']}: {smp['monitoring']['n']:,} observations, {smp['monitoring']['defaults']:,} defaults"],
        ["As-of period", f"{plan['as_of']}: {smp['as_of']['n']:,} observations"],
        ["Outcomes final up to", smp["last_matured"] + (f"; open periods ({', '.join(smp['open_periods'][:3])}{'…' if len(smp['open_periods']) > 3 else ''}) enter the stability tests only" if smp["open_periods"] else "")],
        ["Segment cut", plan["segment_by"].replace("_", " ")],
        ["Variables", ", ".join(x["label"] for x in sc["variables"])],
    ], right_from=99)
    hd.para(doc, "Outcome tests use only periods whose 12-month window has closed. Stability tests compare every period up to the as-of with the development sample. "
                 "Each test carries a stated threshold (Appendix A) and a green, amber or red verdict; the verdict is also written as a word.")
    for no, sec in enumerate(res["sections"], 3):
        hd.heading(doc, f"{no}. {sec['title']}")
        _tests_table(doc, sec)
        for t in sec["tables"][:3]:
            _table(doc, t)
        n = 0
        for ch in sec["charts"]:
            if ch["id"].startswith("woe_") and n >= 4:
                continue
            n += ch["id"].startswith("woe_")
            hd.figure(doc, figure_png(ch["figure"]), width_cm=15.5, caption=f"{ch['title']}. {ch.get('note', '')}".strip())
            doc.paragraphs[-2].paragraph_format.keep_with_next = True      # the caption stays with its chart
    hd.heading(doc, f"{len(res['sections']) + 3}. Findings and recommended actions")
    if res["findings"]:
        hd.table(doc, ["Finding", "Verdict", "What it shows", "Recommended action"],
                 [[f["label"], VERDICT_WORD[f["status"]], f["text"], f["action"]] for f in res["findings"]], widths=[3.5, 1.6, 6.0, 5.9], right_from=99, size=8)
    else:
        hd.para(doc, "There are no findings: every test is green or not applicable.")
    hd.heading(doc, f"{len(res['sections']) + 4}. Review and sign-off")
    hd.table(doc, ["Item", "Record"], [["Review status", "Reviewed" if review.get("status") == "reviewed" else "Pending review"],
                                         ["Conclusion", concl or "—"], ["Note", review.get("note") or "—"], ["Reviewer", review.get("reviewer") or "—"],
                                         ["Reviewed on", (review.get("at") or "—")[:10] if isinstance(review.get("at"), str) else "—"]], right_from=99)
    hd.para(doc, "Approved by: ______________________    Date: ______________")
    hd.page_break(doc)
    hd.heading(doc, "Appendix A. Thresholds applied")
    th = res["thresholds"]
    hd.table(doc, ["Test", "Verdict rule"], [[x["label"], x["text"]] for x in th.values()], right_from=99)
    return hd.to_bytes(doc)
