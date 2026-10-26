import { test } from "node:test";
import assert from "node:assert/strict";

import { friendlyError, friendlyMessage, isDeveloperText, unavailable } from "./errors.ts";

test("a service's own sentence is shown as it is", () => {
  assert.equal(friendlyError("Lenses", 404, { detail: { message: "LN-12 is not a lens." } }), "LN-12 is not a lens.");
  assert.equal(friendlyError("Deal Desk", 422, { detail: "The tenor must be between 1 and 30 years." }),
    "The tenor must be between 1 and 30 years.");
  assert.equal(friendlyError("Deal Desk", 409, { detail: "A policy exception needs a second approver." }),
    "A policy exception needs a second approver.");
});

test("developer text never reaches the screen", () => {
  const dev = [
    "The What-If service at http://127.0.0.1:8503 is not reachable. Start it on port 8503.",
    "Run ops/v5.sh start",
    "sqlite3.OperationalError: unable to open database file",
    "The What-If corporate domain has no file for 2026Q2 (/Users/anne/v5/var/whatif_v5/corporate/2026Q2.parquet).",
    'Traceback (most recent call last):\n  File "backend/x.py", line 3',
    "KeyError: 'ead'",
    '{"error_code":"X"}',
    "500 Internal Server Error",
    "Internal Server Error",
  ];
  for (const m of dev) {
    assert.ok(isDeveloperText(m), m);
    assert.ok(!friendlyError("What-If", 500, { detail: m }).includes("ops/"), m);
  }
  assert.equal(friendlyError("What-If", 503, { detail: dev[0] }), unavailable("What-If"));
});

test("a missing or technical body falls back to a plain sentence by status", () => {
  assert.equal(friendlyError("Admin", 500, null), "Admin could not complete that just now. Please try again in a moment.");
  assert.equal(friendlyError("Admin", 502, "Bad Gateway"), unavailable("Admin"));
  assert.equal(friendlyError("Admin", 401, null), "Your session has ended. Please sign in again.");
  assert.equal(friendlyError("Admin", 403, {}), "You do not have access to this.");
  assert.equal(friendlyError("Workspace", 422, { detail: [{ msg: "Field required", loc: ["body", "x"] }] }),
    "Some of the details are not valid. Please check them and try again.");
});

test("ordinary names and figures are not mistaken for developer text", () => {
  for (const m of ["Adnan Al-Harbi has no exposure in 2026Q2.", "Stage 2 share rose to 12.4% at 2026-08.",
    "The ratio 1.25x is below the 1.30x covenant.", "Nothing to undo."]) {
    assert.equal(isDeveloperText(m), false, m);
  }
});

test("any thrown value becomes a sentence", () => {
  assert.equal(friendlyMessage(new TypeError("Failed to fetch"), "Lenses"), unavailable("Lenses"));
  assert.equal(friendlyMessage(new Error("That lens is archived."), "Lenses"), "That lens is archived.");
  assert.equal(friendlyMessage({}, "Lenses"), unavailable("Lenses"));
});
