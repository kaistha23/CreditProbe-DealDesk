// PLAN_R9 G4: the Workspace Intelligence Briefing (pure part).
import assert from "node:assert/strict";
import { test } from "node:test";

import { type BookSnapshot, eclMovementFigure, findings, kpis, money, share, stageFromRows, stageMixFigure, sectorFigure } from "./briefing.ts";

const stage = stageFromRows([{ value: 1, n: 80, ead_sar_mn: 8000, ecl_sar_mn: 40 }, { value: 2, n: 15, ead_sar_mn: 1500, ecl_sar_mn: 60 },
                             { value: 3, n: 5, ead_sar_mn: 500, ecl_sar_mn: 250 }]);
const snap: BookSnapshot = {
  book: "corporate", period: "2026-09", priorPeriod: "2026-08", moneyUnit: "SAR mn", exposure: 10000, ecl: 350, prevEcl: 320,
  critical: 12, high: 30, warnedExposure: 1800, topReason: { name: "Cheque returns", customers: 9, change: 3 },
  stage, segments: [{ label: "Real estate", exposure: 3000, ecl: 120, eclChange: 20, severe: 300 },
                    { label: "Trade", exposure: 2000, ecl: 80, eclChange: 5, severe: 100 }],
  trend: [{ period: "2026-08", stage, critical: 10, high: 28, moderate: 50, low: 100, ecl: 320, exposure: 9800 },
          { period: "2026-09", stage, critical: 12, high: 30, moderate: 48, low: 99, ecl: 350, exposure: 10000 }],
  crm: { breaches: 7, high: 2, checksInBreach: 3, topArticle: "Art. 4", topTitle: "Large exposures", shortfall: 12.5 },
};

test("house money format and shares", () => {
  assert.equal(money(10000), "SAR 10.00bn");
  assert.equal(money(350), "SAR 350.0m");
  assert.equal(share(2000, 10000), "20.0%");
});

test("stage rows accept both service shapes", () => {
  assert.equal(stage[2].ead, 1500);
  assert.equal(stageFromRows([{ stage: 3, n: 1, ead: 5, ecl: 2 }])[3].ecl, 2);
});

test("KPI band: four figures (R10 G-TILES), no raw decimals", () => {
  const k = kpis(snap);
  assert.equal(k.length, 4);
  assert.deepEqual(k.map((x) => x.key), ["exposure", "ecl", "stage23", "ews"]);
  assert.equal(k.find((x) => x.key === "ews")?.sub, "18.0% of exposure");
  assert.equal(k.find((x) => x.key === "stage23")?.value, "20.0%");
  for (const x of k) assert.ok(!/\d\.\d{3,}/.test(x.value), x.value);
});

test("findings: 5 to 7, each with a pack, rule, figure and link", () => {
  const f = findings(snap);
  assert.ok(f.length >= 5 && f.length <= 7, String(f.length));
  for (const x of f) { assert.match(x.pack, /^P[1-7]$/); assert.ok(x.rule ? x.rule.startsWith(x.pack) : Boolean(x.article)); assert.ok(x.href.startsWith("/")); }
});

test("ECL waterfall ends at the booked ECL and reconciles", () => {
  const fig = eclMovementFigure(snap);
  const y = fig.data[0].y as number[];
  assert.equal(y[0], 320); assert.equal(y[y.length - 1], 350);
  assert.equal(Math.round(y.slice(1, -1).reduce((a, b) => a + b, 0)), 30);
});

test("stage mix adds to 100% and sector chart lists segments", () => {
  const f = stageMixFigure(snap);
  const total = f.data.reduce((n, d) => n + (d.y as number[])[0], 0);
  assert.equal(Math.round(total), 100);
  assert.equal((sectorFigure(snap).data[0].y as string[]).length, 2);
});

test("Accepted Risk Watch: no tile and no separate screen (R10); its finding opens Early Warning", () => {
  assert.ok(!kpis(snap).some((k) => k.key === "watch"));
  const w = { ...snap, watch: { names: 12, escalations: 3, missed: 5, due: 2, top: [] } };
  assert.ok(findings(w).some((f) => f.id === "watch" && f.pack === "P4" && f.href === "/early-warning"));
  assert.ok(findings(w).every((f) => !f.href.startsWith("/accepted-risk")));
  assert.ok(findings(w).length <= 7);
});
