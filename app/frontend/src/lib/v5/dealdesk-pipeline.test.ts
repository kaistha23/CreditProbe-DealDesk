import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type Decision, type LimitRow, type PipelineResult, type PipelineTest,
  allPending, bullet, canTest, limitValue, panelRows, parseBudget, resultTiles, sortDecisions, statusCounts, testLine, toggle, worsened,
} from "./dealdesk-pipeline.ts";

const row = (o: Partial<LimitRow>): LimitRow => ({
  name: "x", label: "X", scope: "book", kind: "soft", unit: "share", direction: "max", appetite: 0.1, trigger: 0.12, limit: 0.15,
  before: 0.11, after: 0.13, status_before: "green", status: "amber", above_appetite: true, headroom: 0.02, basis: "RAS", definition: "", r11: true,
  ...o,
});

test("limit values read in their own unit", () => {
  assert.equal(limitValue(0.2267, "share"), "22.7%");
  assert.equal(limitValue(0.0097, "share"), "0.97%");
  assert.equal(limitValue(0.0771, "index"), "0.077");
  assert.equal(limitValue(50.14, "bps"), "50.1 bps");
  assert.equal(limitValue(1.2, "x"), "1.20x");
  assert.equal(limitValue(1, "deals"), "1 deal");
  assert.equal(limitValue(null, "share"), "–");
  assert.equal(limitValue("B-", "rating"), "B-");
});

test("bullet geometry keeps every marker on the bar, in order", () => {
  const g = bullet(row({}))!;
  assert.ok(g.max > 0.15);
  for (const v of [g.before, g.after, g.appetite, g.trigger, g.limit]) assert.ok(v !== null && v >= 0 && v <= 1);
  assert.ok(g.appetite! < g.trigger! && g.trigger! < g.limit!);
  assert.equal(bullet(row({ limit: null })), null);
  assert.equal(bullet(row({ limit: { IG: 10 } as unknown as number })), null);
});

test("panel rows: numeric limits only, red then amber then green", () => {
  const rows = [row({ name: "a", status: "green" }), row({ name: "b", status: "red" }), row({ name: "c", direction: "deal", status: "green" }),
    row({ name: "d", status: "amber" })];
  assert.deepEqual(panelRows(rows).map((r) => r.name), ["b", "d", "a"]);
  assert.deepEqual(statusCounts(rows), { green: 2, amber: 1, red: 1 });
  assert.deepEqual(worsened(rows).map((r) => r.name), ["b", "d"]);
});

const dec = (id: string, decision: "approve" | "decline", sva: number): Decision => ({
  proposal_id: id, decision, reason: "r", sva_per_100m_rwa: null,
  option: decision === "approve" ? { sva } as Decision["option"] : null,
  options: [{ sva, available: true } as Decision["options"][number]],
} as Decision);

test("decisions: approvals first by SVA, then declines by their best option", () => {
  const out = sortDecisions([dec("A", "decline", 1), dec("B", "approve", 0.5), dec("C", "approve", 2), dec("D", "decline", 3)]);
  assert.deepEqual(out.map((d) => d.proposal_id), ["C", "B", "D", "A"]);
});

test("result tiles: at most four, with n of N and the budget share", () => {
  const r = {
    headline: "h", decisions: [], binding: [], frontier: [], soft_breaches: [], basis: "",
    limits: [row({ status: "red" }), row({ status: "green" })],
    summary: { deals: 40, selected: 14, sva: 25.3, penalty: 0, objective: 25.3, rwa_used: 1750, rwa_budget: 2500, el_used: 3, el_budget: 60,
               ead_new: 1800, ead_pipeline: 3600, raroc_new: 0.19, amount_selected: 1900, amount_pipeline: 3800 },
  } as unknown as PipelineResult;
  const t = resultTiles(r);
  assert.equal(t.length, 4);
  assert.equal(t[0].value, "14 of 40");
  assert.equal(t[2].sub, "70.0% of SAR 2.50bn budget");
  assert.equal(t[3].value, "1 red");
});

test("selection, budgets and the button contract", () => {
  const s = allPending([{ proposal_id: "A" }, { proposal_id: "B" }] as never);
  assert.equal(s.size, 2);
  assert.equal(toggle(s, "A").size, 1);
  assert.equal(toggle(toggle(s, "A"), "A").size, 2);
  assert.equal(parseBudget("2,500"), 2500);
  assert.equal(parseBudget(" 60 "), 60);
  assert.equal(parseBudget(""), null);
  assert.equal(parseBudget("-5"), null);
  assert.equal(parseBudget("abc"), null);
  assert.equal(canTest(false, false), false);
  assert.equal(canTest(true, true), false);
  assert.equal(canTest(true, false), true);
});

test("the pipeline-test line names the verdict and the first binding limit", () => {
  const t = { verdict: "Makes the cut: ranks 3 of 20", binds_first: { text: "Real estate and construction (book) binds first: headroom for 2.1x this deal" } } as PipelineTest;
  assert.equal(testLine(t), "Makes the cut: ranks 3 of 20. Real estate and construction (book) binds first: headroom for 2.1x this deal.");
  assert.equal(testLine({ verdict: "Does not fit.", binds_first: null } as PipelineTest), "Does not fit.");
});
