/**
 * R11 Session L: the Deal Desk pipeline client and its pure helpers (PLAN_R11 L1, L4–L6).
 *
 * Talks to the Deal Desk engine (port 8508, `NEXT_PUBLIC_DEALDESK_API`) under /api/v1/dealdesk:
 *   GET  /pipeline, POST /pipeline/optimise, POST /proposals/{id}/pipeline-test, GET /risk-appetite.
 * Every figure comes from the engine; these helpers only format and lay out. Money is SAR million.
 * Self-contained (no path aliases) so the helpers run under `node --test`.
 */
import { friendlyError } from "./errors.ts";
import { pct, sar } from "./format.ts";

// ---------------------------------------------------------------- schemas

export type LimitStatus = "green" | "amber" | "red" | "n/a";

export interface PipelineDeal {
  proposal_id: string; status: string; obligor_name: string; obligor_id: string; existing: boolean; sector: string; rating: string;
  rm: string; facility_type: string; structure: string; currency: string; amount: number; amount_sar_mn: number; tenor_years: number;
  received: string; case: string; source: "Deal Desk" | "Uploaded" | "Pipeline set"; region: string; group_id: string; group_name: string;
  purpose: string;
}
export interface PipelineListing {
  trace_id: string; as_of: string; deals: PipelineDeal[]; count: number; by_source: Record<string, number>;
  budgets: { rwa: number; el: number; rwa_basis: string; el_basis: string }; amount_sar_mn: number;
}
export interface DealOption {
  index: number; kind: "ask" | "recommended" | "reduced" | "picked"; label: string; amount_sar_mn: number; sva: number;
  lifetime_raroc: number | null; rwa: number; el: number; ead: number; available: boolean; deal_hard_breaches: string[];
  deal_soft_breaches: string[]; approval: string; clears_hurdle: boolean; secured: boolean; islamic: boolean; tenor_years: number;
  stage2_weight: number; stage2_basis: string; structure: string; facility_type: string;
}
export interface LimitRow {
  name: string; label: string; scope: string; kind: "hard" | "soft"; unit: string; direction: "max" | "min" | "rating" | "deal";
  appetite: number | string | null; trigger: number | string | null; limit: number | string | Record<string, number> | null;
  before: number | null; after: number | null; status_before: LimitStatus; status: LimitStatus; above_appetite: boolean;
  headroom: number | null; basis: string; definition: string; r11: boolean; value?: number | null; delta?: number | null;
  before_text?: string; after_text?: string;
}
export interface Decision extends PipelineDeal {
  decision: "approve" | "decline"; option: DealOption | null; reason: string; options: DealOption[]; sva_per_100m_rwa: number | null;
  gets_in?: { possible: boolean; text: string; sva_gap?: number; bps?: number | null; displaces?: string[]; violates?: string[] };
}
export interface Binding { name: string; label: string; scope: string; slack: number; step: number; per: string; shadow_price: number; text: string }
export interface FrontierPoint { rwa_budget: number; rwa_used: number; sva: number; objective: number; selected: number; chosen: boolean }
export interface PipelineSummary {
  deals: number; selected: number; sva: number; penalty: number; objective: number; rwa_used: number; rwa_budget: number;
  el_used: number; el_budget: number; ead_new: number; ead_pipeline: number; raroc_new: number | null; amount_selected: number;
  amount_pipeline: number;
}
export interface PipelineResult {
  trace_id: string; as_of: string; headline: string; summary: PipelineSummary; decisions: Decision[]; limits: LimitRow[];
  soft_breaches: { name: string; scope: string; value: number; status: LimitStatus; penalty: number }[]; binding: Binding[];
  frontier: FrontierPoint[]; solver: { method: string; exact: boolean; nodes: number; seconds: number; feasible: boolean; penalty_rate: number };
  basis: string;
}
export interface PipelineTest {
  trace_id: string; proposal_id: string; obligor: string; structure: DealOption & { terms: Record<string, unknown> };
  makes_cut: boolean; fits: boolean; verdict: string; rank: number; ranked: number; sva_per_100m_rwa: number;
  displaced: { proposal_id: string; obligor: string; sva: number; rwa: number }[];
  resized: { proposal_id: string; obligor: string; from: string; to: string }[]; value_change: number | null;
  pipeline: { deals: number; base_selected: number; base_sva: number; base_objective: number; with_selected: number | null;
              with_objective: number | null; optional_objective: number; rwa_budget: number; el_budget: number };
  limits: LimitRow[]; binds_first: { name: string; label: string; scope: string; times: number; headroom: number; kind: string; text: string } | null;
  solver: { exact: boolean; nodes: number }; basis: string;
}
export interface RiskAppetite {
  trace_id: string; as_of: string; release: string; book_ead: number; rows: LimitRow[]; counts: Record<"green" | "amber" | "red", number>;
  levels: string; owner: string; version: string; penalty_rate: number;
}

// ---------------------------------------------------------------- client

export function pipelineOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}
const ENGINE = "/api/v1/dealdesk";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${pipelineOrigin()}${url}`, {
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
const post = <T>(url: string, body: unknown) => request<T>(url, { method: "POST", body: JSON.stringify(body) });

export interface OptimiseBody { deal_ids?: string[]; rwa_budget?: number; el_budget?: number }

export const pipelineApi = {
  list: () => request<PipelineListing>(`${ENGINE}/pipeline`),
  optimise: (body: OptimiseBody) => post<PipelineResult>(`${ENGINE}/pipeline/optimise`, body),
  test: (id: string, terms?: object | null, body: OptimiseBody = {}) =>
    post<PipelineTest>(`${ENGINE}/proposals/${encodeURIComponent(id)}/pipeline-test`, terms ? { ...body, terms } : body),
  riskAppetite: () => request<RiskAppetite>(`${ENGINE}/risk-appetite`),
};

// ---------------------------------------------------------------- pure helpers

export const STATUS_TONE: Record<LimitStatus, "positive" | "warning" | "negative" | "neutral"> = {
  green: "positive", amber: "warning", red: "negative", "n/a": "neutral",
};
export const STATUS_WORD: Record<LimitStatus, string> = { green: "Within appetite", amber: "Past trigger", red: "Past limit", "n/a": "Each deal" };

/** A limit value in its own unit: shares as %, HHI to 3 dp, bps, SAR m, x, years, deals. */
export function limitValue(v: unknown, unit: string): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "string") return v;
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  switch (unit) {
    case "share": return pct(v, { dp: Math.abs(v) < 0.1 ? 2 : 1 });
    case "index": return v.toFixed(3);
    case "bps": return `${v.toFixed(1)} bps`;
    case "SAR m": return sar(v);
    case "x": return `${v.toFixed(2)}x`;
    case "years": return `${v} years`;
    case "deals": return `${v} ${v === 1 ? "deal" : "deals"}`;
    default: return String(v);
  }
}

/** The bullet bar's scale for a limit row: 0 to a little past the larger of the limit and the values. */
export interface BulletGeometry { max: number; before: number | null; after: number | null; appetite: number | null; trigger: number | null; limit: number | null }
const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
export function bullet(r: Pick<LimitRow, "before" | "after" | "appetite" | "trigger" | "limit">): BulletGeometry | null {
  const lim = n(r.limit);
  if (lim === null) return null;
  const vals = [n(r.before), n(r.after), lim, n(r.trigger), n(r.appetite)].filter((x): x is number => x !== null);
  const top = Math.max(...vals) * 1.12 || 1;
  const f = (x: unknown) => { const v = n(x); return v === null ? null : Math.max(0, Math.min(1, v / top)); };
  return { max: top, before: f(r.before), after: f(r.after), appetite: f(r.appetite), trigger: f(r.trigger), limit: f(r.limit) };
}

/** Rows worth a bullet bar: numeric levels, not the per-deal rows. Breaches and moves first. */
export function panelRows(rows: LimitRow[]): LimitRow[] {
  const rank: Record<LimitStatus, number> = { red: 0, amber: 1, green: 2, "n/a": 3 };
  return rows.filter((r) => r.direction !== "deal" && n(r.limit) !== null)
    .map((r, i) => ({ r, i }))
    .sort((a, b) => rank[a.r.status] - rank[b.r.status] || a.i - b.i).map((x) => x.r);
}

/** The status counts after the selection ("2 red · 3 amber"). */
export function statusCounts(rows: LimitRow[], key: "status" | "status_before" = "status"): Record<"green" | "amber" | "red", number> {
  const out = { green: 0, amber: 0, red: 0 };
  for (const r of rows) if (r[key] !== "n/a") out[r[key] as "green" | "amber" | "red"] += 1;
  return out;
}

/** Deals whose limit status got worse with the selection. */
export function worsened(rows: LimitRow[]): LimitRow[] {
  const rank: Record<LimitStatus, number> = { "n/a": 0, green: 0, amber: 1, red: 2 };
  return rows.filter((r) => rank[r.status] > rank[r.status_before]);
}

/** The ≤4 tiles of the pipeline result (G-TILES). */
export interface Tile { label: string; value: string; sub: string; tone?: "positive" | "negative" | "neutral" | "warning"; info: string }
export function resultTiles(r: PipelineResult): Tile[] {
  const s = r.summary;
  const c = statusCounts(r.limits);
  return [
    { label: "Approve", value: `${s.selected} of ${s.deals}`, sub: `${sar(s.amount_selected)} of ${sar(s.amount_pipeline)} asked`,
      info: "Deals the optimiser approves, out of the pending pipeline, with the amount approved against the amount asked." },
    { label: "SVA", value: sar(s.sva), sub: s.penalty > 0.005 ? `${sar(s.penalty)} appetite charge` : `RAROC ${pct(s.raroc_new)}`,
      tone: s.sva >= 0 ? "positive" : "negative",
      info: "Total shareholder value added of the approved structures (engine results). The appetite charge is 2% of the EAD taken past a soft trigger." },
    { label: "RWA", value: sar(s.rwa_used), sub: `${pct(s.rwa_budget ? s.rwa_used / s.rwa_budget : null)} of ${sar(s.rwa_budget)} budget`,
      tone: s.rwa_used > s.rwa_budget + 1e-6 ? "negative" : "neutral",
      info: "Year-1 risk-weighted assets of the approved structures against the RWA budget you set." },
    { label: "Risk appetite", value: c.red ? `${c.red} red` : c.amber ? `${c.amber} amber` : "All green",
      sub: `${c.green} green · ${c.amber} amber · ${c.red} red`, tone: c.red ? "negative" : c.amber ? "warning" : "positive",
      info: "Every risk-appetite limit after the selection. Red rows already red on the book stay listed; no hard limit is breached by the selection." },
  ];
}

/** The decision table rows, approvals first by SVA, then declines by SVA of their best option. */
export function sortDecisions(ds: Decision[]): Decision[] {
  const best = (d: Decision) => d.option?.sva ?? Math.max(...d.options.filter((o) => o.available).map((o) => o.sva), -1e9);
  return [...ds].sort((a, b) => (a.decision === b.decision ? best(b) - best(a) : a.decision === "approve" ? -1 : 1));
}

/** "All pending" selection toggling. */
export function toggle(sel: ReadonlySet<string>, id: string): Set<string> {
  const out = new Set(sel);
  if (out.has(id)) out.delete(id); else out.add(id);
  return out;
}
export const allPending = (deals: PipelineDeal[]) => new Set(deals.map((d) => d.proposal_id));

/** A budget field: SAR m, positive, or null when blank or not a number. */
export function parseBudget(text: string): number | null {
  const t = text.replace(/[,\s]|SAR|m$/gi, "");
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) && v >= 0 ? v : null;
}

/** The pipeline-test answer line. */
export function testLine(t: PipelineTest): string {
  const b = t.binds_first ? ` ${t.binds_first.text}.` : "";
  return `${t.verdict}.${b}`.replace(/\.\./g, ".");
}

/** The button is live only when Optimise has a result (contract: PipelineTestButton({ proposalId, terms, ready })). */
export function canTest(ready: boolean, busy: boolean): boolean {
  return ready && !busy;
}
