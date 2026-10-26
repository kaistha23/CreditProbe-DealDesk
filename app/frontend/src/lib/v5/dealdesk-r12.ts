/**
 * R12 Session U: the Deal Desk shell client and its pure helpers (PLAN_R12 §1.1, §1.2; I1, I15, I17, I21, I23, I30, O2).
 *
 * Talks to the Deal Desk engine (port 8508, `NEXT_PUBLIC_DEALDESK_API`) under /api/v1/dealdesk:
 *   GET  /landing/cards                 the six landing cards (counts and filtered rows)
 *   GET  /workflow                      states, transitions and the caller's view (Prepare or Review)
 *   GET  /proposals/{id}/workflow       a deal's state, history, allowed transitions and pipeline banner
 *   POST /proposals/{id}/workflow       {to, note?} -> the new state
 * Self-contained (no path aliases) so the helpers run under `node --test`.
 */
import { friendlyError } from "./errors.ts";

// ---------------------------------------------------------------- the deal steps (I15, I1, O2)

/** PLAN_R14 (K23, K31): Upload · Proposal check · Review · Analysis · Structure · Recommendation; Stress is a header
 * button from Structure on, reached at ?step=stress (R14 F). Before (PLAN_R12 §1.2): Proposal · Review · Analysis · Stress · Structure · Recommendation. */
export const R12_STEP_ORDER = ["proposal", "proposal-check", "review", "analysis", "structure", "recommendation"] as const;
export type R12StepKey = (typeof R12_STEP_ORDER)[number] | "stress";
/** I1: every deal opens on Proposal. */
export const LANDING_STEP: R12StepKey = "proposal";

export function parseStep(s: string | null | undefined): R12StepKey {
  return s === "stress" || (R12_STEP_ORDER as readonly string[]).includes(String(s)) ? (s as R12StepKey) : LANDING_STEP;
}

/**
 * O2: a tick means "visited and done", never "computed". Proposal, Review, Analysis and Stress are done once visited;
 * Structure once visited with an optimisation on screen; Recommendation once visited with a saved recommendation.
 */
export function stepDone(key: R12StepKey, visited: ReadonlySet<string>, ctx: { hasOpt: boolean; hasRec: boolean }): boolean {
  if (!visited.has(key)) return false;
  if (key === "structure") return ctx.hasOpt;
  if (key === "recommendation") return ctx.hasRec;
  return true;
}

export function doneSet(visited: ReadonlySet<string>, ctx: { hasOpt: boolean; hasRec: boolean }): Set<string> {
  return new Set([...R12_STEP_ORDER, "stress" as const].filter((k) => stepDone(k, visited, ctx)));
}

const visitedKey = (pid: string) => `dealdesk.visited.${pid}`;

/** The steps visited on this deal in this browser (per-viewer convenience; every storage call guarded). */
export function readVisited(pid: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(visitedKey(pid));
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(arr) ? arr.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

export function writeVisited(pid: string, v: ReadonlySet<string>): void {
  try {
    window.localStorage.setItem(visitedKey(pid), JSON.stringify([...v]));
  } catch { /* storage blocked: the ticks last the visit */ }
}

// ---------------------------------------------------------------- roles and views (I17)

export type Side = "admin" | "rm" | "credit" | "viewer";
export type View = "prepare" | "review";

/** Mirrors backend/dealdesk/workflow.side_of: the Users & Teams role of the effective user. */
export function sideOf(user: { role?: string; is_admin?: boolean } | null | undefined): Side {
  if (!user) return "viewer";
  if (user.is_admin) return "admin";
  const r = String(user.role ?? "").trim().toLowerCase();
  if (r.includes("relationship manager") || r === "rm" || r === "business") return "rm";
  if (["credit", "risk", "committee", "cro", "analyst"].some((k) => r.includes(k))) return "credit";
  return "viewer";
}

export const viewOf = (side: Side): View => (side === "rm" ? "prepare" : "review");
export const VIEW_LABEL: Record<View, string> = { prepare: "Prepare", review: "Review" };

// ---------------------------------------------------------------- the action bar (I23)

export type ActionKey = "write" | "review" | "optimise" | "committee" | "documents" | "word" | "report";
export const ACTIONS: { key: ActionKey; label: string }[] = [
  { key: "write", label: "Write proposal" },
  { key: "review", label: "Review proposal" },
  { key: "optimise", label: "Optimise" },
  { key: "committee", label: "Committee paper" },
  { key: "documents", label: "Documents" },
  { key: "word", label: "Word" },
  { key: "report", label: "Add to report" },
];

/** The one primary action of the bar: Write proposal for business (Prepare), Review proposal for credit (Review). */
export const primaryAction = (view: View): ActionKey => (view === "prepare" ? "write" : "review");

export function documentsLabel(missing: number | null | undefined): string {
  return typeof missing === "number" && missing > 0 ? `Documents (${missing})` : "Documents";
}

// ---------------------------------------------------------------- landing tabs (I30)

export const TABS = [
  { key: "origination", label: "Origination" },
  { key: "book", label: "Book" },
  { key: "monitoring", label: "Monitoring" }, // R14 F (K35): the Monitoring page, a header button next to Book
  { key: "params", label: "Parameters & policy" },
] as const;
export type TabKey = (typeof TABS)[number]["key"];
export const parseTab = (s: string | null | undefined): TabKey => (TABS.some((t) => t.key === s) ? (s as TabKey) : "origination");

// ---------------------------------------------------------------- schemas

export interface WorkflowState { key: string; label: string; side: "business" | "credit" }
export interface WorkflowEvent {
  event_id: string; proposal_id: string; seq: number; from_state: string; to_state: string; from_label: string; to_label: string;
  actor: string; actor_role: string; role_label: string; note: string; at: string;
}
export interface PipelineBanner {
  proposal_id: string; source: "pipeline" | "dealdesk" | ""; in_pipeline: boolean; back_href: string;
  decision: { decision: "approve" | "decline" | string; structure: string | null; amount_sar_mn: number | null; reason: string;
              gets_in: string | null; headline: string } | null;
}
export interface DealWorkflow {
  proposal_id: string; state: string; label: string; since: string; events: number; states: WorkflowState[];
  history: WorkflowEvent[]; view: View; side: Side; actions: { to: string; label: string; by: string }[]; banner: PipelineBanner;
}
export interface CardRow {
  proposal_id: string; obligor_name: string; sector: string; rating: string; amount_sar_mn: number | null; rm: string;
  state: string; state_label: string; since: string; days: number | null; source: string; href: string;
  queries_open: number; committee_date: string | null; product: string;
}
export interface LandingCard {
  key: string; title: string; source: "workflow" | "book" | "conditions" | "products"; info: string; count: number; rows: CardRow[];
  href: string; available: boolean; sub: string;
}
export interface LandingCards { as_of: string; today: string; cards: LandingCard[] }

/** The workflow path drawn on the deal page (Declined shows only when the deal is declined). */
export function pathStates(states: WorkflowState[], current: string): WorkflowState[] {
  return states.filter((s) => s.key !== "declined" || current === "declined");
}

export function stateTone(state: string): "neutral" | "accent" | "warning" | "positive" | "negative" {
  if (state === "approved") return "positive";
  if (state === "declined") return "negative";
  if (state === "queries") return "warning";
  if (state === "draft" || state === "submitted" || state === "renewal_opened") return "neutral";
  return "accent";
}

export function bannerLine(b: PipelineBanner | null | undefined): string {
  const d = b?.decision;
  if (!d) return "";
  const verb = d.decision === "approve" ? "Approve" : d.decision === "decline" ? "Decline" : d.decision;
  return `${verb}${d.structure ? `: ${d.structure}` : ""}`;
}

// ---------------------------------------------------------------- client

export function r12Origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}
const ENGINE = "/api/v1/dealdesk";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${r12Origin()}${url}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(friendlyError("Deal Desk", response.status, body));
  return body as T;
}

const enc = encodeURIComponent;
export const r12Api = {
  cards: () => request<LandingCards>(`${ENGINE}/landing/cards`),
  workflow: (id: string, banner = true) => request<DealWorkflow>(`${ENGINE}/proposals/${enc(id)}/workflow${banner ? "" : "?banner=0"}`),
  documentsMissing: (id: string) =>
    request<{ proposal_id: string; required: number; missing: number | null }>(`${ENGINE}/proposals/${enc(id)}/documents/missing`),
  move: (id: string, to: string, note = "") =>
    request<DealWorkflow & { event: WorkflowEvent }>(`${ENGINE}/proposals/${enc(id)}/workflow`, { method: "POST", body: JSON.stringify({ to, note }) }),
};
