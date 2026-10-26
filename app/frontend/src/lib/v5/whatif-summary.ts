/**
 * The What-If thread header's charts as Plotly figures (PLAN_R3 S3-5), built
 * from the API's population summary (`GET /api/v1/whatif/threads/{id}/summary`,
 * backend/whatif_v5/summary.py). Pure functions: a figure carries exactly the
 * API's numbers, in the API's order (ratings in the global order, bands worst
 * first); hovers show formatted SAR, counts and shares, never a field name.
 *
 * Colours are the module's tokens (resolved by the Plot surface): stages and
 * Early Warning bands carry the status colours, other series the categorical
 * chart colours in fixed order.
 */
import { count, pct, sar } from "./ews.ts";
import { RATING_ORDER, ratingRank } from "./ratings.ts";
import type { PopulationSummary } from "./whatif.ts";

export type Figure = { data: Record<string, unknown>[]; layout: Record<string, unknown>; height: number };

export const STAGE_COLOUR: Record<number, string> = { 1: "var(--ipm-positive)", 2: "var(--ipm-warning)", 3: "var(--ipm-negative)" };
export const BAND_COLOUR: Record<string, string> = {
  critical: "var(--ipm-negative)", high: "var(--ipm-chart-2)", moderate: "var(--ipm-warning)",
  low: "var(--ipm-chart-6)", none: "var(--ipm-text-muted)",
};
export const SERIES_COLOUR = { rating: "var(--ipm-chart-1)", split: "var(--ipm-chart-3)", owners: "var(--ipm-chart-4)", ead: "var(--ipm-chart-1)" };
const GAP = { color: "var(--ipm-surface)", width: 2 };
const EAD_AXIS = { title: { text: "EAD, SAR million" }, tickformat: ",.0f" };

/** Wrap a long category label onto lines of about `width` characters (Plotly breaks on <br>). */
export function wrap(label: string, width = 30): string {
  const lines: string[] = [];
  let line = "";
  for (const w of label.split(" ")) {
    if (line && `${line} ${w}`.length > width) { lines.push(line); line = w; } else { line = line ? `${line} ${w}` : w; }
  }
  if (line) lines.push(line);
  return lines.join("<br>");
}

/** True when corporate ratings run in the global order (AAA ... D) with no unknown grade. */
export function inGlobalOrder(order: readonly string[]): boolean {
  const ranks = order.map((g) => ratingRank(g));
  return ranks.every((r, i) => r < RATING_ORDER.length && (i === 0 || r > ranks[i - 1]));
}

export function stageFigure(s: PopulationSummary): Figure {
  const rows = s.stages;
  return {
    height: 260,
    data: [{
      type: "pie", hole: 0.58, sort: false, direction: "clockwise",
      labels: rows.map((r) => r.label), values: rows.map((r) => r.ead),
      marker: { colors: rows.map((r) => STAGE_COLOUR[r.stage]), line: GAP },
      customdata: rows.map((r) => [sar(r.ead), count(r.n), sar(r.ecl), pct(r.ead_pct, 1)]),
      texttemplate: "%{label}<br>%{customdata[3]}", textposition: "outside",
      hovertemplate: `<b>%{label}</b><br>EAD %{customdata[0]} (%{customdata[3]})<br>%{customdata[1]} ${s.labels.exposures.toLowerCase()}`
        + "<br>ECL %{customdata[2]}<extra></extra>",
    }],
    layout: {
      hovermode: "closest", showlegend: true, margin: { l: 24, r: 24, t: 24, b: 24 },
      legend: { orientation: "h", x: 0.5, xanchor: "center", y: -0.05, yanchor: "top" },
      annotations: [{ text: `${sar(s.cards.ead)}<br>EAD`, showarrow: false, font: { size: 13, color: "var(--ipm-text-primary)" },
                      x: 0.5, y: 0.5, xref: "paper", yref: "paper" }],
    },
  };
}

export function gradeFigure(s: PopulationSummary): Figure {
  const rows = s.grades.rows;
  const order = s.grades.order;
  return {
    height: 260,
    data: [{
      type: "bar", name: "EAD", x: order, y: rows.map((r) => r.ead), marker: { color: SERIES_COLOUR.rating, line: GAP },
      customdata: rows.map((r) => [sar(r.ead), pct(r.ead_pct, 1), count(r.n), count(r.owners), sar(r.ecl)]),
      hovertemplate: `<b>%{x}</b><br>EAD %{customdata[0]} (%{customdata[1]} of EAD)<br>%{customdata[2]} ${s.labels.exposures.toLowerCase()}, `
        + `%{customdata[3]} ${s.labels.owners.toLowerCase()}<br>ECL %{customdata[4]}<extra></extra>`,
    }],
    layout: {
      hovermode: "closest", showlegend: false, bargap: 0.25, margin: { l: 64, r: 12, t: 12, b: 48 },
      xaxis: { type: "category", categoryorder: "array", categoryarray: order, title: { text: s.grades.label } },
      yaxis: EAD_AXIS,
    },
  };
}

export function splitFigure(s: PopulationSummary): Figure {
  const rows = [...s.split.rows].reverse();        // the largest at the top
  return {
    height: Math.max(220, rows.length * 26 + 70),
    data: [{
      type: "bar", orientation: "h", name: "EAD", y: rows.map((r) => r.name), x: rows.map((r) => r.ead),
      marker: { color: SERIES_COLOUR.split, line: GAP },
      customdata: rows.map((r) => [sar(r.ead), pct(r.ead_pct, 1), count(r.n), count(r.owners), sar(r.ecl), pct(r.coverage_pct, 2)]),
      hovertemplate: `<b>%{y}</b><br>EAD %{customdata[0]} (%{customdata[1]} of EAD)<br>%{customdata[2]} ${s.labels.exposures.toLowerCase()}, `
        + `%{customdata[3]} ${s.labels.owners.toLowerCase()}<br>ECL %{customdata[4]} · coverage %{customdata[5]}<extra></extra>`,
    }],
    layout: {
      hovermode: "closest", showlegend: false, bargap: 0.3, margin: { l: 140, r: 16, t: 12, b: 44 },
      xaxis: EAD_AXIS, yaxis: { type: "category", categoryorder: "array", categoryarray: rows.map((r) => r.name) },
    },
  };
}

/** Top warning reasons: owners flagged (left panel) and their EAD (right panel), each on its own scale. */
export function reasonsFigure(s: PopulationSummary): Figure {
  const rows = [...s.reasons].reverse();
  const y = rows.map((r) => wrap(r.reason, 34));
  const owners = s.labels.owners;
  return {
    height: Math.max(240, rows.length * 42 + 90),
    data: [
      { type: "bar", orientation: "h", name: owners, y, x: rows.map((r) => r.owners), xaxis: "x", yaxis: "y",
        marker: { color: SERIES_COLOUR.owners, line: GAP },
        customdata: rows.map((r) => [count(r.owners), count(r.exposures), r.reason]),
        hovertemplate: `<b>%{customdata[2]}</b><br>%{customdata[0]} ${owners.toLowerCase()} · %{customdata[1]} ${s.labels.exposures.toLowerCase()}<extra></extra>` },
      { type: "bar", orientation: "h", name: "EAD", y, x: rows.map((r) => r.ead), xaxis: "x2", yaxis: "y",
        marker: { color: SERIES_COLOUR.ead, line: GAP },
        customdata: rows.map((r) => [sar(r.ead), r.reason]),
        hovertemplate: "<b>%{customdata[1]}</b><br>EAD %{customdata[0]}<extra></extra>" },
    ],
    layout: {
      hovermode: "closest", bargap: 0.3, margin: { l: 220, r: 16, t: 30, b: 56 },
      // Two panels on their own scales (never one dual axis); each panel is named above it, the legend below.
      xaxis: { domain: [0, 0.46], tickformat: ",.0f", nticks: 4, tickangle: 0 },
      xaxis2: { domain: [0.54, 1], anchor: "y", tickformat: ",.0f", nticks: 4, tickangle: 0 },
      legend: { orientation: "h", x: 0, y: -0.06, yanchor: "top", font: { size: 11 } },
      annotations: [
        { text: `<b>${owners} flagged</b>`, showarrow: false, xref: "x domain", x: 0, xanchor: "left", yref: "paper", y: 1, yanchor: "bottom", font: { size: 11 } },
        { text: "<b>EAD, SAR million</b>", showarrow: false, xref: "x2 domain", x: 0, xanchor: "left", yref: "paper", y: 1, yanchor: "bottom", font: { size: 11 } },
      ],
      yaxis: { type: "category", categoryorder: "array", categoryarray: y },
    },
  };
}

export function bandsFigure(s: PopulationSummary): Figure {
  const rows = s.bands;
  const owners = s.labels.owners;
  return {
    height: 240,
    data: [{
      type: "bar", name: owners, x: rows.map((r) => r.label), y: rows.map((r) => r.owners),
      marker: { color: rows.map((r) => BAND_COLOUR[r.band] ?? "var(--ipm-chart-1)"), line: GAP },
      text: rows.map((r) => count(r.owners)), textposition: "outside", cliponaxis: false,
      customdata: rows.map((r) => [count(r.owners), count(r.exposures), sar(r.ead), sar(r.ecl)]),
      hovertemplate: `<b>%{x}</b><br>%{customdata[0]} ${owners.toLowerCase()} · %{customdata[1]} ${s.labels.exposures.toLowerCase()}`
        + "<br>EAD %{customdata[2]} · ECL %{customdata[3]}<extra></extra>",
    }],
    layout: {
      hovermode: "closest", showlegend: false, bargap: 0.3, margin: { l: 56, r: 12, t: 24, b: 44 },
      xaxis: { type: "category", categoryorder: "array", categoryarray: rows.map((r) => r.label), title: { text: "Early Warning band" } },
      yaxis: { title: { text: owners }, tickformat: ",.0f" },
    },
  };
}
