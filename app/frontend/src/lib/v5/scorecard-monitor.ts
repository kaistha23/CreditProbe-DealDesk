/**
 * R16 M8: the Scorecard monitoring client (front page, deep dive, findings register, maker-checker, MMSG report).
 * Same service and cookie as the validation client (`lib/v5/scorecard.ts`, port 8507).
 */
import { friendlyError } from "./errors.ts";
import { apiUrl, ScorecardError } from "./scorecard";
import type { Status } from "./scorecard-words";

export type Criterion = "discrimination" | "calibration" | "stability" | "overrides" | "migration" | "data_quality" | "usage" | "cycle" | "findings";

export interface TracePoint { period: string; value: number | null; status: Status }
export interface CriterionLine {
  criterion: Criterion; status: Status; metric: string; label: string; value: number | null; display: string; threshold: string;
  trend: TracePoint[]; since: string; sentence: string; period: string; owner: string; also: string[];
  trace: { domain?: string; relation: string; keys: Record<string, unknown>; period?: string; column?: string; status?: string }[];
}
export interface Health {
  scorecard_id: string; name: string; version: string; tier: string; book: string; overall: Status; line: string; criteria: CriterionLine[];
  model_owner: string; frequency: string;
}
export interface Breach extends CriterionLine {
  id: string; rank: number; scorecard_id: string; scorecard: string; tier: string; criterion_title: string; score: number; headline: string;
}
export interface ScheduleRow { scorecard_id: string; frequency: string; last_run: string; next_run: string; report_to: string; alert_to: string }
export interface Front {
  as_of: string; plain_words: string[]; health: Health[]; breaches: Breach[];
  counts: { scorecards: number; red: number; amber: number; open_findings: number; overdue_findings: number };
  schedule: ScheduleRow[]; criteria: Record<Criterion, { title: string; what: string }>; sources: string[];
}
export interface Finding {
  finding_id: string; scorecard_id: string; source_ref: string; criterion: string; severity: "High" | "Medium" | "Low"; title: string; text: string;
  remediation: string; owner: string; raised_on: string; due_on: string; status: "open" | "in_progress" | "closed"; overdue: boolean; days_overdue: number;
  origin?: string;
}
export interface Action { decision: string; title: string; why: string; severity: string; owner: string; due: string; reference: string }
export interface ChartData { id: string; title: string; figure: { data: Record<string, unknown>[]; layout: Record<string, unknown> }; note: string }
export interface SegmentRow {
  segment: string; n?: number | null; defaults?: number | null; gini?: number | null; gini_status?: Status; observed?: number | null; expected?: number | null;
  oe?: number | null; oe_status?: Status; psi?: number | null; psi_status?: Status; n_now?: number | null; in_scope: boolean;
}
export interface DeepDive {
  scorecard_id: string; name: string; version: string; tier: string; tier_reason: string; overall: Status; line: string;
  inventory: Record<string, string | number | null>; schedule: ScheduleRow | null; plain_words: string[]; criteria: CriterionLine[]; charts: ChartData[];
  segments: { by: string; rows: SegmentRow[]; window: string };
  grades: { grade: string; n: number; defaults: number; observed: number; expected: number; oe: number; status: Status; note: string }[];
  characteristics: { variable: string; label: string; in_model: boolean; csi: number | null; missing_pct: number; unseen_pct: number | null; iv_dev: number | null; iv_mon: number | null; status: Status }[];
  characteristics_period: string;
  override_reasons: { reason: string; share: number; n: number; observed: number | null; expected: number | null }[];
  root_cause: string[]; actions: Action[]; findings: Finding[];
  validations: { validation_id: string; thread_id: string; title: string; as_of: string; overall: Status; created_at: number;
                 review: { status: string; conclusion: string }; maker_checker: ConclusionRecord | null }[];
  references: Record<string, string>; sources: string[];
}
export type ConclusionId = "fit" | "conditions" | "not_fit";
export interface ConclusionRecord {
  state: "not_proposed" | "proposed" | "approved" | "returned"; conclusion?: ConclusionId; note?: string; maker?: string; maker_at?: string;
  checker?: string; checker_at?: string; checker_note?: string; history?: { step: string; by: string; at: string }[];
}
export interface ConclusionView {
  validation_id: string; proposed: { conclusion: ConclusionId; label: string; reasons: string[] }; record: ConclusionRecord;
  checker_teams: string[]; conclusions: Record<ConclusionId, string>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new ScorecardError(0, "Scorecard monitoring is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ScorecardError(response.status, friendlyError("Scorecard monitoring", response.status, body));
  return body as T;
}

export const monitor = {
  front: () => request<Front>(`/monitor/front`),
  scorecard: (sid: string) => request<DeepDive>(`/monitor/scorecards/${encodeURIComponent(sid)}`),
  register: (sid = "") => request<{ findings: Finding[]; as_of: string }>(`/monitor/register${sid ? `?scorecard_id=${encodeURIComponent(sid)}` : ""}`),
  updateFinding: (id: string, body: { status?: string; owner?: string; due_on?: string; note?: string }) =>
    request<Finding>(`/monitor/register/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify(body) }),
  conclusion: (vid: string) => request<ConclusionView>(`/validations/${encodeURIComponent(vid)}/conclusion`),
  propose: (vid: string, body: { conclusion: ConclusionId; note: string }) =>
    request<ConclusionView>(`/validations/${encodeURIComponent(vid)}/conclusion`, { method: "POST", body: JSON.stringify(body) }),
  decide: (vid: string, body: { approve: boolean; note: string }) =>
    request<ConclusionView>(`/validations/${encodeURIComponent(vid)}/conclusion/decide`, { method: "POST", body: JSON.stringify(body) }),
};

export const mmsgHref = (vid: string) => apiUrl(`/validations/${encodeURIComponent(vid)}/mmsg.docx`);

export { CRITERION_SHORT, day, fullValidationAsk, person } from "@/components/v5/scorecard/monitor-model";
