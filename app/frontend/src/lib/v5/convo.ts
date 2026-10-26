/**
 * Client for the shared conversational layer (backend/convo, docs/v5/CONVO_API.md).
 *
 * A module mounts the convo router under its own prefix (for example
 * `/api/v1/scorecard/convo` on the Scorecard service); `convoClient(base)` talks
 * to it with the session cookie and follows a run's committed events over SSE,
 * resuming from the last seq after a dropped connection (the Cockpit's client).
 */
import { friendlyError, unavailable } from "./errors.ts";

import { auto, kindOf, RAW_FLOAT } from "./format.ts";

export interface ConvoColumn { key: string; label: string }
export type ConvoBlock =
  | { type: "answer"; markdown: string; source?: string; model?: string }
  | { type: "table"; title: string; artifact_id?: string; columns: ConvoColumn[]; rows: Record<string, unknown>[]; row_count?: number }
  | { type: "chart"; title: string; kind: string; x: string; y: string[]; y2?: string; labels: Record<string, string>; rows: Record<string, unknown>[] }
  | { type: "error"; text: string }
  | { type: string; [k: string]: unknown };

export interface ConvoAnswer {
  blocks: ConvoBlock[]; suggestions: { label: string; send: string }[]; question_display: string;
  evidence?: { artifact_id: string; kind: string; sql?: string | null; tool?: string | null; purpose: string; row_count: number }[];
  source?: string;
  trace?: import("./thread").TraceSnapshot;
}
export interface ConvoTurn { ordinal: number; run_id: string; question: string; answer: ConvoAnswer; created_at: number }
export interface ConvoThread {
  thread_id: string; domain: string; scope: Record<string, unknown>; owner: string; team: string; title: string;
  state: Record<string, unknown>;
}
export interface ConvoThreadView { thread: ConvoThread; turns: ConvoTurn[]; active_run: string | null }
export interface ConvoRun { run_id: string; thread_id: string; state: string; terminal: boolean; answer: ConvoAnswer | null }
export interface ConvoEvent {
  seq: number; event_type: string; stage: string; stage_label: string; status: string; public_message: string;
  elapsed_ms: number; detail: Record<string, unknown>;
}

export const CONVO_STAGES: [string, string][] = [
  ["understanding", "Understanding"], ["planning", "Planning"], ["querying", "Querying"],
  ["answering", "Answering"], ["validating", "Checking figures"], ["publishing", "Publishing"],
];
const EVENT_TYPES = ["run.accepted", "run.started", "stage.started", "stage.completed", "tool.started", "tool.completed",
  "tool.failed", "model.requested", "model.response_received", "answer.validated", "answer.ready", "run.failed"];
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

export function convoClient(base: string, service = "The assistant") {
  const root = base.replace(/\/$/, "");
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetch(root + path, {
        ...init, credentials: "include", cache: "no-store",
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      });
    } catch {
      throw new Error(unavailable(service));
    }
    if (!res.ok) {
      const body: unknown = await res.json().catch(() => null);
      throw new Error(friendlyError(service, res.status, body));
    }
    return (await res.json()) as T;
  }
  const api = {
    create: (domain: string, scope: Record<string, unknown>, question = "", title = "", mode: "ask" | "execute" = "ask") =>
      request<{ thread: ConvoThread; run: ConvoRun | null }>("/threads", { method: "POST", body: JSON.stringify({ domain, scope, question, title, mode }) }),
    threads: (domain = "") => request<{ threads: ConvoThread[] }>(`/threads${domain ? `?domain=${encodeURIComponent(domain)}` : ""}`),
    thread: (id: string) => request<ConvoThreadView>(`/threads/${encodeURIComponent(id)}`),
    ask: (id: string, question: string, mode: "ask" | "execute" = "ask") =>
      request<ConvoRun>(`/threads/${encodeURIComponent(id)}/runs`, { method: "POST", body: JSON.stringify({ question, mode }) }),
    run: (id: string) => request<ConvoRun>(`/runs/${encodeURIComponent(id)}`),
    watch(runId: string, on: { onEvent: (e: ConvoEvent) => void; onSettled: () => void; onConnection?: (s: string) => void }): () => void {
      let cursor = 0;
      let attempt = 0;
      let stopped = false;
      let source: EventSource | null = null;
      let timer: ReturnType<typeof setTimeout> | null = null;
      const settle = () => { if (!stopped) { stopped = true; source?.close(); on.onSettled(); } };
      const fromStatus = () => { void api.run(runId).then((r) => { if (r.terminal) settle(); }).catch(() => {}); };
      const open = () => {
        if (stopped) return;
        source = new EventSource(`${root}/runs/${encodeURIComponent(runId)}/events?cursor=${cursor}`, { withCredentials: true });
        source.onopen = () => { attempt = 0; on.onConnection?.("open"); };
        source.addEventListener("run.settled", () => settle());
        const deliver = (raw: MessageEvent) => {
          let e: ConvoEvent;
          try { e = JSON.parse(raw.data) as ConvoEvent; } catch { return; }
          if (e.seq <= cursor) return;
          cursor = e.seq;
          on.onEvent(e);
        };
        for (const name of EVENT_TYPES) source.addEventListener(name, (raw) => deliver(raw as MessageEvent));
        source.onerror = () => {
          source?.close();
          if (stopped) return;
          if (attempt >= RECONNECT_DELAYS_MS.length) { on.onConnection?.("lost"); fromStatus(); return; }
          on.onConnection?.("retrying");
          timer = setTimeout(open, RECONNECT_DELAYS_MS[attempt]);
          attempt += 1;
        };
      };
      open();
      return () => { stopped = true; if (timer) clearTimeout(timer); source?.close(); };
    },
  };
  return api;
}

/** Format a table cell: numbers with thousands separators, ratios and percentages as they come. */
export function formatCell(v: unknown, key = ""): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  // E2 safety net: a raw float sent as text ("0.2810632681763545") is formatted as the number it is.
  if (typeof v === "string" && RAW_FLOAT.test(v.trim())) return formatCell(Number(v.trim()), key);
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "–";
    // G5: shares, percentages, bps and ratios through the one formatter (never 0.xx where % is meant).
    const kind = kindOf(key);
    if (kind === "pct_auto" || kind === "pct_points" || kind === "pp" || kind === "bps" || kind === "ratio" || kind === "sar_bn") return auto(v, key);
    const k = key.toLowerCase();
    const dp = /(_pct|_pp|share|coverage|rate)$/.test(k) || Math.abs(v) < 10 ? 2 : Math.abs(v) < 1000 ? 1 : 0;
    if (Number.isInteger(v) && !/(_pct|_pp|sar|ead|ecl)/.test(k)) return v.toLocaleString("en-US");
    return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  return String(v);
}
