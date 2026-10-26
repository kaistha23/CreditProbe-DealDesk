import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type Item, type Session, allItems, changeTone, countFor, editable, filterItems, fmtValue, headlineText, paramLine, parseEdit,
  sourceOf, statusOf,
} from "./dealdesk-onboard.ts";

const item = (over: Partial<Item> = {}): Item => ({
  id: "ONB-1", type: "threshold", metric: "dscr", label: "DSCR after the deal", clause: "4.2", quote: "DSCR not less than 1.25x.",
  value: 1.25, unit: "x", checkability: "auto", status: "proposed",
  param: { table: "risk_appetite", row: "dscr", field: "limit", proposed: 1.25, in_force: 1.2, change: "tighter" },
  rule: { id: "POL-DSCR-4-2", finding: "" }, learned_from: { document: "Policy.docx", clause: "4.2" }, ...over,
});

const session = (): Session => ({
  session_id: "ONS-1", created_at: "", maker: "m", bank: "B", documents: [],
  items: [item(), item({ id: "ONB-2", metric: "review_months", value: 18, unit: "months", param: undefined, rule: undefined,
    checkability: "manual", conflict: { regulation: "CBUAE CRM Art. 4.3", message: "weaker" } })],
  committee: [item({ id: "CQ-a", type: "committee_question", value: undefined, param: undefined, rule: undefined, question: "Q?",
    learned_from: { documents: ["M1", "M2"] } })],
  structure: [], language: [], conflicts: [], consistent: [], gaps: { data: [], sections: [] },
  decisions: { "ONB-1": { item_id: "ONB-1", action: "accept", by: "c", at: "" } }, versions: ["onb-1"],
  summary: { thresholds: 2, conditions: 0, rules: 1, params: 1, auto: 1, manual: 1, conflicts: 1, data_gaps: 1, section_gaps: 0, committee: 1,
    items: 3, accepted: 1, rejected: 0, pending: 2, text: "Learned …" },
  timings: { learn_s: 1 },
});

test("filters split the learned items", () => {
  const s = session();
  assert.equal(allItems(s).length, 3);
  assert.deepEqual(filterItems(s, "rules").map((i) => i.id), ["ONB-1"]);
  assert.deepEqual(filterItems(s, "conflicts").map((i) => i.id), ["ONB-2"]);
  assert.deepEqual(filterItems(s, "committee").map((i) => i.id), ["CQ-a"]);
  assert.equal(countFor(s, "pending"), 2);
  assert.equal(statusOf(s, "ONB-1"), "accepted");
  assert.equal(statusOf(s, "ONB-2"), "proposed");
});

test("values read as the policy states them", () => {
  assert.equal(fmtValue(1.25, "x"), "1.25x");
  assert.equal(fmtValue(40, "%"), "40%");
  assert.equal(fmtValue(300, "AED m"), "AED 300m");
  assert.equal(fmtValue(18, "months"), "18 months");
  assert.equal(fmtValue("B-", "rating"), "B-");
  assert.equal(fmtValue(null), "condition");
  assert.equal(fmtValue({ IG: 10, BB: 7 }, "years"), "IG 10 · BB 7");
  assert.equal(fmtValue({ IG: [100, 250] }, "bps"), "IG 100–250");
  assert.equal(fmtValue([{ level: "CRO", max_exposure_policy: 200, min_rating: "B-" }, { level: "Board", max_exposure_policy: null }]), "CRO 200 (B-) · Board above");
});

test("parameter line and tone", () => {
  assert.equal(paramLine(item().param!), "1.2 → 1.25 (tighter)");
  assert.equal(changeTone("tighter"), "positive");
  assert.equal(changeTone("looser"), "negative");
  assert.equal(changeTone("same"), "neutral");
});

test("edits parse numbers and committee questions only", () => {
  assert.equal(parseEdit(item(), "1.30x"), 1.3);
  assert.throws(() => parseEdit(item(), "abc"));
  assert.equal(parseEdit(item({ type: "committee_question", value: undefined }), " Is it so? "), "Is it so?");
  assert.equal(editable(item({ value: "B-" })), false);
  assert.equal(editable(item()), true);
});

test("source and headline", () => {
  assert.equal(sourceOf(item()), "Policy.docx, clause 4.2");
  assert.equal(sourceOf(item({ learned_from: { documents: ["a", "b"] } })), "2 memos");
  assert.equal(headlineText({ headline: "Do not approve" }), "Do not approve");
  assert.equal(headlineText("x"), "x");
  assert.equal(headlineText(null), "");
});
