import { test } from "node:test";
import assert from "node:assert/strict";

import { parseExcerpt } from "./policy-excerpt.ts";

test("clause lines split into id, title and rule", () => {
  const [a] = parseExcerpt("CP-1.1 Single obligor limit. Total exposure to a single obligor may not exceed SAR 250 million.");
  assert.deepEqual(a, { kind: "clause", id: "CP-1.1", title: "Single obligor limit", rest: "Total exposure to a single obligor may not exceed SAR 250 million." });
});

test("headings and plain text", () => {
  const parts = parseExcerpt("SECTION 1 CONCENTRATION\nSome plain sentence, here.");
  assert.equal(parts[0].kind, "heading");
  assert.equal(parts[1].kind, "text");
});

test("R6 P2: a regulation's paragraph ids (BM-1230 §4.2) are clause ids", () => {
  const [p] = parseExcerpt("BM-1230 §4.2 Restructuring /Rescheduling. FIs should have the Board approved policy.");
  assert.equal(p.kind, "clause");
  if (p.kind === "clause") { assert.equal(p.id, "BM-1230 §4.2"); assert.equal(p.title, "Restructuring /Rescheduling"); }
});

test("R7 C1: the CBUAE CRM Standards' paragraph ids (CBUAE CRM Art. 7.8) are clause ids", () => {
  const [p] = parseExcerpt("CBUAE CRM Art. 7.8 DPD indicator. Credit Facilities with Repayments more than 30 Days-Past-Due must be identified.");
  assert.equal(p.kind, "clause");
  if (p.kind === "clause") { assert.equal(p.id, "CBUAE CRM Art. 7.8"); assert.equal(p.title, "DPD indicator"); }
  const [q] = parseExcerpt("CBUAE CRM Intro 1 Introduction and Scope. These standards form part of the Credit Risk Regulation.");
  if (q.kind === "clause") assert.equal(q.id, "CBUAE CRM Intro 1"); else assert.fail("not a clause");
});
