/**
 * Plotly figures for the small bar charts the app used to draw with CSS widths (R12: every chart through the one
 * Plotly surface, `components/v5/ews/plot.tsx`). Pure TypeScript: the figure is data, the surface themes it.
 *
 * - `hbarFigure`: a horizontal bar list (one row per label, first label on top), the formatted value the UI shows
 *   printed beside each bar and used as the hover.
 * - `shareBarFigure`: one 100% composition bar (stacked horizontal segments), each segment hovering its own
 *   formatted share.
 */

import { TONE, type Figure } from "@/lib/plotly-theme";

export interface BarFigure { data: Figure[]; layout: Figure; height: number }

/** Row height (px) of a horizontal bar list, and the room above/below for the axis. */
const ROW = 22;

/** A tick label short enough to leave the bars room (the hover carries the full label). */
const short = (label: string, max = 28) => (label.length > max ? `${label.slice(0, max - 1)}\u2026` : label);

export function hbarFigure({ labels, values, text, color = TONE.accent, customdata, signed = false, showText = true, xTitle, base }: {
  labels: string[];
  values: number[];
  /** The formatted value the UI shows for each bar (printed beside the bar and used as the hover). */
  text: string[];
  /** One colour, or one per bar. */
  color?: string | string[];
  /** Passed back to `onPointClick` for a clicked bar. */
  customdata?: unknown[];
  /** Draw negative values to the left of zero (default: bar length is the absolute value). */
  signed?: boolean;
  showText?: boolean;
  xTitle?: string;
  /** Where each bar starts (a timeline / gantt: start offset, `values` the duration). */
  base?: number[];
}): BarFigure {
  const x = signed ? values : values.map((v) => Math.abs(v));
  const data: Figure[] = [{
    // Rows are positions, not categories, so two rows with the same label stay two bars.
    type: "bar", orientation: "h", y: labels.map((_, i) => i), x, text, customdata, hovertext: labels,
    textposition: showText ? "outside" : "none", cliponaxis: false,
    textfont: { size: 11, color: TONE.text },
    marker: { color },
    hovertemplate: "%{hovertext}: %{text}<extra></extra>",
    ...(base ? { base } : {}),
  }];
  const layout: Figure = {
    showlegend: false, hovermode: "closest", bargap: 0.35,
    margin: { l: 8, r: showText ? 64 : 12, t: 4, b: xTitle ? 32 : 4 },
    xaxis: { showticklabels: Boolean(xTitle), zeroline: true, showgrid: false, fixedrange: true, ...(xTitle ? { title: xTitle } : {}) },
    yaxis: { autorange: "reversed", fixedrange: true, showgrid: false, zeroline: false, ticksuffix: "  ",
             tickmode: "array", tickvals: labels.map((_, i) => i), ticktext: labels.map(short) },
  };
  return { data, layout, height: Math.max(60, labels.length * ROW + 8 + (xTitle ? 28 : 0)) };
}

export function shareBarFigure({ segments, height = 40, showLegend = false, showText = false }: {
  /** `outline`: a segment that needs flagging (over a concentration limit) gets this border colour. */
  segments: { label: string; value: number; color: string; text: string; outline?: string }[];
  height?: number;
  showLegend?: boolean;
  /** Print each segment's text inside it (where it fits). */
  showText?: boolean;
}): BarFigure {
  const data: Figure[] = segments.map((s) => ({
    type: "bar", orientation: "h", name: s.label, y: [""], x: [s.value], text: [s.text],
    textposition: showText ? "inside" : "none", insidetextanchor: "middle",
    textfont: { size: 10, color: "#ffffff" },
    marker: { color: s.color, line: s.outline ? { color: s.outline, width: 2 } : { color: TONE.surface, width: 1 } },
    hovertemplate: `${s.label.replace(/[%{}]/g, "")}: %{text}<extra></extra>`,
  }));
  const layout: Figure = {
    barmode: "stack", showlegend: showLegend, hovermode: "closest", bargap: 0.1,
    margin: { l: 0, r: 0, t: 0, b: showLegend ? 4 : 0 },
    legend: { orientation: "h", x: 0, y: -0.15, yanchor: "top" },
    xaxis: { visible: false, fixedrange: true },
    yaxis: { visible: false, fixedrange: true },
  };
  return { data, layout, height: showLegend ? height + 28 : height };
}
