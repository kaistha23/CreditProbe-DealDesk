import assert from "node:assert/strict";
import { test } from "node:test";

import { isSkippable, previousFromEntries, previousFromTrail, recordVisit, resetTrail } from "../v5/back-trail.ts";

/** R7: Back is the exact previous entry of this tab; never the sign-in page; none after a fresh load. */

test("the previous Navigation API entry is Back, unless it is the sign-in page or there is none", () => {
  assert.deepEqual(previousFromEntries(["http://h/workspace", "http://h/deal-desk/DD-02"], 1), { url: "http://h/workspace", delta: 1 });
  // a duplicate of the current page (reloaded, or linked to itself) is skipped
  assert.deepEqual(previousFromEntries(["http://h/investigations", "http://h/investigations/i1", "http://h/investigations/i1"], 2),
                   { url: "http://h/investigations", delta: 2 });
  assert.equal(previousFromEntries(["http://h/login?next=%2Fdeal-desk", "http://h/deal-desk"], 1), null);
  assert.equal(previousFromEntries(["http://h/deal-desk/DD-02"], 0), null);
  assert.ok(isSkippable("/login") && isSkippable("http://h/login?next=x") && !isSkippable("/loginsomething"));
});

test("the trail: pushes add, a step back pops, a replace overwrites, the sign-in page is never recorded", () => {
  resetTrail();
  assert.equal(previousFromTrail(), null);
  recordVisit("/login");
  recordVisit("/workspace");
  assert.equal(previousFromTrail(), null, "a fresh load has no previous");
  recordVisit("/deal-desk?status=draft");
  recordVisit("/deal-desk/DD-02");
  recordVisit("/deal-desk/DD-02?step=structure");
  assert.equal(previousFromTrail()?.url, "/deal-desk/DD-02");
  recordVisit("/deal-desk/DD-02");            // Back
  assert.equal(previousFromTrail()?.url, "/deal-desk?status=draft");
  recordVisit("/deal-desk/DD-02?step=proposal", true);  // a replace
  assert.equal(previousFromTrail()?.url, "/deal-desk?status=draft");
  resetTrail();
});
