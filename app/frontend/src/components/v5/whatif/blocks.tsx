"use client";

/**
 * What an answer in a What-If thread is made of. Every figure is the API's
 * own number (SAR million in, formatted here); nothing is recomputed.
 */

import Link from "next/link";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { cn } from "@/lib/utils";
import {
  type Answer, type Bar, type Block, type Labels, type Result, type ScenarioSetBlock, count, pct, reportHref, sar,
  scenarioMemoHref, signed,
} from "@/lib/v5/whatif";

import { CompareChart, DriverMix, RatingChart, ScenarioWeightsChart, SegmentChart, WaterfallChart } from "./charts";
import { PolicyNote } from "@/components/v5/policy/policy-note";
import { ConvoBlockView, EvidenceInfo } from "@/components/v5/convo/blocks";
import { AnswerMarkdown } from "@/components/v5/thread/markdown";
import { AnswerFrame } from "@/components/answer";
import type { ConvoAnswer } from "@/lib/v5/convo";
import { orderRatingRows } from "@/lib/v5/ratings";
import { Info, Play } from "lucide-react";
import { RegimeStrip } from "@/components/v5/scenarios/regime-strip";
import { SegmentAnalysisCompact } from "@/components/v5/ews/segment-analysis";
import type { SegmentAnalysis } from "@/lib/v5/ews";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { type ContextBlock, type ContextTrendRow, contextHeading, contextTiles, trendCell } from "./context";

type Ask = (text: string) => void;

// ---------------------------------------------------------------- words

export function Markdown({ text, className, headline = false }: { text: string; className?: string; headline?: boolean }) {
  // The shared answer renderer's prose (PLAN_R12 N2): real tables from pipe tables, lists, headings; long decimals tidied.
  return <AnswerMarkdown text={text} className={className} headline={headline} />;
}

export function LegacyMarkdown({ text, className }: { text: string; className?: string }) {
  const paras = text.split(/\n{2,}/);
  return (
    <div className={cn("space-y-2 text-[13px] leading-relaxed text-text-secondary", className)}>
      {paras.map((p, i) => {
        const lines = p.split("\n");
        if (lines.every((l) => /^\s*[-*] /.test(l))) {
          return <ul key={i} className="ml-5 list-disc space-y-0.5">{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-*] /, ""))}</li>)}</ul>;
        }
        return <p key={i}>{inline(p)}</p>;
      })}
    </div>
  );
}

function inline(s: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\*(.+?)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    out.push(m[1] ? <strong key={k++} className="font-semibold text-text-primary">{m[1]}</strong> : <em key={k++}>{m[2]}</em>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

const pp = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`;
const delta = (v: number) => `${v >= 0 ? "+" : "−"}${sar(Math.abs(v)).replace("SAR ", "SAR ")}`;

function Tile({ label, value, sub, tone, testId }: { label: string; value: string; sub?: string; tone?: "up" | "down" | "plain"; testId?: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2" data-testid={testId ? `${testId}-tile` : undefined}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("mt-0.5 text-[18px] font-semibold tabular-nums",
                       tone === "up" ? "text-negative" : tone === "down" ? "text-positive" : "text-text-primary")}
         data-testid={testId}>{value}</p>
      {sub ? <p className="text-[11px] text-text-muted">{sub}</p> : null}
    </div>
  );
}

function Section({ title, children, testId, aside }: { title: string; children: React.ReactNode; testId?: string; aside?: React.ReactNode }) {
  return (
    <section className="space-y-2" data-testid={testId}>
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-text-muted">{title}</h4>
        {aside}
      </div>
      {children}
    </section>
  );
}

const th = "px-2 py-1 text-left text-[11px] font-semibold text-text-muted";
const td = "px-2 py-1 text-[12px] tabular-nums text-text-secondary";

// ---------------------------------------------------------------- the result

export function KeyCards({ result }: { result: Result }) {
  const c = result.cards;
  const lab = result.labels;
  const s2 = (c.stage_after["2"] ?? 0) - (c.stage_before["2"] ?? 0);
  const s3 = (c.stage_after["3"] ?? 0) - (c.stage_before["3"] ?? 0);
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7" data-testid="whatif-cards">
      <Tile label="Reported ECL" value={sar(c.reported_ecl)} sub={`${result.population.label}`} testId="whatif-kpi-reported" />
      <Tile label="Baseline ECL" value={sar(c.start_ecl)} testId="whatif-kpi-baseline"
            sub={Math.abs(c.model_error) > 1e-9 ? `${result.method_name} start, ${pp(c.model_error_pct)} vs reported` : "= reported (Delta)"} />
      <Tile label="Scenario ECL" value={sar(c.scenario_ecl)} testId="whatif-kpi-ecl" tone={c.change > 0 ? "up" : c.change < 0 ? "down" : "plain"} />
      <Tile label="Change" value={delta(c.change)} sub={pp(c.change_pct)} testId="whatif-kpi-change" tone={c.change > 0 ? "up" : c.change < 0 ? "down" : "plain"} />
      <Tile label="Stage moves" value={`${signed(s2)} / ${signed(s3)}`} testId="whatif-kpi-stages"
            sub={`Stage 2 / Stage 3 ${lab.exposures.toLowerCase()} (1→2 ${count(c.moves["1->2"])}, 2→3 ${count(c.moves["2->3"])})`} />
      <Tile label="Coverage" value={pct(c.coverage_after, 2)} sub={`from ${pct(c.coverage_before, 2)}`} testId="whatif-kpi-coverage" />
      <Tile label="Capital (illustrative)" value={pct(c.capital_cet1_after_pct, 2)} testId="whatif-kpi-capital"
            sub={`CET1 from ${pct(c.capital_cet1_before_pct, 1)}; impact ${sar(c.capital_impact)}`} />
    </div>
  );
}

export function WaterfallTable({ bars, result }: { bars: Bar[]; result?: Result }) {
  return (
    <table className="w-full border-collapse" data-testid="whatif-waterfall-table">
      <thead><tr className="border-b border-border"><th className={th}>Step</th><th className={cn(th, "text-right")}>SAR million</th>
        <th className={cn(th, "text-right")}>Running ECL</th></tr></thead>
      <tbody>
        {(() => {
          const runningAt = bars.reduce<number[]>((acc, b) => [...acc, b.kind === "total" ? b.value : (acc[acc.length - 1] ?? 0) + b.value], []);
          return bars.map((b, i) => {
            const running = runningAt[i];
            return (
              <tr key={b.key} className={cn("border-b border-border/50", b.kind === "total" && "font-semibold")}
                  data-testid={`whatif-bar-${b.key}`}>
                <td className={td}>{i === 0 ? "1. " : `${i + 1}. `}{b.label}{b.kind === "driver" && !b.active ? <span className="text-text-muted"> (not in this scenario)</span> : null}</td>
                <td className={cn(td, "text-right")}>{b.kind === "total" ? b.value.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })
                  : `${b.value >= 0 ? "+" : "−"}${Math.abs(b.value).toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}`}</td>
                <td className={cn(td, "text-right")}>{running.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}</td>
              </tr>
            );
          });
        })()}
      </tbody>
      {result ? <tfoot><tr><td colSpan={3} className="px-2 pt-1 text-[11px] text-text-muted" data-testid="whatif-reconciles">
        <span className="inline-flex items-center gap-1" title={`Start + drivers − scenario = ${result.reconciliation.difference.toExponential(1)} (SAR million). Drivers are exact Shapley values.`}>
          <Info size={11} /> {result.reconciliation.reconciles ? "Reconciles" : "Difference"}</span></td></tr></tfoot> : null}
    </table>
  );
}

function SegmentTable({ result }: { result: Result }) {
  return (
    <table className="w-full border-collapse" data-testid="whatif-segment-table">
      <thead><tr className="border-b border-border"><th className={th}>{result.labels.segment}</th>
        <th className={cn(th, "text-right")}>EAD</th><th className={cn(th, "text-right")}>ECL before</th>
        <th className={cn(th, "text-right")}>ECL after</th><th className={cn(th, "text-right")}>Change</th></tr></thead>
      <tbody>{result.by_segment.map((r) => (
        <tr key={r.segment} className="border-b border-border/50">
          <td className={td}>{r.segment}</td><td className={cn(td, "text-right")}>{sar(r.ead_after)}</td>
          <td className={cn(td, "text-right")}>{sar(r.ecl_before)}</td><td className={cn(td, "text-right")}>{sar(r.ecl_after)}</td>
          <td className={cn(td, "text-right", r.change > 0 ? "text-negative" : "")}>{delta(r.change)}</td></tr>))}</tbody>
    </table>
  );
}

function RatingTable({ result }: { result: Result }) {
  return (
    <table className="w-full border-collapse" data-testid="whatif-rating-table">
      <thead><tr className="border-b border-border"><th className={th}>{result.labels.grade}</th>
        <th className={cn(th, "text-right")}>Masterscale PD</th><th className={cn(th, "text-right")}>EAD before</th>
        <th className={cn(th, "text-right")}>EAD after</th><th className={cn(th, "text-right")}>ECL before</th>
        <th className={cn(th, "text-right")}>ECL after</th></tr></thead>
      <tbody>{orderRatingRows(result.by_rating, "grade").map((r) => (
        <tr key={r.grade} className="border-b border-border/50" data-testid={`whatif-rating-row-${r.grade}`}>
          <td className={td}>{r.grade}</td><td className={cn(td, "text-right")}>{r.pd_masterscale_pct === null ? "—" : pct(r.pd_masterscale_pct, 2)}</td>
          <td className={cn(td, "text-right")}>{sar(r.ead_before)}</td><td className={cn(td, "text-right")}>{sar(r.ead_after)}</td>
          <td className={cn(td, "text-right")}>{sar(r.ecl_before)}</td><td className={cn(td, "text-right")}>{sar(r.ecl_after)}</td></tr>))}</tbody>
    </table>
  );
}

function Migration({ result }: { result: Result }) {
  const [view, setView] = React.useState<"counts" | "ead">("counts");
  const m = view === "counts" ? result.migration.counts : result.migration.ead;
  const fmt = (v: number) => (view === "counts" ? count(v) : sar(v));
  const rowTotal = (i: number) => m[i].reduce((s, v) => s + v, 0);
  return (
    <div data-testid="whatif-migration">
      <div className="mb-1 inline-flex rounded border border-border p-0.5 text-[11px]">
        {(["counts", "ead"] as const).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)} aria-pressed={view === v} data-testid={`whatif-migration-${v}`}
                  className={cn("rounded px-2 py-0.5", view === v ? "bg-accent text-accent-contrast" : "text-text-secondary")}>
            {v === "counts" ? `Count of ${result.labels.exposures.toLowerCase()}` : "EAD"}</button>))}
      </div>
      <table className="w-full border-collapse">
        <thead><tr className="border-b border-border"><th className={th}>From \ to</th>
          {result.migration.stages.map((s) => <th key={s} className={cn(th, "text-right")}>Stage {s}</th>)}
          <th className={cn(th, "text-right")}>Total</th></tr></thead>
        <tbody>{result.migration.stages.map((s, i) => (
          <tr key={s} className="border-b border-border/50"><td className={td}>Stage {s}</td>
            {m[i].map((v, j) => <td key={j} className={cn(td, "text-right", i !== j && v > 0 && "font-semibold text-negative")}>{fmt(v)}</td>)}
            <td className={cn(td, "text-right")}>{fmt(rowTotal(i))}</td></tr>))}</tbody>
      </table>
    </div>
  );
}

function Movers({ result }: { result: Result }) {
  const lab = result.labels;
  return (
    <div className="max-h-80 overflow-auto" data-testid="whatif-movers">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-surface"><tr className="border-b border-border"><th className={th}>{lab.exposure}</th>
          <th className={th}>{lab.owner}</th><th className={th}>{lab.segment}</th><th className={th}>{lab.grade}</th>
          <th className={th}>Stage</th><th className={cn(th, "text-right")}>EAD</th><th className={cn(th, "text-right")}>ECL before</th>
          <th className={cn(th, "text-right")}>ECL after</th><th className={cn(th, "text-right")}>Change</th></tr></thead>
        <tbody>{result.top_movers.map((r) => (
          <tr key={r.exposure_id} className="border-b border-border/50">
            <td className={cn(td, "font-mono")}>{r.exposure_id}</td>
            <td className={td}><Link className="text-accent hover:underline" href={`/borrower-360?domain=${result.domain}&id=${r.owner_id}`}>{r.owner_name ?? r.owner_id}</Link></td>
            <td className={td}>{r.segment}</td><td className={td}>{r.grade_before}{r.grade_after !== r.grade_before ? ` → ${r.grade_after}` : ""}</td>
            <td className={td}>{r.stage_before}{r.stage_after !== r.stage_before ? ` → ${r.stage_after}` : ""}</td>
            <td className={cn(td, "text-right")}>{sar(r.ead)}</td><td className={cn(td, "text-right")}>{sar(r.ecl_before)}</td>
            <td className={cn(td, "text-right")}>{sar(r.ecl_after)}</td><td className={cn(td, "text-right text-negative")}>{delta(r.change)}</td></tr>))}</tbody>
      </table>
      {!result.top_movers.length ? <p className="p-2 text-[12px] text-text-muted">No {lab.exposure.toLowerCase()} moved.</p> : null}
    </div>
  );
}

const DETAIL_TABS = ["Sector", "Rating", "Stage migration", "Top movers", "Macro scenarios"] as const;

/** The policy question a result raises (PLAN_R3 S1-2): Stage 2 when exposures moved into it, else ECL; and the driver. */
function whatifPolicyQuestion(result: Result): { measure: string; driver?: string } {
  const s2 = (result.cards.stage_ead_after?.["2"] ?? 0) - (result.cards.stage_ead_before?.["2"] ?? 0);
  const d = (result.drivers ?? []).join(" ").toLowerCase();
  const driver = /rating|notch|downgrade/.test(d) ? "downgrade" : /gdp|oil|macro|mev|unemploy|rate/.test(d) ? "macro" : undefined;
  return { measure: s2 > 0 ? "stage2" : "ecl", driver };
}

export function ResultBlock({ result, index }: { result: Result; index: number }) {
  const [tab, setTab] = React.useState<(typeof DETAIL_TABS)[number]>("Sector");
  const lab = result.labels;
  const tabLabel = (t: string) => (t === "Sector" ? lab.segment : t === "Rating" ? lab.grade : t);
  return (
    <Card className="space-y-4 p-4" data-testid="whatif-result" data-run={result.run_id} data-method={result.method}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-text-primary">Result · {result.method_name}</h3>
        <p className="text-[11px] text-text-muted">{lab.book} · as of {result.period} · {result.population.label} · weights base {Math.round(result.scenario_weights.base * 100)}% /
          upturn {Math.round(result.scenario_weights.upturn * 100)}% / downturn {Math.round(result.scenario_weights.downturn * 100)}% · run {result.run_id}</p>
      </div>
      <KeyCards result={result} />
      <PolicyNote book={result.domain} {...whatifPolicyQuestion(result)} period={result.period} prefix="Policy behind the movement:"
                  testId="whatif-policy-note" className="rounded-md border border-border px-3 py-2" />
      <Section title="ECL decomposition" testId="whatif-waterfall" aside={<span className="w-40"><DriverMix bars={result.waterfall} /></span>}>
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <WaterfallChart bars={result.waterfall} testId={`whatif-waterfall-chart-${index}`} />
          <WaterfallTable bars={result.waterfall} result={result} />
        </div>
      </Section>
      <Section title="Detail" testId="whatif-detail">
        <div className="flex flex-wrap gap-1" role="tablist">
          {DETAIL_TABS.map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                    data-testid={`whatif-tab-${t.toLowerCase().replace(/\s+/g, "-")}`}
                    className={cn("rounded-md border px-2.5 py-1 text-[12px]", tab === t ? "border-accent bg-accent-muted text-text-primary" : "border-border text-text-secondary hover:bg-surface-hover")}>
              {tabLabel(t)}</button>))}
        </div>
        {tab === "Sector" ? <div className="grid gap-4 xl:grid-cols-2"><SegmentChart rows={result.by_segment} labels={lab} testId={`whatif-segment-chart-${index}`} /><div className="max-h-80 overflow-auto"><SegmentTable result={result} /></div></div> : null}
        {tab === "Rating" ? <div className="space-y-2"><RatingChart rows={result.by_rating} labels={lab} testId={`whatif-rating-chart-${index}`} /><RatingTable result={result} /></div> : null}
        {tab === "Stage migration" ? <Migration result={result} /> : null}
        {tab === "Top movers" ? <Movers result={result} /> : null}
        {tab === "Macro scenarios" ? <ScenarioWeightsChart result={result} testId={`whatif-scenarios-chart-${index}`} /> : null}
      </Section>
    </Card>
  );
}

// ---------------------------------------------------------------- the other blocks

export function BlockView({ block, index, onAsk, threadId, busy, lead = false }: { block: Block; index: number; onAsk: Ask; threadId: string; busy: boolean; lead?: boolean }) {
  switch (block.type) {
    case "text":
      // PLAN_R12 N2: the answer's first text block leads with its headline sentence.
      return <Markdown text={block.markdown} headline={lead} />;
    case "understood":
      return (
        <div className="rounded-md border border-border bg-surface-hover/40 px-3 py-2" data-testid="whatif-understood">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            {block.kind === "stack" ? "Added to the scenario" : block.kind === "intensify" ? "Scaled scenario" : block.kind === "library" ? "Scenario definition" : "What I understood"}
            {block.method ? ` · ${block.method}` : ""}</p>
          <ul className="mt-1 list-disc pl-5 text-[13px] text-text-primary">
            {block.steps.map((s, i) => <li key={i} data-testid="whatif-understood-step">{s.restatement}</li>)}</ul>
          <p className="mt-1 text-[11px] text-text-muted">Population: {block.population}.</p>
          {block.assumptions.length ? <span title={block.assumptions.join(" ")} className="mt-1 inline-flex text-text-muted" data-testid="whatif-understood-info"><Info size={11} /></span> : null}
          {block.unread.length ? <p className="mt-1 text-[11px] text-warning">Not read: {block.unread.join(" ")}</p> : null}
        </div>
      );
    case "question":
      return (
        <div className="space-y-2 rounded-md border border-accent/40 bg-accent-muted/30 px-3 py-2" data-testid={`whatif-question-${block.key}`}>
          <p className="text-[13px] font-medium text-text-primary">{block.text}</p>
          <div className="flex flex-wrap gap-2">
            {block.options.map((o) => (
              <button key={o.label} type="button" disabled={busy} onClick={() => onAsk(o.send)}
                      data-testid={`whatif-option-${o.label.toLowerCase().replace(/\W+/g, "-")}`}
                      className="max-w-xs rounded-md border border-border bg-surface px-3 py-1.5 text-left text-[12px] hover:border-accent disabled:opacity-50">
                <span className="font-semibold text-text-primary">{o.label}</span>
                {o.detail ? <span className="block text-[11px] text-text-muted">{o.detail}</span> : null}
              </button>))}
          </div>
        </div>
      );
    case "result":
      return <ResultBlock result={block.result} index={index} />;
    case "commentary":
      return (
        <Card className="space-y-1 p-4" data-testid="whatif-commentary">
          <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Commentary
            <span title={block.source === "model" ? "Every figure is checked against the result." : "Every figure comes from the run."}
                  className="inline-flex text-text-muted"><Info size={11} /></span></p>
          <Markdown text={block.text} />
        </Card>
      );
    case "likelihood":
      return (
        <Card className="space-y-2 p-4" data-testid="whatif-likelihood">
          <div className="flex flex-wrap items-baseline gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Likelihood</p>
            {block.note ? <InfoPopover title="Likelihood">{block.note}</InfoPopover> : null}
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold",
                                block.level >= 3 ? "bg-negative-muted text-negative" : block.level === 2 ? "bg-warning-muted text-warning" : "bg-positive-muted text-positive")}
                  data-testid="whatif-likelihood-label">{block.label}</span>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-[12px] text-text-secondary">
            {block.items.map((it, i) => <li key={i}>{it.text}</li>)}</ul>
          {block.history ? <p className="text-[11px] text-text-muted">History: {block.history}.</p> : null}
        </Card>
      );
    case "comparison":
      return (
        <Card className="space-y-3 p-4" data-testid="whatif-comparison">
          <h3 className="text-[14px] font-semibold text-text-primary">Delta method and XGBoost, side by side</h3>
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-border"><th className={th}></th><th className={cn(th, "text-right")}>Delta method</th>
              <th className={cn(th, "text-right")}>XGBoost</th><th className={cn(th, "text-right")}>Difference</th></tr></thead>
            <tbody>{block.rows.map((r) => (
              <tr key={r.label} className="border-b border-border/50"><td className={td}>{r.label}</td>
                <td className={cn(td, "text-right")} data-testid={`whatif-compare-delta-${r.label.toLowerCase().replace(/\W+/g, "-")}`}>{r.kind === "pct" ? pct(r.delta, 2) : sar(r.delta)}</td>
                <td className={cn(td, "text-right")}>{r.kind === "pct" ? pct(r.xgboost, 2) : sar(r.xgboost)}</td>
                <td className={cn(td, "text-right")}>{r.kind === "pct" ? `${(r.xgboost - r.delta).toFixed(2)}pp` : delta(r.xgboost - r.delta)}</td></tr>))}</tbody>
          </table>
          {block.drivers.length ? <CompareChart drivers={block.drivers} testId={`whatif-compare-chart-${index}`} /> : null}
          <details className="text-[12px]"><summary className="cursor-pointer text-text-muted">Both results in full</summary>
            <div className="mt-2 space-y-3">
              <ResultBlock result={block.results.delta} index={index * 10 + 1} />
              <ResultBlock result={block.results.xgboost} index={index * 10 + 2} />
            </div></details>
        </Card>
      );
    case "cohort":
      return <CohortCard block={block as unknown as CohortBlock} />;
    case "context":
      return <ContextCard block={block as unknown as ContextBlock} />;
    case "ideas":
      return (
        <div className="grid gap-2 md:grid-cols-2" data-testid="whatif-ideas">
          {block.ideas.map((i) => (
            <button key={i.label} type="button" disabled={busy} onClick={() => onAsk(i.send)}
                    className="rounded-md border border-border bg-surface px-3 py-2 text-left hover:border-accent disabled:opacity-50">
              <span className="block text-[13px] font-semibold text-text-primary">{i.label}</span>
              <span className="block text-[11px] text-text-muted">“{i.send}” · {i.why}</span></button>))}
        </div>
      );
    case "saved":
      return <p className="rounded-md border border-positive/40 bg-positive-muted px-3 py-2 text-[13px]" data-testid="whatif-saved"><Markdown text={block.text} /></p>;
    case "report":
      return <p className="text-[13px]" data-testid="whatif-report-ready">{block.text} <a className="text-accent underline" href={reportHref(threadId)} data-testid="whatif-report-link">Download the Word report</a></p>;
    case "attribution":
      return (
        <Card className="space-y-2 p-4" data-testid="whatif-attribution">
          <WaterfallChart bars={block.waterfall} testId={`whatif-attr-chart-${index}`} />
          <WaterfallTable bars={block.waterfall} />
        </Card>
      );
    case "proposal":
      return (
        <div className="space-y-2 rounded-md border border-accent/40 bg-surface px-3 py-2.5" data-testid="whatif-proposal">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              {block.kind === "stack" ? "Scenario with the added step" : block.kind === "intensify" ? "Scaled scenario" : "Proposed scenario"}</p>
            {block.assumptions.length || block.unread.length ? (
              <span title={[...block.assumptions, ...block.unread.map((u) => `Not read: ${u}`)].join(" ")} data-testid="whatif-proposal-info"
                    className="inline-flex items-center text-text-muted"><Info size={12} /></span>) : null}
            <span className="ml-auto text-[11px] text-text-muted">{block.population}</span>
          </div>
          <ul className="space-y-1">
            {block.steps.map((s, i) => (
              <li key={i} className="flex flex-wrap items-center gap-1.5 text-[13px] text-text-primary" data-testid="whatif-proposal-step">
                {s.restatement}
                {s.levers.map((l) => <span key={l} className="rounded-full bg-accent-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">{l}</span>)}
              </li>))}
          </ul>
          {block.assumptions.length ? (
            <ul className="space-y-0.5 text-[11px] leading-snug text-text-muted" data-testid="whatif-proposal-assumptions">
              {block.assumptions.slice(0, 4).map((a, i) => <li key={i} className="break-words">{a}</li>)}
            </ul>) : null}
          {block.unread.length ? (
            <p className="text-[11px] leading-snug text-warning break-words" data-testid="whatif-proposal-unread">Not read: {block.unread.join(" ")}</p>) : null}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button type="button" disabled={busy} onClick={() => onAsk("::execute")} data-testid="whatif-proposal-execute"
                    className="inline-flex items-center gap-1 rounded-md border border-accent px-3 py-1.5 text-[12px] font-medium text-accent hover:bg-accent-muted disabled:opacity-40">
              <Play size={12} /> Execute scenario</button>
            <span className="text-[11px] text-text-muted">{block.method ? `Model: ${block.method}` : "Model chosen on Execute: Delta method or XGBoost"}</span>
          </div>
        </div>
      );
    case "answer":
    case "table":
    case "chart":
      return <ConvoBlockView block={block as never} index={index} />;
    case "scenario_set":
      return <ScenarioSetView block={block} />;
    case "regime":
      return <RegimeStrip block={block} compact={Boolean(block.compact)} testId={`whatif-regime-${index}`} />;
    case "scenario_memo":
      return (
        <p className="text-[13px]" data-testid="whatif-scenario-memo">
          <a className="text-accent underline" href={scenarioMemoHref()} data-testid="whatif-scenario-memo-link">{block.label}</a>
          <span className="ml-2 text-[11px] text-text-muted">engine {block.engine_version} · {block.fingerprint}</span>
        </p>);
    case "refusal":
      return <p className="rounded-md border border-warning/40 bg-warning-muted px-3 py-2 text-[13px] text-text-primary" data-testid="whatif-refusal">{block.text}</p>;
    case "error":
      return <p className="rounded-md border border-negative/40 bg-negative-muted px-3 py-2 text-[13px] text-negative" role="alert" data-testid="whatif-error">{block.text}</p>;
    default:
      return null;
  }
}

const SEV_DOT: Record<string, string> = { mild: "bg-accent/60", moderate: "bg-warning", severe: "bg-negative" };

/** PLAN_R13 §S.4: headline by severity, then the evidence and what the data cannot tell us. */
function ScenarioSetView({ block }: { block: ScenarioSetBlock }) {
  const ev = block.evidence.filter((e) => e.key !== "cannot");
  return (
    <Card className="space-y-3 p-4" data-testid="whatif-scenario-set">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-[14px] font-semibold text-text-primary">Calibrated severities · corporate book</h3>
        <span className="ml-auto text-[11px] text-text-muted">As of {block.as_of} · SAR</span>
      </div>
      {block.regime_note ? (
        <p className="rounded-md border border-warning/40 bg-warning-muted px-3 py-2 text-[12px] leading-snug text-text-primary" data-testid="whatif-scenario-regime-note">
          {block.regime_note}</p>) : null}
      <table className="w-full border-collapse" data-testid="whatif-scenario-table">
        <thead><tr className="border-b border-border">
          <th className={th}>Severity</th><th className={cn(th, "text-right")}>ECL change</th>
          <th className={cn(th, "text-right")}>Stage 2</th><th className={cn(th, "text-right")}>Capital</th></tr></thead>
        <tbody>{block.rows.map((r) => (
          <tr key={r.severity} className="border-b border-border/50 align-top" data-testid={`whatif-scenario-${r.severity}`}>
            <td className={td}>
              <span className="inline-flex items-center gap-1.5 font-semibold text-text-primary">
                <span className={cn("h-2 w-2 rounded-full", SEV_DOT[r.severity])} />{r.label}</span>
              <span className="block text-[11px] text-text-muted">{r.frequency}</span>
              <span className="block max-w-[34rem] text-[11px] leading-snug text-text-muted">{r.scenario}</span></td>
            <td className={cn(td, "whitespace-nowrap text-right")}>{r.ecl_change >= 0 ? "+" : ""}{sar(r.ecl_change)}
              <span className="block whitespace-normal text-[11px] text-text-muted">{pct(r.ecl_change_pct, 1)} · band {sar(r.ecl_band[0])} to {sar(r.ecl_band[1])}</span></td>
            <td className={cn(td, "text-right")}>{pct(r.stage2 * 100, 1)}
              <span className="block text-[11px] text-text-muted">from {pct(r.stage2_start * 100, 1)}</span></td>
            <td className={cn(td, "whitespace-nowrap text-right")}>{sar(r.capital)}</td></tr>))}</tbody>
      </table>
      <dl className="grid gap-x-3 gap-y-1.5 text-[12px] md:grid-cols-[9rem_1fr]" data-testid="whatif-scenario-evidence">
        {ev.map((e) => (
          <React.Fragment key={e.key}>
            <dt className="font-semibold text-text-muted">{e.label}</dt>
            <dd className="leading-snug text-text-secondary">{e.text}</dd>
          </React.Fragment>))}
      </dl>
      <p className="rounded-md border border-warning/40 bg-warning-muted px-3 py-2 text-[12px] leading-snug text-text-primary" data-testid="whatif-scenario-cannot">
        <span className="font-semibold">What this data cannot tell us.</span> {block.cannot}</p>
      <p className="text-[11px] text-text-muted" data-testid="whatif-scenario-source">
        Data Domains: {block.relations.join(", ")} · engine {block.engine_version} · {block.fingerprint}</p>
    </Card>
  );
}

interface CohortBlock {
  title: string; domain: string; period: string; owners: number; exposures: number; ead: number; ecl: number; coverage_pct: number;
  stage_mix: Record<string, { n: number; ead: number; ecl: number }>; grade_mix: { grade: string; n: number; ead: number }[];
  segments: { segment: string; n: number; ead: number; ecl: number }[]; top_reasons: { reason: string; n: number }[];
  bands: { band: string; n: number; ead: number }[]; labels: Labels; ruleset: string; cohort_id: string;
  membership_hash: string; exposures_frozen: number;
  /** R16 m (M2/M4): the Early Warning segment analysis of the frozen population (compact), when the service has it. */
  analysis?: SegmentAnalysis;
}

function CohortCard({ block }: { block: CohortBlock }) {
  const lab = block.labels;
  return (
    <Card className="space-y-3 p-4" data-testid="whatif-cohort" data-membership-hash={block.membership_hash}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-[1_1_20rem] items-center gap-1.5">
          <h3 className="min-w-0 break-words text-[14px] font-semibold text-text-primary">{String(block.title).startsWith("Borrower 360") ? block.title : `Early Warning cohort · ${block.title}`}</h3>
          <InfoPopover title="Cohort">
            Frozen by Early Warning: {count(block.exposures_frozen)} {lab.exposures.toLowerCase()}, membership hash verified
            (sha256 {block.membership_hash.slice(0, 12)}…). Every scenario in this thread runs on exactly these.
          </InfoPopover>
        </div>
        <span className="min-w-0 break-words text-[11px] text-text-muted">{lab.book} · {block.period} · rule set {block.ruleset} · {block.cohort_id}</span>
      </div>
      {block.analysis ? <SegmentAnalysisCompact a={block.analysis} /> : null}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <Tile label={lab.owners} value={count(block.owners)} testId="whatif-customers" />
        <Tile label={lab.exposures} value={count(block.exposures)} testId="whatif-exposures" />
        <Tile label="EAD" value={sar(block.ead)} testId="whatif-ead" />
        <Tile label="ECL" value={sar(block.ecl)} testId="whatif-cohort-ecl" />
        <Tile label="Coverage" value={pct(block.coverage_pct, 2)} />
      </div>
      <span className="inline-flex items-center gap-1 text-[11px] text-text-muted" data-testid="whatif-cohort-membership"
            title={`${count(block.exposures_frozen)} ${lab.exposures.toLowerCase()} frozen by Early Warning; membership hash sha256 ${block.membership_hash.slice(0, 12)}…`}>
        <Info size={11} /> {count(block.exposures_frozen)} {lab.exposures.toLowerCase()}</span>
      <Link href={`/early-warning?domain=${block.domain}&period=${block.period}`} className="text-[12px] text-accent hover:underline" data-testid="whatif-back-to-ews">Open in Early Warning</Link>
    </Card>
  );
}

/** R16 m (M4): the subject's facts a thread opens with, before the proposed scenario (backend chat/subject.py). */
function ContextCard({ block }: { block: ContextBlock }) {
  const tcols: { key: keyof ContextTrendRow; label: string }[] = [
    { key: "period", label: "Period" }, { key: "ead", label: "EAD (SAR)" },
    ...(block.kind === "scope" ? [{ key: "share_pct" as const, label: "Share of book" }] : []),
    { key: "stage23_pct", label: "Stage 2+3 share" }, { key: "ecl", label: "ECL (SAR)" }, { key: "coverage_pct", label: "Coverage" }];
  return (
    <Card className="space-y-3 p-4" data-testid="whatif-context" data-kind={block.kind}>
      <PlainWords lines={block.plain_words} title={contextHeading(block)} testId="whatif-context-plain" />
      <Markdown text={[block.headline, block.trend_line].filter(Boolean).join(" ")} headline />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {contextTiles(block).map((f) => <Tile key={f.key} label={f.label} value={f.text} testId={`whatif-context-${f.key}`} />)}
      </div>
      {block.trend.length ? (
        <Section title="Trend" testId="whatif-context-trend">
          <div className="overflow-x-auto"><table className="w-full">
            <thead><tr>{tcols.map((c) => <th key={c.key} className={th}>{c.label}</th>)}</tr></thead>
            <tbody>{block.trend.map((r) => (
              <tr key={r.period} className="border-t border-border">
                {tcols.map((c) => <td key={c.key} className={td}>{trendCell(c.key, r[c.key])}</td>)}</tr>))}</tbody>
          </table></div>
        </Section>) : null}
      {block.top.rows.length ? (
        <Section title={block.top.title} testId="whatif-context-top">
          <div className="overflow-x-auto"><table className="w-full">
            <thead><tr>{block.top.columns.map((c) => <th key={c.key} className={th}>{c.label}</th>)}</tr></thead>
            <tbody>{block.top.rows.map((r, i) => (
              <tr key={i} className="border-t border-border">
                {block.top.columns.map((c) => {
                  const v = r[c.key];
                  const shown = typeof v === "number" ? (Number.isInteger(v) ? count(v) : v.toFixed(c.key.endsWith("pct") ? 2 : 1)) : String(v ?? "");
                  return <td key={c.key} className={td}>{c.key === "name" && typeof r.href === "string"
                    ? <Link className="text-accent hover:underline" href={r.href}>{shown}</Link> : shown}</td>;
                })}</tr>))}</tbody>
          </table></div>
        </Section>) : null}
      <p className="text-[11px] text-text-muted" data-testid="whatif-context-source">Source: {block.source}</p>
    </Card>
  );
}

export function AnswerView({ answer, onAsk, threadId, busy, turnIndex }: { answer: Answer; onAsk: Ask; threadId: string; busy: boolean; turnIndex: number }) {
  return (
    <AnswerFrame testId="whatif-answer">
      {answer.blocks.map((b, i) => <BlockView key={i} block={b} index={turnIndex * 100 + i} onAsk={onAsk} threadId={threadId} busy={busy}
                                              lead={i === answer.blocks.findIndex((x) => x.type === "text")} />)}
      {answer.evidence?.length ? <EvidenceInfo answer={answer as unknown as ConvoAnswer} /> : null}
    </AnswerFrame>
  );
}
