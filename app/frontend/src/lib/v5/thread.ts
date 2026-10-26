/**
 * The shared thread's process trace (PLAN_R5 G4, docs/v5/THREAD_API.md).
 *
 * Every answer shows the Cockpit's process trace with its running timer:
 * Understand -> Plan -> Query -> Answer -> Validate -> Publish. A trace arrives
 * three ways and is normalised here into one `TraceSnapshot`:
 *   - the SSE events of a convo-store run (CONVO_API section 5)       -> traceFromEvents
 *   - a poll of `GET <base>/trace/{id}` during a one-request turn        -> pollTrace
 *   - the settled `answer.trace` stored with every turn                  -> as is
 * and `toRunView` hands it to the frozen Cockpit `ProcessPanel` (imported, never copied).
 */

import type { RunView, Step } from "../../components/cockpit-v4/reducer.ts";

export type StepKey = "understand" | "plan" | "query" | "answer" | "validate" | "publish";
export type StepState = "running" | "done" | "failed";

export interface TraceStep {
  key: StepKey; label: string; state: StepState; started_ms: number; ended_ms: number | null; detail: string; failures?: number;
}
export interface TraceSnapshot { trace_id: string; state: StepState; elapsed_ms: number; steps: TraceStep[] }

export const STEP_LABELS: Record<StepKey, string> = {
  understand: "Understand", plan: "Plan", query: "Query", answer: "Answer", validate: "Validate", publish: "Publish",
};
export const STEP_ORDER: StepKey[] = ["understand", "plan", "query", "answer", "validate", "publish"];

const STAGE_TO_STEP: Record<string, StepKey> = {
  understanding: "understand", planning: "plan", querying: "query", answering: "answer", validating: "validate",
  publishing: "publish",
  // What-If's engine stages
  computing: "query", attributing: "answer", assessing: "validate",
};

/** The G4 step of a convo stage ("" for `accepted` and unknown stages). */
export function stepOf(stage: string): StepKey | "" {
  if ((STEP_ORDER as string[]).includes(stage)) return stage as StepKey;
  return STAGE_TO_STEP[stage] ?? "";
}

export function newTraceId(): string {
  const rnd = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
    : Math.random().toString(16).slice(2, 18).padEnd(16, "0");
  return `tr-${rnd}`;
}

export function traceHeaders(id: string): Record<string, string> {
  return { "X-Trace-Id": id };
}

export function emptyTrace(id = ""): TraceSnapshot {
  return { trace_id: id, state: "running", elapsed_ms: 0, steps: [] };
}

/** The minimal event shape both convo and What-If SSE frames carry. */
export interface TraceEvent { seq?: number; event_type: string; stage: string; public_message?: string; elapsed_ms: number }

/** Rebuild the trace from a run's committed events (live: `settled` false keeps the open step running). */
export function traceFromEvents(events: TraceEvent[], settled = false): TraceSnapshot {
  const steps: TraceStep[] = [];
  let elapsed = 0;
  let failed = false;
  for (const e of events) {
    elapsed = Math.max(elapsed, e.elapsed_ms || 0);
    if (e.event_type === "run.failed") failed = true;
    const key = stepOf(e.stage || "");
    if (!key) continue;
    if (e.event_type === "stage.started") {
      const open = steps[steps.length - 1];
      if (open && open.key === key && open.state === "running") { if (e.public_message) open.detail = e.public_message; continue; }
      for (const s of steps) if (s.state === "running") { s.state = "done"; s.ended_ms = e.elapsed_ms; }
      steps.push({ key, label: STEP_LABELS[key], state: "running", started_ms: e.elapsed_ms, ended_ms: null,
                   detail: e.public_message ?? "" });
    } else if (e.event_type === "stage.completed") {
      for (let i = steps.length - 1; i >= 0; i -= 1) {
        if (steps[i].key === key && steps[i].state === "running") { steps[i].state = "done"; steps[i].ended_ms = e.elapsed_ms; break; }
      }
    } else {
      const open = steps[steps.length - 1];
      if (open && open.key === key && e.public_message) open.detail = e.public_message;
    }
  }
  const terminal = settled || failed || events.some((e) => e.event_type === "answer.ready");
  if (terminal) {
    for (const s of steps) if (s.state === "running") { s.state = failed ? "failed" : "done"; s.ended_ms = elapsed; }
  }
  return { trace_id: "", state: terminal ? (failed ? "failed" : "done") : "running", elapsed_ms: elapsed, steps };
}

/**
 * The frozen Cockpit's RunView for a snapshot, so `ProcessPanel` renders it as it renders a Cockpit run.
 * `anchorLocalMs` is the local clock reading when the snapshot was taken (live runs count forward from it).
 */
export function toRunView(snap: TraceSnapshot, anchorLocalMs = 0): RunView {
  const steps: Step[] = snap.steps.map((s, i) => ({
    stage: s.key, instanceId: `${s.key}#${i}`, openedAtSeq: i + 1, label: s.label || STEP_LABELS[s.key],
    state: s.state, detail: s.detail || "", startedAtMs: s.started_ms,
    elapsedMs: Math.max(0, (s.ended_ms ?? snap.elapsed_ms) - s.started_ms),
    errorId: "", failures: s.failures ?? 0, attempts: 1, substeps: [],
  }));
  const terminal = snap.state !== "running";
  return {
    runId: snap.trace_id || "trace", lastSeq: steps.length, connection: "open", steps,
    currentStage: steps[steps.length - 1]?.stage ?? "", elapsedMs: snap.elapsed_ms, elapsedIsAuthoritative: terminal,
    anchorLocalMs, terminal, state: snap.state === "done" ? "COMPLETED" : snap.state === "failed" ? "FAILED" : "RUNNING",
    errorCode: snap.state === "failed" ? "FAILED" : "", errorId: "", response: null,
  };
}

/** Live elapsed of a step: server time carried forward by the local clock while it runs (the Cockpit's clock rule). */
export function liveStepMs(step: TraceStep, snap: TraceSnapshot, anchorLocalMs: number, now: number): number {
  const base = (step.ended_ms ?? snap.elapsed_ms) - step.started_ms;
  if (step.state !== "running" || snap.state !== "running" || anchorLocalMs <= 0) return Math.max(0, base);
  return Math.max(0, base + Math.max(0, now - anchorLocalMs));
}

/** Poll a one-request turn's trace until it settles or `stop()` is called. 404s before registration are retried. */
export function pollTrace(base: string, id: string, onSnap: (s: TraceSnapshot) => void, everyMs = 700): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const root = base.replace(/\/$/, "");
  const tick = async () => {
    if (stopped) return;
    try {
      const res = await fetch(`${root}/trace/${encodeURIComponent(id)}`, { credentials: "include", cache: "no-store" });
      if (res.ok) {
        const snap = (await res.json()) as TraceSnapshot;
        if (!stopped) onSnap(snap);
        if (snap.state !== "running") return;
      }
    } catch { /* the request may still be on its way; keep polling */ }
    if (!stopped) timer = setTimeout(() => void tick(), everyMs);
  };
  timer = setTimeout(() => void tick(), 150);
  return () => { stopped = true; if (timer) clearTimeout(timer); };
}
