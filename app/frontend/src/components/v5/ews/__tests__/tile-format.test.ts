import assert from "node:assert/strict";
import { test } from "node:test";

import { ofN, ofNLine, shareOf } from "../tile-format.ts";

test("n of N", () => {
  assert.equal(ofN(368, 5412), "368 of 5,412");
  assert.equal(ofN(null, 5412), "— of 5,412");
});

test("n of N with the share of exposure", () => {
  assert.equal(ofNLine(1049, 5412, 16.6), "1,049 of 5,412 · 16.6% of exposure");
  assert.equal(ofNLine(590, 5412, 11.94, "book"), "590 of 5,412 · 11.9% of book");
  assert.equal(ofNLine(590, 5412, undefined), "590 of 5,412");
  assert.equal(ofNLine(590, 5412, Number.NaN), "590 of 5,412");
});

test("share of a whole", () => {
  assert.equal(shareOf(25, 100), 25);
  assert.equal(shareOf(25, 0), null);
  assert.equal(shareOf(undefined, 100), null);
});
