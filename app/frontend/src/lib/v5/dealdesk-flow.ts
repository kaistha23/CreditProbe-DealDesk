/**
 * R14 Session F: the Deal Desk flow client and its pure helpers (PLAN_R14 "f": K20, K21, K23, K24, K25, K35).
 *
 * Talks to the Deal Desk engine (port 8508, `NEXT_PUBLIC_DEALDESK_API`) under /api/v1/dealdesk:
 *   GET  /proposals/{id}/structure-set            Ask · Recommended · Alternatives · Your structures, the selection, the sticky bar
 *   POST /proposals/{id}/structure-set/select     {key}
 *   POST /proposals/{id}/structure-set            {label, terms, covenants?, select?}
 *   POST /proposals/{id}/stress-matrix            {keys?, force?}
 *   POST /proposals/{id}/stress-proof             {from_key?, target?}
 *   GET  /proposals/{id}/recommendation-r14
 *   GET  /proposals/{id}/pipeline-lines?key=
 *   GET  /monitoring/proposals/prefill · POST /monitoring/proposals · POST /monitoring/proposals/{id}/decide · GET /monitoring/page
 *   GET  /monitoring/proposals/obligor/{id}
 * Self-contained (no path aliases) so the helpers run under `node --test`.
 */
import { friendlyError } from "./errors.ts";

// ---------------------------------------------------------------- the steps (K23 (1), K31)

/** Upload · Proposal check · Review · Analysis · Structure · Recommendation; Stress is a header button from Structure on. */
export const FLOW_STEPS = [
  { key: "proposal", label: "Upload" },
  { key: "proposal-check", label: "Proposal check" },
  { key: "review", label: "Review" },
  { key: "analysis", label: "Analysis" },
  { key: "structure", label: "Structure" },
  { key: "recommendation", label: "Recommendation" },
] as const;
export type FlowStepKey = (typeof FLOW_STEPS)[number]["key"] | "stress";

/** The Stress button is enabled once the deal has reached Structure (on Structure or Recommendation, or Structure visited). */
export function stressEnabled(step: string, visited: ReadonlySet<string>): boolean {
  return step === "structure" || step === "recommendation" || step === "stress" || visited.has("structure");
}

export const STRESS_DISABLED_REASON = "Available from the Structure step: choose the structures to stress first";

// ---------------------------------------------------------------- schemas

export interface Approval { level: string; rank?: number | null; rule: string; reasons: string[]; source: string }
export interface Capacity { method: string; capacity_sar_mn: number; ask_sar_mn: number; passes: boolean; formula: string; source: string }
export interface CovenantBase { type: string; threshold: number; value: number | null; headroom: number | null; status: string }
export interface StructureRow {
  key: string; label: string; role: "ask" | "recommended" | "alternative" | "user" | "stress_proofed"; group: string; origin: string;
  terms: Record<string, unknown>; covenants: { type: string; threshold: number }[] | null; conditions_precedent: string[];
  raroc: number; hurdle: number; clears_hurdle: boolean; sva: number; sva_basis: string; sva_label: string;
  dscr: number | null; debt_ebitda: number | null; covenants_base: CovenantBase[]; covenant_headroom: number | null; covenant_tightest: string | null;
  capacity: Capacity; approval: Approval; hard_breaches: string[]; recommendable: boolean; not_recommendable_reason: string;
  fails_before_stress: boolean; selected: boolean;
}
export interface Regime { label: string; key: string; brent: number | null; month: string | null; chg_12m: number | null; percentile: number | null; vintage: string; source: string }
export interface StructureSet {
  proposal_id: string; obligor: string; rows: StructureRow[]; groups: { group: string; keys: string[] }[]; selected: string;
  selected_by_user: boolean; default_note: string | null; bar: { label: string; key: string; enabled: boolean; reason: string };
  plain_words: string[]; regime: Regime; sva_basis: string; added?: string;
}
export interface MatrixCell {
  severity: "mild" | "moderate" | "severe"; scenarios: number; passes: boolean; breaking: string[]; worst_raroc: number | null; min_dscr: number | null;
  min_covenant_headroom: number | null; worst_stage: number | null; limits: string[];
  first_break: { id: string; label: string; tests: string[]; test_labels: string[] } | null;
}
export interface MatrixStructure {
  key: string; label: string; role: string; raroc: number; hurdle: number; sva: number; sva_basis: string; dscr: number | null;
  covenant_headroom: number | null; approval: Approval; fails_before_stress: boolean; base_reason: string;
  status: "stressed" | "fails_before_stress"; stressed: boolean; forced?: boolean; cells: MatrixCell[]; survives_up_to: "none" | "mild" | "moderate" | "severe";
  verdict?: string; tier?: string; drivers?: string[]; run_id?: string;
  interpretation: string | { first: string; why: string; survives: string; lines: string[] };
}
export interface StressMatrix {
  proposal_id: string; obligor: string; keys: string[]; structures: MatrixStructure[]; severities: string[]; regime: Regime; regime_line: string;
  drivers: string[]; survival_rule: string; sensitivity_version: string | null; plain_words: string[]; basis: string;
  /** R15 b (L8 (b)): how to read the matrix and what breaks first, in plain words. */
  how_to_read?: string[];
}
export interface ProofChange { lever: string; field: string; from: unknown; to: unknown; text: string; client: string; cost: string }
export interface StressProof {
  proposal_id: string; new_key: string; label: string; survives: boolean; changes: ProofChange[]; uncured: string[];
  interpretation: { changes: string; cost: string; client: string; lines: string[] }; matrix: StressMatrix; structure_set: StructureSet;
  plain_words: string[]; proof: { proof_id: string; target_severity: string }; added: boolean;
}
export interface RecFinding { title: string; severity: "critical" | "major"; category: string; source: string; cure_kind: string; cure: string; owner?: string; when?: string }
export interface Recommendation {
  proposal_id: string; obligor: string;
  structure: { key: string; label: string; role: string; origin: string; terms: Record<string, unknown>; raroc: number; hurdle: number; sva: number; sva_label: string; dscr: number | null; recommendable: boolean };
  default_note: string | null; decision: { label: string; tone: "positive" | "warning" | "negative"; why: string; points: string[] };
  approval: Approval; strengths: { text: string; source: string }[]; risks: { text: string; source: string }[]; findings: RecFinding[];
  conditions_precedent: { text: string; owner: string; due: string }[];
  covenants: { type: string; threshold: number; today: number | null; headroom: number | null; status: string }[];
  monitoring: { tier: string; review_frequency_months: number; triggers: { label: string; metric?: string; op?: string; threshold?: number }[] };
  owners: { what: string; owner: string; due: string }[]; proofed_to: string | null; stress: { survives_up_to: string | null; first_break: string };
  plain_words: string[]; as_of: string;
}
export interface PipelineLine {
  line: string; name: string; scope: string; before: number | null; after: number | string | null; limit: number | string | null; unit: string;
  headroom: number | null; room_times_deal: number | null; kind: string; rag: "green" | "amber" | "red"; changed: boolean;
}
export interface PipelineLines {
  proposal_id: string; purpose: string; structure: { key: string; label: string }; label_line: string; verdict: string; makes_cut: boolean; fits: boolean;
  rank: number; ranked: number; sva: { value: number; basis: string; label: string }; value_change: number | null; value_text: string | null;
  displaced: { proposal_id: string; obligor: string; sva: number; rwa: number }[];
  resized: { proposal_id: string; obligor: string; from: string; to: string; text: string }[]; displaces_count: number; displaces_text: string;
  closest_limit: string | null; closest_short: { label: string; room: string; scope: string } | null; lines: PipelineLine[]; rag_legend: Record<string, string>; plain_words: string[];
  pipeline: { deals: number; rwa_budget: number } | null;
}
export interface MonitoringTrigger { metric?: string; operator?: string; threshold?: number; label: string }
export interface MonitoringPrefill {
  proposal_id: string; obligor_id: string; obligor_name: string; facility_ref: string; source_screen: string; tier: "High" | "Medium" | "Standard";
  reason: string; evidence: { label: string; value: string; relation: string }[]; review_frequency: string; triggers: MonitoringTrigger[];
  owner: string; due_date: string; tiers: string[]; frequencies: string[]; plain_words: string[];
}
export interface MonitoringProposal {
  monitoring_proposal_id: string; subject_kind: string; proposal_id: string; obligor_id: string; obligor_name: string; facility_ref: string;
  source_screen: string; tier: string; previous_tier: string; reason: string; review_frequency: string; triggers_json: MonitoringTrigger[];
  evidence_json: { label: string; value: string }[]; owner: string; due_date: string; status: "proposed" | "active" | "rejected" | "closed";
  maker: string; made_at: string; checker: string; decided_at: string | null; decision_note: string; triggers_hit_json: { label: string; value: unknown; at: string }[];
  applied?: string; own?: boolean;
}
export interface MonitoringPage {
  as_of: string; today: string; proposed: MonitoringProposal[]; active: MonitoringProposal[]; active_by_tier: Record<string, number>;
  triggers_hit: MonitoringProposal[]; reviews_due: MonitoringProposal[]; history: MonitoringProposal[]; plain_words: string[];
  counts: { proposed: number; active: number; due_30d: number; triggers_hit: number };
}
export interface ObligorMonitoring { obligor_id: string; active: MonitoringProposal | null; proposed: MonitoringProposal | null; line: string | null }

export interface SwotPoint { id: string; quadrant: "strength" | "weakness" | "opportunity" | "threat"; theme: string; text: string;
  evidence?: { domain?: string; relation?: string }[] }

/** K25 (3): the SWOT in one card: top strengths and weaknesses with their sources. */
export function swotSummary(points: SwotPoint[], n = 3): { strengths: SwotPoint[]; weaknesses: SwotPoint[]; counts: Record<string, number> } {
  const counts: Record<string, number> = { strength: 0, weakness: 0, opportunity: 0, threat: 0 };
  for (const p of points) counts[p.quadrant] = (counts[p.quadrant] ?? 0) + 1;
  return { strengths: points.filter((p) => p.quadrant === "strength").slice(0, n),
           weaknesses: points.filter((p) => p.quadrant === "weakness" || p.quadrant === "threat").slice(0, n), counts };
}

export function evidenceSource(p: SwotPoint): string {
  const s = [...new Set((p.evidence ?? []).map((e) => [e.domain, e.relation].filter(Boolean).join(".")).filter(Boolean))];
  return s.join(", ") || "SWOT";
}

// ---------------------------------------------------------------- pure helpers

export const SEVERITIES = ["mild", "moderate", "severe"] as const;
export type Severity = (typeof SEVERITIES)[number];

export function pct(v: number | null | undefined, dp = 1): string {
  return v == null || !Number.isFinite(v) ? "–" : `${(v * 100).toFixed(dp)}%`;
}
export function x(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${v.toFixed(2)}x`;
}
export function sarm(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  if (Math.abs(v) < 0.005) v = 0; // no "−0.00"
  const a = Math.abs(v);
  return `SAR ${v < 0 ? "−" : ""}${a.toLocaleString("en-US", { minimumFractionDigits: a < 10 ? 2 : 1, maximumFractionDigits: a < 10 ? 2 : 1 })}m`;
}

/** "Survives up to moderate" / "Breaks at the mildest shock" / "Not stressed: fails before stress". */
export function survivalLabel(s: Pick<MatrixStructure, "status" | "survives_up_to">): string {
  if (s.status === "fails_before_stress") return "Fails before stress";
  if (s.survives_up_to === "severe") return "Survives severe";
  if (s.survives_up_to === "none") return "Breaks at mild";
  return `Survives up to ${s.survives_up_to}`;
}

export function survivalTone(s: Pick<MatrixStructure, "status" | "survives_up_to">): "positive" | "warning" | "negative" | "neutral" {
  if (s.status === "fails_before_stress") return "neutral";
  return s.survives_up_to === "severe" ? "positive" : s.survives_up_to === "moderate" ? "positive" : s.survives_up_to === "mild" ? "warning" : "negative";
}

/** The rows of the structure set in display order, grouped. */
export function grouped(set: StructureSet): { group: string; rows: StructureRow[] }[] {
  const by = new Map(set.rows.map((r) => [r.key, r]));
  return set.groups.map((g) => ({ group: g.group, rows: g.keys.map((k) => by.get(k)).filter((r): r is StructureRow => Boolean(r)) }));
}

/** The default stress choice: the selected structure and the ask (K20: the ask is always one of the defaults). */
export function defaultStressKeys(set: StructureSet): string[] {
  return set.selected === "ask" ? ["ask"] : [set.selected, "ask"];
}

export function interpretationLines(i: MatrixStructure["interpretation"]): string[] {
  return typeof i === "string" ? [i] : i.lines;
}

export function sourceLabel(row: { relation?: string; source: string }): string {
  return row.source;
}

export const TIER_TONE: Record<string, "negative" | "warning" | "positive"> = { High: "negative", Medium: "warning", Standard: "positive" };

/** The proposal-from-a-list subject for Propose for monitoring. */
export interface MonitoringSubject {
  proposalId?: string | null; obligorId?: string | null; obligorName?: string; facilityRef?: string | null; source: string; reason?: string;
}

export function prefillQuery(s: MonitoringSubject): string {
  const q = new URLSearchParams();
  if (s.proposalId) q.set("proposal_id", s.proposalId);
  if (s.obligorId) q.set("obligor_id", s.obligorId);
  q.set("source", s.source);
  if (s.facilityRef) q.set("facility_ref", s.facilityRef);
  if (s.obligorName) q.set("obligor_name", s.obligorName);
  if (s.reason) q.set("reason", s.reason.slice(0, 300));
  return q.toString();
}

// ---------------------------------------------------------------- client

export function flowOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}
const ENGINE = "/api/v1/dealdesk";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${flowOrigin()}${url}`, {
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
const post = <T>(url: string, body: unknown) => request<T>(url, { method: "POST", body: JSON.stringify(body ?? {}) });
const enc = encodeURIComponent;

export const flowApi = {
  structureSet: (id: string) => request<StructureSet>(`${ENGINE}/proposals/${enc(id)}/structure-set`),
  select: (id: string, key: string) => post<StructureSet>(`${ENGINE}/proposals/${enc(id)}/structure-set/select`, { key }),
  save: (id: string, label: string, terms: Record<string, unknown>, select = true) =>
    post<StructureSet>(`${ENGINE}/proposals/${enc(id)}/structure-set`, { label, terms, select }),
  matrix: (id: string, keys: string[], force: string[] = []) => post<StressMatrix>(`${ENGINE}/proposals/${enc(id)}/stress-matrix`, { keys, force }),
  proof: (id: string, fromKey: string, target: Severity) => post<StressProof>(`${ENGINE}/proposals/${enc(id)}/stress-proof`, { from_key: fromKey, target }),
  recommendation: (id: string) => request<Recommendation>(`${ENGINE}/proposals/${enc(id)}/recommendation-r14`),
  pipelineLines: (id: string, key?: string) => request<PipelineLines>(`${ENGINE}/proposals/${enc(id)}/pipeline-lines${key ? `?key=${enc(key)}` : ""}`),
  prefill: (s: MonitoringSubject) => request<MonitoringPrefill>(`${ENGINE}/monitoring/proposals/prefill?${prefillQuery(s)}`),
  propose: (body: Record<string, unknown>) => post<MonitoringProposal>(`${ENGINE}/monitoring/proposals`, body),
  decide: (mid: string, approve: boolean, note = "") => post<MonitoringProposal>(`${ENGINE}/monitoring/proposals/${enc(mid)}/decide`, { approve, note }),
  monitoringPage: () => request<MonitoringPage>(`${ENGINE}/monitoring/page`),
  swot: (id: string) => request<{ swot: { summary?: string; points: SwotPoint[] } }>(`${ENGINE}/proposals/${enc(id)}/group/swot`).then((r) => r.swot),
  obligorMonitoring: (oid: string) => request<ObligorMonitoring>(`${ENGINE}/monitoring/proposals/obligor/${enc(oid)}`),
};
