/**
 * PLAN_R11 Session R: proposal review intelligence on the Deal Desk service (/api/v1/dealdesk).
 *
 *   POST  /proposals/{id}/review              the review workspace
 *   GET   /proposals/{id}/review/sheet(.docx) the committee decision sheet (JSON, Word)
 *   POST  /proposals/{id}/review/draft        RM "Draft from data" (GET .../draft.docx for Word)
 *   GET   /review/r11/subjects                every reviewable proposal with its decision
 *   GET   /conditions, /conditions/summary    tracked conditions; PATCH /conditions/{id}
 *
 * Amounts are millions in the deal currency (AED for the prepared cases, SAR or USD for Deal Desk proposals);
 * ratios are decimals. Pure helpers at the bottom are unit-tested (dealdesk-review.test.ts).
 */
import { friendlyError } from "./errors.ts";
import type { EngineFinding, EngineVerdict, FindingCounts } from "./dealdesk-engines.ts";

const ENGINE = "/api/v1/dealdesk";

export function reviewOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${reviewOrigin()}${ENGINE}${path}`, { ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" } });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export type Verdict = "supported" | "contradicted" | "exception" | "unverifiable";
export type Severity = "critical" | "major" | "minor";
export type Category = "data" | "consistency" | "policy" | "connected";
export type CondStatus = "open" | "due" | "overdue" | "met" | "waived" | "breached";

export interface Evidence { source: string; text: string }
export interface Check {
  check_id: string; rule_id: string; category: Category; title: string; tests: string; verdict: Verdict; severity: Severity | null;
  value: unknown; threshold: unknown; unit: string; finding: string; evidence: Evidence[]; policy_ref: string; crm_article: string;
  doa: { rank: number; level: string } | null; claim_ids: string[]; line_ids: string[];
}
export interface MemoLine {
  line_id: string; kind: "text" | "row"; text: string; mark: Verdict | null; check_ids: string[]; claim_ids: string[];
  evidence: { verdict: Verdict; title: string; finding: string; source: string }[];
}
export interface MemoSection { title: string; line_id: string; lines: MemoLine[] }
export interface CounterProposal {
  id: string; title: string; terms: string[]; amount: number; raroc: number | null; hurdle: number | null; clears_hurdle: boolean | null;
  sva: number; ecl_day1: number; rwa: number; approval: string | null; method: "optimiser" | "engine"; hard_breaches: string[];
  soft_breaches: string[]; conditions_precedent: string[];
  structure: { amount: number; currency: string; tenor_years: number; margin_bps: number; commission_bps: number | null;
    funded_share_pct: number | null; cash_margin_pct: number | null; covenant_package: string | null };
  vs_ask: { raroc: number; sva: number; ecl_day1: number };
  forward_risk: { p_stage2_next_q: number | null; p_dpd30_next_q: number | null; ecl_q4: number | null; model: string | null } | null; basis: string;
  /** R14 E: the engine counter-offer (CP-E) lists each critical/major finding with its cure; R11 packages say what they leave open. */
  cures?: { finding_id: string; title: string; severity: string; category: string; cure_kind: string; cure_kind_label: string; cure: string;
    owner: string; when: string; curable: boolean }[];
  not_curable?: { finding_id: string; title: string }[]; headline?: string; note?: string; approval_rule?: string;
}
export interface Condition {
  id: string; deal_id: string; deal_name: string; rule_id: string; kind: "CP" | "covenant" | "watch"; what: string; source: string;
  due_date: string | null; due_text: string; owner: string; origin: string; note: string; status: CondStatus;
  evaluation: "data" | "manual"; data_value: Record<string, unknown> | null;
}
export interface CondSummary { total: number; due: number; deals_due: string[]; by_status: Record<CondStatus, number>; line: string; data_evaluated: number }
export interface Horizon {
  quarters: number; anchor: string; window: string; match: string; N: number; stage2: number; dpd30: number;
  stage2_rate: number | null; dpd30_rate: number | null; book_N: number; book_stage2_rate: number | null; book_dpd30_rate: number | null;
  examples: { borrower_id: string; name: string; rating: string; ead: number; stage2: boolean; dpd30: boolean }[];
}
export interface Workspace {
  subject: { kind: "case" | "dd"; id: string; name: string; group: string | null; sector: string; rating: string; tier: string; currency: string;
    as_of: string; amount_ccy: number; amount_sar: number; existing_ccy: number };
  as_of: string; reviewed_at: string;
  answer: { decision: string; tone: "negative" | "warning" | "positive"; headline: string; counts: Record<Severity, number>; approval: string;
    counter_proposal: string | null };
  memo: { file: string; sections: MemoSection[]; counts: { lines: number; figures: number; assertions: number } };
  findings: Check[]; checks: Check[]; by_category: Record<Category, Record<Verdict, number>>; verdicts: Record<Verdict, number>;
  doa: { rank: number; level: string; exposure_sar_mn: number; binding: { basis: string; rank: number; detail: string; level?: string };
    reasons: { basis: string; rank: number; detail: string; level?: string }[]; basis: string; rule?: string };
  counter: { ask: { raroc: number | null; hurdle: number | null; clears_hurdle: boolean | null; sva: number; ecl_day1: number; rwa: number;
    amount: number; currency: string } | null; counter_proposals: CounterProposal[]; basis?: string };
  conditions: { items: Condition[]; summary: CondSummary; as_of: string; basis: string };
  precedent: { sector: string; rating: string; horizons: Horizon[]; features_used: string[];
    features_not_in_book: { feature: string; reason: string }[]; line: string; basis: string };
  rules: { version: string; count: number; file: string };
  /** R14 E: the findings engine (every finding incl. dd_review_finding and financial quality, one count source, verdict). */
  engine?: { findings: EngineFinding[]; counts: FindingCounts; chips: { key: string; label: string; count: number }[]; verdict: EngineVerdict; source: string };
  powered_by: { pack: string; name: string; rules: string[]; confidence: string; trace: string };
  basis: string;
}
export interface DraftSection { key: string; title: string; kind: "fact" | "judgement"; source: string; text: string;
  table: { header: string[]; rows: string[][] } | null }
export interface Draft { subject: Workspace["subject"]; sections: DraftSection[]; facts_filled: number; basis: string }
export interface Rule { id: string; category: Category; title: string; tests: string; severity: Severity | null; on_fail: "contradicted" | "exception" | null;
  threshold: unknown; unit: string | null; policy_ref: string | null; crm_article: string | null; doa_rank: number | null; scope: string[] | null; enabled: boolean | null }
export interface Subject { id: string; kind: "case" | "dd"; name: string; sector: string; rating: string; amount: number; currency: string;
  decision: string | null; tone?: string; counts?: Record<Severity, number>; approval?: string; contradicted?: number }

const enc = encodeURIComponent;
export const reviewApi = {
  workspace: (id: string, refresh = false) => call<Workspace>(`/proposals/${enc(id)}/review`, { method: "POST", body: JSON.stringify({ refresh }) }),
  uploadMemo: (id: string, file: File) => { const f = new FormData(); f.append("file", file);
    return call<Workspace>(`/proposals/${enc(id)}/review/memo`, { method: "POST", body: f }); },
  draft: (id: string) => call<Draft>(`/proposals/${enc(id)}/review/draft`, { method: "POST", body: "{}" }),
  rules: () => call<{ version: string; effective_from: string; categories: Record<Category, string>; rules: Rule[] }>("/review/r11/rules"),
  subjects: () => call<{ subjects: Subject[]; clean_memos: string[] }>("/review/r11/subjects"),
  conditions: (dealId = "") => call<{ items: Condition[]; summary: CondSummary }>(`/conditions${dealId ? `?deal_id=${enc(dealId)}` : ""}`),
  summary: () => call<CondSummary>("/conditions/summary"),
  patch: (id: string, change: Partial<{ status: CondStatus | "auto"; owner: string; note: string; due_date: string }>) =>
    call<Condition>(`/conditions/${enc(id)}`, { method: "PATCH", body: JSON.stringify(change) }),
  sheetUrl: (id: string) => `${reviewOrigin()}${ENGINE}/proposals/${enc(id)}/review/sheet.docx`,
  draftUrl: (id: string) => `${reviewOrigin()}${ENGINE}/proposals/${enc(id)}/review/draft.docx`,
};

// ---------------------------------------------------------------- pure helpers

export const VERDICT_LABEL: Record<Verdict, string> = {
  supported: "Supported", contradicted: "Contradicted", exception: "Exception", unverifiable: "Unverifiable",
};
export const VERDICT_TONE: Record<Verdict, "positive" | "negative" | "warning" | "neutral"> = {
  supported: "positive", contradicted: "negative", exception: "warning", unverifiable: "neutral",
};
export const SEVERITY_TONE: Record<Severity, "negative" | "warning" | "neutral"> = { critical: "negative", major: "warning", minor: "neutral" };
export const CATEGORY_LABEL: Record<Category, string> = {
  data: "Data", consistency: "Consistency", policy: "Policy and regulation", connected: "Connected parties",
};
export const STATUS_TONE: Record<CondStatus, "positive" | "negative" | "warning" | "neutral" | "accent"> = {
  met: "positive", waived: "neutral", open: "accent", due: "warning", overdue: "negative", breached: "negative",
};
export const STATUS_LABEL: Record<CondStatus, string> = {
  open: "Open", due: "Due", overdue: "Overdue", met: "Met", waived: "Waived", breached: "Breached",
};

/** Findings grouped by severity, in the order critical → major → minor, contradicted before exception. */
export function bySeverity(findings: Check[]): { severity: Severity; items: Check[] }[] {
  const order: Severity[] = ["critical", "major", "minor"];
  return order.map((s) => ({ severity: s, items: findings.filter((f) => f.severity === s)
    .sort((a, b) => (a.verdict === b.verdict ? a.rule_id.localeCompare(b.rule_id) : a.verdict === "contradicted" ? -1 : 1)) }))
    .filter((g) => g.items.length > 0);
}

/** "7 critical · 18 major · 1 minor" (zeros dropped); "No findings" when empty. */
export function countsLine(c: Record<Severity, number>): string {
  const parts = (["critical", "major", "minor"] as Severity[]).filter((s) => c[s] > 0).map((s) => `${c[s]} ${s}`);
  return parts.length ? parts.join(" · ") : "No findings";
}

/** Marked lines per verdict across the memo. */
export function markCounts(sections: MemoSection[]): Record<Verdict, number> {
  const out: Record<Verdict, number> = { supported: 0, contradicted: 0, exception: 0, unverifiable: 0 };
  for (const s of sections) for (const l of s.lines) if (l.mark) out[l.mark] += 1;
  return out;
}

/** Conditions in the tracker's order: breached, overdue, due, open, met, waived; then by due date. */
export function sortConditions(items: Condition[]): Condition[] {
  const rank: Record<CondStatus, number> = { breached: 0, overdue: 1, due: 2, open: 3, met: 4, waived: 5 };
  return [...items].sort((a, b) => rank[a.status] - rank[b.status] || (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999")
    || a.deal_id.localeCompare(b.deal_id));
}

/** Millions in the deal currency: "AED 656.8m", "SAR 1.57bn", "AED 0.45m". */
export function money(v: number | null | undefined, ccy: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1000) return `${ccy} ${(v / 1000).toFixed(2)}bn`;
  return `${ccy} ${v.toFixed(a >= 100 ? 1 : a >= 10 ? 1 : 2)}m`;
}

export function pct(v: number | null | undefined, d = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  return `${(v * 100).toFixed(d)}%`;
}

/** "+2.4pp" / "−1.0pp". */
export function pp(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const x = v * 100;
  return `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(1)}pp`;
}

/** "n of N" with the share, for the precedent line. */
export function nOfN(n: number, N: number): string {
  return N ? `${n} of ${N} (${Math.round((100 * n) / N)}%)` : "none";
}
