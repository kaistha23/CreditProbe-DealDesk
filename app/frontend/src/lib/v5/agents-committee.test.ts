import assert from "node:assert/strict";
import { test } from "node:test";

import { packFigure, packTone } from "./agents-committee.ts";

test("decision tones", () => {
  assert.equal(packTone("Approve as proposed with conditions"), "positive");
  assert.equal(packTone("Approve on the counter-proposal"), "warning");
  assert.equal(packTone("Do not approve as proposed"), "negative");
  assert.equal(packTone("Decline as structured"), "negative");
  assert.equal(packTone("Not enough evidence to recommend"), "neutral");
});

test("pack figures", () => {
  assert.equal(packFigure(0.1609, "pct"), "16.1%");
  assert.equal(packFigure(1234.5, "m"), "1,234.50m");
  assert.equal(packFigure(0.02812, "m3"), "0.028m");
  assert.equal(packFigure(8.43, "s"), "8.4 s");
  assert.equal(packFigure(null, "pct"), "–");
});
