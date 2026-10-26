/**
 * The four charts of an attention item, as Plotly figures built from the Core service's chart data
 * (`GET /api/v1/attention/charts`, backend/attention_v5). Pure functions: the figure carries exactly the API's numbers.
 *
 * Colours are fixed hex values: the attention drawer is the one place the product is deliberately vivid.
 */

export type Kind = "amount" | "share";

export interface ContribItem { name: string; id: string; from: number; to: number; change: number }
export interface ContribView { key: string; label: string; items: ContribItem[]; from: number; to: number; total_change: number }
export interface ChartsPayload {
  domain: "corporate" | "retail"; family: string; segment: string; segment_label?: string; dimension: string; dimension_label: string;
  /** "segment" (an attention item), "portfolio" (a whole-book card: no separate book line) or "component" (an ECL movement component). */
  scope?: "segment" | "portfolio" | "component";
  /** The trend's two line names; an empty book name draws the segment line alone. */
  trend_labels?: { segment: string; book: string };
  measure: string; measure_label: string; kind: Kind; unit: string; period: string; comparison_period: string;
  period_noun: "quarter" | "month";
  trend: { periods: string[]; segment: (number | null)[]; book: (number | null)[]; current_index: number };
  peers: { period: string; items: { segment: string; label?: string; value: number; rows: number; is_segment: boolean }[]; book: number | null; book_label: string };
  contributors: { before: string; after: string; views: ContribView[] };
  stage_mix: { periods: [string, string]; stages: number[]; ead: number[][]; unit: string; basis: string };
  source: string;
}

type Figure = { data: Record<string, unknown>[]; layout: Record<string, unknown> };

export const COLOURS = {
  segment: "#6366f1", book: "#94a3b8", current: "#ef4444", peer: "#a5b4fc", up: "#ef4444", down: "#10b981", total: "#6366f1",
  stages: ["#10b981", "#f59e0b", "#ef4444"],
};

/** "SAR 2,755.1m" for an amount (SAR million); "12.76%" for a share. */
export function fmt(v: number | null | undefined, kind: Kind, places = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (kind === "share") return `${v.toFixed(2)}%`;
  const n = Math.abs(v) >= 100 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : v.toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places });
  return `SAR ${n}m`;
}

export function fmtChange(v: number, kind: Kind): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  if (kind === "share") return `${sign}${Math.abs(v).toFixed(2)} pp`;
  const a = Math.abs(v);
  return `${sign}SAR ${a >= 100 ? a.toLocaleString("en-US", { maximumFractionDigits: 0 }) : a.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`;
}

const yTitle = (c: ChartsPayload) => (c.kind === "amount" ? "SAR million" : "% ");
const tick = (c: ChartsPayload) => (c.kind === "amount" ? ",.0f" : ".1f");
const suffix = (c: ChartsPayload) => (c.kind === "share" ? "%" : "");

export function trendFigure(c: ChartsPayload): Figure {
  const t = c.trend;
  const i = t.current_index;
  const hover = c.kind === "share" ? "%{y:.2f}%" : "SAR %{y:,.1f}m";
  const segName = c.trend_labels?.segment || `${c.segment_label ?? c.segment}`;
  const bookName = c.trend_labels ? c.trend_labels.book : "Whole book";
  const data: Record<string, unknown>[] = [
    { type: "scatter", mode: "lines+markers", name: segName, x: t.periods, y: t.segment,
      line: { color: COLOURS.segment, width: 3, shape: "spline", smoothing: 0.4 }, marker: { size: 7, color: COLOURS.segment },
      hovertemplate: `${segName}: ${hover}<extra></extra>` },
    ...(bookName ? [{ type: "scatter", mode: "lines", name: bookName, x: t.periods, y: t.book,
      line: { color: COLOURS.book, width: 2, dash: "dot" }, hovertemplate: `${bookName}: ${hover}<extra></extra>` }] : []),
    { type: "scatter", mode: "markers+text", name: `Now, ${t.periods[i]}`, x: [t.periods[i]], y: [t.segment[i]],
      text: [fmt(t.segment[i], c.kind)], textposition: "top center", textfont: { color: COLOURS.current, size: 12 },
      marker: { size: 14, color: COLOURS.current, line: { color: "#ffffff", width: 2 } }, showlegend: true,
      hovertemplate: `${t.periods[i]}: ${hover}<extra>Current</extra>` },
  ];
  return {
    data,
    layout: {
      xaxis: { type: "category", tickangle: t.periods.length > 8 ? -40 : 0 },
      yaxis: { title: { text: yTitle(c) }, tickformat: tick(c), ticksuffix: suffix(c), rangemode: c.scope === "component" ? "normal" : "tozero" },
      margin: { l: 64, r: 16, t: 28, b: 56 },
    },
  };
}

export function peersFigure(c: ChartsPayload): Figure {
  const items = [...c.peers.items].sort((a, b) => a.value - b.value);
  const hover = c.kind === "share" ? "%{x:.2f}%" : "SAR %{x:,.1f}m";
  const shapes: Record<string, unknown>[] = [];
  const annotations: Record<string, unknown>[] = [];
  if (c.kind === "share" && c.peers.book !== null) {
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: c.peers.book, x1: c.peers.book, y0: 0, y1: 1,
                  line: { color: COLOURS.current, width: 2, dash: "dash" } });
    annotations.push({ xref: "x", yref: "paper", x: c.peers.book, y: 1.06, text: `${c.peers.book_label} ${fmt(c.peers.book, "share")}`,
                       showarrow: false, font: { color: COLOURS.current, size: 11 } });
  }
  return {
    data: [{ type: "bar", orientation: "h", y: items.map((p) => p.label ?? p.segment), x: items.map((p) => p.value),
             marker: { color: items.map((p) => (p.is_segment ? COLOURS.segment : COLOURS.peer)) },
             text: items.map((p) => fmt(p.value, c.kind)), textposition: "outside", cliponaxis: false,
             hovertemplate: `%{y}: ${hover}<extra></extra>` }],
    layout: {
      showlegend: false, hovermode: "closest", shapes, annotations,
      xaxis: { title: { text: yTitle(c) }, tickformat: tick(c), ticksuffix: suffix(c), rangemode: c.scope === "component" ? "normal" : "tozero" },
      yaxis: { type: "category", automargin: true },
      margin: { l: 120, r: 70, t: 28, b: 44 },
    },
  };
}

export function contributorsFigure(c: ChartsPayload, view: ContribView): Figure {
  const names = [c.contributors.before, ...view.items.map((i) => i.name), c.contributors.after];
  const y = [view.from, ...view.items.map((i) => i.change), 0];
  const measure = ["absolute", ...view.items.map(() => "relative"), "total"];
  const text = [fmt(view.from, c.kind), ...view.items.map((i) => fmtChange(i.change, c.kind)), fmt(view.to, c.kind)];
  return {
    data: [{ type: "waterfall", orientation: "v", x: names, y, measure, text, textposition: "outside", cliponaxis: false,
             connector: { line: { color: "#cbd5e1", width: 1 } },
             increasing: { marker: { color: COLOURS.up } }, decreasing: { marker: { color: COLOURS.down } },
             totals: { marker: { color: COLOURS.total } },
             hovertemplate: "%{x}<br>%{text}<extra></extra>" }],
    layout: {
      showlegend: false, hovermode: "closest", waterfallgap: 0.25,
      xaxis: { type: "category", tickangle: names.length > 5 ? -30 : 0 },
      yaxis: { title: { text: yTitle(c) }, tickformat: tick(c), ticksuffix: suffix(c) },
      margin: { l: 64, r: 16, t: 28, b: 90 },
    },
  };
}

export function stageFigure(c: ChartsPayload): Figure {
  const s = c.stage_mix;
  const totals = s.ead.map((row) => row.reduce((a, b) => a + b, 0));
  const data = s.stages.map((stage, k) => ({
    type: "bar", name: `Stage ${stage}`, x: s.periods, y: s.ead.map((row) => row[k]),
    marker: { color: COLOURS.stages[k] },
    text: s.ead.map((row, j) => (totals[j] ? `${((100 * row[k]) / totals[j]).toFixed(1)}%` : "")), textposition: "inside",
    textfont: { color: "#ffffff", size: 12 },
    customdata: s.ead.map((row, j) => (totals[j] ? (100 * row[k]) / totals[j] : 0)),
    hovertemplate: `Stage ${stage}: SAR %{y:,.1f}m (%{customdata:.1f}% of the total)<extra></extra>`,
  }));
  return {
    data,
    layout: {
      barmode: "stack", hovermode: "closest",
      xaxis: { type: "category" }, yaxis: { title: { text: s.unit }, tickformat: ",.0f" },
      annotations: s.periods.map((p, j) => ({ x: p, y: totals[j], text: `SAR ${totals[j].toLocaleString("en-US", { maximumFractionDigits: 0 })}m`,
                                              showarrow: false, yshift: 12, font: { size: 11 } })),
      margin: { l: 64, r: 16, t: 28, b: 44 },
    },
  };
}

/** The attention item as the Mail / investigation / report text, from the numbers the card already prints. */
export function itemText(item: { headline: string; what_changed: string; why_it_appeared: string;
                                  key_numbers: { label: string; display?: string; value?: string }[] }): string {
  const nums = item.key_numbers.map((k) => `${k.label}: ${k.display ?? k.value ?? ""}`).join("; ");
  return `${item.what_changed} ${item.why_it_appeared}\n\nKey numbers: ${nums}.`;
}
