"use client";

/**
 * What-If charts, drawn through the shared Plotly surface (hover, zoom/pan,
 * legend toggles, PNG download). One palette for the module: baseline in the
 * calm chart colour, scenario in the vivid one, drivers coloured by kind.
 */

import * as React from "react";

import { shareBarFigure } from "@/components/answer/bar-figure";
import { Plot } from "@/components/v5/ews/plot";
import type { Bar, Labels, RatingRow, Result, SegmentRow } from "@/lib/v5/whatif";
import { sar } from "@/lib/v5/whatif";
import { orderRatingRows } from "@/lib/v5/ratings";
import { type ChartExplain, ChartInfo } from "@/components/v5/core/chart-explain";
import { compareExplain, ratingRowsExplain, scenarioWeightsExplain, segmentExplain, waterfallExplain } from "./explain";

/** R6 E4: every What-If chart carries its (i), top right. */
export function Explained({ title, explain, children }: { title: string; explain: ChartExplain; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="flex justify-end"><ChartInfo title={title} explain={explain} hint={"Hover for values · click a legend entry to hide it · drag to zoom, double-click to reset · camera icon saves a PNG."} align="right" /></div>
      {children}
    </div>
  );
}

export const COLOURS = {
  before: "var(--ipm-chart-1)",
  after: "var(--ipm-chart-2)",
  up: "var(--ipm-negative)",
  down: "var(--ipm-positive)",
  total: "var(--ipm-accent)",
  model: "var(--ipm-warning)",
};
const DRIVER_COLOUR: Record<string, string> = {
  pd: "var(--ipm-chart-3)", lgd: "var(--ipm-chart-4)", ccf: "var(--ipm-chart-5)", staging: "var(--ipm-chart-6)",
  rating: "var(--ipm-chart-7)", sector: "var(--ipm-chart-8)", mev: "var(--ipm-chart-2)",
};

const money = (v: number) => sar(v);

/** The ECL decomposition: reported -> start (model) -> 7 drivers -> scenario. Bars add up exactly. */
export function WaterfallChart({ bars, testId, filename = "whatif-ecl-waterfall" }: { bars: Bar[]; testId: string; filename?: string }) {
  const x = bars.map((b) => b.label);
  const measure = bars.map((b, i) => (i === 0 ? "absolute" : b.kind === "total" ? "total" : "relative"));
  const y = bars.map((b) => (b.kind === "total" && bars.indexOf(b) > 0 ? 0 : b.value));
  const text = bars.map((b) => (b.kind === "total" ? money(b.value) : `${b.value >= 0 ? "+" : "−"}${money(Math.abs(b.value)).replace("SAR ", "")}`));
  // Zoom onto the range the ECL moves through, so the driver bars are readable (the totals are labelled).
  const levels = bars.reduce<number[]>((acc, b) => [...acc, b.kind === "total" ? b.value : (acc[acc.length - 1] ?? 0) + b.value], []);
  const lo = Math.min(...levels);
  const hi = Math.max(...levels);
  const pad = Math.max((hi - lo) * 0.25, hi * 0.02);
  const range = [Math.max(0, lo - 2 * pad), hi + pad];
  const data = [{
    type: "waterfall", orientation: "v", x, y, measure, text, textposition: "outside", cliponaxis: false,
    connector: { line: { color: "var(--ipm-border)", width: 1 } },
    increasing: { marker: { color: COLOURS.up } }, decreasing: { marker: { color: COLOURS.down } },
    totals: { marker: { color: COLOURS.total } },
    hovertemplate: "%{x}: %{text}<extra></extra>",
  }];
  return <Explained title="ECL decomposition" explain={waterfallExplain(bars)}><Plot data={data} height={340} testId={testId} filename={filename}
               ariaLabel="ECL decomposition waterfall: reported ECL, the start recomputed by the model, each driver, scenario ECL"
               layout={{ hovermode: "closest", showlegend: false, margin: { l: 64, r: 16, t: 24, b: 96 },
                         yaxis: { title: { text: "ECL, SAR million" }, tickformat: ",.0f", range }, xaxis: { tickangle: -30 } }} /></Explained>;
}

export function SegmentChart({ rows, labels, testId }: { rows: SegmentRow[]; labels: Labels; testId: string }) {
  const top = [...rows].sort((a, b) => b.ecl_after - a.ecl_after).slice(0, 14).reverse();
  const y = top.map((r) => r.segment);
  const data = [
    { type: "bar", orientation: "h", name: "Before", y, x: top.map((r) => r.ecl_before), marker: { color: COLOURS.before },
      hovertemplate: "%{y}<br>Before: SAR %{x:,.1f}m<extra></extra>" },
    { type: "bar", orientation: "h", name: "After", y, x: top.map((r) => r.ecl_after), marker: { color: COLOURS.after },
      hovertemplate: "%{y}<br>After: SAR %{x:,.1f}m<extra></extra>" },
  ];
  return <Explained title={`ECL by ${labels.segment.toLowerCase()}`} explain={segmentExplain(rows, labels.segment)}><Plot data={data} height={Math.max(260, top.length * 30 + 80)} testId={testId} filename="whatif-ecl-by-segment"
               ariaLabel={`ECL by ${labels.segment.toLowerCase()}, before and after the scenario`}
               layout={{ barmode: "group", hovermode: "closest", margin: { l: 150, r: 16, t: 28, b: 40 },
                         xaxis: { title: { text: "ECL, SAR million" }, tickformat: ",.0f" } }} /></Explained>;
}

export function RatingChart({ rows: given, labels, testId }: { rows: RatingRow[]; labels: Labels; testId: string }) {
  const rows = orderRatingRows(given, "grade");   // PLAN_R6 E3: AAA to D whatever order the rows came in
  const order = rows.map((r) => r.grade);
  const data = [
    { type: "bar", name: "Before", x: order, y: rows.map((r) => r.ead_before), marker: { color: COLOURS.before },
      hovertemplate: "%{x}<br>EAD before: SAR %{y:,.1f}m<extra></extra>" },
    { type: "bar", name: "After", x: order, y: rows.map((r) => r.ead_after), marker: { color: COLOURS.after },
      hovertemplate: "%{x}<br>EAD after: SAR %{y:,.1f}m<extra></extra>" },
  ];
  return <Explained title={`EAD by ${labels.grade.toLowerCase()}`} explain={ratingRowsExplain(rows, labels.grade)}><Plot data={data} height={280} testId={testId} filename="whatif-ead-by-rating"
               ariaLabel={`EAD by ${labels.grade.toLowerCase()} in the global rating order, before and after`}
               layout={{ barmode: "group", hovermode: "x unified",
                         xaxis: { type: "category", categoryorder: "array", categoryarray: order, title: { text: labels.grade } },
                         yaxis: { title: { text: "EAD, SAR million" }, tickformat: ",.0f" } }} /></Explained>;
}

export function ScenarioWeightsChart({ result, testId }: { result: Result; testId: string }) {
  const names = ["base", "upturn", "downturn"];
  const label = (s: string) => `${s[0].toUpperCase()}${s.slice(1)} (${Math.round((result.by_scenario[s]?.weight ?? 0) * 100)}%)`;
  const data = [
    { type: "bar", name: "Before", x: names.map(label), y: names.map((s) => result.by_scenario[s]?.before ?? 0), marker: { color: COLOURS.before } },
    { type: "bar", name: "After", x: names.map(label), y: names.map((s) => result.by_scenario[s]?.after ?? 0), marker: { color: COLOURS.after } },
  ];
  return <Explained title="ECL by macro scenario" explain={scenarioWeightsExplain(result)}><Plot data={data} height={240} testId={testId} filename="whatif-ecl-by-macro-scenario"
               ariaLabel="ECL under the base, upturn and downturn macro scenarios, before and after"
               layout={{ barmode: "group", yaxis: { title: { text: "ECL, SAR million" }, tickformat: ",.0f" } }} /></Explained>;
}

export function CompareChart({ drivers, testId }: { drivers: { driver: string; delta: number; xgboost: number }[]; testId: string }) {
  const x = drivers.map((d) => d.driver);
  const data = [
    { type: "bar", name: "Delta method", x, y: drivers.map((d) => d.delta), marker: { color: COLOURS.before } },
    { type: "bar", name: "XGBoost", x, y: drivers.map((d) => d.xgboost), marker: { color: COLOURS.after } },
  ];
  return <Explained title="Delta method against XGBoost" explain={compareExplain(drivers)}><Plot data={data} height={260} testId={testId} filename="whatif-delta-vs-xgboost"
               ariaLabel="ECL change by driver, Delta method against XGBoost"
               layout={{ barmode: "group", yaxis: { title: { text: "ECL change, SAR million" }, tickformat: ",.1f" } }} /></Explained>;
}

export function DriverMix({ bars }: { bars: Bar[] }) {
  const active = bars.filter((b) => b.kind === "driver" && b.active && Math.abs(b.value) > 1e-9);
  const total = active.reduce((s, b) => s + Math.abs(b.value), 0) || 1;
  if (!active.length) return <div className="h-3.5 w-full rounded bg-surface-hover" aria-hidden />;
  const fig = shareBarFigure({ height: 14, segments: active.map((b) => ({
    label: b.label, value: (Math.abs(b.value) / total) * 100, color: DRIVER_COLOUR[b.key] ?? "var(--ipm-chart-1)",
    text: `${((Math.abs(b.value) / total) * 100).toFixed(0)}% (${b.value >= 0 ? "+" : "−"}${money(Math.abs(b.value)).replace("SAR ", "")})`,
  })) });
  return <Plot data={fig.data} layout={{ ...fig.layout, xaxis: { visible: false, fixedrange: true, range: [0, 100] } }} height={fig.height}
               ariaLabel="Share of the ECL change by driver" filename="whatif-driver-mix" testId="whatif-driver-mix" />;
}

export function HistoryChart({ series, testId, title, unit }: { series: { x: (string | number)[]; y: number[]; name: string }[];
  testId: string; title: string; unit: string }) {
  const palette = ["var(--ipm-chart-1)", "var(--ipm-chart-2)", "var(--ipm-chart-3)"];
  const data = series.map((s, i) => ({ type: "scatter", mode: "lines+markers", name: s.name, x: s.x, y: s.y,
                                       line: { color: palette[i % 3], width: 2 }, marker: { size: 5 } }));
  return <Plot data={data} height={240} testId={testId} filename={title.toLowerCase().replace(/\W+/g, "-")}
               ariaLabel={title} layout={{ yaxis: { title: { text: unit } } }} />;
}

export { React };
