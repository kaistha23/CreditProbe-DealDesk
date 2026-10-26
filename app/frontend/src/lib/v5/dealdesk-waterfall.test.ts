import assert from "node:assert/strict";
import { test } from "node:test";

import { waterfallBottom, waterfallTick, waterfallValue } from "./dealdesk-waterfall.ts";

test("each bar's value sits on its own line under its name", () => {
  assert.equal(waterfallTick("Capital benefit", "+0.34"), "Capital<br>benefit<br><b>+0.34</b>");
  assert.equal(waterfallTick("Risk-adjusted profit", "1.91"), "Risk-<br>adjusted<br>profit<br><b>1.91</b>");
  assert.equal(waterfallTick("Profit income", "7.07"), "Profit<br>income<br><b>7.07</b>");
  assert.equal(waterfallTick("FTP", "−5.26"), "FTP<br><b>−5.26</b>");
});

test("values read in the axis unit, steps signed", () => {
  assert.equal(waterfallValue(7.0712, false), "7.07");
  assert.equal(waterfallValue(0.355, true), "+0.36");
  assert.equal(waterfallValue(-5.26, true), "−5.26");
  assert.equal(waterfallValue(1234.5, false), "1,234.50");
});

test("a long name keeps at most three lines; the margin fits the tallest label", () => {
  const t = waterfallTick("Expected loss over the whole life", "−0.20");
  assert.equal(t.split("<br>").length, 4);
  assert.equal(waterfallBottom([t, "FTP<br><b>x</b>"]), 24 + 4 * 16);
});
