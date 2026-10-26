/**
 * PLAN_R12 Session T (I18): "Try it on your documents" on the Deal Desk service (/api/v1/dealdesk/try-docs/*).
 *
 * The participant drops a proposal (PDF, Word or scan; English or Arabic) and a policy; the UI runs the steps one by
 * one (learn the policy, extract the deal, review against their clauses, counter-proposal and committee paper, draft
 * in their memo's language), each timed, and wipes the demo session on exit. The helpers below are pure and tested
 * (try-docs-api.test.ts).
 */
import { friendlyError } from "../../../../lib/v5/errors.ts";

const ENGINE = "/api/v1/dealdesk";

export function tryOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class TryError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${tryOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new TryError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new TryError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

// ---------------------------------------------------------------- schemas

export type StepKey = "read" | "policy" | "extract" | "review" | "counter" | "draft";
export type StepStatus = "pending" | "running" | "done" | "error";
export type Mode = "deterministic" | "model";

export interface FoundRow {
  id: string; metric?: string; label?: string; type: string; clause?: string; quote?: string; value?: unknown; unit?: string;
  checkability?: string; rule_id?: string | null; status: string; conflict?: { regulation: string; message: string } | null;
  param?: { table?: string; row?: string; field?: string; proposed?: unknown; in_force?: unknown; change?: string } | null;
}
export interface MissingRow { metric: string; label: string; value: unknown; unit: string; source: string; default: boolean; checked: boolean }
export interface PolicyResult {
  found: FoundRow[]; missing: MissingRow[]; rules: unknown[]; conflicts: { clause: string; label: string; message: string }[];
  version: { id: string; status: string; applies_to: string } | null; summary: string;
}
export interface DealField { field: string; label: string; value: unknown; source: string; reader?: string }
export interface DefaultRow { field: string; label: string; value: unknown; why: string }
export interface ExtractResult {
  deal_id: string; fields: DealField[]; defaults: DefaultRow[];
  lines: { facility: string; existing: number | null; proposed: number | null; pricing_bps: number | null; facility_type?: string }[];
  currency_in_proposal: string; aed_sar: number | null; assumed: string[];
  published: { published: boolean; via: string; scope: string };
  deal: { name: string; sector: string; rating: string; facility_type: string; currency: string; amount: number; tenor_years: number;
    margin_bps: number; funded_share_pct: number; financials: Record<string, number | string | null> };
}
export interface Finding {
  rule_id: string; title: string; severity: "critical" | "major" | "minor" | string; verdict: string; finding: string;
  policy_ref?: string; source: string; quote?: string;
}
export interface ReviewResult {
  engine: string; headline?: string | null; decision?: string | null; tone?: string | null; findings: Finding[];
  severity: { critical: number; major: number; minor: number }; policy_checks: Finding[];
  policy_counts: { supported: number; contradicted: number; exception: number; unverifiable: number }; summary: string;
}
export interface CounterResult {
  engine: string; counter_proposals: Record<string, unknown>[]; summary: string;
  paper: { answer?: { decision?: string; headline?: string } ; doa?: { level?: string } } & Record<string, unknown>;
}
export interface DraftSection { key: string; heading: string; paragraphs: string[]; bullets?: string[]; table?: { header: string[]; rows: unknown[][] } }
export interface DraftResult { language: "en" | "ar"; direction: "ltr" | "rtl"; engine: string; sections: DraftSection[]; words: number; style_score: number | null; summary: string }
export interface Step {
  key: StepKey; label: string; status: StepStatus; seconds: number | null; summary: string; error?: string | null;
  result: unknown;
}
export interface TrySession {
  session_id: string; created_at: string; mode: Mode; notice: string; model_notice: string | null;
  documents: Record<string, { name: string; method: string; pages: number; language: "en" | "ar"; characters: number }>;
  deal_id: string | null; steps: Step[]; next: StepKey | null; total_seconds: number; complete: boolean;
}
export interface Overview {
  notice: string; model_notice: string; model_available: boolean; modes: Mode[]; default_mode: Mode;
  ocr: { available: boolean; arabic: boolean }; accepted: string[]; steps: { key: StepKey; label: string }[];
  fallback: { proposal: string; policy: string; note: string }; ttl_hours: number; integrations: Record<string, string>;
}
export interface Wiped { session_id: string; wiped: boolean; rows_removed: number; files: Record<string, string>; seconds: number }

// ---------------------------------------------------------------- API

const enc = encodeURIComponent;
export const tryDocs = {
  overview: () => call<Overview>("/try-docs"),
  start: (proposal: File, policy: File | null, mode: Mode) => {
    const fd = new FormData();
    fd.append("proposal", proposal);
    if (policy) fd.append("policy", policy);
    fd.append("mode", mode);
    return call<TrySession>("/try-docs/sessions", { method: "POST", body: fd });
  },
  fallback: (mode: Mode, which = "twin_b") =>
    call<TrySession>("/try-docs/sessions/fallback", { method: "POST", body: JSON.stringify({ mode, which }) }),
  get: (sid: string) => call<TrySession>(`/try-docs/sessions/${enc(sid)}`),
  step: (sid: string, step: StepKey) => call<TrySession>(`/try-docs/sessions/${enc(sid)}/steps/${enc(step)}`, { method: "POST" }),
  approvePolicy: (sid: string) =>
    call<{ onboarding_session: string; items: number; where: string }>(`/try-docs/sessions/${enc(sid)}/approve-policy`, { method: "POST" }),
  wipe: (sid: string) => call<Wiped>(`/try-docs/sessions/${enc(sid)}`, { method: "DELETE" }),
  wipeHref: (sid: string) => `${tryOrigin()}${ENGINE}/try-docs/sessions/${enc(sid)}/wipe`,
  draftHref: (sid: string) => `${tryOrigin()}${ENGINE}/try-docs/sessions/${enc(sid)}/draft.docx`,
  paperHref: (sid: string) => `${tryOrigin()}${ENGINE}/try-docs/sessions/${enc(sid)}/paper.docx`,
};

// ---------------------------------------------------------------- pure helpers

export const ACCEPT = ".docx,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.md";

/** The steps still to run, in order, after the given session state. */
export function remaining(s: TrySession): StepKey[] {
  return s.steps.filter((x) => x.status === "pending" || x.status === "error").map((x) => x.key);
}

export function secs(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return x < 10 ? `${x.toFixed(1)} s` : x < 60 ? `${Math.round(x)} s` : `${Math.floor(x / 60)} min ${Math.round(x % 60)} s`;
}

export function stepTone(st: StepStatus): "positive" | "negative" | "accent" | "neutral" {
  return st === "done" ? "positive" : st === "error" ? "negative" : st === "running" ? "accent" : "neutral";
}

export function stepStatusLabel(st: StepStatus): string {
  return { pending: "Waiting", running: "Running", done: "Done", error: "Stopped" }[st];
}

export function sevTone(s: string): "negative" | "warning" | "neutral" {
  return s === "critical" ? "negative" : s === "major" ? "warning" : "neutral";
}

export function verdictLabel(v: string): string {
  return ({ supported: "Met", contradicted: "Breached", exception: "Breached", unverifiable: "Needs data" } as Record<string, string>)[v] ?? v;
}

export function verdictTone(v: string): "positive" | "negative" | "warning" | "neutral" {
  return v === "supported" ? "positive" : v === "contradicted" || v === "exception" ? "negative" : v === "unverifiable" ? "warning" : "neutral";
}

const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** A value as a banker reads it: numbers with separators, ratings and text as given, nothing for null. */
export function fmtValue(v: unknown, unit?: string): string {
  if (v == null || v === "") return "–";
  if (isNum(v)) {
    const s = Math.abs(v) >= 1000 ? v.toLocaleString("en-US", { maximumFractionDigits: 1 }) : String(Math.round(v * 100) / 100);
    if (!unit) return s;
    if (unit === "pct" || unit === "%") return `${s}%`;
    if (unit === "x") return `${s}x`;
    if (["days", "months", "years", "count", "times"].includes(unit)) return `${s} ${unit === "count" ? "" : unit}`.trim();
    if (unit === "money") return `${s}m`;
    return `${s} ${unit}`;
  }
  if (Array.isArray(v)) return v.map((x) => fmtValue(x)).join("–");
  if (typeof v === "object") {
    const e = Object.entries(v as Record<string, unknown>);
    return e.slice(0, 4).map(([k, x]) => `${k} ${fmtValue(x)}`).join(", ") + (e.length > 4 ? " …" : "");
  }
  return String(v);
}

export function facilityLabel(t: string): string {
  return ({ term_loan: "Term finance", revolver: "Revolving working capital", performance_lg: "Performance LG", financial_lg: "Financial LG",
    trade_lc: "Trade LC" } as Record<string, string>)[t] ?? t;
}

/** One line for the deal the proposal became. */
export function dealLine(d: ExtractResult["deal"]): string {
  return `${d.name} · ${d.sector} · ${d.rating} · ${d.currency} ${fmtValue(d.amount)}m ${facilityLabel(d.facility_type).toLowerCase()}, ` +
    `${d.tenor_years} year${d.tenor_years === 1 ? "" : "s"}, ${d.margin_bps} bps`;
}

/** The answer line once every step is done. */
export function answerLine(s: TrySession): string {
  if (!s.complete) {
    const n = s.steps.filter((x) => x.status === "done").length;
    return `${n} of ${s.steps.length} steps done in ${secs(s.total_seconds)}.`;
  }
  const rev = s.steps.find((x) => x.key === "review")?.result as ReviewResult | undefined;
  const dec = rev?.decision ? ` Review: ${rev.decision}.` : "";
  const n = rev ? rev.findings.length : 0;
  return `From upload to drafted memo in ${secs(s.total_seconds)}: ${n} finding${n === 1 ? "" : "s"} against your policy and the rule book.${dec}`;
}

export function langLabel(l: string): string {
  return l === "ar" ? "Arabic" : "English";
}

/** The file chosen is one the service reads. */
export function acceptedFile(name: string): boolean {
  const low = name.toLowerCase();
  return ACCEPT.split(",").some((e) => low.endsWith(e));
}
