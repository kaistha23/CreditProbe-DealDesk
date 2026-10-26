import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type Step, type TrySession, acceptedFile, answerLine, dealLine, fmtValue, remaining, secs, stepStatusLabel, stepTone, verdictLabel,
  verdictTone,
} from "./try-docs-api.ts";

const step = (key: Step["key"], status: Step["status"], seconds: number | null = null, result: unknown = null): Step =>
  ({ key, label: key, status, seconds, summary: "", result });

const session = (over: Partial<TrySession> = {}): TrySession => ({
  session_id: "TRYS-20261019000000-abcd0001", created_at: "", mode: "deterministic", notice: "Confidential demo session.", model_notice: null,
  documents: { proposal: { name: "p.pdf", method: "pdf text", pages: 2, language: "en", characters: 2000 } }, deal_id: "TRY-ABCD0001",
  steps: [step("read", "done", 0.1), step("policy", "done", 0.2), step("extract", "error", 0.1), step("review", "pending"),
    step("counter", "pending"), step("draft", "pending")],
  next: "extract", total_seconds: 0.3, complete: false, ...over,
});

test("remaining steps are the pending and stopped ones, in order", () => {
  assert.deepEqual(remaining(session()), ["extract", "review", "counter", "draft"]);
});

test("seconds read as a person reads them", () => {
  assert.equal(secs(0.42), "0.4 s");
  assert.equal(secs(12.4), "12 s");
  assert.equal(secs(75), "1 min 15 s");
  assert.equal(secs(null), "–");
});

test("step tones and labels", () => {
  assert.equal(stepTone("done"), "positive");
  assert.equal(stepTone("error"), "negative");
  assert.equal(stepStatusLabel("running"), "Running");
});

test("verdicts in banker language", () => {
  assert.equal(verdictLabel("supported"), "Met");
  assert.equal(verdictLabel("exception"), "Breached");
  assert.equal(verdictLabel("unverifiable"), "Needs data");
  assert.equal(verdictTone("contradicted"), "negative");
});

test("values with units", () => {
  assert.equal(fmtValue(1.25, "x"), "1.25x");
  assert.equal(fmtValue(65, "pct"), "65%");
  assert.equal(fmtValue(18, "months"), "18 months");
  assert.equal(fmtValue(2050, undefined), "2,050");
  assert.equal(fmtValue(null), "–");
  assert.equal(fmtValue([175, 375]), "175–375");
});

test("the deal in one line", () => {
  assert.equal(dealLine({ name: "Gulf Meridian Contracting LLC", sector: "Construction", rating: "BB-", facility_type: "revolver",
    currency: "SAR", amount: 670.593, tenor_years: 1, margin_bps: 112, funded_share_pct: 12.2, financials: {} }),
  "Gulf Meridian Contracting LLC · Construction · BB- · SAR 670.59m revolving working capital, 1 year, 112 bps");
});

test("the answer line says steps done, then the total time and findings", () => {
  assert.equal(answerLine(session()), "2 of 6 steps done in 0.3 s.");
  const done = session({ complete: true, total_seconds: 4.6, steps: [step("read", "done"), step("review", "done", 1, {
    findings: [{}, {}, {}], decision: "Do not approve as proposed" })] });
  assert.equal(answerLine(done), "From upload to drafted memo in 4.6 s: 3 findings against your policy and the rule book. Review: Do not approve as proposed.");
});

test("accepted uploads", () => {
  assert.ok(acceptedFile("Proposal.PDF"));
  assert.ok(acceptedFile("scan.jpg"));
  assert.ok(!acceptedFile("model.xlsx"));
});
