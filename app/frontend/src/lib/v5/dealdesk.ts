/**
 * v5 Deal Desk client (Pre-deal Analysis, DEAL_DESK_PROMPT section 4).
 *
 * Talks to the Deal Desk service (port 8508, `NEXT_PUBLIC_DEALDESK_API`) with
 * the session cookie (`credentials: "include"`): the engine under
 * /api/v1/dealdesk (docs/v5/DEALDESK_API.md) and the thread layer under
 * /api/v1/dealdesk/desk. Every figure on the screens comes from the engine.
 * Money in outputs is SAR million; deal terms are in the deal currency,
 * millions; ratios are decimals; margins and fees are basis points.
 */
import { friendlyError } from "./errors.ts";
export { useEws as useLoad } from "@/lib/v5/ews";
import { fmt } from "@/lib/v5/format";
import { DEPOSIT_NEUTRAL, DEPOSIT_TYPE, type DepositEffect, depositRead } from "./dealdesk-deposit.ts";  // Round D

export function dealdeskOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}
const ENGINE = "/api/v1/dealdesk";
const DESK = "/api/v1/dealdesk/desk";
export const deskUrl = (path: string) => `${dealdeskOrigin()}${DESK}${path}`;

export class DealDeskError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${dealdeskOrigin()}${url}`, {
      ...init,
      credentials: "include",
      headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new DealDeskError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Deal Desk", response.status, body);
    throw new DealDeskError(response.status, message);
  }
  return body as T;
}

const post = <T>(url: string, body: unknown, traceId?: string) =>
  request<T>(url, { method: "POST", body: JSON.stringify(body), headers: traceId ? { "X-Trace-Id": traceId } : undefined });
const enc = encodeURIComponent;

// ---------------------------------------------------------------- engine schemas (DEALDESK_API.md section 2)

export const RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
  "B+", "B", "B-", "CCC", "CC", "C"] as const;
export const STATUSES = ["new", "in_review", "counter_offered", "approved", "declined"] as const;
export type Status = (typeof STATUSES)[number];
export const STATUS_LABEL: Record<Status, string> = {
  new: "New", in_review: "In review", counter_offered: "Counter-offered", approved: "Approved", declined: "Declined",
};

export interface Terms {
  facility_type: string; structure: string; currency: string; amount: number; tenor_years: number; grace_years: number;
  amortisation: string; balloon_pct: number; margin_bps: number; upfront_fee_bps: number; commitment_fee_bps: number;
  commission_bps: number; utilisation_pct: number; funded_share_pct: number; unfunded_type: string; cash_margin_pct: number;
  collateral_ids: string[]; guarantee_id: string | null; guarantee_coverage_pct: number; covenant_package: string;
  // R5 D4: the rest of the risk manager's levers (absent = neutral)
  prepayment_fee_bps?: number; rate_type?: "floating" | "fixed"; hold_pct?: number; insurance_cover_pct?: number;
  receivables_assignment_pct?: number; covenant_items?: string[]; review_cycle_months?: number; cross_sell?: string[];
  // Round D: the Deposit requirement term (lib/v5/dealdesk-deposit.ts)
  deposit_type?: string; deposit_pct?: number; deposit_amount?: number; deposit_tenor_months?: number; deposit_facility?: string;
}
export const NEUTRAL: Partial<Terms> = {
  prepayment_fee_bps: 0, rate_type: "floating", hold_pct: 100, insurance_cover_pct: 0, receivables_assignment_pct: 0,
  covenant_items: [], review_cycle_months: 12, cross_sell: [], ...DEPOSIT_NEUTRAL,
};
export const withNeutral = (t: Terms): Terms => ({ ...NEUTRAL, ...t } as Terms);

/** R5 D4: one lever of the catalogue (`GET /levers?proposal_id=`). */
export interface Lever {
  key: keyof Terms & string; label: string; group: string; channel: string; unit: string; kind: "continuous" | "discrete" | "choice" | "set";
  parameters: { table: string; owner: string; version: string; source: string }; neutral: unknown;
  bounds?: { min: number; max: number; source: "market" | "policy" } | Record<string, never>; options?: unknown[]; ask?: unknown;
}
export interface GuaranteeOption { id: string; label: string; type: string; rating: string; offered: boolean; requested: boolean }
export interface LeverCatalogue { trace_id: string; groups: string[]; levers: Lever[]; guarantee_options: GuaranteeOption[] }
export interface Contribution { lever: string; label: string; group: string; raroc_pts: number; sva: number; from: unknown; to: unknown }
export interface Alternative {
  label: string; why: string; terms: Terms; distance: number; metrics: Metrics; approval: Approval; soft_breaches: string[];
  changes: { field: string; label: string; group: string; ask: unknown; value: unknown; unit: string }[];
  contributions: Contribution[];
}
export interface SingleLever {
  lever: string; label: string; group: string; from: unknown; to: unknown; unit: string; clears_alone: boolean; note: string;
  lifetime_raroc?: number; sva?: number; approval?: string; delta?: number | null; guarantee_id?: string;
}
export interface AlternativesResult {
  trace_id: string; base_clears: boolean; base_metrics: Metrics; alternatives: Alternative[]; single_lever: SingleLever[];
}
/** R5 D5: the proposal as submitted, as labelled rows (one builder for screen, Word and Playbook). */
export interface ProposalFull {
  title: string; obligor: { label: string; value: string }[]; deal: { label: string; value: string }[];
  facility_lines: { line_id: string; facility: string; structure: string; currency: string; amount: string; tenor: string; pricing: string;
                    fees: string; repayment: string; security: string; guarantees: string; covenants: string }[];
  existing_facilities: { facility_id: string; product: string; limit: string; drawn: string; ead: string; stage: string }[];
  memo_href: string;
}
export interface ProposalSummary {
  proposal_id: string; status: Status; obligor_name: string; existing: boolean; sector: string; rating: string; rm: string;
  facility_type: string; structure: string; currency: string; amount: number; amount_sar_mn: number; tenor_years: number;
  received: string; case?: string;
  /** R14 U (K17): from GET /deals (dd_deal + uploads). */
  source?: string; source_label?: string; deal_name?: string; product?: string; branch?: string; pending?: boolean; match?: number;
}
export interface DealList {
  trace_id: string; proposals: ProposalSummary[]; total: number; counts: Record<string, number>; by_source: Record<string, number>; source: string;
}
export interface Collateral { collateral_id: string; type: string; value: number; currency: string; valuation_date: string; pledged_in_ask: boolean }
export interface Guarantee { guarantee_id: string; type: string; guarantor: string; guarantor_rating: string; coverage_pct: number; offered_in_ask: boolean }
export interface FinYear { year: number; kind: string; revenue: number; ebitda: number; total_debt: number; debt_service: number; net_worth: number; current_ratio: number }
export interface Proposal {
  proposal_id: string; status: Status; rm: string; business_unit: string; received: string; purpose: string;
  obligor: {
    obligor_id: string; existing: boolean; name: string; cr_number: string; group_id: string; group_name: string; connected_parties: string[];
    sector: string; sub_sector: string; region: string; sme: boolean; gre: boolean; internal_rating: string; external_rating: string | null;
    pd_master_scale: number; simah_flag: string; existing_exposure_sar_mn: number;
  };
  financials: { currency: string; years: FinYear[] };
  ask: Terms;
  security: { collateral: Collateral[]; guarantees: Guarantee[]; covenant_package: string; covenants: { type: string; threshold: number }[] };
  business_case: { ancillary_income_sar_mn_pa: Record<string, number> };
  memo?: string; case?: string;
}
export interface Metrics {
  amount_sar_mn: number; lifetime_raroc: number; hurdle: number; clears_hurdle: boolean; sva: number; breakeven_margin_bps: number | null;
  relationship_raroc: number; relationship_sva: number; rwa_y1: number; capital_y1: number; el_y1: number; el_lifetime_pv: number;
  day_one_ecl: number; pd_12m: number; lgd_y1: number; ead_y1: number; dscr_post: number | null; debt_ebitda_post: number | null;
  robustness_notches: number | null;
}
export interface Constraint {
  name: string; label: string; scope: string; value: number | string; limit: number | string; headroom: number | null; unit: string;
  kind: "hard" | "soft"; status: "pass" | "breach"; before: number | null; deal: number | null; basis: string;
}
export interface Approval { level: string; rank: number; reasons: string[];
  /** R14 E: the one approval-authority engine's rule and binding reason. */
  rule?: string; binding?: { basis: string; rank: number; level: string; detail: string; label?: string } }
export interface Analysis {
  trace_id: string; proposal_id: string; terms: Terms; el_view: string; capital_basis: string; fx_to_sar: number; metrics: Metrics;
  pd: { model_version: string; model_pd_12m: number; master_scale_pd_12m: number; ttc_pd: number;
        out_of_range: { status: string; features: { feature: string; value: number; p01: number; p99: number; status: string }[] };
        monotonicity: { status: string; adjustments: unknown[] } };
  waterfall: { step: string; value: number; total?: boolean }[];
  constraints: Constraint[]; approval: Approval;
  /** Round D: what the engine used and did with the Deposit requirement term (null when the terms carry none). */
  deposit?: DepositEffect | null;
}
export interface Solution {
  label: string; terms: Terms; metrics: Metrics; distance: number; approval: Approval; soft_breaches: string[];
  changes: { field: string; ask: unknown; value: unknown; unit: string }[];
}
export interface OptimizeResult {
  trace_id: string; feasible: boolean;
  ask: { terms: Terms; metrics: Metrics; clears: boolean; breaches: string[] };
  closest: Solution | null; max_sva: Solution | null; counter_offers: Solution[] | null;
  frontier: { distance: number; sva: number; lifetime_raroc: number; terms: Terms }[];
  binding: { constraint: string; label?: string; shadow_price: number | null; unit: string; per?: string }[];
  alternatives?: Alternative[]; single_lever?: SingleLever[];
  relaxation: { lever: string; from: number | string; to: number | string | null; delta: number | null; unit: string; beyond_market: boolean }[] | null;
  searched: { combinations: number; feasible_points: number; seconds: number };
}
export interface StressResult {
  trace_id: string; base: { lifetime_raroc: number; sva: number };
  rows: { scenario: string; label: string; lifetime_raroc: number; sva: number; el_lifetime_pv: number; rwa_y1: number; dscr_post: number | null;
          clears_hurdle: boolean; breaches: string[] }[];
  robustness_notches: number;
}
export interface Grid {
  trace_id: string; x: string | number[]; y: string | number[] | null; x_values?: number[]; y_values?: number[] | null;
  values: number[][] | number[]; hurdle: number; ask: { x: number; y: number | null };
}
export interface Tornado { trace_id: string; base_raroc: number; bars: { lever: string; low_label?: string; high_label?: string; low: number; high: number }[] }
/** The axis values of a grid (the engine names the axis in `x` and lists its values in `x_values`). */
export const gridX = (g: Grid): number[] => g.x_values ?? (Array.isArray(g.x) ? g.x : []);
export const gridY = (g: Grid): number[] => g.y_values ?? (Array.isArray(g.y) ? g.y : []);
export interface EngineMeta {
  facility_types: string[]; structures: string[]; statuses: Status[]; rating_order: string[]; sectors: string[]; rms: string[];
  hurdle?: number; market_bounds?: { margin_bps: [number, number]; upfront_fee_bps: [number, number] };
}

// ---------------------------------------------------------------- thread layer

export interface DealState {
  terms?: Terms; recommended?: Terms; optimisation?: { trace_id: string; feasible: boolean } | null;
  optimise_request?: { fixed?: Partial<Terms>; bounds?: Record<string, unknown>; weights?: Record<string, number>; allow_soft?: boolean };
}
export interface Bundle {
  proposal: Proposal; proposal_full?: ProposalFull; ask: Analysis; current: Analysis; heatmap: Grid; amount_curve: Grid; tornado: Tornado; stress: StressResult;
  trace_ids: string[]; ms: number; state: DealState;
}
export interface Block {
  type: string; markdown?: string; title?: string; rows?: (string | number | boolean | null)[][]; header?: string[];
  /** The column keys behind `header` (PLAN_R6 E2), so a cell that arrives unformatted is formatted by its key. */
  keys?: string[];
  [k: string]: unknown;
}
export interface RecentRow {
  kind: "saved" | "optimised"; id: string; time: number; user: string; proposal_id: string; obligor: string; name: string; outcome: string;
  approval: string | null; lifetime_raroc: number | null; sva: number | null; href: string; report: string | null;
}
export interface RecentResult {
  recent: RecentRow[];
  continue: { proposal_id: string; obligor: string; question: string; time: number; turns: number; href: string;
              thread_id?: string | null; title?: string } | null;
  /** R14 n (K16): the reader's Deal Desk threads, newest first. */
  threads?: DeskThreadMeta[];
}
export interface AnswerT {
  trace?: import("@/lib/v5/thread").TraceSnapshot;
  intent: string; blocks: Block[]; suggestions: { label: string; send: string }[]; trace_ids: string[];
  validation: { checked: number; untraced: string[]; passed: boolean }; action?: string; source?: string;
}
export interface Turn { turn_id: string; question: string; owner: string; created: number; answer: AnswerT }
export interface SavedAnalysis {
  analysis_id: string; proposal_id: string; owner: string; name: string; created: number; obligor: string;
  terms: Terms; metrics: Metrics; approval: Approval; trace_id: string;
}
export interface IngestField { field: string; label: string; value: unknown; source: string; confidence: number }
export interface Ingested { proposal: Partial<Proposal>; fields: IngestField[]; filename: string; coverage: number;
  /** PLAN_R6 D1: which form the file opens in, the long-form sections read, and the keys read (for marking) */
  form?: "short" | "long"; long?: Record<string, unknown>; long_found?: string[] }

// ---------------------------------------------------------------- calls

export const dealdesk = {
  meta: () => request<EngineMeta>(`${ENGINE}/meta`),
  proposals: () => request<{ trace_id: string; proposals: ProposalSummary[] }>(`${ENGINE}/proposals`),
  /** R14 U (K17): every deal the desk knows (dd_deal + uploads), live status, the Pipeline tab's pending count. */
  deals: () => request<DealList>(`${ENGINE}/deals`),
  proposal: (id: string) => request<{ trace_id: string; proposal: Proposal }>(`${ENGINE}/proposals/${enc(id)}`).then((r) => r.proposal),
  create: (body: unknown) => post<{ trace_id: string; proposal: Proposal }>(`${ENGINE}/proposals`, body).then((r) => r.proposal),
  setStatus: (id: string, status: Status) => post<{ proposal: Proposal }>(`${ENGINE}/proposals/${enc(id)}/status`, { status }),
  compute: (id: string, terms?: Partial<Terms>) => post<Analysis>(`${ENGINE}/compute`, { proposal_id: id, terms }),
  optimize: (id: string, body: { fixed?: Partial<Terms>; bounds?: Record<string, unknown>; weights?: Record<string, number>; allow_soft?: boolean } = {}) =>
    post<OptimizeResult>(`${ENGINE}/optimize`, { proposal_id: id, objective: "both", ...body }),
  modelCard: (id: string) => request<Record<string, unknown>>(`${ENGINE}/model_card?proposal_id=${enc(id)}`),
  stress: (id: string, terms?: Partial<Terms>) => post<StressResult>(`${ENGINE}/stress`, { proposal_id: id, terms, scenario: "all" }),
  levers: (id: string) => request<LeverCatalogue>(`${ENGINE}/levers?proposal_id=${enc(id)}`),
  alternatives: (id: string, body: { terms?: Partial<Terms>; fixed?: Partial<Terms>; bounds?: Record<string, unknown>; allow_soft?: boolean } = {}) =>
    post<AlternativesResult>(`${ENGINE}/alternatives`, { proposal_id: id, ...body }),

  bundle: (id: string) => request<Bundle>(`${DESK}/proposals/${enc(id)}/analysis`),
  setState: (id: string, body: Partial<DealState>) => post<DealState>(`${DESK}/proposals/${enc(id)}/state`, body),
  thread: (id: string) => request<{ turns: Turn[]; state: DealState }>(`${DESK}/proposals/${enc(id)}/thread`),
  ask: (id: string, question: string, traceId?: string) =>
    post<{ turn_id: string; answer: AnswerT; state: DealState }>(`${DESK}/proposals/${enc(id)}/thread`, { question }, traceId),
  optimiseTurn: (id: string, settings: { fixed?: Partial<Terms>; weights?: Record<string, number>; allow_soft?: boolean } = {}, traceId?: string) =>
    post<{ optimisation: OptimizeResult; turn: Turn; state: DealState }>(`${DESK}/proposals/${enc(id)}/optimise`, settings, traceId),
  /** R14 n (K16): with `threadId` the question continues that thread; without, it opens a new one. */
  askDesk: (question: string, traceId?: string, threadId?: string) =>
    post<AnswerT & { turn_id?: string; thread_id?: string; thread_title?: string }>(`${DESK}/ask`,
      threadId ? { question, thread_id: threadId } : { question }, traceId),
  deskThread: (threadId: string) => request<{ turns: Turn[]; thread?: DeskThreadMeta | null }>(
    `${DESK}/desk-thread?thread=${enc(threadId)}`),
  /** A new desk thread for a question (the landing opens it, then the thread page asks the question once). */
  newDeskThread: (question: string) => post<DeskThreadMeta>(`${DESK}/desk-threads`, { question }),
  deskThreads: (limit = 20) => request<{ threads: DeskThreadMeta[] }>(`${DESK}/desk-threads?limit=${limit}`),
  recent: (limit = 20) => request<RecentResult>(`${DESK}/recent?limit=${limit}`),
  createFromFields: (fields: Record<string, string>, source: unknown, long?: Record<string, unknown>) =>
    post<Proposal>(`${DESK}/proposals`, long ? { fields, source, long } : { fields, source }),
  groups: (q: string) => request<{ groups: { group_id: string; group_name: string; ead_sar_mn: number; borrowers: number }[] }>(`${DESK}/groups?q=${encodeURIComponent(q)}`),
  ingest: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Ingested>(`${DESK}/ingest`, { method: "POST", body: form });
  },
  save: (proposal_id: string, name: string, terms?: Partial<Terms>) => post<SavedAnalysis>(`${DESK}/analyses`, { proposal_id, name, terms }),
  analyses: () => request<{ analyses: SavedAnalysis[] }>(`${DESK}/analyses`),
  analysis: (id: string) => request<SavedAnalysis>(`${DESK}/analyses/${enc(id)}`),
};

/** R14 n (K16): one Deal Desk thread per question asked on the landing. */
export interface DeskThreadMeta { thread_id: string; title: string; owner: string; created: number; updated: number; turns: number; href: string }

export const reportHref = (id: string) => deskUrl(`/proposals/${enc(id)}/report.docx`);
export const analysisReportHref = (id: string) => deskUrl(`/analyses/${enc(id)}/report.docx`);

// ---------------------------------------------------------------- formatting

/** Millions in the deal currency through the G5 rules: "SAR 350m", "USD 1.23bn" (SAR goes through `fmt.sar`). */
export function money(v: number | null | undefined, ccy = "SAR"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  if (ccy === "SAR") return fmt.sar(v).replace(/^SAR -/, "−SAR ");
  const a = Math.abs(v);
  const [s, suf] = a >= 1000 ? [v / 1000, "bn"] : [v, "m"];
  const d = a >= 1000 ? 2 : Math.abs(s) >= 10 ? 1 : 2;
  return `${v < 0 ? "−" : ""}${ccy} ${Math.abs(s).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}${suf}`;
}
/** A decimal ratio as a percentage (G5: 1–2 decimals): 0.1534 -> "15.3%", 0.0092 -> "0.92%". */
export const rate = (v: number | null | undefined, places?: number) => fmt.pct(v, places === undefined ? {} : { dp: Math.max(1, Math.min(2, places)) });
export const bps = (v: number | null | undefined) => fmt.bps(v);
export const pctPts = (v: number | null | undefined) =>
  (v === null || v === undefined || !Number.isFinite(v) ? "–" : `${(Math.round(v * 10) / 10).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`);
export const years = (v: number) => `${v} ${v === 1 ? "year" : "years"}`;
export const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export const FACILITY: Record<string, string> = {
  term_loan: "Term finance", revolver: "Revolving working capital", performance_lg: "Performance LG", financial_lg: "Financial LG",
  trade_lc: "Trade LC",
};
export const STRUCTURE: Record<string, string> = {
  conventional: "Conventional", murabaha: "Murabaha", tawarruq: "Tawarruq", ijara: "Ijara", musharaka: "Musharaka",
};
export const COLLATERAL: Record<string, string> = {
  real_estate: "Real estate", cash: "Cash", shares: "Listed shares", receivables: "Receivables", plant_equipment: "Plant and equipment",
  vehicles: "Vehicles",
};
export const isFunded = (t: Pick<Terms, "facility_type">) => t.facility_type === "term_loan" || t.facility_type === "revolver";

export function constraintRead(c: Constraint, v: number | string | null = c.value): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.charAt(0).toUpperCase() + v.slice(1);
  switch (c.unit) {
    case "share": case "ratio": return rate(v, 1);
    case "x": return `${fmt.ratio(v)}x`;
    case "years": return years(v);
    case "SAR m": return money(v);
    case "notch": return RATINGS[Math.max(0, Math.min(RATINGS.length - 1, -v))] ?? String(v);
    default: return `${fmt.num(v)} ${c.unit}`;
  }
}
export function headroomRead(c: Constraint): string {
  if (c.headroom === null || c.headroom === undefined) return "—";
  if (c.unit === "notch" || c.unit === "rating") return `${c.headroom} notch${Math.abs(c.headroom) === 1 ? "" : "es"}`;
  if (c.unit === "share" || c.unit === "ratio") return `${fmt.num(Math.round(c.headroom * 1000) / 10)} pp`;
  return constraintRead(c, c.headroom);
}

/** Term-sheet rows (label, read). Changed cells are those whose read differs from the ask's. */
export const TERM_ROWS: [string, (t: Terms) => string][] = [
  ["Facility", (t) => FACILITY[t.facility_type] ?? t.facility_type],
  ["Structure", (t) => STRUCTURE[t.structure] ?? t.structure],
  ["Amount", (t) => money(t.amount, t.currency)],
  ["Tenor", (t) => years(t.tenor_years)],
  ["Grace", (t) => years(t.grace_years ?? 0)],
  ["Hold level", (t) => pctPts(t.hold_pct ?? 100)],
  ["Repayment", (t) => (t.amortisation === "balloon" ? `Balloon ${pctPts(t.balloon_pct)}` : cap(t.amortisation))],
  ["Rate", (t) => cap(t.rate_type ?? "floating")],
  ["Margin", (t) => `${t.currency === "USD" ? "SOFR" : "SAIBOR"} + ${bps(t.margin_bps)}`],
  ["Upfront fee", (t) => bps(t.upfront_fee_bps)],
  ["Commitment fee", (t) => bps(t.commitment_fee_bps)],
  ["Commission", (t) => bps(t.commission_bps)],
  ["Prepayment fee", (t) => bps(t.prepayment_fee_bps ?? 0)],
  ["Cash margin", (t) => pctPts(t.cash_margin_pct ?? 0)],
  ["Deposit requirement", (t) => depositRead(t)],  // Round D
  ["Collateral pledged", (t) => (t.collateral_ids?.length ? t.collateral_ids.join(", ") : "None")],
  ["Guarantee", (t) => (t.guarantee_id ? `${GUARANTEE_LABEL[t.guarantee_id] ?? t.guarantee_id} · ${pctPts(t.guarantee_coverage_pct)}` : "None")],
  ["Credit insurance", (t) => pctPts(t.insurance_cover_pct ?? 0)],
  ["Assigned receivables", (t) => pctPts(t.receivables_assignment_pct ?? 0)],
  ["Covenant package", (t) => cap(t.covenant_package)],
  ["Covenants", (t) => (t.covenant_items?.length ? t.covenant_items.map((x) => COVENANT_ITEM[x] ?? x).join(", ") : "Package only")],
  ["Review cycle", (t) => `${t.review_cycle_months ?? 12} months`],
  ["Cross-sell committed", (t) => (t.cross_sell?.length ? t.cross_sell.map((x) => CROSS_SELL[x] ?? x).join(", ") : "None")],
];

export const GUARANTEE_LABEL: Record<string, string> = {
  "REQ-PARENT": "Parent guarantee (requested)", "REQ-BANK": "Bank guarantee (requested)", "REQ-SOVEREIGN": "Sovereign guarantee (requested)",
  "REQ-ECA": "ECA cover (requested)",
};
export const COVENANT_ITEM: Record<string, string> = {
  leverage: "Leverage", dscr: "DSCR", cash_sweep: "Cash sweep", dividend_lockup: "Dividend lock-up", negative_pledge: "Negative pledge",
};
export const CROSS_SELL: Record<string, string> = { cash_management: "Cash management", payroll: "Payroll", fx: "FX", trade: "Trade", deposits: "Deposits" };
export const AMORTISATION: Record<string, string> = { equal: "Equal instalments", sculpted: "Sculpted", balloon: "Balloon", bullet: "Bullet" };

/** A lever value in words with its unit (alternatives, single-lever table, changes). */
export function leverRead(field: string, v: unknown, ccy = "SAR"): string {
  if (v === null || v === undefined) return "None";
  if (Array.isArray(v)) return v.length ? v.map((x) => COVENANT_ITEM[String(x)] ?? CROSS_SELL[String(x)] ?? String(x)).join(", ") : "None";
  if (typeof v === "string") {
    if (field === "guarantee_id") return GUARANTEE_LABEL[v] ?? v;
    if (field === "amortisation") return AMORTISATION[v] ?? cap(v);
    if (field === "deposit_type") return DEPOSIT_TYPE[v] ?? cap(v.replace(/_/g, " "));  // Round D
    if (field === "deposit") return v;
    return cap(v.replace(/_/g, " "));
  }
  if (typeof v !== "number") return String(v);
  if (field.endsWith("_bps")) return bps(v);
  if (field.endsWith("_pct")) return pctPts(v);
  if (field === "amount") return money(v, ccy);
  if (field === "tenor_years" || field === "grace_years") return years(v);
  if (field === "review_cycle_months") return `${v} months`;
  return fmt.num(v);
}
