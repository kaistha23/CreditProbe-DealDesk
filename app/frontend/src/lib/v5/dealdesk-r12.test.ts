import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ACTIONS, LANDING_STEP, R12_STEP_ORDER, TABS, bannerLine, documentsLabel, doneSet, parseStep, parseTab, pathStates, primaryAction,
  sideOf, stateTone, stepDone, viewOf,
} from "./dealdesk-r12.ts";

test("I15/I1: the step order is diagnose then cure, and a deal opens on Proposal", () => {
  // PLAN_R14 (K23, K31): Upload · Proposal check · Review · Analysis · Structure · Recommendation; Stress is a header button.
  assert.deepEqual([...R12_STEP_ORDER], ["proposal", "proposal-check", "review", "analysis", "structure", "recommendation"]);
  assert.equal(LANDING_STEP, "proposal");
  assert.equal(parseStep(null), "proposal");
  assert.equal(parseStep("nonsense"), "proposal");
  assert.equal(parseStep("stress"), "stress");
});

test("O2: a tick is visited and done, never computed", () => {
  const none = new Set<string>();
  assert.equal(doneSet(none, { hasOpt: true, hasRec: true }).size, 0, "an optimisation or a recommendation alone ticks nothing");
  const v = new Set(["proposal", "review", "structure", "recommendation"]);
  assert.ok(stepDone("proposal", v, { hasOpt: false, hasRec: false }));
  assert.ok(!stepDone("structure", v, { hasOpt: false, hasRec: false }), "Structure needs an optimisation on screen");
  assert.ok(stepDone("structure", v, { hasOpt: true, hasRec: false }));
  assert.ok(!stepDone("recommendation", v, { hasOpt: true, hasRec: false }), "Recommendation needs a saved recommendation");
  assert.ok(!stepDone("analysis", v, { hasOpt: true, hasRec: true }), "not visited, not ticked");
});

test("I17: the view follows the Users & Teams role, not a button", () => {
  assert.equal(sideOf({ role: "Relationship Manager" }), "rm");
  assert.equal(viewOf(sideOf({ role: "Relationship Manager" })), "prepare");
  for (const r of ["Head of Credit", "Corporate Credit Manager", "Credit Analyst", "Head of Risk", "Risk Manager"]) {
    assert.equal(sideOf({ role: r }), "credit", r);
    assert.equal(viewOf(sideOf({ role: r })), "review", r);
  }
  assert.equal(sideOf({ role: "Administrator", is_admin: true }), "admin");
  assert.equal(viewOf("admin"), "review");
  assert.equal(sideOf({ role: "Internal Auditor" }), "viewer");
  assert.equal(sideOf(null), "viewer");
});

test("I23: the action bar, with the role's own entry point emphasised", () => {
  assert.deepEqual(ACTIONS.map((a) => a.label), ["Write proposal", "Review proposal", "Optimise", "Committee paper", "Documents", "Word", "Add to report"]);
  assert.equal(primaryAction("prepare"), "write");
  assert.equal(primaryAction("review"), "review");
  assert.equal(documentsLabel(3), "Documents (3)");
  assert.equal(documentsLabel(0), "Documents");
  assert.equal(documentsLabel(null), "Documents");
});

test("I30: three tabs, Origination by default", () => {
  assert.deepEqual(TABS.map((t) => t.label), ["Origination", "Book", "Monitoring", "Parameters & policy"]); // R14 F (K35): Monitoring
  assert.equal(parseTab(null), "origination");
  assert.equal(parseTab("book"), "book");
  assert.equal(parseTab("x"), "origination");
});

test("I21/I17: the banner line and the workflow path", () => {
  assert.equal(bannerLine(null), "");
  const b = { proposal_id: "PL-03", source: "pipeline" as const, in_pipeline: true, back_href: "/deal-desk?mode=pipeline",
              decision: { decision: "approve", structure: "Reduced to 120m", amount_sar_mn: 120, reason: "r", gets_in: null, headline: "h" } };
  assert.equal(bannerLine(b), "Approve: Reduced to 120m");
  const states = [{ key: "draft", label: "Draft", side: "business" as const }, { key: "declined", label: "Declined", side: "credit" as const }];
  assert.deepEqual(pathStates(states, "draft").map((s) => s.key), ["draft"]);
  assert.deepEqual(pathStates(states, "declined").map((s) => s.key), ["draft", "declined"]);
  assert.equal(stateTone("approved"), "positive");
  assert.equal(stateTone("queries"), "warning");
});
