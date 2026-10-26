import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type AgentFinding, type AgentPlan, bySeverity, citationParts, duration, evidenceStep, isFinished, mayDecide, normRole,
  plannerLabel, progress, severityCounts, severityTone, stepTone, toolLabel, tracePath,
} from "./agents.ts";

const step = (id: string, status: string) => ({ id, tool: "dd_x", inputs: {}, why: "", status, summary: "", figures: {},
  duration_ms: 0, error: "", added_by: "", trace_id: "" });
const plan = (statuses: string[]) => ({ schema: "", goal: "", agent: "", planner: "deterministic", goal_type: "", context: {},
  notes: [], steps: statuses.map((s, i) => step(`S${i + 1}`, s)) }) as unknown as AgentPlan;

test("progress counts settled steps", () => {
  assert.deepEqual(progress(plan(["done", "skipped", "running", "pending"])), { settled: 2, total: 4, share: 0.5, label: "2 of 4 steps" });
  assert.equal(progress(null).label, "Planning");
});

test("labels and tones", () => {
  assert.equal(toolLabel("dd_forward_risk"), "Forward risk");
  assert.equal(toolLabel("ews_rules_fired"), "Rules fired");
  assert.equal(stepTone("skipped"), "warning");
  assert.equal(severityTone("critical"), "negative");
  assert.equal(isFinished("partial"), true);
  assert.equal(isFinished("running"), false);
  assert.equal(duration(8400), "8.4 s");
  assert.equal(duration(95_000), "1 min 35 s");
  assert.equal(tracePath("agr_1"), "/trace/agent/agr_1");
  assert.equal(plannerLabel({ model: "", plan: { planner: "deterministic" } }), "Written plan (deterministic)");
});

test("findings sort and count by severity", () => {
  const f = [{ severity: "minor" }, { severity: "critical" }, { severity: "major" }] as AgentFinding[];
  assert.deepEqual(bySeverity(f).map((x) => x.severity), ["critical", "major", "minor"]);
  assert.deepEqual(severityCounts(f), { critical: 1, major: 1, minor: 1, info: 0 });
  assert.equal(evidenceStep("S8:CONS-03"), "S8");
});

test("citations split out of the narrative", () => {
  const p = citationParts("RAROC 12.1% [S3]. Stage 2 risk 4.0% [S5, S6].");
  assert.deepEqual(p, [{ text: "RAROC 12.1% " }, { cite: ["S3"] }, { text: ". Stage 2 risk 4.0% " }, { cite: ["S5", "S6"] }, { text: "." }]);
});

test("who may decide mirrors the backend", () => {
  const a = { approver_role: "CREDIT_OFFICER", status: "pending", maker: "anne" };
  assert.equal(mayDecide("RM", a), false);
  assert.equal(mayDecide("Credit Officer", a), true);
  assert.equal(mayDecide("Administrator", a, "anne"), false);
  assert.equal(mayDecide("CCO", { ...a, status: "approved" }), false);
  assert.equal(normRole("User"), "ANALYST");
});
