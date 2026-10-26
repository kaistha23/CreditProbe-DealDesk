import assert from "node:assert/strict";
import { test } from "node:test";

import { CONCLUSION_WORD, STATUS_WORD, SUGGESTED, fmt } from "./scorecard-words.ts";

test("ratios print as the report prints them", () => {
  assert.equal(fmt(0.6381, "pct"), "63.8%");
  assert.equal(fmt(0.0705, "pct2"), "7.05%");
  assert.equal(fmt(0.08862, "num4"), "0.0886");
  assert.equal(fmt(1.3509, "num"), "1.35");
  assert.equal(fmt(11968, "int"), "11,968");
});

test("a missing value is a dash, and a verdict is a word", () => {
  assert.equal(fmt(null, "pct"), "—");
  assert.equal(fmt("", "num"), "—");
  assert.equal(fmt("red", "rag"), "Red");
  assert.equal(fmt("2 red, 0 amber of 8", "text"), "2 red, 0 amber of 8");
  assert.equal(STATUS_WORD.na, "Not applicable");
});

test("the suggested conclusion follows the verdict", () => {
  assert.equal(SUGGESTED.green, "fit");
  assert.equal(SUGGESTED.amber, "conditions");
  assert.equal(SUGGESTED.red, "not_fit");
  assert.equal(CONCLUSION_WORD.conditions, "Fit for use with conditions");
});
