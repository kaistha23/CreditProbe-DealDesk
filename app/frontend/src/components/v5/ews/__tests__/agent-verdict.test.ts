import assert from "node:assert/strict";
import { test } from "node:test";

import { isVerdict, periodRuns, runPeriod, verdictMap, verdictTone, VERDICT_LABEL } from "../agent-verdict-core.ts";

test("verdicts from the run's findings only", () => {
  const m = verdictMap([
    { kind: "ews.summary", data: {} },
    { kind: "ews.verdict.sicr", data: { borrower_id: "CB00808", verdict: "sicr" } },
    { kind: "ews.verdict.noise", data: { borrower_id: "CB02020", verdict: "noise" } },
    { kind: "ews.verdict.bogus", data: { borrower_id: "CB1", verdict: "bogus" } },
    { kind: "ews.followup", data: { borrower_id: "CB2" } },
  ]);
  assert.deepEqual(m, { CB00808: "sicr", CB02020: "noise" });
  assert.deepEqual(verdictMap(undefined), {});
});

test("labels and tones", () => {
  assert.equal(VERDICT_LABEL.utp, "UTP");
  assert.match(verdictTone("utp"), /negative/);
  assert.match(verdictTone("noise"), /surface-muted/);
  assert.ok(isVerdict("watchlist") && !isVerdict("stage2"));
});

test("period runs of the book, newest first", () => {
  const runs = periodRuns([
    { run_id: "a", scope: "corporate", status: "completed", created_at: "2026-10-17T10:00:00Z" },
    { run_id: "b", scope: "corporate:CB00808", status: "completed", created_at: "2026-10-17T11:00:00Z" },
    { run_id: "c", scope: "corporate", status: "running", created_at: "2026-10-17T12:00:00Z" },
    { run_id: "d", scope: "corporate", status: "partial", created_at: "2026-10-17T13:00:00Z" },
    { run_id: "e", scope: "retail", status: "completed", created_at: "2026-10-17T14:00:00Z" },
  ], "corporate");
  assert.deepEqual(runs.map((r) => r.run_id), ["d", "a"]);
});

test("a run's period", () => {
  assert.equal(runPeriod({ output: { period: "2026Q2" }, context: { period: "" } }), "2026Q2");
  assert.equal(runPeriod({ output: null, context: { period: "2026Q1" } }), "2026Q1");
});
