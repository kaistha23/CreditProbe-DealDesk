import assert from "node:assert/strict";
import { test } from "node:test";

import { INTEL_INTENTS, INTEL_INTENTS_IA, dealIdIn, matchIntent } from "./intel-intents-ia.ts";

test("IA intents are registered, unique and point at the intel API", () => {
  const ids = INTEL_INTENTS.map((i) => i.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(INTEL_INTENTS_IA.length, 4);
  for (const i of INTEL_INTENTS_IA) {
    assert.match(i.path, /^\/api\/v1\/dealdesk\/intel\/approval\/\{deal_id\}\/(challenger|reverse|security|consistency)$/);
    assert.ok(i.examples.length >= 2 && i.patterns.length >= 3);
    for (const p of i.patterns) assert.doesNotThrow(() => new RegExp(p));
  }
});

test("each example question routes to its own intent", () => {
  for (const i of INTEL_INTENTS_IA) {
    for (const ex of i.examples) {
      const m = matchIntent(ex, { deal_id: "R12-TWA" });
      assert.ok(m, ex);
      assert.equal(m!.intent.id, i.id, ex);
    }
  }
});

test("deal id from the question beats the context; missing id is no match; book scope for consistency", () => {
  assert.equal(dealIdIn("what will committee ask about r12-twb?"), "R12-TWB");
  assert.equal(matchIntent("What will committee ask about DD-05?", { deal_id: "R12-TWA" })!.url,
               "/api/v1/dealdesk/intel/approval/DD-05/challenger");
  assert.equal(matchIntent("What will committee ask?"), null);
  assert.equal(matchIntent("Are our approvals consistent?")!.url, "/api/v1/dealdesk/intel/approval/book/consistency");
  assert.equal(matchIntent("what is the weather"), null);
});
