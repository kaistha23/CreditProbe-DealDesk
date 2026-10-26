/** PLAN_R11 Session S: the Stress Lab's pure functions over an engine result (DD-06 with a custom shock) and the
 *  component contract (StressLab, StressSummary; answer first, heatmap, distance bars, resilience, drawer; kit only). */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import {
  CELL_ORDER, answerLine, cellText, distanceBars, firstToBreak, fmtDriver, harshest, heatmapGroups, resilienceCounts,
  resilienceRows, stressKey, summaryTiles, visibleCells, type StressLabResult,
} from "./dealdesk-stress.ts";

const here = new URL("./", import.meta.url).pathname;
const r = JSON.parse(readFileSync(here + "dealdesk-stress.fixture.json", "utf8")) as StressLabResult;
const comp = readFileSync(here + "../../components/v5/dealdesk/stress-lab.tsx", "utf8");

test("S3: the answer line comes from the engine and says how many scenarios hold", () => {
  const a = answerLine(r);
  assert.equal(a, r.answer);
  assert.match(a, /(Survives|holds in) \d+ of \d+ scenarios/);
  assert.match(a, /revenue can fall \d+% before DSCR < 1\.0/);
});

test("S3: at most four tiles, each with a value, a sub-line and an (i)", () => {
  const t = summaryTiles(r);
  assert.ok(t.length >= 3 && t.length <= 4);
  for (const x of t) assert.ok(x.label && x.value && x.sub && x.info, x.label);
  const first = t[0];
  const s = r.summary;
  assert.equal(first.value, `${s.base_fails.length ? s.holds : s.survived} of ${s.applicable}`);
  assert.ok(t.some((x) => x.label === "Severe case"));
  assert.ok(t.some((x) => x.label === "Revenue to DSCR 1.0" && x.value.startsWith("−")));
});

test("S3: heatmap rows are grouped in order with the base first; every cell has a tone and a value", () => {
  const g = heatmapGroups(r);
  assert.equal(g[0].group, "base");
  const order = g.map((x) => x.group);
  assert.deepEqual(order, [...order].sort((a, b) => ["base", "macro", "sector", "obligor", "collateral", "rating", "combined", "custom"].indexOf(a)
    - ["base", "macro", "sector", "obligor", "collateral", "rating", "combined", "custom"].indexOf(b)));
  assert.ok(order.includes("custom"));
  const n = g.reduce((k, x) => k + x.rows.length, 0);
  assert.equal(n, r.scenarios.length + 1);
  const cols = visibleCells(r);
  assert.ok(cols.length >= 6 && cols.every((c) => CELL_ORDER.includes(c)));
  for (const x of g) for (const row of x.rows) for (const c of cols) {
    assert.ok(["pass", "amber", "breach", "na"].includes(row.cells[c]));
    const v = cellText(c, row);
    assert.ok(v.length > 0 && !/undefined|NaN|null/.test(v), `${row.id} ${c} ${v}`);
  }
});

test("S3: a scenario that breaches is marked so in its cells; survives means no breach", () => {
  for (const s of r.scenarios) assert.equal(s.survives, !Object.values(s.cells).includes("breach"));
});

test("S3: distance to failure is scaled by the harshest tested move and sorted shortest first", () => {
  const b = distanceBars(r);
  assert.ok(b.length >= 4);
  for (let i = 1; i < b.length; i++) assert.ok(b[i].ratio >= b[i - 1].ratio);
  const rev = b.find((x) => x.driver === "revenue_pct" && x.criterion === "dscr");
  assert.ok(rev && rev.status === "found");
  assert.equal(rev.harshest, harshest(r, "revenue_pct"));
  assert.ok(Math.abs(rev.ratio - Math.abs(rev.value!) / rev.harshest) < 1e-12);
  assert.equal(rev.tone, rev.ratio < 1 ? "breach" : rev.ratio < 1.5 ? "amber" : "pass");
  const f = firstToBreak(r);
  assert.ok(f && f.ratio === Math.min(...b.filter((x) => x.status === "found").map((x) => x.ratio)));
  assert.equal(fmtDriver("revenue_pct", -0.2), "−20.0%");
  assert.equal(fmtDriver("ebitda_margin_bps", -300), "−300 bps");
  assert.equal(fmtDriver("rate_bps", 150), "+150 bps");
});

test("S3: resilience compares asked and recommended on the same scenarios", () => {
  const rows = resilienceRows(r);
  assert.equal(rows.length, r.scenarios.filter((s) => s.applicable).length);
  const c = resilienceCounts(r);
  assert.equal(c.asked, r.resilience!.asked!.summary.survived);
  if (r.resilience!.recommended) assert.equal(c.rec, r.resilience!.recommended.summary.survived);
  assert.ok(rows.every((x) => x.differs === (x.rec !== null && x.asked !== x.rec)));
  assert.ok(r.resilience!.verdict.length > 10);
});

test("S3: one request per structure (the Optimise summary and the Stress step share it)", () => {
  const a = stressKey("DD-06", { terms: { amount: 25, tenor_years: 3 } as never });
  const b = stressKey("DD-06", { terms: { tenor_years: 3, amount: 25 } as never });
  assert.equal(a, b);
  assert.notEqual(a, stressKey("DD-06", { terms: { amount: 30, tenor_years: 3 } as never }));
});

test("S3 contract: StressLab and StressSummary exported; answer first; heatmap, distance bars, resilience, drawer", () => {
  assert.match(comp, /export function StressLab\(\{ proposalId, terms/);
  assert.match(comp, /export function StressSummary\(/);
  for (const id of ["stress-lab", "stress-answer", "stress-tiles", "stress-heatmap", "stress-distance", "stress-resilience",
                    "stress-drawer", "stress-summary", "stress-custom"]) assert.ok(comp.includes(`"${id}`) || comp.includes(`\`${id}`), id);
  const lab = comp.slice(comp.indexOf("export function StressLab("));
  const at = (s: string) => { const i = lab.indexOf(s); assert.ok(i >= 0, s); return i; };
  assert.ok(at('"stress-answer"') < at("<Tiles") && at("<Tiles") < at("<Heatmap"), "answer and tiles before evidence");
  assert.ok(at("<Heatmap") < at("<DistanceChart") && at("<DistanceChart") < at("<Resilience") && at("<Resilience") < at("<Drawer"));
  assert.ok(comp.includes('from "./kit"') && comp.includes("KpiRow") && comp.includes("ChartTitle") && comp.includes("Explainer"));
  assert.ok(!/TODO|FIXME|console\.log|JSON\.stringify\(r/.test(comp), "no rough notes, debug or raw JSON");
});
