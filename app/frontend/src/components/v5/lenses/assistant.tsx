"use client";

/**
 * The lens assistant (PLAN_R5 L1.4, G4): the lens's own thread on the shared convo layer, rendered with the shared
 * thread (ThreadShell, the Cockpit process trace with its running timer, AnswerBlocks). It answers questions about
 * the lens, explains any tile, suggests next tiles, edits the lens by conversation, and turns a tile into a Cockpit
 * thread or a What-If cohort. When a turn changes the lens, `onLensChanged` reloads the dashboard.
 */

import Link from "next/link";
import * as React from "react";
import { Check, ExternalLink, Plus, RefreshCw, Undo2 } from "lucide-react";

import { ConvoChart, ConvoTable } from "@/components/v5/convo/blocks";

import { AnswerBlocks, AssistantTurn, MemoCards, ProcessTrace, ThreadActionsProvider, ThreadShell, UserTurn, useThreadActions } from "@/components/v5/thread";
import { convoSources } from "@/lib/v5/thread-actions";
import { type ConvoBlock, type ConvoEvent, type ConvoThreadView, convoClient } from "@/lib/v5/convo";
import { convoBase, ratingOrdered } from "@/lib/v5/lenses";
import { type TraceSnapshot, traceFromEvents } from "@/lib/v5/thread";
import { friendlyMessage } from "@/lib/v5/errors";
import { stripRepeated } from "./assistant-model"; // R14 G
import { MetricPlanCard } from "./metric-plan"; // R16 M5
import { lenses } from "@/lib/v5/lenses";
import { type MetricPlan, isPlan, mentionsPersona } from "@/lib/v5/lenses-plan";

interface Live { runId: string; question: string; events: ConvoEvent[] }

/** Where a placed block goes and what was placed, for the lens view to commit (PLAN_R6 L2). */
export interface AddRequest { block: ConvoBlock; sql: string; question: string; after: string }
export interface AddTarget { tiles: { id: string; title: string }[]; onAdd: (req: AddRequest) => Promise<boolean>; onUndo: () => Promise<void> }

/** "Add to lens" under an answer's chart or table: choose the position (end, or after a tile), place it, undo it. */
export function AddToLens({ block, sql, question, target }: { block: ConvoBlock; sql: string; question: string; target: AddTarget }) {
  const [after, setAfter] = React.useState("end");
  const [state, setState] = React.useState<"" | "busy" | "added">("");
  const add = async () => {
    setState("busy");
    const ok = await target.onAdd({ block, sql, question, after });
    setState(ok ? "added" : "");
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]" data-testid="lens-add-block">
      {state === "added" ? (
        <>
          <span className="inline-flex items-center gap-1 text-positive" data-testid="lens-add-block-done"><Check size={12} /> Added to the lens</span>
          <button type="button" data-testid="lens-add-block-undo" onClick={() => void target.onUndo().then(() => setState(""))}
                  className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-text-secondary hover:bg-surface-hover"><Undo2 size={11} /> Undo</button>
        </>) : (
        <>
          <button type="button" disabled={state === "busy"} onClick={() => void add()} data-testid="lens-add-block-button"
                  className="inline-flex items-center gap-1 rounded-md border border-accent px-2 py-0.5 font-medium text-accent hover:bg-surface-hover disabled:opacity-50">
            <Plus size={11} /> Add to lens</button>
          <label className="inline-flex items-center gap-1 text-text-muted">
            <span>at</span>
            <select value={after} onChange={(e) => setAfter(e.target.value)} data-testid="lens-add-block-position"
                    className="max-w-[14rem] rounded border border-border bg-surface px-1 py-0.5 text-[11px] text-text-secondary">
              <option value="end">the end</option>
              <option value="start">the start</option>
              {target.tiles.map((t) => <option key={t.id} value={t.id}>after: {t.title}</option>)}
            </select>
          </label>
        </>)}
    </div>
  );
}

function placeable(block: ConvoBlock, sql: string, question: string, target: AddTarget | null): React.ReactNode | null {
  if (block.type !== "chart" && block.type !== "table") return null;
  const ordered = ratingOrdered(block as { type: string; [k: string]: unknown }) as ConvoBlock;
  return (
    <div className="space-y-1.5" data-testid="lens-answer-block">
      {block.type === "chart" ? <ConvoChart block={ordered as Extract<ConvoBlock, { type: "chart" }>} testId="answer-chart" />
        : <ConvoTable block={ordered as Extract<ConvoBlock, { type: "table" }>} testId="answer-table" />}
      {target ? <AddToLens block={ordered} sql={sql} question={question} target={target} /> : null}
    </div>);
}

function lensBlock(block: ConvoBlock): React.ReactNode | null {
  if (block.type === "lens_update") {
    const b = block as { version?: number; change?: string };
    return (
      <p className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[11px] text-text-secondary" data-testid="lens-updated">
        <RefreshCw size={11} /> Lens {b.change === "built" ? "built" : "updated"} · version {b.version}</p>);
  }
  if (block.type === "lens_link") {
    const b = block as { href?: string; label?: string; target?: string };
    return (
      <Link href={String(b.href ?? "/")} data-testid={`lens-handoff-${b.target}`}
            className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast">
        <ExternalLink size={12} /> {b.label}</Link>);
  }
  return null;
}

/** R14 G: drop the dashboard's interpretation lines from stored answers (threads written before R14 repeated them). */
function dedupe(blocks: ConvoBlock[], shown: string[]): ConvoBlock[] {
  if (!shown.length) return blocks;
  return blocks.map((b) => (b.type === "answer" && typeof (b as { markdown?: unknown }).markdown === "string"
    ? { ...b, markdown: stripRepeated((b as { markdown: string }).markdown, shown) } : b));
}

export function LensAssistant({ threadId, onLensChanged, canEdit, seed, addTarget, dashboard = [], lensId = "" }: { threadId: string; onLensChanged: () => void; canEdit: boolean;
  seed?: { text: string; nonce: number } | null; addTarget?: AddTarget | null;
  /** R16 M5: the lens this thread edits; a persona request ("make this a CRO dashboard") shows a metric plan first. */
  lensId?: string;
  /** R14 G: the interpretation lines the dashboard already shows; the assistant never repeats them. */
  dashboard?: string[] }) {
  const client = React.useMemo(() => convoClient(convoBase()), []);
  const [view, setView] = React.useState<ConvoThreadView | null>(null);
  const [live, setLive] = React.useState<Live | null>(null);
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState("");
  const stop = React.useRef<(() => void) | null>(null);
  const changed = React.useRef(onLensChanged);
  React.useEffect(() => { changed.current = onLensChanged; });

  const load = React.useCallback(async () => {
    try { const v = await client.thread(threadId); setView(v); setError(""); return v; }
    catch (e) { setError(friendlyMessage(e)); return null; }
  }, [client, threadId]);

  const follow = React.useCallback((runId: string, question: string) => {
    stop.current?.();
    setLive({ runId, question, events: [] });
    stop.current = client.watch(runId, {
      onEvent: (e) => setLive((l) => (l && l.runId === runId ? { ...l, events: [...l.events, e] } : l)),
      onSettled: () => {
        void load().then((v) => {
          setLive(null);
          const last = v?.turns[v.turns.length - 1];
          if (last?.answer.blocks.some((b) => b.type === "lens_update")) changed.current();
        });
      },
    });
  }, [client, load]);

  React.useEffect(() => {
    void Promise.resolve().then(load).then((v) => { if (v?.active_run) follow(v.active_run, v.turns.length ? "" : String(v.thread.title || "")); });
    return () => stop.current?.();
  }, [load, follow]);

  const [plan, setPlan] = React.useState<MetricPlan | null>(null);
  const [planBusy, setPlanBusy] = React.useState(false);
  const [planError, setPlanError] = React.useState("");
  const busy = Boolean(live);
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo" writes the Word document.
  const ta = useThreadActions({ module: "lenses", threadId, title: String(view?.thread.title || "Lens thread"), busy });
  const askRef = React.useRef<(q: string) => unknown>(() => undefined);
  const ask = React.useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    if (ta.intercept(q, (x) => askRef.current(x))) { setDraft(""); return; }
    setDraft("");
    if (lensId && canEdit && mentionsPersona(q)) {
      try { const r = await lenses.plan({ request: q, lens_id: lensId }); if (isPlan(r)) { setPlan(r); setPlanError(""); return; } }
      catch (e) { setError(friendlyMessage(e)); return; }
    }
    try { const run = await client.ask(threadId, q); follow(run.run_id, q); }
    catch (e) { setError(friendlyMessage(e)); }
  }, [busy, canEdit, client, follow, lensId, threadId, ta]);
  React.useEffect(() => { askRef.current = ask; }, [ask]);
  const buildPlan = async (p: MetricPlan, include: string[]) => {
    setPlanBusy(true);
    try { await lenses.edit(lensId, { op: "persona_plan", persona: p.persona, include }); setPlan(null); setPlanError(""); changed.current(); }
    catch (e) { setPlanError(friendlyMessage(e)); }
    finally { setPlanBusy(false); }
  };

  React.useEffect(() => { if (seed?.text) void Promise.resolve().then(() => ask(seed.text)); }, [seed?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const last = view?.turns[view.turns.length - 1]?.answer;
  const chips = live ? [] : (last?.suggestions ?? []);
  const liveTrace: TraceSnapshot | null = live ? traceFromEvents(live.events) : null;

  return (
    <div data-testid="lens-assistant" data-thread={threadId} data-busy={busy ? "1" : "0"}>
      <ThreadShell compact scrollKey={`${view?.turns.length ?? 0}-${live?.events.length ?? 0}`} testId="lens-thread"
                   notice={error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
                   composer={{ value: draft, onChange: setDraft, onSubmit: (v) => void ask(v), busy, disabled: !canEdit && false, chips,
                               onChip: (c) => void ask(c.send), testId: "lens-assistant", primarySend: true, rows: 2,
                               placeholder: canEdit ? "Ask about this lens or change it: 'add DSCR distribution'" : "Ask about this lens" }}>
        <ThreadActionsProvider value={ta}>
        {(view?.turns ?? []).map((t, i) => (
          <div key={t.run_id} className="space-y-2">
            <UserTurn compact text={t.answer.question_display || t.question} />
            <AssistantTurn compact trace={(t.answer as { trace?: TraceSnapshot }).trace ?? null}
                           actions={{ index: i, question: t.answer.question_display || t.question, answerId: t.run_id, sources: convoSources(t.answer) }}>
              <AnswerBlocks blocks={dedupe(t.answer.blocks, dashboard)} evidence={t.answer.evidence}
                            renderBlock={(b) => lensBlock(b) ?? placeable(b, (t.answer.evidence ?? []).map((e) => e.sql).filter(Boolean).join(";\n"),
                                                                           t.answer.question_display || t.question, canEdit ? addTarget ?? null : null)} />
            </AssistantTurn>
          </div>))}
        <MemoCards api={ta} compact />
        </ThreadActionsProvider>
        {plan ? (
          <div className="rounded-md border border-border p-2.5" data-testid="lens-assistant-plan">
            <MetricPlanCard plan={plan} busy={planBusy} error={planError} onCancel={() => setPlan(null)} onBuild={(inc) => void buildPlan(plan, inc)} />
          </div>) : null}
        {live ? (
          <div className="space-y-2" data-testid="lens-live-turn">
            {live.question ? <UserTurn compact text={live.question} /> : null}
            {liveTrace ? <ProcessTrace snapshot={liveTrace} compact /> : null}
          </div>) : null}
      </ThreadShell>
    </div>
  );
}
