"use client";

/**
 * One What-If conversation at its own URL (/what-if/thread/<id>), forked from
 * the Cockpit's thread view: the settled turns, the live turn with its staged
 * progress (the run's committed events over SSE), and the composer at the
 * bottom with the follow-up chips. A refresh resumes the running turn instead
 * of asking again; Back returns to the What-If home (or to Early Warning for a
 * cohort thread, through the browser's own history).
 */

import { useRouter } from "next/navigation";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { FileSpreadsheet, FileText, Play, Save, SlidersHorizontal } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type Answer, type RunEvent, type RunView, type ThreadView, asOfLabel, exportHref, forgetRun, rememberRun,
  reportHref, watch, whatif,
} from "@/lib/v5/whatif";

import { AssistantTurn, ProcessTrace, ThreadShell, UserTurn, MemoCards, ThreadActionsProvider, useThreadActions } from "@/components/v5/thread";
import { whatifSources } from "@/lib/v5/thread-actions";
import { traceFromEvents } from "@/lib/v5/thread";

import { AnswerView } from "./blocks";
import { goalOfTurn, isGoal } from "./agent-goal";
import { AgentLiveTurn, AgentOffer, AgentRunLink, type AgentRunView, RunAsAgentButton, startWhatIfAgent, WhatIfAgentDrawer } from "./agent-run";
import { CustomShocks } from "./custom-shocks";
import { ThreadHeader } from "./header";
import { AddToReport, ShareButton } from "./share";
import { WhatIfWorkspaceSave } from "./workspace-save";
import { friendlyMessage } from "@/lib/v5/errors";

interface Live { runId: string; question: string; events: RunEvent[]; settled: RunView | null; connection: string }

/** The live turn's process trace (G4): the Cockpit's step list with its running timer, from the run's events. */
function Progress({ live }: { live: Live }) {
  const tools = live.events.filter((e) => e.event_type === "tool.completed").map((e) => String(e.detail?.tool ?? ""));
  return (
    <div data-testid="whatif-progress" data-tools={tools.join(",")} data-connection={live.connection}>
      <ProcessTrace snapshot={traceFromEvents(live.events)} />
    </div>
  );
}

export function WhatIfThread({ threadId }: { threadId: string }) {
  const router = useRouter();
  const [thread, setThread] = React.useState<ThreadView | null>(null);
  const [error, setError] = React.useState("");
  const [live, setLive] = React.useState<Live | null>(null);
  const [draft, setDraft] = React.useState("");
  const [custom, setCustom] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const stopRef = React.useRef<(() => void) | null>(null);
  // R11 W3: the scenario agent on a goal (its run, and the run open in the drawer)
  const [agentRun, setAgentRun] = React.useState<{ runId: string; goal: string } | null>(null);
  const [drawer, setDrawer] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      const t = await whatif.thread(threadId);
      setThread(t);
      setError("");
      return t;
    } catch (e) {
      setError(friendlyMessage(e));
      return null;
    }
  }, [threadId]);

  const follow = React.useCallback((runId: string, question: string) => {
    stopRef.current?.();
    rememberRun(threadId, runId);
    setLive({ runId, question, events: [], settled: null, connection: "open" });
    stopRef.current = watch(runId, {
      onEvent: (e) => setLive((l) => (l && l.runId === runId ? { ...l, events: [...l.events, e] } : l)),
      onSettled: () => {
        forgetRun(threadId);
        void load().then(() => setLive(null));
      },
      onConnection: (c) => setLive((l) => (l && l.runId === runId ? { ...l, connection: c } : l)),
    });
  }, [load, threadId]);

  React.useEffect(() => {
    let alive = true;
    void Promise.resolve().then(load).then((t) => {
      if (alive && t?.active_run) follow(t.active_run, "");
    });
    return () => { alive = false; stopRef.current?.(); };
  }, [load, follow]);

  const busy = Boolean(live) || Boolean(agentRun);
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo" writes the Word document.
  const ta = useThreadActions({ module: "whatif", threadId, title: thread?.title ?? "What-If thread", href: `/what-if/thread/${encodeURIComponent(threadId)}`, busy });
  const askRef = React.useRef<(q: string) => unknown>(() => undefined);
  const ask = React.useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    if (!q.startsWith("::") && ta.intercept(q, (x) => askRef.current(x))) { setDraft(""); return; }
    setDraft("");
    setNotice("");
    try {
      const run = await whatif.ask(threadId, q);
      follow(run.run_id, q.startsWith("::custom") ? "Custom shocks" : q === "::execute" ? "Execute scenario" : q);
    } catch (e) {
      setNotice(friendlyMessage(e));
    }
  }, [busy, follow, threadId, ta]);
  React.useEffect(() => { askRef.current = ask; }, [ask]);

  const runAgent = React.useCallback(async (goal: string) => {
    const g = goal.trim();
    if (!g || busy || !thread) return;
    setNotice("");
    try {
      const r = await startWhatIfAgent(g, { thread_id: thread.thread_id, domain: thread.domain, period: thread.period, cohort_id: thread.cohort_id || "" });
      setDraft((d) => (d.trim() === g ? "" : d));
      setAgentRun({ runId: r.run_id, goal: g });
    } catch (e) { setNotice(friendlyMessage(e)); }
  }, [busy, thread]);

  const onAgentSettled = React.useCallback((r: AgentRunView | null, err?: string) => {
    if (err) setNotice(err);
    else if (r && r.status !== "completed") setNotice(r.stopped || "The scenario agent stopped early; the drawer has what it found.");
    void load().then(() => setAgentRun(null));
  }, [load]);

  const save = async () => {
    if (!thread) return;
    const name = window.prompt("Name for the saved scenario", thread.title);
    if (name === null) return;
    try {
      const row = await whatif.save(threadId, name || thread.title);
      setNotice(`Saved to the scenario repository as “${row.name}”.`);
    } catch (e) { setNotice(friendlyMessage(e)); }
  };

  if (error) {
    return (
      <div className="space-y-3">
        <BackButton fallback={{ href: "/what-if", label: "What-If" }} testId="whatif-back" />
        <p className="text-sm text-negative" role="alert">{error}</p>
      </div>
    );
  }
  if (!thread) return <Skeleton className="h-64 w-full" />;
  const lab = thread.labels;
  const last: Answer | undefined = thread.turns[thread.turns.length - 1]?.answer;
  const chips = live ? [] : last?.suggestions ?? [];
  const hasScenario = thread.state.has_scenario;
  const agentTurns = new Set(thread.turns.map((t) => (t.answer as { agent_run?: { run_id: string } }).agent_run ? t.question.replace(/^Run as agent:\s*/i, "").trim() : "").filter(Boolean));
  const lastGoal = live || agentRun || !thread.turns.length ? "" : goalOfTurn(thread.turns[thread.turns.length - 1].question, agentTurns);
  const canExecute = Boolean(thread.state.pending) || hasScenario;
  // The header follows the thread's population: its cohort, or the scope of its current scenario's steps.
  const steps = (thread.state.scenario?.steps ?? []) as { scope?: unknown }[];
  const scopeKey = `${thread.cohort_id}|${thread.period}|${JSON.stringify(steps.map((x) => x.scope ?? null))}`;

  const header = (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <BackButton fallback={{ href: `/what-if?domain=${thread.domain}`, label: "What-If" }} testId="whatif-back" />
        {thread.cohort_id ? (
          <button type="button" onClick={() => router.push(`/early-warning?domain=${thread.domain}&period=${thread.period}`)} data-testid="whatif-back-ews"
                  className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] text-text-secondary hover:bg-surface-hover">
            Open in Early Warning</button>) : null}
        <div className="min-w-[min(100%,20rem)] flex-1">
          <h1 className="truncate text-[18px] font-semibold text-text-primary" data-testid="whatif-thread-title">{thread.title}</h1>
          <p className="text-[11px] text-text-muted" data-testid="whatif-thread-asof">{lab.book} · as of {asOfLabel(thread.period)}
            {thread.cohort_id ? (thread.cohort_id.startsWith("b360-cohort-") ? ` · Borrower 360 selection ${thread.cohort_id}` : ` · Early Warning cohort ${thread.cohort_id}`) : ""}{thread.state.method ? ` · ${thread.state.method === "xgboost" ? "XGBoost" : "Delta method"}` : ""}
            {thread.owner ? ` · owner ${thread.owner}` : ""}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" data-testid="whatif-actions">
          <button type="button" onClick={save} disabled={!hasScenario || busy} data-testid="whatif-save"
                  className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover disabled:opacity-40"><Save size={13} /> Save</button>
          <ShareButton kind="whatif-thread" id={thread.thread_id} label={thread.title} href={`/what-if/thread/${thread.thread_id}`}
                       summary={thread.state.steps.join("; ")} meta={{ book: thread.domain, period: thread.period, model: thread.state.method ?? "" }}
                       reportUrl={hasScenario ? reportHref(thread.thread_id) : undefined} disabled={busy} />
          <AddToReport threadId={thread.thread_id} disabled={!hasScenario || busy} onDone={setNotice} />
          <WhatIfWorkspaceSave thread={thread} busy={busy} />
          <a href={hasScenario ? reportHref(thread.thread_id) : undefined} aria-disabled={!hasScenario} data-testid="whatif-word"
             className={cn("inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover", !hasScenario && "pointer-events-none opacity-40")}>
            <FileText size={13} /> Word report</a>
          <a href={hasScenario ? exportHref(thread.thread_id) : undefined} aria-disabled={!hasScenario} data-testid="whatif-excel"
             className={cn("inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover", !hasScenario && "pointer-events-none opacity-40")}>
            <FileSpreadsheet size={13} /> Excel</a>
        </div>
      </div>
      {notice ? <p className="rounded-md border border-border bg-surface px-3 py-2 text-[12px]" data-testid="whatif-notice">{notice}</p> : null}

      <ThreadHeader threadId={thread.thread_id} scopeKey={scopeKey} />
    </>
  );

  return (
    <ThreadShell
      header={header}
      testId="whatif-thread-shell"
      scrollKey={`${thread.turns.length}|${live?.events.length ?? 0}`}
      composer={{
        value: draft, onChange: setDraft, onSubmit: (v) => void ask(v), busy, testId: "whatif",
        chips, onChip: (c) => void ask(c.send),
        placeholder: hasScenario ? "Ask about the result, or a change: “rerun with XGBoost”"
          : "Ask about the book, or try “reduce collateral by 20%”",
        leading: (
          <button type="button" onClick={() => setCustom((c) => !c)} title="Custom shocks: a structured editor" data-testid="whatif-custom-toggle"
                  className={cn("rounded-md border border-border p-2 text-text-secondary hover:bg-surface-hover", custom && "border-accent text-accent")}>
            <SlidersHorizontal size={16} /></button>),
        actions: (<>
          {isGoal(draft) ? <RunAsAgentButton onClick={() => void runAgent(draft)} disabled={busy} /> : null}
          <button type="button" disabled={busy || !canExecute} onClick={() => void ask("::execute")} data-testid="whatif-execute"
                  title={thread.state.pending ? "Run the proposed scenario" : hasScenario ? "Run the current scenario again" : "Describe a scenario first"}
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40">
            <Play size={14} /> Execute scenario</button></>),
      }}
    >
      <div data-testid="whatif-thread" data-thread={thread.thread_id} className="space-y-5">
        <ThreadActionsProvider value={ta}>
        {thread.turns.map((t, i) => (
          <div key={t.run_id} className="space-y-3" data-testid="whatif-turn">
            <UserTurn text={t.answer.question_display || t.question} />
            <AssistantTurn trace={t.answer.trace}
                           actions={{ index: i, question: t.answer.question_display || t.question, answerId: t.run_id, sources: whatifSources(t.answer) }}>
              <AnswerView answer={t.answer} onAsk={ask} threadId={thread.thread_id} busy={busy} turnIndex={i} />
              {(t.answer as { agent_run?: { run_id: string } }).agent_run ? (
                <AgentRunLink runId={(t.answer as unknown as { agent_run: { run_id: string } }).agent_run.run_id} onOpen={setDrawer} />) : null}
              {lastGoal && i === thread.turns.length - 1 ? <AgentOffer onRun={() => void runAgent(lastGoal)} busy={busy} /> : null}
            </AssistantTurn>
          </div>))}
        <MemoCards api={ta} />
        </ThreadActionsProvider>
        {live ? (
          <div className="space-y-3" data-testid="whatif-live-turn">
            {live.question ? <UserTurn text={live.question} /> : null}
            <Progress live={live} />
          </div>) : null}
        {agentRun ? (
          <div className="space-y-3" data-testid="whatif-agent-live-turn">
            <UserTurn text={`Run as agent: ${agentRun.goal}`} />
            <AgentLiveTurn runId={agentRun.runId} onSettled={onAgentSettled} onOpen={() => setDrawer(agentRun.runId)} />
          </div>) : null}
        {drawer ? <WhatIfAgentDrawer runId={drawer} onClose={() => setDrawer(null)} /> : null}
        {custom ? <CustomShocks domain={thread.domain} hasScenario={hasScenario} disabled={busy}
                                onSubmit={(body) => { setCustom(false); void ask(`::custom ${JSON.stringify(body)}`); }}
                                onClose={() => setCustom(false)} /> : null}
      </div>
    </ThreadShell>
  );
}
