"use client";

/**
 * One finished validation: the summary with its verdict, a tab per test group (tests with their stated
 * thresholds and a red / amber / green verdict, interactive Plotly charts, and tables), and the review.
 * Every figure is the API's own; nothing is recomputed here.
 */

import * as React from "react";
import { Info } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type ChartExplain, ChartExplainBody } from "@/components/v5/core/chart-explain";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import {
  CONCLUSION_WORD, STATUS_WORD, SUGGESTED, type ChartData, type Conclusion, type Section, type Status, type TableData, type Test,
  type Validation, fmt, scorecard, useLoad,
} from "@/lib/v5/scorecard";

import { WIDE, browserLayout, chartTitle } from "./chart-layout";
import { scorecardChartExplain } from "./explain";
import { keyCharts } from "./key-charts";
import { friendlyMessage } from "@/lib/v5/errors";

const CHIP: Record<Status, string> = {
  green: "border-positive/40 bg-positive-muted text-positive",
  amber: "border-warning/40 bg-warning-muted text-warning",
  red: "border-negative/40 bg-negative-muted text-negative",
  na: "border-border bg-surface-sunken text-text-muted",
};

export function Rag({ status, testId }: { status: Status; testId?: string }) {
  return (
    <span data-testid={testId ?? "sv-rag"} data-status={status}
          className={cn("inline-flex h-fit shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold", CHIP[status])}>
      <span aria-hidden className={cn("inline-block h-1.5 w-1.5 rounded-full", status === "green" ? "bg-positive" : status === "amber" ? "bg-warning" : status === "red" ? "bg-negative" : "bg-text-muted")} />
      {STATUS_WORD[status]}
    </span>
  );
}

function TestsTable({ section }: { section: Section }) {
  return (
    <div className="overflow-x-auto rounded-md border border-border" data-testid={`sv-tests-${section.id}`}>
      <table className="w-full text-[12px]">
        <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
          <tr><th className="px-3 py-2">Test</th><th className="px-3 py-2">Value</th><th className="px-3 py-2">Stated threshold</th><th className="px-3 py-2">Verdict</th><th className="px-3 py-2">Reading</th></tr>
        </thead>
        <tbody>
          {section.tests.map((t: Test) => (
            <tr key={t.id} data-testid={`sv-test-${t.id}`} data-status={t.status} className="border-t border-border align-top">
              <td className="px-3 py-2 font-medium text-text-primary">{t.label}</td>
              <td className="whitespace-nowrap px-3 py-2 tabular-nums">{fmt(t.value, t.format)}</td>
              <td className="px-3 py-2 text-text-muted">{t.threshold || "—"}</td>
              <td className="px-3 py-2"><Rag status={t.status} /></td>
              <td className="px-3 py-2 text-text-secondary">{t.comment}</td>
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function DataTable({ table }: { table: TableData }) {
  return (
    <div className="space-y-1" data-testid={`sv-table-${table.id}`}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[12px] font-semibold text-text-primary">{table.title}</h4>
        <InfoTip text={table.note} />
      </div>
      <div className="max-h-[360px] overflow-auto rounded-md border border-border">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr>{table.columns.map((c) => <th key={c.key} className={cn("px-3 py-1.5", c.format !== "text" && c.format !== "rag" && "text-right")}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i} className="border-t border-border">
                {table.columns.map((c) => (
                  <td key={c.key} className={cn("px-3 py-1.5", c.format !== "text" && c.format !== "rag" && "text-right tabular-nums")}>
                    {c.format === "rag" ? <Rag status={r[c.key] as Status} /> : fmt(r[c.key], c.format)}</td>))}
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** An (i) beside a heading: the explanation shows on hover or focus, never as loose text on the page. */
export function InfoTip({ text, testId, align = "right", explain }: { text: string; testId?: string; align?: "left" | "right"; explain?: ChartExplain }) {
  if (!text && !explain) return null;
  return (
    <span className="group relative inline-flex shrink-0" data-testid={testId ?? "sv-info"}>
      <button type="button" aria-label={explain ? `About this chart: ${explain.shows}` : text} className="inline-flex size-5 items-center justify-center rounded-full border border-border text-text-muted hover:border-border-strong hover:text-text-secondary focus:outline-none focus-visible:border-accent">
        <Info className="size-3" aria-hidden /></button>
      <span role="tooltip" className={cn("pointer-events-none invisible absolute top-6 z-30 max-w-[80vw]", explain ? "w-96" : "w-72", " rounded-md border border-border bg-surface-raised p-2.5 text-[11px] font-normal normal-case leading-snug tracking-normal text-text-secondary opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100", align === "right" ? "right-0" : "left-0")}>{explain ? <ChartExplainBody explain={explain} hint={text || undefined} /> : text}</span>
    </span>
  );
}

export function Chart({ chart }: { chart: ChartData }) {
  const layout = browserLayout({ data: chart.figure.data, layout: chart.figure.layout });
  return (
    <Card className={cn("flex flex-col gap-1 p-3", WIDE.has(chart.id) && "lg:col-span-2")} data-testid={`sv-chart-card-${chart.id}`}>
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-[13px] font-semibold leading-snug text-text-primary" data-testid="sv-card-title">{chartTitle(chart.figure, chart.title)}</h4>
        <InfoTip text={chart.note} explain={scorecardChartExplain(chart.id, chart.title, chart.figure)} />
      </div>
      <Plot data={chart.figure.data} layout={layout} height={layout.height as number}
            testId={`sv-chart-${chart.id}`} ariaLabel={chart.title} filename={`scorecard-${chart.id}`} />
    </Card>
  );
}

function SectionPanel({ section }: { section: Section }) {
  const [allWoe, setAllWoe] = React.useState(false);
  const woe = section.charts.filter((c) => c.id.startsWith("woe_"));
  const other = section.charts.filter((c) => !c.id.startsWith("woe_"));
  const shown = [...other, ...(allWoe ? woe : woe.slice(0, 2))];
  return (
    <div className="space-y-4" data-testid={`sv-panel-${section.id}`}>
      <TestsTable section={section} />
      <div className="grid gap-3 lg:grid-flow-row-dense lg:grid-cols-2">{shown.map((c) => <Chart key={c.id} chart={c} />)}</div>
      {woe.length > 2 ? (
        <button type="button" onClick={() => setAllWoe((a) => !a)} data-testid="sv-woe-toggle" className="text-[12px] text-accent hover:underline">
          {allWoe ? "Show fewer WoE charts" : `Show all ${woe.length} WoE charts`}</button>) : null}
      <div className="space-y-4">{section.tables.map((t) => <DataTable key={t.id} table={t} />)}</div>
    </div>
  );
}

/** The run's key charts, shown first in the result (PLAN_R10 C3): every chart is the API's own figure with its (i). */
function KeyCharts({ v, ids }: { v: Validation; ids?: string[] }) {
  const charts = keyCharts(v.result, ids);
  if (!charts.length) return null;
  return (
    <div className="space-y-2" data-testid="sv-key-charts" data-count={charts.length}>
      <h4 className="text-[12px] font-semibold text-text-primary">Key charts</h4>
      <div className="grid gap-3 lg:grid-cols-2">{charts.map((c) => <Chart key={c.id} chart={c} />)}</div>
    </div>
  );
}

function Summary({ v, onOpen, charts }: { v: Validation; onOpen: (g: string) => void; charts?: string[] }) {
  const r = v.result;
  return (
    <div className="space-y-4" data-testid="sv-panel-summary">
      <KeyCharts v={v} ids={charts} />
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-[12px]">
          <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr><th className="px-3 py-2">Group</th><th className="px-3 py-2">Test</th><th className="px-3 py-2">Value</th><th className="px-3 py-2">Verdict</th></tr>
          </thead>
          <tbody>
            {r.sections.flatMap((s) => s.tests.map((t) => (
              <tr key={t.id} className="border-t border-border" data-testid={`sv-summary-${t.id}`} data-status={t.status}>
                <td className="px-3 py-1.5"><button type="button" className="text-accent hover:underline" onClick={() => onOpen(s.id)}>{s.title}</button></td>
                <td className="px-3 py-1.5">{t.label}</td><td className="whitespace-nowrap px-3 py-1.5 tabular-nums">{fmt(t.value, t.format)}</td>
                <td className="px-3 py-1.5"><Rag status={t.status} /></td>
              </tr>)))}
          </tbody>
        </table>
      </div>
      {r.findings.length ? (
        <div className="space-y-2" data-testid="sv-findings">
          <h4 className="text-[12px] font-semibold text-text-primary">What needs action</h4>
          {r.findings.map((f) => (
            <div key={f.test} className="flex gap-2 rounded-md border border-border p-2.5 text-[12px]" data-testid="sv-finding" data-status={f.status}>
              <Rag status={f.status} />
              <div><p className="font-medium text-text-primary">{f.label}</p><p className="text-text-secondary">{f.text}</p>
                {f.action ? <p className="mt-0.5 text-text-muted">Action: {f.action}</p> : null}</div>
            </div>))}
        </div>) : <p className="text-[12px] text-positive">Every test is green or not applicable.</p>}
    </div>
  );
}

function ReviewPanel({ v, onSaved }: { v: Validation; onSaved: () => void }) {
  const [editing, setEditing] = React.useState(v.review.status !== "reviewed");
  const [conclusion, setConclusion] = React.useState<Conclusion>(v.review.conclusion || SUGGESTED[v.overall]);
  const [note, setNote] = React.useState(v.review.note);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const save = async () => {
    setBusy(true);
    setError("");
    try { await scorecard.review(v.validation_id, { conclusion, note }); setEditing(false); onSaved(); }
    catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Card className="space-y-3 p-4" data-testid="sv-review">
      <div className="flex items-center gap-2">
        <h3 className="text-[14px] font-semibold text-text-primary">Review</h3>
        <span data-testid="sv-review-status" data-status={v.review.status}
              className={cn("rounded-full border px-2 py-0.5 text-[11px] font-semibold", v.review.status === "reviewed" ? CHIP.green : CHIP.amber)}>
          {v.review.status === "reviewed" ? "Reviewed" : "Pending review"}</span>
      </div>
      {!editing && v.review.status === "reviewed" ? (
        <div className="space-y-1 text-[13px]" data-testid="sv-review-record">
          <p><span className="text-text-muted">Conclusion: </span><strong data-testid="sv-review-conclusion">{CONCLUSION_WORD[v.review.conclusion as Conclusion]}</strong></p>
          {v.review.note ? <p className="text-text-secondary">{v.review.note}</p> : null}
          <p className="text-[11px] text-text-muted">{v.review.reviewer ? `Reviewed by ${v.review.reviewer}` : "Reviewed"}{v.review.at ? ` on ${v.review.at.slice(0, 10)}` : ""}</p>
          <button type="button" onClick={() => setEditing(true)} data-testid="sv-review-edit" className="text-[12px] text-accent hover:underline">Change the review</button>
        </div>) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[12px] text-text-muted" data-testid="sv-review-suggested">
            <span>Suggested: <strong className="text-text-primary">{CONCLUSION_WORD[SUGGESTED[v.overall]]}</strong></span>
            <InfoTip text="The suggestion follows the verdicts. Record your own conclusion; the Word report carries it." />
          </div>
          <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Conclusion">
            {(Object.keys(CONCLUSION_WORD) as Conclusion[]).map((c) => (
              <label key={c} className="inline-flex items-center gap-1.5 text-[13px]">
                <input type="radio" name={`concl-${v.validation_id}`} checked={conclusion === c} onChange={() => setConclusion(c)} data-testid={`sv-review-${c}`} />
                {CONCLUSION_WORD[c]}</label>))}
          </div>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="Your note for the committee" data-testid="sv-review-note"
                    className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none" />
          {error ? <p className="text-[12px] text-negative" role="alert" data-testid="sv-review-error">{error}</p> : null}
          <button type="button" onClick={save} disabled={busy} data-testid="sv-review-save"
                  className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-contrast disabled:opacity-40">{busy ? "Saving…" : "Mark reviewed"}</button>
        </div>)}
    </Card>
  );
}

/** The review of a validation, shown once at the foot of its thread so it stays in reach however long the conversation runs. */
export function ReviewSection({ id, onChanged }: { id: string; onChanged?: () => void }) {
  const [version, setVersion] = React.useState(0);
  const load = useLoad(() => scorecard.validation(id), `review-${id}-${version}`);
  if (!load.data) return null;
  const v = load.data;
  return <ReviewPanel key={`${v.review.status}-${v.review.at ?? ""}`} v={v} onSaved={() => { setVersion((n) => n + 1); onChanged?.(); }} />;
}

export function ValidationView({ id, charts }: { id: string; charts?: string[] }) {
  const load = useLoad(() => scorecard.validation(id), `validation-${id}`);
  // Local state: a thread can show the same validation more than once, and each copy keeps its own tab.
  const [tab, setTab] = React.useState<string>("summary");
  if (load.error) return <p className="text-sm text-negative" role="alert">{load.error}</p>;
  if (!load.data) return <Skeleton className="h-64 w-full" />;
  const v = load.data;
  const r = v.result;
  const s = r.summary;
  const tabs = [{ id: "summary", title: "Summary", status: s.overall }, ...r.sections.map((x) => ({ id: x.id as string, title: x.title, status: x.status }))];
  return (
    <div className="space-y-3" data-testid="sv-validation" data-validation={id} data-overall={s.overall}>
      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Validation result</p>
            <h3 className="text-[16px] font-semibold text-text-primary" data-testid="sv-validation-title">{v.title}</h3>
          </div>
          <div className="flex items-center gap-2" data-testid="sv-overall" data-status={s.overall}>
            <Rag status={s.overall} testId="sv-overall-rag" />
            <span className="text-[12px] text-text-secondary" data-testid="sv-counts">{s.counts.green} green · {s.counts.amber} amber · {s.counts.red} red</span>
          </div>
        </div>
        <div className="grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-4" data-testid="sv-sample">
          <p><span className="text-text-muted">Development </span>{r.sample.development.from} to {r.sample.development.to}: {r.sample.development.n.toLocaleString("en-US")} obs, {r.sample.development.defaults.toLocaleString("en-US")} defaults</p>
          <p><span className="text-text-muted">Monitoring </span>{r.sample.monitoring.from} to {r.sample.monitoring.to}: {r.sample.monitoring.n.toLocaleString("en-US")} obs, {r.sample.monitoring.defaults.toLocaleString("en-US")} defaults</p>
          <p><span className="text-text-muted">As of </span>{r.sample.as_of.period}: {r.sample.as_of.n.toLocaleString("en-US")} obs</p>
          <p><span className="text-text-muted">Outcomes final to </span>{r.sample.last_matured}; segments by {r.sample.segment_by.replace(/_/g, " ")}</p>
        </div>
      </Card>
      <div role="tablist" aria-label="Test groups" className="flex flex-wrap gap-1 border-b border-border">
        {tabs.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} onClick={() => setTab(t.id)} data-testid={`sv-tab-${t.id}`} data-status={t.status}
                  className={cn("flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-[13px]", tab === t.id ? "border-accent font-semibold text-text-primary" : "border-transparent text-text-muted hover:text-text-primary")}>
            {t.title}<span aria-hidden className={cn("inline-block h-2 w-2 rounded-full", t.status === "green" ? "bg-positive" : t.status === "amber" ? "bg-warning" : t.status === "red" ? "bg-negative" : "bg-border")} />
          </button>))}
      </div>
      {tab === "summary" ? <Summary v={v} onOpen={setTab} charts={charts} /> : <SectionPanel section={r.sections.find((x) => x.id === tab)!} />}
    </div>
  );
}
