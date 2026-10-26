import { test } from "node:test";
import assert from "node:assert/strict";

import { boldParts, confidence } from "./queries.ts";

test("key figures in an answer are bold parts", () => {
  assert.deepEqual(boldParts("ECL of **SAR 1.2bn** is **2.18%** of CRWA."), [
    { text: "ECL of ", bold: false }, { text: "SAR 1.2bn", bold: true }, { text: " is ", bold: false },
    { text: "2.18%", bold: true }, { text: " of CRWA.", bold: false },
  ]);
});

test("confidence maps to the Powered-by levels", () => {
  assert.equal(confidence("High"), "high");
  assert.equal(confidence("Medium"), "medium");
  assert.equal(confidence("anything"), "high");
});
