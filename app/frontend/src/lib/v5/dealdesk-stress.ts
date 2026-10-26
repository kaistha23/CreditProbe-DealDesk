/**
 * PLAN_R11 Session S: the Stress Lab client and the pure functions its screens read (no React, no formatting
 * library beyond lib/v5/format), so the Stress step, the Optimise summary and the tests see the same numbers.
 *
 *   stressApi        GET /stress/scenarios, POST /proposals/{id}/stress, POST /stress/parse (engine service)
 *   summaryTiles     the ≤ 4 tiles: scenarios survived, severe case, revenue to DSCR 1.0, worst ECL
 *   heatmapGroups    scenario rows by group (base first) with each cell's tone and value text
 *   distanceBars     reverse stress as "distance to failure", scaled by the harshest move the scenario set tests
 *   resilienceRows   asked against recommended, scenario by scenario, differences marked
 *
 * Every number is the engine's (backend/dealdesk/stress_lab.py); this file only selects and words it.
 */
import { friendlyError } from "./errors.ts";
import { bps as fbps, pct, ratio, sar } from "./format.ts";
import type { Terms } from "./dealdesk.ts";

// ---------------------------------------------------------------- schemas (r11_stress_api.py)

export type CellKey = "dscr" | "debt_ebitda" | "ltv" | "covenants" | "rating" | "stage" | "raroc" | "limits";
export type CellTone = "pass" | "amber" | "breach" | "na";
export type Driver = "revenue_pct" | "ebitda_margin_bps" | "collateral_pct" | "rate_bps";

export interface Resolved {
  revenue_pct: number; ebitda_margin_bps: number; receivable_days: number; rate_bps: number;
  collateral: Record<string, number>; notches: number; guarantee_unenforceable: boolean;
}
export interface Covenant { type: string; threshold: number; value: number | null; headroom: number | null; status: "pass" | "amber" | "breach" | "not_modelled"; basis: string }
export interface ScenarioMetrics {
  dscr: number | null; debt_ebitda: number | null; ltv: number | null; interest_cover: number | null;
  pd_12m: number; rating: string; notches: { scenario: number; implied: number; total: number };
  stage: 1 | 2 | 3; stage_reason: string; ecl: number; ecl_basis: string; lifetime_raroc: number | null; hurdle: number;
  sva: number; rwa_y1: number; el_y1: number; lgd_y1: number; ead_y1: number; clears_hurdle: boolean;
}
export interface ScenarioRow {
  id: string; group: string; label: string; severity: string; basis: string; shocks: string[]; resolved: Resolved;
  applicable: boolean;
  financials: { revenue: number; ebitda: number; total_debt: number; working_capital_funded: number; base_revenue: number; base_ebitda: number };
  metrics: ScenarioMetrics;
  deltas: { dscr: number | null; pd_12m: number; lifetime_raroc: number | null; sva: number; rwa_y1: number; ecl: number };
  covenants: Covenant[];
  limits: { breaches: string[]; new_hard: string[]; new_soft: string[]; new_labels: string[]; approval_level: string; approval_rank: number; approval_change: number };
  forward: { source: string; p_stage2_next_q: number; p_dpd30_next_q: number | null } | null;
  thresholds: { dscr_limit: number | null; debt_ebitda_limit: number | null; ltv_limit: number | null };
  cells: Record<CellKey, CellTone>;
  fails_on: CellKey[];
  new_fails?: CellKey[];
  survives: boolean;
}
export interface Criterion { criterion: "dscr" | "ltv" | "raroc" | "stage2"; label: string; status: "found" | "already" | "beyond" | "na"; value: number | null; passes_at?: number; note?: string }
export interface Breakeven { driver: Driver; label: string; unit: string; range: [number, number]; criteria: Criterion[]; first: { criterion: string; label: string; value: number } | null; failing_now?: string[] }
export interface Summary {
  applicable: number; survived: number; holds: number; base_fails: CellKey[]; failed: string[]; failed_labels: string[];
  severe: { survives: boolean; fails_on: CellKey[]; new_fails: CellKey[]; lifetime_raroc: number | null; dscr: number | null; stage: number; rating: string } | null;
  worst_raroc: number | null; worst_dscr: number | null; max_ecl: number | null; stage2_count: number;
}
export interface ResilienceSide {
  label: string; terms: Terms; summary: Summary;
  rows: { id: string; label: string; survives: boolean; fails_on: CellKey[]; new_fails: CellKey[]; lifetime_raroc: number | null; sva: number; dscr: number | null; stage: number; ecl: number; applicable: boolean }[];
}
export interface StressLabResult {
  trace_id: string; proposal_id: string; obligor: string; sector: string;
  structure: { label: string; terms: Terms };
  base: ScenarioRow; scenarios: ScenarioRow[]; summary: Summary; breakevens: Breakeven[]; answer: string;
  custom: { text: string | null; parsed: string[]; unparsed: string[]; ok: boolean } | null;
  cells: { key: CellKey; label: string }[];
  pd_source: string; pd_basis: string; basis: Record<string, unknown>; evaluations: number;
  resilience?: { asked: ResilienceSide | null; recommended: ResilienceSide | null; verdict: string; same_structure: boolean };
}
export interface ScenarioDef { id: string; group: string; label: string; severity: string; basis: string; shocks?: Record<string, unknown>; compose?: string[] }
export interface ScenarioCatalogue { trace_id: string; groups: { id: string; label: string }[]; scenarios: ScenarioDef[]; custom_examples: string[]; transmission: Record<string, { basis: string }> }
export interface StressBody { terms?: Partial<Terms> | null; recommended_terms?: Partial<Terms> | null; scenarios?: string[]; custom?: string; resilience?: boolean; breakevens?: boolean; structure_label?: string }

// ---------------------------------------------------------------- client

const ENGINE = "/api/v1/dealdesk";
function origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class StressError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${origin()}${ENGINE}${path}`, { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" } });
  } catch {
    throw new StressError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new StressError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export const stressApi = {
  scenarios: () => call<ScenarioCatalogue>("/stress/scenarios"),
  run: (proposalId: string, body: StressBody) =>
    call<StressLabResult>(`/proposals/${encodeURIComponent(proposalId)}/stress`, { method: "POST", body: JSON.stringify(body) }),
  parse: (text: string) => call<{ parsed: string[]; unparsed: string[]; ok: boolean }>("/stress/parse", { method: "POST", body: JSON.stringify({ text }) }),
};

/** One request per (proposal, structure, recommended, custom): the Optimise summary and the Stress step share it. */
export function stressKey(proposalId: string, body: StressBody): string {
  const norm = (t: unknown) => (t ? JSON.stringify(t, Object.keys(t as object).sort()) : "");
  return [proposalId, norm(body.terms), norm(body.recommended_terms), body.custom ?? "", (body.scenarios ?? []).join(",")].join("|");
}
const CACHE = new Map<string, Promise<StressLabResult>>();
export function runStressCached(proposalId: string, body: StressBody): Promise<StressLabResult> {
  const k = stressKey(proposalId, body);
  let p = CACHE.get(k);
  if (!p) {
    p = stressApi.run(proposalId, body);
    CACHE.set(k, p);
    p.catch(() => CACHE.delete(k));
    if (CACHE.size > 24) CACHE.delete(CACHE.keys().next().value as string);
  }
  return p;
}

// ---------------------------------------------------------------- words and numbers

export const CELL_LABEL: Record<CellKey, string> = {
  dscr: "DSCR", debt_ebitda: "Debt/EBITDA", ltv: "LTV", covenants: "Covenants", rating: "Rating / PD", stage: "Stage",
  raroc: "RAROC", limits: "Limits",
};
export const CELL_ORDER: CellKey[] = ["dscr", "debt_ebitda", "ltv", "covenants", "rating", "stage", "raroc", "limits"];
export const TONE_WORD: Record<CellTone, string> = { pass: "Pass", amber: "Close", breach: "Breach", na: "n/a" };
export const GROUP_LABEL: Record<string, string> = {
  base: "Base", macro: "Macro", sector: "Sector", obligor: "Obligor", collateral: "Collateral", rating: "Rating", combined: "Combined", custom: "Custom",
};
const GROUP_ORDER = ["base", "macro", "sector", "obligor", "collateral", "rating", "combined", "custom"];

const x = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "–" : `${ratio(v)}x`);

/** The value shown inside a heatmap cell. */
export function cellText(key: CellKey, r: ScenarioRow): string {
  const m = r.metrics;
  switch (key) {
    case "dscr": return x(m.dscr);
    case "debt_ebitda": return m.debt_ebitda === null || !Number.isFinite(m.debt_ebitda) ? "EBITDA ≤ 0" : x(m.debt_ebitda);
    case "ltv": return m.ltv === null ? "–" : pct(m.ltv, { dp: 1 });
    case "covenants": {
      const b = r.covenants.filter((c) => c.status === "breach").length;
      const n = r.covenants.filter((c) => c.status !== "not_modelled").length;
      return n ? (b ? `${b}/${n} breached` : "met") : "–";
    }
    case "rating": return m.notches.total ? `${m.rating} (−${m.notches.total})` : m.rating;
    case "stage": return `Stage ${m.stage}`;
    case "raroc": return m.lifetime_raroc === null ? "–" : pct(m.lifetime_raroc, { dp: 1 });
    case "limits": {
      const l = r.limits;
      if (l.new_hard.length) return `${l.new_hard.length} hard`;
      if (l.new_soft.length) return `${l.new_soft.length} soft`;
      if (l.approval_change > 0) return "higher DoA";
      return "none new";
    }
  }
}

/** A driver's move with a typographic minus: "−20.0%", "+150 bps". */
export function fmtDriver(d: Driver, v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  const s = d === "revenue_pct" || d === "collateral_pct" ? pct(v, { dp: 1, signed: true }) : fbps(v, { signed: true });
  return s.replace(/^-/, "−");
}

export const DRIVER_NOUN: Record<Driver, string> = {
  revenue_pct: "Revenue", ebitda_margin_bps: "EBITDA margin", collateral_pct: "Collateral value", rate_bps: "Benchmark rate",
};

// ---------------------------------------------------------------- tiles

export interface TileData { label: string; value: string; sub: string; tone: "neutral" | "positive" | "negative" | "warning"; info: string }

export function summaryTiles(r: StressLabResult): TileData[] {
  const s = r.summary;
  const pre = s.base_fails.length > 0;
  const tiles: TileData[] = [];
  const n = pre ? s.holds : s.survived;
  tiles.push({
    label: pre ? "Scenarios held" : "Scenarios survived", value: `${n} of ${s.applicable}`,
    sub: pre ? `fails ${s.base_fails.map((c) => CELL_LABEL[c]).join(", ")} before stress` : `${s.applicable - n} breach at least one test`,
    tone: n === s.applicable ? "positive" : n >= s.applicable * 0.7 ? "warning" : "negative",
    info: pre ? "Scenarios with no breach beyond those the structure already has before any stress."
      : "Scenarios with no breach: DSCR ≥ 1.0 and its limit, Debt/EBITDA and LTV limits, covenants, minimum rating, Stage 1, the hurdle, no new hard limit.",
  });
  if (s.severe) {
    const fails = pre ? s.severe.new_fails : s.severe.fails_on;
    tiles.push({
      label: "Severe case", value: fails.length ? "Fails" : "Survives",
      sub: fails.length ? `fails ${fails.slice(0, 2).map((c) => CELL_LABEL[c]).join(", ")}${fails.length > 2 ? ` +${fails.length - 2} more` : ""}`
        : `RAROC ${s.severe.lifetime_raroc === null ? "–" : pct(s.severe.lifetime_raroc, { dp: 1 })} · DSCR ${x(s.severe.dscr)} · Stage ${s.severe.stage}`,
      tone: fails.length ? "negative" : "positive",
      info: "Macro, sector and collateral together: oil −30%, rates +200 bps, the obligor's own sector downturn and collateral −30%.",
    });
  }
  const rev = r.breakevens.find((b) => b.driver === "revenue_pct")?.criteria.find((c) => c.criterion === "dscr");
  if (rev) {
    const v = rev.status === "found" ? pct(Math.abs(rev.value ?? 0), { dp: 1 }) : rev.status === "already" ? "0%" : "> 95%";
    tiles.push({
      label: "Revenue to DSCR 1.0", value: rev.status === "found" ? `−${v}` : v,
      sub: rev.status === "already" ? "below 1.0 before any shock" : "fall before debt service is uncovered",
      tone: rev.status === "already" || (rev.status === "found" && Math.abs(rev.value ?? 0) < 0.15) ? "negative"
        : rev.status === "found" && Math.abs(rev.value ?? 0) < 0.3 ? "warning" : "positive",
      info: "Reverse stress: the revenue fall (with operating leverage) at which the obligor's DSCR after the deal reaches 1.0.",
    });
  }
  const worst = [...r.scenarios].filter((s) => s.applicable).sort((a, b) => b.metrics.ecl - a.metrics.ecl)[0];
  if (worst) {
    tiles.push({
      label: "Worst ECL", value: sar(worst.metrics.ecl),
      sub: `${worst.label} · Stage ${worst.metrics.stage}`,
      tone: worst.metrics.stage >= 2 ? "negative" : "neutral",
      info: `The highest IFRS 9 ECL across the scenarios (base ${sar(r.base.metrics.ecl)}): 12-month ECL in Stage 1, lifetime ECL in Stage 2, EAD × LGD in Stage 3.`,
    });
  }
  return tiles.slice(0, 4);
}

// ---------------------------------------------------------------- heatmap

export interface HeatGroup { group: string; label: string; rows: ScenarioRow[] }

export function heatmapGroups(r: StressLabResult): HeatGroup[] {
  const by = new Map<string, ScenarioRow[]>();
  by.set("base", [r.base]);
  for (const s of r.scenarios) {
    if (!by.has(s.group)) by.set(s.group, []);
    by.get(s.group)!.push(s);
  }
  return [...by.entries()].sort((a, b) => GROUP_ORDER.indexOf(a[0]) - GROUP_ORDER.indexOf(b[0]))
    .map(([g, rows]) => ({ group: g, label: GROUP_LABEL[g] ?? g, rows }));
}

/** Columns that tell something for this deal (LTV only where real estate is pledged; covenants where the memo has them). */
export function visibleCells(r: StressLabResult): CellKey[] {
  const all = [r.base, ...r.scenarios];
  return CELL_ORDER.filter((k) => all.some((s) => s.cells[k] !== "na"));
}

// ---------------------------------------------------------------- distance to failure

export interface DistanceBar {
  driver: Driver; criterion: string; label: string; value: number | null; display: string; status: Criterion["status"];
  /** |breakeven| ÷ the harshest move on this driver in the scenario set (1 = the harshest scenario). */
  ratio: number; harshest: number; tone: "breach" | "amber" | "pass";
}

export function harshest(r: StressLabResult, d: Driver): number {
  const vals = r.scenarios.map((s) => {
    const z = s.resolved;
    if (d === "revenue_pct") return Math.abs(z.revenue_pct);
    if (d === "ebitda_margin_bps") return Math.abs(z.ebitda_margin_bps);
    if (d === "rate_bps") return Math.abs(z.rate_bps);
    return Math.max(0, ...Object.values(z.collateral).map((v) => Math.abs(v)));
  });
  return Math.max(0, ...vals);
}

export const BEYOND_RATIO = 3;

export function distanceBars(r: StressLabResult): DistanceBar[] {
  const out: DistanceBar[] = [];
  for (const b of r.breakevens) {
    const h = harshest(r, b.driver) || Math.abs(b.range[1]);
    for (const c of b.criteria) {
      if (c.status === "na") continue;
      const v = c.status === "found" ? c.value : c.status === "already" ? 0 : null;
      const ratioV = v === null ? BEYOND_RATIO : Math.min(BEYOND_RATIO, Math.abs(v) / h);
      out.push({
        driver: b.driver, criterion: c.criterion, label: `${DRIVER_NOUN[b.driver]} → ${c.label}`, value: v,
        display: c.status === "beyond" ? `beyond ${fmtDriver(b.driver, b.range[1])}` : c.status === "already" ? "fails now" : fmtDriver(b.driver, v),
        status: c.status, ratio: ratioV, harshest: h,
        tone: ratioV < 1 ? "breach" : ratioV < 1.5 ? "amber" : "pass",
      });
    }
  }
  return out.sort((a, b) => a.ratio - b.ratio);
}

/** The first thing that breaks under stress: the shortest distance across drivers (tests already failing before any
 *  shock are the answer line's "fails … before any stress", not a breakeven). */
export function firstToBreak(r: StressLabResult): DistanceBar | null {
  const d = distanceBars(r).filter((b) => b.status === "found");
  return d.length ? d[0] : null;
}

// ---------------------------------------------------------------- resilience

export interface ResilienceRow { id: string; label: string; asked: boolean | null; rec: boolean | null; askedRaroc: number | null; recRaroc: number | null; differs: boolean }

export function resilienceRows(r: StressLabResult): ResilienceRow[] {
  const a = r.resilience?.asked;
  const c = r.resilience?.recommended;
  if (!a) return [];
  const recBy = new Map((c?.rows ?? []).map((x) => [x.id, x]));
  return a.rows.filter((x) => x.applicable).map((x) => {
    const y = recBy.get(x.id);
    const okA = x.survives;
    const okR = y ? y.survives : null;
    return { id: x.id, label: x.label, asked: okA, rec: okR, askedRaroc: x.lifetime_raroc, recRaroc: y?.lifetime_raroc ?? null, differs: okR !== null && okA !== okR };
  });
}

export function resilienceCounts(r: StressLabResult): { asked: number; rec: number | null; of: number } {
  const rows = resilienceRows(r);
  return { asked: rows.filter((x) => x.asked).length, rec: r.resilience?.recommended ? rows.filter((x) => x.rec).length : null, of: rows.length };
}

/** The one-line answer (the engine's; a fallback from the summary when an older engine omits it). */
export function answerLine(r: StressLabResult): string {
  if (r.answer) return r.answer;
  const s = r.summary;
  return `Survives ${s.survived} of ${s.applicable} scenarios.`;
}
