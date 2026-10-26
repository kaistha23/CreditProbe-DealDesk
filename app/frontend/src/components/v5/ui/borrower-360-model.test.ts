import { test } from "node:test";
import assert from "node:assert/strict";

import { b360Href, hasBorrower360 } from "./borrower-360-model.ts";

test("Deal Desk edition (the default): a borrower opens in Deal Desk's customer files, not on a Borrower 360 screen", () => {
  delete process.env.NEXT_PUBLIC_CP_EDITION;
  assert.equal(b360Href("CB01312", "Q2 2026"), "/deal-desk/customer-packs?cif=CB01312");
});

test("K11: the Borrower 360 link uses the book's period spelling (the page refuses Q2-2026)", () => {
  process.env.NEXT_PUBLIC_CP_EDITION = "full";
  assert.equal(b360Href("CB01312", "Q2 2026"), "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2");
  assert.equal(b360Href("CB01312", "Q2-2026"), "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2");
  assert.equal(b360Href("CB01312", "2026q2"), "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2");
  assert.equal(b360Href("CB01312", ""), "/borrower-360?domain=corporate&customer_id=CB01312");
  assert.equal(b360Href("CB01312", "Sep 2026"), "/borrower-360?domain=corporate&customer_id=CB01312");
});

test("only corporate borrowers have a Borrower 360 page", () => {
  assert.equal(hasBorrower360("CB00020"), true);
  assert.equal(hasBorrower360("CG1277"), false);
  assert.equal(hasBorrower360("RC123"), false);
  assert.equal(hasBorrower360(""), false);
});
