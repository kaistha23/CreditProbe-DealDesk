/**
 * PLAN_R14 Session E: the Deal Desk engines (Deal Desk service, prefix /api/v1/dealdesk/engines).
 *
 *   GET  /engines/{id}/summary?structure=      approval + economics + capacity + findings counts + verdict + period (tiles)
 *   GET  /engines/{id}/approval|economics|capacity|raroc-bridge?structure=
 *   GET  /engines/{id}/findings | counter-offer | why-fails
 *   POST /engines/{id}/evaluate {structure, label}
 *
 * One engine per fact (N2): every tile, step, opinion and paper reads these. Pure helpers at the bottom are unit-tested
 * (dealdesk-engines.test.ts); no path aliases so node can run them.
 */
import { friendlyError } from "./errors.ts";

const PREFIX = "/api/v1/dealdesk/engines";

export function enginesOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${enginesOrigin()}${PREFIX}${path}`, { ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json" } });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export type StructureSpec = "ask" | "recommended" | `counter:${string}` | Record<string, unknown>;
export type EngineSeverity = "critical" | "major" | "minor" | "info";

export interface ApprovalReason { basis: string; rank: number; level: string; detail: string; label?: string; code?: string }
export interface Approval {
  proposal_id: string; structure: { key: string; label: string }; level: string; rank: number; rule: string; binding: ApprovalReason;
  reasons: ApprovalReason[]; exposure_after_sar_mn: number; existing_exposure_sar_mn: number; new_limit_sar_mn: number;
  exceptions: { code: string; label: string; rank: number | null; level: string | null }[]; hard_breaches: string[]; soft_breaches: string[];
  approvable: boolean; expected_days: { value: number | null; unit: string; n: number }; documents_missing: { finding_id: string; title: string; severity: string }[];
  path: { rank: number; level: string }[]; source: string;
}
export interface CapacityInput { name: string; value: number; unit: string; advance?: number | null }
export interface Capacity {
  proposal_id: string; structure: { key: string; label: string }; facility_type: string; method: "borrowing_base" | "dscr_leverage";
  method_label: string; formula: string; inputs: CapacityInput[]; capacity_sar_mn: number; ask_sar_mn: number; gap_sar_mn: number;
  ask_to_capacity: number | null; within: boolean; severity: EngineSeverity | null; finding_title: string; recommended_amount_sar_mn: number | null;
  note: string | null; alt: { ebitda_based_sar_mn: number; cash_flow_based_sar_mn: number };
  borrowing_base?: { eligible_receivables: number; eligible_inventory: number; gross_base: number; short_term_debt: number; wc_gap: number;
    payables: number; period: { entity_id: string; entity_name: string; period_label: string; period_kind: string }; cross_check: string };
}
export interface BridgeStep { step: string; raroc: number | null; delta_pp: number | null; pv_sar_mn: number; what: string }
export interface Bridge { steps: BridgeStep[]; pv_capital_sar_mn: number; hurdle: number; basis: string; headline: string; source: string }
export interface Period { quarter: string; as_of: string; label: string; source: string }
export interface Economics {
  proposal_id: string; structure: { key: string; label: string };
  raroc: { lifetime: number | null; one_year: number | null; hurdle: number; clears: boolean; relationship: number | null };
  sva: { lifetime: number; one_year: number; relationship_lifetime: number };
  basis: { raroc: string; sva: string; label: string; note: string };
  el: { y1: number; lifetime_pv: number; rate_y1: number | null; info: string };
  rwa: { y1: number; exposure_reg_y1: number; risk_weight: number; density_exposure: number | null; density_limit: number | null; info: string };
  pd: { pd_12m: number; model_12m: number | null; master_scale_12m: number; rating: string; info: string };
  lgd: { y1: number; unsecured: number; collateral_recognised_sar_mn: number; guarantee_applied: boolean; info: string };
  ead_y1: number; crm: { kind: string; label: string; effect: string; in_lgd: boolean; in_rwa: boolean }[];
  bands: { el_rate: [number, number]; el_in_band: boolean; rwa_in_band: boolean; el_explained_by: string | null; rwa_explained_by: string | null; ok: boolean; rule: string };
  bridge: Bridge; period: Period;
}
export interface Cure { kind: string; kind_label: string; text: string; owner: string; when: string }
export interface EngineFinding {
  id: string; source: string; source_relation: string; code: string; category: string; category_label: string; severity: EngineSeverity;
  verdict: string | null; title: string; text: string; evidence: { source: string; text: string }[]; policy_ref: string; status: string;
  cure: Cure; curable: boolean;
}
export interface FindingCounts {
  total: number; by_severity: Record<EngineSeverity, number>; by_category: Record<string, number>;
  checks: { supported: number; contradicted: number; exception: number; unverifiable: number }; resolved: number; line: string; checks_line: string;
}
export interface EngineVerdict { decision: string; tone: "negative" | "warning" | "positive"; headline: string; critical: string[]; major: string[]; not_curable: string[]; rule: string;
  /** R15 b (L13): the one sentence that reconciles price and verdict (banner, RAROC tile, plain words). */
  story?: string; price_only?: string }
/** R15 b (L13 (2), L8 (a)): the three labelled return views from the one RAROC bridge. */
export interface ReturnView { key: "deal" | "relationship" | "relationship_deposits"; label: string; line: string; raroc: number | null; formula: string | null; clears: boolean; used_for_approval: boolean }
export interface ReturnViews { basis: ReturnView["key"]; views: ReturnView[]; rule: string }
export interface PdRangeNote { label: string; meaning: string; done: string }
export interface CapacityCrossCheck { label: string; value_sar_mn: number | null; line: string }
export interface Findings { proposal_id: string; findings: EngineFinding[]; counts: FindingCounts; chips: { key: string; label: string; count: number }[];
  verdict: EngineVerdict; source: string }
export interface Summary {
  proposal_id: string; structure: { key: string; label: string }; period: Period; raroc: Economics["raroc"]; sva: Economics["sva"];
  basis: Economics["basis"]; el: Economics["el"]; rwa: Economics["rwa"]; pd: Economics["pd"]; lgd: Economics["lgd"]; ead_y1: number;
  bands: Economics["bands"]; bridge: Bridge;
  approval: Pick<Approval, "level" | "rank" | "rule" | "binding" | "reasons" | "exposure_after_sar_mn" | "expected_days" | "documents_missing" | "approvable" | "exceptions">;
  capacity: Pick<Capacity, "method" | "method_label" | "formula" | "capacity_sar_mn" | "ask_sar_mn" | "within" | "severity" | "finding_title">;
  findings: { counts: FindingCounts; chips: Findings["chips"]; verdict: EngineVerdict };
  return_views?: ReturnViews; capacity_cross_check?: CapacityCrossCheck[]; pd_range?: PdRangeNote | null;
}

/** R15 b (L13): the RAROC tile's sub-line: price only, against the hurdle, on the view shown. */
export function rarocTileSub(clears: boolean, hurdle: number, view?: ReturnView | null): string {
  const base = `${clears ? "Clears" : "Below"} the ${pct1(hurdle)} hurdle · price only`;
  return view && view.key !== "deal" ? `${base} · ${view.label.split(" (")[0].toLowerCase()} view` : base;
}

/** The view to show first: the one the approval test uses. */
export function approvalView(rv?: ReturnViews | null): ReturnView | null {
  return rv?.views.find((v) => v.used_for_approval) ?? rv?.views[0] ?? null;
}

const enc = encodeURIComponent;
const q = (s?: StructureSpec) => (!s || s === "ask" ? "" : typeof s === "string" ? `?structure=${enc(s)}` : "");

export const enginesApi = {
  summary: (id: string, s?: StructureSpec) => typeof s === "object"
    ? call<Summary>(`/${enc(id)}/summary`, { method: "POST", body: JSON.stringify({ structure: s }) })
    : call<Summary>(`/${enc(id)}/summary${q(s)}`),
  approval: (id: string, s?: StructureSpec) => call<Approval>(`/${enc(id)}/approval${q(s)}`),
  economics: (id: string, s?: StructureSpec) => call<Economics>(`/${enc(id)}/economics${q(s)}`),
  capacity: (id: string, s?: StructureSpec) => call<Capacity>(`/${enc(id)}/capacity${q(s)}`),
  bridge: (id: string, s?: StructureSpec) => call<Bridge>(`/${enc(id)}/raroc-bridge${q(s)}`),
  findings: (id: string) => call<Findings>(`/${enc(id)}/findings`),
  period: () => call<Period>("/period"),
};

// ---------------------------------------------------------------- pure helpers

export const SEVERITY_ORDER: EngineSeverity[] = ["critical", "major", "minor", "info"];
export const SEVERITY_LABEL: Record<EngineSeverity, string> = { critical: "Critical", major: "Major", minor: "Minor", info: "For information" };
export const SEVERITY_TONE: Record<EngineSeverity, "negative" | "warning" | "neutral"> = { critical: "negative", major: "warning", minor: "neutral", info: "neutral" };
export const CURE_TONE: Record<string, "positive" | "negative" | "warning" | "neutral" | "accent"> = {
  structure: "accent", cp: "warning", security: "accent", covenant: "accent", explanation: "neutral", governance: "warning", not_curable: "negative",
};

/** Open findings in one category ("all" for every one), grouped by severity critical → info. */
export function groupFindings(fs: EngineFinding[], category = "all"): { severity: EngineSeverity; items: EngineFinding[] }[] {
  const open = fs.filter((f) => f.status === "open" && (category === "all" || f.category === category));
  return SEVERITY_ORDER.map((s) => ({ severity: s, items: open.filter((f) => f.severity === s) })).filter((g) => g.items.length > 0);
}

/** "SAR 96.8m" (SAR million, one decimal). */
export function sarMn(x: number | null | undefined, dp = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return `SAR ${x.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp })}m`;
}

/** "14.5%" from a decimal. */
export function pct1(x: number | null | undefined, dp = 1): string {
  return x === null || x === undefined || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(dp)}%`;
}

/** The capacity tile's sub-line: "ask SAR 170.0m · 1.76× capacity" or "ask SAR 60.0m · within". */
export function capacitySub(c: Pick<Capacity, "ask_sar_mn" | "capacity_sar_mn" | "within">): string {
  if (c.within) return `ask ${sarMn(c.ask_sar_mn)} · within capacity`;
  if (c.capacity_sar_mn <= 0) return `ask ${sarMn(c.ask_sar_mn)} · no capacity`;
  return `ask ${sarMn(c.ask_sar_mn)} · ${(c.ask_sar_mn / c.capacity_sar_mn).toFixed(2)}× capacity`;
}

/** Bridge steps as "Deal 14.5% → +5.8 pp ancillary → +13.2 pp deposits". */
export function bridgeLine(b: Bridge): string {
  return b.steps.map((s, i) => (i === 0 ? `${s.step} ${pct1(s.raroc)}` : `${s.delta_pp !== null && s.delta_pp >= 0 ? "+" : ""}${(s.delta_pp ?? 0).toFixed(1)} pp ${s.step.replace(/^\+\s*/, "")}`)).join(" → ");
}
