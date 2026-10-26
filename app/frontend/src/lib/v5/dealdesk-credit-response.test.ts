import assert from "node:assert/strict";
import { test } from "node:test";

import { looksLikeRequest, nextStep, progress, runs, severityTone, type CrStep } from "./dealdesk-credit-response.ts";

const st = (key: CrStep["key"], status: CrStep["status"]): CrStep => ({ key, label: key, status });

test("nextStep runs the pending steps in order and stops when read or deal fails", () => {
  assert.equal(nextStep({ steps: [st("read", "done"), st("deal", "pending"), st("check", "pending")] }), "deal");
  assert.equal(nextStep({ steps: [st("read", "error"), st("deal", "pending")] }), null);
  assert.equal(nextStep({ steps: [st("read", "done"), st("deal", "done"), st("check", "error"), st("review", "pending")] }), "review");
  assert.equal(nextStep({ steps: [st("read", "done"), st("response", "done")] }), null);
});

test("progress counts done and failed steps", () => {
  assert.deepEqual(progress({ steps: [st("read", "done"), st("deal", "error"), st("check", "pending"), st("review", "pending")] }), { done: 2, total: 4, pct: 50 });
});

test("runs splits the bank form's bold and underline markup", () => {
  assert.deepEqual(runs("We note that __the EOT is not formalised__ and **SAR 48.6m** at risk."), [
    { text: "We note that ", bold: false, underline: false }, { text: "the EOT is not formalised", bold: true, underline: true },
    { text: " and ", bold: false, underline: false }, { text: "SAR 48.6m", bold: true, underline: false }, { text: " at risk.", bold: false, underline: false }]);
});

test("severity tones and request names", () => {
  assert.equal(severityTone("critical"), "negative");
  assert.equal(severityTone("major"), "warning");
  assert.equal(severityTone("minor"), "neutral");
  assert.ok(looksLikeRequest("business_request_p1.jpg"));
  assert.ok(!looksLikeRequest("13_audited_fs__fy2025.pdf"));
});
