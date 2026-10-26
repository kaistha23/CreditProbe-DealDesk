import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEMO_BUDGET_S, DEMO_SCRIPT, type BriefItem, type Turn, addTurn, canSwitch, dealDeskView, effectivePersona, intentOf, matchItem,
  moduleOf, personaFor, restoreTurns, speakable, splitFigures, spokenOpening, tickValue, traceLine, traceSchedule,
} from "./noor-model.ts";

const item = (id: string, title: string, name = ""): BriefItem => ({
  id, source: "sector_appetite", source_label: "Risk appetite", module: "dealdesk", title, detail: "", severity: "high",
  materiality_sar_mn: null, due: null, since: null, kind: "sector_appetite", owner: null, numbers: [], trace: [],
  show_me: { href: "/deal-desk", label: "Show" }, open: { href: "/deal-desk", label: "Open" }, entity: { name },
  rank: 1, score: 1,
});

test("personas from identity roles (same table as the backend)", () => {
  assert.equal(personaFor("Head of Risk"), "cro");
  assert.equal(personaFor("Administrator"), "cro");
  assert.equal(personaFor("Corporate Credit Manager"), "reviewer");
  assert.equal(personaFor("Relationship Manager"), "rm");
  assert.equal(personaFor("Credit Analyst"), "analyst");
  assert.equal(personaFor(undefined), "analyst");
});

test("Viewing as: demo and admin accounts only", () => {
  assert.equal(canSwitch({ is_admin: true }), true);
  assert.equal(canSwitch({ username: "demo.presenter" }), true);
  assert.equal(canSwitch({ username: "nawaf.alotaibi", role: "Relationship Manager" }), false);
  assert.equal(canSwitch({ username: "nawaf.alotaibi" }, true), true);
  assert.equal(canSwitch(null, true), false);
  assert.equal(effectivePersona("Relationship Manager", "cro", false), "rm");
  assert.equal(effectivePersona("Relationship Manager", "cro", true), "cro");
  assert.equal(effectivePersona("Head of Credit", null, true), "cro");
});

test("module of a page", () => {
  assert.equal(moduleOf("/").id, "cockpit");
  assert.equal(moduleOf("/deal-desk/DD-02").id, "dealdesk");
  assert.equal(moduleOf("/early-warning").label, "Early Warning");
  assert.equal(moduleOf("/what-if/thread/x").id, "whatif");
  assert.equal(moduleOf("/lenses").id, "lenses");
  assert.equal(moduleOf("/deal-deskx").id, "other");
});

test("thread: pending replaced, capped, restored without pending turns", () => {
  let t: Turn[] = [];
  t = addTurn(t, { id: "p1", kind: "pending", text: "Working" });
  t = addTurn(t, { id: "n1", kind: "note", text: "done", module: "cockpit" }, "p1");
  assert.deepEqual(t.map((x) => x.id), ["n1"]);
  for (let i = 0; i < 50; i++) t = addTurn(t, { id: `n${i + 2}`, kind: "note", text: "x", module: "cockpit" });
  assert.equal(t.length, 40);
  const raw = JSON.stringify([...t.slice(0, 2), { id: "p", kind: "pending", text: "" }, { bad: 1 }]);
  assert.equal(restoreTurns(raw).length, 2);
  assert.deepEqual(restoreTurns("not json"), []);
});

test("typed questions find the brief line and the intent", () => {
  const items = [item("a", "Real Estate is 10.5% of the book", "Real Estate"), item("b", "Construction is 12.2% of the book", "Construction")];
  assert.equal(matchItem("why is construction near its limit?", items)?.id, "b");
  assert.equal(matchItem("??", items), null);
  assert.equal(intentOf("Why is construction up?"), "why");
  assert.equal(intentOf("What should we do about it"), "options");
  assert.equal(intentOf("show me the names"), "show");
  assert.equal(intentOf("morning brief"), "brief");
  assert.equal(intentOf("who drives construction?"), "drivers");
});

test("live trace schedule and ticking counters", () => {
  const s = traceSchedule([
    { label: "a", count: 2516, unit: "facilities read", note: "", ms: 9, source: {} },
    { label: "b", count: 14, unit: "limits checked", note: "", ms: 5000, source: {} },
  ]);
  assert.deepEqual(s, [{ startMs: 0, durationMs: 550 }, { startMs: 550, durationMs: 1100 }]);
  assert.equal(tickValue(2516, 0, 550), 0);
  assert.equal(tickValue(2516, 600, 550), 2516);
  const mid = tickValue(2516, 275, 550) ?? 0;
  assert.ok(mid > 1000 && mid < 2516);
  assert.equal(tickValue(null, 10, 100), null);
});

test("trace and voice wording", () => {
  assert.equal(traceLine({ domain: "deal_desk", relation: "dd_result", keys: {}, period: "2026Q2", status: "ok" }),
    "Data Domains · deal_desk · dd_result · 2026Q2");
  assert.equal(speakable("SAR 1.48bn headroom, SAR 101.0m asked, 1.8pp"), "1.48 billion riyals headroom, 101.0 million riyals asked, 1.8 percentage points");
});

test("the scripted demo fits in 90 seconds", () => {
  assert.ok(DEMO_SCRIPT[DEMO_SCRIPT.length - 1].at < DEMO_BUDGET_S);
  assert.deepEqual(DEMO_SCRIPT.map((d) => d.action), ["brief", "why", "options", "committee", "done"]);
});

test("figures emphasised, never stage numbers or periods", () => {
  const figs = (t: string) => splitFigures(t).filter((_, i) => i % 2 === 1);
  assert.deepEqual(figs("Stage 3 provision: 219 exposures, SAR 1.73bn EAD in 2026Q2, up 5.0x to 22.4% (−SAR 0.95m), 1.8pp"),
    ["219", "SAR 1.73bn", "5.0x", "22.4%", "−SAR 0.95m", "1.8pp"]);
  assert.deepEqual(figs("DD-05 and CB00862"), []);
});

test("the Gulf Arabic voice reads the Arabic opening", () => {
  const b = { opening: "Good morning.", opening_ar: "صباح الخير." };
  assert.equal(spokenOpening(b, "ar-gulf"), "صباح الخير.");
  assert.equal(spokenOpening(b, "en"), "Good morning.");
  assert.equal(spokenOpening({ opening: "Hi" }, "ar-gulf"), "Hi");
});

test("Deal Desk view per persona", () => {
  assert.equal(dealDeskView("rm"), "prepare");
  assert.equal(dealDeskView("reviewer"), "review");
  assert.equal(dealDeskView("cro"), "review");
});

test("the brief's headline: the server's, else the opening without greeting and first line (R13 H, J3)", async () => {
  const { headlineOf } = await import("./noor-model.ts");
  assert.equal(headlineOf({ headline: "Five things across the bank since yesterday, 1 critical.", opening: "x" }),
               "Five things across the bank since yesterday, 1 critical.");
  assert.equal(headlineOf({ opening: "Good morning, Faisal. Three things across the bank since yesterday, 1 of them critical. First: Construction is at 96%. 2 more below." }),
               "Three things across the bank since yesterday, 1 of them critical.");
});
