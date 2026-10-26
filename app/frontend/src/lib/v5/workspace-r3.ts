/**
 * S3-2 Workspace client (PLAN_R3, Anne's definitions): analyses saved and refreshed, investigations imported and
 * continued, projects with access rules, documents and threads. Contract: docs/v5/WORKSPACE_API.md.
 *
 * Talks to the Core service (`NEXT_PUBLIC_WORKSPACE_API`, port 8505) with the session cookie, like lib/v5/workspace.
 * Amounts arrive in SAR million.
 */
import { friendlyError } from "./errors.ts";
import { WsError, wsOrigin, type Person, type Unit, type WsLink } from "@/lib/v5/workspace";

async function call<T>(path: string, init?: { method?: string; body?: unknown; form?: FormData; traceId?: string }): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${wsOrigin()}/api/v1/workspace${path}`, {
      method: init?.method ?? (init?.body !== undefined || init?.form ? "POST" : "GET"),
      cache: "no-store",
      credentials: "include",
      headers: { ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}), ...(init?.traceId ? { "X-Trace-Id": init.traceId } : {}) },
      body: init?.form ?? (init?.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new WsError(0, `Workspace is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new WsError(response.status, friendlyError("Workspace", response.status, body));
  }
  return body as T;
}

// ---------------------------------------------------------------- types

export interface Fig { key: string; label: string; value: number; unit: Unit }
export interface Col { key: string; label: string; unit: Unit | "num" }
export interface ResultTable { columns: Col[]; rows: Record<string, string | number | null>[]; key: string | null; totals?: Record<string, string | number> | null; title?: string }
export interface ChartSpec { kind: string; x: string; y: string; title: string }
export interface Result {
  engine: string; book?: string; period: string; figures: Fig[]; table: ResultTable | null; chart: ChartSpec | null; source: string;
}
export interface SavedAnswer extends Partial<Result> {
  narrative?: string; tables?: ResultTable[]; baseline?: Result | null; recompute_note?: string;
  /** R10 Q2: the answer to the question, key figure in **bold**. */
  headline?: string; steps?: string[];
}
export interface Analysis2 {
  id: string; title: string; description: string; period: string | null; source: string; owner: Person | null;
  project_id: string | null; investigation_id: string | null; created_at: string; question: string; origin: string;
  book: string | null; origin_link: Partial<WsLink> & { type?: string }; refreshable: boolean; refresh_count: number;
  links: WsLink[]; notes: string; answer: SavedAnswer; spec: Record<string, unknown> | null;
  refreshes: { period: string; at: string; by: string }[];
  /** R10 Q2: title is the question; `label` is the short name it was saved under; `headline` the answer line. */
  label?: string; headline?: string; method?: string;
}
export interface Periods { refreshable: boolean; periods: string[]; latest: string | null; saved_period: string | null; reason: string; datasets: { id: string; label: string }[] }
export interface Cell { before: number | null; after: number | null; change: number | null; change_pct: number | null }
export interface Comparison {
  before_period: string; after_period: string; columns: Col[];
  figures: (Cell & { key: string; label: string; unit: Unit })[];
  rows: { key: string; cells: Record<string, Cell> }[];
}
export interface Refresh { analysis_id: string; before: Result; after: Result; comparison: Comparison }

export type Artifact =
  | { kind: "table"; title: string; columns: Col[]; rows: Record<string, string | number | null>[]; totals?: Record<string, string | number> | null; source?: string; period?: string }
  | { kind: "figures"; title: string; figures: Fig[]; period?: string }
  | { kind: "chart"; title: string; points: { label: string; value: number }[]; unit: Unit }
  | { kind: "object"; type: string; id: string; label: string; href: string }
  | { kind: "text"; title: string; text: string };
export interface TurnIn { role: "user" | "assistant" | "note"; text: string; artifacts?: Artifact[]; at?: string }
export interface Turn extends TurnIn { at: string; author?: string | null; artifacts: Artifact[] }
export interface Source { type: string; id: string; label: string; href: string }
export interface ImportBody {
  source: Source; title: string; turns: TurnIn[]; notes?: string[]; summary?: string; continue_href?: string; period?: string;
}

export interface ProjectFile { id: string; name: string; kind: string; size: number; words: number; uploaded_by: Person | null; created_at: string; excerpt: string }
export interface ThreadRow { id: string; title: string; owner: Person | null; created_at: string; updated_at: string; messages: number }
export interface Citation { kind: "data" | "document" | "instructions"; label: string; href?: string; doc_id?: string }
export interface Message {
  id: number; role: "user" | "assistant"; author: Person | null; text: string; created_at: string;
  refused?: boolean; outside?: string[]; domains_used?: string[]; citations?: Citation[]; figures?: Fig[];
  table?: ResultTable | null; tables?: ResultTable[]; stages?: string[]; source?: string;
  trace?: import("./thread").TraceSnapshot;
}
export interface ProjectThread {
  id: string; project_id: string; title: string; owner: Person | null; created_at: string; updated_at: string; messages: Message[];
  project: { id: string; name: string; domains: string[]; instructions: string; files: { id: string; name: string }[] };
}
export interface CockpitContext { available: boolean; domain: "corporate" | "retail" | null; ui_filters: Record<string, unknown>; reason: string }

export const DOMAIN_LABEL: Record<string, string> = {
  corporate: "Cockpit corporate book", retail: "Cockpit retail book", ews: "Early Warning", whatif: "What-If",
  bureau: "Bureau", open_banking: "Open Banking", scorecard: "Scorecard",
};
export const DOMAINS = Object.keys(DOMAIN_LABEL);

// ---------------------------------------------------------------- calls

export const ws3 = {
  analysis: (id: string) => call<Analysis2>(`/analyses/${encodeURIComponent(id)}`),
  createAnalysis: (body: {
    title?: string; question: string; origin: "cockpit" | "whatif"; book?: string | null; period?: string | null;
    answer?: Record<string, unknown>; whatif?: { scenario: Record<string, unknown>; method: string };
    origin_link?: Partial<Source>; notes?: string;
  }) => call<Analysis2>("/analyses", { body }),
  periods: (id: string) => call<Periods>(`/analyses/${encodeURIComponent(id)}/periods`),
  refresh: (id: string, period: string | null) => call<Refresh>(`/analyses/${encodeURIComponent(id)}/refresh`, { body: { period } }),
  analysisSection: (id: string) => call<{ source: Source; section: { title: string; blocks: unknown[] } }>(`/analyses/${encodeURIComponent(id)}/playbook-section`),
  investigationSection: (id: string) => call<{ source: Source; section: { title: string; blocks: unknown[] } }>(`/investigations/${encodeURIComponent(id)}/playbook-section`),
  importInvestigation: (body: ImportBody) => call<{ id: string; title: string }>("/investigations/import", { body }),
  addTurns: (id: string, turns: TurnIn[]) => call<unknown>(`/investigations/${encodeURIComponent(id)}/turns`, { body: { turns } }),
  settings: (id: string, body: { name?: string; description?: string; instructions?: string; domains?: string[]; members?: string[] }) =>
    call<unknown>(`/projects/${encodeURIComponent(id)}/settings`, { body }),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<ProjectFile>(`/projects/${encodeURIComponent(id)}/documents`, { form });
  },
  document: (id: string, docId: string) => call<ProjectFile & { text: string }>(`/projects/${encodeURIComponent(id)}/documents/${encodeURIComponent(docId)}`),
  documentHref: (id: string, docId: string) => `${wsOrigin()}/api/v1/workspace/projects/${encodeURIComponent(id)}/documents/${encodeURIComponent(docId)}/file`,
  newThread: (id: string, body: { title?: string; question?: string }) => call<ProjectThread>(`/projects/${encodeURIComponent(id)}/threads`, { body }),
  thread: (id: string, threadId: string) => call<ProjectThread>(`/projects/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}`),
  send: (id: string, threadId: string, text: string, traceId?: string) =>
    call<ProjectThread>(`/projects/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}/messages`, { body: { text }, traceId }),
  /** Where the live process trace of a project turn is polled (docs/v5/THREAD_API.md 2.2). */
  traceBase: () => `${wsOrigin()}/api/v1/workspace`,
  cockpitContext: (id: string) => call<CockpitContext>(`/projects/${encodeURIComponent(id)}/cockpit-context`),
};

/** A change, signed, in the unit of the figure. */
export function signedValue(v: number | null | undefined, unit: Unit | "num"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (unit === "sar_mn") return `${sign}SAR ${a.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`;
  if (unit === "pct") return `${sign}${a.toFixed(2)}pp`;
  if (unit === "int") return `${sign}${Math.round(a).toLocaleString("en-US")}`;
  return `${sign}${a.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}
