// Deal Desk edition: the Cockpit home's brief is Deal Desk's and its Ask goes to Deal Desk's assistant.
import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";

delete process.env.NEXT_PUBLIC_CP_EDITION;   // the build default is the Deal Desk edition
const starters = await import("./starters.ts");
const route = await import("../noor/noor-route.ts");
const nav = await import("../../lib/navigation.ts");

test("the Deal Desk starters are Deal Desk's own questions and the placeholder is the Deal Desk home's", () => {
  assert.ok(starters.DEALDESK_STARTERS.length >= 4 && starters.DEALDESK_STARTERS.length <= 6);
  // In the edition every question goes to Deal Desk whatever the cue table says (home-ask.tsx forces the engine);
  // the headroom questions are the Deal Desk home's own chips, answered by its portfolio intents.
  assert.ok(starters.DEALDESK_STARTERS.some((s) => route.engineFor(s) === "dealdesk"));
  assert.ok(starters.DEALDESK_STARTERS.every((s) => /proposal|headroom|call today/i.test(s)));
  assert.equal(starters.DEALDESK_ASK_PLACEHOLDER, "Ask Deal Desk, e.g. \u201cWhy does DD-03 fail?\u201d");
});

test("the home brief reads Deal Desk's module brief and offers no Cockpit ECL disclosure in the edition", () => {
  const src = fs.readFileSync(new URL("./home-brief.tsx", import.meta.url), "utf8");
  assert.ok(src.includes('edition() === "dealdesk" ? "dealdesk" : undefined'));
  assert.ok(src.includes("if (module) more = undefined;"));
  assert.ok(src.includes("noor.brief(module ? { persona, module, top: 5 }"));
  assert.ok(src.includes("if (!module) {"), "the Cockpit attention cards are read only for the full brief");
});

test("the home Ask sends every question to Deal Desk in the edition, except the intelligence intents", () => {
  const src = fs.readFileSync(new URL("./home-ask.tsx", import.meta.url), "utf8");
  assert.ok(src.includes('const dealdeskOnly = edition() === "dealdesk";'));
  assert.ok(src.includes('const engine = dealdeskOnly ? "dealdesk" : engineFor(q);'));
  assert.ok(src.indexOf("routeIntel(q)") < src.indexOf('dealdeskOnly ? "dealdesk"'), "the intel intents still answer in place");
  assert.ok(src.includes("books.length > 1 && !dealdeskOnly"), "no book switch in the edition");
  assert.ok(src.includes("{dealdeskOnly ? null : ("), "no Deep allowance in the edition");
});

test("Noor routes every engine to Deal Desk in the edition, and the full product keeps its engines", () => {
  assert.equal(nav.edition(), "dealdesk");
  const dispatch = fs.readFileSync(new URL("../noor/noor-dispatch.ts", import.meta.url), "utf8");
  assert.ok(dispatch.includes('return edition() === "dealdesk" ? "dealdesk" : engine;'));
  assert.ok(dispatch.includes("const engine = engineInEdition(requested);"));
  for (const f of ["../noor/noor-topbar.tsx", "../noor/noor-panel.tsx"]) {
    const src = fs.readFileSync(new URL(f, import.meta.url), "utf8");
    assert.ok(src.includes('edition() === "dealdesk" ? { module: "dealdesk" } : {}'), f);
  }
});
