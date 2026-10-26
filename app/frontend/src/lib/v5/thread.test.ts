import assert from "node:assert/strict";
import { test } from "node:test";

import { STEP_ORDER, liveStepMs, newTraceId, stepOf, toRunView, traceFromEvents, traceHeaders } from "./thread.ts";

const ev = (event_type: string, stage: string, elapsed_ms: number, public_message = "") => ({ event_type, stage, elapsed_ms, public_message });

test("convo stages map onto the six G4 steps", () => {
  assert.deepEqual(["understanding", "planning", "querying", "answering", "validating", "publishing"].map(stepOf), STEP_ORDER);
  assert.equal(stepOf("accepted"), "");
});

test("a live run keeps its open step running and closes the earlier ones", () => {
  const snap = traceFromEvents([ev("run.started", "accepted", 0), ev("stage.started", "understanding", 10, "Reading"),
    ev("stage.completed", "understanding", 300), ev("stage.started", "querying", 300), ev("tool.started", "querying", 320, "Running q1")]);
  assert.equal(snap.state, "running");
  assert.deepEqual(snap.steps.map((s) => [s.key, s.state]), [["understand", "done"], ["query", "running"]]);
  assert.equal(snap.steps[1].detail, "Running q1");
  assert.equal(snap.steps[0].ended_ms, 300);
});

test("answer.ready settles the trace and closes the last step", () => {
  const snap = traceFromEvents([ev("stage.started", "answering", 0), ev("answer.ready", "publishing", 1200)]);
  assert.equal(snap.state, "done");
  assert.equal(snap.steps[0].state, "done");
  assert.equal(snap.elapsed_ms, 1200);
});

test("run.failed marks the open step failed", () => {
  const snap = traceFromEvents([ev("stage.started", "querying", 0), ev("run.failed", "", 50)]);
  assert.equal(snap.state, "failed");
  assert.equal(snap.steps[0].state, "failed");
});

test("toRunView gives the frozen ProcessPanel what it renders", () => {
  const view = toRunView({ trace_id: "tr-1", state: "done", elapsed_ms: 900, steps: [
    { key: "understand", label: "Understand", state: "done", started_ms: 0, ended_ms: 200, detail: "" },
    { key: "query", label: "Query", state: "done", started_ms: 200, ended_ms: 900, detail: "q1" }] });
  assert.equal(view.terminal, true);
  assert.equal(view.state, "COMPLETED");
  assert.deepEqual(view.steps.map((s) => [s.label, s.elapsedMs]), [["Understand", 200], ["Query", 700]]);
});

test("a running step counts forward from the anchor; a done one does not", () => {
  const snap = { trace_id: "", state: "running" as const, elapsed_ms: 1000, steps: [
    { key: "understand" as const, label: "Understand", state: "done" as const, started_ms: 0, ended_ms: 400, detail: "" },
    { key: "query" as const, label: "Query", state: "running" as const, started_ms: 400, ended_ms: null, detail: "" }] };
  assert.equal(liveStepMs(snap.steps[0], snap, 5000, 9000), 400);
  assert.equal(liveStepMs(snap.steps[1], snap, 5000, 9000), 600 + 4000);
});

test("trace ids and headers", () => {
  const id = newTraceId();
  assert.match(id, /^tr-[0-9a-f]{16}$/);
  assert.deepEqual(traceHeaders(id), { "X-Trace-Id": id });
});
