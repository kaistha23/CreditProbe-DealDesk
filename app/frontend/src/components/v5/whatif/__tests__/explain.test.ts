import assert from "node:assert/strict";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import {
  bandsExplain, beeswarmExplain, calibrationExplain, compareExplain, cycleExplain, importanceExplain, sensitivitiesExplain, gradeExplain, ratingRowsExplain, reasonsExplain, scenarioWeightsExplain,
  segmentExplain, splitExplain, stageExplain, waterfallExplain,
} from "../explain.ts";

const summary = {
  kind: "book", domain: "corporate", period: "2026Q2", title: "Book", scope_label: "the corporate book",
  labels: { owners: "Borrowers", owner: "Borrower", grade: "Rating", segment: "Sector", book: "Corporate" },
  stages: [{ stage: 1, label: "Stage 1", n: 10, owners: 8, ead: 900, ecl: 5, ead_pct: 90 },
           { stage: 2, label: "Stage 2", n: 2, owners: 2, ead: 100, ecl: 4, ead_pct: 10 }],
  grades: { label: "Rating", order: ["AAA", "D"], rows: [{ grade: "BB", n: 3, owners: 3, ead: 600, ecl: 2, ead_pct: 60 }] },
  split: { label: "Sector", plural: "Sectors", by: "segment", within: "", rows: [{ name: "Construction", n: 4, owners: 4, ead: 300, ecl: 6, ead_pct: 30, coverage_pct: 2 }] },
  bands: [{ band: "critical", label: "Critical", owners: 3, exposures: 4, ead: 50, ecl: 3 }, { band: "watch", label: "Watch", owners: 9, exposures: 9, ead: 80, ecl: 1 }],
  reasons: [{ reason: "Cheque returns", owners: 12, exposures: 15, ead: 70 }],
  top: { n: 0, rows: [] }, cards: {},
};
const empty = { ...summary, stages: [], grades: { ...summary.grades, rows: [] }, split: { ...summary.split, rows: [] }, bands: [], reasons: [] };
const result = { by_scenario: { base: { before: 10, after: 12, weight: 0.5 }, downturn: { before: 20, after: 30, weight: 0.3 } } };

test("every What-If chart explanation has all four parts, with data and empty data", () => {
  for (const s of [summary, empty] as never[]) {
    for (const f of [stageExplain, gradeExplain, splitExplain, reasonsExplain, bandsExplain]) assert.ok(isCompleteExplain(f(s)), f.name);
  }
  const bars = [{ key: "r", label: "Reported", value: 100, kind: "total" }, { key: "pd", label: "PD", value: 12, kind: "driver" },
                { key: "s", label: "Scenario", value: 112, kind: "total" }] as never;
  for (const e of [
    waterfallExplain(bars), waterfallExplain([]),
    segmentExplain([{ segment: "Construction", ead_before: 1, ead_after: 1, ecl_before: 10, ecl_after: 15, reported: 10, change: 5 }], "Sector"),
    segmentExplain([], "Sector"),
    ratingRowsExplain([{ grade: "D", ead_before: 5, ead_after: 9, ecl_before: 1, ecl_after: 2, pd_masterscale_pct: null }], "Rating"),
    ratingRowsExplain([], "Rating"),
    scenarioWeightsExplain(result as never), scenarioWeightsExplain({ by_scenario: {} } as never),
    compareExplain([{ driver: "PD", delta: 3, xgboost: 5 }]), compareExplain([]),
  ]) assert.ok(isCompleteExplain(e), JSON.stringify(e));
});

test("every What-If model-card chart explanation is complete", () => {
  for (const e of [
    calibrationExplain("pd", [{ predicted: 0.01, actual: 0.012 }], []), calibrationExplain("lgd", [], []),
    importanceExplain("gain", "pd", [{ feature: "rating", share_pct: 31.2 }]), importanceExplain("shap", "pd", []),
    beeswarmExplain(["rating"]), beeswarmExplain([]),
    cycleExplain({ "2025": 0.4 }, { "2025": 0.35 }), cycleExplain({}, {}),
    sensitivitiesExplain([{ name: "Oil price", ecl_change_pct: 4.2 }]), sensitivitiesExplain([]),
  ]) assert.ok(isCompleteExplain(e), JSON.stringify(e));
});

test("the example uses the current figures", () => {
  assert.match(stageExplain(summary as never).read, /Stage 2: \*\*SAR 100\.0m of SAR 1,000\.0m\*\* = \*\*10\.0%\*\*/);
  assert.match(waterfallExplain([{ key: "r", label: "Reported", value: 100, kind: "total" }, { key: "pd", label: "PD", value: 12, kind: "driver" },
                                 { key: "s", label: "Scenario", value: 112, kind: "total" }] as never).read, /largest driver is \*\*PD\*\* at \*\*\+SAR 12\.0m\*\*/);
});
