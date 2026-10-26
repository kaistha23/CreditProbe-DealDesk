import assert from "node:assert/strict";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { playbookChartExplain } from "../explain.ts";

test("every Playbook chart explanation is complete: content charts, scorecard charts, anything else, empty", () => {
  const titles = [
    "ECL and EAD, last 8 quarters", "Construction: EAD by stage, 2026Q1 and 2026Q2 (SAR bn)", "Borrowers by Early Warning band, 2026Q1 and 2026Q2",
    "Construction: ECL change by sub-sector, 2026Q1 to 2026Q2 (SAR m)", "DSCR and leverage, last 8 quarters",
    "ROC curve", "CAP curve", "Gini by period", "Observed vs expected by grade", "Observed vs expected over time", "Score PSI by period",
    "CSI by variable", "Score distribution", "Information value", "Default rate by override decision", "Something from a Lens", "",
  ];
  const fig = { data: [{ type: "bar", name: "EAD (SAR bn)", x: ["Q1 26", "Q2 26"], y: [10.5, 11.25] }], layout: { yaxis: { title: { text: "SAR bn" } } } };
  for (const t of titles) {
    for (const f of [fig, null, { data: [] }]) assert.ok(isCompleteExplain(playbookChartExplain(t, f)), `${t} ${JSON.stringify(f)}`);
  }
});

test("the example reads the latest values of the figure", () => {
  const e = playbookChartExplain("ECL and EAD, last 8 quarters", { data: [
    { type: "bar", name: "EAD (SAR bn)", x: ["Q1 26", "Q2 26"], y: [10.5, 11.25] },
    { type: "scatter", name: "ECL (SAR m)", x: ["Q1 26", "Q2 26"], y: [210, 236.4] }] });
  assert.equal(e.read, "Q2 26: EAD (SAR bn) **11.3**, ECL (SAR m) **236.4**. Hover any point for its exact value.");
  assert.match(e.formula[1], /PD × LGD × EAD/);
});
