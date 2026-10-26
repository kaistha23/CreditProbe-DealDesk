/** PLAN_R12 Session P: the product sections' pure functions over server responses (fictional fixture generated from
 *  the backend analytics), and the component contract (answer first, kit and shared KpiRow, Plotly only, no raw JSON). */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import {
  amt, coverTone, decisionTone, deficitSeries, escrowTiles, month, pct, projectTiles, ruleValue, smeCardLine, smeTiles, srcLine,
  syndicationTiles, times,
  type EscrowResult, type ProjectResult, type SmeCount, type SmeDecision, type SmeLane, type SyndicationResult,
} from "./format.ts";

const here = new URL("./", import.meta.url).pathname;
const fx = JSON.parse(readFileSync(here + "products.fixture.json", "utf8")) as {
  project: ProjectResult; escrow: EscrowResult; syndication: SyndicationResult; sme_lane: SmeLane; sme_count: SmeCount; sme_one: SmeDecision;
};
const comp = (f: string) => readFileSync(here + f, "utf8");

test("formatters", () => {
  assert.equal(amt(12.345), "SAR 12.3m");
  assert.equal(amt(1.5), "SAR 1.50m");
  assert.equal(amt(1200, "USD"), "USD 1.20bn");
  assert.equal(amt(null), "–");
  assert.equal(pct(0.625), "63%");
  assert.equal(times(1.2345), "1.23x");
  assert.equal(month("2026-11"), "Nov 2026");
  assert.equal(ruleValue(2.5), "2.50");
  assert.equal(ruleValue(3), "3");
});

test("lineage line", () => {
  assert.equal(srcLine({ domain: "Deal Desk", relation: "dd_project", key: { project_id: "PRJ-1" }, column: "wd_pct", period: "2026Q2" }),
               "Deal Desk · dd_project · PRJ-1 · wd_pct · 2026Q2");
  assert.match(srcLine({ domain: "Deal Desk", relation: ["dd_project", "dd_facility_limit"], derived: "a / b" }), /dd_project, dd_facility_limit — a \/ b/);
  assert.equal(srcLine(undefined), "");
});

test("cover tone", () => {
  assert.equal(coverTone(1.1, 1.25), "negative");
  assert.equal(coverTone(1.3, 1.25), "warning");
  assert.equal(coverTone(2, 1.25), "positive");
  assert.equal(coverTone(null, 1.25), "neutral");
});

test("project tiles and deficit series", () => {
  const t = projectTiles(fx.project);
  assert.equal(t.length, 4);
  assert.deepEqual(t.map((x) => x.label), ["Financed projects", "Cover ratio", "Peak project deficit", "Deficit at 90 days' delay"]);
  assert.equal(t[1].value, times(fx.project.cover_ratio!.ratio));
  const s = deficitSeries(fx.project);
  assert.equal(s.length, 4);
  assert.equal(s[0].name, "Base");
  assert.deepEqual(s[0].y, fx.project.delay_stress!.rows[0].deficit);
  assert.ok(Math.max(...s[3].y) >= Math.max(...s[0].y));
});

test("escrow and syndication tiles", () => {
  const e = escrowTiles(fx.escrow);
  assert.equal(e.length, 4);
  assert.equal(e[3].value, String(fx.escrow.releases!.breaches));
  const s = syndicationTiles(fx.syndication);
  assert.equal(s[0].label, "Our commitment");
  assert.match(s[0].sub ?? "", /25%/);
});

test("SME lane, card and decision tones", () => {
  const t = smeTiles(fx.sme_lane.counts);
  assert.equal(t[0].value, "3");
  assert.equal(smeCardLine(fx.sme_count), fx.sme_count.sub);
  assert.equal(smeCardLine({ ...fx.sme_count, total: 0 }), "No SME applications in the lane");
  assert.equal(decisionTone("Refer to full flow"), "warning");
  assert.equal(fx.sme_one.decision, "Refer to full flow");
  assert.ok(fx.sme_one.route);
});

test("component contract", () => {
  for (const f of ["project-section.tsx", "escrow-section.tsx", "syndication-section.tsx", "sme-fast-track.tsx"]) {
    const c = comp(f);
    assert.match(c, /from "\.\.\/kit"/, `${f} uses the Deal Desk kit`);
    assert.match(c, /<Answer /, `${f} answers first`);
    assert.doesNotMatch(c, /JSON\.stringify|TODO|console\.log/, `${f} has no raw JSON or debug text`);
    assert.doesNotMatch(c, /recharts|chart\.js|d3/, `${f} charts with Plotly only`);
  }
  assert.match(comp("parts.tsx"), /KpiRow/);
  const idx = comp("index.ts");
  for (const name of ["ProductSection", "ProjectSection", "EscrowSection", "SyndicationSection", "SmeFastTrack", "useSmeFastTrackCount"]) assert.match(idx, new RegExp(name));
});
