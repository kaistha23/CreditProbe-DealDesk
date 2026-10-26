/**
 * v5 Policy Docs client (docs/v5/PLAYBOOK_SERVICE.md "Policy Docs", docs/v5/PLAYBOOK_API.md section 9).
 *
 * Talks ONLY to the Playbook and Policy Docs service (`backend.playbook_v5.api`, port 8506 by default,
 * `NEXT_PUBLIC_PLAYBOOK_API`), routes under `/api/v1/policy`. Identity is the `cp_session` cookie, so every
 * call sends credentials. Writes are refused (403) while the Administrator is viewing as someone.
 */
import { friendlyError } from "./errors.ts";

export function policyOrigin(): string {
  return (process.env.NEXT_PUBLIC_PLAYBOOK_API ?? "http://127.0.0.1:8506").replace(/\/$/, "");
}

const P = "/api/v1/policy";

export class PolicyError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Init = { method?: string; body?: unknown; form?: FormData };

async function request<T>(path: string, init: Init = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${policyOrigin()}${P}${path}`, {
      method: init.method ?? "GET",
      credentials: "include",
      cache: "no-store",
      headers: init.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: init.form ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new PolicyError(0, `Policy Docs is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Policy Docs", response.status, body);
    throw new PolicyError(response.status, message);
  }
  return body as T;
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") out.set(k, String(v));
  const s = out.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- types

export interface Person { username: string; name: string; initials: string; title: string }

export type DocKind = "policy" | "circular" | "guideline" | "regulation";
export type DocStatus = "active" | "pending" | "superseded" | "withdrawn" | "rejected" | "reference";
export type Book = "corporate" | "retail";

export interface DocRow {
  id: string; title: string; kind: DocKind; reference: string; book: string; status: DocStatus;
  effective_from: string | null; approved_by: Person | null; uploaded_by: Person; uploaded_at: string;
  clause_count: number; summary: string; href: string;
  category?: string; issuer?: string; jurisdiction?: string; source_file?: string;
}

export interface ClauseSource { doc_id: string; kind: DocKind | string; reference: string }

export interface Clause {
  clause_id: string; book: string; section: string; section_title: string; title: string; rule: string;
  thresholds: Record<string, string | number>; applies_to: string[]; owner: string; last_reviewed: string | null;
  levers: string[]; effective_from: string | null; source: ClauseSource; status: "active" | "proposed" | "superseded";
}

export type ClauseChange = "new" | "amends" | "unchanged";
export interface InterpretedClause {
  clause_id: string; title: string; rule: string; limit: string | null; threshold: string | null; scope: string;
  book: string; change: ClauseChange; current_rule: string | null;
}
export interface Interpretation {
  summary: string;
  clauses: InterpretedClause[];
  changes: { clause_id: string; before: string; after: string; effect: string }[];
  affects: { books: string[]; segments: string[]; ews_rules: { rule_id: string; name: string; why: string }[] };
  question: string;
  method: "rules" | "model";
}

export interface DocFile { id: string; name: string; size: number; content_type: string }

export interface PackVersionRow {
  version: number | string; label: string; created_at: string; created_by: Person; effective_from: string | null;
  approved_by: Person | null; change: string; documents: string[]; active: boolean; clause_count: number;
}

/** A clause as `credit_policy.json` writes it inside `books.<book>.sections[].clauses[]`. */
export interface PackFileClause {
  clause: string; title: string; rule: string; thresholds?: Record<string, string | number>; applies_to?: string[];
  owner?: string; last_reviewed?: string; levers?: string[]; effective_from?: string | null;
  source?: ClauseSource; [k: string]: unknown;
}
export interface PackBook {
  book_id: string; title: string; approved_by?: string; approved_on?: string; scope?: string;
  sections: { section: string; title: string; clauses: PackFileClause[] }[];
}
/** A pack version with its merged pack (`books` as in `credit_policy.json`). */
export interface PackVersion extends PackVersionRow {
  books?: Record<string, PackBook>;
  /** Not in the spec; read when the service also sends the flat clause list. */
  clauses?: Clause[];
}

export interface Doc extends DocRow {
  clauses: Clause[]; interpretation: Interpretation | null; files: DocFile[]; text_excerpt: string;
  versions: PackVersionRow[];
}

export interface ExplainClause {
  clause_id: string; title: string; text: string; effective_from: string | null; source: ClauseSource;
  approved_by: string | null; href: string;
}
export interface Explain { pack_version: string; clauses: ExplainClause[]; sentence: string | null }

export interface ExplainParams {
  book: Book | string;
  measure: string;
  driver?: string;
  segment?: string;
  period?: string;
}

export type Decision =
  | { add: true; effective_from: string; approver: string; note: string }
  | { add: false; note: string };

// ---------------------------------------------------------------- explain cache

// Several notes on one screen ask the same question; one request answers them all. A write to the pack clears it.
const EXPLAIN_TTL_MS = 60_000;
const explainCache = new Map<string, { at: number; promise: Promise<Explain> }>();

function clearExplain(): void {
  explainCache.clear();
}

// ---------------------------------------------------------------- calls

export const policy = {
  documents: (p: { kind?: DocKind | ""; q?: string } = {}) =>
    request<{ documents: DocRow[] }>(`/documents${qs({ kind: p.kind, q: p.q?.trim() })}`),
  document: (id: string) => request<Doc>(`/documents/${encodeURIComponent(id)}`),
  fileUrl: (docId: string, fileId: string) =>
    `${policyOrigin()}${P}/documents/${encodeURIComponent(docId)}/files/${encodeURIComponent(fileId)}`,

  upload: (file: File, meta: { title?: string; kind?: DocKind | ""; reference?: string } = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (meta.title?.trim()) form.append("title", meta.title.trim());
    if (meta.kind) form.append("kind", meta.kind);
    if (meta.reference?.trim()) form.append("reference", meta.reference.trim());
    return request<{ document: Doc; interpretation: Interpretation }>(`/documents/upload`, { method: "POST", form });
  },
  decision: async (id: string, body: Decision) => {
    const r = await request<{ document: Doc; pack: PackVersion }>(`/documents/${encodeURIComponent(id)}/decision`,
      { method: "POST", body });
    clearExplain();
    return r;
  },
  withdraw: async (id: string, note: string) => {
    const r = await request<{ document: Doc; pack: PackVersion }>(`/documents/${encodeURIComponent(id)}/withdraw`,
      { method: "POST", body: { note } });
    clearExplain();
    return r;
  },

  pack: () => request<PackVersion>(`/pack`),
  versions: () => request<{ versions: PackVersionRow[] }>(`/pack/versions`),
  version: (v: number | string) => request<PackVersion>(`/pack/versions/${encodeURIComponent(String(v))}`),
  clauses: (p: { book?: string; q?: string } = {}) => request<{ clauses: Clause[] }>(`/clauses${qs(p)}`),

  /** The policy lookup behind "Stage 2 rose because ...". Read-only, so allowed while viewing as. */
  explain: (p: ExplainParams): Promise<Explain> => {
    const key = qs({ book: p.book, measure: p.measure, driver: p.driver, segment: p.segment, period: p.period });
    const hit = explainCache.get(key);
    if (hit && Date.now() - hit.at < EXPLAIN_TTL_MS) return hit.promise;
    const promise = request<Explain>(`/explain${key}`);
    explainCache.set(key, { at: Date.now(), promise });
    promise.catch(() => { if (explainCache.get(key)?.promise === promise) explainCache.delete(key); });
    return promise;
  },
};

// ---------------------------------------------------------------- helpers

/** The clause list of a pack version: the flat list when sent, otherwise read out of the merged `books`. */
export function packClauses(pv: PackVersion): Clause[] {
  if (Array.isArray(pv.clauses)) return pv.clauses;
  const out: Clause[] = [];
  for (const [bookKey, book] of Object.entries(pv.books ?? {})) {
    for (const sec of book.sections ?? []) {
      for (const c of sec.clauses ?? []) {
        out.push({
          clause_id: c.clause, book: book.book_id ?? bookKey, section: sec.section, section_title: sec.title,
          title: c.title, rule: c.rule, thresholds: c.thresholds ?? {}, applies_to: c.applies_to ?? [],
          owner: c.owner ?? "", last_reviewed: c.last_reviewed ?? null, levers: c.levers ?? [],
          effective_from: c.effective_from ?? null,
          source: c.source ?? { doc_id: "", kind: "policy", reference: "" }, status: "active",
        });
      }
    }
  }
  return out;
}

export const KIND_LABEL: Record<DocKind, string> = { policy: "Policy", circular: "Circular", guideline: "Guideline", regulation: "Regulatory" };

export const STATUS_LABEL: Record<DocStatus, string> = {
  active: "Active", pending: "Pending", superseded: "Superseded", withdrawn: "Withdrawn", rejected: "Rejected",
  reference: "Reference",
};

export function bookLabel(book: string | null | undefined): string {
  if (!book) return "—";
  if (book === "corporate") return "Corporate";
  if (book === "retail") return "Retail";
  if (book === "both" || book === "all") return "Corporate and Retail";
  return book.charAt(0).toUpperCase() + book.slice(1);
}

/** Today as YYYY-MM-DD in the reader's own calendar (the default effective date). */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "1 clause", "12 clauses". */
export function clauseWord(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  return `${v.toLocaleString("en-US")} clause${v === 1 ? "" : "s"}`;
}
