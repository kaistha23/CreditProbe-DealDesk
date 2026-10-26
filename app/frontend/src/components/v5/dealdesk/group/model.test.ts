import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type CapTest, type Conduct, type GroupFacts, type SwotPoint, byQuadrant, capLine, conductKpis, evidenceLine, mitigantTone, ownershipText, pts,
  sarm, statusTone, stepLabel, structureLine,
} from "./model.ts";

test("money and percentages", () => {
  assert.equal(sarm(554.234), "SAR 554.2m");
  assert.equal(sarm(4.5), "SAR 4.50m");
  assert.equal(sarm(1250), "SAR 1.25bn");
  assert.equal(sarm(null), "–");
  assert.equal(pts(110.84), "111%");
  assert.equal(pts(8.53), "8.5%");
});

test("tones follow the status words", () => {
  assert.equal(statusTone("classified"), "negative");
  assert.equal(statusTone("in arrears"), "warning");
  assert.equal(statusTone("performing"), "positive");
  assert.equal(statusTone("something else"), "neutral");
  assert.equal(mitigantTone("open"), "negative");
  assert.equal(mitigantTone("answered by a condition"), "warning");
  assert.equal(mitigantTone("answered by the structure"), "positive");
});

test("evidence line names domain, relation and keys", () => {
  assert.equal(evidenceLine({ domain: "deposits", relation: "dep_month", keys: { obligor_id: "CB01338" } }), "deposits · dep_month · obligor_id=CB01338");
  const many = evidenceLine({ domain: "cockpit", relation: "corp_facility_quarter", keys: { borrower_id: ["a", "b", "c", "d"] } });
  assert.match(many, /borrower_id=a,b,c…\(4\)/);
  assert.equal(stepLabel("review"), "Review");
});

const cap = (over: Partial<CapTest>): CapTest => ({
  group_name: "G", before_ead: 374.2, deal_ead_y1: 180, after_ead: 554.2, binding_limit: 500, binding: "connected group limit", headroom_after: -54.2,
  status: "breach", utilisation_pct: 110.84, basis: "EAD", connected_group_limit: { limit_sar_mn: 500, basis: "CP-1.2" }, approved_cap: null,
  members: [], increase_ask: null, ...over,
});

test("cap line is the answer first", () => {
  assert.equal(capLine(cap({})), "Group exposure SAR 554.2m after the deal against the connected group limit of SAR 500.0m (111%): breach.");
  assert.match(capLine(cap({ status: "within", binding: "approved cap", after_ead: 150, binding_limit: 200, utilisation_pct: 75 })),
               /approved group cap of SAR 200.0m \(75.0%\): within\.$/);
  assert.equal(capLine(null), "Group cap test not available for this deal.");
});

test("structure line and ownership text", () => {
  const f = {
    obligor: { id: "X", name: "Test Co", existing: true },
    structure: { group_name: "Test Group", members: 4, standalone: false, parent: { name: "Test Holding", ownership_pct: 80 }, subsidiaries: [],
                 sisters: [{}, {}] },
    connected_parties: { classified: 1, in_litigation: 1, in_arrears: 0 },
  } as unknown as GroupFacts;
  assert.equal(structureLine(f), "Test Group: 4 members, parent Test Holding (80.0%), 2 sister companies. Connected parties: 1 classified, 1 in litigation.");
  assert.equal(ownershipText({ name: "A", pct: null, indirect_pct: 56, via: "Test Holding", ubo: true, kind: "person" }), "56.0% via Test Holding");
});

test("SWOT grouped by quadrant keeps order", () => {
  const p = (id: string, q: SwotPoint["quadrant"]): SwotPoint => ({ id, quadrant: q, kind: "financial", theme: "t", text: id, evidence: [], link: {} });
  const g = byQuadrant([p("s1", "strength"), p("w1", "weakness"), p("s2", "strength")]);
  assert.deepEqual(g.strength.map((x) => x.id), ["s1", "s2"]);
  assert.equal(g.threat.length, 0);
});

test("conduct KPIs", () => {
  const c = {
    turnover: { to_limits_x: 2.03, credit_turnover_12m_sar_mn: 68.6, credit_turnover_prev_12m_sar_mn: 73.9, growth_pct: -7, routing_required_x: 1.5,
                routing_actual_x: 2.03, routing_compliant: true, routing_achieved_pct: 135.6, months: [] },
    returned_cheques: { count_12m: 4, amount_12m_sar_mn: 1.6, months_with_returns: 4, reasons: [], dates: [] },
    utilisation: { limits_sar_mn: 33.7, drawn_sar_mn: 24.6, utilisation_pct: 73, over_90_4q: [], excess_days_12m: 0, facilities: [] },
    past_dues: { quarters: Array(8).fill({ quarter: "q", max_dpd: 0, past_due_facilities: 0 }), quarters_past_due_8q: 0, max_dpd_8q: 0, max_dpd_4q: 0,
                 last_past_due: null },
    bureau: { trend: "stable", max_external_dpd_4q: 0, enquiries_4q: 2, quarters: [], entity_reports: [] },
  } as unknown as Conduct;
  const k = conductKpis(c);
  assert.equal(k[0].value, "2.03x");
  assert.equal(k[0].sub, "SAR 68.6m in 12m (PY SAR 73.9m)");
  assert.equal(k[1].value, "136%");
  assert.equal(k[2].tone, "negative");
  assert.equal(k[4].value, "None");
  assert.equal(k[5].value, "Stable");
});
