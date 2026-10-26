import assert from "node:assert/strict";
import { test } from "node:test";

import { type Fig, type Pair, type SecurityItem, decisionTone, delta, failureTone, pairCounts, pct, questionSummary, rankItems, sarm, sourceLine,
  statusTone } from "./model.ts";

const f = (value: number | null, unit = "SAR m"): Fig => ({ value, unit, source: { domain: "deal_desk", relation: "dd_deal", key: { proposal_id: "R12-TWA" } } });

test("numbers read the house way", () => {
  assert.equal(pct(0.1452), "14.5%");
  assert.equal(pct(null), "–");
  assert.equal(sarm(170), "SAR 170.0m");
  assert.equal(sarm(4.5), "SAR 4.50m");
  assert.equal(sarm(1250), "SAR 1.25bn");
  assert.equal(delta(f(-0.083, "share")), "−8.3 pp");
  assert.equal(delta(f(-17)), "−17.0m");
  assert.equal(delta(f(0.259)), "+0.26m");
  assert.equal(delta(null), "–");
});

test("source line names the engine and the Data Domains row", () => {
  assert.equal(sourceLine({ domain: "deal_desk", relation: "dd_condition", key: { condition_id: "CO-TWA-1" }, column: "status" }),
               "deal_desk · dd_condition · condition_id=CO-TWA-1 · status");
  assert.equal(sourceLine({ domain: "deal_desk", relation: "dd_deal", key: { proposal_id: "R12-TWA" }, engine: "engine.analyse" }),
               "engine.analyse on deal_desk · dd_deal · proposal_id=R12-TWA");
});

test("tones", () => {
  assert.equal(statusTone("not explained"), "negative");
  assert.equal(statusTone("partly explained"), "warning");
  assert.equal(statusTone("explained"), "positive");
  assert.equal(decisionTone("approve"), "positive");
  assert.equal(decisionTone("counter-offer"), "warning");
  assert.equal(failureTone("limit"), "negative");
  assert.equal(failureTone("hurdle"), "warning");
});

test("question summary and pair counts", () => {
  const q = (avoided: boolean) => ({ id: "x", rank: 1, source: "s", score: 1, question: "?", answer: "a", evidence: [], avoided, avoided_reason: "", asks_for: "" });
  assert.deepEqual(questionSummary({ questions: [q(true), q(false), q(true)] }), { total: 3, avoided: 2, line: "3 questions, 2 not answered in the proposal" });
  const p = (status: Pair["status"]): Pair => ({ better: "a", worse: "b", status, text: "", similarity: 0.6, rms: [], decided_by: [] });
  assert.deepEqual(pairCounts([p("explained"), p("not explained"), p("not explained")]), { "explained": 1, "partly explained": 0, "not explained": 2 });
});

test("security items: most SVA per SAR tied up first, uncosted items last", () => {
  const d = { lgd_y1: f(0), el_lifetime_pv: f(0), rwa_y1: f(0), capital_y1: f(0), lifetime_raroc: f(0), sva: f(0.1) };
  const it = (id: string, eff: number | null, sva = 0.1): SecurityItem => ({ id, kind: "collateral", type: "t", label: id, in_ask: false, value: null,
    recovery_value: null, standalone: { ...d, sva: f(sva) }, cost_sar_mn: f(1), crm: { eligible: false, basis: "" }, clears_alone: false,
    sva_per_sar_tied: eff === null ? null : f(eff) });
  assert.deepEqual(rankItems([it("a", 0.01), it("b", null, 5), it("c", 0.05)]).map((x) => x.id), ["c", "a", "b"]);
});
