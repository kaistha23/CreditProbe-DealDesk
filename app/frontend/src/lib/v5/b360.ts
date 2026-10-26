/**
 * v5 Borrower 360 client.
 *
 * Talks ONLY to the Borrower 360 service (its own backend, port 8502 by
 * default, `NEXT_PUBLIC_B360_API`). It never imports the Cockpit client or the
 * legacy `lib/api.ts`. Amounts arrive in SAR million, as the books publish
 * them, unless a column's unit says SAR thousand.
 */
import { friendlyError } from "./errors.ts";
import * as React from "react";

import { count, pct, sar } from "@/lib/v5/ews";
import type { GraphPayload } from "@/lib/v5/graph-figure";

export type DomainId = "corporate" | "retail";

export function b360Origin(): string {
  return (process.env.NEXT_PUBLIC_B360_API ?? "http://127.0.0.1:8502").replace(/\/$/, "");
}

export class B360Error extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${b360Origin()}/api/v1/b360${path}`, { cache: "no-store", credentials: "include" });
  } catch {
    throw new B360Error(0, `Borrower 360 is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Borrower 360", response.status, body);
    throw new B360Error(response.status, message);
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

export type Unit =
  | "text" | "id" | "period" | "sar_mn" | "sar_k" | "pct" | "prob" | "x" | "int" | "days" | "months"
  | "flag" | "rating" | "ews_band" | "num" | "code" | "chips" | "@unit";

export type Row = Record<string, unknown>;
export interface Column { key: string; label: string; unit: Unit }
export interface Table { id: string; title: string; columns: Column[]; rows: Row[]; note?: string }
export interface SummaryFigure { label: string; value: unknown; unit: Unit }
export interface Tab {
  key: string; label: string; period: string; summary: SummaryFigure[]; tables: Table[]; series: Row[];
  note: string; meta: Record<string, unknown>;
  /** The Relationships tab: the graph around the borrower and the analytics beside it. */
  graph?: GraphPayload;
}
export interface Profile {
  domain_id: DomainId; customer_id: string; period: string; as_of: string; periods: string[];
  book_periods: string[]; frequency: string; currency: string; money_unit: string; name: string | null;
  exposure: number; ecl: number; limit: number; facilities: number; worst_dpd: number; worst_stage: number;
  ews_score: number | null; ews_band: string; ews_ruleset: string; rating: string | null; rating_label: string;
  rating_previous: string | null; segment: string | null; subsegment: string | null; region: string | null;
  group_id?: string; group_name?: string; watchlist?: boolean; watchlist_reason?: string; outlook?: string;
  behaviour_score?: number; products?: string[];
  releases: { book: string; ews: string; bureau: string; open_banking: string };
  labels: { owner: string; exposure: string; exposures: string };
}
export interface Customer {
  profile: Profile; tab_list: { key: string; label: string }[]; tabs: Record<string, Tab>;
  links: { early_warning: string; borrower_360: string };
}
export interface SearchResult {
  id: string; name: string | null; segment: string | null; subsegment: string | null; rating: string | null;
  group_id: string | null; facilities: number; exposure: number; score: number | null; band: string;
}
export interface Search {
  domain_id: DomainId; period: string; q: string; matched: number; returned: number; ranked: boolean;
  order: string; results: SearchResult[]; labels: { owner: string; exposures: string };
}

/** The book list (PLAN_R4 B2): one page of the whole book, filtered and sorted on the server. */
export interface ListColumn { key: string; label: string; unit: Unit; default: boolean }
export interface ListLabels {
  segment: string; subsegment: string; region: string; branch: string; product: string; band: string; stage: string;
  ews: string; dpd: string; ead: string; owner: string; owners: string; exposures: string;
}
export interface ListPage {
  domain_id: DomainId; period: string; periods: string[]; total: number;
  totals: { ead: number; ecl: number; limit: number; exposures: number };
  book_total: number; book_ead: number; offset: number; limit: number; sort: string; dir: "asc" | "desc";
  columns: ListColumn[]; rows: Row[]; labels: ListLabels; branch_available: boolean;
}
export interface ListOption { value: string; count: number; parent?: string }
export interface ListOptions {
  domain_id: DomainId; period: string; periods: string[]; labels: ListLabels; columns: ListColumn[];
  segment: ListOption[]; subsegment: ListOption[]; region: ListOption[]; branch: ListOption[]; branch_available: boolean;
  product: ListOption[]; band: ListOption[]; stage: ListOption[]; ews: ListOption[]; dpd: ListOption[];
  ead: { min: number | null; max: number | null };
  /** PLAN_R9 B2: P2 filters. */
  sicr?: (ListOption & { label?: string })[]; utp?: (ListOption & { label?: string })[];
  watch?: ListOption[]; rm?: ListOption[];
}

/** PLAN_R9: the "Powered by" facts of an answer (pack, rule or article, confidence, trace). */
export interface PoweredBy { id: string; name: string; rules?: string[]; articles?: string[]; confidence: string; trace: string }

/** PLAN_R9 B1: the top cards (GET /cards). */
export interface BookCard { key: string; label: string; count: number; ead: number; ecl: number; pct_book: number }
export interface BookCards {
  domain_id: DomainId; period: string; as_of: string; book: { count: number; ead: number; ecl: number };
  cards: BookCard[]; powered_by: PoweredBy;
}

/** PLAN_R9 B4: one SICR or UTP reason with its CBUAE CRM article and evidence. */
export interface Reason { code: string; text: string; article: string; section: string; value: string; date: string; source: string; evidence: string }
export interface Classification {
  domain_id: DomainId; id: string; period: string; as_of: string; stage: number;
  sicr: Reason[]; utp: Reason[]; watch_status: string; watch_reason: string | null; restructured: boolean;
  sicr_flag_book: boolean; assessment: string | null; powered_by: PoweredBy;
}

// ---------------------------------------------------------------- calls

export const b360 = {
  search: (domain: DomainId, q: string, period?: string, limit = 25) =>
    request<Search>(`/search${qs({ domain, q, period, limit })}`),
  customer: (domain: DomainId, id: string, period?: string) =>
    request<Customer>(`/customers/${encodeURIComponent(id)}${qs({ domain, period })}`),
  graph: (domain: DomainId, id: string, period: string, depth: number) =>
    request<GraphPayload>(`/customers/${encodeURIComponent(id)}/graph${qs({ domain, period, depth })}`),
  list: (domain: DomainId, period: string, query: Record<string, string | number>) =>
    request<ListPage>(`/list${qs({ domain, period, ...query })}`),
  listOptions: (domain: DomainId, period: string) => request<ListOptions>(`/list/options${qs({ domain, period })}`),
  cards: (domain: DomainId, period: string) => request<BookCards>(`/cards${qs({ domain, period })}`),
  classification: (domain: DomainId, id: string, period?: string) =>
    request<Classification>(`/customers/${encodeURIComponent(id)}/classification${qs({ domain, period })}`),
  tab: (domain: DomainId, id: string, tab: string, period?: string) =>
    request<Tab>(`/customers/${encodeURIComponent(id)}/tab/${encodeURIComponent(tab)}${qs({ domain, period })}`),
};

/** The service's workbook: every tab, or the one named. */
export function excelHref(domain: DomainId, id: string, period: string, tab?: string): string {
  return `${b360Origin()}/api/v1/b360/customers/${encodeURIComponent(id)}/export.xlsx${qs({ domain, period, tab })}`;
}

/** The whole filtered, sorted list as a workbook, with the chosen columns (no paging). */
export function listExcelHref(domain: DomainId, period: string, query: Record<string, string | number>, columns: string[]): string {
  const rest = Object.fromEntries(Object.entries(query).filter(([k]) => k !== "offset" && k !== "limit"));
  return `${b360Origin()}/api/v1/b360/list/export.xlsx${qs({ domain, period, ...rest, columns: columns.join(",") })}`;
}

/** The relationships of one borrower or customer as a workbook (the graph's nodes and links, and every analytic). */
export function graphExcelHref(domain: DomainId, id: string, period: string, depth = 1): string {
  return `${b360Origin()}/api/v1/b360/customers/${encodeURIComponent(id)}/graph/export.xlsx${qs({ domain, period, depth })}`;
}

/** Load once per key; keeps the service's own error text. */
export function useB360<T>(load: () => Promise<T>, key: string) {
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

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** A value as text, by its unit. Ratings and bands are returned as text; the screen styles them. */
export function formatValue(value: unknown, unit: Unit): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = num(value);
  switch (unit) {
    case "sar_mn": return n === null ? String(value) : sar(n);
    case "sar_k": return n === null ? String(value) : `SAR ${n.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}k`;
    case "pct": return n === null ? String(value) : pct(n, 1);
    case "prob": return n === null ? String(value) : pct(n * 100, 2);
    case "x": return n === null ? String(value) : `${n.toFixed(2)}x`;
    case "int": case "days": return n === null ? String(value) : count(Math.round(n));
    case "months": return n === null ? String(value) : n.toFixed(1);
    case "num": return n === null ? String(value) : n.toLocaleString("en-US", { maximumFractionDigits: 2 });
    case "flag": return n === null ? String(value) : n ? "Yes" : "No";
    default: return String(value);
  }
}
