import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  FLOW_STEPS, STRESS_DISABLED_REASON, defaultStressKeys, evidenceSource, grouped, pct, prefillQuery, sarm, stressEnabled, survivalLabel,
  survivalTone, swotSummary, x, type StructureSet,
} from "./dealdesk-flow.ts";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");
const dir = "components/v5/dealdesk/";

test("R14 F (K23, K31): Upload · Proposal check · Review · Analysis · Structure · Recommendation; Stress is a header button", () => {
  assert.deepEqual(FLOW_STEPS.map((s) => s.label), ["Upload", "Proposal check", "Review", "Analysis", "Structure", "Recommendation"]);
  assert.ok(!FLOW_STEPS.some((s) => (s.key as string) === "stress"));
  assert.equal(stressEnabled("review", new Set()), false);
  assert.equal(stressEnabled("structure", new Set()), true);
  assert.equal(stressEnabled("analysis", new Set(["structure"])), true, "once Structure was visited");
  assert.ok(STRESS_DISABLED_REASON.includes("Structure"));
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes('data-testid="dealdesk-stress-button"') && t.includes("disabled={!canStress}") && t.includes("STRESS_DISABLED_REASON"));
  assert.ok(t.includes('data-testid="dealdesk-step-proposal-check-view"'), "the Proposal check step slot (Session p fills it)");
});

const set = {
  proposal_id: "X", obligor: "Fictional Co", selected: "recommended", selected_by_user: false, default_note: null, plain_words: [], sva_basis: "",
  bar: { label: "Selected: Recommended", key: "recommended", enabled: false, reason: "RAROC 14.50% < 15.0% hurdle" },
  groups: [{ group: "Ask", keys: ["ask"] }, { group: "Recommended", keys: ["recommended"] }, { group: "Alternatives", keys: [] }, { group: "Your structures", keys: [] }],
  rows: [{ key: "ask" }, { key: "recommended" }], regime: { label: "", key: "", brent: null, month: null, chg_12m: null, percentile: null, vintage: "", source: "" },
} as unknown as StructureSet;

test("K25: the set is grouped Ask, Recommended, Alternatives, Your structures; the stress default is the selection and the ask", () => {
  assert.deepEqual(grouped(set).map((g) => [g.group, g.rows.length]), [["Ask", 1], ["Recommended", 1], ["Alternatives", 0], ["Your structures", 0]]);
  assert.deepEqual(defaultStressKeys(set), ["recommended", "ask"]);
  assert.deepEqual(defaultStressKeys({ ...set, selected: "ask" }), ["ask"]);
  const s = read(dir + "flow-structure-set.tsx");
  assert.ok(s.includes('data-testid="flow-selected-bar"') && s.includes("Cannot recommend: {set.bar.reason}") && s.includes("disabled={busy || !set.bar.enabled}"),
    "a disabled Recommend states the reason");
});

test("K20/K23: survival labels and tones; fails before stress is not a pass", () => {
  assert.equal(survivalLabel({ status: "fails_before_stress", survives_up_to: "none" }), "Fails before stress");
  assert.equal(survivalLabel({ status: "stressed", survives_up_to: "none" }), "Breaks at mild");
  assert.equal(survivalLabel({ status: "stressed", survives_up_to: "moderate" }), "Survives up to moderate");
  assert.equal(survivalLabel({ status: "stressed", survives_up_to: "severe" }), "Survives severe");
  assert.equal(survivalTone({ status: "stressed", survives_up_to: "none" }), "negative");
  assert.equal(survivalTone({ status: "fails_before_stress", survives_up_to: "none" }), "neutral");
});

test("formatting and the monitoring prefill query", () => {
  assert.equal(pct(0.145, 2), "14.50%");
  assert.equal(pct(null), "–");
  assert.equal(x(3.979), "3.98x");
  assert.equal(sarm(-0.051), "SAR −0.05m");
  assert.equal(sarm(96.8), "SAR 96.8m");
  const q = new URLSearchParams(prefillQuery({ obligorId: "CB00020", source: "ews", reason: "EWS band Red", facilityRef: null }));
  assert.equal(q.get("obligor_id"), "CB00020");
  assert.equal(q.get("source"), "ews");
  assert.equal(q.get("facility_ref"), null);
});

test("K25 (3): the SWOT card picks strengths and weaknesses with their sources", () => {
  const s = swotSummary([
    { id: "1", quadrant: "strength", theme: "", text: "DSCR 1.56x", evidence: [{ domain: "deal_desk", relation: "dd_proposal" }] },
    { id: "2", quadrant: "weakness", theme: "", text: "Leverage 3.98x" }, { id: "3", quadrant: "threat", theme: "", text: "Oil" },
  ]);
  assert.equal(s.strengths.length, 1);
  assert.equal(s.weaknesses.length, 2);
  assert.equal(s.counts.threat, 1);
  assert.equal(evidenceSource(s.strengths[0]), "deal_desk.dd_proposal");
});

test("K24/K35: Recommendation is never blank; Monitoring is a header button next to Book; Propose for monitoring on every list", () => {
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes('step === "recommendation" ? <RecommendationPanel'), "rendered on every deal, with or without a saved recommendation");
  const r = read(dir + "flow-recommendation.tsx");
  assert.ok(r.includes('data-testid="dealdesk-prepare-proposal"') && r.includes('hasSlot("PrepareProposal")'));
  const h = read(dir + "home.tsx");
  assert.ok(h.indexOf('data-testid="dealdesk-tab-book"') < h.indexOf('data-testid="dealdesk-tab-monitoring"'));
  assert.ok(read(dir + "book/book-tab.tsx").includes("<ProposeMonitoringButton compact"));
  assert.ok(read("components/v5/ews/customers.tsx").includes("<ProposeMonitoringButton compact"));
  assert.ok(read("components/v5/b360/workspace.tsx").includes("<MonitoringLine"));
  assert.ok(t.includes('testId="dealdesk-propose-monitoring"'));
});
