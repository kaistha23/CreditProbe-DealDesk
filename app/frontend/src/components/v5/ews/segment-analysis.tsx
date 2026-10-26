"use client";

/**
 * R16 m (M2): the segment analysis of an Early Warning card's population -- the card's primary action ("Analyse").
 *
 * Plain words, the headline (warned owners, their EAD, high/critical share, movement on the prior period), the
 * drivers, the EWS rules fired, the top warned names by EAD (each opens the customer, which links to Borrower 360),
 * the ECL and stage effect (ECL if the warnings come true from the P3 ECL impact engine, the EclImpactPanel's), and
 * rule-based actions. "Stress this cohort" is the existing What-If export, kept as an optional step.
 * Every figure is the service's (GET /api/v1/ews/segment-analysis); nothing is recomputed here.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowLeft, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { type DomainId, type SegmentAnalysis, count, ews, pct, sar, signed, useEws } from "@/lib/v5/ews";

import { ExportToWhatIf } from "./parts";
import { analysisKey, change } from "./segment-analysis-model";

const th = "px-2 py-1 text-left text-[11px] font-semibold text-text-muted";
const td = "px-2 py-1 text-[12px] tabular-nums whitespace-nowrap text-text-secondary";
const BAND_TONE: Record<string, string> = {
  critical: "bg-negative-muted text-negative", high: "bg-warning-muted text-warning",
  moderate: "bg-surface-muted text-text-primary", low: "text-text-muted",
};

export function SegmentAnalysisView({ domain, period, segment = "", cls = "", sub = "", dims, onBack, onOpenCustomer, onList }: {
  domain: DomainId; period: string; segment?: string; cls?: string; sub?: string; dims?: Record<string, string>;
  onBack: () => void; onOpenCustomer: (id: string) => void; onList: (cohort: string, extra?: { reason?: string }) => void;
}) {
  const key = [domain, period, segment, cls, sub, JSON.stringify(dims ?? {})].join("|");
  const { data, error, loading } = useEws<SegmentAnalysis>(
    () => ews.segmentAnalysis({ domain, period, segment, classification: cls, subsegment: sub, dims }), key);
  const cardKey = analysisKey({ segment, cls, sub, dims });
  return (
    <div className="space-y-3" data-testid="ews-segment-analysis-view">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={onBack} data-testid="ews-analysis-back">
          <ArrowLeft className="mr-1 size-3.5" aria-hidden /> Back to the cards
        </Button>
      </div>
      {error ? <p className="text-sm text-negative" data-testid="ews-analysis-error">{error}</p>
        : loading || !data ? (
          <div className="space-y-3"><PlainWords lines={[]} loading testId="ews-analysis-plain-words" /><Skeleton className="h-96 w-full" /></div>
        ) : <SegmentAnalysisCard a={data} cardKey={cardKey} onOpenCustomer={onOpenCustomer} onList={onList} />}
    </div>
  );
}

export function SegmentAnalysisCard({ a, cardKey, onOpenCustomer, onList }: {
  a: SegmentAnalysis; cardKey: string; onOpenCustomer: (id: string) => void;
  onList: (cohort: string, extra?: { reason?: string }) => void;
}) {
  const L = a.labels;
  const h = a.headline;
  const m = h.movement;
  return (
    <Card className="space-y-4 p-4" data-testid="ews-segment-analysis" data-key={cardKey}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Segment analysis</p>
        <h2 className="min-w-0 text-base font-semibold text-text-primary" data-testid="ews-analysis-title">{a.name}</h2>
        <span className="text-[11px] text-text-muted">warned {L.owners} · {a.period}{a.prior_period ? ` vs ${a.prior_period}` : ""} · SAR</span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => onList("warned")} data-testid="ews-analysis-open-list">
            <ListChecks className="mr-1 size-3.5" aria-hidden /> All {count(h.customers_warned)} warned {L.owners}
          </Button>
          {/* The What-If cohort thread is optional now: the existing export, relabelled (M2). */}
          <ExportToWhatIf testId={`ews-export-${cardKey}`} label="Stress this cohort" body={a.stress} />
        </span>
      </div>

      <PlainWords lines={a.plain_words} testId="ews-analysis-plain-words"
                  source={<>From {a.sources.relations.join(", ")}, {a.period}</>} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="ews-analysis-headline">
        <Stat label={`Warned ${L.owners}`} value={count(h.customers_warned)} testId="ews-analysis-warned"
              sub={`of ${count(h.customers)} (${pct(h.warned_pct)}) · ${signed(m.customers_warned)} on last ${L.period}`} />
        <Stat label="Warned EAD" value={sar(h.exposure_warned)} testId="ews-analysis-warned-ead"
              sub={`${pct(h.exposure_warned_pct)} of ${sar(h.exposure)} · ${m.exposure_warned == null ? "—" : `${m.exposure_warned >= 0 ? "+" : "−"}${sar(Math.abs(m.exposure_warned))}`}`} />
        <Stat label="High or critical" value={pct(h.exposure_severe_pct)} testId="ews-analysis-severe"
              sub={`${count(h.high_or_critical)} ${L.owners} · ${sar(h.exposure_severe)} · ${m.exposure_severe_pct == null ? "—" : `${signed(m.exposure_severe_pct, 1)} pts`}`} />
        <Stat label="ECL if warnings come true" value={sar(a.ecl.ecl_if_true_total)} testId="ews-analysis-ecl-true" tone="warning"
              sub={`now ${sar(a.ecl.ecl_now)} · +${sar(a.ecl.uplift)}`} />
      </div>
      <Source text={a.sources.headline} testId="ews-analysis-source-headline" />

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Drivers" info="Indicator families behind the warned exposures. A family counts an exposure once; shares are of the warned EAD and warned names, so they overlap and do not add to 100%."
                 source={a.sources.drivers} testId="ews-analysis-drivers">
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-border">
              <th className={th}>Driver</th><th className={cn(th, "text-right")}>{L.owners}</th>
              <th className={cn(th, "text-right")}>vs {a.prior_period || "prior"}</th>
              <th className={cn(th, "text-right")}>EAD</th><th className={cn(th, "text-right")}>Share of warned EAD</th></tr></thead>
            <tbody>{a.drivers.map((d) => (
              <tr key={d.key} className="border-b border-border/50" data-testid={`ews-analysis-driver-${d.key}`}>
                <td className={td}><span className="font-medium text-text-primary">{d.label}</span>
                  {d.layer_label ? <span className="block text-[10px] text-text-muted">{d.layer_label}</span> : null}</td>
                <td className={cn(td, "text-right")}>{count(d.owners)}</td>
                <td className={cn(td, "text-right", (d.change ?? 0) > 0 ? "text-negative" : (d.change ?? 0) < 0 ? "text-positive" : "")}>{change(d.change)}</td>
                <td className={cn(td, "text-right")}>{sar(d.ead)}</td>
                <td className={cn(td, "text-right")}>{pct(d.share_of_warned_ead_pct)}</td>
              </tr>))}</tbody>
          </table>
        </Section>

        <Section title="Rules fired" info="Every Early Warning rule that fired on the warned exposures. Click a rule for its warned names."
                 source={a.sources.rules} testId="ews-analysis-rules">
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-border">
              <th className={th}>Rule</th><th className={cn(th, "text-right")}>Weight</th>
              <th className={cn(th, "text-right")}>{L.owners}</th><th className={cn(th, "text-right")}>Change</th>
              <th className={cn(th, "text-right")}>EAD</th></tr></thead>
            <tbody>{a.rules.map((r) => (
              <tr key={r.id || r.label} className="cursor-pointer border-b border-border/50 hover:bg-surface-muted"
                  onClick={() => onList("warned", { reason: r.label })} data-testid={`ews-analysis-rule-${r.id}`}>
                <td className={td}><span className="font-mono text-[10px] text-text-muted">{r.id}</span>{" "}
                  <span className="text-accent">{r.label}</span></td>
                <td className={cn(td, "text-right")}>{r.weight ?? "—"}</td>
                <td className={cn(td, "text-right")}>{count(r.owners)}</td>
                <td className={cn(td, "text-right")}>{change(r.change)}</td>
                <td className={cn(td, "text-right")}>{sar(r.ead)}</td>
              </tr>))}</tbody>
          </table>
        </Section>
      </div>

      <Section title={`Top ${a.top_names.length} warned ${L.owners} by EAD`} info={`Open one for its Early Warning detail; Borrower 360 opens from there or from the link.`}
               source={a.sources.top_names} testId="ews-analysis-top">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-border">
              <th className={th}>#</th><th className={th}>{L.owner}</th><th className={th}>Band</th>
              <th className={cn(th, "text-right")}>Stage</th><th className={cn(th, "text-right")}>DPD</th>
              <th className={cn(th, "text-right")}>EAD</th><th className={cn(th, "text-right")}>ECL</th>
              <th className={th}>Main reasons</th><th className={th} /></tr></thead>
            <tbody>{a.top_names.map((n) => (
              <tr key={n.customer_id} className="cursor-pointer border-b border-border/50 align-top hover:bg-surface-muted"
                  onClick={() => onOpenCustomer(n.customer_id)} data-testid={`ews-analysis-name-${n.customer_id}`} data-ead={n.exposure}>
                <td className={td}>{n.rank}</td>
                <td className={td}><span className="text-accent">{n.customer_name ?? n.customer_id}</span>
                  {n.customer_name ? <span className="ml-1 font-mono text-[10px] text-text-muted">{n.customer_id}</span> : null}</td>
                <td className={td}><span className={cn("rounded-full px-2 py-0.5 text-[11px] capitalize", BAND_TONE[n.band])}>{n.band}</span></td>
                <td className={cn(td, "text-right")}>{n.stage}</td>
                <td className={cn(td, "text-right")}>{count(n.dpd)}</td>
                <td className={cn(td, "text-right font-semibold text-text-primary")}>{sar(n.exposure)}</td>
                <td className={cn(td, "text-right")}>{sar(n.ecl)}</td>
                <td className={cn(td, "max-w-[22rem] whitespace-normal")}>{n.main_reasons.join("; ")}{n.reasons_count > n.main_reasons.length ? ` +${n.reasons_count - n.main_reasons.length}` : ""}</td>
                <td className={td}>
                  <Link href={n.links.borrower_360} onClick={(e) => e.stopPropagation()} className="text-accent hover:underline"
                        data-testid={`ews-analysis-b360-${n.customer_id}`}>Borrower 360</Link></td>
              </tr>))}</tbody>
          </table>
        </div>
      </Section>

      <Section title="ECL and stage effect" info={a.ecl.method} source={a.sources.ecl} testId="ews-analysis-ecl">
        <div className="grid gap-4 lg:grid-cols-2">
          <table className="w-full border-collapse" data-testid="ews-analysis-stage">
            <thead><tr className="border-b border-border">
              <th className={th}>Stage</th><th className={cn(th, "text-right")}>{L.exposures} (all)</th>
              <th className={cn(th, "text-right")}>EAD (all)</th><th className={cn(th, "text-right")}>ECL (all)</th>
              <th className={cn(th, "text-right")}>EAD of warned {L.owners}</th></tr></thead>
            <tbody>{a.ecl.stage_mix.map((s) => {
              const w = a.ecl.stage_mix_warned.find((x) => x.stage === s.stage);
              return (
                <tr key={s.stage} className="border-b border-border/50">
                  <td className={td}>Stage {s.stage}</td><td className={cn(td, "text-right")}>{count(s.n)}</td>
                  <td className={cn(td, "text-right")}>{sar(s.ead)}</td><td className={cn(td, "text-right")}>{sar(s.ecl)}</td>
                  <td className={cn(td, "text-right")}>{sar(w?.ead ?? 0)}</td>
                </tr>);
            })}
              <tr className="font-semibold"><td className={td}>Total</td><td />
                <td className={cn(td, "text-right")}>{sar(a.ecl.ead_now)}</td><td className={cn(td, "text-right")}>{sar(a.ecl.ecl_now)}</td>
                <td className={cn(td, "text-right")}>{pct(a.ecl.coverage_pct, 2)} coverage</td></tr>
            </tbody>
          </table>
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[12px]" data-testid="ews-analysis-ecl-figures">
            <dt className="text-text-muted">ECL now (all of the scope)</dt><dd className="text-right tabular-nums">{sar(a.ecl.ecl_now)}</dd>
            <dt className="text-text-muted">Flagged names (Critical to Low), performing</dt><dd className="text-right tabular-nums">{count(a.ecl.flagged_names)} · {sar(a.ecl.flagged_ead)}</dd>
            <dt className="text-text-muted">Their current ECL</dt><dd className="text-right tabular-nums">{sar(a.ecl.current_ecl)}</dd>
            <dt className="text-text-muted">Expected ECL if the warnings come true</dt>
            <dd className="text-right font-semibold tabular-nums text-warning" data-testid="ews-analysis-expected">{sar(a.ecl.expected_ecl)} (+{sar(a.ecl.uplift)})</dd>
            <dt className="text-text-muted">Severe case (Critical and High at 90+ DPD)</dt>
            <dd className="text-right font-semibold tabular-nums text-negative">{sar(a.ecl.severe_ecl)} (+{sar(a.ecl.severe_uplift)})</dd>
            <dt className="text-text-muted">ECL of the scope if the warnings come true</dt><dd className="text-right tabular-nums">{sar(a.ecl.ecl_if_true_total)}</dd>
          </dl>
        </div>
      </Section>

      <Section title="Actions" info="Rule-based: each action names the rule that raised it and the role that owns it." testId="ews-analysis-actions">
        <ul className="space-y-2">
          {a.actions.map((x) => (
            <li key={x.key} className="rounded-md border border-border p-2" data-testid={`ews-analysis-action-${x.key}`} title={`Rule: ${x.rule}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold text-text-primary">{x.title}</span>
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-text-secondary">{x.owner_role}</span>
                {x.key === "stress" ? <span className="ml-auto"><ExportToWhatIf testId={`ews-analysis-stress-${cardKey}`} label="Stress this cohort" body={a.stress} /></span> : null}
              </div>
              <p className="text-[12px] text-text-secondary">{x.why}</p>
            </li>))}
        </ul>
      </Section>
    </Card>
  );
}

function Section({ title, info, source, testId, children }: {
  title: string; info?: string; source?: string; testId: string; children: React.ReactNode;
}) {
  return (
    <section className="min-w-0 space-y-1" data-testid={testId}>
      <div className="flex items-center gap-2">
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        {info ? <InfoPopover title={title}>{info}</InfoPopover> : null}
      </div>
      {children}
      {source ? <Source text={source} testId={`${testId}-source`} /> : null}
    </section>
  );
}

function Source({ text, testId }: { text: string; testId: string }) {
  return <p className="text-[10px] text-text-muted" data-testid={testId}>Source: {text}</p>;
}

function Stat({ label, value, sub, tone, testId }: { label: string; value: string; sub?: string; tone?: "warning"; testId: string }) {
  return (
    <div className="rounded-md border border-border p-3" data-testid={testId}>
      <p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("text-lg font-bold tabular-nums", tone === "warning" ? "text-warning" : "text-text-primary")}>{value}</p>
      {sub ? <p className="text-[11px] tabular-nums text-text-muted">{sub}</p> : null}
    </div>
  );
}

/** The full analysis on the Early Warning screen, by address (Back returns to where the reader came from). */
export function analysisHref(a: Pick<SegmentAnalysis, "domain_id" | "period" | "scope">): string {
  const p = new URLSearchParams({ domain: a.domain_id, period: a.period });
  if (a.scope.dims && Object.keys(a.scope.dims).length) return `/early-warning?${p.toString()}`;
  if (a.scope.segment) p.set("segment", a.scope.segment);
  if (a.scope.classification) p.set("cls", a.scope.classification);
  if (a.scope.subsegment) p.set("sub", a.scope.subsegment);
  p.set("analysis", "1");
  return `/early-warning?${p.toString()}`;
}

/**
 * R16 m (M2/M4): the compact segment analysis a What-If cohort thread opens with, before "Describe a scenario".
 * Same service figures as the Early Warning analysis (the What-If service attaches them to the cohort block).
 */
export function SegmentAnalysisCompact({ a }: { a: SegmentAnalysis }) {
  const L = a.labels;
  const h = a.headline;
  const ews360 = (id: string) => `/early-warning?${new URLSearchParams({ domain: a.domain_id, period: a.period, customer: id }).toString()}`;
  return (
    <div className="space-y-3 rounded-md border border-border/70 p-3" data-testid="whatif-cohort-analysis" data-key={a.key}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[12px] font-semibold text-text-primary">Segment analysis · {a.name}</p>
        <span className="text-[11px] text-text-muted">warned {L.owners} · {a.period}{a.prior_period ? ` vs ${a.prior_period}` : ""}</span>
        <Link href={analysisHref(a)} className="ml-auto text-[12px] text-accent hover:underline" data-testid="whatif-cohort-analysis-full">
          Full analysis in Early Warning</Link>
      </div>
      <PlainWords lines={a.plain_words} testId="whatif-cohort-plain-words" />
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label={`Warned ${L.owners}`} value={count(h.customers_warned)} testId="whatif-cohort-analysis-warned"
              sub={`of ${count(h.customers)} · ${signed(h.movement.customers_warned)} on last ${L.period}`} />
        <Stat label="Warned EAD" value={sar(h.exposure_warned)} testId="whatif-cohort-analysis-ead" sub={`${pct(h.exposure_warned_pct)} of ${sar(h.exposure)}`} />
        <Stat label="High or critical" value={pct(h.exposure_severe_pct)} testId="whatif-cohort-analysis-severe"
              sub={`${count(h.high_or_critical)} ${L.owners} · ${sar(h.exposure_severe)}`} />
        <Stat label="ECL if warnings come true" value={sar(a.ecl.ecl_if_true_total)} tone="warning" testId="whatif-cohort-analysis-ecl"
              sub={`now ${sar(a.ecl.ecl_now)} · +${sar(a.ecl.uplift)}`} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="min-w-0 text-[12px]" data-testid="whatif-cohort-analysis-drivers">
          <p className="mb-1 font-semibold text-text-primary">Drivers and rules fired</p>
          <ul className="space-y-0.5 text-text-secondary">
            {a.drivers.map((d) => (
              <li key={d.key}><span className="text-text-primary">{d.label}</span>: {count(d.owners)} {L.owners} ({change(d.change)}), {sar(d.ead)}</li>))}
          </ul>
          <p className="mt-1 text-[11px] text-text-muted">{a.rules.map((r) => `${r.id} ${count(r.owners)}`).join(" · ")}</p>
        </div>
        <div className="min-w-0 text-[12px]" data-testid="whatif-cohort-analysis-top">
          <p className="mb-1 font-semibold text-text-primary">Top {a.top_names.length} warned {L.owners} by EAD</p>
          <ul className="space-y-0.5">
            {a.top_names.map((n) => (
              <li key={n.customer_id} className="flex flex-wrap gap-x-2">
                <Link href={ews360(n.customer_id)} className="text-accent hover:underline">{n.customer_name ?? n.customer_id}</Link>
                <span className="tabular-nums text-text-secondary">{sar(n.exposure)} · {n.band} · Stage {n.stage} · {count(n.dpd)} DPD</span>
                <Link href={n.links.borrower_360} className="text-[11px] text-text-muted hover:underline">Borrower 360</Link>
              </li>))}
          </ul>
        </div>
      </div>
      {a.actions.length ? (
        <ul className="flex flex-wrap gap-1.5 text-[11px]" data-testid="whatif-cohort-analysis-actions">
          {a.actions.map((x) => (
            <li key={x.key} className="rounded-full border border-border px-2 py-0.5 text-text-secondary" title={`${x.why} Rule: ${x.rule}`}>
              {x.title} <span className="text-text-muted">· {x.owner_role}</span></li>))}
        </ul>) : null}
      <Source text={`${a.sources.headline} ECL: ${a.ecl.engine}.`} testId="whatif-cohort-analysis-source" />
    </div>
  );
}
