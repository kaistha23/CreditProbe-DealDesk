"use client";

/**
 * R14 r (K2, K4): the issue view. A brief line about a regulatory or data issue lands here, never on the raw Data
 * Domains catalogue: what the issue is (headline), in plain words, the rule in one sentence, bank vs requirement (both
 * rates), the tables by vintage and collateral type, the shortfall bridge by driver (sums to the total), concentration,
 * impact, what to do (owner, date), the breaching exposures with Borrower 360 links, what the data cannot tell us,
 * and the source as one small link (lineage, N5). Every number comes from backend/regulatory/issues (deterministic).
 */

import * as React from "react";
import Link from "next/link";
import { BookOpen, Loader2 } from "lucide-react";

import { Chip, Section, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { Plot } from "@/components/v5/ews/plot";
import { TONE } from "@/lib/plotly-theme";
import { cn } from "@/lib/utils";

import { cell, dueText } from "./issue-format";
import { issuesApi, type Bridge, type Concentration, type Fig, type IssueTable, type IssueView as View } from "./issues-api";
import { BorrowerNameLink } from "@/components/v5/ui/borrower-360-link";
import { PlainWords } from "@/components/v5/ui/plain-words";

const SEV_TONE: Record<string, "negative" | "warning" | "neutral"> = { critical: "negative", high: "negative", medium: "warning", low: "neutral" };

export function useIssue(id: string): { data: View | null; error: string; busy: boolean } {
  const [state, set] = React.useState<{ id: string; data: View | null; error: string }>({ id: "", data: null, error: "" });
  React.useEffect(() => {
    let live = true;
    issuesApi.get(id).then((data) => live && set({ id, data, error: "" }))
      .catch((e: unknown) => live && set({ id, data: null, error: e instanceof Error ? e.message : "That did not load." }));
    return () => { live = false; };
  }, [id]);
  const busy = state.id !== id;
  return { data: busy ? null : state.data, error: busy ? "" : state.error, busy };
}

export function IssueView({ issueId, onOpenIssue }: {
  issueId: string; onOpenIssue?: (id: string) => void;
}) {
  const { data, error, busy } = useIssue(issueId);
  if (busy) {
    return <p className="flex items-center gap-2 py-10 text-[13px] text-text-muted" data-testid="issue-loading">
      <Loader2 size={14} className="animate-spin" />Reading the facilities behind the issue…</p>;
  }
  if (error || !data) {
    return <p role="alert" className="rounded-md border border-negative/30 bg-negative-muted px-3 py-2 text-[13px] text-negative"
              data-testid="issue-error">{error || "That issue did not load."}</p>;
  }
  const v = data;
  const open = (href: string, issue?: string) => (issue && onOpenIssue ? onOpenIssue(issue) : undefined);
  return (
    <article className="space-y-4" data-testid="issue-view" data-issue={v.id} data-kind={v.kind}>
      <header className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-text-muted">
          <span>{v.module}</span><span aria-hidden>·</span>
          <span>{v.rule.article}</span><span aria-hidden>·</span><span>{v.period}</span>
          <Chip tone={SEV_TONE[v.severity] ?? "neutral"} testId="issue-severity">{v.severity}</Chip>
        </div>
        <h1 className="text-[20px] font-semibold leading-7 text-text-primary">{v.title}</h1>
        <p className="max-w-[920px] text-[14px] leading-6 text-text-primary" data-testid="issue-headline">{v.headline}</p>
      </header>

      <PlainWords lines={v.plain_words} speak testId="issue-plain-words" />

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-4 max-[1180px]:grid-cols-1">
        <RuleCard v={v} />
        {v.comparison ? <Comparison c={v.comparison} /> : null}
      </div>

      {v.tables.length ? (
        <div className="grid gap-4">
          {v.tables.map((t) => <TableCard key={t.id} t={t} />)}
        </div>) : null}

      {v.bridge && v.bridge.steps.length ? <BridgeCard b={v.bridge} onOpen={(i) => open("", i)} /> : null}

      <div className={cn("grid gap-4", v.concentration && v.impact.length ? "min-[1180px]:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]" : "")}>
        {v.concentration ? <ConcentrationCard c={v.concentration} /> : null}
        {v.impact.length ? <ImpactCard figs={v.impact} /> : null}
      </div>

      <Section title="What to do" testId="issue-actions">
        <ol className="space-y-2">
          {v.actions.map((a) => (
            <li key={a.n} className="grid grid-cols-[24px_minmax(0,1fr)_auto] items-start gap-2 border-b border-border/60 pb-2 last:border-0 last:pb-0">
              <span className="mt-0.5 inline-flex size-5 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-accent-contrast">{a.n}</span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-text-primary">{a.action}</p>
                <p className="text-[12px] text-text-secondary">{a.why}
                  {a.link ? (/issue=/.test(a.link.href) ? <> <button type="button" className="text-accent hover:underline"
                                       onClick={() => { const m = /issue=([^&]+)/.exec(a.link!.href); if (m) open("", decodeURIComponent(m[1])); }}>
                    {a.link.label} →</button></> : <> <Link href={a.link.href} className="text-accent hover:underline">{a.link.label} →</Link></>) : null}</p>
              </div>
              <div className="text-right text-[12px] leading-5">
                <p className="text-text-primary">{a.owner}</p>
                <p className="tabular-nums text-text-muted">Due {dueText(a.due)}</p>
              </div>
            </li>))}
        </ol>
      </Section>

      {v.exposures && v.exposures.rows.length ? <ExposuresCard t={v.exposures} /> : null}

      <footer className="grid gap-3 rounded-lg border border-border bg-surface-sunken/40 px-4 py-3 text-[12px] min-[1180px]:grid-cols-[minmax(0,1fr)_auto]"
              data-testid="issue-footer">
        {v.cannot_tell.length ? (
          <div>
            <p className="mb-1 font-semibold text-text-secondary">What this data cannot tell us</p>
            <ul className="list-disc space-y-0.5 pl-4 text-text-secondary" data-testid="issue-cannot-tell">
              {v.cannot_tell.map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          </div>) : <div />}
        {v.source ? (
          <Link href={v.source.href} className="self-end whitespace-nowrap text-[11px] text-text-muted hover:text-accent hover:underline"
                data-testid="issue-source">{v.source.label}</Link>) : null}
      </footer>
    </article>
  );
}

function RuleCard({ v }: { v: View }) {
  return (
    <Section title="The rule" testId="issue-rule"
             action={v.rule.href ? <Link href={v.rule.href} className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
               <BookOpen size={13} />Read {v.rule.article.replace("CBUAE CRM ", "")}</Link> : undefined}>
      <p className="text-[13px] leading-5 text-text-primary">{v.rule.text}</p>
      {v.rule.detail ? <p className="mt-2 text-[12px] leading-5 text-text-secondary">{v.rule.detail}</p> : null}
    </Section>
  );
}

function Comparison({ c }: { c: NonNullable<View["comparison"]> }) {
  const pctBar = c.bank.unit === "%" && c.required.unit === "%" && c.bank.value !== null && c.required.value !== null;
  const max = pctBar ? Math.max(100, c.bank.value!, c.required.value!) : 0;
  return (
    <Section title="Bank vs requirement" testId="issue-comparison">
      <div className="grid grid-cols-2 gap-3">
        <BigFig f={c.bank} tone="negative" testId="issue-bank-rate" />
        <BigFig f={c.required} testId="issue-required-rate" />
      </div>
      {pctBar ? (
        <div className="mt-3 space-y-1.5" aria-hidden>
          {[c.bank, c.required].map((f, i) => (
            <div key={i} className="h-2 overflow-hidden rounded-full bg-surface-sunken">
              <div className={cn("h-full rounded-full", i === 0 ? "bg-negative" : "bg-text-muted")}
                   style={{ width: `${Math.max(1, (100 * (f.value ?? 0)) / max)}%` }} />
            </div>))}
        </div>) : null}
      <p className="mt-3 text-[13px] leading-5 text-text-primary" data-testid="issue-comparison-sentence">{c.sentence}</p>
      {c.model ? <p className="mt-1 text-[12px] text-text-secondary">{c.model.label}: <span className="tabular-nums">{c.model.display}</span></p> : null}
      {c.figures.length ? (
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
          {c.figures.map((f) => <div key={f.label} className="flex gap-1.5"><dt className="text-text-muted">{f.label}</dt>
            <dd className="font-medium tabular-nums text-text-primary">{f.display}</dd></div>)}
        </dl>) : null}
    </Section>
  );
}

function BigFig({ f, tone, testId }: { f: Fig; tone?: "negative"; testId: string }) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">{f.label}</p>
      <p className={cn("text-[26px] font-semibold tabular-nums leading-8", tone === "negative" ? "text-negative" : "text-text-primary")}>{f.display}</p>
    </div>
  );
}

function TableCard({ t }: { t: IssueTable }) {
  return (
    <Section title={t.title} testId={`issue-table-${t.id}`} info={t.note || undefined}>
      <div className="overflow-x-auto">
        <table className={tableCls}>
          <thead><tr>{t.columns.map((c) => <th key={c.key} className={cn(thCls, "whitespace-nowrap", c.unit !== "text" && "text-right")}>{c.label}</th>)}</tr></thead>
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={i}>{t.columns.map((c) => <td key={c.key} className={cn(tdCls, c.unit !== "text" && "text-right")}>{cell(r[c.key], c.unit)}</td>)}</tr>))}
            {t.total ? (
              <tr className="font-semibold">{t.columns.map((c) => <td key={c.key} className={cn(tdCls, "border-b-0", c.unit !== "text" && "text-right")}>{cell(t.total![c.key], c.unit)}</td>)}</tr>) : null}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

/** A chart label on up to three short lines (no rotated ticks). */
function wrap(label: string, width = 16): string {
  const out: string[] = [];
  let line = "";
  for (const w of label.split(" ")) {
    if ((line + " " + w).trim().length > width && line) { out.push(line); line = w; } else line = (line + " " + w).trim();
  }
  if (line) out.push(line);
  return out.slice(0, 3).join("<br>") + (out.length > 3 ? "…" : "");
}

function BridgeCard({ b, onOpen }: { b: Bridge; onOpen: (issue: string) => void }) {
  const steps = b.steps;
  const shown = steps.filter((s) => Math.abs(s.value) > 0.005);
  return (
    <Section title={b.title} testId="issue-bridge" info={b.method}>
      <div className="grid gap-4 min-[1180px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Plot testId="issue-bridge-chart" ariaLabel={b.title} height={280} filename="issue-bridge"
              data={[{ type: "waterfall", orientation: "v", measure: [...shown.map(() => "relative"), "total"],
                       x: [...shown.map((s) => wrap(s.label)), "Total"], y: [...shown.map((s) => s.value), b.total],
                       text: [...shown.map((s) => s.display), b.total_display], textposition: "outside", cliponaxis: false,
                       connector: { line: { color: TONE.muted } }, increasing: { marker: { color: TONE.negative } },
                       decreasing: { marker: { color: TONE.positive } }, totals: { marker: { color: TONE.accent } },
                       hovertemplate: "%{x}: %{text}<extra></extra>" }]}
              layout={{ showlegend: false, margin: { l: 10, r: 10, t: 24, b: 10 },
                        xaxis: { automargin: true, tickangle: 0, tickfont: { size: 10 } }, yaxis: { title: { text: b.unit === "SAR mn" ? "SAR m" : b.unit } } }} />
        <ul className="space-y-2" data-testid="issue-bridge-steps">
          {steps.map((s) => (
            <li key={s.key} className={cn("rounded-md border border-border px-3 py-2", !s.value && "opacity-60")} data-step={s.key}>
              <div className="flex items-baseline gap-2">
                <span className="text-[13px] font-medium text-text-primary">{s.label}</span>
                <span className="ml-auto whitespace-nowrap text-[13px] font-semibold tabular-nums">{s.display}</span>
                <span className="w-12 text-right text-[12px] tabular-nums text-text-muted">{s.share_pct === null ? "" : `${s.share_pct.toFixed(0)}%`}</span>
              </div>
              <p className="mt-0.5 text-[12px] leading-5 text-text-secondary">{s.explain}
                {s.facilities ? <span className="text-text-muted"> {s.facilities.toLocaleString()} facilit{s.facilities === 1 ? "y" : "ies"}.</span> : null}
                {s.link && s.value ? <> <button type="button" onClick={() => onOpen(s.link!.issue)} className="text-accent hover:underline">
                  Open {s.link.issue.replace("crm:", "")} →</button></> : null}
              </p>
            </li>))}
          <li className="flex items-baseline gap-2 px-3 text-[13px] font-semibold">
            <span>Total</span><span className="ml-auto tabular-nums">{b.total_display}</span><span className="w-12" />
          </li>
        </ul>
      </div>
    </Section>
  );
}

function ConcentrationCard({ c }: { c: Concentration }) {
  return (
    <Section title="Concentration" testId="issue-concentration">
      <p className="text-[13px] text-text-primary">
        The 10 largest of {c.borrowers.toLocaleString()} borrowers carry{" "}
        <span className="font-semibold tabular-nums">{c.top10_share_pct === null ? "–" : `${c.top10_share_pct.toFixed(0)}%`}</span>{" "}
        of the {c.total_display} {c.label.toLowerCase()}.</p>
      <ol className="mt-2 grid gap-x-6 gap-y-1 text-[12px] min-[1360px]:grid-cols-2">
        {c.top.slice(0, 6).map((t, i) => (
          <li key={t.borrower_id} className="flex min-w-0 items-baseline gap-2">
            <span className="w-4 shrink-0 text-right tabular-nums text-text-muted">{i + 1}</span>
            <BorrowerNameLink customerId={t.borrower_id} name={t.name} from="regulatory" className="truncate !text-accent" />
            <span className="ml-auto whitespace-nowrap tabular-nums">{t.display}</span>
          </li>))}
      </ol>
      <div className="mt-3 grid gap-3 text-[12px] min-[900px]:grid-cols-3">
        {([["Sector", c.by_sector], ["Branch", c.by_branch], ["Relationship manager", c.by_rm]] as const).map(([lab, xs]) => (
          <div key={lab} className="min-w-0">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">{lab}</p>
            <ul className="space-y-0.5">
              {xs.slice(0, 3).map((x) => (
                <li key={x.name} className="flex min-w-0 gap-2"><span className="truncate" title={x.name}>{x.name}</span>
                  <span className="ml-auto whitespace-nowrap tabular-nums text-text-secondary">{x.share_pct === null ? "" : `${x.share_pct.toFixed(0)}%`}</span></li>))}
            </ul>
          </div>))}
      </div>
    </Section>
  );
}

function ImpactCard({ figs }: { figs: Fig[] }) {
  return (
    <Section title="Impact" testId="issue-impact">
      <div className="grid grid-cols-2 gap-2">
        {figs.map((f) => (
          <div key={f.label} className="min-w-0 rounded-md border border-border bg-surface px-3 py-2" title={f.source?.method}>
            <p className="truncate text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted" title={f.label}>{f.label}</p>
            <p className="text-[18px] font-semibold tabular-nums">{f.display}</p>
          </div>))}
      </div>
    </Section>
  );
}

function ExposuresCard({ t }: { t: IssueTable }) {
  const [all, setAll] = React.useState(false);
  const rows = all ? t.rows : t.rows.slice(0, 10);
  return (
    <Section title={t.title} testId="issue-exposures" info={t.note || undefined}
             action={t.rows.length > 10 ? <button type="button" onClick={() => setAll((x) => !x)} className="text-[12px] text-accent hover:underline"
                                                  data-testid="issue-exposures-more">{all ? "Show 10" : `Show all ${t.rows.length}`}</button> : undefined}>
      <div className="overflow-x-auto">
        <table className={tableCls}>
          <thead><tr>{t.columns.map((c) => <th key={c.key} className={cn(thCls, "whitespace-nowrap", c.unit !== "text" && "text-right")}>{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{t.columns.map((c) => (
                <td key={c.key} className={cn(tdCls, c.unit !== "text" && "text-right", c.key === "name" && "max-w-[220px] truncate",
                                         c.key === "detail" && "max-w-[260px] truncate")} title={c.key === "detail" ? String(r[c.key] ?? "") : undefined}>
                  {c.key === "name" && r.borrower_id ? (
                    <BorrowerNameLink customerId={String(r.borrower_id)} name={String(r.name)} from="regulatory"
                                      className="!text-accent" />) : cell(r[c.key], c.unit)}
                </td>))}</tr>))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
