import assert from "node:assert/strict";
import { test } from "node:test";

import { sameAsRecommended, vsRows, vsVerdict } from "./dealdesk-vs.ts";

const rec = { raroc: 0.182, sva: 1.4, ecl: 0.31, p_stage2: 0.041 };

test("each figure is compared the right way round", () => {
  const rows = vsRows({ raroc: 0.17, sva: 1.6, ecl: 0.25, p_stage2: 0.05 }, rec);
  assert.deepEqual(rows.map((r) => [r.key, r.better]), [["raroc", false], ["sva", true], ["ecl", true], ["p_stage2", false]]);
  assert.ok(Math.abs((rows[0].delta ?? 0) + 0.012) < 1e-9);
  assert.equal(vsVerdict(rows), "Better on 2 of 4 against the recommended structure, with 1.2 pts less RAROC.");
});

test("the recommended structure on the panel reads as such", () => {
  const rows = vsRows({ ...rec }, rec);
  assert.ok(sameAsRecommended(rows));
  assert.equal(vsVerdict(rows), "This is the recommended structure.");
  assert.ok(rows.every((r) => r.better === null && r.delta === 0));
});

test("missing figures stay missing, never zero", () => {
  const rows = vsRows({ raroc: 0.2, sva: 1, ecl: 0.3, p_stage2: null }, null);
  assert.ok(rows.every((r) => r.delta === null && r.better === null));
  assert.equal(vsVerdict(rows), "Comparing with the recommended structure…");
  const half = vsRows({ raroc: 0.2, sva: 1.5, ecl: 0.3, p_stage2: null }, rec);
  assert.equal(half[3].delta, null);
  assert.match(vsVerdict(half), /of 3 against/);
});
