import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type ReviewRow, acceptable, approvePreview, changeTone, countBy, decisionBody, fileName, groupRows, parseValue, provenanceLine,
  shortDate, sourceChip, statusWord, valueText,
} from "./dealdesk-params.ts";

const found = (over: Partial<ReviewRow> = {}): ReviewRow => ({
  id: "risk_appetite.dscr", group: "Risk appetite", table: "risk_appetite", key: "dscr", field: "limit", label: "DSCR after the deal", unit: "x",
  display: "1.20x", version: "v1", effective_from: "2026-10-01", owner: "CFO", status: "found", change: "tighter", decision: "accept",
  options: ["accept", "edit", "keep"],
  proposals: [{ item_id: "ONB-1", field: "limit", subfield: "", proposed: 1.25, in_force: 1.2, display: "1.25x", in_force_display: "1.20x",
                change: "tighter", conversion: "", clause: "4.2", quote: "not less than 1.25x", label: "DSCR" }],
  ...over,
});
const missing = (over: Partial<ReviewRow> = {}): ReviewRow => found({
  id: "uae_desk.cost_of_equity", table: "uae_desk", key: "cost_of_equity", unit: "rate", status: "not_found", change: "", decision: "keep",
  options: ["keep", "define"], proposals: [], label: "Cost of equity", ...over });
const fresh = (over: Partial<ReviewRow> = {}): ReviewRow => found({
  id: "new.ONB-9", table: "policy_params", key: "bureau_days", status: "new", change: "new", decision: "skip",
  options: ["skip", "add_parameter", "add_rule"], proposals: [], ...over });

test("provenance reads as the (i) says it", () => {
  const p = { kind: "policy" as const, text: "", policy: "Corporate Credit Policy", policy_version: 2, clause: "4.2", quote: "not less than 1.25x" };
  assert.equal(provenanceLine(p), "Set by Corporate Credit Policy v2, clause 4.2: ‘not less than 1.25x’");
  assert.deepEqual(sourceChip(p), { label: "Policy v2 · 4.2", tone: "accent" });
  const m = { kind: "manual" as const, text: "", owner: "CFO", date: "2026-10-01" };
  assert.equal(provenanceLine(m), "Set manually by CFO on 2026-10-01");
  assert.deepEqual(sourceChip(m), { label: "Manual", tone: "neutral" });
  assert.equal(provenanceLine({ kind: "manual", text: "Set manually by Finance on 2026-10-01" }), "Set manually by Finance on 2026-10-01");
});

test("values are typed the way they read", () => {
  assert.deepEqual(parseValue("1.30x", "x"), { value: 1.3 });
  assert.deepEqual(parseValue("13", "rate"), { value: 0.13 });
  assert.deepEqual(parseValue("65%", "share"), { value: 0.65 });
  assert.ok(parseValue("165", "share").error);
  assert.ok(parseValue("abc", "x").error);
  assert.ok(parseValue("", "x").error);
  assert.deepEqual(parseValue("SAR 250m", "sar m"), { value: 250 });
  assert.deepEqual(parseValue("BB-", "rating"), { value: "BB-" });
  assert.deepEqual(parseValue("Corporate Banking: 15\nSME: 18", "rate_map", { "Corporate Banking": 0.15, SME: 0.2 }), { value: { "Corporate Banking": 0.15, SME: 0.18 } });
  assert.deepEqual(parseValue("Construction: Selective", "text_map", { Construction: "Grow" }), { value: { Construction: "Selective" } });
  assert.equal(valueText({ a: 0.15, b: 0.2 }, "rate_map"), "a: 15\nb: 20");
  assert.equal(valueText(1.2, "x"), "1.2");
  assert.equal(valueText(0.125, "rate"), "12.5");
});

test("a found sub-value is one number; a map to define takes the shape in force", () => {
  const sub = found({ id: "uae_desk.tenor_cap_years", unit: "number_map", options: ["accept", "edit", "keep"],
    proposals: [{ ...found().proposals[0], subfield: "Working capital", proposed: 1, display: "1 year" }] });
  assert.deepEqual(decisionBody([sub], { "uae_desk.tenor_cap_years": { action: "edit", text: "2" } }).decisions,
                   { "uae_desk.tenor_cap_years": { action: "edit", value: 2 } });
  const map = missing({ id: "returns.hurdle", unit: "rate_map", value: { "Corporate Banking": 0.15, SME: 0.18 } });
  assert.deepEqual(decisionBody([map], { "returns.hurdle": { action: "define", text: "SME: 20" } }).decisions,
                   { "returns.hurdle": { action: "define", value: { SME: 0.2 } } });
  assert.ok(decisionBody([map], { "returns.hurdle": { action: "define", text: "20" } }).errors["returns.hurdle"]);
});

test("the approve body carries only changed choices, with parsed values; errors are per row", () => {
  const rows = [found(), missing(), fresh()];
  const { decisions, errors } = decisionBody(rows, {
    "risk_appetite.dscr": { action: "edit", text: "1.3" }, "uae_desk.cost_of_equity": { action: "define", text: "13" },
    "new.ONB-9": { action: "add_rule" },
  });
  assert.deepEqual(errors, {});
  assert.deepEqual(decisions, { "risk_appetite.dscr": { action: "edit", value: 1.3 }, "uae_desk.cost_of_equity": { action: "define", value: 0.13 },
                                "new.ONB-9": { action: "add_rule" } });
  assert.deepEqual(decisionBody(rows, { "risk_appetite.dscr": { action: "accept" } }).decisions, {}); // the default is not sent
  const bad = decisionBody(rows, { "uae_desk.cost_of_equity": { action: "define", text: "" }, "risk_appetite.dscr": { action: "define" } });
  assert.deepEqual(Object.keys(bad.errors).sort(), ["risk_appetite.dscr", "uae_desk.cost_of_equity"]);
});

test("the preview says what approve will do and that reject changes nothing", () => {
  const rows = [found(), found({ id: "risk_appetite.raroc_floor", change: "same" }), missing(), fresh()];
  assert.equal(approvePreview(rows, {}), "Approving writes 1 value from the policy as a new version of 1 table. Reject changes nothing.");
  assert.equal(approvePreview(rows, { "risk_appetite.dscr": { action: "keep" } }),
               "Approving records the policy as active; no parameter value changes.");
  assert.match(approvePreview(rows, { "uae_desk.cost_of_equity": { action: "define", text: "13" }, "new.ONB-9": { action: "add_parameter" } }),
               /1 value from the policy, 1 defined now, 1 new item added as a new version of 3 tables/);
});

test("counts, groups, tones and words", () => {
  assert.deepEqual(countBy([found(), missing(), missing(), fresh()]), { found: 1, new: 1, not_found: 2 });
  const g = groupRows([{ group: "B" }, { group: "A" }, { group: "B" }], ["A", "B", "C"]);
  assert.deepEqual(g.map((x) => [x.group, x.rows.length]), [["A", 1], ["B", 2]]);
  assert.equal(changeTone("looser"), "negative");
  assert.equal(changeTone("tighter"), "positive");
  assert.equal(statusWord("pending"), "Awaiting approval");
  assert.equal(statusWord("trial"), "Trial only");
  assert.equal(shortDate("2026-07-01T10:00:00Z"), "1 Jul 2026");
  assert.equal(fileName("attachment; filename*=UTF-8''Deal%20Desk%20parameters.xlsx"), "Deal Desk parameters.xlsx");
  assert.equal(fileName('attachment; filename="a.docx"'), "a.docx");
  assert.ok(acceptable("Policy.PDF") && !acceptable("policy.xlsx"));
});
