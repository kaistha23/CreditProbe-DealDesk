/**
 * v5 What-If client (conversational, PLAN_R2 item 6).
 *
 * Talks to the What-If service (port 8503, `NEXT_PUBLIC_WHATIF_API`) with the
 * session cookie (`credentials: "include"`), and follows a run's committed
 * events over SSE -- the same contract as the Cockpit's `watch()` (forked,
 * re-keyed): a cursor, no duplicate or invented events, a re-read of the run
 * on a gap, bounded reconnects. Amounts arrive in SAR million.
 */
import { friendlyError } from "./errors.ts";
import type { DomainId } from "@/lib/v5/ews";

export { count, pct, sar, signed, asOfLabel, useEws as useLoad } from "@/lib/v5/ews";
export type { DomainId };

export function whatifOrigin(): string {
  return (process.env.NEXT_PUBLIC_WHATIF_API ?? "http://127.0.0.1:8503").replace(/\/$/, "");
}
const PREFIX = "/api/v1/whatif";
export const apiUrl = (path: string) => `${whatifOrigin()}${PREFIX}${path}`;

export class WhatIfError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new WhatIfError(0, `What-If is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("What-If", response.status, body);
    throw new WhatIfError(response.status, message);
  }
  return body as T;
}

// ---------------------------------------------------------------- types

export interface Labels {
  book: string; segment: string; segments: string; subsegment: string; owner: string; owners: string;
  exposure: string; exposures: string; grade: string; grade_notch: string; period: string; frequency: string;
}
export interface Meta {
  domain: DomainId; as_of: string; periods: string[]; labels: Labels; segments: string[]; subsegments: string[];
  methods: { key: string; name: string }[]; scenario_weights: Record<string, number>;
  mev: MevSeries[]; assistant: { model_available: boolean; model: string | null; planner: string }; examples: string[];
}
export interface MevSeries {
  key: string; name: string; unit: string; shock_unit: string; direction: string; first_year: number | null;
  last_year: number | null; coverage: string; source: string; vintage: string; retrieved: string;
}
export interface LibraryRow {
  scenario_id: string; owner: string; team: string; name: string; description: string; domain: DomainId; period: string;
  method: string; ecl_before: number | null; ecl_after: number | null; change: number | null; change_pct: number | null;
  tags: string[]; created_at: number; standard: boolean; thread_id: string; cohort_id: string; steps: string[];
}
export interface Library { domain: DomainId; standard: LibraryRow[]; saved: LibraryRow[] }
export interface ThreadRow { thread_id: string; owner: string; domain: DomainId; period: string; cohort_id: string; title: string; origin: string; updated_at: number }

export interface Cards {
  reported_ecl: number; start_ecl: number; model_error: number; model_error_pct: number; scenario_ecl: number;
  change: number; change_pct: number; ead_before: number; ead_after: number; coverage_before: number; coverage_after: number;
  stage_before: Record<string, number>; stage_after: Record<string, number>;
  stage_ead_before: Record<string, number>; stage_ead_after: Record<string, number>;
  moves: Record<string, number>; rwa_before: number; rwa_after: number; capital_cet1_before_pct: number;
  capital_cet1_after_pct: number; capital_impact: number; exposures: number; owners: number;
}
export interface Bar { key: string; label: string; value: number; kind: "total" | "model" | "driver"; active?: boolean; total_after?: number }
export interface SegmentRow { segment: string; ead_before: number; ead_after: number; ecl_before: number; ecl_after: number; reported: number; change: number }
export interface RatingRow { grade: string; ead_before: number; ead_after: number; ecl_before: number; ecl_after: number; pd_masterscale_pct: number | null }
export interface Mover {
  exposure_id: string; owner_id: string; owner_name: string | null; segment: string; grade_before: string; grade_after: string;
  stage_before: number; stage_after: number; ead: number; ecl_before: number; ecl_after: number; change: number;
  drivers: Record<string, number>;
}
export interface Result {
  run_id: string; method: "delta" | "xgboost"; method_name: string; method_version: string; cards: Cards; waterfall: Bar[];
  reconciliation: { start_plus_drivers: number; scenario: number; difference: number; reconciles: boolean };
  by_scenario: Record<string, { before: number; after: number; weight: number }>;
  by_segment: SegmentRow[]; by_rating: RatingRow[]; rating_order: string[];
  migration: { counts: number[][]; ead: number[][]; stages: number[] }; top_movers: Mover[];
  attribution_by_segment: Record<string, number | string>[]; drivers: string[]; domain: DomainId; period: string;
  labels: Labels; steps: { instruction: string; restatement: string; shocks: string[]; scope: string }[];
  population: { kind: string; label: string }; scenario_weights: Record<string, number>; seconds: number;
}
export interface LikelihoodItem { shock: string; text: string; share: number; level: number }
export type Block =
  | { type: "text"; markdown: string }
  | { type: "understood"; kind: string; population: string; steps: { restatement: string }[]; assumptions: string[]; unread: string[]; method: string }
  | { type: "question"; key: string; text: string; options: { label: string; send: string; detail?: string }[] }
  | { type: "result"; result: Result }
  | { type: "commentary"; text: string; source: string; note?: string; model?: string }
  | { type: "likelihood"; label: string; level: number; items: LikelihoodItem[]; note: string; history?: string }
  | { type: "comparison"; rows: { label: string; delta: number; xgboost: number; kind: string }[];
      drivers: { driver: string; delta: number; xgboost: number }[]; segments: { segment: string; delta: number; xgboost: number }[];
      moves: Record<string, Record<string, number>>; results: Record<string, Result> }
  | { type: "cohort"; [k: string]: unknown }
  | { type: "context"; [k: string]: unknown }   // R16 m (M4): the subject's facts a thread opens with (whatif/context.ts)
  | { type: "ideas"; ideas: { label: string; send: string; why: string; family?: string; severity?: string; key?: string }[] }
  | import("./regime").RegimeBlock
  | { type: "saved"; scenario_id: string; name: string; text: string }
  | { type: "report"; text: string }
  | { type: "attribution"; waterfall: Bar[]; by_segment: Record<string, number | string>[]; drivers: string[]; labels: Labels;
      reconciliation: Result["reconciliation"] }
  | { type: "refusal"; text: string }
  | { type: "proposal"; kind: string; population: string; method: string; needs_method: boolean; assumptions: string[]; unread: string[];
      steps: { restatement: string; shocks: Record<string, unknown>; scope: Record<string, unknown>; levers: string[] }[] }
  | { type: "answer"; markdown: string; source?: string; model?: string }
  | { type: "table"; title: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[]; row_count?: number }
  | { type: "chart"; title: string; kind: string; x: string; y: string[]; y2?: string; labels: Record<string, string>; rows: Record<string, unknown>[] }
  | { type: "error"; text: string }
  | ScenarioSetBlock
  | { type: "scenario_memo"; href: string; label: string; engine_version: string; fingerprint: string };

/** PLAN_R13 §S: the scenario engine's answer (calibrated mild / moderate / severe on the corporate book). */
export interface ScenarioSetRow {
  severity: "mild" | "moderate" | "severe"; label: string; scenario: string; frequency: string;
  ecl_start: number; ecl_stressed: number; ecl_change: number; ecl_band: [number, number]; ecl_change_pct: number;
  stage2_start: number; stage2: number; pd_start: number; pd: number; capital: number; lgd_add_pp: number;
}
export interface ScenarioSetBlock {
  type: "scenario_set"; book: string; as_of: string; rows: ScenarioSetRow[];
  evidence: { key: string; label: string; text: string }[]; supports: string; cannot: string;
  top_sectors: { sector: string; ecl_change: number }[]; relations: string[]; engine_version: string; fingerprint: string;
  memo_href: string;
  /** R14 m (K12): in a high-oil regime, how the oil leg reads (a reversal from today's level). */
  regime_note?: string;
}
export interface Answer {
  blocks: Block[]; suggestions: { label: string; send: string }[]; question_display: string;
  state: { has_scenario?: boolean; method?: string | null; waiting?: boolean; steps?: string[]; pending?: boolean };
  planner?: { model_available: boolean; model: string | null; planner: string };
  evidence?: { artifact_id: string; kind: string; sql?: string | null; tool?: string | null; purpose: string; row_count: number }[];
  trace?: import("./thread").TraceSnapshot;
}
export interface Turn { ordinal: number; run_id: string; question: string; answer: Answer; created_at: number }
export interface RunView { run_id: string; thread_id: string; state: string; terminal: boolean; last_event_seq: number; answer: Answer | null; error_code: string | null }
export interface ThreadView {
  thread_id: string; title: string; domain: DomainId; period: string; cohort_id: string; origin: string; owner: string; team: string;
  labels: Labels; turns: Turn[]; active_run: string | null;
  state: { has_scenario: boolean; method: string | null; pending: boolean; steps: string[]; scenario: Record<string, unknown> | null };
}
export interface RunEvent {
  seq: number; event_type: string; stage: string; stage_label: string; status: string; public_message: string;
  elapsed_ms: number; detail: Record<string, unknown>;
}

/** The population summary at the head of every thread (GET /threads/{id}/summary, /cohort/{id}/summary). */
export interface SummaryCards {
  owners: number; exposures: number; ead: number; ecl: number; coverage_pct: number;
  stage2_ead_pct: number; stage3_ead_pct: number; stage2_n: number; stage3_n: number;
  ews_avg_score: number; ews_warned_owners: number; ews_warned_ead: number; ews_warned_pct: number;
}
export interface SummaryTopRow {
  rank: number; owner_id: string; owner_name: string | null; segment: string; grade: string; stage: number; exposures: number;
  ead: number; ecl: number; coverage_pct: number; ews_score: number; ews_band: string; ews_band_label: string; share_pct: number; href: string;
}
export interface PopulationSummary {
  kind: "book" | "scope" | "cohort"; domain: DomainId; period: string; labels: Labels; title: string; scope_label: string;
  cards: SummaryCards;
  stages: { stage: number; label: string; n: number; owners: number; ead: number; ecl: number; ead_pct: number }[];
  grades: { label: string; order: string[]; rows: { grade: string; n: number; owners: number; ead: number; ecl: number; ead_pct: number }[] };
  split: { label: string; plural: string; by: "segment" | "subsegment"; within: string; rows: { name: string; n: number; owners: number; ead: number; ecl: number; ead_pct: number; coverage_pct: number }[] };
  bands: { band: string; label: string; owners: number; exposures: number; ead: number; ecl: number }[];
  reasons: { reason: string; owners: number; exposures: number; ead: number }[];
  top: { n: number; rows: SummaryTopRow[] };
  thread_id?: string; cohort_id?: string; ruleset?: string; membership_hash?: string; membership_verified?: boolean;
  reconciliation?: { source: string; matches: boolean; checks: { label: string; ews: number | null; whatif: number; matches: boolean }[] };
}

// ---------------------------------------------------------------- calls

export const whatif = {
  meta: (domain: DomainId) => request<Meta>(`/meta?domain=${domain}`),
  library: (domain: DomainId) => request<Library>(`/library?domain=${domain}`),
  threads: (domain: DomainId) => request<{ threads: ThreadRow[] }>(`/threads?domain=${domain}`),
  thread: (id: string) => request<ThreadView>(`/threads/${encodeURIComponent(id)}`),
  threadSummary: (id: string) => request<PopulationSummary>(`/threads/${encodeURIComponent(id)}/summary`),
  cohortSummary: (id: string) => request<PopulationSummary>(`/cohort/${encodeURIComponent(id)}/summary`),
  createThread: (body: { domain?: DomainId; period?: string; question?: string; library_id?: string; cohort_id?: string }) =>
    request<{ thread_id: string; run: RunView | null }>(`/threads`, { method: "POST", body: JSON.stringify(body) }),
  ask: (threadId: string, question: string) =>
    request<RunView>(`/threads/${encodeURIComponent(threadId)}/runs`, { method: "POST", body: JSON.stringify({ question }) }),
  run: (runId: string) => request<RunView>(`/runs/${encodeURIComponent(runId)}`),
  rename: (threadId: string, title: string) =>
    request<{ title: string }>(`/threads/${encodeURIComponent(threadId)}/title`, { method: "POST", body: JSON.stringify({ title }) }),
  save: (threadId: string, name: string, tags: string[] = []) =>
    request<LibraryRow>(`/scenarios`, { method: "POST", body: JSON.stringify({ thread_id: threadId, name, tags }) }),
  removeScenario: (id: string) => request<{ deleted: string }>(`/scenarios/${encodeURIComponent(id)}`, { method: "DELETE" }),
  card: (book: DomainId, method: string) => request<Record<string, unknown>>(`/models/${book}/${method}`),
  reportPack: () => request<{ items: ReportItem[] }>(`/reports`),
  addToReport: (body: { thread_id?: string; scenario_id?: string }) =>
    request<{ items: ReportItem[]; added: ReportItem }>(`/reports/items`, { method: "POST", body: JSON.stringify(body) }),
  removeFromReport: (id: string) => request<{ items: ReportItem[] }>(`/reports/items/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
export interface ReportItem { item_id: string; kind: string; ref: string; name: string; domain: DomainId; method: string; added_at: number; change: number | null }

export const scenarioMemoHref = () => apiUrl("/scenario-engine/memo.docx");
export const reportHref = (threadId: string) => apiUrl(`/threads/${encodeURIComponent(threadId)}/report.docx`);
export const scenarioReportHref = (id: string) => apiUrl(`/scenarios/${encodeURIComponent(id)}/report.docx`);
export const exportHref = (threadId: string) => apiUrl(`/threads/${encodeURIComponent(threadId)}/export.xlsx`);
export const reportPackHref = () => apiUrl(`/reports/pack.docx`);

// ---------------------------------------------------------------- following a run (forked from the Cockpit's watch())

const EVENT_TYPES = ["run.accepted", "run.started", "stage.started", "stage.completed", "tool.started", "tool.completed",
  "tool.failed", "model.requested", "model.response_received", "answer.validated", "answer.ready", "run.failed"];
const RECONNECT_DELAYS_MS = [250, 500, 1000, 2000, 4000, 8000];

export interface WatchHandlers {
  onEvent: (e: RunEvent) => void;
  onSettled: (r: RunView) => void;
  onConnection?: (state: "open" | "retrying" | "lost") => void;
}

export function watch(runId: string, handlers: WatchHandlers, startCursor = 0): () => void {
  let cursor = startCursor;
  let attempt = 0;
  let stopped = false;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const settleFromStatus = () => {
    void whatif.run(runId).then((r) => { if (r.terminal && !stopped) { stopped = true; source?.close(); handlers.onSettled(r); } }).catch(() => {});
  };
  const open = () => {
    if (stopped) return;
    source = new EventSource(apiUrl(`/runs/${encodeURIComponent(runId)}/events?cursor=${cursor}`), { withCredentials: true });
    source.onopen = () => { attempt = 0; handlers.onConnection?.("open"); };
    source.addEventListener("run.settled", (raw) => {
      stopped = true;
      source?.close();
      try { handlers.onSettled(JSON.parse((raw as MessageEvent).data) as RunView); } catch { settleFromStatus(); }
    });
    const deliver = (raw: MessageEvent) => {
      let event: RunEvent;
      try { event = JSON.parse(raw.data) as RunEvent; } catch { return; }
      if (event.seq <= cursor) return;
      if (event.seq > cursor + 1 && cursor !== 0) settleFromStatus();
      cursor = Math.max(cursor, event.seq);
      handlers.onEvent(event);
    };
    for (const name of EVENT_TYPES) source.addEventListener(name, (raw) => deliver(raw as MessageEvent));
    source.onmessage = deliver;
    source.onerror = () => {
      source?.close();
      if (stopped) return;
      if (attempt >= RECONNECT_DELAYS_MS.length) { handlers.onConnection?.("lost"); settleFromStatus(); return; }
      handlers.onConnection?.("retrying");
      timer = setTimeout(open, RECONNECT_DELAYS_MS[attempt]);
      attempt += 1;
    };
  };
  open();
  return () => { stopped = true; if (timer) clearTimeout(timer); source?.close(); };
}

/** Remember the run a page started, so a refresh resumes it instead of asking again (Cockpit's rememberRun). */
export function rememberRun(threadId: string, runId: string) {
  try { sessionStorage.setItem(`cp.v5.whatif.run.${threadId}`, runId); } catch { /* private mode */ }
}
export function forgetRun(threadId: string) {
  try { sessionStorage.removeItem(`cp.v5.whatif.run.${threadId}`); } catch { /* private mode */ }
}

// ---------------------------------------------------------------- stages (mirror backend chat/events.py)

export const STAGES: [string, string][] = [
  ["accepted", "Question received"], ["understanding", "Reading the statement"], ["planning", "Planning the scenario"],
  ["querying", "Querying the What-If data"], ["answering", "Writing the answer"], ["computing", "Re-measuring ECL"], ["attributing", "Attributing the change"], ["assessing", "Checking history"],
  ["validating", "Validating the answer"], ["publishing", "Publishing"],
];

/** Legacy deep links (v5/next) to the standard library. */
export const LEGACY_SCENARIOS: Record<string, Record<string, string>> = {
  corporate: { rating: "downgrade-1", parameters: "parameters", stage: "migration", macro: "recession", sector: "construction", borrower: "construction" },
  retail: { rating: "score-band", parameters: "cards", stage: "score-band", macro: "recession", sector: "cards", borrower: "cards" },
};
