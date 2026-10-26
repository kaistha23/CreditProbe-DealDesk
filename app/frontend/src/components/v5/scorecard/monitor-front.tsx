"use client";

/**
 * R16 M8: "Scorecards today", the Scorecard Validation front page in the Cockpit pattern. A centred Ask, the plain
 * words, one health line per scorecard against the MMSG monitoring criteria, and a newspaper front page of the 5-10
 * breaches that matter (lead story first). Every line opens the scorecard's deep dive. Served by /monitor/front.
 */

import * as React from "react";
import { ArrowRight, Bell, CalendarClock, Send } from "lucide-react";

import { MicButton } from "@/components/noor/mic-button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/scorecard";
import { type Breach, type CriterionLine, type Health, monitor } from "@/lib/v5/scorecard-monitor";

import { ASK_PLACEHOLDER, ASK_STARTERS, CRITERION_SHORT, day, frontHeadline, newspaper, person, sparkPoints } from "./monitor-model";
import { Rag } from "./validation-view";

const DOT: Record<string, string> = { green: "bg-positive", amber: "bg-warning", red: "bg-negative", na: "bg-border" };
const STROKE: Record<string, string> = { green: "var(--color-positive, #2E9E5B)", amber: "var(--color-warning, #E8A317)", red: "var(--color-negative, #D64545)", na: "#8A94A6" };

/** A small trend line of a breach's metric (last 8 periods), coloured by today's verdict. */
export function Sparkline({ line, w = 96, h = 24, testId = "sm-spark" }: { line: Pick<CriterionLine, "trend" | "status">; w?: number; h?: number; testId?: string }) {
  const pts = sparkPoints(line.trend.map((t) => t.value), w, h);
  if (pts.length < 2) return <span className="inline-block text-[11px] text-text-muted" data-testid={testId}>—</span>;
  const last = pts[pts.length - 1];
  const first = line.trend.find((t) => t.value !== null);
  const lastT = [...line.trend].reverse().find((t) => t.value !== null);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" data-testid={testId}
         aria-label={`Trend from ${first?.period} to ${lastT?.period}`} className="shrink-0 overflow-visible">
      <polyline fill="none" stroke={STROKE[line.status] ?? STROKE.na} strokeWidth={1.6} points={pts.map((p) => `${p.x},${p.y}`).join(" ")} />
      <circle cx={last.x} cy={last.y} r={2.4} fill={STROKE[line.status] ?? STROKE.na} />
    </svg>
  );
}

function Facts({ b }: { b: Breach | CriterionLine }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-4" data-testid="sm-facts">
      <div><dt className="text-text-muted">{b.label}</dt><dd className="font-semibold tabular-nums text-text-primary" data-testid="sm-value">{b.display}</dd></div>
      <div className="col-span-1 sm:col-span-1"><dt className="text-text-muted">Limit</dt><dd className="text-text-secondary" data-testid="sm-threshold">{b.threshold || "—"}</dd></div>
      <div><dt className="text-text-muted">Since</dt><dd className="text-text-secondary" data-testid="sm-since">{b.since ? day(b.since) : "this period"}</dd></div>
      <div><dt className="text-text-muted">Owner</dt><dd className="text-text-secondary" data-testid="sm-owner">{person(b.owner)}</dd></div>
    </dl>
  );
}

function Story({ b, lead, onOpen }: { b: Breach; lead?: boolean; onOpen: (sid: string, criterion: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(b.scorecard_id, b.criterion)} data-testid={lead ? "sm-lead" : "sm-story"} data-breach={b.id} data-status={b.status}
            data-rank={b.rank}
            className={cn("group block w-full rounded-lg border bg-surface text-left transition-colors hover:border-accent focus:outline-none focus-visible:border-accent",
                          lead ? "border-border-strong p-5" : "border-border p-3.5",
                          b.status === "red" ? "border-l-4 border-l-negative" : "border-l-4 border-l-warning")}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 shrink-0 tabular-nums text-text-muted", lead ? "text-[22px] font-semibold" : "text-[13px] font-semibold")}>{b.rank}</span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{b.scorecard} · {b.tier} · {b.criterion_title}</p>
          <h3 className={cn("font-semibold leading-snug text-text-primary group-hover:text-accent", lead ? "text-[22px]" : "text-[15px]")} data-testid="sm-headline">{b.headline}</h3>
          <p className={cn("text-text-secondary", lead ? "text-[14px]" : "text-[12.5px]")} data-testid="sm-sentence">{b.sentence}</p>
          {b.also.length ? <p className="text-[11px] text-text-muted">Also: {b.also.join("; ")}</p> : null}
          <div className="flex flex-wrap items-end justify-between gap-3 pt-1">
            <Facts b={b} />
            <div className="flex items-center gap-2">
              <Sparkline line={b} w={lead ? 140 : 96} h={lead ? 34 : 24} />
              <Rag status={b.status} />
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function HealthCard({ h, onOpen }: { h: Health; onOpen: (sid: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(h.scorecard_id)} data-testid="sm-health" data-scorecard={h.scorecard_id} data-status={h.overall}
            className="flex w-full flex-col gap-2 rounded-lg border border-border bg-surface p-3 text-left hover:border-accent">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{h.tier} · {h.frequency}</p>
          <p className="truncate text-[14px] font-semibold text-text-primary">{h.name} <span className="font-normal text-text-muted">v{h.version}</span></p>
        </div>
        <Rag status={h.overall} />
      </div>
      <div className="flex flex-wrap gap-1" data-testid="sm-health-criteria">
        {h.criteria.map((c) => (
          <span key={c.criterion} title={`${c.label}: ${c.display}. ${c.sentence}`} data-criterion={c.criterion} data-status={c.status}
                className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10.5px] text-text-secondary">
            <span aria-hidden className={cn("inline-block h-1.5 w-1.5 rounded-full", DOT[c.status])} />{CRITERION_SHORT[c.criterion]}</span>))}
      </div>
      <p className="text-[12px] text-text-secondary" data-testid="sm-health-line">{h.line}</p>
    </button>
  );
}

export function CentredAsk({ onAsk, busy, error }: { onAsk: (q: string) => void; busy: boolean; error?: string }) {
  const [draft, setDraft] = React.useState("");
  const send = (t: string) => { const q = t.trim(); if (q) onAsk(q); };
  return (
    <div className="mx-auto w-full max-w-[46rem] space-y-2" data-testid="sm-ask-box">
      <form className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 shadow-sm focus-within:border-accent"
            onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={1} data-testid="sm-ask" placeholder={ASK_PLACEHOLDER}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); } }}
                  className="min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[14px] text-text-primary focus:outline-none" />
        <MicButton value={draft} onChange={setDraft} size="md" testId="sm-mic" className="mb-1" />
        <button type="submit" disabled={busy || !draft.trim()} data-testid="sm-ask-send"
                className="inline-flex items-center gap-1 rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40"><Send size={14} /> Ask</button>
      </form>
      <div className="flex flex-wrap justify-center gap-1.5">
        {ASK_STARTERS.map((s) => (
          <button key={s.label} type="button" onClick={() => send(s.send)} disabled={busy} data-testid="sm-starter"
                  className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-text-secondary hover:border-accent disabled:opacity-40">{s.label}</button>))}
      </div>
      {error ? <p className="text-center text-[12px] text-negative" role="alert" data-testid="sm-ask-error">{error}</p> : null}
    </div>
  );
}

export function MonitorFront({ onOpen, onAsk, busy, askError, onRegister }: {
  onOpen: (sid: string, criterion?: string) => void; onAsk: (q: string) => void; busy: boolean; askError?: string; onRegister: () => void;
}) {
  const load = useLoad(() => monitor.front(), "monitor-front");
  const f = load.data;
  return (
    <div className="space-y-6" data-testid="sm-front">
      <CentredAsk onAsk={onAsk} busy={busy} error={askError} />
      {load.error ? <p className="text-sm text-negative" role="alert">{load.error}</p> : null}
      {!f && !load.error ? <div className="space-y-3"><Skeleton className="h-20 w-full" /><Skeleton className="h-64 w-full" /></div> : null}
      {f ? (
        <>
          <PlainWords lines={f.plain_words} speak testId="sm-plain-words" source={<span>From {f.sources.join(", ")}</span>} />
          <div className="flex flex-wrap items-end justify-between gap-3 border-b-2 border-text-primary pb-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Scorecards today · {day(f.as_of)} · CBUAE MMSG monitoring criteria</p>
              <h2 className="text-[24px] font-semibold leading-tight text-text-primary" data-testid="sm-headline-top">{frontHeadline(f.breaches.length, f.counts.scorecards, f.counts.red)}</h2>
            </div>
            <button type="button" onClick={onRegister} data-testid="sm-findings-link"
                    className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
              {f.counts.overdue_findings} of {f.counts.open_findings} open findings past due <ArrowRight size={12} /></button>
          </div>
          <section className="grid gap-3 md:grid-cols-3" data-testid="sm-health-row" aria-label="Health per scorecard">
            {f.health.map((h) => <HealthCard key={h.scorecard_id} h={h} onOpen={(sid) => onOpen(sid)} />)}
          </section>
          <Paper breaches={f.breaches} onOpen={onOpen} />
          <section className="grid gap-3 md:grid-cols-2" data-testid="sm-schedule">
            <Card className="space-y-2 p-3">
              <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-text-primary"><CalendarClock size={14} /> Monitoring schedule</h3>
              <table className="w-full text-[12px]">
                <thead className="text-left text-[10px] uppercase tracking-wide text-text-muted"><tr><th className="py-1">Scorecard</th><th>Runs</th><th>Last</th><th>Next</th></tr></thead>
                <tbody>{f.schedule.map((s) => (
                  <tr key={s.scorecard_id} className="border-t border-border" data-testid="sm-schedule-row">
                    <td className="py-1">{f.health.find((h) => h.scorecard_id === s.scorecard_id)?.name ?? s.scorecard_id}</td>
                    <td className="capitalize">{s.frequency}</td><td>{day(s.last_run)}</td><td>{day(s.next_run)}</td></tr>))}</tbody>
              </table>
            </Card>
            <Card className="space-y-1.5 p-3 text-[12px] text-text-secondary">
              <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-text-primary"><Bell size={14} /> Alerts</h3>
              <p>Red breaches on Tier 1 scorecards go to Noor&apos;s brief the day they appear; every run goes to the Model Oversight Committee&apos;s quarterly pack (MMS 3.6.4).</p>
              <p>Limits are the bank&apos;s pre-defined monitoring limits (MMG 2.11.1); the Gini, calibration, PSI, CSI and override limits are the validation engine&apos;s own, so monitoring and validation never disagree.</p>
            </Card>
          </section>
        </>) : null}
    </div>
  );
}

function Paper({ breaches, onOpen }: { breaches: Breach[]; onOpen: (sid: string, criterion?: string) => void }) {
  if (!breaches.length) return <Card className="p-4 text-[13px] text-text-secondary" data-testid="sm-paper-empty">Every scorecard is inside its monitoring limits today.</Card>;
  const { lead, columns } = newspaper(breaches);
  return (
    <section className="space-y-3" data-testid="sm-paper" aria-label="The breaches that matter">
      {lead ? <Story b={lead} lead onOpen={onOpen} /> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {columns.map((col, i) => <div key={i} className="space-y-3">{col.map((b) => <Story key={b.id} b={b} onOpen={onOpen} />)}</div>)}
      </div>
    </section>
  );
}
