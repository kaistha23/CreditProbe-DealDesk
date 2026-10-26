import assert from "node:assert/strict";
import { test } from "node:test";

import type { BriefItem } from "./noor-model.ts";
import { engineFor, routeQuestion } from "./noor-route.ts";

const item = (id: string, title: string, name = ""): BriefItem => ({
  id, source: "sector_appetite", source_label: "Risk appetite", module: "dealdesk", title, detail: "", severity: "high",
  materiality_sar_mn: null, due: null, since: null, kind: "sector_appetite", owner: null, numbers: [], trace: [],
  show_me: { href: "/deal-desk", label: "Show" }, open: { href: "/deal-desk", label: "Open" }, entity: { name },
  rank: 1, score: 1,
});
const lines = [item("appetite:Construction", "Construction is at 96% of its sector limit", "Construction"),
               item("reg:floor", "Provision floor breached on Stage 3 coverage")];

test("any question goes to an engine; nothing is refused", () => {
  for (const q of ["Decompose the ECL movement this quarter", "Which borrowers moved to Stage 2?",
                   "What is the early warning picture for retail?", "Who are you?"]) {
    const r = routeQuestion(q, lines);
    assert.notEqual(r.engine, "none");
    assert.equal(r.engine, "cockpit", q);
  }
});

test("scenario, dashboard and deal questions go to their module engines", () => {
  assert.equal(engineFor("What if oil falls 30%?"), "whatif");
  assert.equal(engineFor("Run a severe downturn stress on the corporate book"), "whatif");
  assert.equal(engineFor("Build a dashboard for Stage 2 migration"), "lenses");
  assert.equal(engineFor("Which proposals are waiting for credit?"), "dealdesk");
  assert.equal(engineFor("Show the pipeline by sector"), "dealdesk");
});

test("a question about a brief line is answered on that line", () => {
  const r = routeQuestion("Why is Construction so close to its limit?", lines);
  assert.equal(r.engine, "brief");
  assert.equal(r.item?.id, "appetite:Construction");
  assert.equal(r.intent, "why");
  assert.equal(routeQuestion("What should we do about Construction?", lines).intent, "options");
  assert.equal(routeQuestion("today's brief please", lines).engine, "brief");
});

test("a book question that shares one word with a line still goes to the Cockpit", () => {
  assert.equal(routeQuestion("ECL by sector for Construction and Real Estate", lines).engine, "cockpit");
  assert.equal(routeQuestion("today's ECL by stage", lines).engine, "cockpit");
});

test("an empty question is the only thing not routed", () => {
  assert.equal(routeQuestion("   ").engine, "none");
});

test("a weak tie (one common word) does not take a book question to a line", () => {
  const ews = { ...item("ews:migrations", "1,031 corporate exposures moved to a worse stage in 2026Q2"), source_label: "Early Warning" };
  assert.equal(routeQuestion("Which borrowers moved into Stage 2 this quarter?", [...lines, ews]).engine, "cockpit");
  assert.equal(routeQuestion("Why did the provision floor breach?", lines).item?.id, "reg:floor");
});
