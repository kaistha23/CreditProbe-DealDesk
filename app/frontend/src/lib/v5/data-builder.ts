/**
 * v5 Data Builder client.
 *
 * Talks ONLY to the Data Builder service (its own backend, port 8504 by
 * default, `NEXT_PUBLIC_DATA_API`), which reads every v5 data domain
 * read-only. It never imports the Cockpit client or the legacy `lib/api.ts`.
 */
import { friendlyError } from "./errors.ts";
import * as React from "react";

export function dataOrigin(): string {
  return (process.env.NEXT_PUBLIC_DATA_API ?? "http://127.0.0.1:8504").replace(/\/$/, "");
}

const PREFIX = "/api/v1/data";

export class DataError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${dataOrigin()}${PREFIX}${path}`, { cache: "no-store", credentials: "include" });
  } catch {
    throw new DataError(0, `Data Domains is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Data Domains", response.status, body);
    throw new DataError(response.status, message);
  }
  return body as T;
}

// ---------------------------------------------------------------- types

export type Op = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in" | "contains";
export const OPS: { op: Op; label: string; numeric: boolean; text: boolean }[] = [
  { op: "eq", label: "equals", numeric: true, text: true },
  { op: "neq", label: "does not equal", numeric: true, text: true },
  { op: "gt", label: ">", numeric: true, text: false },
  { op: "gte", label: "≥", numeric: true, text: false },
  { op: "lt", label: "<", numeric: true, text: false },
  { op: "lte", label: "≤", numeric: true, text: false },
  { op: "in", label: "is one of", numeric: true, text: true },
  { op: "contains", label: "contains", numeric: false, text: true },
];
export function opLabel(op: string): string {
  return OPS.find((o) => o.op === op)?.label ?? op;
}

export interface Filter { column: string; op: Op; value: string }

export interface RelationInfo {
  relation: string; label: string; book: "corporate" | "retail" | string; description: string; grain: string;
  rows: number; periods: string[]; latest_period: string | null; period_column: string | null;
  key_columns: string[]; columns: number; release_id: string;
}
export interface DomainInfo {
  domain: string; label: string; status: "live" | "coming" | string; description: string;
  relations: RelationInfo[]; rows: number;
}
export interface DomainsResponse { domains: DomainInfo[] }

export type ColumnType = "text" | "integer" | "number" | "flag" | "date";
export interface Column {
  name: string; label: string; type: ColumnType; storage_type: string; unit: string; description: string;
  source: "manifest" | "registry" | "derived" | string; key: boolean; period: boolean;
  role?: "key" | "value" | "compare" | "delta" | "presence"; base?: string; period_of?: string;
}
export interface SchemaResponse {
  domain: string; domain_label: string; relation: string; relation_label: string;
  book: string; release_id: string; period_column: string | null; key_columns: string[]; periods: string[];
  latest_period: string | null; rows: number; columns: Column[];
}
export type Row = Record<string, string | number | boolean | null>;
export interface RowsResponse {
  domain: string; relation: string; period: string | null;
  compare_period: string | null; compare_basis: string | null; total: number; limit: number; offset: number;
  columns: Column[]; rows: Row[];
}

export interface Query {
  period?: string; compare?: string; search?: string; filters?: Filter[]; columns?: string[];
  sort?: string; desc?: boolean;
}

function params(q: Query, extra: Record<string, string | number> = {}): string {
  const out = new URLSearchParams();
  if (q.period) out.set("period", q.period);
  if (q.compare) out.set("compare_period", q.compare);
  if (q.search) out.set("search", q.search);
  if (q.filters?.length) out.set("filters", JSON.stringify(q.filters));
  if (q.columns?.length) out.set("columns", q.columns.join(","));
  if (q.sort) out.set("sort", q.sort);
  if (q.sort && q.desc) out.set("desc", "true");
  for (const [k, v] of Object.entries(extra)) out.set(k, String(v));
  const s = out.toString();
  return s ? `?${s}` : "";
}

const rel = (domain: string, relation: string) =>
  `/relations/${encodeURIComponent(domain)}/${encodeURIComponent(relation)}`;

export const dataApi = {
  domains: () => request<DomainsResponse>("/domains"),
  schema: (domain: string, relation: string) => request<SchemaResponse>(`${rel(domain, relation)}/schema`),
  rows: (domain: string, relation: string, q: Query, limit: number, offset: number) =>
    request<RowsResponse>(`${rel(domain, relation)}/rows${params(q, { limit, offset })}`),
};

/** A plain link to the service's export; the browser downloads it (Content-Disposition). */
export function exportHref(domain: string, relation: string, q: Query, format: "csv" | "xlsx"): string {
  return `${dataOrigin()}${PREFIX}${rel(domain, relation)}/export.${format}${params(q)}`;
}

/**
 * Load by key. The last answer is kept while the next one loads, so a page
 * turn or a new filter does not blank the grid; `stale` says it is showing.
 */
export function useData<T>(load: () => Promise<T>, key: string | null) {
  const [state, setState] = React.useState<{ key: string | null; data: T | null; error: string | null }>(
    { key: null, data: null, error: null });
  const ref = React.useRef(load);
  React.useEffect(() => { ref.current = load; });
  React.useEffect(() => {
    if (key === null) return;
    let live = true;
    ref.current().then(
      (data) => { if (live) setState({ key, data, error: null }); },
      (err: unknown) => {
        if (live) setState((prev) => ({ key, data: prev.data, error: err instanceof Error ? err.message : String(err) }));
      },
    );
    return () => { live = false; };
  }, [key]);
  const current = state.key === key;
  return {
    data: state.data,
    error: current ? state.error : null,
    loading: key !== null && !current,
    stale: key !== null && !current && state.data !== null,
  };
}

// ---------------------------------------------------------------- words

export function count(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : Math.round(n).toLocaleString("en-US");
}

/** A cell as a reader wants it: integers grouped, decimals to a sensible precision, flags as Yes/No. */
export function cell(value: Row[string], type: ColumnType | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (type === "flag") return value === 1 ? "1" : value === 0 ? "0" : String(value);
    if (Number.isInteger(value) && type !== "number") return value.toLocaleString("en-US");
    const abs = Math.abs(value);
    const digits = abs === 0 ? 0 : abs >= 1000 ? 1 : abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6;
    return value.toLocaleString("en-US", { maximumFractionDigits: digits });
  }
  return String(value);
}

export function signedCell(value: Row[string], type: ColumnType | undefined): string {
  if (typeof value !== "number") return cell(value, type);
  if (value === 0) return "0";
  return `${value > 0 ? "+" : "−"}${cell(Math.abs(value), type)}`;
}

export const BOOK_LABEL: Record<string, string> = { corporate: "Corporate", retail: "Retail", both: "Reference" };
