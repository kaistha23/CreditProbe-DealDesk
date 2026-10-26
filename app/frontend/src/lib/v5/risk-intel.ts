/**
 * PLAN_R9 Session C client: P3 ECL of warnings, P4 Accepted Risk Watch, P6 ECL diagnostics.
 * Served by the Early Warning service under /api/v1/ews/intel. Amounts arrive in SAR million.
 */
import { friendlyError } from "./errors.ts";
import { ewsOrigin, type DomainId } from "./ews";

export type Bucket = "critical" | "high" | "moderate" | "low";

export interface PoweredByInfo { pack: string; rule_id?: string; article?: string; confidence?: string; trace?: string }

export interface PdConfig {
  values: Record<Bucket, number>; basis: string; version: number; updated_by: string; updated_at: string | null;
  history?: { version: number; values: Record<Bucket, number>; updated_by: string | null; updated_at: string | null }[];
}

export interface ImpactAgg {
  names: number; exposures: number; ead: number; current_ecl: number; ecl_if_defaulted: number; expected_ecl: number;
  uplift: number; severe_ecl: number; severe_uplift: number;
}
export interface Impact {
  domain: DomainId; period: string; segment: string | null; unit: string; pd_by_bucket: PdConfig; total: ImpactAgg;
  by_bucket: (ImpactAgg & { bucket: Bucket; label: string; pd_pct: number })[];
  by_segment: (ImpactAgg & { segment: string; by_bucket: Record<Bucket, number> })[];
  top_contributors: { owner: string; owner_name: string; segment: string; bucket: Bucket; ead: number; current_ecl: number;
                      ecl_if_defaulted: number; expected_ecl: number; uplift: number; stage: number; dpd: number; reasons: string }[];
  book: { ead: number; ecl: number }; labels: { segment: string; names: string }; method: string; powered_by: PoweredByInfo;
}

export interface WatchItem {
  item_id: string; watch_id: string; trigger: string; metric: string; due_date: string; frequency: string;
  status: "on track" | "due" | "missed"; critical: boolean; article: string; evidence: string;
}
export interface WatchClient {
  watch_id: string; obligor_id: string; source: string; name: string; group_name?: string; sector: string; rating?: string;
  tier: number; currency: string; exposure_sar_mn: number; exposure_ccy_mn?: number; ecl_sar_mn: number; ecl_stage2_sar_mn: number;
  stage: number; approved_on: string; approved_by: string; no_sicr_rationale: string; items: WatchItem[];
  escalation: { escalate: boolean; why: string; missed: number; due: number; action: string };
}
export interface WatchView {
  as_of: string; names: number; exposure: number; ecl: number; escalations: number; rule: string; currency_note: string;
  tiers: { tier: number; names: number; exposure: number; ecl: number; ecl_stage2: number; escalate: number }[];
  tier1_stage2: { current_ecl: number; stage2_ecl: number; uplift: number };
  items: { total: number; on_track: number; due: number; missed: number };
  clients: WatchClient[]; powered_by: PoweredByInfo;
}

export interface WaterfallBar { key: string; label: string; info: string; value: number; exposures: number;
  top_clients: { obligor_id: string; name: string; value: number }[] }
export interface Waterfall { book: string; prior_run: string; current_run: string; opening: number; closing: number; change: number;
  bars: WaterfallBar[]; residual: number; source: string; method: string; powered_by: PoweredByInfo }
export interface Anomalies { book: string; run: string; verdict: string; why: string; input_errors: number;
  data_quality: number; planted_listed: number; planted_found: number; total_ecl: number; source: string;
  checks: { key: string; label: string; rule: string; count: number; input_error: boolean; ecl_at_stake: number; ead: number }[];
  rows: { check: string; label: string; exposure_id: string; obligor_id: string; name: string; stage: number; dpd_days: number;
          ead: number; ecl: number; prior: number | null; current: number | null; field: string; planted: boolean }[]; powered_by: PoweredByInfo }
export interface Coverage { book: string; run: string; crwa: number; stage12_ecl: number; required_9_21: number;
  coverage_pct_of_crwa: number | null; shortfall_9_21: number; meets_9_21: boolean; total_shortfall: number; crwa_source: string;
  stage3: { breaches: number; shortfall: number; stage3_ecl: number; stage3_ead: number; article?: string; error?: string;
            top: { entity_id: string; borrower_id: string; ecl: number; floor: number; shortfall: number }[] };
  powered_by: PoweredByInfo }
export interface Shocks { book: string; run: string; shock: { pd_pct: number; lgd_pp: number; macro_pct: number };
  base_ecl: number; shocked_ecl: number; delta: number; method: string;
  by_stage: { stage: number; ecl_sar_mn: number; shocked: number }[];
  by_sector: { sector: string; ecl_sar_mn: number; shocked: number; delta: number }[];
  top_movers: { obligor_id: string; name: string; ecl_sar_mn: number; shocked: number; delta: number; ead_sar_mn: number }[];
  powered_by: PoweredByInfo }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${ewsOrigin()}/api/v1/ews/intel${path}`, {
      ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store", credentials: "include",
    });
  } catch {
    throw new Error("The intelligence service is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(friendlyError("Early Warning", response.status, body));
  return body as T;
}

function qs(p: Record<string, string | number | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const intel = {
  pd: () => request<PdConfig>("/pd-by-bucket"),
  setPd: (values: Record<Bucket, number>) => request<PdConfig>("/pd-by-bucket", { method: "PUT", body: JSON.stringify({ values }) }),
  impact: (domain: DomainId, period?: string, segment?: string) => request<Impact>(`/ecl-impact${qs({ domain, period, segment })}`),
  watch: () => request<WatchView>("/watch"),
  action: (body: Record<string, unknown>) => request<{ kind: string; added: number; obligor_ids: string[] }>("/actions", { method: "POST", body: JSON.stringify(body) }),
  waterfall: (book = "corporate") => request<Waterfall>(`/diagnostics/waterfall${qs({ book })}`),
  anomalies: (book = "corporate") => request<Anomalies>(`/diagnostics/anomalies${qs({ book })}`),
  coverage: (book = "corporate") => request<Coverage>(`/diagnostics/coverage${qs({ book })}`),
  shocks: (book: string, pd: number, lgd: number, macro: number) => request<Shocks>(`/diagnostics/shocks${qs({ book, pd, lgd, macro })}`),
  memoHref: (domain: DomainId, period?: string) => `${ewsOrigin()}/api/v1/ews/intel/memo.docx${qs({ domain, period })}`,
};

export const BUCKETS: Bucket[] = ["critical", "high", "moderate", "low"];
export const BUCKET_LABEL: Record<Bucket, string> = { critical: "Critical", high: "High", moderate: "Medium", low: "Low" };
export const BUCKET_COLOR: Record<Bucket, string> = {
  critical: "var(--ipm-negative)", high: "var(--ipm-warning)", moderate: "var(--ipm-chart-3)", low: "var(--ipm-text-muted)",
};
