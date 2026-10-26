/** PLAN_R12 Session D: the ladder's pure functions over an engine result (DD-02, a construction deal that fails its
 *  hurdle before stress) and the component contract (StressLabR12, ScenarioEditor, MonitoringPlanPanel,
 *  MonitoringTierPanel: answer first, kit only, no raw JSON). */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import {
  COL_ORDER, SHOCK_FIELDS, cellTone, dataDomainsHref, cellValue, ladderGroups, reverseLines, shocksFrom, stress2Key, tierSentence, visibleCols,
  type Stress2Result,
} from "./dealdesk-stress2.ts";

const here = new URL("./", import.meta.url).pathname;
const r = JSON.parse(readFileSync(here + "dealdesk-stress2.fixture.json", "utf8")) as Stress2Result;
const comp = (f: string) => readFileSync(here + "../../components/v5/" + f, "utf8");

test("D: the ladder groups every family mild -> moderate -> severe, rating -1/-2/-3 visible", () => {
  const g = ladderGroups(r);
  assert.deepEqual(g.map((x) => x.id).slice(0, 6), ["macro", "sector", "borrower", "collateral", "rating", "combined"]);
  const rating = g.find((x) => x.id === "rating")!;
  assert.deepEqual(rating.rows.map((x) => x.id), ["notch_1", "notch_2", "notch_3"]);
  assert.deepEqual(rating.rows.map((x) => x.severity), ["mild", "moderate", "severe"]);
  const oil = g.find((x) => x.id === "macro")!.rows.filter((x) => x.id.startsWith("oil_"));
  assert.deepEqual(oil.map((x) => x.severity), ["mild", "moderate", "severe"]);
  assert.equal(g.reduce((n, x) => n + x.rows.length, 0), r.rows.length);
});

test("D: combined severe includes the revenue shock (O5)", () => {
  const cs = r.rows.find((x) => x.id === "combined_severe")!;
  assert.ok(cs.applicable);
  assert.ok(cs.steps.some((s) => s.step === "Revenue shock"));
});

test("D: not-applicable rows keep their reason and show no cells (O6)", () => {
  const na = r.rows.filter((x) => !x.applicable);
  for (const s of na) {
    assert.match(s.na_reason ?? "", /^Not applicable to this deal: /);
    for (const c of COL_ORDER) assert.equal(cellTone(c, s), "na");
    assert.equal(cellValue("dscr", s), "");
  }
  assert.equal(na.length, r.counts.not_applicable);
});

test("D: LTV column only where collateral is pledged", () => {
  const cols = visibleCols(r);
  assert.equal(cols.includes("ltv_cover"), r.show_ltv);
  const c = r.rows.find((x) => x.id === "coll_40")!;
  if (r.show_ltv && c.applicable) assert.match(cellValue("ltv_cover", c), /%$/);
});

test("D: verdict, tier and commentary come from the engine", () => {
  assert.ok(["Restructure", "Approve with enhanced monitoring", "Approve, standard monitoring", "Approve"].includes(r.verdict.verdict));
  assert.ok(r.commentary.words >= 100 && r.commentary.words <= 200);
  assert.ok(r.commentary.text.startsWith(`Verdict: ${r.verdict.verdict}.`));
  assert.equal(r.tier.review_frequency_months, { High: 3, Medium: 6, Standard: 12 }[r.tier.tier]);
});

test("D: reverse stress lines start with the rating family", () => {
  const l = reverseLines(r);
  assert.equal(l[0].label, "Rating");
  assert.ok(l.length >= 3);
  for (const x of l) assert.ok(x.text && !/undefined|NaN/.test(x.text), x.text);
});

test("D: the stressed RAROC shown is the checked one (O4)", () => {
  for (const s of r.rows.filter((x) => x.applicable)) {
    assert.equal(s.metrics!.lifetime_raroc, s.raroc_check!.raroc);
    assert.ok(s.raroc_check!.attribution_ok);
  }
});

test("D: request key and the tier sentence", () => {
  assert.equal(stress2Key("DD-02", { terms: { b: 1, a: 2 } as never }), stress2Key("DD-02", { terms: { a: 2, b: 1 } as never }));
  assert.equal(tierSentence({ tier: "High", set_on: "2026-10-19", driver_labels: ["Revenue", "Largest-customer concentration"] }),
    "Monitoring tier High, set by Deal Desk on 2026-10-19 because revenue, largest-customer concentration");
});

test("D: the editor maps typed values to engine shocks", () => {
  const s = shocksFrom({ oil_pct: "−30", revenue_pct: "-20", notches: "2", collateral_pct: "", customer_loss_share: "100" }, true);
  assert.deepEqual(s, { oil_pct: -30, revenue_pct: -0.2, notches: 2, customer_loss_share: 1, guarantee_unenforceable: true });
  assert.ok(SHOCK_FIELDS.length >= 10);
});

test("D: component contract (kit, answer first, no debug text)", () => {
  const lab = comp("dealdesk/stress-lab-r12.tsx");
  for (const name of ["export function StressLabR12", "export function StressCommentary", "export function StressVerdictCard", "export function ChainDrawer"]) assert.ok(lab.includes(name), name);
  assert.ok(lab.indexOf("<StressCommentary") < lab.indexOf("<Ladder "), "commentary above the grid");
  assert.ok(comp("dealdesk/stress-lab-editor.tsx").includes("export function ScenarioEditor"));
  assert.ok(comp("dealdesk/stress-lab-monitoring.tsx").includes("export function MonitoringPlanPanel"));
  const ews = comp("ews/monitoring-tier-panel.tsx");
  assert.ok(ews.includes("export function MonitoringTierPanel"));
  const page = comp("ews/customer-detail.tsx");
  assert.equal((page.match(/<MonitoringTierPanel /g) ?? []).length, 1, "one mount line on the EWS customer page");
  for (const f of ["dealdesk/stress-lab-r12.tsx", "dealdesk/stress-lab-editor.tsx", "dealdesk/stress-lab-monitoring.tsx", "ews/monitoring-tier-panel.tsx"]) {
    const src = comp(f);
    assert.ok(!/TODO|console\.log|JSON\.stringify\(r\b/.test(src), f);
  }
});

test("D: every chain step links to Data Domains", () => {
  assert.equal(dataDomainsHref({ domain: "deal_desk", relation: "dd_stress_sensitivity", period: "2026Q2" }),
    "/data-builder?domain=deal_desk&relation=dd_stress_sensitivity&period=2026Q2");
  assert.equal(dataDomainsHref({ domain: null, relation: "x", period: null }), null);
});
