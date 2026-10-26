import assert from "node:assert/strict";
import { test } from "node:test";

import { KPI_ROW_MAX, clampTiles, gridClass, nOfN, shareLine, shareOf } from "../v5/kpi-row.ts";

/** PLAN_R10 S2 / G-TILES: at most 4 tiles, one row, "n of N · x% of exposure". */

test("n of N and x% of exposure", () => {
  assert.equal(nOfN(214, 1250), "214 of 1,250");
  assert.equal(nOfN(null, 10), "");
  assert.equal(shareOf(840, 4560), "18.4% of exposure");
  assert.equal(shareOf(5, 100, "the book"), "5.00% of the book");
  assert.equal(shareOf(5, 0), "");
  assert.equal(shareLine({ n: 214, of: 1250, exposure: 840, exposureTotal: 4560 }), "214 of 1,250 · 18.4% of exposure");
  assert.equal(shareLine({ n: 3, of: 12 }), "3 of 12");
});

test("never more than 4 tiles, one row at >= 900 px, 2x2 below", () => {
  assert.equal(KPI_ROW_MAX, 4);
  assert.deepEqual(clampTiles([1, 2, 3, 4, 5, 6]), [1, 2, 3, 4]);
  assert.deepEqual(clampTiles([1, 2], 9), [1, 2]);
  assert.equal(gridClass(4), "grid-cols-2 min-[900px]:grid-cols-4");
  assert.equal(gridClass(7), "grid-cols-2 min-[900px]:grid-cols-4");
  assert.equal(gridClass(2), "grid-cols-2");
  assert.equal(gridClass(1), "grid-cols-1");
});
