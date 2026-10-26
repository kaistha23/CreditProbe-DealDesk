import { test } from "node:test";
import assert from "node:assert/strict";

import { type Check, type Condition, bySeverity, countsLine, markCounts, money, nOfN, pp, pct, sortConditions } from "./dealdesk-review.ts";

const chk = (rule_id: string, severity: Check["severity"], verdict: Check["verdict"]): Check => ({
  check_id: rule_id, rule_id, category: "data", title: rule_id, tests: "", verdict, severity, value: null, threshold: null, unit: "",
  finding: "", evidence: [], policy_ref: "", crm_article: "", doa: null, claim_ids: [], line_ids: [],
});

test("findings group by severity, contradicted first", () => {
  const g = bySeverity([chk("B", "major", "exception"), chk("A", "critical", "exception"), chk("C", "major", "contradicted"), chk("D", "critical", "contradicted")]);
  assert.deepEqual(g.map((x) => x.severity), ["critical", "major"]);
  assert.deepEqual(g[0].items.map((x) => x.rule_id), ["D", "A"]);
  assert.deepEqual(g[1].items.map((x) => x.rule_id), ["C", "B"]);
});

test("counts line drops zeros", () => {
  assert.equal(countsLine({ critical: 3, major: 5, minor: 0 }), "3 critical · 5 major");
  assert.equal(countsLine({ critical: 0, major: 0, minor: 0 }), "No findings");
});

test("memo marks are counted", () => {
  const m = markCounts([{ title: "s", line_id: "L1", lines: [
    { line_id: "L2", kind: "text", text: "", mark: "contradicted", check_ids: [], claim_ids: [], evidence: [] },
    { line_id: "L3", kind: "row", text: "", mark: "supported", check_ids: [], claim_ids: [], evidence: [] },
    { line_id: "L4", kind: "row", text: "", mark: null, check_ids: [], claim_ids: [], evidence: [] }] }]);
  assert.equal(m.contradicted, 1);
  assert.equal(m.supported, 1);
  assert.equal(m.exception, 0);
});

test("conditions sort by urgency then due date", () => {
  const c = (id: string, status: Condition["status"], due: string | null): Condition => ({
    id, deal_id: "D", deal_name: "", rule_id: "", kind: "CP", what: id, source: "", due_date: due, due_text: "", owner: "", origin: "", note: "",
    status, evaluation: "manual", data_value: null });
  const s = sortConditions([c("a", "met", "2026-01-01"), c("b", "due", "2026-11-30"), c("c", "overdue", null), c("d", "due", "2026-10-31")]);
  assert.deepEqual(s.map((x) => x.id), ["c", "d", "b", "a"]);
});

test("number words", () => {
  assert.equal(money(656.8, "AED"), "AED 656.8m");
  assert.equal(money(1570, "AED"), "AED 1.57bn");
  assert.equal(money(0.45, "SAR"), "SAR 0.45m");
  assert.equal(money(null, "SAR"), "–");
  assert.equal(pct(0.1605), "16.1%");
  assert.equal(pp(0.024), "+2.4pp");
  assert.equal(pp(-0.01), "−1.0pp");
  assert.equal(nOfN(75, 118), "75 of 118 (64%)");
});
