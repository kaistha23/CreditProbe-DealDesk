"use client";

/**
 * A conversation thread on the shared layer (docs/v5/CONVO_API.md): the settled
 * turns, the live turn with its stages (committed events over SSE), the
 * follow-up chips and the composer. A module passes its service base
 * (`<origin>/api/v1/<module>/convo`), optionally an action button beside the
 * composer (sent as an `execute` turn) and a renderer for its own block types.
 */

import * as React from "react";
import { Play, Send } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type ConvoBlock, type ConvoEvent, type ConvoThreadView, CONVO_STAGES, convoClient } from "@/lib/v5/convo";

import { AnswerChips, AnswerFrame } from "@/components/answer";

import { ConvoBlockView, EvidenceInfo } from "./blocks";
import { friendlyMessage } from "@/lib/v5/errors";

interface Props {
  base: string;
  threadId: string;
  placeholder?: string;
  /** An action beside the composer (for example "Execute scenario"); sends `text` with mode "execute". */
  action?: { label: string; text: string; enabled?: (view: ConvoThreadView) => boolean };
  renderBlock?: (block: ConvoBlock, index: number, ask: (text: string) => void) => React.ReactNode | null;
  header?: (view: ConvoThreadView) => React.ReactNode;
  testId?: string;
}

interface Live { runId: string; question: string; events: ConvoEvent[] }

function TurnBlock({ block, index, renderBlock, onAsk }: { block: ConvoBlock; index: number; onAsk: (text: string) => void;
  renderBlock?: Props["renderBlock"] }) {
  return <>{renderBlock?.(block, index, onAsk) ?? <ConvoBlockView block={block} index={index} />}</>;
}

export function ConvoThreadView({ base, threadId, placeholder, action, renderBlock, header, testId = "convo-thread" }: Props) {
  const client = React.useMemo(() => convoClient(base), [base]);
  const [view, setView] = React.useState<ConvoThreadView | null>(null);
  const [live, setLive] = React.useState<Live | null>(null);
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState("");
  const stop = React.useRef<(() => void) | null>(null);
  const bottom = React.useRef<HTMLDivElement | null>(null);

  const load = React.useCallback(async () => {
    try { const v = await client.thread(threadId); setView(v); setError(""); return v; }
    catch (e) { setError(friendlyMessage(e)); return null; }
  }, [client, threadId]);

  const follow = React.useCallback((runId: string, question: string) => {
    stop.current?.();
    setLive({ runId, question, events: [] });
    stop.current = client.watch(runId, {
      onEvent: (e) => setLive((l) => (l && l.runId === runId ? { ...l, events: [...l.events, e] } : l)),
      onSettled: () => { void load().then(() => setLive(null)); },
    });
  }, [client, load]);

  React.useEffect(() => {
    void Promise.resolve().then(load).then((v) => { if (v?.active_run) follow(v.active_run, ""); });
    return () => stop.current?.();
  }, [load, follow]);
  React.useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [view?.turns.length, live?.events.length]);

  const busy = Boolean(live);
  const ask = React.useCallback(async (text: string, mode: "ask" | "execute" = "ask") => {
    const q = text.trim();
    if (!q || busy) return;
    setDraft("");
    try { const run = await client.ask(threadId, q, mode); follow(run.run_id, q); }
    catch (e) { setError(friendlyMessage(e)); }
  }, [busy, client, follow, threadId]);

  const onAsk = React.useCallback((x: string) => { void ask(x); }, [ask]);

  if (!view) return error ? <p className="text-sm text-negative" role="alert">{error}</p> : <Skeleton className="h-48 w-full" />;
  const last = view.turns[view.turns.length - 1]?.answer;
  const chips = live ? [] : last?.suggestions ?? [];
  const started = new Set(live?.events.filter((e) => e.event_type === "stage.started").map((e) => e.stage));
  const done = new Set(live?.events.filter((e) => e.event_type === "stage.completed").map((e) => e.stage));
  const lastEvent = live?.events[live.events.length - 1];

  return (
    <div className="space-y-4" data-testid={testId} data-thread={view.thread.thread_id}>
      {header ? header(view) : null}
      <div className="space-y-5">
        {view.turns.map((t) => (
          <div key={t.run_id} className="space-y-3" data-testid="convo-turn">
            <div className="flex justify-end"><p className="max-w-3xl rounded-lg bg-accent px-3 py-2 text-[13px] text-accent-contrast">{t.answer.question_display || t.question}</p></div>
            <AnswerFrame>
              {t.answer.blocks.map((b, i) => <TurnBlock key={i} block={b} index={t.ordinal * 100 + i} renderBlock={renderBlock} onAsk={onAsk} />)}
              <EvidenceInfo answer={t.answer} />
            </AnswerFrame>
          </div>))}
        {live ? (
          <div className="space-y-3" data-testid="convo-live-turn">
            {live.question ? <div className="flex justify-end"><p className="max-w-3xl rounded-lg bg-accent px-3 py-2 text-[13px] text-accent-contrast">{live.question}</p></div> : null}
            <Card className="space-y-2 p-3" aria-live="polite">
              <ol className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
                {CONVO_STAGES.filter(([k]) => started.has(k)).map(([k, label]) => (
                  <li key={k} className={cn("flex items-center gap-1", done.has(k) ? "text-positive" : "font-semibold text-text-primary")}>
                    <span className={cn("inline-block h-1.5 w-1.5 rounded-full", done.has(k) ? "bg-positive" : "animate-pulse bg-accent")} />{label}</li>))}
              </ol>
              <p className="text-[11px] text-text-muted">{lastEvent?.public_message ?? "Starting"}{lastEvent ? ` · ${(lastEvent.elapsed_ms / 1000).toFixed(1)}s` : ""}</p>
            </Card>
          </div>) : null}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 z-20 -mx-1 space-y-2 border-t border-border bg-surface/95 px-1 py-3 backdrop-blur">
        <AnswerChips chips={chips} onAsk={(send) => void ask(send)} busy={busy} testId="convo-chips" />
        {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); void ask(draft); }}>
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} placeholder={placeholder ?? "Ask a question"} data-testid="convo-composer"
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(draft); } }}
                    className="min-h-[44px] flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text-primary focus:border-accent focus:outline-none" />
          <button type="submit" disabled={busy || !draft.trim()} data-testid="convo-send"
                  className={cn("inline-flex items-center gap-1 rounded-md px-3 py-2 text-[13px] font-medium disabled:opacity-40",
                                action ? "border border-border text-text-primary hover:bg-surface-hover" : "bg-accent text-accent-contrast")}>
            <Send size={14} /> Send</button>
          {action ? (
            <button type="button" disabled={busy || (action.enabled ? !action.enabled(view) : false)} onClick={() => void ask(action.text, "execute")}
                    data-testid="convo-action" className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40">
              <Play size={14} /> {action.label}</button>) : null}
        </form>
      </div>
    </div>
  );
}
