// PLAN_R9: the Intelligence Packs registry behind "Powered by", the Library and the briefing.
import assert from "node:assert/strict";
import { test } from "node:test";

import { INTELLIGENCE_PACKS, findPack, findRule, packTitle, poweredByText, traceHref, confidenceFromScore } from "./intelligence-packs.ts";

test("seven packs, P1 to P7, each with rules and a place it is used", () => {
  assert.deepEqual(INTELLIGENCE_PACKS.map((p) => p.id), ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]);
  for (const p of INTELLIGENCE_PACKS) {
    assert.ok(p.rules.length > 0, p.id);
    assert.ok(p.usedIn.every((u) => u.href.startsWith("/")), p.id);
    for (const r of p.rules) assert.ok(r.id.startsWith(`${p.id}-`), r.id);
  }
});

test("rule IDs are unique", () => {
  const ids = INTELLIGENCE_PACKS.flatMap((p) => p.rules.map((r) => r.id));
  assert.equal(new Set(ids).size, ids.length);
});

test("lookups are case-insensitive", () => {
  assert.equal(findPack("p2")?.name, "SICR & Default Intelligence");
  assert.equal(findRule("p2-utp-03")?.pack.id, "P2");
  assert.equal(packTitle("P5"), "P5 Network Intelligence");
});

test("the trace link prefers an explicit app path, then a run ID", () => {
  assert.equal(traceHref({ href: "/trace/x" }), "/trace/x");
  assert.equal(traceHref({ runId: "r 1" }), "/trace/r%201");
  assert.equal(traceHref({ href: "https://evil" }), null);
  assert.equal(traceHref(null), null);
});

test("plain-text form names pack, rule, article and confidence", () => {
  const t = poweredByText({ pack: "P2", rule: "P2-DEF-04", confidence: "high" });
  assert.match(t, /^Powered by P2 SICR & Default Intelligence · P2-DEF-04 · CBUAE/);
  assert.match(t, /High confidence$/);
  assert.equal(confidenceFromScore(0.9), "high");
  assert.equal(confidenceFromScore(0.1), "low");
});

test("no banned words in the packs", () => {
  const text = JSON.stringify(INTELLIGENCE_PACKS).toLowerCase();
  for (const w of ["demo", "sample", "synthetic", "mock", "lorem"]) assert.ok(!text.includes(w), w);
  assert.ok(!/\btest\b/.test(text));
});
