/**
 * Round S: the Intelligence Studio on the Deal Desk service (/api/v1/dealdesk/intelligence-studio): what CreditProbe
 * has learnt from the RMs and the bank, counted from the stores that hold it. Pure helpers tested in
 * intelligence-studio.test.ts.
 */
import { friendlyError } from "./errors.ts";

const BASE = "/api/v1/dealdesk/intelligence-studio";

export function studioOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export interface Absent { available: false; reason?: string }
export type Part<T> = (T & { available: true }) | Absent;

export interface Customers {
  total: number; existing: number; new_to_bank: number;
  coverage: { source: string; label: string; customers: number; pct: number }[];
  sources: { key: string; label: string }[];
  rows: { customer_id: string; name: string; existing: boolean; proposals: string[]; decisions: number; sources: Record<string, boolean>; sources_n: number }[];
}
export interface Documents {
  total: number; files: number; pages: number;
  by_type: { doc_type: string; label: string; n: number }[]; by_method: { method: string; n: number }[]; by_kind: { kind: string; n: number }[];
}
export interface Proposals {
  learned: number; uploaded: number; reason?: string;
  by_bank: { bank: string; label: string; proposals: number; kinds: Record<string, number>; sources: Record<string, number> }[];
  by_analyst: { person: string; deals_as_analyst: number; deals_as_rm: number; sections_edited: number; sections_accepted: number; rules: number; paper_edits: number; total: number }[];
}
export interface Rules {
  total: number; by_scope: Record<string, number>;
  by_author: { author: string; name: string; rules: number; me: number; team: number; bank: number; from_instruction: number; last: string }[];
  recent: { id: string; text: string; scope: string; author: string; created_at: string; section: string }[];
}
export interface Policies {
  pack_version?: string; clauses?: number;
  books?: { book: string; title: string; approved_by: string; approved_on: string; next_review: string; clauses: number }[];
  regulatory?: { key: string; title: string; issuer: string; effective_from: string; clauses: number }[];
  library: { policy_id: string; version: number; title: string; status: string; effective_date: string; clauses: number }[];
  rulebook: { available?: false; reason?: string; assessments?: number; approved?: number; thresholds?: number; gold?: number; open_flags?: number };
}
export interface ReaderPeriod {
  period: string; documents: number; readable: number; corrected: number; recon_agrees: number; recon_differs: number; recon_flags: number;
  fields_read: number; fields_confirmed: number; fields_offered: number; fields_flagged: number;
  reader_accuracy_pct: number | null; field_agreement_pct: number | null;
}
export interface Reader { periods: ReaderPeriod[]; totals: Omit<ReaderPeriod, "period">; field_states: boolean }
export interface Corrections {
  total: number; sources: Record<string, boolean>;
  by_kind: { kind: string; label: string; n: number }[]; by_week: { period: string; n: number }[];
  recent: { kind: string; at: string; by: string; what: string }[];
}
export interface StageRow { purpose: string; model: string; calls: number; ok_calls: number; input_tokens: number; output_tokens: number; cached_tokens: number; avg_ms: number; max_ms: number; runs: number }
export interface Governance {
  module: string; efficiency: boolean; modules: string[];
  totals: { calls: number; ok: number; input_tokens: number; output_tokens: number; cached_tokens: number; p50_ms: number | null; p95_ms: number | null;
            turns: number; calls_per_turn: number | null; input_per_turn: number | null; models: string[] };
  by_stage: StageRow[]; by_model: (StageRow & { provider: string })[];
  by_day: { day: string; calls: number; input_tokens: number; output_tokens: number; cached_tokens: number }[];
}
export interface Overview {
  as_of: string; plain_words: string[];
  headline: { customers: number | null; documents_read: number | null; proposals_learned: number | null; rules_active: number | null;
              policy_clauses: number | null; corrections_absorbed: number | null; reader_accuracy_pct: number | null; model_calls: number | null };
  customers: Part<Customers>; documents: Part<Documents>; proposals: Part<Proposals>; rules: Part<Rules>; policies: Part<Policies>;
  reader: Part<Reader>; corrections: Part<Corrections>; governance: Part<Governance> & { efficiency?: boolean };
}

async function call<T>(path: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${studioOrigin()}${BASE}${path}`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export const studioApi = {
  overview: (module = "") => call<Overview>(module ? `?module=${encodeURIComponent(module)}` : ""),
};

/** A count for a KPI tile: "–" when the store is absent (null), never a zero that was not measured. */
export function count(v: number | null | undefined): string {
  return v == null ? "–" : v.toLocaleString("en-US");
}

/** "92.5%" (null-safe, one decimal, trailing .0 dropped). */
export function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "–";
  return `${Number(v.toFixed(1))}%`;
}

/** Tokens in thousands above 10,000 ("38.2k"), else the whole number. */
export function tokens(v: number | null | undefined): string {
  if (v == null) return "–";
  return v >= 10000 ? `${(v / 1000).toFixed(1)}k` : v.toLocaleString("en-US");
}

/** Seconds from milliseconds ("4.2 s"). */
export function secs(ms: number | null | undefined): string {
  return ms == null ? "–" : `${(ms / 1000).toFixed(1)} s`;
}

/** The model call stages in plain words. */
export const STAGE_LABEL: Record<string, string> = {
  ENGINE_FIRST_WRITE: "Writing from the engine's results (one call)",
  ANALYSIS_ACTION: "Analysis step (tool choice)",
  ANSWER_CORRECTION: "Answer correction",
  FINAL_ANSWER: "Final answer",
};
export function stageLabel(p: string): string {
  return STAGE_LABEL[p] ?? p.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

/** Reader periods that have documents (the chart's points), oldest first. */
export function readerSeries(r: Reader): { x: string[]; accuracy: (number | null)[]; documents: number[] } {
  const ps = r.periods.filter((p) => p.documents > 0);
  return { x: ps.map((p) => p.period), accuracy: ps.map((p) => p.reader_accuracy_pct), documents: ps.map((p) => p.documents) };
}

/** Coverage bars ordered as the sources are listed (deal register first). */
export function coverageBars(c: Customers): { label: string; pct: number; customers: number }[] {
  return c.coverage.map((x) => ({ label: x.label, pct: x.pct, customers: x.customers }));
}
