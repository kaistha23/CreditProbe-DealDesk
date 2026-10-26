/**
 * PLAN_R12 Session I: the Book's API client (prefix /api/v1/dealdesk/book). Every figure comes from Data Domains
 * relations through the Deal Desk service; the client only fetches and posts.
 */

import { dealdeskOrigin } from "@/lib/v5/dealdesk";

export const BOOK = "/api/v1/dealdesk/book";

export type BookFilter = "all" | "going_bad" | "repricing" | "promises_unmet" | "tier_high" | "renewals_due" | "conditions_due"
  | "material_going_bad" | "material_renewals";
export type Tier = "High" | "Medium" | "Standard";

export const FILTERS: { key: BookFilter; label: string; info: string }[] = [
  { key: "all", label: "All facilities", info: "Every live corporate facility at the book's as-of, with its origination record." },
  { key: "going_bad", label: "Going bad", info: "RAROC drifted below hurdle, downgraded two notches or more, Early Warning high or critical, a monitoring trigger hit, or an approval-condition promise unmet. Defaulted names are in workout and not listed." },
  { key: "repricing", label: "Repricing list", info: "Below hurdle now and up for renewal in 3–6 months, ranked by the RAROC the reprice or restructure recovers." },
  { key: "promises_unmet", label: "Promises unmet", info: "Routing undertakings and approval-condition commitments delivered below 80%, measured on the deposits data." },
  { key: "tier_high", label: "Tier High", info: "Facilities on High monitoring (quarterly review, tighter Early Warning thresholds)." },
  { key: "renewals_due", label: "Renewals due", info: "Annual review or maturity in the next 90 days." },
  { key: "conditions_due", label: "Covenants and conditions", info: "Covenants in breach at the last test, or approval conditions due this month." },
  // R13 X (J9): the landing counters' lists: material names only (tier High, or relationship EAD above the materiality floor with
  // Early Warning high or critical or RAROC below hurdle by the drift gap; renewals in 90 days above the floor).
  { key: "material_going_bad", label: "Material going bad", info: "Tier High, or relationship EAD above the materiality floor with Early Warning high or critical or RAROC drifted below hurdle by the drift gap (Deal Desk Parameters)." },
  { key: "material_renewals", label: "Material renewals", info: "Renewals and reviews in the next 90 days on names whose relationship EAD is above the materiality floor." },
];

export interface BookRow {
  facility_id: string; source: "book" | "deal_desk"; borrower_id: string; borrower_name: string; sector: string; product_type: string;
  limit_sar_mn: number; ead_sar_mn: number; orig_date: string; orig_rating: string; rating_now: string | null; notches: number | null;
  stage: number; tier: string; tier_set: boolean; plan_reason: string | null; plan_set_by: string | null; plan_set_on: string | null;
  hurdle: number | null; raroc_orig: number | null; raroc_now: number | null; drift: number | null;
  d_pd_migration: number; d_lgd: number; d_funding: number; d_fees: number; d_utilisation: number; d_cross_sell: number; main_driver: string;
  ews_band: string; ews_score: number; ews_reasons: string | null; watch_status: string | null;
  covenants: number; covenants_breached: number; covenant_min_headroom_pct: number | null; covenant_next_test: string;
  conditions_open: number; conditions_due: number; conditions_overdue: number;
  promise_status: string | null; promise_realisation: number | null;
  renewal_date: string; renewal_kind: string; months_to_renewal: number;
  going_bad: boolean; defaulted: boolean; on_repricing_list: boolean;
  recoverable_raroc: number; recoverable_sva_sar_mn: number; action: string; action_text: string;
  new_margin_bps: number | null; margin_change_bps: number | null; renewal_fee_bps: number; extra_collateral_sar_mn: number;
  proposal_id: string | null; reasons: string[];
}

export interface Source { key: string; domain: string; relation: string; path: string; rows: number | null }
export interface Trace { domain: string; relation: string; key: Record<string, string | number | null>; period?: string | null; column?: string }

/** "Open in Data Domains": the relation filtered to the row a figure comes from (PLAN_R12 §0 rule 3). */
export function dataDomainsHref(t: { domain: string; relation: string; key?: Record<string, unknown>; period?: string | null }): string {
  const s = new URLSearchParams({ domain: t.domain, relation: t.relation });
  if (t.period) s.set("period", String(t.period));
  const first = Object.entries(t.key ?? {}).find(([k]) => k !== "reporting_quarter" && k !== "run_id");
  if (first && first[1] != null) s.set("q", String(first[1]));
  return `/data-builder?${s.toString()}`;
}

export interface BookList {
  filter: BookFilter; total: number; ead_sar_mn: number; offset: number; limit: number; rows: BookRow[];
  as_of: string; ref_date: string; pending: string[]; sectors: string[]; sources: Source[];
}

export interface BookCounts {
  all: number; going_bad: number; repricing: number; promises_unmet: number; tier_high: number; renewals_due: number; conditions_due: number;
  material_going_bad: number; material_renewals: number; material_going_bad_names?: number; material_renewals_names?: number;
  going_bad_ead_sar_mn: number; going_bad_by_reason: Record<string, number>; renewals_due_repricing: number; defaulted: number;
  as_of: string; pending: string[];
}

export interface Promise_ {
  promise_id: string; kind: string; obligor_id: string; facility_id: string | null; proposal_id: string | null; condition_id: string | null;
  description: string; promised_value: number | null; measured_value: number | null; realisation: number | null; unit: string;
  status: string; period: string; source: string;
}

export interface Optimiser {
  proposal_id: string; available: boolean; feasible?: boolean; why?: string; label?: string; lifetime_raroc?: number; sva?: number;
  changes?: { field: string; ask: number | string | null; value: number | string | null; unit?: string }[];
  terms?: Record<string, number | null>; relaxation?: { lever: string; label?: string; from?: number; to?: number }[];
}

export interface FacilityDetail {
  facility: BookRow;
  waterfall: { step: string; value: number; source?: Trace }[];
  inputs: Record<string, number>;
  promises: Promise_[];
  covenants: { covenant_id: string; covenant_type: string; threshold_value: number; observed_value: number; headroom_pct: number; test_status: string }[];
  plan_history: Record<string, unknown>[];
  repricing: { action: string; text: string; new_margin_bps: number | null; margin_change_bps: number | null; renewal_fee_bps: number;
    extra_collateral_sar_mn: number; recoverable_raroc: number; recoverable_sva_sar_mn: number | null; method: string; optimiser: Optimiser | null };
  pending: string[]; sources: Source[]; source: string; drift_source: string;
}

export interface Cut { group: string; ead_sar_mn: number; facilities_count: number; raroc_orig: number; raroc_now: number; hurdle: number;
  share_above_orig: number; share_above_now: number; drift: number; pd_migration: number; lgd: number; funding: number; fees: number;
  utilisation: number; cross_sell: number }

export interface Drift {
  as_of: string; ref_date: string; facilities: number; ead_sar_mn: number; defaulted_count: number; defaulted_ead_sar_mn: number;
  share_above_hurdle_orig: number; share_above_hurdle_now: number; median_raroc_orig: number; median_raroc_now: number; drift: number;
  mean_raroc_orig: number; mean_raroc_now: number;
  attribution: { component: string; label: string; value: number }[];
  by_sector: Cut[]; by_rating: Cut[]; by_vintage: Cut[]; by_product: Cut[]; by_rm?: Cut[]; rm_basis?: string;
  decayed_count: number; decayed_ead_sar_mn: number; summary: string; sources: Source[]; method: string; source?: string;
}

export interface HurdleSector { sector: string; facilities: number; ead_sar_mn: number; pd_migration_drift_pa: number; current_hurdle: number;
  proposed_hurdle: number | null; uplift: number; share_below_hurdle_now: number; text: string }
export interface HurdleProposal { id: string; sector: string; current_hurdle: number; proposed_hurdle: number; evidence: string; maker: string;
  reason: string; proposed_at: string; status: string; checker?: string; decided_at?: string; note?: string; returns_version?: string }
export interface Feedback {
  hurdles: { sectors: HurdleSector[]; proposals: HurdleProposal[]; method: string };
  realisation: { basis: string; flat: number; actual: number | null; promises: number; by_kind: Record<string, number>; in_use: number; min_promises: number };
  ratchet: { lever: string; max_bps_per_notch: number; text: string };
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${dealdeskOrigin()}${BOOK}${path}`, {
    credentials: "include", cache: "no-store", ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...(init.headers ?? {}) } : init?.headers,
  });
  if (!r.ok) {
    let msg = "The Book is temporarily unavailable.";
    try { const j = (await r.json()) as { detail?: unknown }; if (typeof j.detail === "string") msg = j.detail; } catch { /* keep the default */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

export const bookApi = {
  list: (p: { filter: BookFilter; q?: string; sector?: string; tier?: string; limit?: number; offset?: number }) => {
    const s = new URLSearchParams({ filter: p.filter, limit: String(p.limit ?? 50), offset: String(p.offset ?? 0) });
    if (p.q) s.set("q", p.q);
    if (p.sector) s.set("sector", p.sector);
    if (p.tier) s.set("tier", p.tier);
    return call<BookList>(`?${s.toString()}`);
  },
  counts: () => call<BookCounts>("/counts"),
  facility: (fid: string) => call<FacilityDetail>(`/facility/${encodeURIComponent(fid)}`),
  drift: () => call<Drift>("/drift"),
  feedback: () => call<Feedback>("/feedback"),
  setTier: (fid: string, tier: Tier, reason: string) =>
    call<{ text: string }>(`/facility/${encodeURIComponent(fid)}/tier`, { method: "POST", body: JSON.stringify({ tier, reason }) }),
  sendToEws: (fid: string, reason: string) =>
    call<{ text: string; ews_url: string }>(`/facility/${encodeURIComponent(fid)}/ews`, { method: "POST", body: JSON.stringify({ reason }) }),
  startRenewal: (fid: string, note = "") =>
    call<{ text: string; url: string }>(`/facility/${encodeURIComponent(fid)}/renewal`, { method: "POST", body: JSON.stringify({ note }) }),
  proposeHurdle: (sector: string, hurdle: number, reason: string) =>
    call<HurdleProposal>("/feedback/hurdles", { method: "POST", body: JSON.stringify({ sector, hurdle, reason }) }),
  decideHurdle: (id: string, approve: boolean, note = "") =>
    call<HurdleProposal>(`/feedback/hurdles/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({ approve, note }) }),
};

/** For U's landing card "Existing deals going bad" (and the renewals / conditions cards). */
export function fetchBookCounts(): Promise<BookCounts> {
  return bookApi.counts();
}

export const DRIFT_LABELS: Record<string, string> = {
  pd_migration: "PD migration", lgd: "LGD", funding: "Funding", fees: "Fees", utilisation: "Utilisation", cross_sell: "Unrealised cross-sell",
};
