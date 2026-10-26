"use client";

/**
 * One Deal Desk thread (R14 n, K16), at `/deal-desk/thread/<id>`. It replaces the fixed `?thread=desk`: a question
 * asked on the landing opens a new thread with its own id and a title from the question; questions typed in this
 * composer continue it. The first question arrives once in `?q=` and the address is cleaned after it is asked.
 * A question naming a proposal (its id or obligor) opens that proposal's page with the question.
 */

import { useRouter } from "next/navigation";
import * as React from "react";
import { ArrowLeft } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { AssistantTurn, LiveTrace, MemoCards, ThreadActionsProvider, ThreadShell, UserTurn, useThreadActions } from "@/components/v5/thread";
import { dealdeskSources } from "@/lib/v5/thread-actions";
import { backOr } from "@/lib/v5/back";
import { type DeskThreadMeta, type ProposalSummary, type Turn, dealdesk, deskUrl } from "@/lib/v5/dealdesk";
import { friendlyMessage } from "@/lib/v5/errors";
import { newTraceId } from "@/lib/v5/thread";
import { deskThreadHref, threadFor } from "@/lib/v5/thread-rule";

import { AnswerView } from "./answer";

export function DeskThread({ threadId, first }: { threadId: string; first: string }) {
  const router = useRouter();
  const [turns, setTurns] = React.useState<Turn[] | null>(threadId === "new" ? [] : null);
  const [meta, setMeta] = React.useState<DeskThreadMeta | null>(null);
  const [names, setNames] = React.useState<ProposalSummary[]>([]);
  const [draft, setDraft] = React.useState("");
  const [pending, setPending] = React.useState("");
  const [traceId, setTraceId] = React.useState("");
  const [error, setError] = React.useState("");
  const sent = React.useRef(false);
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo" writes the Word document.
  const ta = useThreadActions({ module: "dealdesk", threadId, title: meta?.title || first || "Deal Desk thread",
                                href: `/deal-desk/thread/${encodeURIComponent(threadId)}`, busy: Boolean(pending) });
  const askRef = React.useRef<(q: string) => unknown>(() => undefined);

  React.useEffect(() => {
    let live = true;
    if (threadId !== "new") void dealdesk.deskThread(threadId).then((r) => { if (live) { setTurns(r.turns); setMeta(r.thread ?? null); } })
      .catch((e) => { if (live) { setTurns([]); setError(friendlyMessage(e)); } });
    void dealdesk.proposals().then((r) => { if (live) setNames(r.proposals ?? []); }).catch(() => undefined);
    return () => { live = false; };
  }, [threadId]);

  const ask = React.useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || pending) return;
    if (ta.intercept(q, (x) => askRef.current(x))) { setDraft(""); return; }
    const named = names.find((r) => q.toUpperCase().includes(r.proposal_id) || q.toLowerCase().includes(r.obligor_name.toLowerCase()));
    if (named) { router.push(`/deal-desk/${encodeURIComponent(named.proposal_id)}?q=${encodeURIComponent(q)}`); return; }
    setDraft("");
    setError("");
    setPending(q);
    const tid = newTraceId();
    setTraceId(tid);
    // Typed inside this thread: it continues it (K16).
    const d = threadId === "new" ? { kind: "new" as const } : threadFor("thread", threadId);
    try {
      const a = await dealdesk.askDesk(q, tid, d.kind === "continue" ? d.threadId : undefined);
      if (threadId === "new" && a.thread_id) { router.replace(`/deal-desk/thread/${encodeURIComponent(a.thread_id)}`); return; }
      setTurns((t) => [...(t ?? []), { turn_id: a.turn_id ?? tid, question: q, owner: "", created: Date.now() / 1000, answer: a }]);
      if (a.thread_title && !meta) setMeta((m) => m ?? { thread_id: threadId, title: a.thread_title!, owner: "", created: 0, updated: 0, turns: 1, href: "" });
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setPending("");
    }
  }, [pending, names, router, threadId, meta, ta]);
  React.useEffect(() => { askRef.current = ask; }, [ask]);

  React.useEffect(() => {
    if (turns && first && !sent.current) {
      sent.current = true;
      window.history.replaceState(null, "", `/deal-desk/thread/${encodeURIComponent(threadId)}`);
      // The landing's question is asked once, here; if the thread already holds it (a refresh), it is not asked again.
      if (!turns.some((t) => t.question === first)) void Promise.resolve().then(() => ask(first));
    }
  }, [turns, first, ask, threadId]);

  const last = turns?.[turns.length - 1];
  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" onClick={() => backOr(router, () => router.push("/deal-desk"))} data-testid="dealdesk-thread-back"
              className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-[12px] text-text-secondary hover:bg-surface-hover">
        <ArrowLeft size={14} /> Back</button>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deal Desk · thread</p>
        <h1 className="truncate text-[20px] font-semibold text-text-primary" data-testid="dealdesk-thread-title">
          {meta?.title || first || "Ask Deal Desk"}</h1>
      </div>
    </div>
  );
  return (
    <div data-testid="dealdesk-home-thread" data-thread-id={threadId}>
      <ThreadShell testId="dealdesk-desk-thread" header={header} scrollKey={`${turns?.length ?? 0}|${pending}`}
                   notice={error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
                   composer={{ value: draft, onChange: setDraft, onSubmit: (v) => void ask(v), busy: Boolean(pending),
                               chips: pending ? [] : (last?.answer.suggestions ?? []), onChip: (c) => void ask(c.send),
                               placeholder: "Ask a follow-up, or name a proposal: “Why does DD-03 fail?”",
                               testId: "dealdesk-desk", primarySend: true }}>
        {!turns ? <Skeleton className="h-24 w-full" /> : null}
        <ThreadActionsProvider value={ta}>
        {(turns ?? []).map((t, i) => (
          <div key={t.turn_id} className="space-y-3" data-testid="dealdesk-desk-turn">
            <UserTurn text={t.question} />
            <AssistantTurn trace={t.answer.trace ?? null}
                           actions={{ index: i, question: t.question, answerId: t.turn_id, sources: dealdeskSources(t.answer) }}>
              <AnswerView answer={t.answer} onAsk={(x) => void ask(x)} busy={Boolean(pending)} chips={false} />
            </AssistantTurn>
          </div>))}
        <MemoCards api={ta} />
        </ThreadActionsProvider>
        {pending ? (
          <div className="space-y-3" data-testid="dealdesk-desk-live">
            <UserTurn text={pending} />
            <div aria-live="polite"><LiveTrace base={deskUrl("")} traceId={traceId} /></div>
          </div>) : null}
      </ThreadShell>
    </div>
  );
}

/**
 * A landing question (K16): open a new desk thread for it and go there; the thread page asks it once. If the thread
 * cannot be created first (service busy), the thread page creates it on the first ask instead.
 */
export async function openDeskThread(router: { push: (href: string) => void }, question: string): Promise<void> {
  const q = question.trim();
  if (!q) return;
  const d = threadFor("landing");
  if (d.kind !== "new") return;
  try {
    const t = await dealdesk.newDeskThread(q);
    router.push(deskThreadHref(t.thread_id, q));
  } catch {
    router.push(deskThreadHref("new", q));
  }
}
