"use client";

/**
 * The Cockpit's process trace with its running timer, for every module (PLAN_R5 G4, docs/v5/THREAD_API.md 1.3).
 *
 * While the answer is being worked on, the steps are listed open (Understand -> Plan -> Query -> Answer -> Validate ->
 * Publish), each started step with its elapsed time; the running one counts up every second by the Cockpit's own
 * clock (`cockpit-v4/clock.ts`: the server's elapsed carried forward by the local clock). A step appears when it
 * starts, never before. Once the answer settles, the frozen Cockpit `ProcessPanel` itself takes over, collapsed:
 * "Answered in 4.2s · Show process".
 *
 * The frozen files are imported as they are, never copied or edited.
 */

import * as React from "react";

import { formatElapsed, liveStepElapsedMs, runHeadline, systemNow } from "@/components/cockpit-v4/clock";
import { ProcessPanel } from "@/components/cockpit-v4/process-panel";
import { formatSeconds } from "@/components/cockpit-v4/reducer";
import { cn } from "@/lib/utils";
import { type TraceSnapshot, emptyTrace, pollTrace, toRunView } from "@/lib/v5/thread";

function Marker({ state }: { state: string }) {
  const glyph = state === "failed" ? "✕" : state === "done" ? "✓" : "●";
  const tone = state === "failed" ? "text-negative" : state === "done" ? "text-positive" : "animate-pulse text-accent";
  return <span aria-hidden className={cn("w-4 shrink-0 text-center", tone)}>{glyph}</span>;
}

export function ProcessTrace({ snapshot, compact = false, testId = "process-trace" }: {
  snapshot: TraceSnapshot | null | undefined; compact?: boolean; testId?: string;
}) {
  const snap = snapshot ?? null;
  // The anchor: the local clock when this snapshot arrived. Live elapsed is the snapshot's own figure carried
  // forward from here, never a clock started independently on mount.
  const live = Boolean(snap) && snap?.state === "running";
  const stamp = snap ? `${snap.trace_id}|${snap.elapsed_ms}|${snap.steps.length}|${snap.state}` : "";
  // One tick source: `now` advances every second while live; the anchor is re-taken when a new snapshot arrives.
  const [clock, setClock] = React.useState(() => ({ stamp, anchor: systemNow(), now: systemNow() }));
  if (clock.stamp !== stamp) setClock({ stamp, anchor: clock.now, now: clock.now });
  React.useEffect(() => {
    if (!live) return undefined;
    const handle = setInterval(() => setClock((c) => ({ ...c, now: systemNow() })), 1000);
    return () => clearInterval(handle);
  }, [live]);
  const { anchor, now } = clock;

  if (!snap) return null;
  const view = toRunView(snap, anchor);
  if (!live) {
    if (!snap.steps.length) return null;
    return (
      <div data-testid={testId} data-state={snap.state} className={cn(compact && "text-[12px]")}>
        <ProcessPanel view={view} />
      </div>
    );
  }
  const headline = snap.steps.length ? runHeadline({ ...view, runId: view.runId || "trace" }, now)
    : `Working · ${formatElapsed(snap.elapsed_ms + Math.max(0, now - anchor))} elapsed`;
  return (
    <section data-testid={testId} data-state="running" aria-label="Process"
             className={cn("rounded-lg border border-border bg-surface-sunken/60 text-sm", compact && "text-[12px]")}>
      <p className="px-3 py-2 text-text-secondary" aria-live="polite" data-testid="process-elapsed">{headline}</p>
      {view.steps.length ? (
        <ol className="space-y-1 border-t border-border px-3 py-2" data-testid="process-steps">
          {view.steps.map((step) => (
            <li key={step.instanceId} className="flex items-start gap-2" data-testid={`process-step-${step.stage}`} data-state={step.state}>
              <Marker state={step.state} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3 text-text-primary">
                  <span className="truncate">{step.label}</span>
                  <span className="shrink-0 tabular-nums text-xs text-text-muted">
                    {step.state === "running" ? formatElapsed(liveStepElapsedMs(step, view, now)) : formatSeconds(step.elapsedMs)}
                  </span>
                </div>
                {step.detail ? <p className="truncate text-xs text-text-muted">{step.detail}</p> : null}
              </div>
            </li>))}
        </ol>) : null}
    </section>
  );
}

/**
 * The live trace of a ONE-REQUEST turn: polls `GET {base}/trace/{traceId}` while the request is in flight
 * (THREAD_API 2.2). Shows "Working · 3s elapsed" until the server registers the trace.
 */
export function LiveTrace({ base, traceId, compact = false }: { base: string; traceId: string; compact?: boolean }) {
  return <PolledTrace key={traceId} base={base} traceId={traceId} compact={compact} />;
}

function PolledTrace({ base, traceId, compact }: { base: string; traceId: string; compact: boolean }) {
  const [snap, setSnap] = React.useState<TraceSnapshot>(() => emptyTrace(traceId));
  React.useEffect(() => {
    return pollTrace(base, traceId, (s) => setSnap(s.state === "running" ? s : { ...s, state: "running" }));
  }, [base, traceId]);
  // A live trace stays "running" on screen until the request itself returns and the caller swaps in the answer.
  return <ProcessTrace snapshot={snap} compact={compact} />;
}
