import assert from "node:assert/strict";
import { test } from "node:test";

import { MODEL_NAMES, hasVendorName, modelDisplayName } from "./model-names.ts";

test("known model IDs map to LLM model 1.1 and 1.2", () => {
  assert.equal(modelDisplayName("claude-opus-5"), "LLM model 1.1");
  assert.equal(modelDisplayName("claude-sonnet-5"), "LLM model 1.2");
  assert.equal(modelDisplayName("LLM model 1.2"), "LLM model 1.2");
  assert.deepEqual(MODEL_NAMES.map((m) => m.display), ["LLM model 1.1", "LLM model 1.2"]);
});

test("unknown vendor IDs never leak a vendor name", () => {
  assert.equal(modelDisplayName("claude-opus-4-1-20250805"), "LLM model 1.1");
  assert.equal(modelDisplayName("claude-sonnet-4-5-20250929"), "LLM model 1.2");
  assert.equal(modelDisplayName("claude-haiku-4-5"), "LLM model");
  assert.equal(modelDisplayName("gpt-4o"), "LLM model");
  for (const id of ["claude-opus-5", "claude-haiku-3", "gpt-5", "Opus", "Sonnet"]) assert.equal(hasVendorName(modelDisplayName(id)), false, id);
});

test("an Admin mapping overrides the table; plain text passes through", () => {
  assert.equal(modelDisplayName("claude-opus-6", { "LLM model 1.1": "claude-opus-6" }), "LLM model 1.1");
  assert.equal(modelDisplayName("planner (kill switch on)"), "planner (kill switch on)");
  assert.equal(modelDisplayName(null), "");
  assert.equal(hasVendorName("the configured model"), false);
});
