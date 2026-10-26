import { test } from "node:test";
import assert from "node:assert/strict";

import { canBuild, counts, includeIds, initialSelection, isPlan, mentionsPersona, toggle, type MetricPlan, type PlanMetric } from "./lenses-plan.ts";

const m = (id: string, kind: "kpi" | "tile", available = true): PlanMetric => ({
  id, kind, label: id, definition: "d", formula: "f", sql: available ? "SELECT 1" : "", relation: "corp", sources: [], tile_type: kind,
  chart: "bar", available, reason: available ? "" : "not available: no RWA or CET1 column", include: available,
});
const plan: MetricPlan = {
  persona: "cro", persona_label: "Chief Risk Officer (CRO)", short: "CRO", book: "corporate", scope_label: "Corporate book", period: "2026Q2",
  title: "CRO dashboard", request: "CRO dashboard", plain_words: ["a", "b", "c"], relation_note: "",
  metrics: [m("kpi:ead", "kpi"), m("appetite_utilisation", "tile"), m("stage_migration", "tile"), m("capital", "tile", false)],
};

test("persona words are found as words, plain requests are not", () => {
  for (const t of ["CRO dashboard", "dashboard for an analyst", "risk analyst view", "Chief Credit Officer pack", "branch head view"]) assert.ok(mentionsPersona(t), t);
  for (const t of ["Construction sector dashboard", "Stage 2 migration by RM", "micro enterprises", "Makkah retail cards"]) assert.ok(!mentionsPersona(t), t);
});

test("the plan card starts with every available measure and never ticks an unavailable one", () => {
  assert.ok(isPlan(plan) && !isPlan({ persona: null }));
  let sel = initialSelection(plan);
  assert.deepEqual(includeIds(plan, sel), ["kpi:ead", "appetite_utilisation", "stage_migration"]);
  sel = toggle(plan, sel, "capital");
  assert.ok(!sel.has("capital"));
  sel = toggle(plan, sel, "stage_migration");
  assert.deepEqual(includeIds(plan, sel), ["kpi:ead", "appetite_utilisation"]);
  assert.deepEqual(counts(plan, sel), { tiles: 1, kpis: 1, unavailable: 1 });
  assert.ok(canBuild(plan, sel));
  sel = toggle(plan, sel, "appetite_utilisation");
  assert.ok(!canBuild(plan, sel), "key figures alone are not a dashboard");
});
