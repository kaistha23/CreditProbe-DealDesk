/**
 * R14 i: response shapes of /api/v1/dealdesk/intel2/{id}/{feature} and pure helpers (no path aliases: `node --test`).
 */

export type Source = {
  domain?: string; relation?: string; key?: Record<string, unknown>; column?: string; period?: string | null; engine?: string; terms?: unknown;
  filter?: Record<string, unknown>; rows?: number; method?: string;
};
export type Fig = { value: number | null; unit: string; source: Source; label?: string };
export type Plain = { lines: string[]; words: number };
export type Structure = { kind: "terms" | "selected" | "recommended" | "ask"; label: string; note: string };
type Base = { proposal_id: string; obligor: string; headline: string; plain: Plain; structure?: Structure; method?: string; trace_id?: string };

export type Frontier = Base & {
  price_lever: string;
  base: { sva: Fig; raroc: Fig; hurdle: Fig; price: Fig; sva_per_bp: Fig; gap_bps: Fig };
  worth: { key: string; label: string; available: boolean; why?: string; per?: string; worth_bps?: Fig; sva_change?: Fig; raroc_after?: Fig }[];
  offers: { key: string; label: string; rank: number; acceptable: boolean; hard_breaches: string[]; approval: string; sva: Fig; raroc: Fig; client_cost: Fig }[];
  assumptions: Record<string, number>;
};
export type Premortem = Base & {
  paths: { key: string; rank: number; driver: string; breaking_severity: string; probability: Fig; speed: string; speed_class: string;
    first_warning: string; ews_rule: string; lead: string; what_breaks: string[]; dscr_at_break?: Fig;
    calibration: { label: string; window?: string; freq_labels?: string[]; method?: string; move?: number; unit?: string } }[];
  pd_12m: Fig; note: string; stress_run: string | null;
};
export type Precedents = Base & {
  this_deal: { sector: string; rating: string; amount: number; family: string; collateral: string | null; decision: string };
  precedents: { id: string; kind: string; name: string; decision: string; date: string; level?: string; conditions: string; performance: string;
    similarity: Fig; sector: string; rating: string; amount: Fig; basis_text: string; href: string;
    similarity_basis: { factor: string; weight: number; score: number; this: unknown; past: unknown }[] }[];
  inconsistent: boolean; weights: Record<string, number>; note: string;
};
export type Pricing = Base & {
  price_lever: string; price: Fig; percentile: Fig; peers: Fig; breakeven: Fig; gap_to_breakeven: Fig; raroc: Fig; hurdle: Fig;
  quartiles: Record<"p10" | "p25" | "p50" | "p75" | "p90", Fig>; basis_used: Record<string, string>; dropped: string[];
  histogram: { from_bps: number; to_bps: number; n: number; deal: boolean }[];
};
export type Revenue = Base & {
  verdict: string; period: { revenue: string; inflows: string };
  inflows: { label: string; kind: string; months?: number; value: Fig }[];
  sales_backed: Fig; revenue: Fig | null; coverage: Fig; gap: Fig; vat_sales: Fig | null; vat_coverage: Fig | null;
  implied: { ebitda_cut: Fig; dscr_after: Fig; leverage_after: Fig; dscr_now: Fig; leverage_now: Fig } | null;
  monthly: { month: string; this_bank: number; other_banks: number }[]; note: string;
};
export type RenewalDiff = Base & {
  applies: boolean; case_type: string;
  approval: { ref: string; date: string; authority?: string; basis: string; text?: string } | null;
  rows: { area: string; item: string; then: string; now: string; change: string; direction: "better" | "worse" | "same" | "n/a"; note: string; evidence: Fig[] }[];
  counts?: { worse: number; better: number; rows: number };
};
export type Party = {
  borrower_id: string; name: string; status: string; worst_stage: number | null; in_litigation: boolean; links: string[]; rating: string;
  exposure: Fig; adverse: boolean; href?: string;
  effect?: { channels: string[]; notches: number; raroc_after: Fig; sva_after: Fig; leverage_after: Fig; clears_after: boolean; approval_after: string };
};
export type Contagion = Base & {
  parties: Party[]; adverse_count: number; adverse_exposure: Fig; base: { raroc: Fig; clears: boolean; approval: string };
  combined: { parties: string[]; notches: number; raroc_after: Fig; sva_after: Fig; clears_after: boolean; approval_after: string } | null;
  conditions: { text: string; kind?: string; due?: string }[];
};
export type RQuestion = {
  id: string; rank: number; source: string; score: number; question: string; fact: string; suggested_answer: string; status: string;
  avoided: boolean; avoided_reason: string; evidence: (Fig | { value: null; source: Source })[]; similarity_basis?: string;
};
export type Rehearsal = Base & {
  header: string; questions: RQuestion[]; avoids: { note: string; items: { id: string; question: string; reason: string; source: string }[] };
  raroc: Fig; approval: { level: string };
};

export type Intel2Key = "frontier" | "premortem" | "precedents" | "pricing" | "revenue" | "renewal-diff" | "contagion" | "rehearsal";

/** key = API path; panel = the `?intel=` / More-menu key (unique across every intelligence panel). */
export const INTEL2_FEATURES: { key: Intel2Key; panel: string; code: string; label: string; step: string; stepKeys: string[] }[] = [
  { key: "frontier", panel: "frontier", code: "D6", label: "Negotiation frontier", step: "Structure", stepKeys: ["structure"] },
  { key: "premortem", panel: "premortem", code: "D7", label: "Default pre-mortem", step: "Analysis + Recommendation", stepKeys: ["analysis", "recommendation"] },
  { key: "precedents", panel: "precedents", code: "D8", label: "Precedent explorer", step: "Review", stepKeys: ["review"] },
  { key: "pricing", panel: "pricing", code: "D9", label: "Pricing benchmark", step: "Proposal + Structure", stepKeys: ["proposal", "structure"] },
  { key: "revenue", panel: "revenue-check", code: "D10", label: "Revenue truth check", step: "Proposal check + Financial quality",
    stepKeys: ["proposal", "check", "proposal-check", "review"] },
  { key: "renewal-diff", panel: "renewal-diff", code: "D11", label: "Renewal diff", step: "Proposal (renewals)", stepKeys: ["proposal"] },
  { key: "contagion", panel: "group-contagion", code: "D12", label: "Group contagion", step: "Review + Group & SWOT", stepKeys: ["review"] },
  { key: "rehearsal", panel: "challenger", code: "D13", label: "Committee questions", step: "More · Committee questions", stepKeys: ["recommendation"] },
];

/** The features the plan places in a step (renewal diff only on renewals). */
export function featuresForStep(step: string, caseType?: string | null): typeof INTEL2_FEATURES {
  return INTEL2_FEATURES.filter((f) => f.stepKeys.includes(step) && (f.key !== "renewal-diff" || /renewal/.test(caseType ?? "")));
}

export const pct = (x: number | null | undefined, dp = 1): string => (x == null ? "n/a" : `${(x * 100).toFixed(dp)}%`);
export const mn = (x: number | null | undefined, dp = 1): string =>
  (x == null ? "n/a" : `${x < 0 ? "−" : ""}SAR ${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: dp, minimumFractionDigits: dp })}m`);
export const bps = (x: number | null | undefined): string => (x == null ? "n/a" : `${Math.round(x).toLocaleString("en-US")} bps`);
export const signedBps = (x: number | null | undefined): string => (x == null ? "n/a" : `${x >= 0 ? "+" : "−"}${Math.abs(Math.round(x))} bps`);

export function sourceLine(s: Source | null | undefined): string {
  if (!s) return "–";
  const key = Object.entries(s.key ?? {}).map(([k, v]) => `${k}=${String(v)}`).join(", ");
  const head = [s.domain, s.relation, key, s.column].filter(Boolean).join(" · ");
  return s.engine ? `${s.engine} on ${head}` : head;
}

export function directionTone(d: string): "positive" | "negative" | "neutral" {
  return d === "better" ? "positive" : d === "worse" ? "negative" : "neutral";
}

export function verdictTone(v: string): "positive" | "warning" | "negative" | "neutral" {
  return v === "supported" ? "positive" : v === "partly supported" ? "warning" : v === "not supported" ? "negative" : "neutral";
}
