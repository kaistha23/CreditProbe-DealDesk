import assert from "node:assert/strict";
import { test } from "node:test";

import { INTEL_INTENTS_I, matchIntentI } from "./intel-intents-i.ts";
import { INTEL_ROUTES, intelHref, routeIntel } from "./intel-intents.ts";

const key = (q: string, ctx = {}) => routeIntel(q, ctx)?.route.key ?? null;

test("R14 i: eight intents, D6-D13, each with a panel and examples", () => {
  assert.deepEqual(INTEL_INTENTS_I.map((i) => i.code).sort(), ["D10", "D11", "D12", "D13", "D6", "D7", "D8", "D9"]);
  for (const it of INTEL_INTENTS_I) {
    assert.ok(it.examples.length >= 2 && it.panel && it.path.includes("/api/v1/dealdesk/intel2/{deal_id}/"));
    for (const ex of it.examples) assert.equal(matchIntentI(ex)?.intent.id, it.id, ex);
  }
});

test("R14 i: registered in the Noor registry and routed from plain questions", () => {
  const cases: [string, string][] = [
    ["What is 10% cash margin worth in bps on DD-06?", "frontier"],
    ["Give me three counter-offers the client will accept.", "frontier"],
    ["How could DD-06 go bad?", "premortem"],
    ["Show me the closest past deals to DD-06.", "precedents"],
    ["Is this margin in line with the book?", "pricing"],
    ["Is R12-TWA's reported revenue real?", "revenue-check"],
    ["What changed since the last approval of R12-TWA?", "renewal-diff"],
    ["Are any connected parties of DD-06 in Stage 3 or litigation?", "group-contagion"],
    ["Rehearse the committee for DD-06.", "challenger"],
  ];
  for (const [q, k] of cases) assert.equal(key(q), k, q);
  for (const k of ["frontier", "premortem", "precedents", "pricing", "revenue-check", "renewal-diff", "group-contagion"]) {
    assert.ok(INTEL_ROUTES.some((r) => r.key === k && r.session === "I"), k);
  }
});

test("R14 i: the deal comes from the question or the page; the link opens the deal page panel", () => {
  const m = routeIntel("How could this deal go bad?", { dealId: "DD-06" })!;
  assert.equal(m.deal, "DD-06");
  assert.equal(intelHref(m), "/deal-desk/DD-06?intel=premortem");
  assert.equal(routeIntel("Run a default pre-mortem")?.missing, "deal");
});

test("R14 i: earlier routes and ordinary questions unchanged", () => {
  assert.equal(key("What will committee ask about R12-TWA?"), "challenger");
  assert.equal(key("If Al Ahsa Energy fails, who else is hit?"), "contagion");
  assert.equal(key("Were similar deals decided differently?"), "consistency");
  for (const q of ["What is ECL by sector?", "What is our largest exposure?", "Explain the PD model"]) assert.equal(routeIntel(q), null, q);
});
