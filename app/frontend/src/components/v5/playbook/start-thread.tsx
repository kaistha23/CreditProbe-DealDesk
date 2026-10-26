"use client";

/**
 * The Playbook home conversation as a thread (PLAN_R5 G4, screen 02): asking from the home chat box opens this
 * thread at `/playbook?thread=<id>`. The conversation scrolls in the middle with the Cockpit's process trace on
 * every answer; the chat box is pinned at the bottom with "Create report" beside Send.
 */

import { useRouter } from "next/navigation";
import * as React from "react";
import { ArrowLeft, FilePlus2 } from "lucide-react";

import { AssistantTurn, LiveTrace, MemoCards, ThreadActionsProvider, ThreadShell, UserTurn, useThreadActions } from "@/components/v5/thread";
import { playbookSources } from "@/lib/v5/thread-actions";
import { type Message, messageTrace, playbook, reportHref, traceBase } from "@/lib/v5/playbook";
import { newTraceId } from "@/lib/v5/thread";
import { threadIdFor } from "@/lib/v5/thread-rule";

import { AnswerExtras, MessageText } from "./ai-thread";
import { friendlyMessage } from "@/lib/v5/errors";

export function PlaybookStartThread({ threadId, initial, onBack, onStarted }: {
  threadId: string | null; initial: string | null; onBack: () => void; onStarted?: () => void;
}) {
  const router = useRouter();
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [tid, setTid] = React.useState<string | null>(threadId);
  const [pending, setPending] = React.useState<string | null>(null);
  const [traceId, setTraceId] = React.useState("");
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const started = React.useRef(false);
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo of this" writes the Word document
  // (a request for a new paper on a subject stays Playbook's own report proposal).
  const ta = useThreadActions({ module: "playbook", threadId: tid ?? "new", title: [...messages].reverse().find((m) => m.role === "assistant")?.actions?.find((a) => a.kind === "proposal")?.title ?? "", busy: Boolean(pending) });
  const opened = React.useRef<string | null>(null);  // the thread this view created or continued last

  const send = React.useCallback(async (raw: string, thread: string | null) => {
    const q = raw.trim();
    if (!q) return;
    if (ta.intercept(q, undefined, { writeOnly: true })) { setDraft(""); return; }
    const trace = newTraceId();
    setPending(q);
    setTraceId(trace);
    setError(null);
    setDraft("");
    try {
      const r = await playbook.start(q, thread, trace);
      if (r.report?.id) {
        // From a fresh question (?ask=) the report replaces it, so Back from the report returns to where the question
        // was asked, never to the question again.
        if (thread) router.push(reportHref(r.report.id)); else router.replace(reportHref(r.report.id));
        onStarted?.();
        return;
      }
      setTid(r.thread_id);
      opened.current = r.thread_id;
      setMessages((m) => [...m, ...(r.messages ?? [])]);
      if (r.thread_id && r.thread_id !== thread) router.replace(`/playbook?thread=${encodeURIComponent(r.thread_id)}`);
    } catch (e) {
      setError(friendlyMessage(e));
      setDraft(q);
    } finally {
      setPending(null);
    }
  }, [router, onStarted, ta]);

  // R16 m (M6): a question arriving as ?ask= (the home box, a suggestion, Noor) is a NEW thread, even when this view was
  // showing another thread a moment ago; ?thread=<id> (Recent work) reopens that thread. The id this view itself just
  // put in the address after the first answer is not a reopen.
  const shown = React.useRef<string>("");
  React.useEffect(() => {
    if (initial) {
      const key = `ask:${initial}`;
      if (shown.current === key) return;
      shown.current = key;
      started.current = true;
      void Promise.resolve().then(() => {
        setMessages([]);
        setTid(null);
        return send(initial, threadIdFor("landing", threadId));
      });
      return;
    }
    if (!threadId || shown.current === `thread:${threadId}` || (started.current && opened.current === threadId)) {
      if (threadId) shown.current = `thread:${threadId}`;
      return;
    }
    shown.current = `thread:${threadId}`;
    started.current = true;
    void Promise.resolve().then(() => { setTid(threadId); setMessages([]); return playbook.startThread(threadId); })
      .then((r) => setMessages(r.messages)).catch((e) => setError(friendlyMessage(e)));
  }, [threadId, initial, send]);

  const busy = Boolean(pending);
  const last = [...messages].reverse().find((m) => m.role === "assistant");
  const proposal = (last?.actions ?? []).find((a) => a.kind === "proposal");
  const chips = busy ? [] : (last?.suggestions ?? []).map((sug) => ({ label: sug, send: sug }));

  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" onClick={onBack} data-testid="playbook-thread-back"
              className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] text-text-secondary hover:bg-surface-hover">
        <ArrowLeft size={14} /> Back</button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[18px] font-semibold text-text-primary">{proposal?.title || "New document"}</h1>
        <p className="text-[11px] text-text-muted">Playbook assistant · drafts from the books</p>
      </div>
    </div>
  );

  // Pair each question with the answers that follow it.
  const turns: { user: Message | null; answers: Message[] }[] = [];
  for (const m of messages) {
    if (m.role === "user" || !turns.length) turns.push({ user: m.role === "user" ? m : null, answers: m.role === "user" ? [] : [m] });
    else turns[turns.length - 1].answers.push(m);
  }

  return (
    <ThreadShell
      header={header}
      testId="playbook-start-thread"
      scrollKey={`${messages.length}|${pending ?? ""}`}
      notice={error ? <p className="text-sm text-negative" role="alert" data-testid="playbook-chat-error">{error}</p> : null}
      composer={{
        value: draft, onChange: setDraft, onSubmit: (v) => void send(v, tid), busy, testId: "playbook-chat",
        inputTestId: "playbook-chat-input", sendTestId: "playbook-chat-send", chipTestId: "playbook-chat-followup",
        placeholder: "Reply, change the structure, or say “create it”",
        chips, onChip: (c) => void send(c.send, tid),
        actions: (
          <button type="button" disabled={busy || !proposal} onClick={() => void send("Create it", tid)} data-testid="playbook-proposal-create"
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40">
            <FilePlus2 size={14} aria-hidden /> Create report</button>),
      }}
    >
      <div className="space-y-5" data-testid="playbook-chat-reply">
        <ThreadActionsProvider value={ta}>
        {turns.map((t, i) => (
          <div key={t.user?.id ?? `t${i}`} className="space-y-3">
            {t.user ? <div data-testid="playbook-chat-message" data-role="user"><UserTurn text={t.user.text} /></div> : null}
            {t.answers.map((m, j) => (
              <div key={m.id} data-testid="playbook-chat-message" data-role="assistant">
                <AssistantTurn trace={messageTrace(m)}
                               actions={{ index: i * 100 + j, question: t.user?.text ?? "", answerId: m.id, sources: playbookSources(m.actions) }}>
                  <div className="rounded-lg border border-border bg-surface-sunken px-3.5 py-2 text-[13px] leading-relaxed text-text-primary">
                    <MessageText text={m.text} />
                  </div>
                  <AnswerExtras message={m} busy={busy} />
                </AssistantTurn>
              </div>))}
          </div>))}
        <MemoCards api={ta} />
        </ThreadActionsProvider>
        {pending ? (
          <div className="space-y-3" data-testid="playbook-chat-working">
            <UserTurn text={pending} />
            <LiveTrace base={traceBase()} traceId={traceId} />
          </div>) : null}
      </div>
    </ThreadShell>
  );
}
