/**
 * v5 Admin console client (PLAN_R5 Session A). Talks to the Admin service (port 8510, `NEXT_PUBLIC_ADMIN_API`)
 * with the session cookie. Every configuration change is maker-checker: draft -> submit -> approve -> live.
 *
 * Number formatting follows G5 through Session T's shared formatter (`lib/v5/format.ts`).
 */
import { friendlyError } from "./errors.ts";
export { useEws as useLoad } from "@/lib/v5/ews";

export function adminOrigin(): string {
  return (process.env.NEXT_PUBLIC_ADMIN_API ?? "http://127.0.0.1:8510").replace(/\/$/, "");
}
export const adminUrl = (path: string) => `${adminOrigin()}/api/v1/admin${path}`;
export const convoBase = () => `${adminOrigin()}/api/v1/admin/convo`;

export class AdminError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new AdminError(0, `Admin is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminError(response.status, friendlyError("Admin", response.status, body));
  }
  return body as T;
}
const get = <T,>(p: string) => request<T>(adminUrl(p));
const post = <T,>(p: string, body?: unknown) => request<T>(adminUrl(p), { method: "POST", body: JSON.stringify(body ?? {}) });

// ---------------------------------------------------------------- types
export type Kind = "policy" | "workflow" | "role" | "team" | "user" | "studio" | "setting" | "param";
export interface LiveObject<B = Record<string, unknown>> { kind: Kind; id: string; version: number; body: B; updated_at: string; updated_by: string }
export interface Change<B = unknown> {
  change_id: string; kind: Kind; kind_label: string; object_id: string; op: "create" | "update" | "retire"; title: string;
  body: B; base_version: number | null; status: "draft" | "submitted" | "live" | "rejected" | "withdrawn";
  maker: string; checker: string; created_at: string; submitted_at: string | null; decided_at: string | null; comment: string; source: string;
}
export interface Policy {
  id: string; name: string; status: string; description: string; books: ("corporate" | "retail")[];
  scope: Partial<Record<"corporate" | "retail", Record<string, string[]>>>; modules: string[];
  actions: Record<string, boolean>; mask: { obligor_name: boolean; obligor_id: boolean };
  assignees: { users: string[]; roles: string[]; teams: string[] }; drafted_from?: string;
}
export interface Step {
  id: string; name: string; kind: "action" | "review" | "approve" | "notify"; assignee: { type: string; value?: string };
  sla_days: number; escalate_after_days: number | null; escalate_to: { type: string; value?: string } | null;
  condition: { field: string; op: string; value: unknown }[]; delegation: boolean; note: string;
}
export interface Workflow {
  id: string; name: string; status: string; object_type: string; description: string;
  trigger: { event: string; conditions: { field: string; op: string; value: unknown }[] }; steps: Step[]; drafted_from?: string;
}
export interface SimStep {
  n?: number; step: string; kind: string; assignee?: string; starts?: string; due?: string; sla_days?: number; escalates?: string | null;
  escalate_to?: string | null; delegation?: boolean; notify?: string[]; note?: string; skipped?: boolean; why?: string;
}
export interface Simulation { workflow: string; object: Record<string, unknown>; fires: boolean; timeline: SimStep[]; total_days: number; doa: { level: string; next: string } | null }
export interface Sample { id: string; label: string; [k: string]: unknown }
export interface AdminUser {
  username: string; name: string; title: string; department: string; core_team: string; books: string[]; role: string; team: string;
  rm_id: string; branch_id: string; status: string; last_activity: string; delegate: string; version: number;
  policies: { id: string; name: string }[]; in_core: boolean;
}
export interface Role { id: string; name: string; description: string; modules: string[]; permissions: string[] }
export interface Team { id: string; name: string; core_team: string; lead: string; description: string; branch_id?: string }
export interface Preview {
  user: { username: string; name: string; role: string; team: string; rm_id: string; is_admin: boolean };
  policy: { policies: { id: string; name: string }[]; books: string[]; mask: { obligor_name: boolean; obligor_id: boolean }; unrestricted: boolean;
            scopes: Record<string, Record<string, string[]>[]> };
  modules: { key: string; label: string; allowed: boolean }[]; actions: { key: string; label: string; allowed: boolean }[];
  cockpit: { books: string[]; row_level: string };
  books: { book: string; visible: boolean; total: { customers: number; ead_sar_mn: number; ecl_sar_mn: number };
           seen: { customers: number; ead_sar_mn: number; ecl_sar_mn: number }; sample: Record<string, unknown>[] }[];
}
export interface AiRun {
  run_id: string; at: string; module: string; domain: string; user: string; question: string; mode: string;
  steps: { stage: string; at_ms: number; ms: number }[]; tools: string[]; source: string; model: string; latency_ms: number;
  outcome: string; tokens_in: number; tokens_out: number; cost_usd: number; figures_validated: number; figures_removed: number;
  refusal_reason?: string; seeded: boolean;
}
export interface Daily {
  days: { day: string; runs: number; p50_ms: number; p95_ms: number; cost_usd: number; refused: number; failed: number }[];
  modules: { module: string; runs: number; p50_ms: number; p95_ms: number; cost_usd: number; refusal_rate: number; failure_rate: number }[];
}
export interface EvalRun { id: string; module: string; at: string; by: string; passed: number; total: number;
  results: { question: string; expect_tools: string[]; tools: string[]; pass: boolean; ms: number }[] }
export interface StudioConfig {
  id: string; module: string; title: string; read_only: boolean; model: string; instructions: string; tone: string;
  glossary: { term: string; meaning: string }[]; knowledge: string[]; tools: string[]; known_tools?: string[];
  guardrails: { no_untraced_figure: boolean; scope_refusal: boolean; max_steps: number; refuse_outside_domain: boolean };
  answer_style: { length: string; tables: boolean; charts: boolean }; kill_switch: boolean;
}
export interface Bench { model: string; system_prompt: string; prompt_chars: number; tools_planned: string[]; refused: boolean; refusal: string }
export interface AuditEvent { at: string; actor: string; action: string; label: string; category: string; object: string;
  detail: Record<string, unknown>; source: string; on_behalf_of?: string }
export interface Param { id: string; module: string; name: string; owner: string; version: string; effective_from: string;
  approved_by: string; description: string; source: string; workflow: string }
export interface Feed { feed: string; release: string; as_of: string; files: number; status: string; loaded_at: string }
export interface Item { item_id: string; workflow_id: string; status: string; object_type: string; object_id: string; title: string;
  step: string; assignee: string; opened_at: string; due_at: string; escalated_to?: string }

// ---------------------------------------------------------------- calls
export const admin = {
  overview: () => get<{ policies: number; workflows: number; users: number; pending: Change[]; drafts: Change[]; items: Item[];
    ai_runs: number; refused: number; killed: string[]; me: { username: string; can_approve: boolean } }>("/overview"),
  objects: <B,>(kind: Kind) => get<{ kind: Kind; label: string; objects: LiveObject<B>[]; changes: Change<B>[] }>(`/objects/${kind}`),
  object: <B,>(kind: Kind, id: string) => get<{ object: LiveObject<B>; versions: { version: number; body: B; change_id: string; at: string; by: string }[];
    changes: Change<B>[] }>(`/objects/${kind}/${encodeURIComponent(id)}`),
  changes: (status = "", kind = "") => get<{ changes: Change[] }>(`/changes?status=${status}&kind=${kind}`),
  draft: (kind: Kind, op: "create" | "update" | "retire", body: unknown, title = "", object_id = "", submit = false, source = "console") =>
    request<Change>(adminUrl("/changes"), { method: "POST", body: JSON.stringify({ kind, op, body, title, object_id, submit, source }) }),
  submit: (id: string) => post<Change>(`/changes/${id}/submit`),
  approve: (id: string, comment = "") => post<Change>(`/changes/${id}/approve`, { comment }),
  reject: (id: string, comment = "") => post<Change>(`/changes/${id}/reject`, { comment }),
  withdraw: (id: string) => post<Change>(`/changes/${id}/withdraw`),
  options: () => get<{ fields: Record<string, Record<string, string[]>>; rms: { rm_id: string; rm_name: string; branch_id: string; branch_name: string }[];
    branches: Record<string, { branch_id: string; branch_name: string }[]>; modules: { key: string; label: string }[];
    actions: { key: string; label: string }[]; roles: { id: string; name: string }[]; teams: { id: string; name: string }[] }>("/access/options"),
  preview: (username: string) => get<Preview>(`/access/preview?username=${encodeURIComponent(username)}`),
  previewDraft: (body: unknown, username: string) => post<{ books: Record<string, { customers: number; of: number; ead_sar_mn: number; of_ead_sar_mn: number }> }>(
    "/access/preview-draft", { body, username }),
  samples: () => get<{ samples: Record<string, Sample[]> }>("/workflows/samples"),
  simulate: (workflow: Workflow, object?: Sample) => post<Simulation>("/workflows/simulate", { workflow, object }),
  items: () => get<{ items: Item[] }>("/workflows/items"),
  users: () => get<{ users: AdminUser[]; roles: Role[]; teams: Team[]; changes: Change[] }>("/users"),
  resetPassword: (u: string) => post<{ ok: boolean; message: string }>(`/users/${encodeURIComponent(u)}/reset-password`),
  runs: (q: { module?: string; outcome?: string; user?: string; q?: string } = {}) =>
    get<{ runs: AiRun[]; total: number; all: number; modules: string[]; users: string[] }>(
      `/agent-ops/runs?${new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]).toString()}`),
  run: (id: string) => get<AiRun>(`/agent-ops/runs/${encodeURIComponent(id)}`),
  daily: (module = "") => get<Daily>(`/agent-ops/daily?module=${module}`),
  evals: () => get<{ suites: Record<string, { q: string; expect_tools: string[] }[]>; runs: EvalRun[] }>("/agent-ops/evals"),
  runEval: (module: string) => post<EvalRun>(`/agent-ops/evals/${module}/run`),
  kill: (module: string, on: boolean, reason = "") => post<LiveObject<StudioConfig>>("/agent-ops/kill-switch", { module, on, reason }),
  studio: () => get<{ configs: LiveObject<StudioConfig>[]; changes: Change<StudioConfig>[] }>("/studio"),
  bench: (module: string, question: string, draft?: StudioConfig) =>
    post<{ question: string; live: Bench; draft: Bench | null; diff: string[] }>(`/studio/${module}/test`, { question, draft }),
  settings: () => get<{ settings: LiveObject<{ id: string; name: string; body: Record<string, unknown> }>[]; changes: Change[];
    parameters: Param[]; feeds: Feed[] }>("/settings"),
  audit: (q: { actor?: string; category?: string; q?: string } = {}) =>
    get<{ events: AuditEvent[]; total: number; categories: string[]; actors: string[] }>(
      `/audit?${new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]).toString()}`),
  auditExportUrl: (q: { actor?: string; category?: string; q?: string } = {}) =>
    adminUrl(`/audit/export.xlsx?${new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]).toString()}`),
  me: () => request<{ authenticated: boolean; username?: string; viewing_as?: boolean; modules: Record<string, boolean>;
    actions?: Record<string, boolean>; cockpit_books?: string[]; policy: { policies: { id: string; name: string }[] } }>(
    `${adminOrigin()}/api/v1/access/me`),
};

// ---------------------------------------------------------------- formatting (G5): Session T's shared formatter
import { count as fcount, pct as fpct, sar as fsar } from "@/lib/v5/format";
const nf = (d: number) => new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const sar = (mn: number | null | undefined) => fsar(mn);
export const pct = (fraction: number | null | undefined, d?: number) => fpct(fraction, d === undefined ? {} : { dp: d });
export const count = (n: number | null | undefined) => fcount(n);
export const usd = (n: number | null | undefined) => (n == null ? "–" : `USD ${nf(2).format(n)}`);
export function secs(ms: number | null | undefined): string {
  if (ms == null) return "–";
  return ms < 1000 ? `${nf(0).format(ms)} ms` : `${nf(1).format(ms / 1000)} s`;
}
export function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}

export const MODULE_LABEL: Record<string, string> = {
  cockpit: "Cockpit", early_warning: "Early Warning", borrower_360: "Customer 360", what_if: "What-If", scorecard: "Scorecard Validation",
  deal_desk: "Deal Desk", lenses: "Lenses", playbook: "Playbook", policy_docs: "Policy Docs", projects: "Projects", mail: "Mail",
  data_builder: "Data Domains", admin: "Admin",
};
export const OBJECT_LABEL: Record<string, string> = {
  ews_name: "Early Warning name", deal_proposal: "Deal Desk proposal", playbook_report: "Playbook report",
  whatif_scenario: "What-If scenario", parameter_table: "Parameter table",
};
export const ROLE_LABEL: Record<string, string> = { admin: "Admin", cro: "CRO", analyst: "Credit Risk Analyst", rm: "RM", auditor: "Auditor", validator: "Model Validator" };
export const TEAM_LABEL: Record<string, string> = {
  "T-ADM": "Administration", "T-CRM": "Credit Risk Management", "T-CORP": "Corporate Credit", "T-RET": "Retail Credit",
  "T-MV": "Model Validation", "T-RMC": "Riyadh RMs", "T-IA": "Internal Audit",
};
export const FIELD_LABEL: Record<string, string> = {
  sectors: "Sectors", sub_sectors: "Sub-sectors", regions: "Regions", branches: "Branches", rm_ids: "RM portfolios",
  segments: "Segments", business_units: "Business units",
};
export function assigneeText(a: { type: string; value?: string } | null | undefined, users: Record<string, string> = {}): string {
  if (!a) return "–";
  switch (a.type) {
    case "user": return users[a.value ?? ""] ?? a.value ?? "";
    case "role": return ROLE_LABEL[a.value ?? ""] ?? a.value ?? "";
    case "team": return TEAM_LABEL[a.value ?? ""] ?? `Team ${a.value}`;
    case "rm_of_object": return "The borrower's RM";
    case "owner_of_object": return "The owner";
    case "doa_level": return "Approver at the DOA level";
    case "doa_next": return "Next DOA level";
    default: return a.value ?? a.type;
  }
}
