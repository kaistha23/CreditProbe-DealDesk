/**
 * R11 agents client (PLAN_R11_AGENTS, Session G): the agents service on port 8517
 * (`NEXT_PUBLIC_AGENTS_API`), with the session cookie. Types mirror backend/agents_v5/runtime/types.py.
 *
 *   startRun(agent, goal, context)    POST /api/v1/agents/{agent}/runs   (returns the queued run; poll getRun)
 *   getRun(runId)                     GET  /api/v1/agents/runs/{runId}
 *   listRuns({ agent, scope })        GET  /api/v1/agents/runs
 *   decide(approvalId, decision)      POST /api/v1/agents/approvals/{id}/decision
 *
 * The pure helpers below (progress, step and severity labels, evidence links) are unit tested.
 */
import { friendlyError } from "./errors.ts";

export function agentsOrigin(): string {
  return (process.env.NEXT_PUBLIC_AGENTS_API ?? "http://127.0.0.1:8517").replace(/\/$/, "");
}
const BASE = "/api/v1/agents";

export class AgentsError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${agentsOrigin()}${BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new AgentsError(0, "The agents service is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new AgentsError(response.status, friendlyError("The agent", response.status, body));
  return body as T;
}

// ---------------------------------------------------------------- types

export type StepStatus = "pending" | "running" | "done" | "skipped" | "failed";
export type RunStatus = "queued" | "running" | "completed" | "partial" | "failed";
export type Severity = "critical" | "major" | "minor" | "info";

export interface AgentStep {
  id: string;
  tool: string;
  inputs: Record<string, unknown>;
  why: string;
  status: StepStatus;
  summary: string;
  figures: Record<string, number>;
  output?: unknown;
  duration_ms: number;
  error: string;
  added_by: string;
  trace_id: string;
}

export interface AgentPlan {
  schema: string;
  goal: string;
  agent: string;
  planner: "deterministic" | "model" | "recorded" | string;
  goal_type: string;
  context: Record<string, unknown>;
  notes: string[];
  steps: AgentStep[];
}

export interface AgentFinding {
  title: string;
  severity: Severity;
  detail: string;
  evidence: string[];
  kind: string;
  data: Record<string, unknown>;
}

export interface AgentApproval {
  id: string;
  kind: string;
  title: string;
  reason: string;
  change: Record<string, unknown>;
  evidence: string[];
  agent: string;
  run_id: string;
  maker: string;
  approver_role: string;
  status: "pending" | "approved" | "rejected" | "expired" | string;
  created_at: string;
  expires_at: string;
  decided_by: string;
  decided_at: string;
  note: string;
  applied: { applied: boolean; note?: string; error?: string } | null;
}

export interface AgentRun {
  run_id: string;
  agent: string;
  goal: string;
  context: Record<string, unknown>;
  trigger: string;
  scope: string;
  status: RunStatus;
  plan: AgentPlan | null;
  findings: AgentFinding[];
  narrative: string;
  output: Record<string, unknown> & { headline?: string; timing?: { run_ms: number; steps: { id: string; tool: string; ms: number }[] } };
  proposals: string[];
  approvals?: AgentApproval[];
  budget: { limits?: Record<string, number>; spent?: Record<string, number> };
  stopped: string;
  user: string;
  created_at: string;
  finished_at: string;
  duration_ms: number;
  model: string;
  citation_check: { ok?: boolean; removed?: number };
}

export interface AgentRunSummary {
  run_id: string;
  agent: string;
  goal: string;
  scope: string;
  trigger: string;
  status: RunStatus;
  planner: string;
  created_at: string;
  finished_at: string;
  duration_ms: number;
  steps: number;
  steps_done: number;
  findings: number;
  proposals: number;
  headline: string;
}

export interface AgentSchedule {
  id: string;
  agent: string;
  cron: string;
  goal: string;
  enabled: boolean;
  last_fired: string;
  last_run: string;
  runs: number;
}

// ---------------------------------------------------------------- calls

export const startRun = (agent: string, goal: string, context: Record<string, unknown> = {}, planner = "auto") =>
  request<AgentRun>(`/${encodeURIComponent(agent)}/runs`, { method: "POST", body: JSON.stringify({ goal, context, planner }) });

export const getRun = (runId: string) => request<AgentRun>(`/runs/${encodeURIComponent(runId)}`);

export const listRuns = (q: { agent?: string; scope?: string; limit?: number } = {}) => {
  const p = new URLSearchParams();
  if (q.agent) p.set("agent", q.agent);
  if (q.scope) p.set("scope", q.scope);
  if (q.limit) p.set("limit", String(q.limit));
  return request<{ runs: AgentRunSummary[]; schedules: AgentSchedule[] }>(`/runs?${p.toString()}`);
};

/** R15 L5: the approvals queue (e.g. proposals still pending from an earlier run, decidable from the new run's table). */
export const listApprovals = (q: { agent?: string; status?: string; run_id?: string; scope?: string } = {}) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
  return request<{ approvals: AgentApproval[] }>(`/approvals?${p.toString()}`);
};

export const decide = (approvalId: string, decision: "approve" | "reject", note = "") =>
  request<AgentApproval>(`/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST", body: JSON.stringify({ decision, note }),
  });

// ---------------------------------------------------------------- pure helpers

export const isFinished = (s: RunStatus | undefined): boolean => s === "completed" || s === "partial" || s === "failed";

/** "4 of 11 steps" and the share for a progress bar; skipped and failed steps count as settled. */
export function progress(plan: AgentPlan | null | undefined): { settled: number; total: number; share: number; label: string } {
  const steps = plan?.steps ?? [];
  const settled = steps.filter((s) => s.status === "done" || s.status === "skipped" || s.status === "failed").length;
  const total = steps.length;
  return { settled, total, share: total ? settled / total : 0, label: total ? `${settled} of ${total} steps` : "Planning" };
}

/** A tool id in words: dd_forward_risk -> "Forward risk". */
export function toolLabel(tool: string): string {
  const t = tool.replace(/^(dd|ews|wi|whatif|lens|lenses)_/, "").replace(/_/g, " ").trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : tool;
}

export function stepTone(s: StepStatus): "positive" | "negative" | "warning" | "neutral" | "accent" {
  return s === "done" ? "positive" : s === "failed" ? "negative" : s === "skipped" ? "warning" : s === "running" ? "accent" : "neutral";
}

export function severityTone(s: Severity | string): "negative" | "warning" | "neutral" | "accent" {
  return s === "critical" ? "negative" : s === "major" ? "warning" : s === "minor" ? "accent" : "neutral";
}

const SEV: Record<string, number> = { critical: 0, major: 1, minor: 2, info: 3 };
export function bySeverity(f: AgentFinding[]): AgentFinding[] {
  return [...f].sort((a, b) => (SEV[a.severity] ?? 9) - (SEV[b.severity] ?? 9));
}

export function severityCounts(f: AgentFinding[]): Record<Severity, number> {
  const out: Record<Severity, number> = { critical: 0, major: 0, minor: 0, info: 0 };
  for (const x of f) if (x.severity in out) out[x.severity] += 1;
  return out;
}

/** "S3" or "S3:rule" -> the step it cites. */
export function evidenceStep(ref: string): string {
  return ref.split(":")[0];
}

/** Splits a narrative into text and citation parts: "RAROC 12.1% [S3]." -> text, cite S3, text. */
export function citationParts(text: string): { text?: string; cite?: string[] }[] {
  const out: { text?: string; cite?: string[] }[] = [];
  const re = /\[(S\d+(?:\s*,\s*S\d+)*)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    out.push({ cite: m[1].split(",").map((s) => s.trim()) });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

export function plannerLabel(run: Pick<AgentRun, "model"> & { plan: Pick<AgentPlan, "planner"> | null }): string {
  if (!run.plan) return "Planning";
  return run.plan.planner === "model" ? `Planned by ${run.model || "the model"}` : "Written plan (deterministic)";
}

export function duration(ms: number | null | undefined): string {
  if (!ms && ms !== 0) return "";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

export const tracePath = (runId: string) => `/trace/agent/${encodeURIComponent(runId)}`;

/** Whether a role may decide (mirrors backend approvals.ROLE_RANK). */
const RANK: Record<string, number> = { VIEWER: 0, ANALYST: 1, RM: 1, DATA_STEWARD: 2, CREDIT_OFFICER: 2, RISK_MANAGER: 2, ADMIN: 3, CCO: 3, CRO: 3 };
export function normRole(role: string | null | undefined): string {
  const r = String(role ?? "").trim().toUpperCase().replace(/ /g, "_");
  return r === "ADMINISTRATOR" ? "ADMIN" : r === "USER" ? "ANALYST" : r;
}
export function mayDecide(role: string | null | undefined, approval: Pick<AgentApproval, "approver_role" | "status" | "maker">, user?: string): boolean {
  if (approval.status !== "pending") return false;
  if (user && user === approval.maker) return false;
  return (RANK[normRole(role)] ?? -1) >= (RANK[approval.approver_role] ?? 99);
}
