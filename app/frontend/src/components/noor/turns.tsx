"use client";

/**
 * How each turn of Noor's thread is drawn: the brief, Why? (the trace steps playing out live with ticking counters,
 * then a one-line answer and one Plotly chart), What should we do? (three options with the engines' numbers, each
 * with Send to committee) and the committee item created.
 *
 * Answer style: N2's shared answer renderer (`@/components/answer`, PLAN_R12 N2): the one-line answer in the answer
 * headline style, key figures as answer tiles, the chart through the one Plotly surface with the shared theme.
 */

import * as React from "react";
import Link from "next/link";
import { Check, Loader2, Send } from "lucide-react";

import { ANSWER_STYLE, AnswerFigures, AnswerHeadline, AnswerTable, Plot } from "@/components/answer";
import { cn } from "@/lib/utils";

import { NoorBrief } from "./noor-brief";
import {
  type BriefItem, type BriefNumber, type DecisionOption, type Turn, type WhyAnswer, splitFigures, tickValue, traceLine,
  traceSchedule,
} from "./noor-model";
import { askDrivers, askHere, askOptions, go, hereAction, sendToCommittee, showMe } from "./noor-store";
import type { HereAnswer, HereFix } from "./noor-model";
import { NoorPlainWords } from "./noor-plain-words";
import { SpeakText } from "./speak-text";

/** K10: the speaker on an answer reads its spoken summary (the explanation), never its tables. */
function Speaker({ en, ar, testId }: { en?: string; ar?: string | null; testId: string }) {
  if (!en) return null;
  return <SpeakText en={en} ar={ar} label="Listen to this answer" testId={testId} className="float-right -mr-1 ml-2" />;
}

export function TurnView({ turn }: { turn: Turn }) {
  switch (turn.kind) {
    case "brief":
      return (
        <div data-testid="noor-turn-brief">
          <span className="sr-only" data-testid="noor-opening">{turn.brief.opening}</span>
          <NoorBrief brief={turn.brief} variant="panel" testId="noor-brief" />
        </div>
      );
    case "ask":
      return (
        <p className="ml-auto max-w-[85%] rounded-lg bg-surface-sunken px-3 py-1.5 font-user text-[12.5px] text-text-secondary"
           data-testid="noor-turn-ask">{turn.text}</p>
      );
    case "pending":
      return (
        <p className="flex items-center gap-2 text-[12.5px] text-text-muted" data-testid="noor-turn-pending">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />{turn.text}…
        </p>
      );
    case "note":
      return <p className="text-[12.5px] text-text-muted" data-testid="noor-turn-note">{turn.text}</p>;
    case "routed":
      return (
        <div className="space-y-1" data-testid="noor-turn-routed">
          <p className="flex flex-wrap items-baseline gap-x-2 text-[12.5px] text-text-secondary">
            <span>Answered in {turn.label}.</span>
            <button type="button" onClick={() => go(turn.href)} className="font-medium text-accent underline-offset-4 hover:underline">
              Open the answer</button>
          </p>
          {/* R15 L9: a question asked on a deal page that went elsewhere says why, and can be answered on the page instead. */}
          {turn.why ? <p className="text-[11.5px] text-text-muted" data-testid="noor-routed-why">{turn.why}</p> : null}
          {turn.here?.deal_id ? (
            <button type="button" onClick={() => void askHere(turn.question, turn.here!, { force: true, echo: false })}
                    data-testid="noor-answer-here-instead"
                    className="text-[12px] font-medium text-accent underline-offset-4 hover:underline">
              Answer here instead, on {turn.here.deal_id}</button>) : null}
        </div>
      );
    case "here":
      return <HereView answer={turn.answer} fix={turn.fix ?? null} question={turn.question} />;
    case "error":
      return <p className="text-[12.5px] text-negative" role="alert" data-testid="noor-turn-error">{turn.text}</p>;
    case "why":
      return <WhyView item={turn.item} answer={turn.answer} turnId={turn.id} />;
    case "options":
      return (
        <section data-testid="noor-turn-options">
          <NoorPlainWords lines={turn.answer.plain_words ?? []} speak={turn.answer.spoken} className="mb-2" testId="noor-plain-words" />
          <Speaker en={turn.answer.spoken || turn.answer.answer} testId="noor-answer-speaker" />
          <AnswerHeadline text={turn.answer.answer} compact inlineRun={(t) => <Emph text={t} />} />
          <div className="mt-2 space-y-2">
            {turn.answer.options.map((o, i) => <OptionCard key={o.key} n={i + 1} option={o} item={turn.item} />)}
          </div>
          {turn.answer.engine ? <p className="mt-1.5 text-[11px] text-text-muted">Priced by the {turn.answer.engine}.</p> : null}
        </section>
      );
    case "drivers":
      return (
        <section data-testid="noor-turn-drivers" className="space-y-2">
          <Speaker en={turn.answer.spoken || turn.answer.answer} testId="noor-answer-speaker" />
          <AnswerHeadline text={turn.answer.answer} compact inlineRun={(t) => <Emph text={t} />} />
          {turn.answer.rows.length ? (
            <AnswerTable columns={turn.answer.columns} max={8} testId="noor-drivers-table"
                         rows={turn.answer.rows.map((r) => ({
                           ...r,
                           name: <button type="button" onClick={() => go(r.href)} className="text-left font-medium text-accent hover:underline">{r.name}</button>,
                         }))} />
          ) : null}
          {turn.answer.show_me ? (
            <p className="text-[12px]"><FollowUp onClick={() => go(turn.answer.show_me!.href)} testId="noor-drivers-show">
              {turn.answer.show_me.label}</FollowUp></p>
          ) : null}
        </section>
      );
    case "committee":
      return (
        <section className="rounded-md border border-positive/40 bg-positive-muted px-3 py-2" data-testid="noor-turn-committee">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-text-primary">
            <Check className="size-4 text-positive" aria-hidden />{turn.result.message}
          </p>
          <p className="mt-0.5 text-[11.5px] text-text-muted">
            On the committee agenda for the chair&apos;s decision; nothing changes until the committee decides.{" "}
            <Link href={turn.result.open.href} className="text-accent hover:underline">{turn.result.open.label}</Link>
          </p>
        </section>
      );
    default:
      return null;
  }
}

/** Figures in a sentence drawn in the figures face, so the eye finds them (I10 answer style). */
export function Emph({ text }: { text: string }) {
  const parts = splitFigures(text);
  return (
    <>{parts.map((p, i) => (i % 2 === 1
      ? <strong key={i} className="font-display font-semibold tabular-nums">{p}</strong>
      : <React.Fragment key={i}>{p}</React.Fragment>))}</>
  );
}

function Numbers({ items }: { items: BriefNumber[] }) {
  const shown = items.filter((n) => n.display && n.display !== "–");
  if (!shown.length) return null;
  return (
    <dl className="grid grid-cols-3 gap-x-3 gap-y-1.5">
      {shown.map((n) => (
        <div key={n.label} className="min-w-0">
          <dt className={cn(ANSWER_STYLE.kpiLabel, "truncate text-[10px]")}>{n.label}</dt>
          <dd className={cn(ANSWER_STYLE.figure, "text-[13.5px]")}>{n.display}</dd>
        </div>
      ))}
    </dl>
  );
}

function WhyView({ item, answer, turnId }: { item: BriefItem; answer: WhyAnswer; turnId: string }) {
  const schedule = React.useMemo(() => traceSchedule(answer.steps), [answer.steps]);
  const total = schedule.length ? schedule[schedule.length - 1].startMs + schedule[schedule.length - 1].durationMs : 0;
  // Played once per turn; a turn restored from the session is shown settled.
  const [t0] = React.useState(() => (played.has(turnId) ? -1 : performance.now()));
  const [now, setNow] = React.useState(() => performance.now());
  const settled = t0 < 0 || now - t0 >= total;
  React.useEffect(() => {
    if (t0 < 0) return;
    played.add(turnId);
    let raf = 0;
    const tick = () => { setNow(performance.now()); if (performance.now() - t0 < total) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [t0, total, turnId]);
  const elapsed = t0 < 0 ? Infinity : now - t0;
  return (
    <section data-testid="noor-turn-why">
      <ol className="space-y-1 rounded-md border border-border bg-surface-sunken px-3 py-2" data-testid="noor-trace">
        {answer.steps.map((s, i) => {
          const sc = schedule[i];
          if (elapsed < sc.startMs) return null;
          const done = elapsed >= sc.startMs + sc.durationMs;
          const v = tickValue(s.count, elapsed - sc.startMs, sc.durationMs);
          return (
            <li key={i} className="flex items-baseline gap-2 text-[12px]" data-testid="noor-trace-step">
              <span className={cn("w-3 shrink-0", done ? "text-positive" : "animate-pulse text-accent")} aria-hidden>
                {done ? "✓" : "●"}</span>
              <span className="min-w-0 flex-1 text-text-secondary">{s.label}</span>
              {v !== null ? (
                <span className="shrink-0 font-display tabular-nums text-text-primary">
                  {v.toLocaleString("en-GB")} <span className="text-text-muted">{s.unit}</span></span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {settled ? (
        <div className="mt-2 space-y-2">
          <NoorPlainWords lines={answer.plain_words ?? []} speak={answer.spoken} ar={answer.spoken_ar} testId="noor-plain-words" />
          <div data-testid="noor-why-answer">
            <Speaker en={answer.spoken || answer.answer} ar={answer.spoken_ar} testId="noor-answer-speaker" />
            <AnswerHeadline text={answer.answer} compact inlineRun={(t) => <Emph text={t} />} />
          </div>
          {answer.figure ? (
            <div className="rounded-md border border-border bg-surface px-1 pt-1" data-testid="noor-why-chart">
              <Plot data={answer.figure.data} layout={{ ...answer.figure.layout, height: undefined, title: undefined }}
                    height={Number(answer.figure.layout.height ?? 260)}
                    ariaLabel={String((answer.figure.layout.title as { text?: string } | undefined)?.text ?? "Why chart")}
                    filename="noor-why" />
            </div>
          ) : null}
          <AnswerFigures compact testId="noor-why-figures"
                         items={answer.numbers.filter((n) => n.display && n.display !== "–")
                           .map((n) => ({ label: n.label, value: n.display }))} />
          <details className="text-[11px] text-text-muted">
            <summary className="cursor-pointer select-none">Sources ({answer.trace.length})</summary>
            <ul className="mt-1 space-y-0.5">{answer.trace.map((t, i) => <li key={i}>{traceLine(t)}</li>)}</ul>
          </details>
          <nav aria-label="Next" className="flex flex-wrap items-baseline gap-x-1.5 text-[12px]">
            <FollowUp onClick={() => void askOptions(item)} testId="noor-why-options">What to do</FollowUp>
            {item.kind === "sector_appetite" ? (<>
              <Sep /><FollowUp onClick={() => void askDrivers(item)} testId="noor-why-drivers">Who drives it</FollowUp></>) : null}
            {item.evidence?.length ? (<>
              <Sep /><FollowUp onClick={() => go(item.evidence![0].href)} testId="noor-why-evidence">Evidence card</FollowUp></>) : null}
            <Sep /><FollowUp onClick={() => showMe(item)} testId="noor-why-show">{item.show_me.label}</FollowUp>
          </nav>
        </div>
      ) : null}
    </section>
  );
}

const played = new Set<string>();

function FollowUp({ children, onClick, testId }: { children: React.ReactNode; onClick: () => void; testId: string }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
            className="font-medium text-accent underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none">
      {children}</button>
  );
}

function Sep() {
  return <span aria-hidden className="text-text-muted/50">·</span>;
}

function OptionCard({ n, option, item }: { n: number; option: DecisionOption; item: BriefItem }) {
  const [sent, setSent] = React.useState(false);
  return (
    <article className={cn("rounded-md border px-3 py-2", option.recommended ? "border-accent bg-accent-muted/40" : "border-border")}
             data-testid={`noor-option-${option.key}`}>
      <header className="flex items-start justify-between gap-2">
        <h4 className="text-[13px] font-semibold leading-snug text-text-primary">
          <span className="mr-1.5 font-display text-text-muted">{n}.</span>{option.title}</h4>
        {option.recommended ? (
          <span className="shrink-0 rounded-full bg-accent px-2 py-[1px] text-[10.5px] font-semibold text-accent-contrast">
            Recommended</span>) : null}
      </header>
      <p className="mt-0.5 text-[12px] text-text-secondary">{option.how}</p>
      <div className="mt-1.5"><Numbers items={option.numbers} /></div>
      <p className="mt-1 text-[11.5px] text-text-muted">{option.effect}</p>
      <button type="button" disabled={sent} data-testid={`noor-committee-${option.key}`}
              onClick={() => { setSent(true); void sendToCommittee(item, option); }}
              className={cn("mt-1.5 inline-flex items-center gap-1 rounded-full px-3 py-1 text-[12px] font-medium transition-colors",
                option.recommended ? "bg-accent text-accent-contrast hover:bg-accent-hover"
                                   : "border border-border text-text-secondary hover:border-accent hover:text-accent",
                sent && "opacity-60")}>
        <Send className="size-3" aria-hidden />{sent ? "Sent" : "Send to committee"}
      </button>
    </article>
  );
}

/** R15 L9: Noor's answer on the page: the deal on screen or the stress run on screen, with the cheapest fix. */
function HereView({ answer: a, fix, question }: { answer: HereAnswer; fix: HereFix | null; question: string }) {
  const sevs = ["mild", "moderate", "severe"];
  return (
    <section data-testid="noor-turn-here" data-topic={a.topic} data-deal={a.deal_id} className="space-y-2">
      <p className="text-[11px] text-text-muted" data-testid="noor-here-reason">{a.reason}</p>
      <NoorPlainWords lines={a.plain_words} speak={a.spoken} testId="noor-here-plain-words" />
      <Speaker en={a.spoken} testId="noor-here-speaker" />
      <AnswerHeadline text={a.title} compact />
      <ul className="space-y-1 text-[12.5px] leading-snug text-text-secondary" data-testid="noor-here-lines">
        {a.lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
      {a.rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[11.5px]" data-testid="noor-here-table">
            <thead><tr className="text-left text-[10px] uppercase tracking-wide text-text-muted">
              <th className="py-1 pr-2">Structure</th>{sevs.map((s) => <th key={s} className="py-1 pr-2 capitalize">{s}</th>)}</tr></thead>
            <tbody>{a.rows.map((r) => (
              <tr key={r.key} className="border-t border-border align-top" data-testid="noor-here-row" data-key={r.key}>
                <td className="py-1 pr-2 font-medium text-text-primary">{r.structure}</td>
                {sevs.map((s) => {
                  const c = r.cells[s];
                  return (
                    <td key={s} className="py-1 pr-2">
                      {r.status !== "stressed" ? <span className="text-text-muted">fails before stress</span> : c ? (<>
                        <span className={cn("font-medium", c.passes ? "text-positive" : "text-negative")}>{c.passes ? "Pass" : "Fail"}</span>
                        {c.applicable ? <span className="text-text-muted"> · {c.breaking}/{c.applicable}</span> : null}
                        {!c.passes ? <p className="text-text-secondary">{c.first}</p> : null}</>) : "–"}
                    </td>);
                })}
              </tr>))}</tbody>
          </table>
        </div>) : null}
      {a.fix_from ? (
        <div className="rounded-md border border-border bg-surface-sunken px-3 py-2 text-[12px]" data-testid="noor-here-fix" data-ready={fix ? "true" : "false"}>
          {fix ? (<>
            <p className="text-text-primary">{fix.line}</p>
            {fix.asks.length ? <p className="mt-0.5 text-text-muted">Asks of the client: {fix.asks.join("; ")}.</p> : null}
          </>) : <p className="flex items-center gap-2 text-text-muted"><Loader2 className="size-3.5 animate-spin" aria-hidden />Finding the cheapest fix (Stress-proof)…</p>}
        </div>) : null}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
        {a.actions.map((x) => (
          <button key={x.label} type="button" onClick={() => hereAction(x.kind, question, x)} data-testid={`noor-here-action-${x.kind}`}
                  className="font-medium text-accent underline-offset-4 hover:underline">{x.label}</button>))}
      </div>
      <p className="text-[11px] text-text-muted">{a.basis}{a.regime_line ? ` ${a.regime_line}` : ""}</p>
    </section>
  );
}
