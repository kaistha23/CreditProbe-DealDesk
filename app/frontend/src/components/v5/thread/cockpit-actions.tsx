"use client";

/**
 * R16 t (M7): the thread actions on the frozen Cockpit, from outside it.
 *
 *   <CockpitAnswerActions>  rendered by AnswerMailShare (non-frozen, already in every Cockpit answer's action row):
 *                           Trace, Word (this answer / the whole thread), Add to report, and Share where the row's own
 *                           "Share in Mail" is absent (past answers carry no thread id there).
 *   cockpitMemo(text, id)   the "write a memo" rule for the Cockpit's ask (FX-R16-T1, one line in thread-view.tsx):
 *                           handled -> the frozen ask stops (or asks the question part first); the memo is written here.
 *   <CockpitMemo threadId>  the memo cards under the conversation (FX-R16-T1).
 *
 * The thread document comes from the Cockpit's own transcript (readThread: narrative, published tables, numeric
 * claims); one answer's blocks are read from the screen (domBlocks) and its sources from the run trace (readTrace).
 */

import * as React from "react";

import { type FinalResponse, type ThreadTranscript, readThread, readTrace } from "@/components/cockpit-v4/client";
import {
  type ActionDoc, type ActionSource, type DomLike, cockpitBlocks, cockpitSources, composeDoc, domBlocks, planMemo,
} from "@/lib/v5/thread-actions";
import { threadActions } from "@/lib/v5/thread-actions-client";
import { takePendingMemo } from "@/lib/v5/thread-actions-pending";

import { MemoCard, type MemoCardState, ThreadActionBar } from "./action-bar";

const transcripts = new Map<string, Promise<ThreadTranscript | null>>();
const resolved = new Map<string, ThreadTranscript>();
function transcript(threadId: string, fresh = false): Promise<ThreadTranscript | null> {
  if (!threadId) return Promise.resolve(null);
  if (fresh || !transcripts.has(threadId)) {
    transcripts.set(threadId, readThread(threadId).then((t) => { resolved.set(threadId, t); return t; }).catch(() => null));
  }
  return transcripts.get(threadId)!;
}

export function threadIdFromPath(path?: string): string {
  const p = path ?? (typeof window !== "undefined" ? window.location.pathname : "");
  const m = /^\/cockpit\/thread\/([^/?#]+)/.exec(p);
  return m ? decodeURIComponent(m[1]) : "";
}

function claimsOf(a: FinalResponse | undefined) {
  return (a?.numeric_claims ?? []).map((c) => ({ evidence: (c as { evidence?: { artifact_id: string; row_key: string; column_id: string } | null }).evidence ?? null }));
}

export function cockpitThreadDoc(t: ThreadTranscript | null, threadId: string): ActionDoc {
  return composeDoc("cockpit", threadId, t?.title ?? "Cockpit thread", `/cockpit/thread/${encodeURIComponent(threadId)}`,
    (t?.turns ?? []).map((x) => ({
      question: x.question, answer_id: x.run_id,
      blocks: cockpitBlocks(x.answer as unknown as Parameters<typeof cockpitBlocks>[0]),
      sources: cockpitSources([], claimsOf(x.answer), (x.answer.tables ?? []).map((tb) => ({ title: tb.title, artifact_id: tb.artifact_id, row_count: tb.row_count }))),
    })).filter((x) => x.blocks.length));
}

/** The bar on one Cockpit answer (inside the frozen action row, via AnswerMailShare). */
export function CockpitAnswerActions({ question, threadId: given, runId, hasMailShare }: {
  question: string; threadId?: string; runId: string; hasMailShare: boolean;
}) {
  const anchor = React.useRef<HTMLSpanElement | null>(null);
  const threadId = given || threadIdFromPath();
  const [sources, setSources] = React.useState<ActionSource[]>([]);
  const [t, setT] = React.useState<ThreadTranscript | null>(null);
  React.useEffect(() => {
    let live = true;
    if (runId) void readTrace(runId).then((r) => { if (live) setSources((s) => [...cockpitSources(r.events as unknown as Parameters<typeof cockpitSources>[0]), ...s]); }).catch(() => undefined);
    void transcript(threadId).then((x) => {
      if (!live || !x) return;
      setT(x);
      const turn = x.turns.find((y) => y.run_id === runId);
      if (turn) setSources((s) => [...s, ...cockpitSources([], claimsOf(turn.answer), (turn.answer.tables ?? []).map((tb) => ({ title: tb.title, artifact_id: tb.artifact_id, row_count: tb.row_count })))]);
    });
    return () => { live = false; };
  }, [runId, threadId]);
  const getDoc = React.useCallback((): ActionDoc => {
    const el = anchor.current?.closest('[data-testid="v4-turn-assistant"]') ?? null;
    return composeDoc("cockpit", threadId, question, threadId ? `/cockpit/thread/${encodeURIComponent(threadId)}` : "/cockpit",
                      [{ question, answer_id: runId, blocks: domBlocks(el as unknown as DomLike | null), sources }]);
  }, [threadId, question, runId, sources]);
  const getThreadDoc = React.useCallback(() => cockpitThreadDoc(t, threadId), [t, threadId]);
  return (
    <span ref={anchor} className="contents">
      <ThreadActionBar module="cockpit" threadId={threadId} answerId={runId} getDoc={getDoc} getThreadDoc={t && t.turns.length > 1 ? getThreadDoc : undefined}
                       answers={() => t?.turns.length ?? 1} share={!hasMailShare} className="border-t-0 pt-0" testId="cockpit-thread-actions"
                       question={question} getEl={() => anchor.current?.closest('[data-testid="v4-turn-assistant"]') ?? null} />
    </span>
  );
}

// ------------------------------------------------------------------ the memo intent on the Cockpit

type Listener = () => void;
const cards = new Map<string, MemoCardState[]>();
const listeners = new Set<Listener>();
const pendings = new Map<string, { cardId: string; baseline: number; kind: "memo" | "note" | "paper"; to: string; scope: "thread" | "answer"; text: string; at: number }>();
const emit = () => listeners.forEach((l) => l());
function setCard(threadId: string, id: string, patch: Partial<MemoCardState> & { request?: string }) {
  const list = cards.get(threadId) ?? [];
  const i = list.findIndex((c) => c.id === id);
  const next = i < 0 ? [...list, { id, request: patch.request ?? "", state: "working", ...patch } as MemoCardState]
                     : list.map((c) => (c.id === id ? { ...c, ...patch } : c));
  cards.set(threadId, next);
  emit();
}

async function writeFor(threadId: string, cardId: string, kind: "memo" | "note" | "paper", to: string, scope: "thread" | "answer", text: string) {
  const t = await transcript(threadId, true);
  const doc = cockpitThreadDoc(t, threadId);
  if (!doc.turns.length) { setCard(threadId, cardId, { state: "empty", message: "There is no answer in this thread to write up yet. Ask your question first." }); return; }
  try {
    const one = scope === "answer" ? { ...doc, turns: [doc.turns[doc.turns.length - 1]] } : doc;
    const r = await threadActions.memo(one, { kind, scope: "thread", to, trigger: "memo_intent", request_text: text });
    setCard(threadId, cardId, { state: "done", result: r });
  } catch (e) {
    setCard(threadId, cardId, { state: "error", message: e instanceof Error ? e.message : "The memo could not be written." });
  }
}

/**
 * The Cockpit's ask calls this first (FX-R16-T1). `{ handled: false }`: ask as usual. `{ handled: true }`: the memo is
 * being written, do not ask. `{ handled: true, ask }`: ask `ask` (the question part); the memo follows its answer.
 */
export function cockpitMemo(text: string, threadId: string): { handled: boolean; ask?: string } {
  const answers = typeof document !== "undefined" ? document.querySelectorAll('[data-testid="v4-turn-assistant"]').length : 0;
  const plan = planMemo(text, answers);
  if (plan.action === "none" || !threadId) return { handled: false };
  const id = `m${Date.now().toString(36)}`;
  if (plan.action === "empty") { setCard(threadId, id, { request: text, state: "empty", message: plan.message }); return { handled: true }; }
  if (plan.action === "ask-then-write") {
    setCard(threadId, id, { request: text, state: "asking", message: `Answering “${plan.question}” first, then writing the ${plan.intent.kind}.` });
    pendings.set(threadId, { cardId: id, baseline: answers, kind: plan.intent.kind, to: plan.intent.to, scope: plan.intent.scope, text, at: Date.now() });
    return { handled: true, ask: plan.question };
  }
  setCard(threadId, id, { request: text, state: "working" });
  void writeFor(threadId, id, plan.intent.kind, plan.intent.to, plan.intent.scope, text);
  return { handled: true };
}

/** The memo cards under the Cockpit conversation (FX-R16-T1). */
export function CockpitMemo({ threadId }: { threadId: string }) {
  const [, force] = React.useReducer((x: number) => x + 1, 0);
  React.useEffect(() => { listeners.add(force); return () => { listeners.delete(force); }; }, []);
  // a memo asked for with its question on the Cockpit Ask or in Noor: written once the answer is in the transcript
  React.useEffect(() => {
    const req = takePendingMemo("cockpit", threadId);
    const plan = req ? planMemo(req, 1) : null;
    if (!req || !plan || plan.action === "none" || plan.action === "empty") return;
    const id = `m${Date.now().toString(36)}`;
    setCard(threadId, id, { request: req, state: "asking", message: `Writing the ${plan.intent.kind} once the answer is ready.` });
    pendings.set(threadId, { cardId: id, baseline: 0, kind: plan.intent.kind, to: plan.intent.to, scope: plan.intent.scope, text: req, at: Date.now() });
  }, [threadId]);
  // ask-then-write: once the new answer is in the transcript, write the memo
  React.useEffect(() => {
    const iv = window.setInterval(() => {
      const p = pendings.get(threadId);
      if (!p) return;
      if (Date.now() - p.at > 240_000) { pendings.delete(threadId); setCard(threadId, p.cardId, { state: "error", message: "The answer did not finish, so the memo was not written. Ask again." }); return; }
      void transcript(threadId, true).then((t) => {
        if (!t || t.turns.length <= p.baseline || pendings.get(threadId) !== p) return;
        pendings.delete(threadId);
        setCard(threadId, p.cardId, { state: "working", message: undefined });
        void writeFor(threadId, p.cardId, p.kind, p.to, p.scope, p.text);
      });
    }, 3000);
    return () => window.clearInterval(iv);
  }, [threadId]);
  const list = cards.get(threadId) ?? [];
  if (!list.length) return null;
  const threadDoc = () => cockpitThreadDoc(resolved.get(threadId) ?? null, threadId);
  return <div className="space-y-6" data-testid="cockpit-memo">{list.map((c) => <MemoCard key={c.id} card={c} threadDoc={threadDoc} />)}</div>;
}
