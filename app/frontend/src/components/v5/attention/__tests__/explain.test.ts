import assert from "node:assert/strict";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { contributorsExplain, peersExplain, stageMixExplain, trendExplain } from "../explain.ts";

const view = { key: "sector", label: "Sector", from: 100, to: 130, total_change: 30,
               items: [{ name: "Construction", id: "c", from: 40, to: 64, change: 24 }, { name: "Retail", id: "r", from: 60, to: 66, change: 6 }] };
const c = {
  domain: "corporate", family: "ecl", segment: "construction", segment_label: "Construction", dimension: "sector", dimension_label: "Sector",
  scope: "segment", measure: "ecl", measure_label: "ECL", kind: "amount", unit: "SAR m", period: "2026Q2", comparison_period: "2026Q1",
  period_noun: "quarter",
  trend: { periods: ["2026Q1", "2026Q2"], segment: [40, 64], book: [100, 130], current_index: 1 },
  peers: { period: "2026Q2", items: [{ segment: "construction", label: "Construction", value: 64, rows: 3, is_segment: true },
                                     { segment: "retail", label: "Retail", value: 66, rows: 3, is_segment: false }], book: 130, book_label: "Book" },
  contributors: { before: "2026Q1", after: "2026Q2", views: [view] },
  stage_mix: { periods: ["2026Q1", "2026Q2"], stages: [1, 2, 3], ead: [[800, 150, 50], [760, 180, 60]], unit: "SAR m", basis: "EAD" },
  source: "test",
};
const empty = { ...c, trend: { periods: [], segment: [], book: [], current_index: 0 }, peers: { ...c.peers, items: [], book: null },
                contributors: { before: "a", after: "b", views: [] }, stage_mix: { ...c.stage_mix, ead: [] } };

test("every Cockpit drawer chart explanation has all four parts, with data and empty data", () => {
  for (const x of [c, empty, { ...c, kind: "share", scope: "portfolio" }] as never[]) {
    assert.ok(isCompleteExplain(trendExplain(x)));
    assert.ok(isCompleteExplain(peersExplain(x)));
    assert.ok(isCompleteExplain(contributorsExplain(x, (x as typeof c).contributors.views[0])));
    assert.ok(isCompleteExplain(stageMixExplain(x)));
  }
});

test("the example uses the current figures", () => {
  assert.match(peersExplain(c as never).read, /Construction: \*\*SAR 64\.0m\*\*, rank \*\*2 of 2\*\*/);
  assert.match(contributorsExplain(c as never, view).read, /Construction: .*\(80\.0%\)/);
  assert.match(stageMixExplain(c as never).read, /Stage 2 holds \*\*SAR 180m of SAR 1,000m\*\* = \*\*18\.0%\*\*/);
});
