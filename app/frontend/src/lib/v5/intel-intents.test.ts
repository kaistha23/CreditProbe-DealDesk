import assert from "node:assert/strict";
import { test } from "node:test";

import { INTEL_ROUTES, intelHref, routeIntel } from "./intel-intents.ts";

const key = (q: string, ctx = {}) => routeIntel(q, ctx)?.route.key ?? null;

test("registry: every backlog engine built in R13 is routable (20 engines incl. Q)", () => {
  const backlog = INTEL_ROUTES.map((r) => r.backlog).filter((b) => b < 100).sort((a, b) => a - b);
  assert.deepEqual(backlog, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 19, 20, 21, 22]);
  assert.equal(new Set(INTEL_ROUTES.map((r) => r.key)).size, INTEL_ROUTES.length);
});

test("the two UAT questions route to their engines", () => {
  assert.equal(key("Who should I call today?"), "calls");
  assert.equal(key("oil falls 30% this morning"), "event");
  assert.equal(key("What if oil falls 30% this morning?"), "event");
});

test("each engine is reachable from a plain question", () => {
  const cases: [string, string][] = [
    ["What will committee ask about R12-TWA?", "challenger"],
    ["What is the smallest change that gets DD-05 approved?", "reverse"],
    ["Which collateral actually helps on R12-TWB?", "security"],
    ["Were similar deals decided differently?", "consistency"],
    ["Which renewals in the next 90 days are exceptions?", "renewals"],
    ["Can you design covenants for R12-TWA?", "covenants"],
    ["If Al Ahsa Energy fails, who else is hit?", "contagion"],
    ["Which project employers are we most exposed to?", "employer"],
    ["Where can we still grow next quarter?", "headroom"],
    ["Who should we exit?", "exits"],
    ["Where can we save RWA?", "rwa"],
    ["What will ECL be next quarter?", "ecl-bridge"],
    ["What is the best workout for CB00002?", "workout"],
    ["The auditor wants approvals, conditions and stage for the 5 largest Stage 3 borrowers", "inspection"],
    ["Which policy exceptions lead to defaults?", "exceptions"],
    ["Which RMs book worse than the risk they take?", "rm-track"],
    ["Which approval levels slow deals without changing them?", "doa"],
    ["How good are R12-TWA's accounts?", "fin-quality"],
  ];
  for (const [q, k] of cases) assert.equal(key(q), k, q);
});

test("ordinary book questions stay with the Cockpit and What-If", () => {
  for (const q of ["What is ECL by sector?", "Show Stage 2 for CB00039", "Stress the corporate book: mild, moderate and severe",
                   "Which sectors drive the ECL increase?", "What is our largest exposure?", "Explain the PD model", "What if Brent falls 30% over the next year?"]) {
    assert.equal(routeIntel(q), null, q);
  }
});

test("ids come from the question, else the page; missing ones are named", () => {
  assert.equal(routeIntel("What will committee ask?", { dealId: "R12-TWB" })?.deal, "R12-TWB");
  assert.equal(routeIntel("What will committee ask?")?.missing, "deal");
  assert.equal(routeIntel("What is the best workout for CB00002?")?.borrower, "CB00002");
  assert.equal(intelHref(routeIntel("Who should I call today?")!), "/early-warning?intel=calls");
  assert.equal(intelHref(routeIntel("How good are R12-TWA's accounts?")!), "/deal-desk/R12-TWA?intel=fin-quality");
});
