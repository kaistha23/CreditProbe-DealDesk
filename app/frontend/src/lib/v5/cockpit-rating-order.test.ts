import assert from "node:assert/strict";
import { test } from "node:test";

import { compareRatingValues, withRatingOrder } from "./cockpit-rating-order.ts";

test("a chart of rating grades is drawn AAA to D, points otherwise untouched", () => {
  const chart = { title: "EAD by rating", points: [{ label: "CCC", v: 1 }, { label: "AA", v: 2 }, { label: "C", v: 3 },
    { label: "BBB-", v: 4 }] };
  const out = withRatingOrder(chart);
  assert.deepEqual(out.points.map((p) => p.label), ["AA", "BBB-", "CCC", "C"]);
  assert.deepEqual(out.points.map((p) => p.v), [2, 4, 1, 3]);
  assert.equal(out.title, chart.title);
});

test("a chart with any non-grade category keeps the server's order", () => {
  const chart = { points: [{ label: "Construction" }, { label: "AA" }] };
  assert.equal(withRatingOrder(chart), chart);
});

test("table comparison uses the scale only for grades", () => {
  assert.ok((compareRatingValues("BB+", "BBB-") ?? 0) > 0);
  assert.equal(compareRatingValues("Riyadh", "AA"), null);
});
