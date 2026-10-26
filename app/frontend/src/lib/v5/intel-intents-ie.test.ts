import assert from "node:assert/strict";
import { test } from "node:test";

import { GOVERNANCE_INTENTS, INTEL_INTENTS, intentFor, intentHref, intentsForMenu } from "./intel-intents-ie.ts";

test("IE: four governance intents, one API and one panel each, exported to Admin and Deal Desk tools", () => {
  assert.deepEqual(GOVERNANCE_INTENTS.map((i) => i.id), ["inspection", "exceptions", "rm-track", "doa"]);
  assert.deepEqual(GOVERNANCE_INTENTS.map((i) => i.backlog), [18, 19, 21, 22]);
  for (const i of GOVERNANCE_INTENTS) {
    assert.ok(i.api.path.startsWith("/api/v1/intel/governance/"), i.id);
    assert.ok(i.menus.includes("admin-tools") && i.menus.includes("dealdesk-tools"), i.id);
    assert.ok(i.href.includes(`gov=${i.id}`));
    assert.ok(i.examples.length >= 2);
    for (const c of i.cues) new RegExp(c, "i");
  }
  assert.equal(new Set(INTEL_INTENTS.map((i) => i.id)).size, INTEL_INTENTS.length);
  assert.equal(intentsForMenu("admin-tools").length, 4);
});

test("IE: Noor routes governance questions to the right engine", () => {
  const cases: [string, string][] = [
    ["The auditor wants approvals, conditions and stage for the 5 largest Stage 3 borrowers", "inspection"],
    ["SAMA inspection sample: CB00039, R12-TWA", "inspection"],
    ["Which policy exceptions lead to defaults?", "exceptions"],
    ["Which RMs book worse than the risk they take?", "rm-track"],
    ["Rank the branches: branch performance on conditions", "rm-track"],
    ["Which approval levels slow deals without changing them?", "doa"],
    ["Propose a new delegation of authority", "doa"],
  ];
  for (const [q, id] of cases) assert.equal(intentFor(q)?.id, id, q);
  for (const i of GOVERNANCE_INTENTS) for (const ex of i.examples) assert.equal(intentFor(ex)?.id, i.id, ex);
  assert.equal(intentFor("What is the ECL of the book?"), null);
  assert.equal(intentFor(""), null);
});

test("IE: the href carries the question", () => {
  const i = GOVERNANCE_INTENTS[0];
  assert.equal(intentHref(i), "/deal-desk?gov=inspection");
  assert.equal(intentHref(i, " stage for CB00039 "), "/deal-desk?gov=inspection&q=stage%20for%20CB00039");
});
