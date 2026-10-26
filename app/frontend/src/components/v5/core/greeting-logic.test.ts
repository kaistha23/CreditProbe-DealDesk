import assert from "node:assert/strict";
import test from "node:test";

import { greetingName, salutationFor } from "./greeting-logic.ts";

test("time of day follows PLAN_R6 B4 boundaries", () => {
  assert.equal(salutationFor(0), "Good morning");
  assert.equal(salutationFor(11), "Good morning");
  assert.equal(salutationFor(12), "Good afternoon");
  assert.equal(salutationFor(16), "Good afternoon");
  assert.equal(salutationFor(17), "Good evening");
  assert.equal(salutationFor(23), "Good evening");
});

test("the greeting uses the first name, or the Showing to name when set", () => {
  assert.equal(greetingName("", "Anne Sharma"), "Anne");
  assert.equal(greetingName("  ", "Anne"), "Anne");
  assert.equal(greetingName("Al Rajhi Capital", "Anne Sharma"), "Al Rajhi Capital");
  assert.equal(greetingName("", ""), "");
});
