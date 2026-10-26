"use client";

/**
 * The header of every What-If thread (PLAN_R3 S3-5): key-figure cards and the
 * population mix charts for the thread's population -- its Early Warning
 * cohort, the scope of its current scenario (a sector, a product, a borrower)
 * or the whole book -- at the thread's period.
 *
 * A cohort thread gets the full dashboard: cards, stage donut, EAD by rating
 * (global order) or behaviour score band, the sector or product split, the top
 * warning reasons, the Early Warning bands, and the top 20 owners by EAD, each
 * linking to Borrower 360. Every figure is the API's
 * (GET /threads/{id}/summary), computed from the What-If domain and the Early
 * Warning release; nothing is recomputed here.
 */

import Link from "next/link";
import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type PopulationSummary, asOfLabel, count, pct, sar, whatif } from "@/lib/v5/whatif";

import { BAND_COLOUR, BandBars, GradeBars, ReasonBars, SplitBars, StageDonut } from "./summary-charts";
import { type ChartExplain, ChartInfo } from "@/components/v5/core/chart-explain";
import { bandsExplain, gradeExplain, reasonsExplain, splitExplain, stageExplain } from "./explain";
import { friendlyMessage } from "@/lib/v5/errors";

const th = "px-2 py-1 text-left text-[11px] font-semibold text-text-muted";
const td = "px-2 py-1 text-[12px] tabular-nums text-text-secondary";

function Figure({ label, value, sub, testId, raw }: { label: string; value: string; sub?: string; testId: string; raw: number }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2" data-testid={`${testId}-tile`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className="mt-0.5 text-[17px] font-semibold tabular-nums text-text-primary" data-testid={testId} data-value={raw}>{value}</p>
      {sub ? <p className="text-[11px] text-text-muted">{sub}</p> : null}
    </div>
  );
}

function Panel({ title, note, info, children, className }: { title: string; note?: string; info?: ChartExplain; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0 space-y-1 rounded-md border border-border/70 p-2", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h4 className="flex items-center gap-1.5 text-[12px] font-semibold text-text-primary">{title}{info ? <ChartInfo title={title} explain={info} /> : null}</h4>
        {note ? <span className="text-[11px] text-text-muted">{note}</span> : null}
      </div>
      {children}
    </div>
  );
}

export function SummaryCards({ s, prefix }: { s: PopulationSummary; prefix: string }) {
  const c = s.cards;
  const lab = s.labels;
  const k = (key: string) => `${prefix}-kpi-${key}`;
  // R10 G-TILES: four compact tiles in one row; the other figures sit behind "More figures".
  return (
    <div className="space-y-2" data-testid={`${prefix}-cards`}>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4" data-testid={`${prefix}-tiles`}>
        <Figure label="EAD" value={sar(c.ead)} sub={`${count(c.owners)} ${lab.owners.toLowerCase()} · ${count(c.exposures)} ${lab.exposures.toLowerCase()}`}
                testId={k("ead")} raw={c.ead} />
        <Figure label="ECL" value={sar(c.ecl)} sub={`coverage ${pct(c.coverage_pct, 2)} of EAD`} testId={k("ecl")} raw={c.ecl} />
        <Figure label="Stage 2" value={pct(c.stage2_ead_pct, 1)} sub={`${count(c.stage2_n)} of ${count(c.exposures)} ${lab.exposures.toLowerCase()} · ${pct(c.stage2_ead_pct, 1)} of exposure`}
                testId={k("stage2")} raw={c.stage2_ead_pct} />
        <Figure label={`Warned ${lab.owners.toLowerCase()}`} value={count(c.ews_warned_owners)}
                sub={`${count(c.ews_warned_owners)} of ${count(c.owners)} · ${sar(c.ews_warned_ead)} EAD`} testId={k("warned")} raw={c.ews_warned_owners} />
      </div>
      <details className="text-[11px] text-text-muted" data-testid={`${prefix}-more-figures`}>
        <summary className="cursor-pointer select-none">More figures</summary>
        <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          <span data-testid={k("owners")}>{lab.owners}: <b className="text-text-primary">{count(c.owners)}</b></span>
          <span data-testid={k("exposures")}>{lab.exposures}: <b className="text-text-primary">{count(c.exposures)}</b></span>
          <span data-testid={k("coverage")}>Coverage: <b className="text-text-primary">{pct(c.coverage_pct, 2)}</b></span>
          <span data-testid={k("stage3")}>Stage 3: <b className="text-text-primary">{pct(c.stage3_ead_pct, 1)}</b> of EAD · {count(c.stage3_n)} {lab.exposures.toLowerCase()}</span>
          <span data-testid={k("ews-score")}>Average Early Warning score: <b className="text-text-primary">{c.ews_avg_score.toFixed(1)}</b></span>
          <span data-testid={k("warned-ead")}>Warned EAD: <b className="text-text-primary">{sar(c.ews_warned_ead)}</b> ({pct(c.ews_warned_pct, 1)})</span>
        </p>
      </details>
    </div>
  );
}

export function TopOwners({ s, prefix }: { s: PopulationSummary; prefix: string }) {
  const lab = s.labels;
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full border-collapse" data-testid={`${prefix}-top20`} data-rows={s.top.rows.length}>
        <thead className="sticky top-0 bg-surface"><tr className="border-b border-border">
          <th className={th}>#</th><th className={th}>{lab.owner}</th><th className={th}>{lab.segment}</th>
          <th className={th}>{lab.grade}</th><th className={th}>Stage</th><th className={cn(th, "text-right")}>{lab.exposures}</th>
          <th className={cn(th, "text-right")}>EAD</th><th className={cn(th, "text-right")}>Share of EAD</th>
          <th className={cn(th, "text-right")}>ECL</th><th className={cn(th, "text-right")}>Coverage</th>
          <th className={th}>Early Warning</th></tr></thead>
        <tbody>{s.top.rows.map((r) => (
          <tr key={r.owner_id} className="border-b border-border/50" data-testid={`${prefix}-top20-row`} data-owner={r.owner_id} data-ead={r.ead}>
            <td className={td}>{r.rank}</td>
            <td className={td}>
              <Link href={r.href} className="text-accent hover:underline" data-testid={`${prefix}-b360-${r.owner_id}`}
                    title={`Open ${r.owner_name ?? r.owner_id} in Borrower 360`}>
                {r.owner_name ? <>{r.owner_name} <span className="font-mono text-[11px] text-text-muted">{r.owner_id}</span></> : <span className="font-mono">{r.owner_id}</span>}
              </Link></td>
            <td className={td}>{r.segment}</td><td className={td}>{r.grade}</td><td className={td}>Stage {r.stage}</td>
            <td className={cn(td, "text-right")}>{count(r.exposures)}</td>
            <td className={cn(td, "text-right font-semibold text-text-primary")} data-testid={`${prefix}-top20-ead`}>{sar(r.ead)}</td>
            <td className={cn(td, "text-right")}>{pct(r.share_pct, 1)}</td>
            <td className={cn(td, "text-right")}>{sar(r.ecl)}</td><td className={cn(td, "text-right")}>{pct(r.coverage_pct, 2)}</td>
            <td className={td}><span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: BAND_COLOUR[r.ews_band] ?? "var(--ipm-text-muted)" }} aria-hidden />
              {r.ews_band_label} · {r.ews_score}</span></td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

export function SummaryView({ s }: { s: PopulationSummary }) {
  const cohort = s.kind === "cohort";
  const prefix = cohort ? "whatif-cohort" : "whatif-header";
  const lab = s.labels;
  const file = (what: string) => `whatif-${cohort ? "cohort" : s.kind}-${s.domain}-${s.period}-${what}`;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Panel title="Stage mix" note="EAD by IFRS 9 stage" info={stageExplain(s)}><StageDonut summary={s} testId={`${prefix}-stage-donut`} filename={file("stage-mix")} /></Panel>
        <Panel title={`EAD by ${lab.grade.toLowerCase()}`} note={s.domain === "corporate" ? "global rating order, AAA to D" : "the book's band order, A best"} info={gradeExplain(s)}>
          <GradeBars summary={s} testId={`${prefix}-rating`} filename={file("ead-by-rating")} /></Panel>
        <Panel title={`EAD by ${s.split.label.toLowerCase()}`}
               note={s.split.within ? `all in ${s.split.within}` : `${count(s.split.rows.length)} ${s.split.plural.toLowerCase()}`} info={splitExplain(s)}>
          <SplitBars summary={s} testId={`${prefix}-split`} filename={file(`ead-by-${s.split.label.toLowerCase().replace(/\W+/g, "-")}`)} /></Panel>
      </div>
      <div className={cn("grid gap-3", s.reasons.length ? "xl:grid-cols-[3fr_2fr]" : "")}>
        {s.reasons.length ? (
          <Panel title="Top warning reasons" note={`${lab.owners.toLowerCase()} flagged and their EAD`} info={reasonsExplain(s)}>
            <ReasonBars summary={s} testId={`${prefix}-reasons`} filename={file("warning-reasons")} /></Panel>) : null}
        <Panel title="Early Warning bands" note={`${lab.owners.toLowerCase()} by their worst band, worst first`} info={bandsExplain(s)}>
          <BandBars summary={s} testId={`${prefix}-bands`} filename={file("early-warning-bands")} /></Panel>
      </div>
      {cohort ? (
        <Panel title={`Top ${s.top.n} ${lab.owners.toLowerCase()} by EAD`} note="open one in Borrower 360; Back returns here">
          <TopOwners s={s} prefix={prefix} /></Panel>
      ) : (
        <details className="rounded-md border border-border/70 p-2" data-testid={`${prefix}-top20-details`}>
          <summary className="cursor-pointer px-1 text-[12px] font-semibold text-text-primary">Top {s.top.n} {lab.owners.toLowerCase()} by EAD</summary>
          <div className="mt-2"><TopOwners s={s} prefix={prefix} /></div>
        </details>
      )}
      {cohort && s.reconciliation ? (
        <div className={cn("flex items-center gap-1.5 text-[11px]", s.reconciliation.matches ? "text-text-muted" : "text-negative")} data-testid="whatif-cohort-reconciliation"
           data-matches={s.reconciliation.matches ? "true" : "false"} data-membership-verified={s.membership_verified ? "true" : "false"}>
          <span>{s.reconciliation.matches ? "Reconciled to Early Warning" : "Does not reconcile to Early Warning: "}
            {s.reconciliation.matches ? "" : s.reconciliation.checks.filter((x) => !x.matches).map((x) => `${x.label} ${x.label === "EAD" ? sar(x.whatif) : count(x.whatif)}`
              + ` (Early Warning ${x.label === "EAD" ? sar(x.ews ?? 0) : count(x.ews ?? 0)})`).join(" · ")}</span>
          <InfoPopover title="Reconciliation">
            {s.reconciliation.checks.slice(0, 3).map((x) => `${x.label} ${x.label === "EAD" ? sar(x.whatif) : count(x.whatif)}`).join(" · ")}
            {s.membership_verified ? ". Membership hash verified." : "."}
          </InfoPopover></div>) : null}
    </div>
  );
}

/**
 * The header of a thread; refetched when the thread's population (its scenario's scope) changes.
 * R13 X (J4): the question comes first. The figures are one collapsed "Book at a glance" line (EAD · ECL · Stage 2 · warned);
 * it opens the tiles, and the tiles open the charts.
 */
export function ThreadHeader({ threadId, scopeKey }: { threadId: string; scopeKey: string }) {
  const [s, setS] = React.useState<PopulationSummary | null>(null);
  const [error, setError] = React.useState("");
  const [expanded, setExpanded] = React.useState(false);
  // R10 G-SCROLL: the charts open on request so the conversation is above the fold.
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => {
    let alive = true;
    whatif.threadSummary(threadId)
      .then((x) => { if (alive) { setS(x); setError(""); } })
      .catch((e: unknown) => { if (alive) setError(friendlyMessage(e)); });
    return () => { alive = false; };
  }, [threadId, scopeKey]);
  if (error) return <p className="text-[12px] text-negative" role="alert" data-testid="whatif-header-error">{error}</p>;
  if (!s) return <Skeleton className="h-9 w-full" data-testid="whatif-header-loading" />;
  const lab = s.labels;
  const c = s.cards;
  const title = s.kind === "cohort" ? (s.title.startsWith("Borrower 360") ? s.title : `Early Warning cohort · ${s.title}`) : s.kind === "scope" ? `In scope · ${s.title}` : `${lab.book} book`;
  const glance = s.kind === "cohort" ? "Cohort at a glance" : s.kind === "scope" ? "Scope at a glance" : "Book at a glance";
  return (
    <div className="rounded-lg border border-border bg-surface" data-testid="whatif-header" data-kind={s.kind} data-period={s.period} data-domain={s.domain}
         data-expanded={expanded ? "true" : "false"}>
      <button type="button" onClick={() => setExpanded((x) => !x)} aria-expanded={expanded} data-testid="whatif-glance"
              className="flex w-full min-w-0 flex-wrap items-center gap-x-4 gap-y-0.5 px-3 py-2 text-left text-[12px] hover:bg-surface-hover">
        {/* R16 m (M2): the title and the figures wrap onto two lines rather than squeezing the figures into a narrow
            column (checked at 1440 and 1280 wide). */}
        <span className="shrink-0 font-semibold text-text-primary" data-testid="whatif-header-title" title={title}>{glance}</span>
        <span className="flex min-w-[min(100%,18rem)] flex-[1_1_18rem] flex-wrap gap-x-4 gap-y-0.5 text-text-muted" data-testid="whatif-glance-figures">
          <span>EAD <b className="tabular-nums text-text-primary">{sar(c.ead)}</b></span>
          <span>ECL <b className="tabular-nums text-text-primary">{sar(c.ecl)}</b></span>
          <span>Stage 2 <b className="tabular-nums text-text-primary">{pct(c.stage2_ead_pct, 1)}</b></span>
          <span>Warned <b className="tabular-nums text-text-primary">{count(c.ews_warned_owners)}</b> {lab.owners.toLowerCase()}</span>
          <span className="hidden xl:inline">{lab.book} · {asOfLabel(s.period)}</span>
        </span>
        {expanded ? <ChevronUp size={14} className="ml-auto shrink-0 text-text-muted" /> : <ChevronDown size={14} className="ml-auto shrink-0 text-text-muted" />}
      </button>
      {expanded ? (
        <div className="space-y-3 border-t border-border p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="min-w-0 flex-[1_1_24rem] text-[11px] text-text-muted"><span className="font-semibold text-text-primary">{title}</span> · {lab.book} · as of {asOfLabel(s.period)} · {count(c.owners)} {lab.owners.toLowerCase()},{" "}
              {count(c.exposures)} {lab.exposures.toLowerCase()}{s.kind === "cohort" && s.ruleset ? ` · rule set ${s.ruleset}` : ""} · amounts in SAR</p>
            <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid="whatif-header-toggle"
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover">
              {open ? <><ChevronUp size={12} /> Hide charts</> : <><ChevronDown size={12} /> Show charts</>}</button>
          </div>
          <SummaryCards s={s} prefix={s.kind === "cohort" ? "whatif-cohort" : "whatif-header"} />
          {open ? <SummaryView s={s} /> : null}
        </div>) : null}
    </div>
  );
}
