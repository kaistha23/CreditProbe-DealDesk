import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { LOOK, SERIES, SHOWS, tabChartExplain } from "../explain.ts";

const source = readFileSync(new URL("../charts.tsx", import.meta.url), "utf8");

test("every series drawn in Borrower 360 has its formula, and every tab its text", () => {
  const names = [...source.matchAll(/\b(?:bar|line)\("([^"]+)"/g)].map((m) => m[1]);
  assert.ok(names.length > 20);
  for (const n of names) assert.ok(SERIES[n], `no formula for series "${n}"`);
  assert.ok(SERIES.EAD && SERIES.DPD);
  const tabs = [...source.matchAll(/case "([a-z-]+)":/g)].map((m) => m[1]);
  assert.ok(tabs.length >= 10);
  for (const t of tabs) {
    assert.ok(LOOK[t] && SHOWS[t], `no text for tab ${t}`);
    assert.ok(isCompleteExplain(tabChartExplain(t, "A chart", [])), t);
  }
});

test("the example reads the latest value of each series, grades as grades", () => {
  const e = tabChartExplain("ratings", "Rating every quarter", [
    { name: "Rating", x: ["Q1 26", "Q2 26"], y: [10, 12], customdata: ["BB", "B+"] },
    { name: "PD (TTC 12m, %)", x: ["Q1 26", "Q2 26"], y: [1.5, 2.25] },
  ]);
  assert.ok(isCompleteExplain(e));
  assert.equal(e.read, "At Q2 26: Rating **B+**, PD (TTC 12m, %) **2.25**. Hover any point for its exact value.");
  assert.equal(e.formula.length, 2);
  const x = tabChartExplain("exposure", "EAD", [{ name: "EAD F-1", x: ["Q2 26"], y: [12.5] }, { name: "EAD F-2", x: ["Q2 26"], y: [3] }]);
  assert.equal(x.formula.length, 1);
});
