import assert from "node:assert/strict";
import { test } from "node:test";

import { BAND_COLOUR, STAGE_COLOUR, bandsFigure, gradeFigure, inGlobalOrder, reasonsFigure, splitFigure, stageFigure, wrap } from "./whatif-summary.ts";
import type { PopulationSummary } from "./whatif.ts";

const labels = {
  book: "Corporate", segment: "Sector", segments: "Sectors", subsegment: "Sub-sector", owner: "Borrower", owners: "Borrowers",
  exposure: "Facility", exposures: "Facilities", grade: "Rating", grade_notch: "notch", period: "Quarter", frequency: "quarterly",
};

const s = {
  kind: "cohort", domain: "corporate", period: "2026Q2", labels, title: "Construction · warned", scope_label: "Early Warning cohort",
  cards: { owners: 348, exposures: 1456, ead: 10872.8629, ecl: 1200.5, coverage_pct: 11.04, stage2_ead_pct: 50.1, stage3_ead_pct: 20.2,
           stage2_n: 700, stage3_n: 300, ews_avg_score: 7.4, ews_warned_owners: 348, ews_warned_ead: 10872.8629, ews_warned_pct: 100 },
  stages: [{ stage: 1, label: "Stage 1", n: 456, owners: 100, ead: 3240.1, ecl: 20.1, ead_pct: 29.8 },
           { stage: 2, label: "Stage 2", n: 700, owners: 200, ead: 5447.3, ecl: 300.2, ead_pct: 50.1 },
           { stage: 3, label: "Stage 3", n: 300, owners: 48, ead: 2185.4629, ecl: 880.2, ead_pct: 20.1 }],
  grades: { label: "Rating", order: ["A-", "BBB", "BB+", "B", "CCC", "C"],
            rows: ["A-", "BBB", "BB+", "B", "CCC", "C"].map((g, i) => ({ grade: g, n: 10 + i, owners: 5, ead: 100 * (i + 1), ecl: 1, ead_pct: 5 })) },
  split: { label: "Sector", plural: "Sectors", rows: [{ name: "Construction", n: 1456, owners: 348, ead: 10872.8629, ecl: 1200.5, ead_pct: 100, coverage_pct: 11.04 }] },
  bands: [{ band: "critical", label: "Critical", owners: 40, exposures: 200, ead: 2000, ecl: 500 },
          { band: "high", label: "High", owners: 100, exposures: 400, ead: 3000, ecl: 400 },
          { band: "moderate", label: "Moderate", owners: 208, exposures: 856, ead: 5872.8629, ecl: 300.5 }],
  reasons: [{ reason: "SICR flag raised", owners: 300, exposures: 900, ead: 8000 },
            { reason: "Past due at another lender (external DPD > 59)", owners: 120, exposures: 300, ead: 2500 }],
  top: { n: 20, rows: [] },
} as unknown as PopulationSummary;

test("stage donut: EAD by stage, status colours, formatted hover", () => {
  const f = stageFigure(s);
  const d = f.data[0] as Record<string, unknown>;
  assert.equal(d.type, "pie");
  assert.deepEqual(d.values, [3240.1, 5447.3, 2185.4629]);
  assert.deepEqual((d.marker as { colors: string[] }).colors, [STAGE_COLOUR[1], STAGE_COLOUR[2], STAGE_COLOUR[3]]);
  assert.deepEqual((d.customdata as string[][])[1], ["SAR 5.45bn", "700", "SAR 300m", "50.1%"]);
  assert.match(String(d.hovertemplate), /facilities/);
});

test("ratings: the API's global order is kept on the axis", () => {
  const f = gradeFigure(s);
  assert.deepEqual((f.data[0] as { x: string[] }).x, s.grades.order);
  assert.deepEqual((f.layout.xaxis as { categoryarray: string[] }).categoryarray, s.grades.order);
  assert.equal((f.layout.xaxis as { title: { text: string } }).title.text, "Rating");
  assert.ok(inGlobalOrder(s.grades.order));
  assert.ok(!inGlobalOrder(["BBB", "A-"]));
  assert.ok(!inGlobalOrder(["A", "A"]));
  assert.ok(!inGlobalOrder(["A", "E"]));        // E is not a rating
});

test("split, reasons and bands", () => {
  const sp = splitFigure(s);
  assert.deepEqual((sp.data[0] as { y: string[] }).y, ["Construction"]);
  const r = reasonsFigure(s);
  assert.equal(r.data.length, 2);
  assert.deepEqual((r.data[0] as { x: number[] }).x, [120, 300]);          // largest at the top of the panel
  assert.deepEqual((r.data[1] as { x: number[] }).x, [2500, 8000]);
  assert.equal((r.data[1] as { xaxis: string }).xaxis, "x2");
  assert.ok(!("yaxis2" in r.layout));                                     // two panels, one shared category axis
  const b = bandsFigure(s);
  assert.deepEqual((b.data[0] as { x: string[] }).x, ["Critical", "High", "Moderate"]);
  assert.deepEqual((b.data[0] as { marker: { color: string[] } }).marker.color, [BAND_COLOUR.critical, BAND_COLOUR.high, BAND_COLOUR.moderate]);
  for (const fig of [stageFigure(s), gradeFigure(s), sp, r, b]) {
    const text = JSON.stringify(fig).toLowerCase();
    for (const raw of ["ecl_final", "owner_id", "ews_band", "ead_sar_mn", "synthetic", "demo"]) assert.ok(!text.includes(raw), raw);
  }
});

test("wrap keeps words and breaks long reasons", () => {
  assert.equal(wrap("SICR flag raised"), "SICR flag raised");
  const w = wrap("Past due at another lender (external DPD > 59)", 20);
  assert.ok(w.includes("<br>"));
  assert.equal(w.replaceAll("<br>", " "), "Past due at another lender (external DPD > 59)");
});
