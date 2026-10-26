/**
 * v5 Queries and BRF studio client (PLAN_R9 Session F, P7 regulatory response).
 *
 * Talks to the Queries and BRF service (backend.queries_v5.api, port 8516, `NEXT_PUBLIC_QUERIES_API`).
 * Every figure arrives with its display string (`<key>__d`, G5) and a trace.
 */
import { friendlyError } from "./errors.ts";

export function queriesOrigin(): string {
  return (process.env.NEXT_PUBLIC_QUERIES_API ?? "http://127.0.0.1:8516").replace(/\/$/, "");
}
export const qUrl = (path: string) => `${queriesOrigin()}/api/v1/queries${path}`;
export const brfUrl = (path: string) => `${queriesOrigin()}/api/v1/brf${path}`;

async function request<T>(url: string, init?: RequestInit, service = "Queries"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "include", cache: "no-store" });
  } catch {
    throw new Error(`${service} is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(friendlyError(service, response.status, body));
  return body as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

export type Kind = "sar" | "pct" | "count" | "text" | "days" | "ratio";
export interface Column { key: string; label: string; kind: Kind }
export type Row = Record<string, unknown>;
export interface Table { columns: Column[]; rows: Row[]; total?: Row }
export interface Trace { sources: string[]; steps: string[]; rule: string; article: string; row_count: number; period: string; engine: string }
export interface Powered { pack: string; pack_id: string; rule: string; article: string; confidence: string }
export interface DataUsed { domain: string; relation: string; fields: string[]; filter: string }
export interface Answer {
  n: number; question: string; data_used: DataUsed[]; analysis: string; draft: string; table: Table | null;
  chart: { data: Record<string, unknown>[]; layout?: Record<string, unknown> } | null; trace: Trace; powered_by: Powered;
  status?: string; edited?: boolean;
}
export const STATUSES = ["Open", "Drafted", "Reviewed", "Sent"] as const;
export interface QueryCard {
  id: string; file: string; case: string; title: string; from: string; article: string; reference: string; subject: string;
  status: string; owner: string; due: string; received: string; questions: number;
}
export interface QueryItem extends QueryCard { sender: string; period: string; answers: Answer[]; log: { at: string; text: string }[] }
export interface CaseCard { case: string; title: string; from: string; article: string; file: string | null }

export const queries = {
  cases: () => request<CaseCard[]>(qUrl("/cases")),
  list: () => request<QueryCard[]>(qUrl("/items")),
  get: (id: string) => request<QueryItem>(qUrl(`/items/${id}`)),
  prepared: (c: string) => request<QueryItem>(qUrl(`/items/prepared/${c}`), { method: "POST" }),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return request<QueryItem>(qUrl("/items/upload"), { method: "POST", body: f }); },
  edit: (id: string, n: number, body: { draft?: string; status?: string }) => request<QueryItem>(qUrl(`/items/${id}/answers/${n}`), json(body)),
  status: (id: string, body: { status?: string; owner?: string; due?: string }) => request<QueryItem>(qUrl(`/items/${id}/status`), json(body)),
  exportUrl: (id: string, ext: "docx" | "xlsx") => qUrl(`/items/${id}/export.${ext}`),
};

export interface BrfField { id: string; label: string; domain: string; dataset: string; fields: string[]; filters: string; calc: string; edited: boolean }
export interface FlowNode { id: string; kind: "source" | "transform" | "calc" | "check" | "output"; label: string; detail: string }
export interface BrfCheck { id: string; label: string; rule: string; status?: string; detail?: string }
export interface BrfReturnCard { id: string; title: string; frequency: string; article: string; state: string; period: string | null; fields: number; schedule: string | null }
export interface BrfReturn extends Omit<BrfReturnCard, "fields"> {
  fields: BrfField[]; flow: { nodes: FlowNode[]; edges: { from: string; to: string }[] };
  checks: BrfCheck[]; periods: string[]; as_of: string; template: { file: string; at: string } | null; log: { at: string; text: string }[];
}
export interface BrfRun { return_id: string; title: string; period: string; grid: Table; checks: BrfCheck[]; note: string; powered_by: Powered; trace: Trace }

export const brf = {
  list: () => request<BrfReturnCard[]>(brfUrl("/returns"), undefined, "BRF"),
  get: (id: string) => request<BrfReturn>(brfUrl(`/returns/${id}`), undefined, "BRF"),
  upload: (id: string, file: File) => { const f = new FormData(); f.append("file", file); return request<BrfReturn>(brfUrl(`/returns/${id}/upload`), { method: "POST", body: f }, "BRF"); },
  field: (id: string, body: { id: string; filters?: string; calc?: string; label?: string }) => request<BrfReturn>(brfUrl(`/returns/${id}/field`), json(body), "BRF"),
  lock: (id: string, period: string) => request<BrfReturn>(brfUrl(`/returns/${id}/lock`), json({ period }), "BRF"),
  run: (id: string) => request<BrfRun>(brfUrl(`/returns/${id}/run`), { method: "POST" }, "BRF"),
  publish: (id: string, schedule: string) => request<BrfReturn>(brfUrl(`/returns/${id}/publish`), json({ schedule }), "BRF"),
  exportUrl: (id: string) => brfUrl(`/returns/${id}/export.xlsx`),
};

/** "High" -> "high" for the shared Powered-by strip. */
export function confidence(c: string): "high" | "medium" | "low" {
  const x = c.toLowerCase();
  return x === "medium" || x === "low" ? x : "high";
}

/** Split "**bold** text" into parts for rendering key figures in bold. */
export function boldParts(text: string): { text: string; bold: boolean }[] {
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((t) => (t.startsWith("**") && t.endsWith("**") ? { text: t.slice(2, -2), bold: true } : { text: t, bold: false }));
}
