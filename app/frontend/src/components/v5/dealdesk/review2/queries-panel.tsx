"use client";

/**
 * PLAN_R12 Session B (I16-1, I17): RM queries on a deal, sent through Mail and threaded back.
 *
 *   <QueriesPanel dealId="PRP-B-ASB" role="credit" />   credit raises a query, sees the RM's reply from the Mail thread, closes or reopens it
 *   <QueriesPanel dealId="PRP-B-ASB" role="rm" />       the RM sees credit's queries and answers in place (the answer is a reply in the thread)
 */

import * as React from "react";
import { Mail, RefreshCw, Send } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useLoad } from "@/lib/v5/dealdesk";
import { cn } from "@/lib/utils";

import { Chip, Empty, PrimaryButton, SecondaryButton, Section } from "../kit";
import { review2Api } from "./api";
import { QUERY_LABEL, QUERY_TONE, type Query } from "./helpers";

function QueryRow({ q, role, onDone }: { q: Query; role: "credit" | "rm"; onDone: (m: string) => void }) {
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const act = async (fn: () => Promise<unknown>, m: string) => {
    setBusy(true);
    try { await fn(); onDone(m); } catch (e) { onDone(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  return (
    <li className="rounded-md border border-border px-3 py-2" data-testid="query-row" data-status={q.status}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={QUERY_TONE[q.status]}>{QUERY_LABEL[q.status]}</Chip>
        <span className="text-[11px] text-text-muted">{q.kind === "document" ? "Document" : q.kind === "finding" ? "Finding" : "Information"} · to {q.to_user} · {q.created_at.slice(0, 10)}</span>
        {q.mail_href ? <a href={q.mail_href} className="ml-auto inline-flex items-center gap-1 text-[11px] text-accent hover:underline"><Mail size={12} aria-hidden />Open in Mail</a> : null}
      </div>
      <p className="mt-1 whitespace-normal text-[12px] leading-5 text-text-primary">{q.question}</p>
      {q.reply_text ? (
        <blockquote className="mt-1.5 border-l-2 border-accent pl-2 text-[12px] leading-5 text-text-secondary" data-testid="query-reply">
          {q.reply_text}<span className="ml-1 text-[11px] text-text-muted">({q.reply_by}, {(q.answered_at ?? "").slice(0, 10)})</span>
        </blockquote>) : null}
      {q.note && q.status === "queued" ? <p className="mt-1 text-[11px] text-text-muted">Will be sent through Mail on the next refresh.</p> : null}
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {role === "rm" && q.status !== "closed" ? (
          <>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Answer credit's query" aria-label="Answer"
                   className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface px-2 text-[12px]" />
            <SecondaryButton disabled={busy || !text.trim()} onClick={() => void act(() => review2Api.answerQuery(q.query_id, text), "Answer sent.")}>
              <Send size={12} aria-hidden />Answer</SecondaryButton>
          </>) : null}
        {role === "credit" && q.status !== "closed" ? (
          <SecondaryButton disabled={busy} onClick={() => void act(() => review2Api.closeQuery(q.query_id), "Query closed.")} data-testid="query-close">Close</SecondaryButton>) : null}
        {role === "credit" && q.status === "closed" ? (
          <SecondaryButton disabled={busy} onClick={() => void act(() => review2Api.reopenQuery(q.query_id), "Query reopened.")}>Reopen</SecondaryButton>) : null}
      </div>
    </li>
  );
}

export function QueriesPanel({ dealId, role = "credit", prefill }: { dealId: string; role?: "credit" | "rm"; prefill?: { question: string; refId?: string; kind?: "finding" | "document" } | null }) {
  const [tick, setTick] = React.useState(0);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState("");
  const { data, error, loading } = useLoad(() => review2Api.queries(dealId), `queries:${dealId}:${tick}`);
  React.useEffect(() => { if (prefill?.question) setDraft(prefill.question); }, [prefill]);
  const done = (m: string) => { setMsg(m); setTick((t) => t + 1); };
  const send = async () => {
    try {
      const q = await review2Api.raiseQuery(dealId, draft, prefill?.kind ?? "information", prefill?.refId ?? null);
      setDraft("");
      done(q.status === "sent" ? `Query sent to ${q.to_user} through Mail.` : "Query kept; Mail is not reachable and it will be sent on the next refresh.");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <Section title={role === "rm" ? "Credit's queries" : "Queries to the RM"} testId="queries-panel"
             info={<>Questions credit sends to the relationship manager. Each query is a Mail message with a link back to this deal; the RM&rsquo;s
               reply in Mail (or here) is threaded back into the review, and credit closes the item once it is answered. Open queries keep the
               Versions point of the review open.</>}
             action={<SecondaryButton onClick={() => setTick((t) => t + 1)} aria-label="Refresh queries"><RefreshCw size={13} aria-hidden />Refresh</SecondaryButton>}>
      {role === "credit" ? (
        <div className="mb-3 flex items-start gap-2">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} placeholder="Ask the RM for a document, an explanation or a figure"
                    aria-label="New query" data-testid="query-draft"
                    className="min-h-[56px] min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] leading-5" />
          <PrimaryButton disabled={!draft.trim()} onClick={() => void send()} data-testid="query-send"><Send size={13} aria-hidden />Send</PrimaryButton>
        </div>) : null}
      {msg ? <p className="mb-2 text-[12px] text-text-secondary" role="status">{msg}</p> : null}
      {loading ? <Skeleton className="h-24 w-full" /> : error || !data ? <Empty>Queries are not available right now.</Empty> : !data.items.length ? (
        <Empty>{role === "rm" ? "Credit has no open queries on this deal." : "No queries raised yet."}</Empty>) : (
        <>
          <p className={cn("mb-2 text-[12px] text-text-secondary")} data-testid="queries-headline">{data.headline}</p>
          <ul className="max-h-[420px] space-y-1.5 overflow-y-auto pr-1">
            {[...data.items].reverse().map((q) => <QueryRow key={q.query_id} q={q} role={role} onDone={done} />)}
          </ul>
        </>)}
    </Section>
  );
}
