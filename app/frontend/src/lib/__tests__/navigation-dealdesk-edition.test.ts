// Deal Desk edition (October 2026): CreditProbe with Deal Desk as its one intelligence module. The Cockpit stays the
// landing page (its brief and Ask are Deal Desk's, components/home); the navigation lists the Cockpit, Deal Desk, the
// Work group, Data Domains and Analysis Studio, Trace, and Admin; every removed module's route redirects to Deal
// Desk, in the client (liveHref) and at the server (next.config.ts redirects).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";

delete process.env.NEXT_PUBLIC_CP_EDITION;   // the build default is the Deal Desk edition
const nav = await import("../navigation.ts");

const labels = (group: Parameters<typeof nav.itemsInGroup>[0], isAdmin = true) =>
  nav.itemsInGroup(group, "ADMIN", false, isAdmin).map((i) => i.label);

test("the Deal Desk edition is the default; the Cockpit is the landing page and Deal Desk is where removed routes go", () => {
  assert.equal(nav.edition(), "dealdesk");
  assert.equal(nav.DEALDESK_HOME, "/deal-desk");
  assert.equal(nav.liveHref("/"), "/");
  assert.equal(nav.liveHref("/cockpit/thread/abc"), "/cockpit/thread/abc");
  assert.equal(nav.DEALDESK_EDITION_HREFS[0], "/");
});

test("Deal Desk is the one intelligence module; the other modules leave the navigation", () => {
  assert.deepEqual(labels("Home"), ["Cockpit"]);
  assert.deepEqual(labels("Intelligence"), ["Deal Desk"]);
  const all = nav.NAV_GROUPS.flatMap((g) => labels(g));
  for (const gone of ["BRF", "Lenses", "Early Warning", "Playbooks", "Stress Testing", "What-If", "Borrower 360", "Scorecard"]) {
    assert.ok(!all.includes(gone), gone);
  }
});

test("everything Deal Desk draws on stays: the Work group, Data, Trace and Admin", () => {
  assert.deepEqual(labels("Work"), ["Workspace", "Mail", "Playbook", "Policy Docs", "Projects", "Investigations", "Analyses"]);
  assert.deepEqual(labels("Data"), ["Data Domains", "Analysis Studio"]);
  assert.deepEqual(labels("Govern"), ["Trace & Lineage"]);
  assert.deepEqual(labels("Admin"), ["Workflow", "Users & Teams", "Agent Operations", "AI Studio", "Settings", "Audit log"]);
  assert.deepEqual(labels("Admin", false), []);
});

test("a removed module's route redirects to Deal Desk; a kept route is unchanged", () => {
  for (const gone of ["/lenses", "/lenses/cro", "/early-warning/model", "/what-if/thread/t1",
                      "/borrower-360", "/scorecard-validation", "/brf", "/stress", "/playbooks", "/engine-builder/new",
                      "/analysis/a1", "/intelligence", "/queries?id=Q-1", "/accepted-risk?tier=2"]) {
    assert.equal(nav.liveHref(gone), "/deal-desk", gone);
  }
  for (const kept of ["/", "/cockpit/thread/t1", "/deal-desk", "/deal-desk/review", "/workspace", "/analyses", "/policy-docs", "/data-builder",
                      "/studio", "/trace/run-1", "/settings"]) {
    assert.equal(nav.liveHref(kept), kept, kept);
  }
});

test("the full product is still one environment variable away", () => {
  process.env.NEXT_PUBLIC_CP_EDITION = "full";
  try {
    assert.equal(nav.edition(), "full");
    assert.equal(nav.liveHref("/intelligence"), "/");
    assert.equal(nav.liveHref("/lenses"), "/lenses");
  } finally {
    delete process.env.NEXT_PUBLIC_CP_EDITION;
  }
});

test("next.config.ts redirects the same routes the navigation removes", () => {
  const config = fs.readFileSync(path.join(process.cwd(), "next.config.ts"), "utf8");
  const block = config.slice(config.indexOf("DEALDESK_EDITION_REMOVED = ["));
  const listed = [...block.slice(0, block.indexOf("];")).matchAll(/"(\/[a-z0-9-]+)"/g)].map((m) => m[1]);
  assert.deepEqual(listed, [...nav.DEALDESK_EDITION_REMOVED]);
  assert.ok(!config.includes('source: "/",'), "the Cockpit is the landing page: no redirect of /");
});
