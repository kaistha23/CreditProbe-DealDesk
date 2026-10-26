import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type ForwardRiskResult, type ForwardStructure, askedStructure, bandLabel, bandTone, checkResult, comparisonRows, driverBars,
  driverValue, headlineStructure, wrapLabel, leverLine, prob, requestBody, stage2PlusPath, vsBook,
} from "./dealdesk-forward.ts";

const terms = (amount: number) => ({ amount, tenor_years: 3, margin_bps: 250, currency: "SAR" }) as never;

function structure(label: string, role: ForwardStructure["role"], p2: number, p30: number, q4: number, optimal = false): ForwardStructure {
  const path = [0, 1, 2, 3, 4].map((q) => {
    const s2 = q === 0 ? 0 : p2 * q * 0.9;
    const s3 = q === 0 ? 0 : 0.001 * q;
    return { quarter: q, s1: 1 - s2 - s3, s2, s3 };
  });
  return {
    key: role, label, role, terms: terms(role === "asked" ? 100 : 80),
    metrics: { lifetime_raroc: role === "asked" ? 0.12 : 0.18, sva: 1, clears_hurdle: role !== "asked", hurdle: 0.16, pd_12m: 0.01, lgd_y1: 0.4,
               ead_y1: 80, day_one_ecl: 0.3, amount_sar_mn: 80 },
    p_stage2_next_q: p2, p_stage2_model: p2, p_dpd30_next_q: p30, backstop_applied: false, stage_path: path,
    chain: { matrix: [[0.97, 0.02, 0.01], [0.2, 0.75, 0.05], [0, 0, 1]], basis: {} },
    ecl: { day1: 0.3, next_q: 0.35, q4: q4, engine_day_one_ecl: 0.3, by_quarter: [] },
    drivers: [
      { feature: "dscr_x", label: "Debt service cover", value: 1.37, contribution: 0.38, direction: "raises", structure_term: true },
      { feature: "grade_rank", label: "Internal rating", value: "BB", contribution: 0.18, direction: "raises", structure_term: false },
      { feature: "current_ratio_x", label: "Current ratio", value: 1.65, contribution: -0.29, direction: "lowers", structure_term: false },
      { feature: "utilisation_pct", label: "Utilisation", value: 100, contribution: 0.05, direction: "raises", structure_term: true },
      { feature: "log_limit", label: "Facility size", value: 16, contribution: 0.02, direction: "raises", structure_term: true },
      { feature: "sector_code", label: "Sector", value: "Construction", contribution: -0.23, direction: "lowers", structure_term: false },
    ],
    features: {}, feature_basis: {}, ecl_optimal: optimal,
  };
}

const result = (): ForwardRiskResult => ({
  trace_id: "DT-000000000000", proposal_id: "DD-02", as_of: "2026Q2",
  obligor: { name: "Taif Central Engineering", existing: true, rating: "BB", sector: "Construction" },
  answer: "Recommended structure: 3.4% chance of Stage 2 next quarter (book 5.0%), 2.3% of 30+ DPD; EWS band None.",
  headline: { label: "Closest to the ask", role: "recommended", p_stage2_next_q: 0.034, p_dpd30_next_q: 0.023, ecl_day1: 0.3, ecl_q4: 0.5,
              ews_band: "none", ews_score: 0 },
  book: { p_stage2_next_q: 0.05, p_dpd30_next_q: 0.02, observed_stage2: 0.036, observed_dpd30: 0.026, observed_quarter: "2026Q1", basis: "" },
  structures: [structure("As asked", "asked", 0.037, 0.023, 0.8), structure("Closest to the ask", "recommended", 0.034, 0.023, 0.5, true),
               structure("Maximum value", "alternative", 0.024, 0.018, 0.6)],
  ecl_optimal: { label: "Closest to the ask", role: "recommended", ecl_q4: 0.5, lifetime_raroc: 0.18, reason: "" },
  best_lever: { reference: "Closest to the ask", best: { lever: "cash_margin", label: "Cash margin +20 pts", d_stage2: -0.004, d_raroc_bps: -25,
    d_ecl_q4: -0.1, stage2_cut_per_bp: 0.00016, free: false, clears_hurdle: true }, levers: [] },
  ews: { ruleset: "gw-ews-1.3.0", score: 0, band: "none", fired: [], checked: [], not_evaluable: [], covenant_breaches_post_deal: [], basis: "",
         book: { as_of: "2026Q2", borrowers: 5412, share_at_or_below: 0.6, band_share: {}, median_score: 0 }, current: null },
  asked_label: "As asked", model: { version: "dd-transition-1.0.0", trained: "2026-10-17", as_of: "2026Q2", card: "" },
  validation: {}, method: "",
});

test("request body drops duplicate structures and keeps order", () => {
  const a = { label: "Closest to the ask", role: "recommended" as const, terms: terms(80) };
  const b = { label: "Maximum value", role: "alternative" as const, terms: terms(80) };
  const c = { label: "Lower amount", role: "alternative" as const, terms: terms(60) };
  assert.deepEqual(requestBody([a, b, c]).structures.map((s) => s.label), ["Closest to the ask", "Lower amount"]);
});

test("request body keeps Session U's key-only structures", () => {
  const body = requestBody([{ key: "ask", label: "Ask", terms: terms(100) }, { key: "recommended", label: "Recommended", terms: terms(80) }]);
  assert.deepEqual(body.structures.map((s) => [s.key, s.role]), [["ask", undefined], ["recommended", undefined]]);
});

test("headline is the recommendation, else the ask", () => {
  const r = result();
  assert.equal(headlineStructure(r)?.label, "Closest to the ask");
  assert.equal(askedStructure(r)?.label, "As asked");
  r.structures = r.structures.filter((s) => s.role !== "recommended");
  assert.equal(headlineStructure(r)?.role, "asked");
});

test("probability format and book comparison", () => {
  assert.equal(prob(0.0342), "3.4%");
  assert.equal(prob(0.0042), "0.42%");
  assert.equal(prob(Number.NaN), "–");
  assert.equal(vsBook(0.034, 0.05), "below");
  assert.equal(vsBook(0.07, 0.05), "above");
  assert.equal(vsBook(0.051, 0.05), "at");
});

test("EWS band words and tones", () => {
  assert.equal(bandLabel("none"), "None");
  assert.equal(bandLabel("moderate"), "Moderate");
  assert.equal(bandTone("none"), "positive");
  assert.equal(bandTone("high"), "negative");
});

test("paths and comparison read the structures as returned", () => {
  const r = result();
  const p = stage2PlusPath(r.structures[1]);
  assert.equal(p.length, 5);
  assert.ok(Math.abs(p[4].s23 - (p[4].s2 + p[4].s3)) < 1e-12);
  const rows = comparisonRows(r);
  assert.deepEqual(rows.map((x) => x.role), ["asked", "recommended", "alternative"]);
  assert.equal(rows.filter((x) => x.optimal).length, 1);
});

test("drivers: at most five, largest first, values read in units", () => {
  const d = driverBars(result().structures[1]);
  assert.equal(d.length, 5);
  assert.equal(d[0].feature, "dscr_x");
  assert.ok(Math.abs(d[0].contribution) >= Math.abs(d[4].contribution));
  assert.equal(driverValue(d[0]), "1.37x");
  assert.equal(driverValue({ ...d[0], feature: "utilisation_pct", value: 100 }), "100%");
  assert.equal(driverValue({ ...d[0], value: null }), "not available");
});

test("lever line", () => {
  const r = result();
  assert.match(leverLine(r), /^Cash margin \+20 pts cuts P\(Stage 2\) by 0\.40% for 25 bps of RAROC/);
  r.best_lever = { reference: "x", best: null, levers: [] };
  assert.equal(leverLine(r), "");
});

test("result check: probabilities in range and paths summing to one", () => {
  const r = result();
  assert.deepEqual(checkResult(r), []);
  r.structures[0].p_stage2_next_q = 1.2;
  r.structures[1].stage_path[2].s1 = 0.5;
  assert.equal(checkResult(r).length, 2);
});

test("chart labels wrap on two lines at most", () => {
  assert.equal(wrapLabel("As asked"), "As asked");
  assert.equal(wrapLabel("Cash margin and price"), "Cash margin<br>and price");
  assert.equal(wrapLabel("Credit insurance and assignment of proceeds"), "Credit<br>insurance and…");
});
