import { test } from "node:test";
import assert from "node:assert/strict";

import { boldRuns, checksLine, paperUrls, voiceLabel } from "./model.ts";

test("paper urls are under the Deal Desk engine and encode the id", () => {
  const u = paperUrls("DD 31");
  assert.equal(u.bankFormDocx, "/api/v1/dealdesk/proposals/DD%2031/bank-form.docx");
  assert.equal(u.committeePdf, "/api/v1/dealdesk/proposals/DD%2031/committee-paper.pdf");
  assert.equal(u.summaryMemoDocx("DR-1"), "/api/v1/dealdesk/drafts/DR-1/docx");
});

test("voice labels name who speaks", () => {
  assert.equal(voiceLabel({ voice: "business", part: "anatomy" }), "Business");
  assert.equal(voiceLabel({ voice: "credit", part: "creditprobe" }), "CreditProbe");
  assert.equal(voiceLabel({ voice: "form", part: "anatomy" }), "Form");
});

test("checks line reports coverage first, then voice and gaps", () => {
  const sections = new Array(26).fill(0).map(() => ({}) as never);
  assert.deepEqual(checksLine({ coverage: [], voice: [], gaps: [], sections }), { tone: "positive", text: "All 26 sections · every sentence in the house voice" });
  assert.equal(checksLine({ coverage: ["missing section 11 Credit bureau"], voice: [], gaps: [], sections }).tone, "warning");
  assert.match(checksLine({ coverage: [], voice: [], gaps: [{ section: "bureau", heading: "Credit bureau", missing: ["bureau_entity_report"] }], sections }).text, /1 section\(s\) with data not available/);
});

test("bold runs", () => {
  assert.deepEqual(boldRuns("Verdict: **Approve**; tier **High**"), [["Verdict: ", false], ["Approve", true], ["; tier ", false], ["High", true]]);
});
