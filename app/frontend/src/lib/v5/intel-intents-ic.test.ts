import { test } from "node:test";
import assert from "node:assert/strict";

import { IC_INTENTS, INTEL_INTENTS, employerOf, failedBorrower, matchIntent } from "./intel-intents-ic.ts";

test("every IC example matches its own intent", () => {
  for (const intent of IC_INTENTS) {
    for (const ex of intent.examples) {
      const m = matchIntent(ex, { borrowerId: "CB03184" });
      assert.ok(m, `no match for ${ex}`);
      assert.equal(m.intent.id, intent.id, ex);
    }
  }
});

test("oil question posts the text to the event translator", () => {
  const m = matchIntent("What if oil falls 30% this morning, severe?");
  assert.equal(m?.intent.id, "intel.network.event");
  assert.equal(m?.request.method, "POST");
  assert.equal(m?.request.path, "/api/v1/intel/network/event");
  assert.deepEqual(m?.request.body, { text: "What if oil falls 30% this morning, severe?", severity: "severe" });
});

test("a failure question goes to contagion, not the event translator", () => {
  const m = matchIntent("What if Al Ahsa Energy fails?");
  assert.equal(m?.intent.id, "intel.network.contagion");
  assert.equal(m?.request.path, "/api/v1/intel/network/contagion/Al%20Ahsa%20Energy");
  assert.equal(failedBorrower("if CB00002 defaults", {}), "CB00002");
  assert.equal(failedBorrower("if this borrower fails", { borrowerId: "CB01045" }), "CB01045");
  assert.equal(matchIntent("show the contagion map"), null);            // no borrower named or on screen
});

test("employer questions name the employer or open the ranking", () => {
  assert.equal(employerOf("What is our exposure to Saadiyat Crest Developments through its contractors?", {}), "Saadiyat Crest Developments");
  const m = matchIntent("Which project employers are we most exposed to?");
  assert.equal(m?.intent.id, "intel.network.employer");
  assert.equal(m?.request.path, "/api/v1/intel/network/employers?limit=10");
  const p = matchIntent("employer exposure for this developer", { borrowerId: "CB03616", period: "2026Q2" });
  assert.equal(p?.request.path, "/api/v1/intel/network/employer/CB03616?period=2026Q2");
});

test("unrelated questions do not match; descriptors are complete", () => {
  assert.equal(matchIntent("What is the cost of risk this quarter?"), null);
  assert.equal(matchIntent("   "), null);
  for (const i of INTEL_INTENTS) {
    assert.ok(i.backlog >= 1 && i.backlog <= 22 && i.panel && i.examples.length >= 2 && i.modules.length);
    assert.equal(i.answer.headline, "text.headline");
  }
});
