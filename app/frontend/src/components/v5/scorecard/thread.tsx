"use client";

/**
 * One validation conversation at its own URL (/scorecard-validation/thread/<id>): choose a scorecard, agree the
 * plan, run it, review, report. A turn is answered in one request, so the page shows a working state while the
 * tests run (about a second) and then the settled answer.
 */

import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { FileSpreadsheet, FileText } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { ShareButton } from "@/components/v5/mail/share";
import { cn } from "@/lib/utils";
import { AssistantTurn, LiveTrace, ThreadShell, UserTurn, MemoCards, ThreadActionsProvider, useThreadActions } from "@/components/v5/thread";
import { scorecardSources } from "@/lib/v5/thread-actions";
import { type ThreadView, apiUrl, exportHref, reportHref, scorecard } from "@/lib/v5/scorecard";
import { mmsgHref } from "@/lib/v5/scorecard-monitor";
import { newTraceId } from "@/lib/v5/thread";

import { AddToReport } from "./add-report";
import { AnswerView } from "./blocks";
import { CONCLUSION_EVENT, MmsgPanel } from "./mmsg-panel";
import { ReviewSection } from "./validation-view";
import { friendlyMessage } from "@/lib/v5/errors";

export function ScorecardThread({ threadId }: { threadId: string }) {
  const [thread, setThread] = React.useState<ThreadView | null>(null);
  const [error, setError] = React.useState("");
  const [pending, setPending] = React.useState<string | null>(null);
  const [traceId, setTraceId] = React.useState("");
  const [draft, setDraft] = React.useState("");
  const [notice, setNotice] = React.useState("");

  const [reviewKey, setReviewKey] = React.useState(0);
  React.useEffect(() => {
    const on = () => setReviewKey((n) => n + 1);
    window.addEventListener(CONCLUSION_EVENT, on);
    return () => window.removeEventListener(CONCLUSION_EVENT, on);
  }, []);
  const load = React.useCallback(async () => {
    try { setThread(await scorecard.thread(threadId)); setError(""); }
    catch (e) { setError(friendlyMessage(e)); }
  }, [threadId]);
  React.useEffect(() => { void Promise.resolve().then(load); }, [load]);

  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo" writes the Word document.
  const ta = useThreadActions({ module: "scorecard", threadId, title: thread?.title ?? "Scorecard thread", busy: Boolean(pending) });
  const askRef = React.useRef<(q: string) => unknown>(() => undefined);
  const ask = React.useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || pending) return;
    if (ta.intercept(q, (x) => askRef.current(x))) { setDraft(""); return; }
    setDraft("");
    setNotice("");
    setPending(q);
    const tid = newTraceId();
    setTraceId(tid);
    try { setThread(await scorecard.say(threadId, q, tid)); }
    catch (e) { setNotice(friendlyMessage(e)); }
    finally { setPending(null); }
  }, [pending, threadId, ta]);
  React.useEffect(() => { askRef.current = ask; }, [ask]);

  // A question asked on the home arrives as ?ask=: send it once, then drop it from the address.
  const asked = React.useRef(false);
  React.useEffect(() => {
    if (!thread || asked.current || typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search).get("ask");
    asked.current = true;
    if (!q) return;
    window.history.replaceState(null, "", window.location.pathname);
    void Promise.resolve().then(() => ask(q));
  }, [thread, ask]);

  if (error) {
    return (
      <div className="space-y-3">
        <BackButton fallback={{ href: "/scorecard-validation", label: "Scorecard Validation" }} testId="sv-back" />
        <p className="text-sm text-negative" role="alert" data-testid="sv-error">{error}</p>
      </div>
    );
  }
  if (!thread) return <Skeleton className="h-64 w-full" />;
  const val = thread.validations[thread.validations.length - 1];
  const sc = thread.scorecard;
  const last = thread.turns[thread.turns.length - 1];
  const chips = pending ? [] : last?.answer.suggestions ?? [];
  const busy = Boolean(pending);

  const linkCls = "inline-flex items-center gap-1 rounded-md border border-border px-3 py-2 text-[13px] hover:bg-surface-hover";
  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <BackButton fallback={{ href: "/scorecard-validation", label: "Scorecard Validation" }} testId="sv-back" />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[18px] font-semibold text-text-primary" data-testid="sv-thread-title">{thread.title}</h1>
        <p className="text-[11px] text-text-muted" data-testid="sv-thread-sub">
          {sc ? `${sc.name} v${sc.version} · ${sc.book} book` : "Choose a scorecard"}{val ? ` · as of ${val.as_of}` : ""}{thread.owner ? ` · owner ${thread.owner}` : ""}</p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5" data-testid="sv-actions">
        {val ? (
          <ShareButton testId="sv-share" object={{ type: "scorecard-validation", id: val.validation_id, label: val.title, href: `/scorecard-validation?validation=${val.validation_id}`,
                                                    summary: `${val.counts.green} green, ${val.counts.amber} amber, ${val.counts.red} red tests.`, meta: { book: val.book, period: val.as_of, scorecard: val.scorecard_id } }} />) : null}
        {val ? <AddToReport validationId={val.validation_id} defaultTitle={`${val.scorecard}: validation ${val.as_of}`} book={val.book} /> : null}
      </div>
    </div>
  );

  return (
    <ThreadShell
      header={header}
      testId="sv-thread-shell"
      scrollKey={`${thread.turns.length}|${pending ?? ""}`}
      notice={notice ? <p className="rounded-md border border-border bg-surface px-3 py-2 text-[12px] text-negative" role="alert" data-testid="sv-notice">{notice}</p> : null}
      composer={{
        value: draft, onChange: setDraft, onSubmit: (v) => void ask(v), busy, testId: "sv", primarySend: true,
        // PLAN_R10 G-CHAT: the report and Excel links lead the input row, so Send is its right end.
        leading: (
          <div className="flex items-end gap-1.5" data-testid="sv-actions-lead">
            <a href={val ? mmsgHref(val.validation_id) : undefined} aria-disabled={!val} data-testid="sv-mmsg"
               className={cn(linkCls, !val && "pointer-events-none opacity-40")}><FileText size={14} /> MMSG report</a>
            <a href={val ? reportHref(val.validation_id) : undefined} aria-disabled={!val} data-testid="sv-word"
               className={cn(linkCls, !val && "pointer-events-none opacity-40")}><FileText size={14} /> Create report</a>
            <a href={val ? exportHref(val.validation_id) : undefined} aria-disabled={!val} data-testid="sv-excel"
               className={cn(linkCls, !val && "pointer-events-none opacity-40")}><FileSpreadsheet size={14} /> Excel</a>
          </div>),
        chips: chips.map((c) => ({ label: c.label, send: c.send })), onChip: (c) => void ask(c.send),
        placeholder: thread.stage === "ran" ? "Ask about the results, e.g. “what is PSI?”"
          : thread.stage === "plan" ? "Change the plan, or say “run it”" : "Which scorecard should we validate?",
      }}
    >
      <div className="space-y-5" data-testid="sv-thread" data-thread={thread.thread_id} data-stage={thread.stage}>
        <ThreadActionsProvider value={ta}>
        {thread.turns.map((t, i) => (
          <div key={t.ordinal} className="space-y-3" data-testid="sv-turn">
            <UserTurn text={t.answer.question_display || t.question} />
            <AssistantTurn trace={(t.answer as { trace?: import("@/lib/v5/thread").TraceSnapshot }).trace}
                           actions={{ index: i, question: t.answer.question_display || t.question, answerId: String(t.ordinal), sources: scorecardSources(t.answer, thread.scorecard_id) }}>
              <AnswerView answer={t.answer} onAsk={ask} busy={busy} isLast={i === thread.turns.length - 1} />
            </AssistantTurn>
          </div>))}
        <MemoCards api={ta} />
        </ThreadActionsProvider>
        {pending ? (
          <div className="space-y-3" data-testid="sv-live-turn">
            <UserTurn text={pending} />
            <div data-testid="sv-working" aria-live="polite"><LiveTrace base={apiUrl("")} traceId={traceId} /></div>
          </div>) : null}
        {/* R16 M8: the maker-checker conclusion and the MMSG report; shown here when no answer above carries it. */}
        {val && !thread.turns.some((t) => t.answer.blocks.some((b) => b.type === "mmsg" && b.validation_id === val.validation_id))
          ? <MmsgPanel validationId={val.validation_id} onChanged={load} /> : null}
        {val ? (
          <details open className="rounded-md border border-border bg-surface px-3 py-2" data-testid="sv-review-single">
            <summary className="cursor-pointer text-[12px] text-text-secondary">Single-step review (earlier record; the maker-checker conclusion above is the one that counts)</summary>
            <div className="pt-2"><ReviewSection key={reviewKey} id={val.validation_id} onChanged={load} /></div>
          </details>) : null}
      </div>
    </ThreadShell>
  );
}
