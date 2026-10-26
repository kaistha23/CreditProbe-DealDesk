/** PLAN_R10 Session D: deal view only on open, horizontal steps, the ask, Optimise view, four tiles, bounds. */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import { bestOffers, bestTenorRate, rarocByTenor } from "../v5/dealdesk-offer.ts";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");
const dir = "components/v5/dealdesk/";

test("D1: opening a deal shows the view only; the saved thread is in Recent threads, collapsed, at the bottom", () => {
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes("setHistory(th.turns)") && !t.includes("setTurns(th.turns)"), "loaded turns go to history, not the open thread");
  assert.ok(t.includes('data-testid="dealdesk-recent-threads"') && t.includes("open={historyOpen}"));
  assert.ok(t.includes("React.useState(false);\n  const scroller"), "Recent threads start collapsed");
  assert.ok(t.indexOf('data-testid="dealdesk-conversation"') < t.indexOf('data-testid="dealdesk-recent-threads"'), "new thread under the view, recent threads below");
  assert.ok(!t.includes("<ThreadShell"));
});

test("D2: the step bar is one horizontal row", () => {
  const k = read(dir + "kit.tsx");
  const st = k.slice(k.indexOf("export function Stepper"), k.indexOf("export function TileRow"));
  assert.ok(st.includes("flex-row flex-nowrap") && !st.includes("grid-cols-1") && !st.includes("flex-col"));
});

test("D3: the Proposal step shows the ask; Analysis keeps one ask line at the top", () => {
  const s = read(dir + "steps.tsx");
  for (const r of ["Amount", "Tenor", "Pricing", "Fees", "Security", "Covenants", "Purpose"]) assert.ok(s.includes(`label: "${r}"`), r);
  const proposal = s.slice(s.indexOf("export function ProposalStep"), s.indexOf("export function AnalysisStep"));
  assert.ok(proposal.indexOf("<AskCard") > -1 && proposal.indexOf("<AskCard") < proposal.indexOf("<ProposalInFull"));
  const analysis = s.slice(s.indexOf("export function AnalysisStep"));
  assert.ok(analysis.indexOf("<AskLine") > -1 && analysis.indexOf("<AskLine") < analysis.indexOf("<Verdict"));
});

test("D4: Optimise shows the hurdle-rate chart, RAROC against tenor and amount, best tenor and rate, three offers", () => {
  const o = read(dir + "optimise-view.tsx");
  for (const c of ["<IsoRarocHeatmap", "<RarocTenorCurve", "<RarocAmountCurve", "dealdesk-best-tenor-rate", "dealdesk-best-offers", "-raroc`}", "-sva`}"]) assert.ok(o.includes(c), c);
  const s = read(dir + "steps.tsx");
  const structure = s.slice(s.indexOf("export function StructureStep"));
  assert.ok(structure.indexOf("<OptimiseView") > -1 && structure.indexOf("<OptimiseView") < structure.indexOf("<StructureItYourself"))  // PLAN_R12 I14 (G, mounted by U): the term panel inside "Structure it yourself";
  // RAROC charts are kept on Analysis
  const analysis = s.slice(s.indexOf("export function AnalysisStep"), s.indexOf("export function StructureStep"));
  for (const c of ["<WaterfallChart", "<IsoRarocHeatmap", "<RarocAmountCurve", "<TornadoChart", "<HeadroomChart", "<RatingChart"]) assert.ok(analysis.includes(c), c);
});

test("D5: four tiles in one row (RAROC price only, SVA, RWA, approval) through the shared KpiRow", () => {
  const s = read(dir + "steps.tsx");
  const row = s.slice(s.indexOf("export function KpiRow"), s.indexOf("// ------------------------------------------------------------------ the ask"));
  assert.ok(row.includes("<SharedKpiRow"));
  assert.equal((row.match(/\{ label: "/g) ?? []).length, 4);
  for (const l of ["RAROC (price only)", "SVA", "RWA", "Approval"]) assert.ok(row.includes(`label: "${l}"`), l);
  for (const f of ["portfolio-raroc.tsx", "proposal-review.tsx"]) assert.ok(read(dir + f).includes("<KpiRow"), f);
});

test("D6: the panel scrolls, the composer has its own space, text wraps", () => {
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes("overflow-y-auto overflow-x-hidden") && t.includes("[overflow-wrap:anywhere]") && t.includes("shrink-0 border-t"));
});

const grid = {
  trace_id: "t", x: "margin_bps", y: "tenor_years", x_values: [100, 150, 200, 250], y_values: [1, 2, 3, 4, 5],
  values: [[0.10, 0.16, 0.22, 0.28], [0.09, 0.15, 0.21, 0.27], [0.08, 0.14, 0.20, 0.26], [0.07, 0.13, 0.19, 0.25], [0.06, 0.12, 0.14, 0.24]],
  hurdle: 0.15, ask: { x: 200, y: 3 },
};
const ask = { margin_bps: 200, commission_bps: 0, tenor_years: 3 } as never;

test("best tenor and rate from the grid; RAROC against tenor at the asked margin", () => {
  assert.deepEqual(rarocByTenor(grid, ask).map((r) => r.tenor), [1, 2, 3, 4, 5]);
  assert.equal(rarocByTenor(grid, ask)[2].raroc, 0.20);
  const tr = bestTenorRate(grid, ask, 128.4);
  assert.equal(tr.maxTenor, 4);
  assert.equal(tr.minPrice, 129, "the engine breakeven, rounded up");
  assert.equal(bestTenorRate(grid, ask, null).minPrice, 200, "grid fallback");
});

test("bestOffers: recommended then two distinct alternatives, the same structure every deal", () => {
  const sol = (label: string, amount: number) => ({ label, terms: { amount } as never, metrics: {} as never, distance: 0, approval: {} as never, soft_breaches: [], changes: [] });
  const opt = { closest: sol("Closest to ask", 1), max_sva: sol("Maximum value", 2), counter_offers: [sol("Shorter tenor", 1), sol("Higher fee", 3), sol("X", 4)], alternatives: [] } as never;
  const o = bestOffers(opt);
  assert.equal(o.length, 3);
  assert.equal(o[0].role, "recommended");
  assert.deepEqual(o.map((x) => (x.solution.terms as unknown as { amount: number }).amount), [1, 2, 3]);
  assert.deepEqual(bestOffers(null), []);
});
