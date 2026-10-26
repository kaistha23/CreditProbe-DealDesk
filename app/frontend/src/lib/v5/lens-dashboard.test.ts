import assert from "node:assert/strict";
import { test } from "node:test";

import { LABEL_MAX, STRIP_CLASSES, deltaArrow, lensFigure, periodLine, stripCols, toneOf } from "./lens-dashboard.ts";

test("lensFigure hands font, background, hover and grid to the house theme", () => {
  const fig = {
    data: [{ type: "bar", x: ["a"], y: [1], marker: { color: ["#2563A8", "#A92A25"] } }],
    layout: { font: { family: "Inter", color: "#334155" }, paper_bgcolor: "rgba(0,0,0,0)", hoverlabel: { bgcolor: "#fff" },
              xaxis: { gridcolor: "rgba(1,1,1,0.1)", title: { text: "x" } }, yaxis: { gridcolor: "#eee" }, showlegend: false },
  };
  const out = lensFigure(fig);
  assert.equal(out.layout.font, undefined);
  assert.equal(out.layout.paper_bgcolor, undefined);
  assert.equal(out.layout.hoverlabel, undefined);
  assert.equal((out.layout.xaxis as Record<string, unknown>).gridcolor, undefined);
  assert.deepEqual((out.layout.xaxis as Record<string, unknown>).title, { text: "x" });
  assert.deepEqual((out.data[0].marker as Record<string, unknown>).color, ["var(--ipm-chart-1)", "var(--ipm-negative)"]);
  assert.equal(out.layout.showlegend, false);
  assert.equal((fig.layout.font as Record<string, unknown>).family, "Inter");      // the input is not mutated
});

test("lensFigure shows the house legend on multi-series charts", () => {
  const out = lensFigure({ data: [{ type: "scatter", name: "ECL" }, { type: "scatter", name: "Coverage" }],
                           layout: { showlegend: false, legend: { y: 1.12 }, margin: { t: 12 } } });
  assert.equal(out.layout.showlegend, true);
  assert.equal((out.layout.legend as Record<string, unknown>).orientation, "h");
  assert.equal((out.layout.margin as Record<string, number>).t, 28);
});

test("stripCols: one row of up to 8 without the panel, two even rows with it", () => {
  assert.equal(stripCols(8, false), "grid-cols-2 sm:grid-cols-4 2xl:grid-cols-8");
  assert.equal(stripCols(8, true), "grid-cols-2 sm:grid-cols-4");
  assert.equal(stripCols(6, true), "grid-cols-2 sm:grid-cols-3");
  assert.equal(stripCols(3, true), "grid-cols-2 sm:grid-cols-3");
  assert.equal(stripCols(12, false), "grid-cols-2 sm:grid-cols-4 2xl:grid-cols-8");
  for (const n of [1, 2, 3, 4, 5, 6, 7, 8]) for (const p of [true, false])
    for (const c of stripCols(n, p).split(" ")) assert.ok(STRIP_CLASSES.split(" ").includes(c), c);
});

test("deltaArrow, toneOf, periodLine", () => {
  assert.equal(deltaArrow(2), "▲");
  assert.equal(deltaArrow(-0.1), "▼");
  assert.equal(deltaArrow(0), "");
  assert.equal(deltaArrow(null), "");
  assert.equal(toneOf("bad"), "bad");
  assert.equal(toneOf("x"), "neutral");
  assert.equal(periodLine("2026Q2", "2026Q1"), "2026Q2 against 2026Q1");
  assert.equal(periodLine("2026Q2", ""), "2026Q2");
});

test("lensFigure shortens long hbar labels on the axis only and drops decimals on large amount ticks", () => {
  const long = "2 or more bureau enquiries this quarter";
  const out = lensFigure({ data: [{ type: "bar", orientation: "h", y: [long, "Short"], x: [12000, 300] }],
                           layout: { xaxis: { tickformat: ",.1f" }, yaxis: { type: "category" }, margin: { l: 140, t: 12 } } });
  const y = out.layout.yaxis as Record<string, unknown>;
  assert.deepEqual(y.tickvals, [long, "Short"]);
  assert.ok((y.ticktext as string[])[0].length <= LABEL_MAX && (y.ticktext as string[])[0].endsWith("…"));
  assert.equal((out.data[0].y as string[])[0], long);                    // hover keeps the full name
  assert.equal((out.layout.margin as Record<string, unknown>).l, undefined);
  assert.equal((out.layout.xaxis as Record<string, unknown>).tickformat, ",.0f");
});
