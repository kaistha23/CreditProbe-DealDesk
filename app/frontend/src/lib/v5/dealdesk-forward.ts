/**
 * PLAN_R11 Session F: forward risk on a proposed deal. Types for POST /api/v1/dealdesk/proposals/{id}/forward-risk
 * and GET /api/v1/dealdesk/forward-risk/model-card, and the pure read functions the ForwardRiskPanel and its tests
 * share (no fetch, no React): which structures to send, the headline tiles, the path chart series, the structure
 * comparison and the driver bars. Every figure comes from the engine and the transition models.
 */
import type { Terms } from "./dealdesk.ts";

export type StructureRole = "asked" | "recommended" | "alternative";

/**
 * What the panel receives from Optimise: one entry per structure on screen. Session U sends `{ key, label, terms }` with
 * key "ask", "recommended" or "alternative_n"; the server reads the role from `role`, else from `key`.
 */
export interface ForwardStructureInput { key?: string; label: string; role?: StructureRole; terms: Terms }

export interface StagePoint { quarter: number; s1: number; s2: number; s3: number }
export interface Driver {
  feature: string; label: string; value: string | number | null; contribution: number; direction: "raises" | "lowers"; structure_term: boolean;
}
export interface StageEcl { s1: number; s2: number; s3: number }
export interface ForwardStructure {
  key: string; label: string; role: StructureRole; also?: string[]; is_recommended?: boolean; terms: Terms;
  metrics: { lifetime_raroc: number; sva: number; clears_hurdle: boolean; hurdle: number; pd_12m: number; lgd_y1: number; ead_y1: number;
             day_one_ecl: number; amount_sar_mn: number };
  p_stage2_next_q: number; p_stage2_model: number; p_dpd30_next_q: number; backstop_applied: boolean;
  stage_path: StagePoint[];
  chain: { matrix: number[][]; basis: Record<string, string> };
  ecl: { day1: number; next_q: number; q4: number; engine_day_one_ecl: number;
         by_quarter: { quarter: number; expected_ecl: number; stage_ecl: StageEcl }[] };
  drivers: Driver[];
  features: Record<string, number | null>;
  feature_basis: Record<string, string>;
  ecl_optimal: boolean;
}
export interface EwsRule { id: string; label: string; weight: number; rule: string; values: Record<string, number | null>; fired?: boolean }
export interface ForwardEws {
  ruleset: string; score: number; band: string; fired: EwsRule[]; checked: EwsRule[];
  not_evaluable: { id: string; label: string; missing: string[] }[];
  covenant_breaches_post_deal: { covenant: string; threshold: number; post_deal: number }[];
  basis: string;
  book: { as_of: string; borrowers: number; share_at_or_below: number | null; band_share: Record<string, number>; median_score: number };
  current: { quarter: string; score: number; band: string; reasons: string[]; ruleset: string } | null;
}
export interface LeverRow {
  lever: string; label: string; d_stage2: number; d_raroc_bps: number; d_ecl_q4: number; stage2_cut_per_bp: number | null;
  free: boolean; clears_hurdle: boolean;
}
export interface ForwardRiskResult {
  trace_id: string; proposal_id: string; as_of: string;
  obligor: { name: string; existing: boolean; rating: string; sector: string };
  answer: string;
  headline: { label: string; role: StructureRole; is_recommended?: boolean; p_stage2_next_q: number; p_dpd30_next_q: number; ecl_day1: number; ecl_q4: number;
              ews_band: string; ews_score: number };
  book: { p_stage2_next_q: number; p_dpd30_next_q: number; observed_stage2: number; observed_dpd30: number; observed_quarter: string; basis: string };
  structures: ForwardStructure[];
  ecl_optimal: { label: string; role: StructureRole; ecl_q4: number; lifetime_raroc: number; reason: string } | null;
  best_lever: { reference: string; best: LeverRow | null; levers: LeverRow[]; note?: string } | null;
  ews: ForwardEws;
  asked_label: string;
  model: { version: string; trained: string; as_of: string; card: string };
  validation: Record<string, boolean>;
  method: string;
}

export interface TargetCardBlock { n: number; events: number; event_rate: number; mean_predicted: number; auc: number; gini: number; ks: number }
export interface TargetCard {
  target: string; rows: number; events: number; train_quarters: string; oot_quarters: string;
  in_time: TargetCardBlock; out_of_time: TargetCardBlock; calibration_test: TargetCardBlock; calibration_note: string;
  calibration_deciles_oot: { decile: number; n: number; predicted: number; actual: number }[];
  psi_train_vs_oot: number; psi_train_vs_last_quarter: number;
  importance: { feature: string; label: string; share: number }[];
  monotone: { feature: string; sign: number; violations: number }[];
}
export interface BacktestRow { quarter: string; next_quarter: string; n: number; actual: number; predicted: number; sample: string }
export interface TransitionCard {
  version: string; trained: string; as_of: string;
  card: { method: string; split: string; targets: Record<"stage2" | "dpd30", TargetCard>; limitations: string[] };
  backtest: Record<"stage2" | "dpd30", BacktestRow[]>;
  chain: { s2_to_s1: number; s2_to_s3: number; basis: string };
}

export const ROLE_LABEL: Record<StructureRole, string> = { asked: "As asked", recommended: "Recommended", alternative: "Alternative" };

/** The request body: the structures shown in Optimise (the server adds the ask itself), without duplicates. */
export function requestBody(structures: readonly ForwardStructureInput[]): { structures: ForwardStructureInput[] } {
  const seen = new Set<string>();
  const out: ForwardStructureInput[] = [];
  for (const s of structures) {
    const k = JSON.stringify(s.terms);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ ...(s.key ? { key: s.key } : {}), label: s.label, ...(s.role ? { role: s.role } : {}), terms: s.terms });
  }
  return { structures: out };
}

/** The headline structure: the recommendation when there is one, else the ask. */
export function headlineStructure(r: ForwardRiskResult): ForwardStructure | undefined {
  return r.structures.find((s) => s.role === "recommended") ?? r.structures.find((s) => s.is_recommended)
    ?? r.structures.find((s) => s.role === "asked") ?? r.structures[0];
}

export function askedStructure(r: ForwardRiskResult): ForwardStructure | undefined {
  return r.structures.find((s) => s.role === "asked");
}

/** "3.1%" / "0.42%": two decimals under 1%, one decimal above. */
export function prob(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const p = v * 100;
  return `${p.toLocaleString("en-US", { minimumFractionDigits: p < 1 ? 2 : 1, maximumFractionDigits: p < 1 ? 2 : 1 })}%`;
}

/** Relative to the book: "below book", "above book" or "at book" (within 10% of the book rate). */
export function vsBook(v: number, book: number): "below" | "above" | "at" {
  if (!Number.isFinite(v) || !Number.isFinite(book) || book <= 0) return "at";
  const r = v / book;
  return r < 0.9 ? "below" : r > 1.1 ? "above" : "at";
}

export const EWS_BANDS = ["none", "low", "moderate", "high", "critical"] as const;
export function bandLabel(b: string): string {
  return b === "none" ? "None" : b.charAt(0).toUpperCase() + b.slice(1);
}
export function bandTone(b: string): "positive" | "neutral" | "warning" | "negative" {
  return b === "none" ? "positive" : b === "low" ? "neutral" : b === "moderate" ? "warning" : "negative";
}

/** Stage 2+3 probability by quarter for one structure: the path chart's y values. */
export function stage2PlusPath(s: ForwardStructure): { quarter: number; s2: number; s3: number; s23: number }[] {
  return s.stage_path.map((p) => ({ quarter: p.quarter, s2: p.s2, s3: p.s3, s23: p.s2 + p.s3 }));
}

/** The structure comparison rows, in the order shown in Optimise. */
export function comparisonRows(r: ForwardRiskResult): { label: string; role: StructureRole; pStage2: number; eclQ4: number; eclDay1: number;
  raroc: number; clears: boolean; optimal: boolean }[] {
  return r.structures.map((s) => ({ label: s.label, role: s.role, pStage2: s.p_stage2_next_q, eclQ4: s.ecl.q4, eclDay1: s.ecl.day1,
    raroc: s.metrics.lifetime_raroc, clears: s.metrics.clears_hurdle, optimal: s.ecl_optimal }));
}

/** A chart category label on at most two lines of about `width` characters ("Cash margin<br>and price"). */
export function wrapLabel(label: string, width = 14): string {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if (cur && (cur + " " + w).length > width) { lines.push(cur); cur = w; } else cur = cur ? `${cur} ${w}` : w;
  }
  if (cur) lines.push(cur);
  if (lines.length <= 2) return lines.join("<br>");
  const second = lines.slice(1).join(" ");
  return `${lines[0]}<br>${second.length > width ? `${second.slice(0, width - 1)}…` : second}`;
}

/** Driver bars, largest absolute contribution first, at most 5. */
export function driverBars(s: ForwardStructure): Driver[] {
  return [...s.drivers].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 5);
}

/** A driver's value as read on screen. */
export function driverValue(d: Driver): string {
  const v = d.value;
  if (v === null || v === undefined) return "not available";
  if (typeof v === "string") return v;
  switch (d.feature) {
    case "utilisation_pct": case "collateral_cover_pct": case "ebitda_margin_pct": case "inflow_trend_pct":
      return `${v.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
    case "sec_s2_share": case "sec_dpd30_share": case "sec_s2_flow": case "sec_dpd30_flow": case "log_pd_ttc":
      return prob(v);
    case "leverage_x": case "dscr_x": case "interest_cover_x": case "current_ratio_x":
      return `${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}x`;
    case "log_limit": return `SAR ${v.toLocaleString("en-US", { maximumFractionDigits: 1 })}m`;
    case "obl_dpd_max_4q": case "external_dpd_days": return `${v} days`;
    default: return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
}

/** The best-lever sentence, or empty when none lowers P(Stage 2). */
export function leverLine(r: ForwardRiskResult): string {
  const b = r.best_lever?.best;
  if (!b) return "";
  const cut = prob(Math.abs(b.d_stage2));
  if (b.free) return `${b.label} cuts P(Stage 2) by ${cut} with no RAROC given up`;
  const per = b.stage2_cut_per_bp;
  return `${b.label} cuts P(Stage 2) by ${cut} for ${Math.abs(b.d_raroc_bps).toFixed(0)} bps of RAROC` +
    (per !== null && Number.isFinite(per) ? ` (${(per * 1e4).toFixed(2)} bps of probability per bp)` : "");
}

/** Probabilities in [0, 1] and every stage path summing to 1: the panel refuses to draw otherwise. */
export function checkResult(r: ForwardRiskResult): string[] {
  const problems: string[] = [];
  for (const s of r.structures) {
    for (const v of [s.p_stage2_next_q, s.p_dpd30_next_q]) if (!(v >= 0 && v <= 1)) problems.push(`${s.label}: probability out of range`);
    for (const p of s.stage_path) if (Math.abs(p.s1 + p.s2 + p.s3 - 1) > 1e-6) problems.push(`${s.label}: Q${p.quarter} path does not sum to 1`);
  }
  return problems;
}
