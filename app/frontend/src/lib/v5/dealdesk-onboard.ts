/**
 * PLAN_R11 P6 (Session O): "Learn from documents" on the Deal Desk service (/api/v1/dealdesk/onboarding/*).
 *
 * Upload the bank's credit policy (and its memos, DoA matrix, risk appetite statement); every learned item comes back
 * PROPOSED with its source quote; a checker accepts, edits or rejects each one, and each accept writes the next
 * version of the rule book and parameter tables with learned-from provenance. The helpers below are pure and tested
 * (dealdesk-onboard.test.ts).
 */
import { friendlyError } from "./errors.ts";

const ENGINE = "/api/v1/dealdesk";

export function onboardOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class OnboardError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${onboardOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new OnboardError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new OnboardError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

// ---------------------------------------------------------------- schemas

export type Checkability = "auto" | "manual";
export type ItemType = "threshold" | "condition" | "committee_question" | "structure" | "language";
export interface LearnedFrom { document?: string; documents?: string[]; clause?: string; quote?: string; kind?: string }
export interface ParamChange {
  table: string; row: string; field: string; proposed: unknown; in_force?: unknown; change?: "same" | "tighter" | "looser" | "changed" | "new";
  conversion?: string; version_in_force?: string; unit_in_force?: string;
}
export interface Item {
  id: string; type: ItemType; metric: string; label: string; clause?: string; section?: string; quote: string;
  value?: unknown; unit?: string; checkability: Checkability; why?: string; data_fields?: string[]; status: string;
  param?: ParamChange; rule?: { id: string; finding: string; crm_article?: string } & Record<string, unknown>;
  same_as?: string; conflict?: { regulation: string; message: string }; learned_from: LearnedFrom;
  question?: string; raised_in?: number; of?: number; memos?: string[] | number; sections?: { key: string; label: string; heading: string; share: number }[];
  phrases?: string[]; unmapped?: boolean;
}
export interface RegRow {
  id: string; item_id: string; clause: string; label: string; quote: string; policy_value: number; unit: string; regulation: string;
  regulation_value: number; regulation_quote: string; quote_verified: boolean; message: string; href: string; kind: string;
}
export interface Gap { id: string; kind: string; clause: string; message: string; severity: string; section?: string; missing?: number; of?: number; quote?: string }
export interface Decision { item_id: string; action: "accept" | "edit" | "reject"; by: string; at: string; note?: string; value?: unknown; version?: string }
export interface Summary {
  thresholds: number; conditions: number; rules: number; params: number; auto: number; manual: number; conflicts: number;
  data_gaps: number; section_gaps: number; committee: number; items: number; accepted: number; rejected: number; pending: number; text: string;
}
export interface Session {
  session_id: string; created_at: string; maker: string; bank: string;
  documents: { name: string; kind: string; clauses?: number; tables?: number; items?: number; sections?: number }[];
  items: Item[]; committee: Item[]; structure: Item[]; language: Item[]; conflicts: RegRow[]; consistent: RegRow[];
  gaps: { data: Gap[]; sections: Gap[] }; decisions: Record<string, Decision>; versions: string[]; summary: Summary;
  timings: { learn_s: number };
}
export interface Version {
  version: string; created_at: string; by: string; session_id: string; previous: string | null; accepted_items: string[];
  rules_added: number; params_changed: string[]; committee_questions: number; learned_from: string[]; applies_to: string;
}
export interface Overview { session: Session | null; versions: Version[]; demo: { policy: string; memos: string[] } }
export interface CommitteeAnswer { id: string; question: string; status: "answered" | "open"; where: string | null; answer?: string }
export interface DraftReview {
  proposal_id: string; version: string | null; draft_id: string; style_score: number | null; sections: string[];
  committee_answers: CommitteeAnswer[];
  review: { headline: { headline?: string; decision?: string; tone?: string } | string | null; findings: number;
    policy_checks: { rule_id: string; verdict: string; finding?: string; text?: string }[]; policy_findings: number;
    open_questions: { rule_id: string; finding: string }[] };
  timings: { draft_s: number; draft_to_review_s: number };
}

// ---------------------------------------------------------------- API

const enc = encodeURIComponent;
export const onboard = {
  overview: () => call<Overview>("/onboarding"),
  demo: () => call<Session>("/onboarding/demo", { method: "POST" }),
  learn: (files: { policy: File; memos?: File[]; doa?: File | null; appetite?: File | null }) => {
    const fd = new FormData();
    fd.append("policy", files.policy);
    for (const m of files.memos ?? []) fd.append("memos", m);
    if (files.doa) fd.append("doa", files.doa);
    if (files.appetite) fd.append("appetite", files.appetite);
    return call<Session>("/onboarding/learn", { method: "POST", body: fd });
  },
  session: (sid: string) => call<Session>(`/onboarding/sessions/${enc(sid)}`),
  decide: (sid: string, itemId: string, action: Decision["action"], value?: unknown, note?: string) =>
    call<{ decision: Decision; item: Item; version: Version | null; summary: Summary }>(
      `/onboarding/sessions/${enc(sid)}/items/${enc(itemId)}/decision`, { method: "POST", body: JSON.stringify({ action, value, note }) }),
  draftReview: (proposalId: string, version?: string) =>
    call<DraftReview>("/onboarding/draft-review", { method: "POST", body: JSON.stringify({ proposal_id: proposalId, version }) }),
  proposedHref: (sid: string, name: string) => `${onboardOrigin()}${ENGINE}/onboarding/sessions/${enc(sid)}/proposed/${enc(name)}`,
};

// ---------------------------------------------------------------- pure helpers

export type Filter = "all" | "rules" | "params" | "committee" | "structure" | "conflicts" | "pending";
export const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "Pending" }, { key: "rules", label: "Rules" }, { key: "params", label: "Parameters" },
  { key: "conflicts", label: "Weaker than CBUAE" }, { key: "committee", label: "Committee questions" },
  { key: "structure", label: "Structure and language" }, { key: "all", label: "All" },
];

export function allItems(s: Session): Item[] {
  return [...s.items, ...s.committee, ...s.structure, ...s.language];
}

export function filterItems(s: Session, f: Filter): Item[] {
  const xs = allItems(s);
  switch (f) {
    case "rules": return xs.filter((i) => i.rule);
    case "params": return xs.filter((i) => i.param);
    case "committee": return xs.filter((i) => i.type === "committee_question");
    case "structure": return xs.filter((i) => i.type === "structure" || i.type === "language");
    case "conflicts": return xs.filter((i) => i.conflict);
    case "pending": return xs.filter((i) => !s.decisions[i.id]);
    default: return xs;
  }
}

export function countFor(s: Session, f: Filter): number {
  return filterItems(s, f).length;
}

const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

export function fmtNum(x: number): string {
  return Number.isInteger(x) ? x.toLocaleString("en-US") : x.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

/** A value as the policy states it: "1.25x", "40%", "AED 300 m", "18 months", "B-". Tables in one line. */
export function fmtValue(value: unknown, unit = ""): string {
  if (value == null) return "condition";
  if (isNum(value)) {
    if (unit === "%" ) return `${fmtNum(value)}%`;
    if (unit === "x") return `${fmtNum(value)}x`;
    if (/^[A-Z]{3} m$/.test(unit)) return `${unit.slice(0, 3)} ${fmtNum(value)}m`;
    return unit ? `${fmtNum(value)} ${unit}` : fmtNum(value);
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((l: { level?: string; max_exposure_policy?: number | null; min_rating?: string }) =>
      `${l.level ?? "?"} ${l.max_exposure_policy == null ? "above" : fmtNum(l.max_exposure_policy)}${l.min_rating ? ` (${l.min_rating})` : ""}`).join(" · ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(([k, v]) =>
      `${k} ${Array.isArray(v) ? v.map((n) => fmtNum(Number(n))).join("–") : isNum(v) ? fmtNum(v) : String(v)}`).join(" · ");
  }
  return String(value);
}

/** The parameter in force and the proposed one, in the table's own unit: "1.2 → 1.25 (tighter)". */
export function paramLine(p: ParamChange): string {
  const f = (x: unknown) => (x == null ? "none" : isNum(x) ? fmtNum(x) : fmtValue(x));
  if (Array.isArray(p.proposed)) return `${p.table}: ${p.change ?? "new"}`;
  return `${f(p.in_force)} → ${f(p.proposed)}${p.change && p.change !== "new" ? ` (${p.change})` : ""}`;
}

export function changeTone(c?: string): "positive" | "negative" | "neutral" {
  return c === "tighter" ? "positive" : c === "looser" ? "negative" : "neutral";
}

export function statusOf(s: Session, id: string): "accepted" | "edited" | "rejected" | "proposed" {
  const d = s.decisions[id];
  if (!d) return "proposed";
  return d.action === "accept" ? "accepted" : d.action === "edit" ? "edited" : "rejected";
}

/** The answer first: "Learned 38 thresholds …; 6 clauses weaker than the CBUAE CRM Standards …". */
export function answerLine(s: Session): string {
  return s.summary.text;
}

/** An edit: a number for numeric values, the text otherwise. Throws on a bad number. */
export function parseEdit(item: Item, text: string): unknown {
  if (isNum(item.value)) {
    const v = Number(text.replace(/[,%x\s]/g, ""));
    if (!Number.isFinite(v)) throw new Error(`"${text}" is not a number`);
    return v;
  }
  if (item.type === "committee_question") {
    if (!text.trim()) throw new Error("The question is empty");
    return text.trim();
  }
  throw new Error("Only numbers and committee questions are edited here; reject and re-upload for other changes");
}

export function editable(item: Item): boolean {
  return isNum(item.value) || item.type === "committee_question";
}

export function sourceOf(item: Item): string {
  const lf = item.learned_from ?? {};
  if (lf.document) return `${lf.document}${lf.clause ? `, clause ${lf.clause}` : ""}`;
  const docs = lf.documents ?? [];
  return docs.length ? `${docs.length} memo${docs.length === 1 ? "" : "s"}` : "";
}

export function headlineText(h: DraftReview["review"]["headline"]): string {
  if (!h) return "";
  return typeof h === "string" ? h : (h.headline ?? h.decision ?? "");
}

export function secs(x: number): string {
  return `${x.toFixed(x < 10 ? 1 : 0)} s`;
}
