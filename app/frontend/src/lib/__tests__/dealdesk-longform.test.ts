import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

/** PLAN_R6 D1 (Session D2): the long form on screen, checked against its source; the sweep and pytest check behaviour. */

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");
const lf = read("components/v5/dealdesk/long-form.tsx");
const np = read("components/v5/dealdesk/new-proposal.tsx");

test("New proposal has four tabs: Customer documents (R16 i), Short form, Long form, Upload a memo", () => {
  assert.match(np, /\["docs", "form", "long", "memo"\]/);
  assert.match(np, /"Customer documents"/);
  assert.match(np, /"Short form"/);
  assert.match(np, /"Long form"/);
  assert.match(np, /"Upload a memo"/);
});

test("the long form has all eight D1 sections, in order", () => {
  const titles = [...lf.matchAll(/<Section n=\{(\d)\} title="([^"]+)"/g)].map((m) => `${m[1]} ${m[2]}`);
  assert.deepEqual(titles, ["1 Obligor and group", "2 Ratings", "3 Financials, 3 years (SAR million)", "4 Facility lines", "5 Security",
    "6 Covenants and conditions", "7 Relationship", "8 RM and business unit"]);
});

test("the financials grid carries the nine D1 metrics", () => {
  for (const k of ["revenue", "ebitda", "net_income", "total_debt", "cash", "equity", "operating_cash_flow", "capex", "interest"]) {
    assert.ok(lf.includes(`["${k}",`), k);
  }
});

test("facility lines, collateral, guarantees, owners and covenants can be added and removed", () => {
  for (const t of ["longform-add-line", "longform-add-collateral", "longform-add-guarantee", "longform-add-owner", "longform-add-covenant"]) {
    assert.ok(lf.includes(t), t);
  }
  assert.match(lf, /Remove line/);
  assert.match(lf, /LTV/);
});

test("a line carries amount, currency, tenor, pricing, fees, repayment, grace and purpose", () => {
  for (const k of ["amount", "currency", "tenor_years", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps", "amortisation", "grace_years", "purpose"]) {
    assert.ok(lf.includes(`${k}:`), k);
  }
});

test("validation speaks in plain words and names the section", () => {
  assert.match(lf, /the amount must be a number above zero/);
  assert.match(lf, /the tenor must be a whole number of years from 1 to 10/);
  assert.match(lf, /the grace period must be shorter than the tenor/);
  assert.match(lf, /the valuation date must be a date/);
  assert.match(np, /data-testid="longform-errors"/);
});

test("an upload opens the extracted fields in the form, marked from file or missing", () => {
  assert.match(np, /setMode\(r\.form === "short" \? "form" : "long"\)/);
  assert.match(lf, /from file/);
  assert.match(lf, /missing/);
  assert.match(np, /please confirm/);
});

test("one primary action, Confirm and open; amounts through the G5 formatter", () => {
  assert.equal((np.match(/<PrimaryButton/g) ?? []).length, 1);
  assert.match(np, /Confirm and open/);
  assert.match(lf, /fmt\.sar\(/);
  assert.match(lf, /fmt\.pct\(/);
  assert.doesNotMatch(lf, /toFixed\(/);
});
