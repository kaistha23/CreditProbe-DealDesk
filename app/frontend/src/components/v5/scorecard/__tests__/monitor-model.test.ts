import assert from "node:assert/strict";
import { test } from "node:test";

import { ASK_PLACEHOLDER, ASK_STARTERS, day, frontHeadline, newspaper, person, sparkPoints } from "../monitor-model.ts";

test("dates and owners read as a banker writes them", () => {
  assert.equal(day("2026-10-21"), "21 Oct 2026");
  assert.equal(day("2025Q2"), "2025Q2");
  assert.equal(person("Nadia Al-Rashidi (Head of SME Credit Risk)"), "Nadia Al-Rashidi");
});

test("the Ask placeholder is short (M3) and the starters ask for full MMSG validations", () => {
  assert.ok(ASK_PLACEHOLDER.length <= 60);
  assert.ok(ASK_STARTERS.some((s) => /full MMSG validation/i.test(s.send)));
});

test("sparkline points stay in the box and skip missing values", () => {
  const p = sparkPoints([0.1, null, 0.3, 0.2], 100, 20, 2);
  assert.equal(p.length, 3);
  for (const q of p) { assert.ok(q.x >= 0 && q.x <= 100); assert.ok(q.y >= 0 && q.y <= 20); }
  assert.equal(sparkPoints([]).length, 0);
  assert.equal(sparkPoints([1, 1])[0].y, 12);
});

test("the newspaper puts rank 1 in the lead and alternates the rest", () => {
  const n = newspaper([1, 2, 3, 4, 5]);
  assert.equal(n.lead, 1);
  assert.deepEqual(n.columns, [[2, 4], [3, 5]]);
  assert.equal(frontHeadline(10, 3, 10), "10 breaches across 3 scorecards, 10 red");
  assert.equal(frontHeadline(0, 3, 0), "All 3 scorecards are inside their limits");
});
