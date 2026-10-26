import assert from "node:assert/strict";
import { test } from "node:test";

import { coverageGrid, coverageTone, flagTone, parseGovPanel, parseSample, pctText, rateText, ratioText, verdictTone,
  type Coverage } from "./intel-governance.ts";

test("sample list: separators, case and duplicates", () => {
  assert.deepEqual(parseSample("cb00039, R12-TWA\nCB00039;  cf000011 "), ["CB00039", "R12-TWA", "CF000011"]);
  assert.deepEqual(parseSample(""), []);
});

test("numbers read as the screen shows them; missing is a dash", () => {
  assert.equal(pctText(12.345), "12.3%");
  assert.equal(pctText(null), "—");
  assert.equal(rateText({ pct: 8.3, k: 10, n: 120, ci_low_pct: 7.2, ci_high_pct: 9.6 }), "8.3% (7.2–9.6)");
  assert.equal(rateText(null), "—");
  assert.equal(ratioText(1.234, [0.5, 2]), "1.23× (0.50–2.00)");
  assert.equal(ratioText(Number.NaN), "—");
});

test("tones", () => {
  assert.equal(verdictTone("tighten"), "negative");
  assert.equal(verdictTone("keep"), "positive");
  assert.equal(verdictTone("watch"), "warning");
  assert.equal(coverageTone("not_available"), "negative");
  assert.equal(flagTone("worse than risk taken"), "negative");
  assert.equal(flagTone(""), "neutral");
});

test("coverage grid keeps the request order", () => {
  const c = (item: string, topic: string, status: Coverage["status"]): Coverage =>
    ({ item, kind: "borrower", topic, topic_label: topic.toUpperCase(), status, reason: "" });
  const g = coverageGrid([c("B", "stage", "answered"), c("B", "ecl", "partial"), c("A", "stage", "not_available")]);
  assert.deepEqual(g.items, ["B", "A"]);
  assert.deepEqual(g.topics.map((t) => t.key), ["stage", "ecl"]);
  assert.equal(g.cell("A", "stage")?.status, "not_available");
  assert.equal(g.cell("A", "ecl"), undefined);
});

test("panel keys", () => {
  assert.equal(parseGovPanel("doa"), "doa");
  assert.equal(parseGovPanel("x"), null);
  assert.equal(parseGovPanel(null), null);
});
