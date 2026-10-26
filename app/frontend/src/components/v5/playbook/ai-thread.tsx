"use client";

/**
 * Playbook AI (PLAN_R4): the pieces the three conversations share.
 *
 *  - `MessageText`: an assistant's prose (paragraphs, bullet and numbered lists, bold).
 *  - `AnswerExtras`: what an answer carries under its prose: tables and charts as report blocks, links that open
 *    the screen each figure comes from, the proposal card of the top chat (sections, Create), and "Add to section".
 *  - `SectionAssistantPanel`: each section's own assistant, opened as a right-side panel from "Ask AI". Its data
 *    access follows the section (Early Warning, the Cockpit books, What-If, Scorecard, Borrower 360).
 */
import Link from "next/link";
import * as React from "react";
import { FilePlus2, Loader2, Sparkles, Undo2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AssistantTurn, Composer, LiveTrace, MemoCards, ThreadActionsProvider, UserTurn, useThreadActions } from "@/components/v5/thread";
import { playbookSources } from "@/lib/v5/thread-actions";
import { messageTrace, traceBase } from "@/lib/v5/playbook";
import { newTraceId } from "@/lib/v5/thread";
import { type Message, type MessageAction, type Report, type SectionThread as Thread, playbook } from "@/lib/v5/playbook";
import { AnswerProse } from "@/components/answer";

import { Blocks, Inline } from "./blocks";
import { friendlyMessage } from "@/lib/v5/errors";
import { canInsert, mergedOf, panelChips } from "./section-panel";

const LINK = /\[([^\]]+)\]\((\/[^)\s]*)\)/g;

/** Bold and italics as `Inline` does, plus markdown links to CreditProbe screens (relative paths only). */
function RichInline({ text }: { text: string }) {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LINK)) {
    const at = m.index ?? 0;
    if (at > last) out.push(<Inline key={`t${at}`} text={text.slice(last, at)} />);
    out.push(<Link key={`l${at}`} href={m[2]} data-testid="ai-answer-link" className="font-medium text-accent underline-offset-2 hover:underline">{m[1]}</Link>);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(<Inline key="tail" text={text.slice(last)} />);
  return <>{out}</>;
}

/**
 * A message's prose: paragraphs, lists, bold, links, and (PLAN_R5 P2) real tables, never raw pipes. PLAN_R12 N2: an
 * assistant's message is drawn by the shared answer renderer (headline sentence first, key figures, compact tables,
 * Show more); the user's own words keep the bubble's colour and size.
 */
export function MessageText({ text, role = "assistant" }: { text: string; role?: string }) {
  const mine = role === "user";
  return <AnswerProse text={String(text ?? "")} inlineRun={(t) => <RichInline text={t} />} headline={!mine} fold={!mine} inherit={mine}
                      testId="playbook-message-text" />;
}

const SHOWN = new Set(["section_drafted", "section_revised", "imported", "status", "created"]);

/** Action chips an assistant message may carry (the rich kinds are rendered by AnswerExtras). */
export function chipActions(actions: MessageAction[] | undefined): MessageAction[] {
  return (actions ?? []).filter((a) => SHOWN.has(a.kind) && a.label);
}

export function AnswerExtras({ message, onApply, applying, onSend, busy }: {
  message: Message; onApply?: (messageId: string) => void; applying?: boolean;
  onSend?: (text: string) => void; busy?: boolean;
}) {
  const answer = (message.actions ?? []).find((a) => a.kind === "answer");
  const proposal = (message.actions ?? []).find((a) => a.kind === "proposal");
  const canApply = (message.actions ?? []).some((a) => a.kind === "can_apply");
  const blocks = answer && !answer.refused ? [...(answer.blocks ?? []), ...(answer.table_blocks ?? [])] : [];
  const links = (answer?.citations ?? []).filter((c) => c.href);
  if (!blocks.length && !links.length && !proposal && !canApply) return null;
  return (
    <div className="w-full space-y-2" data-testid="playbook-answer-extras">
      {blocks.length ? (
        <div className="rounded-xl border border-border bg-surface p-3" data-testid="playbook-answer-blocks">
          <Blocks blocks={blocks} className="space-y-3 text-[13px]" />
        </div>
      ) : null}
      {proposal?.sections?.length ? (
        <div className="rounded-xl border border-accent/30 bg-accent-muted/40 p-3" data-testid="playbook-proposal">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-accent">Proposed report</p>
          <p className="mt-0.5 text-sm font-semibold text-text-primary">{proposal.title}</p>
          <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-[12px] text-text-secondary">
            {proposal.sections.map((s) => <li key={s.title}><span className="font-medium text-text-primary">{s.title}</span></li>)}
          </ol>
          {onSend ? (
            <Button size="sm" className="mt-3" disabled={busy} onClick={() => onSend("Create it")} data-testid="playbook-proposal-create">
              <FilePlus2 aria-hidden /> Create the report
            </Button>
          ) : null}
        </div>
      ) : null}
      {links.length || (canApply && onApply) ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {links.map((c, i) => (
            <Link key={i} href={c.href as string} data-testid="playbook-answer-link"
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-accent hover:bg-surface-hover">{c.label}</Link>
          ))}
          {canApply && onApply ? (
            <Button variant="outline" size="sm" className="ml-auto h-7 text-[12px]" disabled={applying}
                    onClick={() => onApply(message.id)} data-testid="playbook-answer-apply">
              {applying ? <Loader2 className="animate-spin" aria-hidden /> : <FilePlus2 aria-hidden />} Add to section
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** PLAN_R5 P3: after a merge, where it went and one Undo that restores the section (a new version). */
export function MergedNote({ reportId, sectionId, version, where, onReport }: {
  reportId: string; sectionId: string; version: number; where?: string; onReport: (r: Report) => void;
}) {
  const [state, setState] = React.useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = React.useState<string | null>(null);
  async function undo() {
    setState("busy");
    setError(null);
    try {
      onReport(await playbook.undoMerge(reportId, sectionId, version));
      setState("done");
    } catch (e) {
      setError(friendlyMessage(e));
      setState("idle");
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] text-text-secondary" data-testid="playbook-merged" data-version={version}>
      <span>{state === "done" ? "Undone: the section is back as it was." : `Added to the section${where ? ` ${where}` : ""}.`}</span>
      {state !== "done" ? (
        <Button variant="outline" size="sm" className="h-7 text-[12px]" disabled={state === "busy"} onClick={() => void undo()}
                data-testid="playbook-merge-undo">
          {state === "busy" ? <Loader2 className="animate-spin" aria-hidden /> : <Undo2 aria-hidden />} Undo
        </Button>
      ) : null}
      {error ? <span className="text-negative" role="alert">{error}</span> : null}
    </div>
  );
}

/**
 * R10 C2: the assistant of one section, opened as a right-side panel from the section's "Ask AI". Its data access
 * follows the section; each answer (words, tables, charts) carries "Insert into this section", which merges it into
 * the section as a new version (with one Undo).
 */
export function SectionAssistantPanel({ reportId, sectionId, title, canWrite, onReport, onClose }: {
  reportId: string; sectionId: string; title: string; canWrite: boolean; onReport: (r: Report) => void; onClose: () => void;
}) {
  const [data, setData] = React.useState<Thread | null>(null);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [text, setText] = React.useState("");
  const [pending, setPending] = React.useState<string | null>(null);
  const [traceId, setTraceId] = React.useState("");
  const [applying, setApplying] = React.useState<string | null>(null);
  const [merged, setMerged] = React.useState<Record<string, { version: number; where?: string }>>({});
  const [error, setError] = React.useState<string | null>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo of this" writes the Word document.
  const ta = useThreadActions({ module: "playbook", threadId: `${reportId}:${sectionId}`, title: `Playbook: ${title}`, busy: Boolean(pending) });

  React.useEffect(() => {
    let live = true;
    playbook.sectionThread(reportId, sectionId)
      .then((t) => { if (live) { setData(t); setMessages(t.messages); } })
      .catch((e) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, [reportId, sectionId]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  React.useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [messages.length, pending]);

  async function send(raw: string) {
    const q = raw.trim();
    if (!q || pending) return;
    if (ta.intercept(q, undefined, { writeOnly: true })) { setText(""); return; }
    setPending(q);
    setError(null);
    setText("");
    const trace = newTraceId();
    setTraceId(trace);
    try {
      const r = await playbook.sectionSay(reportId, sectionId, q, trace);
      setMessages((m) => [...m, ...r.messages]);
      onReport(r.report);
    } catch (e) {
      setError(friendlyMessage(e));
      setText(q);
    } finally {
      setPending(null);
    }
  }

  async function apply(mid: string) {
    setApplying(mid);
    setError(null);
    try {
      const rep = await playbook.applyAnswer(reportId, sectionId, mid);
      if (rep.merged) setMerged((m) => ({ ...m, [mid]: { version: rep.merged!.version, where: rep.merged!.where } }));
      onReport(rep);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setApplying(null);
    }
  }

  const chips = panelChips(messages, data?.suggestions);
  return (
    <aside role="dialog" aria-modal="false" aria-label={`Ask AI about ${title}`} data-testid="playbook-section-panel" data-section={sectionId}
           className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-border bg-surface shadow-2xl sm:w-[460px]">
      <header className="flex items-start gap-2 border-b border-border px-4 py-3">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Ask AI</p>
          <h2 className="truncate text-[15px] font-semibold text-text-primary" data-testid="playbook-section-panel-title">{title}</h2>
          {data ? <p className="truncate text-[11px] text-text-muted">Reads {data.data_access}</p> : null}
        </div>
        <button type="button" onClick={onClose} aria-label="Close the assistant" data-testid="playbook-section-panel-close"
                className="rounded-md p-1 text-text-muted hover:bg-surface-hover hover:text-text-primary">
          <X className="size-4" aria-hidden />
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3" data-testid="playbook-section-thread-body">
        {!data && !error ? <p className="flex items-center gap-2 text-xs text-text-muted"><Loader2 className="size-3.5 animate-spin" aria-hidden /> Opening the thread…</p> : null}
        {data && !messages.length && !pending ? (
          <p className="text-[13px] text-text-secondary">Ask about this section: an analysis, a chart or a paragraph. Insert any answer into the section.</p>
        ) : null}
        <ThreadActionsProvider value={ta}>
        {messages.map((m, i) => (
          <div key={m.id} data-testid="playbook-section-message" data-role={m.role}>
            {m.role === "user" ? <UserTurn text={m.text} compact /> : (
              <AssistantTurn trace={messageTrace(m)} compact
                             actions={{ index: i, question: [...messages.slice(0, i)].reverse().find((x) => x.role === "user")?.text ?? title, answerId: m.id, sources: playbookSources(m.actions) }}>
                <div className="max-w-full rounded-lg border border-border bg-surface-sunken px-3.5 py-2 text-[13px] leading-relaxed text-text-primary [overflow-wrap:anywhere]">
                  <MessageText text={m.text} />
                </div>
                <AnswerExtras message={m} />
                {canWrite ? (() => {
                  const done = mergedOf(m, merged);
                  if (done) return <MergedNote reportId={reportId} sectionId={sectionId} version={done.version} where={done.where} onReport={onReport} />;
                  return canInsert(m, merged) ? (
                    <Button variant="outline" size="sm" className="h-7 text-[12px]" disabled={!!applying || !!pending}
                            onClick={() => void apply(m.id)} data-testid="playbook-answer-apply">
                      {applying === m.id ? <Loader2 className="animate-spin" aria-hidden /> : <FilePlus2 aria-hidden />} Insert into this section
                    </Button>
                  ) : null;
                })() : null}
              </AssistantTurn>)}
          </div>
        ))}
        <MemoCards api={ta} compact />
        </ThreadActionsProvider>
        {pending ? (
          <div className="space-y-2" data-testid="playbook-section-thread-working">
            <UserTurn text={pending} compact />
            <LiveTrace base={traceBase()} traceId={traceId} compact />
          </div>
        ) : null}
        <div ref={endRef} />
        {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
      </div>
      {canWrite ? (
        <div className="border-t border-border bg-surface px-4 py-3" data-testid="playbook-section-composer">
          <Composer compact testId="playbook-section-thread" inputTestId="playbook-section-thread-input" sendTestId="playbook-section-thread-send" chipTestId="playbook-section-thread-chip"
                    value={text} onChange={setText} onSubmit={(v) => void send(v)} busy={!!pending}
                    placeholder={`Ask about “${title}”`}
                    chips={pending ? [] : chips.map((c) => ({ label: c, send: c }))} onChip={(c) => void send(c.send)} />
        </div>
      ) : (
        <p className="border-t border-border px-4 py-3 text-xs text-text-muted">Read only: you can see the answers but not ask or insert.</p>
      )}
    </aside>
  );
}
