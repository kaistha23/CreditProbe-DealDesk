"use client";

/**
 * Scorecard Validation home (R16 M8: a monitoring system in the Cockpit pattern). Two tabs, in the address (?tab=ask):
 *
 *   Scorecards today  the front page: centred Ask, plain words, a health line per scorecard against the MMSG monitoring
 *                     criteria and the newspaper of the 5-10 breaches that matter; a click opens the deep dive
 *                     (?scorecard=<id>[&breach=<criterion>], also the target of Noor's brief lines)
 *   Ask               the full chat (a question opens a new thread, M6), the findings register, and past validations
 *                     kept as history (no longer the landing)
 *
 * Opened with ?validation=<id> (a link from Mail or Playbook) it goes straight to that validation's thread.
 */

import { MicButton } from "@/components/noor/mic-button";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Send } from "lucide-react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { CONCLUSION_WORD, type Conclusion, scorecard, useLoad, when } from "@/lib/v5/scorecard";
import { monitor } from "@/lib/v5/scorecard-monitor";

import { MonitorDeepDive } from "./monitor-deep";
import { MonitorFront } from "./monitor-front";
import { ASK_PLACEHOLDER } from "./monitor-model";
import { FindingsTable } from "./monitor-register";
import { Rag } from "./validation-view";
import { friendlyMessage } from "@/lib/v5/errors";
import { startFresh } from "@/lib/v5/thread-rule";

type Tab = "today" | "ask";
const TABS: { id: Tab; label: string }[] = [{ id: "today", label: "Scorecards today" }, { id: "ask", label: "Ask" }];

export function ScorecardHome() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const open = params.get("validation") ?? "";
  const sid = params.get("scorecard") ?? "";
  const breach = params.get("breach") ?? "";
  const tab: Tab = params.get("tab") === "ask" ? "ask" : "today";
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const opening = React.useRef(false);

  const go = React.useCallback((next: Partial<{ tab: Tab; scorecard: string; breach: string }>, push = false) => {
    const sp = new URLSearchParams();
    const t = next.tab ?? tab;
    if (t === "ask") sp.set("tab", "ask");
    if (next.scorecard) sp.set("scorecard", next.scorecard);
    if (next.breach) sp.set("breach", next.breach);
    const url = sp.toString() ? `${pathname}?${sp.toString()}` : pathname;
    if (push) router.push(url, { scroll: true }); else router.replace(url, { scroll: false });
  }, [pathname, router, tab]);

  const start = React.useCallback(async (question: string) => {
    setBusy(true);
    setError("");
    try {
      // M6: a question from the front page, a starter or the Ask tab always opens a NEW thread; it is asked there.
      const t = await scorecard.createThread(startFresh("scorecard", {}));  // R16 m (M6) rule + R16 s tabs
      router.push(`/scorecard-validation/thread/${t.thread_id}?ask=${encodeURIComponent(question)}`);
    } catch (e) { setError(friendlyMessage(e)); setBusy(false); }
  }, [router]);

  React.useEffect(() => {
    if (!open || opening.current) return;
    opening.current = true;
    void scorecard.validation(open).then((v) => router.replace(`/scorecard-validation/thread/${v.thread_id}`))
      .catch((e: unknown) => { setError(friendlyMessage(e)); opening.current = false; });
  }, [open, router]);

  if (open && !error) {
    return <div className="space-y-3" data-testid="sv-opening"><p className="text-[13px] text-text-muted">Opening the validation…</p><Skeleton className="h-40 w-full" /></div>;
  }
  return (
    <div className="space-y-5" data-testid="sv-home" data-tour="scorecard-home" data-tab={tab}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Model risk · monitoring</p>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-text-primary">Scorecard Validation</h1>
            <InfoPopover title="About Scorecard Validation">
              <p>Scorecards today watches every scorecard against the CBUAE Model Management Standards and Guidance (MMSG) monitoring criteria: discrimination, calibration, stability, overrides, grade migration and concentration, data quality, use against the approved scope, the validation cycle and open findings.</p>
              <p className="mt-2">Ask runs a full validation in the MMSG structure and writes its Word report; the conclusion needs a maker and a checker.</p>
            </InfoPopover>
          </div>
        </div>
        <div role="tablist" aria-label="Scorecard Validation" className="flex items-center gap-1 rounded-lg border border-border bg-surface p-0.5">
          {TABS.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={tab === t.id && !sid} data-testid={`sv-tab-home-${t.id}`}
                    onClick={() => go({ tab: t.id }, true)}
                    className={cn("rounded-md px-4 py-1.5 text-[13px] font-medium transition-colors",
                                  tab === t.id && !sid ? "bg-accent text-accent-contrast shadow-sm" : "text-text-secondary hover:text-text-primary")}>{t.label}</button>))}
        </div>
      </div>

      {sid ? (
        <div className="space-y-3">
          <BackButton fallback={{ href: "/scorecard-validation", label: "Scorecards today" }} testId="sm-deep-back" />
          <MonitorDeepDive sid={sid} focus={breach} onAsk={(q) => void start(q)} busy={busy} />
          {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        </div>
      ) : tab === "today" ? (
        <MonitorFront onOpen={(s, c) => go({ scorecard: s, breach: c }, true)} onAsk={(q) => void start(q)} busy={busy} askError={error}
                      onRegister={() => go({ tab: "ask" }, true)} />
      ) : (
        <AskTab onAsk={(q) => void start(q)} busy={busy} error={error} />
      )}
    </div>
  );
}

function AskTab({ onAsk, busy, error }: { onAsk: (q: string) => void; busy: boolean; error: string }) {
  const router = useRouter();
  const [draft, setDraft] = React.useState("");
  const [regVersion, setRegVersion] = React.useState(0);
  const meta = useLoad(() => scorecard.meta(), "meta");
  const past = useLoad(() => scorecard.validations(), "validations");
  const threads = useLoad(() => scorecard.threads(), "threads");
  const reg = useLoad(() => monitor.register(), `register-${regVersion}`);
  const ask = (text: string) => { const q = text.trim(); if (q) onAsk(q); };
  const drafts = (threads.data?.threads ?? []).filter((t) => t.stage !== "ran");
  const examples = ["Run a full MMSG validation of the SME Scorecard", ...(meta.data?.examples ?? [])];
  const openFindings = (reg.data?.findings ?? []).filter((f) => f.status !== "closed");
  return (
    <div className="space-y-5" data-testid="sv-ask-tab">
      <PlainWords testId="sv-ask-plain-words" speak lines={[
        "Ask for a validation in plain words: CreditProbe proposes a plan, runs every test and writes the MMSG report in Word.",
        "A conclusion counts only when a checker approves it; its findings join the register with an owner and a due date.",
      ]} />
      <Card className="mx-auto w-full max-w-[46rem] space-y-3 p-4" data-testid="sv-chat">
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} data-testid="sv-ask" placeholder={ASK_PLACEHOLDER}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(draft); } }}
                    className="min-h-[52px] flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-[14px] text-text-primary focus:border-accent focus:outline-none" />
          <MicButton value={draft} onChange={setDraft} size="md" testId="sv-mic" className="mb-2" />
          <button type="submit" disabled={busy || !draft.trim()} data-testid="sv-ask-send"
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-4 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40"><Send size={14} /> Ask</button>
        </form>
        <div className="flex flex-wrap gap-1.5">
          {examples.map((ex) => (
            <button key={ex} type="button" onClick={() => ask(ex)} disabled={busy} data-testid="sv-example"
                    className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-text-secondary hover:border-accent disabled:opacity-40">{ex}</button>))}
        </div>
        {error ? <p className="text-[12px] text-negative" role="alert" data-testid="sv-error">{error}</p> : null}
      </Card>

      <section className="space-y-2" data-testid="sv-register">
        <h2 className="text-[14px] font-semibold text-text-primary">Findings register <span className="font-normal text-text-muted">· {openFindings.length} open, {openFindings.filter((f) => f.overdue).length} past due</span></h2>
        {reg.error ? <p className="text-sm text-negative" role="alert">{reg.error}</p> : null}
        {!reg.data && !reg.error ? <Skeleton className="h-24 w-full" /> : null}
        {reg.data ? <FindingsTable rows={reg.data.findings} onChanged={() => setRegVersion((n) => n + 1)} showScorecard /> : null}
      </section>

      <section className="space-y-2" data-testid="sv-past">
        <h2 className="text-[14px] font-semibold text-text-primary">Past validations <span className="font-normal text-text-muted">· history</span></h2>
        {past.error ? <p className="text-sm text-negative" role="alert">{past.error}</p> : null}
        {!past.data && !past.error ? <Skeleton className="h-32 w-full" /> : null}
        {past.data && !past.data.validations.length ? <p className="text-[13px] text-text-muted">No validation has been run yet.</p> : null}
        {past.data?.validations.length ? (
          <div className="overflow-x-auto rounded-md border border-border bg-surface">
            <table className="w-full text-[13px]">
              <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                <tr><th className="px-3 py-2">Validation</th><th className="px-3 py-2">Scorecard</th><th className="px-3 py-2">As of</th><th className="px-3 py-2">Verdict</th>
                  <th className="px-3 py-2">Tests</th><th className="px-3 py-2">Review</th><th className="px-3 py-2">Run</th></tr>
              </thead>
              <tbody>
                {past.data.validations.map((v) => (
                  <tr key={v.validation_id} data-testid="sv-past-row" data-id={v.validation_id} data-scorecard={v.scorecard_id} data-overall={v.overall}
                      className="cursor-pointer border-t border-border hover:bg-surface-hover" onClick={() => router.push(`/scorecard-validation/thread/${v.thread_id}`)}>
                    <td className="px-3 py-2"><a href={`/scorecard-validation/thread/${v.thread_id}`} data-testid="sv-past-open" className="font-medium text-accent hover:underline"
                                                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); router.push(`/scorecard-validation/thread/${v.thread_id}`); }}>{v.title}</a></td>
                    <td className="px-3 py-2 text-text-secondary">{v.scorecard} v{v.version}</td>
                    <td className="px-3 py-2 tabular-nums">{v.as_of}</td>
                    <td className="px-3 py-2"><Rag status={v.overall} /></td>
                    <td className="px-3 py-2 text-[12px] text-text-secondary">{v.counts.green} / {v.counts.amber} / {v.counts.red}</td>
                    <td className="px-3 py-2 text-[12px]">{v.review.status === "reviewed" ? <span className="text-positive">{CONCLUSION_WORD[v.review.conclusion as Conclusion]}</span> : <span className="text-warning">Pending review</span>}</td>
                    <td className="px-3 py-2 text-[12px] text-text-muted">{when(v.created_at)}</td>
                  </tr>))}
              </tbody>
            </table>
          </div>) : null}
      </section>

      {drafts.length ? (
        <section className="space-y-2" data-testid="sv-drafts">
          <h2 className="text-[14px] font-semibold text-text-primary">Conversations in progress</h2>
          <div className="flex flex-wrap gap-2">
            {drafts.map((t) => (
              <button key={t.thread_id} type="button" onClick={() => router.push(`/scorecard-validation/thread/${t.thread_id}`)} data-testid="sv-draft"
                      className="rounded-md border border-border bg-surface px-3 py-1.5 text-left text-[12px] hover:border-accent">
                <span className="block font-medium text-text-primary">{t.title}</span><span className="text-text-muted">{t.stage === "plan" ? "Plan being agreed" : "Choosing a scorecard"} · {when(t.updated_at)}</span></button>))}
          </div>
        </section>) : null}
    </div>
  );
}
