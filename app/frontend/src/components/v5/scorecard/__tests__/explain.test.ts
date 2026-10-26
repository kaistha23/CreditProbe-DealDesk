import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { TEXT, scorecardChartExplain } from "../explain.ts";

const engine = readFileSync(new URL("../../../../../../backend/scorecard_v5/engine.py", import.meta.url), "utf8");

test("every chart the validation engine draws has a complete explanation", () => {
  const ids = [...engine.matchAll(/charts\.append\(\{"id": "([a-z_]+)"/g)].map((m) => m[1]);
  assert.ok(ids.length >= 17, `found ${ids.length}`);
  assert.match(engine, /"id": f"woe_/);
  for (const id of [...ids, "woe_income"]) {
    assert.ok(TEXT[id.startsWith("woe_") ? "woe" : id], `no text for ${id}`);
    assert.ok(isCompleteExplain(scorecardChartExplain(id, "T", { data: [] })), id);
  }
});

test("the example is read from the figure", () => {
  const roc = scorecardChartExplain("roc", "ROC", { data: [
    { name: "Development", x: [0, 0.1, 0.2, 1], y: [0, 0.5, 0.7, 1] },
    { name: "Monitoring", x: [0, 0.1, 0.21, 1], y: [0, 0.4, 0.65, 1] },
    { name: "No skill", x: [0, 1], y: [0, 1] }] });
  assert.match(roc.read, /false positive rate of \*\*21\.0%\*\* the score catches \*\*65\.0%\*\*/);
  const gini = scorecardChartExplain("gini_trend", "Gini", { data: [{ type: "bar", name: "Gini", x: ["2025Q4", "2026Q1"], y: [0.52, 0.48] },
    { name: "Green threshold", x: ["2025Q4", "2026Q1"], y: [0.45, 0.45] }] });
  assert.match(gini.read, /^2026Q1: Gini \*\*48\.0%\*\*\./);
  const corr = scorecardChartExplain("corr", "Corr", { data: [{ type: "heatmap", x: ["a", "b"], y: ["a", "b"], z: [[1, 0.8], [0.8, 1]] }] });
  assert.match(corr.read, /strongest pair is \*\*a\*\* and \*\*b\*\* at \*\*0\.800\*\*/);
});
