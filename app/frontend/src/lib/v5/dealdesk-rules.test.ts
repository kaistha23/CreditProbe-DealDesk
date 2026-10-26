import assert from "node:assert/strict";
import { test } from "node:test";

import { APPLIED_LABEL, type RuleApplied, appliedLine, assessKindOf, rules, rulebook } from "./dealdesk-rules.ts";

const row = (status: RuleApplied["status"]): RuleApplied => ({
  rule_id: "R", text: "t", kind: "wording", scope: "me", scope_label: "Me", author: "a", author_name: "A", document: "both", section: "",
  origin: "analyst", created_at: "", status, effect: "", count: 0,
});

test("the Rules applied line counts what changed and what the analyst must fix", () => {
  assert.equal(appliedLine([row("applied"), row("in_place"), row("flagged"), row("noted")]),
    "4 rules in force · 1 changed this document · 1 already followed · 1 for you to fix");
  assert.equal(appliedLine([row("in_place")]), "1 rule in force · 0 changed this document · 1 already followed");
  assert.equal(APPLIED_LABEL.flagged, "For you to fix");
});

test("Policy Docs kinds map to the rulebook's two reading kinds", () => {
  assert.equal(assessKindOf("circular"), "regulation");
  assert.equal(assessKindOf("regulation"), "regulation");
  assert.equal(assessKindOf("policy"), "policy");
  assert.equal(assessKindOf("guideline"), "policy");
});

test("the client calls the Deal Desk rules and rulebook routes", async () => {
  const seen: { url: string; method: string; body: unknown }[] = [];
  const real = globalThis.fetch;
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    seen.push({ url: String(url), method: init.method ?? "GET", body: init.body });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }) as typeof fetch;
  try {
    await rules.suggest({ instruction: "Say obligor, not client", section: "summary" });
    await rules.list({ scope: "bank" });
    await rulebook.decide("PA-1", true, "", "pd-1");
    await rulebook.flags({ proposal_id: "DD-02" });
  } finally {
    globalThis.fetch = real;
  }
  assert.match(seen[0].url, /\/api\/v1\/dealdesk\/rules\/suggest$/);
  assert.equal(seen[0].method, "POST");
  assert.match(seen[1].url, /\/rules\?scope=bank$/);
  assert.match(seen[2].url, /\/rulebook\/assessments\/PA-1\/decision$/);
  assert.deepEqual(JSON.parse(String(seen[2].body)), { approve: true, note: "", policy_doc_id: "pd-1" });
  assert.match(seen[3].url, /\/rulebook\/flags\?proposal_id=DD-02$/);
});

test("an error status becomes a readable error", async () => {
  const real = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "Sign in" }), { status: 401 })) as typeof fetch;
  try {
    await assert.rejects(rules.create({ text: "x", scope: "me", document: "both" }), (e: Error & { status?: number }) => e.status === 401);
  } finally {
    globalThis.fetch = real;
  }
});
