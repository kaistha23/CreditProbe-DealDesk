/**
 * R13 IB (PLAN_R13 §I): renewal autopilot, covenant designer, who to call today — the response contracts and the pure
 * helpers the three compact panels use. Pure (no React, no "@/" imports) so `node --test` covers it.
 *
 * Every figure the engines return is `Sourced`: its value and where it comes from (domain, relation, key, column, period),
 * or, for a computed figure, the method and its inputs.
 */

export interface Source {
  domain: string; relation: string; key?: Record<string, unknown>; column?: string; period?: string | null; method?: string;
  inputs?: Source[];
}
export interface Sourced<T = number | string | null> { value: T; source: Source; unit?: string; label?: string }

// ------------------------------------------------------------------ renewal autopilot

export type RenewalClass = "clean" | "exception";
export interface Criterion { id: string; label: string; op: string; threshold: number; source: string; kind: "credit" | "commercial" }
export interface RenewalRow {
  facility_id: string; borrower_id: string; borrower_name: string; sector: string; product: string; renewal_date: string;
  days_to_renewal: number; ead_sar_mn: number; limit_sar_mn: number; stage: number | null; rating_now: string | null; ews_band: string | null;
  classification: RenewalClass; fired: string[]; commercial: string[]; line: string; proposal_id: string | null; output: string;
}
export interface RenewalQueue {
  window_days: number; ref_date: string; as_of: string; summary: string; counts: Record<RenewalClass, number>;
  ead_sar_mn: Record<RenewalClass, number>; total: number; by_criterion: Record<string, number>; criteria: Criterion[];
  rows: RenewalRow[]; offset: number; limit: number; pending: string[]; data_limits: string[]; sectors: string[];
  /** R14 G: material renewals by default (relationship EAD at or above the J9 floor, as the landing's Renewals counter). */
  scope?: "material" | "all"; materiality_floor_sar_mn?: number; names?: number; whole_book_total?: number; whole_book_ead_sar_mn?: number;
}
export interface Block { t: string; text?: string; items?: string[]; header?: string[]; rows?: (string | number)[][]; source?: string }
export interface RenewalNote { title: string; recommendation: string; sections: { key: string; heading: string; blocks: Block[] }[]; markdown: string; pages: number }
export interface CriterionResult { id: string; label: string; op: string; threshold: number; value: number | null; fired: boolean; known: boolean; reads: string; kind: string }
export interface RenewalItem {
  classification: RenewalClass;
  review: { facility_id: string; borrower_name: string; criteria: CriterionResult[]; data_limits: string[]; fired: string[]; commercial: string[];
    proposal_id: string | null; as_of_quarter: string };
  note?: RenewalNote;
  paper?: { available: boolean; proposal_id: string | null; text: string };
}
export interface RenewalPaper {
  facility_id: string; proposal_id: string | null; opened_file?: boolean; why?: string;
  paper: { title: string; sections: { key: string; heading: string }[] } | null;
  links?: { bank_form: string; docx: string; pdf: string; committee_paper: string; deal: string };
  fired?: { id: string; label: string }[];
}

export function renewalQuery(p: { days?: number; cls?: "all" | RenewalClass; q?: string; sector?: string; limit?: number; offset?: number; scope?: "material" | "all" }): string {
  const s = new URLSearchParams({ days: String(p.days ?? 90), cls: p.cls ?? "all", limit: String(p.limit ?? 25), offset: String(p.offset ?? 0) });
  if (p.scope) s.set("scope", p.scope);
  if (p.q) s.set("q", p.q);
  if (p.sector) s.set("sector", p.sector);
  return `?${s.toString()}`;
}

/** The criteria that fired, most common first in the window (for the chip row). */
export function topCriteria(q: Pick<RenewalQueue, "by_criterion" | "criteria">, n = 4): { id: string; label: string; count: number }[] {
  return q.criteria.filter((c) => c.kind === "credit" && (q.by_criterion[c.id] ?? 0) > 0)
    .map((c) => ({ id: c.id, label: c.label, count: q.by_criterion[c.id] ?? 0 }))
    .sort((a, b) => b.count - a.count || a.id.localeCompare(b.id)).slice(0, n);
}

export const OP_WORDS: Record<string, string> = { ">": "above", ">=": "at or above", "<": "below", "<=": "at or below", "=": "equal to" };

/** "Covenant headroom below 10%: 4.2" — one fired criterion as a line. */
export function criterionLine(c: CriterionResult): string {
  const v = c.value == null ? "n/a" : Number.isInteger(c.value) ? String(c.value) : c.value.toFixed(2);
  return `${c.label}: ${v} (exception if ${OP_WORDS[c.op] ?? c.op} ${c.threshold})`;
}

// ------------------------------------------------------------------ covenant designer

export interface CovenantStats {
  threshold: number; events: number; detected: number; hit_rate: number | null; early_hit_rate: number | null; on_time_rate: number | null;
  median_lead_q: number | null; false_alarm_rate: number | null; precision: number | null; deal_headroom_pct?: number | null; lead_on_target?: boolean;
  /** R14 G (K32): set at exactly the minimum headroom because no book level left the cushion; clipped to the bounds. */
  set_by_headroom?: boolean; bounded?: boolean;
}
export interface CovenantFinding { covenant: string; kind: "template_too_tight" | "template_too_loose"; severity: string; title: string; text: string }
export interface TradePoint { threshold: number; headroom_pct: number | null; early_hit_rate: number | null; false_alarm_rate: number | null }
export interface CovenantRow {
  covenant: string; label: string; direction: "min" | "max"; unit: string; current: Sourced<number> | null; proposed: CovenantStats;
  template: CovenantStats | null; template_source: string; as_set: (CovenantStats & { borrowers_with_covenant: number; median_threshold: number }) | null;
  recommended: boolean; already_breached: boolean; why_not?: string | null; text: string; grid?: CovenantStats[];
  /** R14 G (K32): one verdict; "beats template" only against a meaningful template; the trade-off and the bounds. */
  verdict?: "Recommend" | "Not recommended"; beats_template?: boolean; template_meaningful?: boolean;
  statistical_best?: CovenantStats; trade_off?: TradePoint[]; trade_off_line?: string; bounds?: { low: number; high: number };
}
export interface CovenantDesign {
  deal: string; name: string; sector: string | null; population: string; events: number; summary: string;
  method: { window_quarters: number; horizon_quarters: number; max_false_alarm: number; target_lead: string; objective: string };
  covenants: CovenantRow[]; data_limits: string[];
  /** R14 G (K32) */
  min_headroom_pct?: number; coverage_note?: string; findings?: CovenantFinding[];
}

export function threshold(v: number | null | undefined, unit: string): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return unit === "%" ? `${v.toFixed(0)}%` : `${v.toFixed(2)}x`;
}
export function rate(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${Math.round(v * 100)}%`;
}
/** Better/worse than the template on the trade-off the designer optimises (early hits − false alarms). */
export function versusTemplate(r: CovenantRow): "better" | "worse" | "same" | "no template" {
  if (!r.template || r.template.early_hit_rate == null || r.template.false_alarm_rate == null) return "no template";
  const a = (r.proposed.early_hit_rate ?? 0) - (r.proposed.false_alarm_rate ?? 0);
  const b = r.template.early_hit_rate - r.template.false_alarm_rate;
  return Math.abs(a - b) < 0.005 ? "same" : a > b ? "better" : "worse";
}

// ------------------------------------------------------------------ who to call today

export type Urgency = "today" | "this week" | "next week";
export interface CallSignal { id: string; label: string; weight: number; value: Sourced<number | string>; text: string }
export interface CallRow {
  rank: number; borrower_id: string; borrower_name: string; sector: string; source: string; proposal_id: string | null; top_facility: string | null;
  ead_sar_mn: Sourced<number>; materiality_sar_mn: Sourced<number>; weight: number; urgency: Urgency; call_by: string;
  signals: CallSignal[]; reason: string; action: string; open: string;
}
export interface CallList {
  summary: string; total: number; today: number; this_week: number; rows: CallRow[]; by_signal: Record<string, number>;
  signals: { id: string; label: string; weight: number; action: string }[]; method: string; data_limits: string[];
  offset: number; limit: number; as_of: { book: string; conduct: string; bureau: string };
  /** R14 G: material names by default (relationship EAD at or above the J9 floor); scope=all is the RM-level list. */
  scope?: "material" | "all"; materiality_floor_sar_mn?: number; whole_book_total?: number; below_floor?: number; material_ead_sar_mn?: number;
}

export function callsQuery(p: { limit?: number; offset?: number; signal?: string; sector?: string; minWeight?: number; scope?: "material" | "all" }): string {
  const s = new URLSearchParams({ limit: String(p.limit ?? 25), offset: String(p.offset ?? 0) });
  if (p.scope) s.set("scope", p.scope);
  if (p.signal) s.set("signal", p.signal);
  if (p.sector) s.set("sector", p.sector);
  if (p.minWeight) s.set("min_weight", String(p.minWeight));
  return `?${s.toString()}`;
}

export const urgencyTone = (u: Urgency): "negative" | "warning" | "neutral" => (u === "today" ? "negative" : u === "this week" ? "warning" : "neutral");

/** Signal chips for the filter row: the signals that fired on someone, strongest first. */
export function signalChips(c: Pick<CallList, "signals" | "by_signal">, n = 6): { id: string; label: string; count: number }[] {
  return c.signals.filter((s) => (c.by_signal[s.id] ?? 0) > 0)
    .sort((a, b) => b.weight - a.weight || (c.by_signal[b.id] ?? 0) - (c.by_signal[a.id] ?? 0))
    .slice(0, n).map((s) => ({ id: s.id, label: s.label, count: c.by_signal[s.id] ?? 0 }));
}

/** "ews.corp_exposure · ews_band · 2026Q2" — a source as a one-line tooltip. */
export function sourceLine(s: Source | undefined): string {
  if (!s) return "";
  if (s.domain === "computed") return `Computed: ${s.method ?? ""}`;
  return [`${s.domain}.${s.relation}`, s.column, s.period].filter(Boolean).join(" · ");
}
