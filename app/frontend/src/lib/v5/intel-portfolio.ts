/**
 * PLAN_R13 §I session ID: portfolio steering client (Deal Desk service, prefix /api/v1/intel/portfolio).
 *
 * Five engines, one API each: growth headroom map (#14), exit and sell-down list (#15), RWA finder (#16),
 * ECL bridge forecast (#17) and workout optimiser (#11). Every response carries the same envelope: a headline and
 * 3–5 summary lines from the deterministic writer, KPIs, rows, data limits, method and lineage.
 * Money is SAR million. Pure helpers live here (no React, no path aliases) so node --test can run them.
 */

export const INTEL_PORTFOLIO = "/api/v1/intel/portfolio";

export type PortfolioTool = "headroom" | "exits" | "rwa" | "ecl_bridge" | "workout";

export interface IntelKpi { key: string; label: string; value: number | string | null; unit: string; text: string | null }
export interface IntelLineage { domain: string; relation: string; path: string | null; period: string | number | null; rows: number | null; columns: string[]; note?: string }

export interface IntelEnvelope<R> {
  engine: string; version: string; title: string; as_of: string; ecl_run: string; headline: string; summary: string[];
  kpis: IntelKpi[]; rows: R[]; data_limits: string[]; method: string[]; lineage: IntelLineage[]; writer: "deterministic"; digest: string;
}

export interface HeadroomConstraint { name: string; label: string; cap: number | null; now: number | null; unit: string; headroom_sar_mn: number; already_beyond: boolean }
export interface HeadroomRow {
  sector: string; bucket: string; slice: string; book_ead_sar_mn: number; headroom_sar_mn: number; binding: string; binding_label: string;
  binding_already_beyond: boolean; rwa_used_sar_mn: number; capital_used_sar_mn: number; el_rate_bps: number; risk_weight: number;
  hurdle: number; hurdle_source: string; raroc_median: number | null; clears_hurdle: boolean | null; ead_share_above_hurdle: number | null;
  margin_uplift_bps: number | null; constraints: HeadroomConstraint[];
}
export interface HeadroomGroup { group_id: string; group_name: string; members: number; ead_sar_mn: number; cap_sar_mn: number; headroom_sar_mn: number; binding: string; over_cap_sar_mn: number; utilisation: number }
export interface Headroom extends IntelEnvelope<HeadroomRow> { level: "appetite" | "trigger" | "limit"; groups: HeadroomGroup[] }

export type ExitAction = "not_renew" | "sell_down" | "reduce";
export interface ExitRow {
  borrower_id: string; borrower_name: string; sector: string; bucket: string; rating: string; group_name: string; relationship_tier: string;
  ead_sar_mn: number; facilities: number; raroc_now: number | null; hurdle: number; ews_band: string | null; action: ExitAction; how: string;
  ead_reduced_sar_mn: number; capital_freed_sar_mn: number; ecl_freed_sar_mn: number; sale_loss_sar_mn: number; net_freed_sar_mn: number;
  relationship_value_lost_sar_mn: number; relationship_value_sar_mn: number; score: number; reasons: string[];
}
export interface Exits extends IntelEnvelope<ExitRow> { totals_by_action: Record<ExitAction, { names: number; capital: number; ecl: number }>; universe: number }

export type RwaStatus = "recognisable" | "after_action" | "to_confirm";
export interface RwaRow {
  facility_id: string; borrower_id: string; borrower_name: string; sector: string; rating: string; stage: number; category: string;
  category_label: string; status: RwaStatus; ead_sar_mn: number; rwa_now_sar_mn: number; rw_now: number; rwa_saving_sar_mn: number;
  capital_saving_sar_mn: number; detail: string;
}
export interface RwaCategory { category: string; label: string; status: RwaStatus; facilities: number; rwa_saving_sar_mn: number; capital_saving_sar_mn: number }
export interface Rwa extends IntelEnvelope<RwaRow> {
  by_category: RwaCategory[]; by_status: Record<RwaStatus, number>; rwa_total_sar_mn: number;
  at_risk: { rwa_sar_mn: number; capital_sar_mn: number; facilities: number };
}

export interface BridgeStep { key: string; label: string; value_sar_mn: number }
export interface MoverRow {
  facility_id: string; borrower_id: string; facilities: number; borrower_name: string; sector: string; rating: string; stage: number; ews_band: string;
  ews_reasons: string | null; ead_sar_mn: number; p_stage2: number; p_stage3: number; p_worse: number; ecl_now_sar_mn: number;
  ecl_if_moves_sar_mn: number; expected_increase_sar_mn: number;
}
export interface EclBridge extends IntelEnvelope<MoverRow> {
  bridge: BridgeStep[]; stage_ead_now: Record<"1" | "2" | "3", number>; stage_ead_next: Record<"1" | "2" | "3", number>;
  backtest: {
    from: string; to: string; error: Record<"2" | "3", number | null>; facilities: number;
    pooled: { quarters: string[]; inflow_error: Record<"2" | "3", number | null> };
  };
  overlay: { amount_sar_mn: number; components: { key: string; amount_sar_mn: number; why: string }[]; current_overlay_sar_mn: number; text: string; status: string };
  next_run: string;
  /** R14 G (ID gap 4): the base forecast under the §S calibrated scenarios (deal_desk.dd_scenario_result). */
  macro?: EclMacro;
}

export interface EclScenarioPath {
  severity: "mild" | "moderate" | "severe" | string; closing_sar_mn: number; delta_sar_mn: number; label?: string;
  stage2_share_start?: number | null; stage2_share_stressed?: number | null;
}
export interface EclMacro { source: string; scenarios: EclScenarioPath[]; window: string; fingerprint: string; engine_version: string; as_of?: string; note?: string }

export type WorkoutKey = "hold" | "reschedule" | "extra_collateral" | "partial_exit" | "sale" | "legal";
export interface WorkoutOption {
  key: WorkoutKey; label: string; recovery_npv_sar_mn: number; recovery_rate: number | null; ecl_after_sar_mn: number; ecl_change_sar_mn: number;
  rwa_after_sar_mn: number; capital_after_sar_mn: number; capital_change_sar_mn: number; stage_after: number | null;
  restructuring_number: number | null; net_value_sar_mn: number; notes: string[];
}
export interface WorkoutProfile {
  borrower_id: string; borrower_name: string; sector: string; rating: string; stage: number; ead_sar_mn: number; ecl_now_sar_mn: number;
  capital_now_sar_mn: number; collateral_net_sar_mn: number; restructurings_24m: number; deferrals_24m: number; utp: boolean; third_restructuring_next: boolean;
}
export interface Workout extends IntelEnvelope<WorkoutOption> { profile: WorkoutProfile; recommended: WorkoutKey; clauses: Record<string, string> }
export interface WorkoutCandidate { borrower_id: string; borrower_name: string; sector: string; ead_sar_mn: number; stage: number; rating: string; ews_band: string; restructurings_24m: number; third_restructuring_next: boolean }
export interface WorkoutCandidates { total: number; rows: WorkoutCandidate[]; headline: string }

// ---------------------------------------------------------------- URLs

export function toolPath(tool: PortfolioTool, opts: { level?: string; borrowerId?: string; limit?: number } = {}): string {
  const q = new URLSearchParams();
  if (opts.limit) q.set("limit", String(opts.limit));
  switch (tool) {
    case "headroom": if (opts.level) q.set("level", opts.level); return withQuery(`${INTEL_PORTFOLIO}/headroom`, q);
    case "exits": return withQuery(`${INTEL_PORTFOLIO}/exits`, q);
    case "rwa": return withQuery(`${INTEL_PORTFOLIO}/rwa`, q);
    case "ecl_bridge": return withQuery(`${INTEL_PORTFOLIO}/ecl-bridge`, q);
    case "workout": return opts.borrowerId ? `${INTEL_PORTFOLIO}/workout/${encodeURIComponent(opts.borrowerId)}` : withQuery(`${INTEL_PORTFOLIO}/workout`, q);
  }
}

function withQuery(p: string, q: URLSearchParams): string {
  const s = q.toString();
  return s ? `${p}?${s}` : p;
}

// ---------------------------------------------------------------- words (SAR million in)

export function sarM(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1000) return `${sign}SAR ${(a / 1000).toFixed(Math.max(dp, 1))}bn`;
  if (a > 0 && a < 1) return `${sign}SAR ${(a * 1000).toFixed(0)}k`;
  return `${sign}SAR ${a.toFixed(dp)}m`;
}

export function pctOf(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(dp)}%`;
}

export function signedSar(v: number): string {
  return `${v >= 0 ? "+" : "-"}${sarM(Math.abs(v))}`;
}

export const ACTION_LABEL: Record<ExitAction, string> = { not_renew: "Not renew", sell_down: "Sell down", reduce: "Reduce" };
export const STATUS_LABEL: Record<RwaStatus, string> = { recognisable: "Recognisable now", after_action: "After an action", to_confirm: "To confirm" };

export function kpiValue(k: IntelKpi): string {
  if (k.value === null || k.value === undefined) return "—";
  if (typeof k.value === "string") return k.value;
  if (k.unit.startsWith("SAR")) return sarM(k.value);
  if (k.unit === "share") return pctOf(k.value);
  if (k.unit === "bps") return `${k.value.toFixed(1)} bps`;
  if (k.unit === "x") return `${k.value.toFixed(1)}x`;
  if (k.unit === "count") return k.value.toLocaleString("en-US");
  return String(k.value);
}

// ---------------------------------------------------------------- bridge waterfall (pure)

export interface WaterfallBar { key: string; label: string; value: number; start: number; end: number; kind: "total" | "up" | "down" }

/** Floating bars for the bridge: totals from zero, steps from the running level. The last step must equal the sum. */
export function waterfall(steps: BridgeStep[]): WaterfallBar[] {
  let level = 0;
  return steps.map((s, i) => {
    const total = i === 0 || s.key === "closing";
    if (total) {
      level = s.value_sar_mn;
      return { key: s.key, label: s.label, value: s.value_sar_mn, start: 0, end: s.value_sar_mn, kind: "total" };
    }
    const start = level;
    level += s.value_sar_mn;
    return { key: s.key, label: s.label, value: s.value_sar_mn, start, end: level, kind: s.value_sar_mn >= 0 ? "up" : "down" };
  });
}

/** Bar geometry in % of the track width, scaled to the largest level; the axis starts at `floor` share of the min total. */
export function barGeometry(bars: WaterfallBar[]): { key: string; left: number; width: number }[] {
  const totals = bars.filter((b) => b.kind === "total").map((b) => b.end);
  const lo = totals.length ? Math.min(...totals) * 0.8 : 0;
  const hi = Math.max(...bars.map((b) => Math.max(b.start, b.end)), lo + 1e-9);
  const x = (v: number) => ((Math.max(v, lo) - lo) / (hi - lo)) * 100;
  return bars.map((b) => {
    const a = b.kind === "total" ? x(lo) : x(Math.min(b.start, b.end));
    const z = b.kind === "total" ? x(b.end) : x(Math.max(b.start, b.end));
    return { key: b.key, left: a, width: Math.max(z - a, 0.6) };
  });
}

/** Sum of a bridge's steps (opening + moves) against its closing: the bridge must add up. */
export function bridgeAddsUp(steps: BridgeStep[], tol = 1e-6): boolean {
  const close = steps.find((s) => s.key === "closing");
  if (!close) return false;
  const sum = steps.filter((s) => s.key !== "closing").reduce((a, s) => a + s.value_sar_mn, 0);
  return Math.abs(sum - close.value_sar_mn) <= tol * Math.max(1, Math.abs(close.value_sar_mn));
}

// ---------------------------------------------------------------- tones

export function bandTone(b: string | null | undefined): "negative" | "warning" | "neutral" {
  return b === "critical" || b === "high" ? "negative" : b === "moderate" ? "warning" : "neutral";
}

export function stageTone(s: number | null): "negative" | "warning" | "positive" | "neutral" {
  return s === 3 ? "negative" : s === 2 ? "warning" : s === 1 ? "positive" : "neutral";
}

/** "Open in Data Domains" for a lineage row (PLAN_R12 §0 rule 3). Parameters and assumptions have no Data Domains page. */
export function lineageHref(l: IntelLineage): string | null {
  if (l.domain === "deal_desk_parameters") return "/deal-desk/parameters";
  if (l.domain === "expert_assumptions") return null;
  const s = new URLSearchParams({ domain: l.domain, relation: l.relation });
  if (l.period !== null && l.period !== undefined) s.set("period", String(l.period));
  return `/data-builder?${s.toString()}`;
}
