// PLAN_R5 P1: the v5 navigation. Playbook under Intelligence, Lenses added there, Policy Docs stays in Work,
// and an Admin group at the bottom (Workflow, Users & Teams, Agent Operations, AI Studio, Settings, Audit log).
import assert from "node:assert/strict";
import { test } from "node:test";

process.env.NEXT_PUBLIC_COCKPIT_V4_API = "http://127.0.0.1:8500";
// These are the full product's groups; the Deal Desk edition (the build default) is in navigation-dealdesk-edition.test.ts.
process.env.NEXT_PUBLIC_CP_EDITION = "full";
const nav = await import("../navigation.ts");

const labels = (group: Parameters<typeof nav.itemsInGroup>[0], isAdmin = true) =>
  nav.itemsInGroup(group, "ADMIN", false, isAdmin).map((i) => i.label);

// PLAN_R10 S1 supersedes the R9 grouping: Home = Cockpit, then Intelligence, Work, Data, Admin.
test("R10: Home is the Cockpit; Intelligence and Work in the order of the plan", () => {
  assert.deepEqual(labels("Home"), ["Cockpit"]);
  assert.deepEqual(labels("Intelligence"),
    ["Early Warning", "Borrower 360", "What-If", "Lenses", "Deal Desk", "Scorecard", "BRF"]);
  assert.deepEqual(labels("Work"),
    ["Workspace", "Mail", "Playbook", "Policy Docs", "Projects", "Investigations", "Analyses"]);
  assert.deepEqual(labels("Functionalities"), []);
  assert.deepEqual(nav.NAV_GROUPS.slice(0, 4), ["Home", "Intelligence", "Work", "Data"]);
});

test("R10: Intelligence Library, Queries and Accepted Risk Watch leave the navigation and redirect", () => {
  const all = nav.NAV_GROUPS.flatMap((g) => labels(g));
  for (const gone of ["Intelligence Library", "Queries", "Accepted Risk Watch"]) assert.ok(!all.includes(gone), gone);
  assert.equal(nav.liveHref("/intelligence"), "/");
  assert.equal(nav.liveHref("/queries?id=Q-1"), "/");
  assert.equal(nav.liveHref("/accepted-risk?tier=2"), "/early-warning");
  assert.equal(nav.liveHref("/deal-desk"), "/deal-desk");
});

test("Admin is the last group and lists its six pages in order", () => {
  assert.equal(nav.NAV_GROUPS[nav.NAV_GROUPS.length - 1], "Admin");
  assert.deepEqual(labels("Admin"),
    ["Workflow", "Users & Teams", "Agent Operations", "AI Studio", "Settings", "Audit log"]);
});

test("Admin is hidden from a user who is not an administrator", () => {
  assert.deepEqual(labels("Admin", false), []);
});

test("Govern is empty in v5 (Workflow moved to Admin)", () => {
  assert.deepEqual(labels("Govern"), []);
  assert.deepEqual(labels("Data"), ["Data Domains"]);
});

// PLAN_R6 B5: the BUILD group is now DATA and Data Builder is now Data Domains, on the same route.
test("R6 B5: the DATA group holds Data Domains at /data-builder", () => {
  assert.ok(nav.NAV_GROUPS.includes("Data"));
  assert.ok(!(nav.NAV_GROUPS as string[]).includes("Build"));
  const item = nav.NAV_ITEMS.find((i) => i.href === "/data-builder");
  assert.equal(item?.label, "Data Domains");
  assert.equal(item?.group, "Data");
  assert.ok(!nav.NAV_ITEMS.some((i) => i.label === "Data Builder"));
});
