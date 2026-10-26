import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { contextFromLocation, routeHere } from "./noor-context.ts";

// The same cases as tests/v5/noor/test_r15_here.py (backend/agents_v5/brief/here.py): both routers agree.
const CASES = JSON.parse(readFileSync(new URL("../../../../tests/v5/noor/here_cases.json", import.meta.url), "utf8")).cases as
  { q: string; ctx: { deal_id: string | null; step: string | null; stress_on_screen?: boolean }; here: boolean; topic?: string }[];

test("L9: the page context comes from the location (deal, step); other Deal Desk pages are not deals", () => {
  const c = contextFromLocation("/deal-desk/DD-02", "?step=stress");
  assert.equal(c.deal_id, "DD-02");
  assert.equal(c.step, "stress");
  assert.equal(c.module, "deal-desk");
  for (const p of ["/deal-desk", "/deal-desk/thread/abc", "/deal-desk/parameters", "/deal-desk/review", "/what-if", "/"]) {
    assert.equal(contextFromLocation(p, "?step=stress").deal_id, null, p);
  }
  assert.equal(contextFromLocation("/deal-desk/DD%2007", "").deal_id, "DD 07");
});

test("L9: routing cases equal to the backend's", () => {
  for (const c of CASES) {
    const ctx = { module: "deal-desk", path: c.ctx.deal_id ? `/deal-desk/${c.ctx.deal_id}` : "/", deal_id: c.ctx.deal_id,
                  step: c.ctx.step, structures: [], stress_on_screen: Boolean(c.ctx.stress_on_screen) };
    const r = routeHere(c.q, ctx);
    assert.equal(r.here, c.here, c.q);
    if (r.here) assert.equal(r.topic, c.topic, c.q);
    else if (c.ctx.deal_id && c.q) assert.ok(r.reason, `says why: ${c.q}`);
  }
});

test("L9: the R14 question on DD-02 Stress stays on the page; without a deal the usual routes apply", () => {
  const ctx = contextFromLocation("/deal-desk/DD-02", "?step=stress");
  const r = routeHere("how is this failing on all stress scenario?", ctx);
  assert.ok(r.here && r.topic === "stress");
  assert.match(r.reason ?? "", /DD-02, Stress step/);
  assert.equal(routeHere("how is this failing on all stress scenario?", contextFromLocation("/what-if", "")).here, false);
});
