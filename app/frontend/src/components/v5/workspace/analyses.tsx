"use client";

/**
 * Analyses (PLAN_R3 S3-2): a single saved question with its answer, from the Cockpit or What-If. Reopen it, then
 * Refresh it against any period of its dataset (the latest by default): the before and after side by side, figure by
 * figure and row by row. The refresh is computed by the Workspace from the books or the What-If engine.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowUpRight, BarChart3, Loader2, RefreshCw } from "lucide-react";

import { hbarFigure } from "@/components/answer/bar-figure";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plot } from "@/components/v5/ews/plot";
import { ShareButton } from "@/components/v5/mail/share";
import { AddToReportButton, type BuiltSection } from "@/components/v5/playbook/add-to-report";
import { TONE } from "@/lib/plotly-theme";
import { cn } from "@/lib/utils";
import { day, formatValue, useWs, when, ws, type Unit } from "@/lib/v5/workspace";
import { DOMAIN_LABEL, signedValue, ws3, type Col, type Refresh, type Result, type ResultTable } from "@/lib/v5/workspace-r3";

import { Empty, ErrorBox, LinkChips, Loading, PageTop, Prose, SectionTitle, Who } from "./parts";
import { friendlyMessage } from "@/lib/v5/errors";
import { boldParts } from "@/lib/v5/queries";
import { edition } from "@/lib/navigation";

/** R10 Q2: the answer line, its key figures in bold. */
function Headline({ text, className, testId }: { text: string; className?: string; testId?: string }) {
  return (
    <p className={cn("text-text-primary", className)} data-testid={testId}>
      {boldParts(text).map((p, i) => (p.bold ? <strong key={i} className="font-semibold">{p.text}</strong> : <React.Fragment key={i}>{p.text}</React.Fragment>))}
    </p>
  );
}

const ORIGIN: Record<string, string> = { cockpit: "Cockpit", whatif: "What-If", workspace: "Workspace", dealdesk: "Deal Desk" };
const DD = edition() === "dealdesk";
const ABOUT = DD
  ? "Each analysis is a saved Deal Desk result: a structure optimisation, a stress run, a proposal check or an answer from a deal's thread. The answer first, then the chart and table behind it, the method and the Trace. Refresh one against any period to see the before and after."
  : "Each analysis is a saved question with its answer, from the Cockpit or What-If: the answer first, then the chart and table behind it, the method and the Trace. Refresh one against any period to see the before and after.";
const EMPTY = DD ? "No saved analyses yet. Use Save as analysis on a Deal Desk result." : "No saved analyses yet. Use Save as analysis on a Cockpit answer or a What-If result.";

function fmt(v: unknown, unit: Col["unit"]): string {
  return formatValue(v, (unit === "num" ? "int" : unit) as Unit);
}

export function AnalysisList() {
  const list = useWs(() => ws.analyses(), "analyses");
  return (
    <div className="space-y-5" data-testid="ws-analyses">
      <PageTop title="Analyses"
               about={ABOUT} />
      {list.error ? <ErrorBox error={list.error} /> : !list.data ? <Loading /> : list.data.analyses.length === 0 ? <Empty>{EMPTY}</Empty> : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.analyses.map((a0) => {
            const a = a0 as typeof a0 & { question?: string; origin?: string; book?: string | null; refresh_count?: number; headline?: string };
            return (
              <Card key={a.id} className="p-0" data-testid={`ws-analysis-${a.id}`}>
                <Link href={`/analyses/${a.id}`} className="flex gap-3 p-4 transition-colors hover:bg-surface-hover" data-testid={`ws-analysis-open-${a.id}`}>
                  <BarChart3 className="mt-0.5 size-4 shrink-0 text-text-muted" aria-hidden />
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 flex-1 text-[15px] font-semibold text-text-primary">{a.title}</span>
                      {a.origin ? <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-secondary">{ORIGIN[a.origin] ?? a.origin}</span> : null}
                    </span>
                    <span className="block line-clamp-2 text-sm" data-testid={`ws-analysis-headline-${a.id}`}>
                      {a.headline ? <Headline text={a.headline} className="text-sm" /> : <span className="text-text-secondary">{a.description}</span>}
                    </span>
                    <span className="block text-xs text-text-muted">
                      {a.book ? `${DOMAIN_LABEL[a.book] ?? a.book} · ` : ""}{a.period} · {a.owner ? `saved by ${a.owner.name}` : ""} · {day(a.created_at)}
                      {a.refresh_count ? ` · refreshed ${a.refresh_count}×` : ""}
                    </span>
                  </span>
                </Link>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ResultTableView({ table, testId }: { table: ResultTable; testId: string }) {
  const numeric = (u: string) => u !== "text";
  return (
    <Card className="overflow-x-auto p-0" data-testid={testId}>
      <Table>
        <TableHeader>
          <TableRow>
            {table.columns.map((c) => <TableHead key={c.key} className={cn(numeric(c.unit) && "text-right")}>{c.label}{c.unit === "sar_mn" ? " (SAR m)" : ""}</TableHead>)}
          </TableRow>
        </TableHeader>
        <TableBody>
          {table.rows.map((r, i) => (
            <TableRow key={i}>
              {table.columns.map((c) => <TableCell key={c.key} className={cn("tabular-nums", numeric(c.unit) && "whitespace-nowrap text-right")}>{fmt(r[c.key], c.unit)}</TableCell>)}
            </TableRow>
          ))}
          {table.totals ? (
            <TableRow className="font-semibold">
              {table.columns.map((c) => <TableCell key={c.key} className={cn("tabular-nums", numeric(c.unit) && "text-right")}>{fmt(table.totals?.[c.key], c.unit)}</TableCell>)}
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
    </Card>
  );
}

/** Horizontal bars for the saved chart spec: one bar per row of the table, the spec's measure. */
function Bars({ result, testId }: { result: Pick<Result, "table" | "chart">; testId: string }) {
  const t = result.table;
  const c = result.chart;
  if (!t || !c) return null;
  const unit = (t.columns.find((x) => x.key === c.y)?.unit ?? "int") as Col["unit"];
  const pts = t.rows.map((r) => ({ label: String(r[c.x]), value: Number(r[c.y] ?? 0) }));
  const shown = pts.slice(0, 20);
  // A negative bar (a fall, a release) keeps its own colour, as the list did.
  const fig = hbarFigure({ labels: shown.map((p) => p.label), values: shown.map((p) => p.value),
                           text: shown.map((p) => fmt(p.value, unit)),
                           color: shown.map((p) => (p.value < 0 ? TONE.positive : TONE.accent)) });
  return (
    <Card className="space-y-2 p-4" data-testid={testId}>
      <p className="text-sm font-semibold text-text-primary">{c.title}</p>
      <Plot data={fig.data} layout={fig.layout} height={fig.height} ariaLabel={c.title} filename="analysis-chart" testId={`plot-${testId}`} />
    </Card>
  );
}

function Compare({ r }: { r: Refresh }) {
  const c = r.comparison;
  const num = c.columns.filter((x) => x.unit !== "text");
  return (
    <div className="space-y-4" data-testid="ws-analysis-compare" data-before={c.before_period} data-after={c.after_period}>
      <SectionTitle>Before and after · {c.before_period} → {c.after_period}</SectionTitle>
      <Card className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Figure</TableHead>
              <TableHead className="text-right">Before · {c.before_period}</TableHead>
              <TableHead className="text-right">After · {c.after_period}</TableHead>
              <TableHead className="text-right">Change</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {c.figures.map((f) => (
              <TableRow key={f.key} data-testid={`ws-compare-fig-${f.key}`} data-before-value={f.before ?? ""} data-after-value={f.after ?? ""}>
                <TableCell>{f.label}</TableCell>
                <TableCell className="text-right tabular-nums">{fmt(f.before, f.unit)}</TableCell>
                <TableCell className="text-right tabular-nums">{fmt(f.after, f.unit)}</TableCell>
                <TableCell className={cn("text-right tabular-nums", (f.change ?? 0) > 0 ? "text-negative" : (f.change ?? 0) < 0 ? "text-positive" : "")}>
                  {signedValue(f.change, f.unit)}{f.change_pct !== null && f.change_pct !== undefined ? ` (${f.change_pct > 0 ? "+" : ""}${f.change_pct.toFixed(1)}%)` : ""}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {c.rows.length ? (
        <Card className="overflow-x-auto p-0" data-testid="ws-compare-rows">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{c.columns[0]?.label}</TableHead>
                {num.map((col) => (
                  <React.Fragment key={col.key}>
                    <TableHead className="text-right">{col.label} {c.before_period}</TableHead>
                    <TableHead className="text-right">{col.label} {c.after_period}</TableHead>
                    <TableHead className="text-right">Δ</TableHead>
                  </React.Fragment>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {c.rows.map((row) => (
                <TableRow key={row.key} data-testid={`ws-compare-row-${row.key.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                  <TableCell className="font-medium">{row.key}</TableCell>
                  {num.map((col) => {
                    const cell = row.cells[col.key];
                    return (
                      <React.Fragment key={col.key}>
                        <TableCell className="text-right tabular-nums">{fmt(cell?.before, col.unit)}</TableCell>
                        <TableCell className="text-right tabular-nums" data-after-value={cell?.after ?? ""}>{fmt(cell?.after, col.unit)}</TableCell>
                        <TableCell className="text-right tabular-nums text-text-secondary">{signedValue(cell?.change, col.unit)}</TableCell>
                      </React.Fragment>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : null}
      <div className="grid gap-3 lg:grid-cols-2">
        <Bars result={r.before} testId="ws-compare-chart-before" />
        <Bars result={r.after} testId="ws-compare-chart-after" />
      </div>
      <p className="text-[11px] text-text-muted">Recomputed from {r.after.source}. SAR million.</p>
    </div>
  );
}

function RefreshPanel({ id, savedPeriod, onDone }: { id: string; savedPeriod: string | null; onDone: () => void }) {
  const periods = useWs(() => ws3.periods(id), `periods|${id}`);
  const [period, setPeriod] = React.useState<string>("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<Refresh | null>(null);
  if (periods.error) return <ErrorBox error={periods.error} />;
  if (!periods.data) return <Loading what="Loading periods…" />;
  const p = periods.data;
  if (!p.refreshable) {
    return <Card className="p-4 text-sm text-text-secondary" data-testid="ws-analysis-refresh-unavailable">{p.reason || "This analysis cannot be refreshed here."}</Card>;
  }
  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await ws3.refresh(id, period || null));
      onDone();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4" data-testid="ws-analysis-refresh">
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Dataset</p>
          <p className="text-sm text-text-primary" data-testid="ws-analysis-dataset">{p.datasets.map((d) => d.label).join(", ")}</p>
        </div>
        <label className="text-xs text-text-secondary">
          <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Period</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="ws-analysis-period"
                  className="mt-0.5 rounded-md border border-border bg-surface px-2 py-1.5 text-sm">
            <option value="">Latest ({p.latest})</option>
            {[...p.periods].reverse().map((x) => <option key={x} value={x}>{x}{x === savedPeriod ? " (saved)" : ""}</option>)}
          </select>
        </label>
        <Button size="sm" onClick={() => void run()} disabled={busy} data-testid="ws-analysis-refresh-run">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />} Refresh
        </Button>
        <InfoPopover title="Refresh">Saved at {savedPeriod}. Refresh recomputes it from the data for the period you choose.</InfoPopover>
      </Card>
      {error ? <ErrorBox error={error} /> : null}
      {result ? <Compare r={result} /> : null}
    </section>
  );
}

/** The one chart that answers the question (Plotly, house style): the saved spec's measure by its dimension. */
function AnswerChart({ table, chart }: { table: ResultTable | null; chart: Result["chart"] }) {
  if (!table || !chart) return null;
  const unit = (table.columns.find((x) => x.key === chart.y)?.unit ?? "int") as Col["unit"];
  const rows = table.rows.slice(0, 20);
  const x = rows.map((r) => String(r[chart.x]));
  const y = rows.map((r) => Number(r[chart.y] ?? 0));
  const label = table.columns.find((c) => c.key === chart.y)?.label ?? chart.y;
  return (
    <Card className="space-y-1 p-3" data-testid="ws-analysis-chart">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-text-primary">{chart.title}</p>
        <InfoPopover title="About this chart" align="right">{label}{unit === "sar_mn" ? " in SAR million" : ""} by {table.columns.find((c) => c.key === chart.x)?.label.toLowerCase() ?? chart.x}{table.rows.length > 20 ? `; the first 20 of ${table.rows.length} rows` : ""}. The table beside it has every figure.</InfoPopover>
      </div>
      <Plot data={[{ type: "bar", x, y, marker: { color: y.map((v) => (v < 0 ? "#2f7d5b" : "#8a6d3b")) },
                     hovertemplate: `%{x}: %{y:,.1f}${unit === "pct" ? "%" : ""}<extra></extra>` }]}
            layout={{ margin: { t: 10, l: 60, r: 10, b: 90 }, yaxis: { title: { text: unit === "sar_mn" ? `${label} (SAR m)` : label } } }}
            height={280} ariaLabel={chart.title} testId="ws-analysis-plot" filename="analysis" />
    </Card>
  );
}

export function AnalysisDetail({ id }: { id: string }) {
  const [reload, setReload] = React.useState(0);
  const a = useWs(() => ws3.analysis(id), `analysis|${id}|${reload}`, `analysis|${id}`);
  const back = { href: "/analyses", label: "Analyses" };
  if (a.error) return <div className="space-y-4"><PageTop title="Analysis" back={back} /><ErrorBox error={a.error} /></div>;
  if (!a.data) return <div className="space-y-4"><PageTop title="Analysis" back={back} /><Loading /></div>;
  const d = a.data;
  const ans = d.answer ?? {};
  const table: ResultTable | null = ans.table ?? null;
  const object = { type: "analysis" as const, id: d.id, label: `Analysis: ${d.title}`, href: `/analyses/${d.id}`,
                   summary: (ans.narrative ?? d.description).slice(0, 300), meta: { book: d.book, period: d.period } };
  return (
    <div className="space-y-5" data-testid={`ws-analysis-detail-${d.id}`}>
      <PageTop eyebrow={`Analysis · ${ORIGIN[d.origin] ?? "Saved"}`} title={d.title} back={back}
               actions={<>
                 <ShareButton object={object} testId="ws-analysis-share" />
                 <AddToReportButton source={object} testId="ws-analysis-add-report" defaultTitle={d.title}
                                    build={async () => (await ws3.analysisSection(d.id)).section as unknown as BuiltSection} />
               </>} />
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-secondary">
        {d.book ? <span>{DOMAIN_LABEL[d.book] ?? d.book}</span> : null}
        {d.period ? <span>Period {d.period}</span> : null}
        {d.owner ? <span>Saved by <Who person={d.owner} /></span> : null}
        <span>{when(d.created_at)}</span>
        {d.origin_link?.href ? (
          <Link href={d.origin_link.href} className="inline-flex items-center gap-1 text-accent hover:underline" data-testid="ws-analysis-origin">
            {d.origin_link.label || "Open the source"} <ArrowUpRight className="size-3" aria-hidden />
          </Link>) : null}
        {d.investigation_id ? <Link className="text-accent hover:underline" href={`/investigations/${d.investigation_id}`}>Investigation</Link> : null}
        {d.project_id ? <Link className="text-accent hover:underline" href={`/projects/${d.project_id}`}>Project</Link> : null}
      </div>
      {/* R10 Q2 (item 17): the answer to the question first, then the chart and table that answer it, then method and Trace. */}
      <Card className="space-y-2 p-4" data-testid="ws-analysis-answer">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Answer · {ans.period ?? d.period}</p>
        {d.headline ? <Headline text={d.headline} className="text-[17px] leading-snug" testId="ws-analysis-headline" /> : null}
        {ans.narrative && !d.headline ? (
          <div className="text-sm text-text-secondary" data-testid="ws-analysis-narrative"><Prose text={ans.narrative} /></div>) : null}
      </Card>
      {table || ans.chart ? (
        <div className="grid gap-3 xl:grid-cols-[2fr_3fr]" data-testid="ws-analysis-evidence">
          <AnswerChart table={table} chart={ans.chart ?? null} />
          {table ? <ResultTableView table={table} testId="ws-analysis-table" /> : null}
        </div>) : null}
      {ans.tables && (ans.baseline ? ans.tables : ans.tables.slice(1)).length ? (
        <details className="rounded-md border border-border p-3" data-testid="ws-analysis-cockpit-tables">
          <summary className="cursor-pointer text-sm text-text-secondary">{ans.baseline ? (DD ? "As published" : "As the Cockpit published it") : "More tables from the answer"}</summary>
          <div className="mt-2 space-y-2">
            {(ans.baseline ? ans.tables : ans.tables.slice(1)).map((t, i) => <ResultTableView key={i} table={t} testId={`ws-analysis-cockpit-table-${i}`} />)}
          </div>
        </details>) : null}
      <details className="rounded-md border border-border p-3 text-sm" data-testid="ws-analysis-method">
        <summary className="cursor-pointer text-text-secondary">Method and Trace</summary>
        <div className="mt-2 space-y-1 text-[13px] text-text-secondary">
          {d.method ? <p data-testid="ws-analysis-method-text">{d.method}</p> : null}
          {ans.narrative && d.headline ? <div data-testid="ws-analysis-narrative"><span className="font-medium text-text-primary">Summary as saved. </span>{ans.narrative}</div> : null}
          {d.notes ? <p>{d.notes}</p> : null}
          <p>Source <span className="font-mono text-[12px]">{ans.source ?? d.source}</span>{ans.period ?? d.period ? ` · period ${ans.period ?? d.period}` : ""}.</p>
          {ans.steps?.length ? <ol className="list-decimal pl-5" data-testid="ws-analysis-steps">{ans.steps.map((x, i) => <li key={i}>{String(x)}</li>)}</ol> : null}
          {ans.recompute_note ? <p>{ans.recompute_note}</p> : null}
          {d.origin_link?.href ? <p>Trace: <Link href={d.origin_link.href} className="text-accent hover:underline">{d.origin_link.label || "open the source"}</Link></p> : null}
        </div>
      </details>

      <RefreshPanel id={d.id} savedPeriod={d.period} onDone={() => setReload((n) => n + 1)} />

      {d.refreshes?.length ? (
        <section data-testid="ws-analysis-history">
          <SectionTitle>Refreshed</SectionTitle>
          <ul className="space-y-1 text-xs text-text-secondary">
            {[...d.refreshes].reverse().slice(0, 8).map((r, i) => <li key={i}>Against {r.period} · {when(r.at)} · {r.by}</li>)}
          </ul>
        </section>) : null}
      {d.links.length ? (
        <section>
          <SectionTitle>Open in the modules</SectionTitle>
          <LinkChips links={d.links} />
        </section>) : null}
    </div>
  );
}
