import assert from "node:assert/strict";
import { test } from "node:test";

import { browserLayout, chartTitle } from "../chart-layout.ts";

const twoSeries = {
  data: [{ type: "bar", name: "Development", orientation: "h" }, { type: "bar", name: "Monitoring", orientation: "h" }],
  layout: { title: { text: "Information value by variable" }, height: 400, margin: { l: 8, r: 16, t: 76, b: 44 },
            legend: { orientation: "h", y: 1.02, yanchor: "bottom" }, yaxis: { automargin: true, ticktext: ["a"] } },
};

test("the title moves to the card heading and the top margin shrinks to the legend", () => {
  const l = browserLayout(twoSeries);
  assert.equal((l.title as { text: string }).text, "");
  assert.equal((l.margin as { t: number }).t, 36);
  assert.equal(l.height, 360);
  assert.equal(chartTitle(twoSeries, "x"), "Information value by variable");
});

test("the legend stays above the plot area and both axes keep automargin", () => {
  const l = browserLayout({ data: twoSeries.data, layout: { xaxis: { automargin: false } } });
  const legend = l.legend as { y: number; yanchor: string };
  assert.ok(legend.y >= 1 && legend.yanchor === "bottom");
  assert.equal((l.xaxis as { automargin: boolean }).automargin, true);
  assert.equal((l.yaxis as { automargin: boolean }).automargin, true);
});

test("a single series has no legend band", () => {
  const l = browserLayout({ data: [{ type: "bar", name: "CSI" }], layout: { title: "CSI by variable" } });
  assert.equal((l.margin as { t: number }).t, 12);
  assert.equal(chartTitle({ data: [], layout: { title: "CSI by variable" } }, "x"), "CSI by variable");
  assert.equal(chartTitle({ data: [], layout: {} }, "Fallback"), "Fallback");
});

test("the input figure is not changed", () => {
  const before = JSON.stringify(twoSeries);
  browserLayout(twoSeries);
  assert.equal(JSON.stringify(twoSeries), before);
});
