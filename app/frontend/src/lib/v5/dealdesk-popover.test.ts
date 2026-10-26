import assert from "node:assert/strict";
import { test } from "node:test";

import { MARGIN, PANEL_MAX_WIDTH, inBounds, placePanel } from "./dealdesk-popover.ts";

const VIEWS = [{ width: 1440, height: 900 }, { width: 1280, height: 800 }];
const PANEL = { width: PANEL_MAX_WIDTH, height: 360 };

test("the panel opens below the (i) when it fits, aligned with it", () => {
  const p = placePanel({ top: 100, left: 200, right: 220, bottom: 120 }, PANEL, VIEWS[0]);
  assert.equal(p.side, "below");
  assert.equal(p.left, 200);
  assert.equal(p.top, 126);
});

test("near the bottom it flips above; near the right edge it shifts left", () => {
  const p = placePanel({ top: 820, left: 1400, right: 1420, bottom: 840 }, PANEL, VIEWS[0]);
  assert.equal(p.side, "above");
  assert.ok(p.top + PANEL.height <= 820);
  assert.equal(p.left, 1440 - MARGIN - PANEL_MAX_WIDTH);
});

test("align right lines the panel's right edge with the (i), still inside the left margin", () => {
  const p = placePanel({ top: 100, left: 30, right: 50, bottom: 120 }, PANEL, VIEWS[1], "right");
  assert.equal(p.left, MARGIN);
});

test("a tall panel is capped to the room on its side and scrolls inside", () => {
  const p = placePanel({ top: 400, left: 600, right: 620, bottom: 420 }, { width: 416, height: 2000 }, VIEWS[1]);
  assert.equal(p.side, "above"); // 386 px above against 366 below: the larger room wins
  assert.equal(p.maxHeight, 400 - 6 - MARGIN);
  assert.ok(inBounds({ top: p.top, left: p.left, width: p.width, height: Math.min(2000, p.maxHeight) }, VIEWS[1]));
});

test("every anchor on a grid at both sizes keeps the panel in bounds", () => {
  for (const v of VIEWS) {
    for (let x = 0; x <= v.width - 20; x += 40) {
      for (let y = 0; y <= v.height - 20; y += 40) {
        for (const align of ["left", "right"] as const) {
          const p = placePanel({ top: y, left: x, right: x + 20, bottom: y + 20 }, PANEL, v, align);
          const h = Math.min(PANEL.height, p.maxHeight);
          assert.ok(inBounds({ top: p.top, left: p.left, width: p.width, height: h }, v), `${v.width}x${v.height} at ${x},${y} ${align}`);
          assert.ok(p.side === "below" ? p.top >= y + 20 : p.top + h <= y, "never covers its own (i)");
        }
      }
    }
  }
});

test("a narrow viewport caps the width", () => {
  const p = placePanel({ top: 10, left: 10, right: 30, bottom: 30 }, PANEL, { width: 360, height: 640 });
  assert.equal(p.width, 360 - 2 * MARGIN);
  assert.equal(p.left, MARGIN);
});
