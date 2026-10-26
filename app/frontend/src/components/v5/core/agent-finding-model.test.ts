import { test } from "node:test";
import assert from "node:assert/strict";

import {
  b360LinkFor, backWithRun, ewsDetailHref, findingSubject, originFor, planningState, sourceLegend, splitIds,
} from "./agent-finding-model.ts";

test("L6: a triage finding names its customer, book and period", () => {
  const s = findingSubject({ data: { borrower_id: "CB00808", borrower_name: "Tuwaiq Construction", ews: { period: "2026Q2" } } });
  assert.deepEqual(s, { id: "CB00808", name: "Tuwaiq Construction", domain: "corporate", period: "2026Q2" });
  assert.equal(findingSubject({ data: { borrower_id: "RC0011824" } })?.domain, "retail");
  assert.equal(findingSubject({ data: { obligor_id: "CB00020" } })?.id, "CB00020");
  assert.equal(findingSubject({ data: { figures: {} } }), null);
});

test("Deal Desk edition (the default): a finding's customer opens in Deal Desk, with the back path that reopens the run", () => {
  delete process.env.NEXT_PUBLIC_CP_EDITION;
  const s = findingSubject({ data: { borrower_id: "CB00808", ews: { period: "2026Q2" } } })!;
  const e = new URL(ewsDetailHref(s, "brief", "/?tab=brief"), "http://x");
  assert.equal(e.pathname, "/deal-desk/customer-packs");
  assert.equal(e.searchParams.get("cif"), "CB00808");
  assert.equal(e.searchParams.get("back"), "/?tab=brief");
  assert.equal(new URL(b360LinkFor(s, "brief", "/?tab=brief")!, "http://x").pathname, "/deal-desk/customer-packs");
});

test("L6: Early Warning detail and Borrower 360 carry the back path that reopens the run", () => {
  process.env.NEXT_PUBLIC_CP_EDITION = "full";
  const back = backWithRun("/early-warning?domain=corporate&period=2026Q2&from=brief", "agr_1");
  assert.equal(back, "/early-warning?domain=corporate&period=2026Q2&agent_run=agr_1");
  const s = findingSubject({ data: { borrower_id: "CB00808", ews: { period: "2026Q2" } } })!;
  const e = new URL(ewsDetailHref(s, "ews", back), "http://x");
  assert.equal(e.pathname, "/early-warning");
  assert.equal(e.searchParams.get("customer"), "CB00808");
  assert.equal(e.searchParams.get("period"), "2026Q2");
  assert.equal(e.searchParams.get("from"), "ews");
  assert.equal(e.searchParams.get("back"), back);
  const b = new URL(b360LinkFor(s, "ews", back)!, "http://x");
  assert.equal(b.pathname, "/borrower-360");
  assert.equal(b.searchParams.get("customer_id"), "CB00808");
  assert.equal(b.searchParams.get("back"), back);
  assert.equal(b360LinkFor({ ...s, id: "RC0011824", domain: "retail" }, "ews", back), null);
});

test("L6: names in the answer text are split out as ids", () => {
  const parts = splitIds("Tuwaiq Construction (CB00808): Propose UTP; RC0011824 too.");
  assert.deepEqual(parts.filter((p) => p.id).map((p) => p.id), ["CB00808", "RC0011824"]);
  assert.equal(parts.map((p) => p.text ?? p.id).join(""), "Tuwaiq Construction (CB00808): Propose UTP; RC0011824 too.");
});

test("L5: S-chips have a legend; origins per agent module", () => {
  assert.equal(sourceLegend("S3", { S3: "Borrower 360 facts" }), "S3: Borrower 360 facts (opens the step that read it)");
  assert.match(sourceLegend("S9", null, "ews_rules_trend"), /rules trend/);
  assert.equal(originFor("ews.triage"), "ews");
  assert.equal(originFor("dealdesk.committee"), "deal-desk");
  assert.equal(originFor("whatif.scenario"), "whatif");
});

test("L4: planning longer than 60 s with no step is stalled; steps or a finish clear it", () => {
  assert.deepEqual(planningState(0, 61_000, false, false), { seconds: 61, stalled: true });
  assert.equal(planningState(0, 61_000, true, false).stalled, false);
  assert.equal(planningState(0, 61_000, false, true).stalled, false);
  assert.equal(planningState(0, 30_000, false, false).stalled, false);
});
