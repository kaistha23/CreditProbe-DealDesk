import assert from "node:assert/strict";
import { test } from "node:test";

import { ID_INTENTS, INTEL_INTENTS, borrowerIdIn, intentUrl, intentsForMenu, matchIntelIntent } from "./intel-intents-id.ts";

test("every ID example routes to its own intent", () => {
  for (const i of ID_INTENTS) {
    for (const ex of i.examples) {
      const m = matchIntelIntent(ex);
      assert.ok(m, ex);
      assert.equal(m.intent.id, i.id, `${ex} -> ${m.intent.id}`);
    }
  }
});

test("ID intents: five engines, unique ids, Lenses and Book menus, portfolio endpoints", () => {
  assert.equal(ID_INTENTS.length, 5);
  assert.equal(new Set(INTEL_INTENTS.map((i) => i.id)).size, INTEL_INTENTS.length);
  assert.deepEqual(ID_INTENTS.map((i) => i.backlog).sort((a, b) => a - b), [11, 14, 15, 16, 17]);
  for (const i of ID_INTENTS) {
    assert.ok(i.endpoint.startsWith("/api/v1/intel/portfolio/"));
    assert.ok(i.menus.includes("lenses") && i.menus.includes("book"));
  }
  assert.equal(intentsForMenu("book").length, 5);
});

test("workout needs a borrower id and fills it", () => {
  const m = matchIntelIntent("Should we reschedule or sell cb00002?");
  assert.ok(m);
  assert.equal(m.intent.id, "portfolio.workout");
  assert.equal(m.borrowerId, "CB00002");
  assert.equal(intentUrl(m), "/api/v1/intel/portfolio/workout/CB00002");
  const n = matchIntelIntent("workout options please");
  assert.ok(n);
  assert.equal(intentUrl(n), null);
  assert.equal(borrowerIdIn("nothing here"), null);
});

test("no match on an unrelated question", () => {
  assert.equal(matchIntelIntent("what is the weather in Riyadh"), null);
});
