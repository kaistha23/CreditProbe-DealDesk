import assert from "node:assert/strict";
import { test } from "node:test";

import { isCompleteExplain } from "../../core/chart-explain-core.ts";
import { cardTrendExplain, compareExplain, customerHistoryExplain, levelTrendExplain, ratingExplain } from "../explain.ts";

const tp = (period: string, w: number) => ({
  period, customers_warned: w, high_or_critical: 3, current_bad: 1, forward_risk: 2, exposure_severe: 41.5,
  exposure_warned_pct: 10, odr_pct: 1.25, warned_pct: 8,
});
const trend = [tp("2026Q1", 10), tp("2026Q2", 12)];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const card = (label: string, customers: number, warned: number) => ({ key: label, label, customers, customers_warned: warned, exposure_severe: 20 }) as any;

test("every Early Warning chart explanation has all four parts, with data and empty data", () => {
  for (const e of [
    levelTrendExplain(trend, "borrowers"), levelTrendExplain([], "borrowers"),
    cardTrendExplain(trend, "borrowers", "Construction"), cardTrendExplain([], "customers"),
    compareExplain([card("Construction", 140, 12), card("Retail", 90, 4)], "borrowers", "sectors"), compareExplain([], "borrowers", ""),
    ratingExplain([{ rating: "BB", borrowers: 50, warned: 5, high_or_critical: 1, exposure: 9 }], "borrowers"), ratingExplain([], "borrowers"),
    customerHistoryExplain([{ period: "2026Q2", score: 61, band: "high", dpd: 12, stage: 2, exposure: 3.2 }] as never, 40, "borrower"),
    customerHistoryExplain([], 40, "customer"),
  ]) assert.ok(isCompleteExplain(e), JSON.stringify(e));
});

test("the example is computed from the current figures", () => {
  const e = compareExplain([card("Construction", 140, 12), card("Retail", 90, 4)], "borrowers", "sectors");
  assert.match(e.read, /Construction: \*\*12 of 140\*\* borrowers warned = \*\*8\.6%\*\*/);
  assert.match(levelTrendExplain(trend, "borrowers").read, /Q2 26: \*\*12\*\* borrowers warned/);
});
