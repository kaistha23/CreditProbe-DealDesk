import assert from "node:assert/strict";
import { test } from "node:test";

import { isQuietTrend, periodWord, quietTrendNote } from "./ews-trend.ts";

const q = (period: string, w: number | null, o: number | null, s: number | null) =>
  ({ period, customers_warned: w, odr_pct: o, exposure_severe: s });
const QUARTERS = ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"];

test("all three series zero in every period: one line with the number of periods shown", () => {
  const trend = QUARTERS.map((p) => q(p, 0, 0, 0));
  assert.equal(isQuietTrend(trend), true);
  assert.equal(quietTrendNote(trend), "No warnings in 6 quarters");
  const eight = ["2024Q3", "2024Q4", ...QUARTERS].map((p) => q(p, 0, 0, 0));
  assert.equal(quietTrendNote(eight), "No warnings in 8 quarters");
});

test("monthly books say months", () => {
  const trend = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"].map((p) => q(p, 0, 0, 0));
  assert.equal(quietTrendNote(trend), "No warnings in 6 months");
  assert.equal(periodWord(["2026-08"], 1), "month");
});

test("any non-zero value in any series keeps the sparklines", () => {
  // Healthcare in Dammam: one warned borrower in the first quarter, zeros after.
  assert.equal(quietTrendNote(QUARTERS.map((p, i) => q(p, i === 0 ? 1 : 0, 0, 0))), null);
  assert.equal(quietTrendNote(QUARTERS.map((p, i) => q(p, 0, i === 5 ? 2.2 : 0, 0))), null);
  assert.equal(quietTrendNote(QUARTERS.map((p, i) => q(p, 0, 0, i === 3 ? 21.4 : 0))), null);
});

test("no data is not 'no warnings'", () => {
  assert.equal(quietTrendNote([]), null);
  assert.equal(quietTrendNote(QUARTERS.map((p) => q(p, null, null, null))), null);
});
