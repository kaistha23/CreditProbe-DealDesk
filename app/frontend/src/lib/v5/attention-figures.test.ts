import assert from "node:assert/strict";
import { test } from "node:test";

import { contributorsFigure, fmt, fmtChange, itemText, peersFigure, stageFigure, trendFigure, type ChartsPayload } from "./attention-figures.ts";

const base: ChartsPayload = {
  domain: "corporate", family: "sector_ecl", segment: "Construction", dimension: "sector", dimension_label: "Sector",
  measure: "ecl", measure_label: "Recognised ECL", kind: "amount", unit: "SAR million", period: "2026Q2",
  comparison_period: "2026Q1", period_noun: "quarter",
  trend: { periods: ["2025Q4", "2026Q1", "2026Q2"], segment: [1500, 1789.7, 2755.1], book: [6000, 6500, 7800], current_index: 2 },
  peers: { period: "2026Q2", items: [{ segment: "Construction", value: 2755.1, rows: 10, is_segment: true }, { segment: "Energy", value: 900, rows: 5, is_segment: false }], book: 7800, book_label: "Book total" },
  contributors: { before: "2026Q1", after: "2026Q2", views: [{ key: "sub_sector", label: "Sub-sector", from: 1789.7, to: 2755.1, total_change: 965.4,
    items: [{ name: "Building", id: "Building", from: 436, to: 971.7, change: 535.7 }, { name: "Other", id: "x", from: 1353.7, to: 1783.4, change: 429.7 }] }] },
  stage_mix: { periods: ["2026Q1", "2026Q2"], stages: [1, 2, 3], ead: [[4852, 10438, 2863], [3892, 10166, 4637]], unit: "SAR million", basis: "Exposure at default of the segment" },
  source: "x",
};

test("formatting", () => {
  assert.equal(fmt(2755.117, "amount"), "SAR 2,755m");
  assert.equal(fmt(45.14, "amount"), "SAR 45.1m");
  assert.equal(fmt(12.7587, "share"), "12.76%");
  assert.equal(fmt(null, "share"), "—");
  assert.equal(fmtChange(965.4, "amount"), "+SAR 965m");
  assert.equal(fmtChange(-2.5, "share"), "−2.50 pp");
});

test("trend figure carries the API's values and highlights the current point", () => {
  const f = trendFigure(base);
  assert.deepEqual(f.data[0].y, base.trend.segment);
  assert.deepEqual(f.data[1].y, base.trend.book);
  assert.deepEqual(f.data[2].x, ["2026Q2"]);
  assert.deepEqual(f.data[2].y, [2755.1]);
  assert.deepEqual(f.data[2].text, ["SAR 2,755m"]);
});

test("peers: the segment is the highlighted bar; a share gets a book line, an amount does not", () => {
  const f = peersFigure(base);
  const marker = f.data[0].marker as { color: string[] };
  assert.equal(marker.color.filter((c) => c === "#6366f1").length, 1);
  assert.deepEqual((f.data[0] as { y: string[] }).y, ["Energy", "Construction"]);
  assert.equal((f.layout.shapes as unknown[]).length, 0);
  const share = peersFigure({ ...base, kind: "share", peers: { ...base.peers, book: 12.1 } });
  assert.equal((share.layout.shapes as { x0: number }[])[0].x0, 12.1);
});

test("waterfall: from, each contributor's change, to; it adds up", () => {
  const view = base.contributors.views[0];
  const f = contributorsFigure(base, view);
  const d = f.data[0] as { x: string[]; y: number[]; measure: string[] };
  assert.deepEqual(d.x, ["2026Q1", "Building", "Other", "2026Q2"]);
  assert.deepEqual(d.measure, ["absolute", "relative", "relative", "total"]);
  assert.ok(Math.abs(d.y[0] + d.y[1] + d.y[2] - view.to) < 1e-6);
});

test("stage mix: three stacked traces whose labels are shares of the period total", () => {
  const f = stageFigure(base);
  assert.equal(f.data.length, 3);
  const t0 = 4852 + 10438 + 2863;
  assert.equal((f.data[1] as { text: string[] }).text[0], `${((100 * 10438) / t0).toFixed(1)}%`);
});

test("itemText quotes the card's own sentences and numbers", () => {
  const t = itemText({ headline: "h", what_changed: "A rose.", why_it_appeared: "B.", key_numbers: [{ label: "ECL", display: "SAR 1m" }] });
  assert.ok(t.startsWith("A rose. B.") && t.includes("ECL: SAR 1m"));
});
