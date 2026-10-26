"""A Plotly figure drawn as a PNG for the Word export (bar, line/scatter, pie/donut, heatmap, waterfall).

The screen draws the Plotly JSON itself; Word needs a picture, and the container has no Plotly image engine, so
the common trace types are redrawn with matplotlib in the house palette. A caller may send its own PNG instead.
"""
from __future__ import annotations

import base64
import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PALETTE = ["#1F4E6B", "#2E7D9A", "#E0A100", "#C2410C", "#5B8C5A", "#7C5CBF", "#9AA5B1", "#D9467A"]


def _title(fig: dict[str, Any]) -> str:
    t = (fig.get("layout") or {}).get("title")
    if isinstance(t, dict):
        return str(t.get("text") or "")
    return str(t or "")


def _axis_title(layout: dict[str, Any], key: str) -> str:
    a = layout.get(key) or {}
    t = a.get("title")
    return str(t.get("text") if isinstance(t, dict) else (t or ""))


def png(fig: dict[str, Any], title: str = "") -> bytes | None:
    """The figure as PNG bytes, or None when it holds nothing drawable."""
    data = [t for t in (fig.get("data") or []) if isinstance(t, dict)]
    if not data:
        return None
    layout = fig.get("layout") or {}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})
    f, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    drawn = False
    try:
        kinds = {t.get("type", "scatter") for t in data}
        if kinds & {"pie"}:
            t = next(x for x in data if x.get("type") == "pie")
            vals = [float(v or 0) for v in t.get("values", [])]
            labels = [str(v) for v in t.get("labels", [])]
            if sum(vals) > 0:
                ax.pie(vals, labels=labels, colors=PALETTE[: len(vals)] * 3, autopct="%1.0f%%",
                       wedgeprops={"width": 0.45 if t.get("hole") else 1, "edgecolor": "white"}, textprops={"fontsize": 8})
                ax.axis("equal")
                drawn = True
        elif kinds & {"heatmap"}:
            t = next(x for x in data if x.get("type") == "heatmap")
            z = [[float(v) if v is not None else 0.0 for v in row] for row in t.get("z", [])]
            if z:
                im = ax.imshow(z, cmap="Blues", aspect="auto")
                xs, ys = t.get("x") or list(range(len(z[0]))), t.get("y") or list(range(len(z)))
                ax.set_xticks(range(len(xs)), [str(x) for x in xs], rotation=40, ha="right")
                ax.set_yticks(range(len(ys)), [str(y) for y in ys])
                f.colorbar(im, ax=ax, shrink=0.8)
                drawn = True
        else:
            ax_main = ax
            ax2 = ax.twinx() if any(t.get("yaxis") == "y2" for t in data) else None
            bars = [t for t in data if t.get("type") in ("bar", "waterfall")]
            nb = max(len(bars), 1)
            bi = 0
            for i, t in enumerate(data):
                ax = ax2 if (ax2 is not None and t.get("yaxis") == "y2") else ax_main
                colour = ((t.get("marker") or {}).get("color") if isinstance((t.get("marker") or {}).get("color"), str)
                          else None) or PALETTE[i % len(PALETTE)]
                name = str(t.get("name") or "")
                if t.get("type") in ("bar", "waterfall"):
                    horiz = t.get("orientation") == "h"
                    cats = t.get("y") if horiz else t.get("x")
                    vals = t.get("x") if horiz else t.get("y")
                    if not cats or not vals:
                        continue
                    cats = [str(c) for c in cats]
                    vals = [float(v or 0) for v in vals]
                    pos = [k + (bi - (nb - 1) / 2) * (0.8 / nb) for k in range(len(cats))]
                    if horiz:
                        ax.barh(pos, vals, height=0.8 / nb, color=colour, label=name or None)
                        ax.set_yticks(range(len(cats)), cats)
                        ax.invert_yaxis()
                    else:
                        ax.bar(pos, vals, width=0.8 / nb, color=colour, label=name or None)
                        ax.set_xticks(range(len(cats)), cats, rotation=30 if len(cats) > 5 else 0,
                                      ha="right" if len(cats) > 5 else "center")
                    bi += 1
                    drawn = True
                else:
                    xs, ys = t.get("x") or [], t.get("y") or []
                    if not ys:
                        continue
                    xs = [str(x) for x in xs] if xs else list(range(len(ys)))
                    ys = [float(v) if v is not None else float("nan") for v in ys]
                    mode = str(t.get("mode") or "lines")
                    ax.plot(xs, ys, color=colour, label=name or None, linewidth=2,
                            marker="o" if "markers" in mode else None, markersize=3,
                            linestyle="--" if (t.get("line") or {}).get("dash") else "-")
                    drawn = True
            ax = ax_main
            if ax2 is not None:
                ax2.set_ylabel(_axis_title(layout, "yaxis2"))
                ax2.spines[["top"]].set_visible(False)
                h1, l1 = ax.get_legend_handles_labels()
                h2, l2 = ax2.get_legend_handles_labels()
                ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7.5, loc="upper left")
            if drawn:
                ax.grid(axis="y", color="#E5E8EC", linewidth=0.8)
                ax.spines[["top"] if ax2 is not None else ["top", "right"]].set_visible(False)
                ax.set_xlabel(_axis_title(layout, "xaxis"))
                ax.set_ylabel(_axis_title(layout, "yaxis"))
                if any(t.get("name") for t in data) and len(data) > 1 and ax2 is None:
                    ax.legend(frameon=False, fontsize=7.5)
                if len(ax.get_xticklabels()) > 12:
                    for k, lab in enumerate(ax.get_xticklabels()):
                        lab.set_visible(k % max(1, len(ax.get_xticklabels()) // 10) == 0)
        if not drawn:
            return None
        head = title or _title(fig)
        if head:
            ax.set_title(head, loc="left", fontsize=10, fontweight="bold", color="#1B2430")
        f.tight_layout()
        buf = io.BytesIO()
        f.savefig(buf, format="png")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - a chart that cannot be drawn is listed, never fails the export
        return None
    finally:
        plt.close(f)


def block_png(block: dict[str, Any]) -> bytes | None:
    if block.get("png_base64"):
        try:
            return base64.b64decode(block["png_base64"])
        except (ValueError, TypeError):
            pass
    return png(block.get("figure") or {}, block.get("title") or "")
