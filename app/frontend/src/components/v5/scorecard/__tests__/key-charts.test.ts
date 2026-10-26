import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { browserLayout, chartTitle } from "../chart-layout.ts";
import { TEXT, scorecardChartExplain } from "../explain.ts";
import { KEY_CHARTS, keyCharts } from "../key-charts.ts";

// The key charts of a Retail Application Scorecard run, as the Scorecard service returns them (engine.run, house style).
const fixture = JSON.parse(readFileSync(new URL("./fixtures/key-charts.json", import.meta.url), "utf8"));
const engine = readFileSync(new URL("../../../../../../backend/scorecard_v5/engine.py", import.meta.url), "utf8");

const REQUIRED: Record<string, string> = {
  roc: "ROC", cap: "CAP", gini_trend: "Gini by period", ks_trend: "KS by period", gini_segment: "Gini by segment", ks_segment: "KS by segment",
  oe_grade: "observed vs expected by grade", psi_trend: "PSI by period", csi_bar: "CSI by variable", ovr_outcome: "override outcomes",
};

test("the browser's key-chart list is the engine's, and covers every chart PLAN_R10 C3 asks for", () => {
  const m = engine.match(/^KEY_CHARTS = \[([^\]]+)\]/m);
  assert.ok(m, "engine.KEY_CHARTS not found");
  assert.deepEqual([...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]), [...KEY_CHARTS]);
  for (const id of Object.keys(REQUIRED)) assert.ok((KEY_CHARTS as readonly string[]).includes(id), REQUIRED[id]);
});

test("each key chart of a run renders: a figure with data, a card title, a browser layout and a complete (i)", () => {
  const charts = keyCharts(fixture);
  assert.deepEqual(charts.map((c) => c.id), Object.keys(REQUIRED));
  for (const c of charts) {
    const series = c.figure.data.filter((t) => !/threshold|perfect|random|no skill|^0\.\d+$/i.test(String(t.name ?? "")));
    assert.ok(series.length, `${c.id}: no data series`);
    for (const t of series) {
      const vals = (Array.isArray(t.x) ? t.x : []).concat(Array.isArray(t.y) ? t.y : []);
      assert.ok(vals.length > 0, `${c.id}: empty series ${String(t.name)}`);
    }
    assert.ok(chartTitle(c.figure, c.title).length > 0, c.id);
    const layout = browserLayout(c.figure);
    assert.equal((layout.title as { text: string }).text, "", c.id);
    assert.ok(typeof layout.height === "number" && layout.height >= 240, c.id);
    assert.ok(TEXT[c.id], `${c.id}: no (i) text`);
    const ex = scorecardChartExplain(c.id, c.title, c.figure);
    assert.ok(isCompleteExplain(ex), c.id);
    // the (i) example is read off this run's numbers, never a raw decimal for a share
    assert.match(ex.read, /\*\*/, `${c.id}: no figure in the (i) example`);
    if (TEXT[c.id].pct) assert.doesNotMatch(ex.read, /\*\*0\.\d+\*\*/, `${c.id}: raw decimal`);
  }
});

test("the service's list decides the order; a stored result without one falls back to KEY_CHARTS, missing charts are skipped", () => {
  assert.deepEqual(keyCharts(fixture, ["psi_trend", "roc"]).map((c) => c.id), ["psi_trend", "roc"]);
  const old = { sections: fixture.sections.filter((s: { id: string }) => s.id !== "overrides") };
  const ids = keyCharts(old).map((c) => c.id);
  assert.ok(!ids.includes("ovr_outcome") && ids[0] === "roc" && ids.length === KEY_CHARTS.length - 1);
});
