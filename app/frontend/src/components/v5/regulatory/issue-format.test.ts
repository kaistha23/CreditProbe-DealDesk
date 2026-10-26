import { test } from "node:test";
import assert from "node:assert/strict";

import { cell, dueText } from "./issue-format.ts";
import { plainValue } from "./plain-value.ts";

test("issue cells in house format", () => {
  assert.equal(cell(878.5007, "SAR mn"), "SAR 878.5m");
  assert.equal(cell(1728.5517, "SAR mn"), "SAR 1.73bn");
  assert.equal(cell(0.51, "SAR mn"), "SAR 0.51m");
  assert.equal(cell(-12.07, "SAR mn"), "−SAR 12.1m");
  assert.equal(cell(44.08, "%"), "44.1%");
  assert.equal(cell(1570, "n"), "1,570");
  assert.equal(cell("Real Estate", "text"), "Real Estate");
  assert.equal(cell(null, "%"), "–");
});

test("due dates read as a banker writes them", () => {
  assert.equal(dueText("2026-11-09"), "9 Nov 2026");
});

test("no raw JSON: parameters and expected values in plain words", () => {
  assert.equal(plainValue({ min_dpd: 90, books: ["corporate", "retail"] }), "min dpd: 90; books: corporate, retail");
  assert.equal(plainValue([1, 2.5, "x"]), "1, 2.5, x");
  assert.equal(plainValue({ a: { b: true } }), "a: (b: yes)");
  assert.equal(plainValue(null), "—");
  assert.ok(!plainValue({ k: [1, { z: 2 }] }).includes("{"));
});

test("the runtime error is said in words, without the API path", async () => {
  const { runtimeMessage } = await import("./plain-value.ts");
  const m = runtimeMessage("/studio?limit=300 is served by the main CreditProbe backend, which is not part of this isolated Cockpit V4 runtime. It was not requested.", "The method library");
  assert.ok(!m.includes("/studio") && m.startsWith("The method library"));
  assert.equal(runtimeMessage("Network down"), "Network down");
});
