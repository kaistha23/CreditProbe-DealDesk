/**
 * v5 Lenses client (PLAN_R5 Session L).
 *
 * Talks to the Lenses service (port 8509, `NEXT_PUBLIC_LENSES_API`) with the session cookie
 * (`credentials: "include"`). The lens assistant is the shared convo layer mounted at
 * `/api/v1/lenses/convo` (docs/v5/CONVO_API.md), rendered with the shared thread (docs/v5/THREAD_API.md).
 * Every figure arrives with its display string (G5) and a trace (the SQL behind the (i)).
 */
import { friendlyError } from "./errors.ts";
import { RATING_ORDER, ratingRank, sortByRating } from "@/lib/v5/ratings";
import { fmt } from "@/lib/v5/format";
import type { PlanReply } from "./lenses-plan.ts";

export function lensesOrigin(): string {
  return (process.env.NEXT_PUBLIC_LENSES_API ?? "http://127.0.0.1:8509").replace(/\/$/, "");
}
const PREFIX = "/api/v1/lenses";
export const lensesUrl = (path: string) => `${lensesOrigin()}${PREFIX}${path}`;
export const convoBase = () => `${lensesOrigin()}${PREFIX}/convo`;

export class LensesError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(lensesUrl(path), {
      ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new LensesError(0, `Lenses is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new LensesError(response.status, friendlyError("Lenses", response.status, body));
  }
  return body as T;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export type Book = "corporate" | "retail";
export type Unit = "sar_mn" | "pct" | "ratio" | "bps" | "count" | "score" | "days" | "text";

export interface Trace { sql: string; relations: string[]; sources: string[]; period: string; row_count: number; engine: string; at: string }
/** PLAN_R6 L3: what the (i) says about a tile, in plain words with the tile's own figures. */
export interface Explain { shows: string; formula: string; read: string; look_for: string }

export interface Kpi {
  key: string; label: string; unit: Unit; value: number | null; display: string; prior: number | null; change: number | null;
  change_display: string | null; tone: "good" | "bad" | "neutral"; spark: { period: string; value: number | null }[]; source: string; trace: Trace; explain?: Explain | null;
}
export interface Column { key: string; label: string; unit: Unit }
export interface Tile {
  id: string; type: string; title: string; chart: string; size: "half" | "wide"; unit?: Unit;
  figure: { data: Record<string, unknown>[]; layout: Record<string, unknown> } | null;
  table: { columns: Column[]; rows: Record<string, unknown>[] } | null; trace: Trace | null; explain?: Explain | null; error?: string;
  badges?: { label: string; display: string; value: number | null }[]; links?: Record<string, string>;
}
export interface Rendered {
  lens_id: string; version: number; title: string; name: string; book: Book; period: string; periods: string[]; window: string[];
  scope: { dim: string; label: string; values: string[] }[]; scope_label: string; compare: { label: string } | null;
  kpis: Kpi[]; tiles: Tile[]; commentary: { markdown: string; source: string }; charts: number; untraced: number; ms: number;
  /** R13 L (J8): the deterministic reading at the top of the lens: where the scope stands and the 2-3 movements that matter. */
  interpretation?: Interpretation;
  intel?: { pack: { id: string; name: string; version: string }; findings: CrmFinding[]; built_at: number } | null;
}
export interface Interpretation {
  headline: string; period: string; prior: string; markdown: string; source: string;
  lines: { metric: string; tone: "good" | "bad" | "neutral"; text: string }[];
  trace: { sql: string; note: string };
}
export interface Thumb { figures: { label: string; display: string }[]; spark: (number | null)[]; period?: string }
export interface Card {
  lens_id: string; name: string; description: string; tags: string[]; book: Book; kind: "lens" | "template" | "featured"; owner: string; saved: boolean;
  updated_at: number; version: number; scope_label: string; tiles: number; thumb: Thumb; schedule: Schedule | null; mine: boolean; template_key: string;
}
export interface Schedule { cadence: string; recipients: string[]; next_at: number; note: string }
export interface Version { version: number; change: string; author: string; created_at: number }
export interface TileSpec { id: string; type: string; metric?: string; metrics?: string[]; dim?: string; chart?: string; column?: string; title?: string; top?: number;
  filters?: { dim: string; values: string[] }[] }
export interface Spec {
  book: Book; filters: { dim: string; values: string[] }[]; period: string; scope_label: string; title: string; kpis: string[];
  tiles: TileSpec[]; compare: { label: string; filters: unknown[] } | null; custom_metrics: { key: string; label: string }[];
}
export interface LensDetail extends Card { spec: Spec; head: number; latest: number; versions: Version[]; thread_id: string; can_edit: boolean }
export interface Metric { key: string; label: string; unit: Unit; kind: string; books: Book[]; source: string; description: string; group: string }
export interface Meta {
  book: Book; metrics: Metric[]; dimensions: { key: string; label: string }[]; distributions: { key: string; label: string; unit: Unit }[];
  periods: string[]; as_of: string; values: Record<string, string[]>; examples: string[];
  assistant: { model_available: boolean; model: string | null; planner: string };
}
export interface EditResult { lens_id: string; version: number; latest: number; change: string; versions: Version[] }
export interface PlaybookReport { id: string; title: string; status: string }

export const CHART_CHOICES: Record<string, string[]> = {
  trend: ["line", "bar", "area"], breakdown: ["hbar", "bar", "donut", "treemap"], mix_trend: ["stacked", "stacked100"],
  distribution: ["bar", "hbar"], compare: ["line", "bar"], concentration: ["hbar", "bar"], reasons: ["hbar", "bar"],
  regulatory: ["hbar", "bar"],
};
export const CHART_WORD: Record<string, string> = {
  line: "Line", bar: "Columns", area: "Area", hbar: "Bars", donut: "Donut", treemap: "Treemap", stacked: "Stacked", stacked100: "Stacked (100%)",
};

export const lenses = {
  meta: (book: Book) => request<Meta>(`/meta?book=${book}`),
  list: (book?: Book) => request<{ featured?: Card[]; mine: Card[]; shared: Card[]; templates: Card[] }>(`/lenses${book ? `?book=${book}` : ""}`),
  create: (body: { request?: string; book?: Book; template?: string; plan?: { persona: string; include: string[] } }) =>
    post<{ lens: Card; thread_id: string; run: { run_id: string } | null }>("/lenses", body),
  /** R16 M5: the metric plan for a request that names a persona ({persona: null} when none); with lens_id, that lens's scope. */
  plan: (body: { request: string; book?: Book; persona?: string; lens_id?: string }) => post<PlanReply>("/plan", body),
  lens: (id: string) => request<LensDetail>(`/lenses/${encodeURIComponent(id)}`),
  render: (id: string, period = "", version = 0) =>
    request<Rendered>(`/lenses/${encodeURIComponent(id)}/render?period=${encodeURIComponent(period)}${version ? `&version=${version}` : ""}`),
  edit: (id: string, op: Record<string, unknown>) => post<EditResult>(`/lenses/${encodeURIComponent(id)}/edit`, op),
  command: (id: string, text: string) => post<EditResult>(`/lenses/${encodeURIComponent(id)}/command`, { text }),
  undo: (id: string) => post<EditResult>(`/lenses/${encodeURIComponent(id)}/undo`),
  redo: (id: string) => post<EditResult>(`/lenses/${encodeURIComponent(id)}/redo`),
  restore: (id: string, version: number) => post<EditResult>(`/lenses/${encodeURIComponent(id)}/restore`, { version }),
  save: (id: string, body: { name: string; description: string; tags: string[] }) =>
    post<{ lens_id: string; saved: boolean; copied: boolean }>(`/lenses/${encodeURIComponent(id)}/save`, body),
  duplicate: (id: string) => post<{ lens_id: string }>(`/lenses/${encodeURIComponent(id)}/duplicate`),
  remove: (id: string) => request<{ deleted: string }>(`/lenses/${encodeURIComponent(id)}`, { method: "DELETE" }),
  share: (id: string, body: { users: string[]; teams: string[]; note: string }) =>
    post<{ shared_with: string[] }>(`/lenses/${encodeURIComponent(id)}/share`, body),
  playbookReports: () => request<{ reports: PlaybookReport[] }>("/playbook/reports"),
  toPlaybook: (id: string, body: { report_id?: string; new_report?: { title: string; book: Book } }) =>
    post<{ report_title: string; href: string; report_id: string }>(`/lenses/${encodeURIComponent(id)}/playbook`, body),
  schedule: (id: string, body: { cadence: string; recipients?: string[]; teams?: string[] }) =>
    post<{ schedule: Schedule | null }>(`/lenses/${encodeURIComponent(id)}/schedule`, body),
  handoff: (id: string, tile: string, target: "cockpit" | "whatif") =>
    post<{ href: string; label: string; summary: string }>(`/lenses/${encodeURIComponent(id)}/tiles/${encodeURIComponent(tile)}/handoff`, { target }),
  validateRatio: (body: { book: Book; num: string; den: string; filters: { dim: string; values: string[] }[]; label: string; scale?: number }) =>
    post<{ valid: boolean; value: number; display: string; period: string }>("/custom/validate", body),
  exportUrl: (id: string, kind: "xlsx" | "pdf", period = "") => lensesUrl(`/lenses/${encodeURIComponent(id)}/export.${kind}${period ? `?period=${period}` : ""}`),
};

/** One cell of a lens table through the G5 formatter, by the column's unit. */
export function cell(v: unknown, unit: Unit | string): string {
  if (v === null || v === undefined) return "–";
  if (typeof v !== "number") return String(v);
  switch (unit) {
    case "sar_mn": return fmt.sar(v);
    case "pct": return fmt.pct(v, { scale: "points" });
    case "ratio": return fmt.ratio(v);
    case "bps": return fmt.bps(v);
    case "count": case "days": return fmt.count(v);
    case "score": return fmt.num(v);
    default: return fmt.num(v);
  }
}

export function when(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export const BOOK_WORD: Record<Book, string> = { corporate: "Corporate", retail: "Retail" };

// ---------------------------------------------------------------- PLAN_R6 L4: rating order in assistant answers
/** True when the values (ignoring empties) are rating grades, so the axis or first column is a rating scale. */
export function isRatingScale(values: unknown[]): boolean {
  const xs = values.filter((v) => v !== null && v !== undefined && v !== "").map((v) => String(v));
  return xs.length > 1 && xs.filter((v) => ratingRank(v) < RATING_ORDER.length).length / xs.length >= 0.8;
}

/** An assistant chart or table with a rating axis (or a rating first column) in the global order AAA … D, never by value. */
export function ratingOrdered<B extends { type: string; [k: string]: unknown }>(block: B): B {
  const rows = block.rows as Record<string, unknown>[] | undefined;
  if (!Array.isArray(rows) || rows.length < 2) return block;
  let key = "";
  if (block.type === "chart") key = String(block.x ?? "");
  else if (block.type === "table") key = String(((block.columns as { key: string }[] | undefined) ?? [])[0]?.key ?? "");
  if (!key || !isRatingScale(rows.map((r) => r[key]))) return block;
  return { ...block, rows: sortByRating(rows as Record<string, string>[], key) };
}

// ---------------------------------------------------------------- PLAN_R9 D: P1 CBUAE CRM Intelligence
export interface CrmFinding { text: string; article: string; figure: string; rule: string; confidence: string; href: string; pack: string }
export interface CrmMetric { id: string; group: string; name: string; definition: string; formula: string; fields: string; article: string;
  frequency: string; threshold: string; status: "available" | "partial" | "gap"; lens_metric: string; closes_with: string }
export interface CrmLibrary { pack: { id: string; name: string; version: string; href: string }; metrics: CrmMetric[]; groups: string[];
  counts: { available: number; partial: number; gap: number }; total: number }
export interface CrmArticle { article: string; number: number; title: string; clauses: number; obligations: number; coverage: string;
  metrics: { id: string; name: string; status: string; closes_with: string }[]; items: { clause: string; text: string; metrics: string[]; coverage: string }[] }
export interface CrmUpload { upload_id: string; file: string; recognised: boolean; method: string; document: string; articles: CrmArticle[];
  obligations: number; metrics: number; coverage: { available: number; partial: number; gap: number };
  steps: { label: string; detail: string; ms: number }[]; ms: number; powered_by: { confidence: string; rule: string } }

export const crm = {
  library: () => request<CrmLibrary>("/crm/library"),
  upload: async (file: File): Promise<CrmUpload> => {
    const form = new FormData();
    form.append("file", file);
    let response: Response;
    try {
      response = await fetch(lensesUrl("/crm/upload"), { method: "POST", body: form, credentials: "include", cache: "no-store" });
    } catch {
      throw new LensesError(0, "Lenses is temporarily unavailable. Please try again in a moment.");
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new LensesError(response.status, friendlyError("Lenses", response.status, body));
    return body as CrmUpload;
  },
  dashboard: (body: { book: Book; upload_id?: string }) =>
    post<{ lens_id: string; href: string; findings: CrmFinding[] }>("/crm/dashboard", body),
};
