/** PLAN_R12 Session I: the Book (I7, I8, I29, I31) — exports for U, filters, row actions, RAROC drift rename and redirect. */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");
const dir = "components/v5/dealdesk/book/";

test("BookTab is exported for U's shell with the landing-card counts", () => {
  const idx = read(dir + "index.ts");
  for (const x of ["BookTab", "fetchBookCounts", "RarocDriftView", "FeedbackView"]) assert.ok(idx.includes(x), x);
  const tab = read(dir + "book-tab.tsx");
  assert.ok(tab.includes("export function BookTab") && tab.includes("filter?: string"), "takes U's filter prop");
  assert.ok(tab.includes('"going-bad": "going_bad"') && tab.includes('renewals: "renewals_due"'), "maps the landing cards' filter words");
});

test("the Book has the plan's filters, columns and row actions", () => {
  const api = read(dir + "api.ts");
  for (const f of ["going_bad", "repricing", "promises_unmet", "tier_high", "renewals_due", "conditions_due"]) assert.ok(api.includes(`"${f}"`), f);
  const tab = read(dir + "book-tab.tsx");
  for (const t of ["Raise or lower tier", "Open deal", "Start renewal", "Send to Early Warning", "Why RAROC moved", "Promises against delivery",
    "Renewal: reprice or restructure", "Covenants, conditions and Early Warning", "RAROC drift", "Feedback to origination"]) assert.ok(tab.includes(t), t);
  assert.ok(tab.includes("Reason (required, logged)"), "a tier change needs a reason");
  assert.ok(!/TODO|FIXME|JSON\.stringify\(d/.test(tab), "no debug text");
});

test("Portfolio RAROC at origination is renamed RAROC drift and the old route redirects", () => {
  const v = read("components/v5/dealdesk/portfolio-raroc.tsx");
  assert.ok(v.includes(">RAROC drift<") && v.includes("<KpiRow") && v.includes("DriftWaterfall") && v.includes("export const PortfolioRarocPage"));
  assert.ok(!v.includes("Portfolio RAROC at origination</h1>"));
  const old = read("app/deal-desk/portfolio-raroc/page.tsx");
  assert.ok(old.includes('redirect("/deal-desk/raroc-drift")'));
  assert.ok(read("app/deal-desk/raroc-drift/page.tsx").includes("<RarocDriftPage"));
});

test("feedback to origination: maker-checker hurdle overrides, ratchet and realisation", () => {
  const f = read(dir + "feedback-view.tsx");
  for (const t of ["Sector hurdle overrides from observed drift", "Proposals waiting for a checker", "Margin ratchet", "Promise realisation in use"]) assert.ok(f.includes(t), t);
});
