import assert from "node:assert/strict";
import { test } from "node:test";

import { formatCell } from "./convo.ts";

test("R6 E2: the generic convo table never shows a raw float or an empty yes/no", () => {
  assert.equal(formatCell(0.2810632681763545, "lifetime_raroc"), "28.1%");
  assert.equal(formatCell(true, "clears_hurdle"), "Yes");
  assert.equal(formatCell(false, "clears_hurdle"), "No");
  assert.equal(formatCell("0.8882297289798154", "sva"), "0.89");
  assert.equal(formatCell(0.8882297289798154, "sva"), "0.89");
  assert.equal(formatCell(3.14159265, "something"), "3.14");
  assert.equal(formatCell("Rating -1 notch", "scenario"), "Rating -1 notch");
  for (const v of [0.123456789, 12.3456789, 1234.56789, 0.000123456]) {
    assert.doesNotMatch(formatCell(v, "value"), /\d\.\d{5,}/);
  }
});
