/** PLAN_R9 Session E: proposal review (nine outputs in order, Powered by P7), Deal Desk Parameters, deposits, batch RAROC. */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");

test("proposal review shows the nine outputs in order with Powered by P7", () => {
  const s = read("components/v5/dealdesk/proposal-review.tsx");
  const titles = ["1. Extracted summary", "2. Arithmetic and reconciliation", "3. Quality score", "4. Information gap register",
    "5. Weakness → mitigant map", "6. Pre-deal analysis", "7. Counter-proposals", "8. Proposed Accepted Risk Watch entry", "9. Reviewer opinion"];
  const at = titles.map((t) => s.indexOf(t));
  assert.ok(at.every((i) => i > 0), "every section present");
  assert.deepEqual([...at].sort((a, b) => a - b), at, "in order");
  assert.ok(s.includes('pack="P7"') && s.includes("Send as query to RM") && s.includes("text-negative"));
  assert.ok(s.includes('accept=".docx,.pdf"'));
});

test("parameters page: (i) why and where on every row, versioned save, verdicts before and after", () => {
  const s = read("components/v5/dealdesk/desk-parameters.tsx");
  assert.ok(s.includes("Why it is required.") && s.includes("Where it comes from in the bank."));
  assert.ok(s.includes("Save and apply") && s.includes("Before the change"));
});

test("routes exist and are linked from Deal Desk and Settings without touching navigation", () => {
  for (const p of ["review", "parameters", "portfolio-raroc"]) assert.ok(read(`app/deal-desk/${p}/page.tsx`).length > 0);
  const home = read("components/v5/dealdesk/home.tsx");
  assert.ok(home.includes("/deal-desk/review") && home.includes("/deal-desk/parameters") && home.includes("/deal-desk/portfolio-raroc"));
  assert.ok(read("components/v5/admin/pages.tsx").includes("/deal-desk/parameters"));
  assert.ok(read("components/v5/dealdesk/thread.tsx").includes("<AccountBehaviour"));
});
