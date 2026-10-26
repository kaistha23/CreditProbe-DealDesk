"use client";

/**
 * Deal Desk charts, drawn through the shared Plotly surface (hover, zoom,
 * legend toggles, PNG download from the mode bar). One palette for the
 * module: the ask in chart-1, the recommendation in the accent, the hurdle in
 * the warning colour, gains positive and costs negative.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import type { Analysis, Constraint, Grid, OptimizeResult, Terms, Tornado } from "@/lib/v5/dealdesk";
import { gridX, gridY, money } from "@/lib/v5/dealdesk";
import { headroomWords, usedShare } from "./explain";
import { ratingAxisOrder } from "@/lib/v5/ratings";
import { waterfallBottom, waterfallTick, waterfallValue } from "@/lib/v5/dealdesk-waterfall";

export const C = {
  ask: "var(--ipm-chart-1)",
  rec: "var(--ipm-accent)",
  best: "var(--ipm-chart-3)",
  hurdle: "var(--ipm-warning)",
  up: "var(--ipm-positive)",
  down: "var(--ipm-negative)",
  muted: "var(--ipm-border-strong)",
};

const pctAxis = { tickformat: ".0%", hoverformat: ".1%" };

/** R7 U2: the heatmap's price lever, margin for a funded ask and commission for an LG or LC (the engine names it in `x`). */
export const heatLever = (grid: Grid): { key: "margin_bps" | "commission_bps"; label: string } =>
  grid.x === "commission_bps" ? { key: "commission_bps", label: "Commission" } : { key: "margin_bps", label: "Margin" };

export function IsoRarocHeatmap({ grid, ask, rec, height = 340 }: { grid: Grid; ask: Terms; rec?: Terms | null; height?: number }) {
  const z = grid.values as number[][];
  const lever = heatLever(grid);
  const askX = grid.ask?.x ?? ask[lever.key];
  const data: Record<string, unknown>[] = [
    { type: "heatmap", x: gridX(grid), y: gridY(grid), z, colorscale: [[0, "#a92a25"], [0.5, "#f4efe6"], [1, "#12704b"]],
      zmid: grid.hurdle, colorbar: { title: { text: "RAROC" }, tickformat: ".0%", thickness: 12 },
      hovertemplate: `${lever.label} %{x} bps · tenor %{y} years<br>RAROC %{z:.1%}<extra></extra>` },
    { type: "contour", x: gridX(grid), y: gridY(grid), z, showscale: false, name: "Hurdle",
      contours: { start: grid.hurdle, end: grid.hurdle, size: 1, coloring: "none", showlabels: false },
      line: { color: C.hurdle, width: 3, dash: "dash" }, hoverinfo: "skip", showlegend: true },
    { type: "scatter", mode: "markers", name: "Ask", x: [askX], y: [ask.tenor_years],
      marker: { size: 13, color: C.ask, symbol: "x", line: { width: 1, color: "#fff" } },
      hovertemplate: "Ask: %{x} bps, %{y} years<extra></extra>" },
  ];
  if (rec) data.push({ type: "scatter", mode: "markers", name: "Recommended", x: [rec[lever.key]], y: [rec.tenor_years],
    marker: { size: 13, color: C.rec, symbol: "star", line: { width: 1, color: "#fff" } },
    hovertemplate: "Recommended: %{x} bps, %{y} years<extra></extra>" });
  return <Plot data={data} height={height} testId="dealdesk-chart-heatmap" filename="deal-desk-iso-raroc"
               ariaLabel={`Lifetime RAROC over ${lever.label.toLowerCase()} and tenor, with the hurdle contour and the ask marked`}
               layout={{ hovermode: "closest", margin: { l: 56, r: 16, t: 28, b: 48 },
                         xaxis: { title: { text: `${lever.label}, bps` } }, yaxis: { title: { text: "Tenor, years" }, dtick: 1 } }} />;
}

export function RarocAmountCurve({ grid, ask, rec, ccy, height = 300 }: { grid: Grid; ask: Terms; rec?: Terms | null; ccy: string; height?: number }) {
  const xs = gridX(grid);
  const data: Record<string, unknown>[] = [
    { type: "scatter", mode: "lines+markers", name: "RAROC", x: xs, y: grid.values as number[],
      line: { color: C.ask, width: 2 }, hovertemplate: `${ccy} %{x:,.0f}m<br>RAROC %{y:.1%}<extra></extra>` },
    { type: "scatter", mode: "lines", name: "Hurdle", x: [Math.min(...xs), Math.max(...xs)], y: [grid.hurdle, grid.hurdle],
      line: { color: C.hurdle, dash: "dash", width: 2 }, hoverinfo: "skip" },
  ];
  const shapes = [{ type: "line", x0: ask.amount, x1: ask.amount, yref: "paper", y0: 0, y1: 1, line: { color: C.ask, dash: "dot", width: 1 } }];
  if (rec) shapes.push({ type: "line", x0: rec.amount, x1: rec.amount, yref: "paper", y0: 0, y1: 1, line: { color: C.rec, dash: "dot", width: 1 } });
  return <Plot data={data} height={height} testId="dealdesk-chart-amount" filename="deal-desk-raroc-vs-amount"
               ariaLabel="Lifetime RAROC against the amount, with the hurdle"
               layout={{ hovermode: "x unified", margin: { l: 56, r: 16, t: 28, b: 48 }, shapes,
                         xaxis: { title: { text: `Amount, ${ccy} million` }, tickformat: ",.0f" }, yaxis: { title: { text: "RAROC" }, ...pctAxis } }} />;
}

export function FrontierChart({ opt }: { opt: OptimizeResult }) {
  const data: Record<string, unknown>[] = [];
  const offers = opt.counter_offers ?? [];
  if (offers.length) data.push({ type: "scatter", mode: "markers", name: "Counter-offers", x: offers.map((o) => o.distance), y: offers.map((o) => o.metrics.sva),
    text: offers.map((o) => o.label), marker: { size: 9, color: C.ask, symbol: "diamond" }, hovertemplate: "%{text}<br>Distance %{x:.2f}<br>SVA SAR %{y:,.2f}m<extra></extra>" });
  data.push({ type: "scatter", mode: "lines+markers", name: "Frontier", x: opt.frontier.map((p) => p.distance), y: opt.frontier.map((p) => p.sva),
    line: { color: C.rec, width: 2, shape: "hv" }, marker: { size: 8, color: C.rec },
    hovertemplate: "Distance %{x:.2f}<br>SVA SAR %{y:,.2f}m<extra></extra>" });
  const ends = [opt.frontier[0], opt.frontier[opt.frontier.length - 1]].filter(Boolean);
  data.push({ type: "scatter", mode: "markers+text", name: "Closest / max SVA", x: ends.map((p) => p.distance), y: ends.map((p) => p.sva),
    text: ends.length > 1 ? ["Closest", "Max SVA"] : ["Closest"], textposition: "top center",
    marker: { size: 12, color: [C.rec, C.best] }, hoverinfo: "skip" });
  return <Plot data={data} height={300} testId="dealdesk-chart-frontier" filename="deal-desk-frontier"
               ariaLabel="Pareto frontier: distance from the ask against SVA"
               layout={{ hovermode: "closest", margin: { l: 56, r: 16, t: 28, b: 48 },
                         xaxis: { title: { text: "Distance from the ask" } }, yaxis: { title: { text: "SVA, SAR million" }, tickformat: ",.1f" } }} />;
}

export function TornadoChart({ t }: { t: Tornado }) {
  const bars = [...t.bars].reverse();
  const y = bars.map((r) => r.lever);
  const d = (v: number) => v - t.base_raroc;
  const data = [
    { type: "bar", orientation: "h", name: "Lower RAROC", y, x: bars.map((r) => Math.min(d(r.low), d(r.high), 0)),
      customdata: bars.map((r) => (d(r.low) <= d(r.high) ? r.low_label : r.high_label) ?? ""),
      marker: { color: C.down }, hovertemplate: "%{y} %{customdata}: %{x:+.1%}<extra></extra>" },
    { type: "bar", orientation: "h", name: "Higher RAROC", y, x: bars.map((r) => Math.max(d(r.low), d(r.high), 0)),
      customdata: bars.map((r) => (d(r.low) > d(r.high) ? r.low_label : r.high_label) ?? ""),
      marker: { color: C.up }, hovertemplate: "%{y} %{customdata}: %{x:+.1%}<extra></extra>" },
  ];
  return <Plot data={data} height={Math.max(240, bars.length * 36 + 70)} testId="dealdesk-chart-tornado" filename="deal-desk-tornado"
               ariaLabel="Lever impact on lifetime RAROC (tornado)"
               layout={{ barmode: "overlay", hovermode: "closest", margin: { l: 150, r: 16, t: 28, b: 40 },
                         xaxis: { title: { text: "Change in RAROC" }, tickformat: "+.0%" } }} />;
}

/** PLAN_R6 D4: share of each limit used after the deal, sorted, coloured pass / near / breach, labelled in plain words. */
export function HeadroomChart({ rows }: { rows: Constraint[] }) {
  const shown = rows.map((c) => ({ c, u: usedShare(c) })).filter((x) => x.u !== null && x.c.unit !== "notch" && x.c.unit !== "rating")
    .sort((a, b) => (a.u as number) - (b.u as number));
  const tone = (c: Constraint, u: number) => (c.status === "breach" || u > 1 ? (c.kind === "hard" ? C.down : C.hurdle) : u >= 0.85 ? C.hurdle : C.up);
  const capped = shown.map((x) => Math.min(x.u as number, 1.5));
  const data = [{
    type: "bar", orientation: "h", y: shown.map((x) => x.c.label), x: capped,
    marker: { color: shown.map((x) => tone(x.c, x.u as number)) },
    text: shown.map((x) => headroomWords(x.c).replace(`${x.c.label}: `, "")), textposition: "auto", insidetextanchor: "start",
    textfont: { size: 11 }, cliponaxis: false,
    customdata: shown.map((x) => [headroomWords(x.c), x.c.kind === "hard" ? "Hard limit" : "Soft limit", x.c.basis]),
    hovertemplate: "%{customdata[0]}<br>%{customdata[1]} · %{customdata[2]}<extra></extra>",
  }];
  const shapes = [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: C.down, dash: "dash", width: 1.5 } }];
  return <Plot data={data} height={Math.max(260, shown.length * 34 + 70)} testId="dealdesk-chart-headroom" filename="deal-desk-headroom"
               ariaLabel="Share of each limit used after the deal, tightest at the top; green pass, amber near, red breach"
               layout={{ hovermode: "closest", showlegend: false, margin: { l: 200, r: 24, t: 16, b: 48 }, shapes,
                         annotations: [{ x: 1, y: 1.02, yref: "paper", text: "Limit", showarrow: false, font: { size: 11 } }],
                         xaxis: { title: { text: "Share of the limit used after the deal (100% = at the limit)" }, tickformat: ".0%", range: [0, 1.55] } }} />;
}

export function WaterfallChart({ res }: { res: Analysis }) {
  const bars = res.waterfall;
  // R12 G (O1): the values live in the category labels under the axis, so no label in the plot can meet a hover box
  const ticks = bars.map((b, i) => waterfallTick(b.step, waterfallValue(b.value, !(i === 0 || b.total))));
  const data = [{
    type: "waterfall", orientation: "v", x: bars.map((b) => b.step), y: bars.map((b) => (b.total ? 0 : b.value)),
    measure: bars.map((b, i) => (i === 0 ? "absolute" : b.total ? "total" : "relative")),
    text: bars.map((b) => money(b.value)), textposition: "none",
    connector: { line: { color: "var(--ipm-border)", width: 1 } },
    increasing: { marker: { color: C.up } }, decreasing: { marker: { color: C.down } }, totals: { marker: { color: C.rec } },
    hovertemplate: "%{x}: %{text}<extra></extra>",
  }];
  return <Plot data={data} height={320 + Math.max(0, waterfallBottom(ticks) - 72)} testId="dealdesk-chart-waterfall" filename="deal-desk-raroc-waterfall"
               ariaLabel="RAROC waterfall: profit income, fees, FTP, opex, EL, zakat, capital benefit, risk-adjusted profit (present values)"
               layout={{ hovermode: "closest", showlegend: false, margin: { l: 64, r: 16, t: 16, b: waterfallBottom(ticks) },
                         hoverlabel: { bgcolor: "var(--ipm-surface-raised)", bordercolor: "var(--ipm-border-strong)", font: { color: "var(--ipm-text-primary)" } },
                         xaxis: { tickmode: "array", tickvals: bars.map((b) => b.step), ticktext: ticks, tickangle: 0, automargin: true,
                                  tickfont: { size: 10, color: "var(--ipm-text-secondary)" } },
                         yaxis: { title: { text: "PV, SAR million" }, tickformat: ",.1f" } }} />;
}

/** RAROC by obligor grade in the global rating order (the robustness view). */
export function RatingChart({ rows, hurdle }: { rows: { rating: string; raroc: number }[]; hurdle: number }) {
  const data = [
    { type: "bar", name: "RAROC", x: rows.map((r) => r.rating), y: rows.map((r) => r.raroc),
      marker: { color: rows.map((r) => (r.raroc >= hurdle ? C.up : C.down)) }, hovertemplate: "%{x}: %{y:.1%}<extra></extra>" },
    { type: "scatter", mode: "lines", name: "Hurdle", x: rows.map((r) => r.rating), y: rows.map(() => hurdle),
      line: { color: C.hurdle, dash: "dash", width: 2 }, hoverinfo: "skip" },
  ];
  return <Plot data={data} height={280} testId="dealdesk-chart-rating" filename="deal-desk-raroc-by-grade"
               ariaLabel="Lifetime RAROC by obligor grade, in the global rating order"
               layout={{ hovermode: "x unified", margin: { l: 56, r: 16, t: 28, b: 40 },
                         xaxis: { type: "category", categoryorder: "array", categoryarray: ratingAxisOrder(rows.map((r) => r.rating)) },
                         yaxis: { title: { text: "RAROC" }, ...pctAxis } }} />;
}

/** PLAN_R10 D4: lifetime RAROC against tenor at the asked price (a column of the iso-RAROC grid), with the hurdle. */
export function RarocTenorCurve({ rows, hurdle, askTenor, recTenor }: { rows: { tenor: number; raroc: number }[]; hurdle: number; askTenor: number; recTenor?: number | null }) {
  const xs = rows.map((r) => r.tenor);
  const data: Record<string, unknown>[] = [
    { type: "scatter", mode: "lines+markers", name: "RAROC", x: xs, y: rows.map((r) => r.raroc),
      marker: { color: rows.map((r) => (r.raroc >= hurdle ? C.up : C.down)), size: 8 }, line: { color: C.ask, width: 2 },
      hovertemplate: "Tenor %{x} years<br>RAROC %{y:.1%}<extra></extra>" },
    { type: "scatter", mode: "lines", name: "Hurdle", x: [Math.min(...xs), Math.max(...xs)], y: [hurdle, hurdle],
      line: { color: C.hurdle, dash: "dash", width: 2 }, hoverinfo: "skip" },
  ];
  const shapes = [{ type: "line", x0: askTenor, x1: askTenor, yref: "paper", y0: 0, y1: 1, line: { color: C.ask, dash: "dot", width: 1 } }];
  if (recTenor !== null && recTenor !== undefined) shapes.push({ type: "line", x0: recTenor, x1: recTenor, yref: "paper", y0: 0, y1: 1, line: { color: C.rec, dash: "dot", width: 1 } });
  return <Plot data={data} height={260} testId="dealdesk-chart-tenor" filename="deal-desk-raroc-vs-tenor"
               ariaLabel="Lifetime RAROC against tenor at the asked price, with the hurdle"
               layout={{ hovermode: "x unified", margin: { l: 56, r: 16, t: 20, b: 44 }, shapes,
                         xaxis: { title: { text: "Tenor, years" }, dtick: 1 }, yaxis: { title: { text: "RAROC" }, ...pctAxis } }} />;
}
