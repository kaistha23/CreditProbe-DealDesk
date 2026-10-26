/**
 * R14 U: source checks that the shell rules stay in place (K1, K11, K17, K28).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(import.meta.dirname, "..", "..", "..");
const read = (p: string) => readFileSync(join(SRC, p), "utf8");

test("K28: every header menu is the house Dropdown (no hand-made role=menu)", () => {
  for (const f of ["components/v5/dealdesk/action-bar.tsx", "components/v5/core/user-menu.tsx",
                   "components/v5/intel/ib/tools-menu.tsx", "components/v5/intel/network/tools-menu.tsx",
                   "components/v5/intel/portfolio/tools-menu.tsx", "components/v5/intel/governance/tools.tsx"]) {
    const s = read(f);
    assert.ok(s.includes("<Dropdown"), `${f} uses the house Dropdown`);
    assert.ok(!/role="menu"/.test(s), `${f} has no hand-made menu`);
  }
  const more = read("components/v5/dealdesk/action-bar.tsx");
  assert.ok(more.includes('title: "Deal file"') && more.includes('title: "Intelligence"'));
  const user = read("components/v5/core/user-menu.tsx");
  for (const l of ['"Settings"', '"Sign out"', "Viewing as"]) assert.ok(user.includes(l), l);
});

test("K1: Noor navigations carry their origin and are pushes", () => {
  const s = read("components/noor/noor-store.ts");
  const calls = s.match(/navigate\(([^)]*)/g) ?? [];
  const bare = calls.filter((c) => !c.includes("via(") && !/navigate\(\s*href\s*:/.test(c) && !c.startsWith("navigate(fn"));
  assert.deepEqual(bare, [], "every navigate() goes through via()");
  const bar = read("components/noor/noor-topbar.tsx");
  assert.ok(bar.includes("router.push(href)") && !bar.includes("router.replace(href)"));
  assert.ok(read("components/layout/app-shell.tsx").includes("<OriginBackLink />"), "the shell shows Back to <origin>");
});

test("K11: Borrower 360 on EWS cards, Who to call, Book rows", () => {
  assert.ok(read("components/v5/ews/customers.tsx").includes('<Borrower360Button customerId={row.customer_id} period={period} from="ews"'));
  assert.ok(read("components/v5/intel/ib/who-to-call-panel.tsx").includes("<Borrower360Button"));
  assert.ok(read("components/v5/dealdesk/book/book-tab.tsx").includes("<Borrower360Button"));
});

test("K17: the Deal Desk list reads every deal and searches fuzzily", () => {
  const s = read("components/v5/dealdesk/home.tsx");
  assert.ok(s.includes("dealdesk.deals()") && !s.includes("dealdesk.proposals()"));
  assert.ok(s.includes("searchDeals(") && s.includes("findNamedDeal(question, all)"));
  assert.ok(s.includes('"pending"'), "a Pending tab that matches the Pipeline tab");
});
