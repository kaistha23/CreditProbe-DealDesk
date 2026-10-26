import assert from "node:assert/strict";
import { test } from "node:test";

import type { ChartAxis, ChartPoint, RenderedChart } from "@/components/cockpit-v4/client";

import { CHART_KINDS } from "../cockpit-v4/visual-choice.ts";
import { cockpitFigure, esc } from "./cockpit-figure.ts";

type Fig = Record<string, unknown>;

const AXIS: ChartAxis = {
  kind: "measure", label: "Exposure at default", column: "ead", unit: "SAR mn",
  ticks: [{ value: 0, display: "SAR 0 mn" }, { value: 50, display: "SAR 50 mn" }, { value: 100, display: "SAR 100 mn" }],
};

function pt(label: string, values: Record<string, unknown>, display: Record<string, string>, i = 0): ChartPoint {
  return { row_id: `r${i}-${label}`, label, values, display };
}

function chart(kind: string, extra: Partial<RenderedChart> = {}): RenderedChart {
  return {
    kind, title: "Exposure by sector", artifact_id: "a1", x_column: "sector", y_columns: ["ead"], unit: "SAR mn",
    points: [
      pt("Retail", { ead: 40 }, { ead: "SAR 40 mn" }, 0),
      pt("Energy", { ead: 90 }, { ead: "SAR 90 mn" }, 1),
      pt("Real estate", { ead: 10 }, { ead: "SAR 10 mn" }, 2),
    ],
    y_axis: AXIS,
    ...extra,
  };
}

const two = (kind: string, extra: Partial<RenderedChart> = {}) => chart(kind, {
  y_columns: ["stage1", "stage2"],
  points: [
    pt("Retail", { stage1: 30, stage2: 10 }, { stage1: "SAR 30 mn", stage2: "SAR 10 mn" }, 0),
    pt("Energy", { stage1: 60, stage2: 20 }, { stage1: "SAR 60 mn", stage2: "SAR 20 mn" }, 1),
  ],
  ...extra,
});

const fig = (c: RenderedChart) => {
  const f = cockpitFigure(c);
  assert.ok(f, `expected a figure for ${c.kind}`);
  return f;
};
const ax = (f: { layout: Fig }, key: string) => f.layout[key] as Fig;
const cd = (trace: Fig) => trace.customdata as unknown[][];

test("every one of the 16 kinds gets a figure", () => {
  assert.equal(CHART_KINDS.length, 16);
  for (const kind of CHART_KINDS) {
    const c = kind === "heatmap" ? chart(kind, { matrix: { row_axis: "From", column_axis: "To", measure: "n", unit: "", rows: ["S1"], columns: ["S1"], square: true, cells: { "S1|S1": 3 }, display: { "S1|S1": "3" } } })
      : kind === "box" ? chart(kind, { boxes: [{ label: "", count: 3, unit: "", minimum: "1", q1: "2", median: "3", q3: "4", maximum: "5", display: { median: "3.0" } }] })
      : ["stacked_bar", "stacked_bar_100", "grouped_bar", "combo", "bubble"].includes(kind) ? two(kind) : chart(kind);
    const f = cockpitFigure(c);
    assert.ok(f && f.data.length > 0 && f.height > 0, kind);
  }
});

test("bar: horizontal, first point on top, display strings as text and hover, server ticks", () => {
  const f = fig(chart("bar"));
  const [t] = f.data;
  assert.equal(t.type, "bar");
  assert.equal(t.orientation, "h");
  assert.deepEqual(t.y, ["Retail", "Energy", "Real estate"]);
  assert.deepEqual(t.x, [40, 90, 10]);
  assert.deepEqual(t.text, ["SAR 40 mn", "SAR 90 mn", "SAR 10 mn"]);
  assert.deepEqual(cd(t).map((r) => r[1]), ["SAR 40 mn", "SAR 90 mn", "SAR 10 mn"]);
  assert.match(String(t.hovertemplate), /customdata/);
  const y = ax(f, "yaxis");
  assert.equal(y.categoryorder, "array");
  assert.deepEqual(y.categoryarray, ["Retail", "Energy", "Real estate"]);
  assert.equal(y.autorange, "reversed");
  const x = ax(f, "xaxis");
  assert.equal(x.tickmode, "array");
  assert.deepEqual(x.tickvals, [0, 50, 100]);
  assert.deepEqual(x.ticktext, ["SAR 0 mn", "SAR 50 mn", "SAR 100 mn"]);
  assert.deepEqual((x.title as Fig).text, "Exposure at default");
  assert.deepEqual(x.range, [0, 100]);
  assert.equal((t.marker as Fig).color, "var(--ipm-chart-1)");
});

test("bar without server ticks hides numeric tick labels", () => {
  const f = fig(chart("bar", { y_axis: undefined }));
  const x = ax(f, "xaxis");
  assert.equal(x.showticklabels, false);
  assert.equal(x.tickvals, undefined);
  assert.deepEqual(x.range, [0, 90]);
});

test("null when nothing is plottable", () => {
  const empty = chart("bar", { points: [pt("A", { ead: null }, { ead: "" })] });
  for (const kind of ["bar", "histogram", "waterfall", "pie", "donut", "line"]) {
    assert.equal(cockpitFigure({ ...empty, kind }), null, kind);
  }
  // A line of one plottable point is not drawn (the SVG needs two).
  assert.equal(cockpitFigure(chart("line", { points: [pt("A", { ead: 1 }, { ead: "1" })] })), null);
  // A pie with no whole to divide.
  assert.equal(cockpitFigure(chart("pie", { points: [pt("A", { ead: 0 }, { ead: "0" }), pt("B", { ead: 0 }, { ead: "0" })] })), null);
  // Multi-series forms need two columns.
  for (const kind of ["stacked_bar", "stacked_bar_100", "grouped_bar", "combo", "bubble"]) {
    assert.equal(cockpitFigure(chart(kind)), null, kind);
  }
  assert.equal(cockpitFigure(chart("heatmap")), null);
  assert.equal(cockpitFigure(chart("box")), null);
  assert.equal(cockpitFigure(chart("box", { boxes: [{ label: "x", count: 0, unit: "", minimum: "n/a", q1: "", median: "", q3: "", maximum: "abc", display: {} }] })), null);
  assert.equal(cockpitFigure(chart("bar", { y_columns: [] })), null);
});

test("line, step_line, area, scatter: modes, order, ticks, display hover", () => {
  const points = Array.from({ length: 10 }, (_, i) => pt(`2025-${String(i + 1).padStart(2, "0")}`, { ead: 10 + i }, { ead: `SAR ${10 + i} mn` }, i));
  const line = fig(chart("line", { points, x_axis: { kind: "category", label: "Month", column: "m", unit: "", ticks: [] } }));
  const main = line.data[line.data.length - 1];
  assert.equal(main.type, "scatter");
  assert.equal(main.mode, "lines+markers");
  assert.deepEqual(main.y, points.map((p) => p.values.ead));
  assert.deepEqual(cd(main).map((r) => r[1]), points.map((p) => p.display.ead));
  const x = ax(line, "xaxis");
  assert.deepEqual(x.categoryarray, points.map((p) => p.label));
  // Thinned like the SVG: every 2nd label of ten, plus the last.
  assert.deepEqual(x.tickvals, ["2025-01", "2025-03", "2025-05", "2025-07", "2025-09", "2025-10"]);
  assert.equal((x.title as Fig).text, "Month");
  assert.deepEqual(ax(line, "yaxis").ticktext, ["SAR 0 mn", "SAR 50 mn", "SAR 100 mn"]);

  const step = fig(chart("step_line"));
  assert.equal(((step.data[0].line as Fig).shape), "hv");
  const scatter = fig(chart("scatter"));
  assert.equal(scatter.data[0].mode, "markers");
  const area = fig(chart("area"));
  assert.equal(area.data.length, 2);
  assert.equal(area.data[0].fill, "tozeroy");
  assert.equal(area.data[0].hoverinfo, "skip");
});

test("histogram: touching vertical bars in point order", () => {
  const f = fig(chart("histogram"));
  assert.equal(f.data[0].type, "bar");
  assert.equal(f.data[0].orientation, undefined);
  assert.equal(f.layout.bargap, 0);
  assert.deepEqual(f.data[0].x, ["Retail", "Energy", "Real estate"]);
  assert.deepEqual(ax(f, "yaxis").tickvals, [0, 50, 100]);
});

test("stacked_bar keeps lengths and the ruler; stacked_bar_100 normalises each row and shows no scale", () => {
  const abs = fig(two("stacked_bar"));
  assert.equal(abs.layout.barmode, "stack");
  assert.deepEqual(abs.data.map((t) => t.name), ["stage1", "stage2"]);
  assert.deepEqual(abs.data[0].x, [30, 60]);
  assert.deepEqual(abs.data.map((t) => (t.marker as Fig).color), ["var(--ipm-chart-1)", "var(--ipm-chart-2)"]);
  assert.deepEqual(cd(abs.data[1]).map((r) => r[1]), ["SAR 10 mn", "SAR 20 mn"]);
  assert.deepEqual(ax(abs, "xaxis").ticktext, ["SAR 0 mn", "SAR 50 mn", "SAR 100 mn"]);

  const pct = fig(two("stacked_bar_100"));
  assert.deepEqual(pct.data[0].x, [0.75, 0.75]);
  assert.deepEqual(pct.data[1].x, [0.25, 0.25]);
  assert.equal(ax(pct, "xaxis").showticklabels, false);
  assert.equal(ax(pct, "xaxis").title, undefined);
  assert.equal(ax(pct, "yaxis").autorange, "reversed");
});

test("grouped_bar: side by side, display text per bar", () => {
  const f = fig(two("grouped_bar"));
  assert.equal(f.layout.barmode, "group");
  assert.deepEqual(f.data[0].text, ["SAR 30 mn", "SAR 60 mn"]);
  assert.deepEqual(f.data[1].text, ["SAR 10 mn", "SAR 20 mn"]);
  assert.deepEqual(ax(f, "yaxis").categoryarray, ["Retail", "Energy"]);
});

test("combo: bars on the primary scale, the rate on y_axis_secondary", () => {
  const secondary: ChartAxis = { kind: "measure", label: "Delinquency rate", column: "dr", unit: "%",
    ticks: [{ value: 0, display: "0.00%" }, { value: 0.05, display: "5.00%" }] };
  const f = fig(chart("combo", {
    y_columns: ["ead", "dr"], y_axis_secondary: secondary,
    points: [pt("Retail", { ead: 40, dr: 0.02 }, { ead: "SAR 40 mn", dr: "2.00%" }, 0),
             pt("Energy", { ead: 90, dr: 0.04 }, { ead: "SAR 90 mn", dr: "4.00%" }, 1)],
  }));
  const [bars, rate] = f.data;
  assert.equal(bars.type, "bar");
  assert.equal(rate.type, "scatter");
  assert.equal(rate.xaxis, "x2");
  assert.deepEqual(rate.x, [0.02, 0.04]);
  assert.deepEqual(cd(rate).map((r) => r[1]), ["2.00%", "4.00%"]);
  const x2 = ax(f, "xaxis2");
  assert.deepEqual(x2.tickvals, [0, 0.05]);
  assert.deepEqual(x2.ticktext, ["0.00%", "5.00%"]);
  assert.equal((x2.title as Fig).text, "Delinquency rate");
  assert.deepEqual((f.layout.annotations as Fig[]).map((a) => a.text), ["2.00%", "4.00%"]);
});

test("pie and donut: points' order, clockwise, display strings, slot colours", () => {
  const pie = fig(chart("pie"));
  const [t] = pie.data;
  assert.equal(t.type, "pie");
  assert.equal(t.sort, false);
  assert.equal(t.direction, "clockwise");
  assert.equal(t.hole, 0);
  assert.deepEqual(t.values, [40, 90, 10]);
  assert.deepEqual(cd(t).map((r) => r[1]), ["SAR 40 mn", "SAR 90 mn", "SAR 10 mn"]);
  assert.ok((t.labels as string[])[0].startsWith("Retail") && (t.labels as string[])[0].endsWith("SAR 40 mn"));
  assert.deepEqual((t.marker as Fig).colors, ["var(--ipm-chart-1)", "var(--ipm-chart-2)", "var(--ipm-chart-3)"]);
  assert.equal(fig(chart("donut")).data[0].hole, 0.55);
});

test("waterfall: running totals, closing total from zero, positive/negative/total colours", () => {
  const f = fig(chart("waterfall", {
    y_axis: undefined,
    points: [
      pt("Opening", { ead: 100 }, { ead: "SAR 100 mn" }, 0),
      pt("New lending", { ead: 30 }, { ead: "SAR 30 mn" }, 1),
      pt("Repayments", { ead: -50 }, { ead: "-SAR 50 mn" }, 2),
      pt("Closing", { ead: 80 }, { ead: "SAR 80 mn" }, 3),
    ],
  }));
  const [t] = f.data;
  assert.deepEqual(t.base, [0, 100, 80, 0]);
  assert.deepEqual(t.x, [100, 30, 50, 80]);
  assert.deepEqual(t.text, ["SAR 100 mn", "SAR 30 mn", "-SAR 50 mn", "SAR 80 mn"]);
  assert.deepEqual((t.marker as Fig).color, ["var(--ipm-positive)", "var(--ipm-positive)", "var(--ipm-negative)", "var(--ipm-text-secondary)"]);
  assert.deepEqual(ax(f, "xaxis").range, [0, 130]);
  assert.equal(ax(f, "xaxis").showticklabels, false);
});

test("bubble: x, y and an area-scaled size; every column's display in the hover", () => {
  const f = fig(chart("bubble", {
    y_columns: ["ead", "dr", "n"],
    x_axis: AXIS,
    points: [pt("A", { ead: 10, dr: 1, n: 100 }, { ead: "SAR 10 mn", dr: "1.0%", n: "100" }, 0),
             pt("B", { ead: 50, dr: 2, n: 25 }, { ead: "SAR 50 mn", dr: "2.0%", n: "25" }, 1)],
  }));
  const [t] = f.data;
  assert.deepEqual(t.x, [10, 50]);
  assert.deepEqual(t.y, [1, 2]);
  const sizes = (t.marker as Fig).size as number[];
  assert.ok(sizes[0] > sizes[1]);
  assert.match(String(cd(t)[0][1]), /SAR 10 mn.*1\.0%.*100/);
  assert.deepEqual(ax(f, "xaxis").ticktext, ["SAR 0 mn", "SAR 50 mn", "SAR 100 mn"]);
  assert.match(String((f.layout.annotations as Fig[])[0].text), /Sized by n/);
});

test("heatmap: absent cells stay null (not zero), display strings in cells and hover", () => {
  const f = fig(chart("heatmap", {
    matrix: {
      row_axis: "From stage", column_axis: "To stage", measure: "borrowers", unit: "borrowers",
      rows: ["S1", "S2"], columns: ["S1", "S2"], square: true,
      cells: { "S1|S1": 120, "S1|S2": 8, "S2|S2": 30 },
      display: { "S1|S1": "120", "S1|S2": "8", "S2|S2": "30" },
    },
  }));
  const main = f.data[1];
  assert.equal(main.type, "heatmap");
  assert.deepEqual(main.z, [[120, 8], [null, 30]]);
  assert.deepEqual(main.text, [["120", "8"], ["", "30"]]);
  assert.equal((main.customdata as unknown[][][])[0][1][2], "8");
  assert.deepEqual(f.data[0].z, [[null, null], [1, null]]);
  assert.deepEqual(ax(f, "yaxis").categoryarray, ["S1", "S2"]);
  assert.equal(ax(f, "yaxis").autorange, "reversed");
  assert.equal((ax(f, "xaxis").title as Fig).text, "To stage");
  assert.equal((f.layout.shapes as Fig[]).length, 2);
});

test("box: the server's five numbers, median display at the row end, no computed stats", () => {
  const f = fig(chart("box", {
    boxes: [
      { label: "Retail", count: 10, unit: "%", minimum: "1", q1: "2", median: "3", q3: "4", maximum: "9", display: { minimum: "1.0%", median: "3.0%", maximum: "9.0%" } },
      { label: "", count: 5, unit: "%", minimum: "0.5", q1: "1", median: "2", q3: "3", maximum: "4", display: { median: "2.0%" } },
    ],
  }));
  const [box, hover] = f.data;
  assert.equal(box.type, "box");
  assert.deepEqual(box.y, ["Retail", "All"]);
  assert.deepEqual(box.median, [3, 2]);
  assert.deepEqual(box.lowerfence, [1, 0.5]);
  assert.deepEqual(box.upperfence, [9, 4]);
  assert.equal(box.hoverinfo, "skip");
  assert.match(String(cd(hover)[0][1]), /min: 1\.0%.*median: 3\.0%.*max: 9\.0%/);
  assert.deepEqual((f.layout.annotations as Fig[]).map((a) => a.text), ["3.0%", "2.0%"]);
});

test("unknown kind falls back like visuals.tsx: 100% stack for >1 column, else bars", () => {
  const stacked = fig(two("ribbon"));
  assert.equal(stacked.layout.barmode, "stack");
  assert.deepEqual(stacked.data[0].x, [0.75, 0.75]);
  const bar = fig(chart("ribbon"));
  assert.equal(bar.data[0].type, "bar");
  assert.equal(bar.data[0].orientation, "h");
});

test("repeated labels stay separate rows and show the label itself", () => {
  const f = fig(chart("bar", { points: [pt("A", { ead: 1 }, { ead: "1" }, 0), pt("A", { ead: 2 }, { ead: "2" }, 1)] }));
  const keys = f.data[0].y as string[];
  assert.equal(new Set(keys).size, 2);
  assert.deepEqual(ax(f, "yaxis").ticktext, ["A", "A"]);
});

test("reader-visible strings are entity-escaped so Plotly draws them as written", () => {
  assert.equal(esc("<30 DPD & >90"), "&lt;30 DPD &amp; &gt;90");
  const f = fig(chart("bar", { points: [pt("<30 DPD", { ead: 1 }, { ead: "1" }, 0), pt("B", { ead: 2 }, { ead: "2" }, 1)] }));
  assert.equal((ax(f, "yaxis").ticktext as string[])[0], "&lt;30 DPD");
});
