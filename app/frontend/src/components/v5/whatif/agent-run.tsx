"use client";

/**
 * The What-If scenario agent in the thread (PLAN_R11_AGENTS W3), the smallest UI that exposes it:
 * - `RunAsAgentButton`: one click starts `whatif.scenarios` on a goal (the composer, or a goal turn);
 * - `AgentLiveTurn`: the running agent as the live turn, its plan ticking off step by step;
 * - `AgentRunLink`: on the agent's turn, opens the run in the shared agent drawer.
 * The results themselves land in the thread as the existing result cards (the agent posts them).
 * The agents service, its client and the drawer are Session G's (`lib/v5/agents.ts`, `core/agent-run.tsx`).
 */

import * as React from "react";
import { Bot, CheckCircle2, Circle, Loader2, MinusCircle, XCircle } from "lucide-react";

import { AgentRunDrawer } from "@/components/v5/core/agent-run";
import { type AgentRun, getRun, isFinished, startRun } from "@/lib/v5/agents";
import { cn } from "@/lib/utils";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

export const WHATIF_AGENT = "whatif.scenarios";

export type AgentRunView = AgentRun;

export interface AgentContext { thread_id: string; domain: string; period: string; cohort_id?: string }

export function startWhatIfAgent(goal: string, context: AgentContext): Promise<AgentRun> {
  return startRun(WHATIF_AGENT, goal, { ...context });
}


export function RunAsAgentButton({ onClick, disabled, testId = "whatif-run-as-agent", compact = false }:
  { onClick: () => void; disabled?: boolean; testId?: string; compact?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} data-testid={testId}
            title="Plan graded scenarios with their basis, test management actions, size an overlay and draft the ECL committee note"
            className={cn("inline-flex items-center gap-1 rounded-md border border-accent text-accent hover:bg-accent-muted disabled:opacity-40",
                          compact ? "px-2 py-1 text-[12px]" : "px-3 py-2 text-[13px] font-medium")}>
      <Bot size={compact ? 12 : 14} /> Run as agent</button>
  );
}

/** Under a goal the chat answered as a question: the one-click offer. */
export function AgentOffer({ onRun, busy }: { onRun: () => void; busy: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-accent/40 bg-accent-muted/30 px-3 py-2" data-testid="whatif-agent-offer">
      <p className="flex items-center gap-1 text-[12px] text-text-primary">A goal: run it as an agent
        <InfoPopover title="Scenario agent">This is a goal, not a single scenario: the scenario agent can run graded scenarios, management actions and an overlay for it.</InfoPopover></p>
      <span className="ml-auto"><RunAsAgentButton onClick={onRun} disabled={busy} compact testId="whatif-agent-offer-run" /></span>
    </div>
  );
}

function StepIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 size={13} className="text-positive" />;
  if (status === "running") return <Loader2 size={13} className="animate-spin text-accent" />;
  if (status === "failed") return <XCircle size={13} className="text-negative" />;
  if (status === "skipped") return <MinusCircle size={13} className="text-text-muted" />;
  return <Circle size={13} className="text-text-muted" />;
}

/** The running agent: its plan as numbered steps that tick off; calls `onSettled` when the run ends. */
export function AgentLiveTurn({ runId, onSettled, onOpen }: { runId: string; onSettled: (r: AgentRunView | null, error?: string) => void; onOpen: () => void }) {
  const [run, setRun] = React.useState<AgentRunView | null>(null);
  const settled = React.useRef(false);
  React.useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const r = await getRun(runId);
        if (!alive) return;
        setRun(r);
        if (isFinished(r.status)) {
          if (!settled.current) { settled.current = true; onSettled(r); }
          return;
        }
      } catch (e) {
        if (!alive) return;
        if (!settled.current) { settled.current = true; onSettled(null, e instanceof Error ? e.message : String(e)); }
        return;
      }
      timer = setTimeout(tick, 1000);
    };
    void tick();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [runId, onSettled]);
  const steps = run?.plan?.steps ?? [];
  const done = steps.filter((s) => s.status === "done" || s.status === "skipped" || s.status === "failed").length;
  return (
    <div className="space-y-2 rounded-md border border-border bg-surface px-3 py-2" data-testid="whatif-agent-live" data-run={runId}>
      <div className="flex items-center gap-2">
        <Loader2 size={13} className="animate-spin text-accent" />
        <p className="text-[12px] font-semibold text-text-primary">Scenario agent{steps.length ? ` · ${done} of ${steps.length} steps` : " · planning"}</p>
        <button type="button" onClick={onOpen} className="ml-auto text-[12px] text-accent hover:underline" data-testid="whatif-agent-live-open">Open the run</button>
      </div>
      {steps.length ? (
        <ol className="space-y-0.5">
          {steps.map((s) => (
            <li key={s.id} className="flex items-start gap-1.5 text-[12px]" data-testid="whatif-agent-step" data-status={s.status}>
              <span className="mt-0.5"><StepIcon status={s.status} /></span>
              <span className="w-7 shrink-0 text-text-muted">{s.id}</span>
              <span className={cn("min-w-0 break-words", s.status === "pending" ? "text-text-muted" : "text-text-primary")}>
                {s.summary || s.why}</span>
            </li>))}
        </ol>) : null}
    </div>
  );
}

/** On the agent's own turn: open the run (plan, findings, narrative, proposals) in the drawer. */
export function AgentRunLink({ runId, onOpen }: { runId: string; onOpen: (runId: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(runId)} data-testid="whatif-agent-open"
            className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline"><Bot size={12} /> Open the agent run</button>
  );
}

interface OverlayOut { overlay_low: number; overlay_high: number; overlay_point: number; segments: string[]; rule: string }

const sarM = (v: number) => `SAR ${v.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}m`;

/** The What-If part of the drawer: the overlay range and where the full results are. */
function WhatIfOutput({ run }: { run: AgentRun }) {
  const ov = run.output?.overlay as OverlayOut | null | undefined;
  const posted = (run.output?.thread as { posted?: boolean } | undefined)?.posted;
  return (
    <div className="space-y-1 px-4 py-2 text-[12px]" data-testid="whatif-agent-output">
      {ov ? (
        <p className="text-text-primary">Overlay range <span className="font-semibold tabular-nums">{sarM(ov.overlay_low)}</span> to{" "}
          <span className="font-semibold tabular-nums">{sarM(ov.overlay_high)}</span>{ov.segments?.length ? ` · ${ov.segments.join(", ")}` : ""}</p>) : null}
      <p className="text-text-muted">{posted ? "The scenario and action results and the ECL committee note are in the thread."
        : "The ECL committee note is in the run's output."}</p>
    </div>
  );
}

/** The shared agent drawer (Session G) with the What-If output. */
export function WhatIfAgentDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  return <AgentRunDrawer runId={runId} onClose={onClose} renderOutput={(run) => <WhatIfOutput run={run} />} />;
}
