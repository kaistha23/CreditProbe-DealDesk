/**
 * v5 Scorecard Validation client (PLAN_R3, session S2).
 *
 * Talks to the Scorecard service (port 8507, `NEXT_PUBLIC_SCORECARD_API`) with the session cookie
 * (`credentials: "include"`). A turn is answered in one request (the tests take about a second), so there is no
 * stream to follow. Figures arrive as Plotly `{data, layout}`; ratios arrive as fractions.
 */
import { friendlyError } from "./errors.ts";
export { useEws as useLoad } from "@/lib/v5/ews";
export { CONCLUSION_WORD, STATUS_WORD, SUGGESTED, fmt, when } from "@/lib/v5/scorecard-words";

export function scorecardOrigin(): string {
  return (process.env.NEXT_PUBLIC_SCORECARD_API ?? "http://127.0.0.1:8507").replace(/\/$/, "");
}
const PREFIX = "/api/v1/scorecard";
export const apiUrl = (path: string) => `${scorecardOrigin()}${PREFIX}${path}`;

export class ScorecardError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ScorecardError(0, `Scorecard Validation is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ScorecardError(response.status, friendlyError("Scorecard Validation", response.status, body));
  }
  return body as T;
}

// ---------------------------------------------------------------- types

import type { Conclusion, Status } from "@/lib/v5/scorecard-words";
export type { Conclusion, Status };
export type GroupId = "discrimination" | "calibration" | "stability" | "variables" | "overrides";
export interface ScorecardInfo {
  scorecard_id: string; name: string; version: string; type: string; segment: string; book: "corporate" | "retail"; frequency: string;
  description: string; rows: number; periods: [string, string]; development: [string, string]; monitoring: [string, string];
  last_matured: string; as_of: string; variables: { name: string; label: string; iv: number }[]; has_overrides: boolean;
  owner_key: string; unit_key: string; segment_options: string[];
}
export interface Plan {
  scorecard_id: string; development: [string, string]; monitoring: [string, string]; as_of: string; segment_by: string;
  tests: Record<GroupId, boolean>; thresholds: Record<string, { green: number; amber: number }>; notes: string[];
}
export interface Test {
  id: string; group: GroupId; label: string; value: number | string | null; format: string; threshold: string; status: Status; comment: string;
}
export interface Column { key: string; label: string; format: string }
export interface TableData { id: string; title: string; columns: Column[]; rows: Record<string, unknown>[]; note: string }
export interface ChartData { id: string; title: string; figure: { data: Record<string, unknown>[]; layout: Record<string, unknown> }; note: string }
export interface Section { id: GroupId; title: string; status: Status; tests: Test[]; tables: TableData[]; charts: ChartData[] }
export interface Finding { test: string; group: GroupId; label: string; status: Status; text: string; action: string }
export interface Result {
  engine_version: string; plan: Plan; scorecard: ScorecardInfo;
  sample: { development: { from: string; to: string; n: number; defaults: number }; monitoring: { from: string; to: string; n: number; defaults: number };
            as_of: { period: string; n: number }; last_matured: string; segment_by: string; open_periods: string[] };
  summary: { overall: Status; counts: Record<Status, number>; tests: number }; sections: Section[];
  thresholds: Record<string, { label: string; text: string }>; findings: Finding[]; seconds: number;
}
export interface Review { status: "pending" | "reviewed"; conclusion: Conclusion | ""; note: string; reviewer: string; at: string | null }
export interface ValidationRow {
  validation_id: string; thread_id: string; scorecard_id: string; scorecard: string; version: string; type: string; book: "corporate" | "retail";
  title: string; as_of: string; overall: Status; counts: Record<Status, number>; owner: string; created_at: number; review: Review; plan: Plan;
}
export interface Validation extends ValidationRow { result: Result; seed: boolean }
export interface PlanGroup { group: GroupId; title: string; what: string; enabled: boolean; thresholds: { label: string; text: string }[] }
export type Block =
  | { type: "text"; markdown: string }
  | { type: "choose"; scorecards: ScorecardInfo[] }
  | { type: "plan"; plan: Plan; groups: PlanGroup[]; note: string; readiness: string[]; segment_options: string[] }
  | { type: "validation"; validation_id: string }
  | { type: "findings"; items: Finding[] }
  | { type: "report"; validation_id: string; text: string }
  | { type: "mmsg"; validation_id: string; text: string }
  | { type: "answer"; markdown: string; source?: string; model?: string }
  | { type: "table"; title: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[]; row_count?: number }
  | { type: "chart"; title: string; kind: string; x: string; y: string[]; y2?: string; labels: Record<string, string>; rows: Record<string, unknown>[] };
export interface Answer {
  blocks: Block[]; suggestions: { label: string; send: string }[]; question_display: string;
  evidence?: { artifact_id: string; kind: string; sql?: string | null; tool?: string | null; purpose: string; row_count: number }[];
}
export interface Turn { ordinal: number; question: string; answer: Answer; created_at: number }
export interface ThreadView {
  thread_id: string; title: string; owner: string; team: string; scorecard_id: string; scorecard: ScorecardInfo | null; created_at: number; updated_at: number;
  stage: "choose" | "plan" | "ran"; plan: Plan | null; validation_id: string | null; turns: Turn[]; validations: ValidationRow[];
}
export interface ThreadRow { thread_id: string; owner: string; scorecard_id: string; title: string; created_at: number; updated_at: number; stage: string }
export interface Meta {
  scorecards: ScorecardInfo[]; groups: { group: GroupId; title: string; what: string }[]; assistant: { planner: string; model_available: boolean };
  examples: string[]; thresholds: Record<string, Record<string, { label: string; text: string }>>;
}
export interface PlaybookReport { id: string; title: string; template: string; status: string; owner: { username: string; name: string }; due_date: string | null; version: number; section_count: number; href: string }

// ---------------------------------------------------------------- calls

export const scorecard = {
  meta: () => request<Meta>(`/meta`),
  validations: () => request<{ validations: ValidationRow[] }>(`/validations`),
  validation: (id: string) => request<Validation>(`/validations/${encodeURIComponent(id)}`),
  review: (id: string, body: { conclusion: Conclusion; note: string }) =>
    request<{ review: Review }>(`/validations/${encodeURIComponent(id)}/review`, { method: "POST", body: JSON.stringify(body) }),
  threads: () => request<{ threads: ThreadRow[] }>(`/threads`),
  thread: (id: string) => request<ThreadView>(`/threads/${encodeURIComponent(id)}`),
  createThread: (body: { question?: string; scorecard_id?: string }) => request<ThreadView>(`/threads`, { method: "POST", body: JSON.stringify(body) }),
  /** One turn; `traceId` lets the page poll the live process trace (docs/v5/THREAD_API.md 2.2). */
  say: (threadId: string, text: string, traceId?: string) =>
    request<ThreadView>(`/threads/${encodeURIComponent(threadId)}/messages`, {
      method: "POST", body: JSON.stringify({ text }), headers: traceId ? { "X-Trace-Id": traceId } : undefined }),
  playbookReports: () => request<{ reports: PlaybookReport[] }>(`/playbook/reports`),
  toPlaybook: (id: string, body: { report_id?: string; new_report?: { title: string; template: string; book?: string } }) =>
    request<{ report_id: string; report_title: string; section_id: string; href: string; created_report: boolean }>(
      `/validations/${encodeURIComponent(id)}/playbook`, { method: "POST", body: JSON.stringify(body) }),
};

export const reportHref = (id: string) => apiUrl(`/validations/${encodeURIComponent(id)}/report.docx`);
export const exportHref = (id: string) => apiUrl(`/validations/${encodeURIComponent(id)}/export.xlsx`);

