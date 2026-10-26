/**
 * v5 Early Warning client.
 *
 * Talks ONLY to the Early Warning service (its own backend, port 8501 by
 * default, `NEXT_PUBLIC_EWS_API`). It never imports the Cockpit client or the
 * legacy `lib/api.ts`, so nothing here can reach or rewire the frozen Cockpit.
 * Amounts arrive in SAR million, as the books publish them.
 */
import { friendlyError } from "./errors.ts";
import * as React from "react";

export type DomainId = "corporate" | "retail";

export function ewsOrigin(): string {
  return (process.env.NEXT_PUBLIC_EWS_API ?? "http://127.0.0.1:8501").replace(/\/$/, "");
}

export class EwsError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${ewsOrigin()}/api/v1/ews${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
      credentials: "include",
    });
  } catch {
    throw new EwsError(0, `Early Warning is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Early Warning", response.status, body);
    throw new EwsError(response.status, message);
  }
  return body as T;
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") out.set(k, String(v));
  const s = out.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- types

export interface Counts {
  customers: number; customers_warned: number; high_or_critical: number; current_bad: number;
  forward_risk: number; critical: number; high: number; moderate: number; low: number;
  facilities: number; exposure: number; ecl: number; exposure_warned: number; exposure_severe: number;
  exposure_warned_pct: number; exposure_severe_pct: number; dpd_30_plus_pct: number;
  default_entries: number; default_eligible: number; odr_pct: number | null; warned_pct: number;
  triggers_fired: number;
  /** PLAN_R10 E1: EAD of exposures that are already bad, and its share of exposure (absent on older services). */
  exposure_bad?: number; exposure_bad_pct?: number;
  /** Warned customers by the data source whose rule fired (absent until the service publishes it). */
  by_source?: SourceShare[];
}
export type SourceKey = "bank_internal" | "bureau" | "open_banking";
export interface SourceShare { key: SourceKey | string; label: string; customers: number; share_pct: number | null }
/** One rating grade on a corporate level (absent until the service publishes it). */
export interface RatingMix { rating: string; borrowers: number; warned: number; high_or_critical: number; exposure: number }
export type Movement = Partial<Record<keyof Counts, number | null>>;
export interface TrendPoint {
  period: string; customers_warned: number | null; high_or_critical: number | null;
  current_bad: number | null; forward_risk: number | null; exposure_severe: number | null;
  exposure_warned_pct: number | null; odr_pct: number | null; warned_pct: number | null;
}
export interface Reason {
  key: string; reason: string; name: string; weight: number | null; family: string;
  family_label: string; layer: string; layer_name: string; customers: number; facilities: number;
  exposure: number; previous_customers: number | null; change: number | null;
}
export interface Card extends Counts {
  key: string; label: string; movement: Movement; trend: TrendPoint[]; top_reasons: Reason[];
  commentary: string; materiality?: { customers_pct: number; facilities_pct: number; exposure_pct: number };
  meaning?: string; derivation?: string;
}
export interface Labels {
  segment: string; segments: string; subsegment: string; subsegments: string; owner: string;
  owners: string; exposure: string; exposures: string; period: string; portfolio: string;
  classification?: string;
}
export interface Scope { segment?: string; classification?: string; subsegment?: string; level?: string | null }
export interface Ranking {
  key: string; label: string; rank: number; severe_share_of_book_pct: number; exposure_severe: number;
  warned_pct: number; warned_change: number | null; odr_pct: number | null; odr_change: number | null;
  materiality_pct: number;
}
export interface Level {
  domain_id: DomainId; release_id: string; ruleset: string; period: string; prior_period: string;
  periods: string[]; trend_periods: string[]; frequency: string; money_unit: string; scope: Scope;
  labels: Labels; name: string; breadcrumbs: { label: string; scope: Scope }[];
  headline: Counts; previous: Counts | null; movement: Movement; trend: TrendPoint[];
  top_reasons: Reason[]; commentary: string; children: Card[]; children_kind: string | null;
  classifications: Card[]; definitions: Record<string, string>;
  interpretation?: { headline: string; interpretation: string; ranking: Ranking[]; ranking_basis: string };
  rating_mix?: RatingMix[];
}
export interface ReasonRef { key: string; name: string; weight: number | null; layer: string; layer_name: string; family: string }
export interface CustomerRow {
  customer_id: string; customer_name: string | null; score: number; band: string; current_bad: boolean;
  forward_risk: boolean; facilities: number; exposure: number; ecl: number; dpd: number; stage: number;
  segments: string; subsegments: string; worst_exposure: string; share_of_scope_pct: number;
  reasons: ReasonRef[]; layers: string[];
  series: { period: string; score: number | null; dpd: number | null; exposure: number | null }[];
  [fact: string]: unknown;
}
export interface Customers {
  domain_id: DomainId; period: string; scope: Scope; labels: Labels; cohort: string;
  cohorts: { key: string; label: string; customers: number }[];
  filters: Record<string, string | number | null>; dpd_buckets: { key: string; label: string }[];
  layers: string[]; layer_labels: Record<string, string>; reasons: string[];
  total: number; total_exposure: number; limit: number; offset: number; customers: CustomerRow[];
  definitions: Record<string, string>; warned_min: number;
}
export interface RuleEval {
  id: string; name: string; weight: number; fired: boolean; condition: string;
  values: Record<string, unknown>; available: boolean; layer: string; layer_name: string;
  family: string; limitation: string;
}
export interface CustomerDetail {
  domain_id: DomainId; release_id: string; period: string; prior_period: string; labels: Labels;
  customer_id: string; customer_name: string | null; score: number; band: string;
  current_bad: boolean; forward_risk: boolean; exposure: number; ecl: number; facilities: number;
  facts: Record<string, unknown>; reasons: ReasonRef[];
  exposures: {
    exposure_id: string; segment: string; subsegment: string; product_type?: string | null;
    exposure: number; limit: number; ecl: number; utilisation_pct: number; dpd: number; stage: number;
    score: number; band: string; reasons: string[]; rules: RuleEval[];
  }[];
  history: { period: string; score: number; band: string; dpd: number; stage: number; exposure: number;
             ecl: number; facilities: number; bad: boolean; reasons: string[] }[];
  links: { borrower_360: string; early_warning: string };
  definitions: Record<string, string>; warned_min: number;
}
export interface Cohort {
  object_id: string; title: string; domain_id: DomainId; release_id: string; period: string;
  ruleset: string; membership_hash: string; counts: { customers: number; exposures: number };
  exposure: number; ecl: number; stage_mix: Record<string, { n: number; ead: number; ecl: number }>;
  customer_ids: string[]; request: Record<string, unknown>;
  receiver: { module: string; status: string; note: string }; created_at: number;
}
export interface Meta {
  domain_id: DomainId; release_id: string; ruleset: string; periods: string[]; as_of: string;
  labels: Labels; frequency: string; segments: string[];
  classifications: { key: string; label: string }[]; definitions: Record<string, string>;
}

// ---------------------------------------------------------------- calls

export interface ScopeQuery { domain: DomainId; period?: string; segment?: string; classification?: string; subsegment?: string }

/** R7 (C3.3): the CBUAE CRM compliance card on the Early Warning home. */
export interface CrmArticle { article: string; title: string; breaches: number; ead_sar_mn: number; ecl_sar_mn: number; shortfall_sar_mn: number; note?: string }
export interface CrmBreach {
  check_id: string; article: string; title: string; book: string; period: string; entity_type: string;
  entity_id: string; borrower_id: string; measured: number | string; required: number | string; unit: string;
  ead_sar_mn: number; ecl_sar_mn: number; shortfall_sar_mn: number; severity: "high" | "medium" | "low"; detail: string;
}
export interface CrmCheckRow {
  check_id: string; article: string; title: string; rule: string; book: string; period: string; status: string;
  tested: number; breaches: number; ead_sar_mn: number; ecl_sar_mn: number; shortfall_sar_mn: number; severity: string;
}
export interface Crm {
  domain: DomainId; period: string; document: string; href: string; breaches: number; checks: number;
  checks_in_breach: number; high: number; ead_sar_mn: number; ecl_sar_mn: number; shortfall_sar_mn: number;
  by_article: CrmArticle[]; check_rows: CrmCheckRow[]; top: CrmBreach[];
  not_checked: { article: string; rule: string; why: string }[]; ask: string;
}

/** R16 m (M2): the segment analysis behind an Early Warning card (GET /segment-analysis). Amounts in SAR million. */
export interface SegmentDriver {
  key: string; label: string; layer: string; layer_label: string; owners: number; exposures: number; ead: number;
  prior_owners: number | null; prior_ead: number | null; change: number | null; ead_change: number | null;
  share_of_warned_owners_pct: number; share_of_warned_ead_pct: number; rules: string[];
}
export interface SegmentRule {
  id: string; label: string; weight: number | null; family: string; family_label: string; layer_label: string;
  source_label: string; owners: number; exposures: number; ead: number; prior_owners: number | null;
  change: number | null; share_of_warned_owners_pct: number; share_of_warned_ead_pct: number;
}
export interface SegmentName {
  rank: number; customer_id: string; customer_name: string | null; score: number; band: string; stage: number;
  dpd: number; exposure: number; ecl: number; facilities: number; current_bad: boolean; main_reasons: string[];
  reasons_count: number; links: { borrower_360: string; early_warning: string };
}
export interface SegmentStage { stage: number; n: number; ead: number; ecl: number }
export interface SegmentAction { key: string; title: string; why: string; owner_role: string; rule: string }
export interface SegmentAnalysis {
  domain_id: DomainId; release_id: string; ruleset: string; period: string; prior_period: string;
  scope: Scope & { dims?: Record<string, string> }; labels: Labels; name: string; key: string;
  plain_words: string[];
  headline: Counts & {
    warned_exposures: number; warned_ead: number; prior_warned_ead: number | null;
    movement: Record<string, number | null>; previous: Record<string, number> | null;
  };
  drivers: SegmentDriver[]; rules: SegmentRule[]; top_names: SegmentName[];
  ecl: {
    stage_mix: SegmentStage[]; stage_mix_warned: SegmentStage[]; ecl_now: number; ead_now: number; coverage_pct: number;
    flagged_names: number; flagged_ead: number; current_ecl: number; ecl_if_defaulted: number; expected_ecl: number;
    uplift: number; uplift_pct: number; severe_ecl: number; severe_uplift: number; ecl_if_true_total: number;
    by_bucket?: { bucket: string; label: string; pd_pct: number; names: number; ead: number; current_ecl: number;
                  expected_ecl: number; uplift: number }[];
    pd_version: number | null; engine: string; engine_call: string; method: string;
  };
  actions: SegmentAction[]; stress: Record<string, unknown>;
  sources: { relations: string[]; headline: string; drivers: string; rules: string; top_names: string; ecl: string };
  definitions?: Record<string, string>;
}

export const ews = {
  segmentAnalysis: (q: ScopeQuery & { dims?: Record<string, string> }) =>
    request<SegmentAnalysis>(`/segment-analysis${qs({ ...q, dims: q.dims && Object.keys(q.dims).length ? JSON.stringify(q.dims) : undefined })}`),
  meta: (domain: DomainId) => request<Meta>(`/meta${qs({ domain })}`),
  crm: (domain: DomainId) => request<Crm>(`/crm${qs({ domain })}`),
  level: (q: ScopeQuery) => request<Level>(`/level${qs({ ...q })}`),
  customers: (q: ScopeQuery & { cohort?: string; reason?: string; layer?: string; dpd?: string;
                                stage?: string; band_min?: string; search?: string; limit?: number;
                                offset?: number }) =>
    request<Customers>(`/customers${qs({ ...q })}`),
  customer: (domain: DomainId, id: string, period?: string) =>
    request<CustomerDetail>(`/customers/${encodeURIComponent(id)}${qs({ domain, period })}`),
  exportCohort: (body: Record<string, unknown>) =>
    request<Cohort>(`/export`, { method: "POST", body: JSON.stringify(body) }),
  cohort: (id: string) => request<Cohort>(`/cohorts/${encodeURIComponent(id)}`),
};

export interface ExcelParams {
  domain: DomainId; period?: string; segment?: string; classification?: string; subsegment?: string;
  cohort?: string; reason?: string; layer?: string; dpd?: string; stage?: string | number;
  band_min?: string; search?: string; customer_id?: string;
}

/** The service's Excel workbook for a view (GET, empty parameters left out). */
export function excelHref(params: ExcelParams): string {
  return `${ewsOrigin()}/api/v1/ews/export.xlsx${qs({ ...params })}`;
}

/** Load once per key; keeps the service's own error text. */
export function useEws<T>(load: () => Promise<T>, key: string) {
  // Results are stored WITH the key they answer, so a view whose key has
  // changed reads as loading until its own answer arrives -- no state is set
  // synchronously inside the effect.
  const [state, setState] = React.useState<{ key: string | null; data: T | null; error: string | null }>(
    { key: null, data: null, error: null });
  const ref = React.useRef(load);
  React.useEffect(() => { ref.current = load; });
  React.useEffect(() => {
    let live = true;
    ref.current().then(
      (data) => { if (live) setState({ key, data, error: null }); },
      (err: unknown) => { if (live) setState({ key, data: null, error: err instanceof Error ? err.message : String(err) }); },
    );
    return () => { live = false; };
  }, [key]);
  const current = state.key === key;
  return { data: current ? state.data : null, error: current ? state.error : null, loading: !current };
}

// ---------------------------------------------------------------- words

/** "SAR 171m", "SAR 2.60m", "SAR 23.3bn", "SAR 845k". Input in SAR million. */
export function sar(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || !Number.isFinite(valueInMillions)) return "—";
  const v = Number(valueInMillions);
  if (v === 0) return "SAR 0";
  const abs = Math.abs(v);
  const [scaled, suffix] = abs >= 1000 ? [v / 1000, "bn"] : abs >= 1 ? [v, "m"] : abs >= 0.001 ? [v * 1000, "k"] : [v * 1e6, ""];
  const a = Math.abs(scaled);
  const decimals = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return `SAR ${scaled.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`;
}

export function count(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US");
}

export function pct(v: number | null | undefined, places = 1): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : `${Number(v).toFixed(places)}%`;
}

export function signed(v: number | null | undefined, places = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places })}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026Q2" -> "Q2 2026 (30 Jun 2026)"; "2026-08" -> "Aug 2026 (31 Aug 2026)". */
export function asOfLabel(period: string): string {
  const q = /^(\d{4})Q([1-4])$/.exec(period);
  if (q) {
    const month = Number(q[2]) * 3;
    const day = new Date(Date.UTC(Number(q[1]), month, 0)).getUTCDate();
    return `Q${q[2]} ${q[1]} (${day} ${MONTHS[month - 1]} ${q[1]})`;
  }
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  if (m) {
    const day = new Date(Date.UTC(Number(m[1]), Number(m[2]), 0)).getUTCDate();
    return `${MONTHS[Number(m[2]) - 1]} ${m[1]} (${day} ${MONTHS[Number(m[2]) - 1]} ${m[1]})`;
  }
  return period;
}

/** Short axis label: "Q2 26" / "Aug 26". */
export function shortPeriod(period: string): string {
  const q = /^(\d{4})Q([1-4])$/.exec(period);
  if (q) return `Q${q[2]} ${q[1].slice(2)}`;
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1].slice(2)}` : period;
}

export const BAND_ORDER = ["critical", "high", "moderate", "low", "none"] as const;
