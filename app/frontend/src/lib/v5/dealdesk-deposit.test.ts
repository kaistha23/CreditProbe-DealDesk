import { test } from "node:test";
import assert from "node:assert/strict";

import { DEPOSIT_NEUTRAL, DEPOSIT_TYPE, depositRead, hasDeposit } from "./dealdesk-deposit.ts";

test("Round D: no deposit reads None", () => {
  assert.equal(depositRead(undefined), "None");
  assert.equal(depositRead({ ...DEPOSIT_NEUTRAL }), "None");
  assert.equal(hasDeposit({ deposit_type: "lien_cash", deposit_pct: 0 }), false);
  assert.equal(hasDeposit({ deposit_type: "none", deposit_pct: 0 }), false);
  assert.equal(depositRead({ deposit_type: "none", deposit_pct: 20 }), "Lien-marked cash · 20% of limit · life of facility");
});

test("Round D: the term sheet cell names type, size, maintenance and facility", () => {
  assert.equal(depositRead({ deposit_type: "lien_cash", deposit_pct: 30 }), "Lien-marked cash · 30% of limit · life of facility");
  assert.equal(depositRead({ deposit_type: "lien_cash", deposit_pct: 30 }, 5.37), "Lien-marked cash · 30% of limit (SAR 5.4m) · life of facility");
  assert.equal(depositRead({ deposit_type: "relationship", deposit_amount: 5, deposit_tenor_months: 24, currency: "USD" }),
    "Operating balances · USD 5.0m · 24 months");
  assert.equal(depositRead({ deposit_type: "lien_cash", deposit_pct: 10, deposit_facility: "CF013381" }),
    "Lien-marked cash · 10% of limit · life of facility · secures CF013381");
  assert.equal(depositRead({ deposit_type: "lien_cash", deposit_pct: 10, deposit_facility: "all" }),
    "Lien-marked cash · 10% of limit · life of facility · secures all facilities");
});

test("Round D: the lever's choices", () => {
  assert.deepEqual(Object.keys(DEPOSIT_TYPE), ["none", "lien_cash", "relationship"]);
});
