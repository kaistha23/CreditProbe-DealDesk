"""Lens exports in the house style (backend/house_style): Excel (About, KPIs, one sheet per tile) and PDF
(cover line, commentary, KPI table, every chart as an image, the top-names table). Every number is written as a
number with its unit format (Excel) or through the G5 formatter (PDF)."""
from __future__ import annotations

import io
import re
from typing import Any

from backend.house_style import ACCENT, BAND, CHART, INK, MUTED, RULE, Meta, xlsx as hx
from backend.house_style.xlsx import Col
from backend.lenses_v5 import fmt

KIND = {"sar_mn": "sar_mn", "pct": "pct", "ratio": "x", "bps": "bps", "count": "int", "days": "int", "score": "num", "text": "text"}


def _meta(lens: dict[str, Any], spec: dict[str, Any], r: dict[str, Any], by: str) -> Meta:
    return Meta(title=f"Lens: {lens['name']}", book=spec["book"], period=r["period"], subject=spec.get("scope_label", ""), generated_by=by,
                reference=lens["lens_id"])


def _sheet_name(title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title)[:28].strip() or "Tile"
    name, i = base, 2
    while name in used:
        name = f"{base[:25]} {i}"
        i += 1
    used.add(name)
    return name


def xlsx(lens: dict[str, Any], spec: dict[str, Any], r: dict[str, Any], by: str = "") -> bytes:
    meta = _meta(lens, spec, r, by)
    wb = hx.workbook(meta)
    hx.about_sheet(wb, meta, [("Lens", lens["name"]), ("Scope", spec.get("scope_label", "")), ("As of", r["period"]),
                              ("Tiles", len(r["tiles"])), ("Commentary", r["commentary"]["markdown"][:1000])])
    used = {"About"}
    hx.table_sheet(wb, _sheet_name("KPIs", used), meta, [Col("label", "Measure", "text"), Col("value", "Value", "num"), Col("unit", "Unit", "text"),
                                                         Col("change", "Change on prior period", "num"), Col("source", "Source", "text")],
                   [{"label": k["label"], "value": k["value"], "unit": fmt.UNIT_SUFFIX.get(k["unit"], "") or "count", "change": k["change"], "source": k["source"]}
                    for k in r["kpis"]])
    for t in r["tiles"]:
        tab = t.get("table")
        if not tab or not tab.get("rows"):
            continue
        cols = [Col(c["key"], c["label"], KIND.get(c.get("unit", "text"), "num")) for c in tab["columns"]]
        hx.table_sheet(wb, _sheet_name(t["title"], used), meta, cols, tab["rows"])
    return hx.to_bytes(wb)


# ------------------------------------------------------------------ figures as images (PDF, Playbook)
def figure_png(fig: dict[str, Any], title: str = "", width_in: float = 6.6, height_in: float = 3.0) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    data = fig.get("data") or []
    lay = fig.get("layout") or {}
    f, ax = plt.subplots(figsize=(width_in, height_in), dpi=150)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=7, colors="#334155")
    heat = next((d for d in data if d.get("type") == "heatmap"), None)
    pie = next((d for d in data if d.get("type") in ("pie", "treemap")), None)
    if heat:
        z = heat["z"]
        ax.imshow(z, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(heat["x"])), heat["x"], fontsize=7)
        ax.set_yticks(range(len(heat["y"])), heat["y"], fontsize=7)
        for i, row in enumerate(z):
            for j, v in enumerate(row):
                ax.text(j, i, f"{v:,.1f}", ha="center", va="center", fontsize=6.5, color=INK and "#12181F")
    elif pie:
        vals = [v or 0 for v in pie["values"]]
        ax.pie(vals, labels=pie["labels"], colors=CHART[: len(vals)] * 3, textprops={"fontsize": 7}, wedgeprops={"width": 0.45})
    else:
        bars = [d for d in data if d.get("type") == "bar"]
        horiz = any(d.get("orientation") == "h" for d in bars)
        stacked = lay.get("barmode") == "stack"
        n = len(bars)
        bottom: dict[int, float] = {}
        for i, d in enumerate(data):
            col = (d.get("marker") or {}).get("color") if isinstance((d.get("marker") or {}).get("color"), str) else CHART[i % len(CHART)]
            if d.get("type") == "bar":
                cats = d["y"] if horiz else d["x"]
                vals = [v or 0 for v in (d["x"] if horiz else d["y"])]
                pos = list(range(len(cats)))
                if horiz:
                    ax.barh(pos, vals, color=col, height=0.7)
                    ax.set_yticks(pos, [str(c)[:28] for c in cats], fontsize=7)
                    ax.invert_yaxis()
                elif stacked:
                    b = [bottom.get(j, 0) for j in pos]
                    ax.bar(pos, vals, bottom=b, color=col, label=d.get("name"), width=0.7)
                    for j, v in enumerate(vals):
                        bottom[j] = b[j] + v
                    ax.set_xticks(pos, [str(c) for c in cats], fontsize=7, rotation=30 if len(cats) > 6 else 0)
                else:
                    w = 0.8 / max(1, n)
                    ax.bar([p + i * w - 0.4 + w / 2 for p in pos], vals, width=w, color=col, label=d.get("name"))
                    ax.set_xticks(pos, [str(c)[:16] for c in cats], fontsize=7, rotation=30 if len(cats) > 6 else 0)
            else:
                ys = [v if v is not None else float("nan") for v in d.get("y", [])]
                ax.plot(d.get("x", []), ys, marker="o", markersize=3, linewidth=1.8, color=CHART[i % len(CHART)], label=d.get("name"))
                ax.tick_params(axis="x", rotation=30)
        if len(data) > 1 and any(d.get("name") for d in data):
            ax.legend(fontsize=6.5, frameon=False, loc="upper left", ncol=min(4, len(data)))
        ax.grid(axis="x" if horiz else "y", color=RULE and "#D5DCE3", linewidth=0.6)
    if title:
        ax.set_title(title, fontsize=9, loc="left", color="#12181F")
    f.tight_layout()
    buf = io.BytesIO()
    f.savefig(buf, format="png")
    plt.close(f)
    return buf.getvalue()


def pdf(lens: dict[str, Any], spec: dict[str, Any], r: dict[str, Any], by: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    meta = _meta(lens, spec, r, by)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.4 * cm, rightMargin=1.4 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
                            title=meta.title, author=by or "CreditProbe", subject="creditprobe-house-style-1")
    accent = colors.HexColor("#" + ACCENT)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, textColor=accent, spaceAfter=4)
    small = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#" + MUTED))
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#" + INK))
    cell = ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)
    story: list[Any] = [Paragraph("CREDITPROBE", small), Paragraph(lens["name"], h1), Paragraph(meta.scope_line(), small),
                        Paragraph(meta.generated_line(), small), Spacer(1, 8), Paragraph(r["commentary"]["markdown"].replace("**", ""), body), Spacer(1, 8)]
    kp = [[Paragraph(f"<b>{k['label']}</b>", cell) for k in r["kpis"][:5]], [Paragraph(k["display"], cell) for k in r["kpis"][:5]],
          [Paragraph(f"<b>{k['label']}</b>", cell) for k in r["kpis"][5:10]], [Paragraph(k["display"], cell) for k in r["kpis"][5:10]]]
    kp = [row for row in kp if row]
    if kp:
        t = Table(kp, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#" + RULE)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BAND)),
                               ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#" + BAND))]))
        story += [t, Spacer(1, 10)]
    imgs = []
    for tile in r["tiles"]:
        if tile.get("figure"):
            png = figure_png(tile["figure"], tile["title"], width_in=6.2, height_in=2.9)
            imgs.append(Image(io.BytesIO(png), width=12.4 * cm, height=5.8 * cm))
    for i in range(0, len(imgs), 2):
        row = imgs[i:i + 2] + ([Spacer(1, 1)] if len(imgs[i:i + 2]) == 1 else [])
        story.append(KeepTogether(Table([row], hAlign="LEFT", colWidths=[13.2 * cm, 13.2 * cm])))
    for tile in r["tiles"]:
        if tile["type"] == "top_names" and tile.get("table"):
            cols = tile["table"]["columns"]
            rows = [[Paragraph(f"<b>{c['label']}</b>", cell) for c in cols]]
            for row in tile["table"]["rows"][:20]:
                rows.append([Paragraph(fmt.fmt_value(row.get(c["key"]), c["unit"]) if c["unit"] != "text" else str(row.get(c["key"]) or ""), cell) for c in cols])
            t = Table(rows, hAlign="LEFT", repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), accent), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#" + RULE))]))
            rows[0] = [Paragraph(f"<font color='white'><b>{c['label']}</b></font>", cell) for c in cols]
            story += [Spacer(1, 10), Paragraph(tile["title"], ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, textColor=accent)), Spacer(1, 4), t]

    def footer(canvas, d):  # noqa: ANN001
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#" + MUTED))
        canvas.drawString(1.4 * cm, 0.7 * cm, f"CreditProbe · {lens['name']} · {r['period']} · INTERNAL")
        canvas.drawRightString(landscape(A4)[0] - 1.4 * cm, 0.7 * cm, f"Page {d.page}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
