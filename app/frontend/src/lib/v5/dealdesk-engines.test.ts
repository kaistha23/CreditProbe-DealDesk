import { test } from "node:test";
import assert from "node:assert/strict";

import { type Bridge, type EngineFinding, bridgeLine, capacitySub, groupFindings, pct1, sarMn } from "./dealdesk-engines.ts";

const f = (id: string, severity: EngineFinding["severity"], category: string, status = "open"): EngineFinding => ({
  id, source: "review", source_relation: "dd_review_finding", code: id, category, category_label: category, severity, verdict: null,
  title: id, text: "", evidence: [], policy_ref: "", status, cure: { kind: "cp", kind_label: "CP", text: "", owner: "RM", when: "" }, curable: true,
});

test("findings group by severity critical → info, open only, by category", () => {
  const fs = [f("a", "major", "documents"), f("b", "critical", "capacity"), f("c", "info", "financial_quality"), f("d", "critical", "pricing", "resolved")];
  const g = groupFindings(fs);
  assert.deepEqual(g.map((x) => x.severity), ["critical", "major", "info"]);
  assert.deepEqual(g[0].items.map((x) => x.id), ["b"]);
  assert.deepEqual(groupFindings(fs, "documents").map((x) => x.items.map((i) => i.id)), [["a"]]);
});

test("capacity sub-line states the multiple of capacity", () => {
  assert.equal(capacitySub({ ask_sar_mn: 170, capacity_sar_mn: 96.8, within: false }), "ask SAR 170.0m · 1.76× capacity");
  assert.equal(capacitySub({ ask_sar_mn: 60, capacity_sar_mn: 90, within: true }), "ask SAR 60.0m · within capacity");
  assert.equal(capacitySub({ ask_sar_mn: 223, capacity_sar_mn: 0, within: false }), "ask SAR 223.0m · no capacity");
});

test("bridge line deal → relationship → deposits", () => {
  const b: Bridge = { steps: [
    { step: "Deal", raroc: 0.145, delta_pp: null, pv_sar_mn: 1.5, what: "" },
    { step: "+ ancillary income (relationship)", raroc: 0.203, delta_pp: 5.8, pv_sar_mn: 0.6, what: "" },
    { step: "+ deposits", raroc: 0.335, delta_pp: 13.2, pv_sar_mn: 1.4, what: "" }], pv_capital_sar_mn: 10, hurdle: 0.15, basis: "lifetime", headline: "", source: "" };
  assert.equal(bridgeLine(b), "Deal 14.5% → +5.8 pp ancillary income (relationship) → +13.2 pp deposits");
});

test("formatters", () => {
  assert.equal(sarMn(96.84), "SAR 96.8m");
  assert.equal(sarMn(null), "–");
  assert.equal(pct1(0.1452), "14.5%");
});
