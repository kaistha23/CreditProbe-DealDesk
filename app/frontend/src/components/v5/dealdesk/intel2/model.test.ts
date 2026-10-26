import assert from "node:assert/strict";
import { test } from "node:test";

import { INTEL2_FEATURES, featuresForStep, signedBps, verdictTone } from "./model.ts";

test("R14 i: eight features D6-D13, unique panel keys, D13 on the challenger key (K29)", () => {
  assert.deepEqual(INTEL2_FEATURES.map((f) => f.code), ["D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13"]);
  assert.equal(new Set(INTEL2_FEATURES.map((f) => f.panel)).size, 8);
  assert.equal(INTEL2_FEATURES.find((f) => f.code === "D13")?.panel, "challenger");
});

test("R14 i: each step shows what the plan places there; renewal diff only on renewals", () => {
  const keys = (s: string, c?: string) => featuresForStep(s, c).map((f) => f.key);
  assert.deepEqual(keys("structure"), ["frontier", "pricing"]);
  assert.deepEqual(keys("review"), ["precedents", "revenue", "contagion"]);
  assert.deepEqual(keys("analysis"), ["premortem"]);
  assert.ok(keys("proposal", "renewal").includes("renewal-diff"));
  assert.ok(!keys("proposal", "new").includes("renewal-diff"));
  assert.deepEqual(keys("stress"), []);
});

test("R14 i: helpers", () => {
  assert.equal(signedBps(26.7), "+27 bps");
  assert.equal(signedBps(-13.3), "−13 bps");
  assert.equal(verdictTone("not supported"), "negative");
});
