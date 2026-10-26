"use client";

/**
 * R11 Session L (PLAN_R11 L1, L6): Deal Desk Pipeline mode. The pending deals with checkboxes and "All pending",
 * the capital budget (prefilled from the RWA and EL budgets) and the primary action Optimise pipeline.
 * The result reads answer first: one line, at most 4 tiles; then the decision table, the risk-appetite panel
 * (before and after) and the efficient frontier of SVA against RWA. Every figure is an engine result.
 * PLAN_R12 I21 (Session U): every deal, in the pending list and in the decisions, opens the full deal page.
 */

import * as React from "react";
import { Play } from "lucide-react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { Plot } from "@/components/v5/ews/plot";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { FACILITY, STRUCTURE } from "@/lib/v5/dealdesk";
import {
  type Decision, type FrontierPoint, type PipelineDeal, type PipelineListing, type PipelineResult,
  allPending, parseBudget, pipelineApi, resultTiles, sortDecisions, toggle,
} from "@/lib/v5/dealdesk-pipeline";
import { pct, sar } from "@/lib/v5/format";
import { friendlyMessage } from "@/lib/v5/errors";

import { APPETITE_INFO, AppetitePanel } from "./appetite-panel";
import { C } from "./charts";
import { ChartTitle, Chip, PrimaryButton, Section, tableCls, tdCls, thCls } from "./kit";

const SOURCE_TONE: Record<string, "neutral" | "accent"> = { "Deal Desk": "accent", Uploaded: "accent", "Pipeline set": "neutral" };

/** The efficient frontier: optimum SVA at each RWA budget, the chosen budget marked. */
export function PipelineFrontier({ points, height = 260 }: { points: FrontierPoint[]; height?: number }) {
  const ps = [...points].sort((a, b) => a.rwa_used - b.rwa_used);
  const chosen = ps.find((p) => p.chosen);
  const data: Record<string, unknown>[] = [
    { type: "scatter", mode: "lines+markers", name: "Optimum", x: ps.map((p) => p.rwa_used), y: ps.map((p) => p.sva),
      customdata: ps.map((p) => [p.rwa_budget, p.selected]), line: { color: C.rec, width: 2, shape: "linear" }, marker: { size: 7, color: C.rec },
      hovertemplate: "RWA budget SAR %{customdata[0]:,.0f}m<br>RWA used SAR %{x:,.0f}m<br>SVA SAR %{y:,.2f}m<br>%{customdata[1]} deals<extra></extra>" },
  ];
  if (chosen) data.push({ type: "scatter", mode: "markers", name: "Your budget", x: [chosen.rwa_used], y: [chosen.sva],
    marker: { size: 14, color: C.ask, symbol: "star", line: { width: 1, color: "#fff" } },
    hovertemplate: "Your budget: SAR %{x:,.0f}m RWA, SVA SAR %{y:,.2f}m<extra></extra>" });
  return <Plot data={data} height={height} testId="dealdesk-pipeline-frontier" filename="deal-desk-pipeline-frontier"
               ariaLabel="Efficient frontier: the best total SVA for each RWA budget, with your budget marked"
               layout={{ hovermode: "closest", margin: { l: 56, r: 16, t: 16, b: 44 }, showlegend: false,
                         xaxis: { title: { text: "RWA consumed, SAR million" }, tickformat: ",.0f", rangemode: "tozero" },
                         yaxis: { title: { text: "SVA, SAR million" }, tickformat: ",.1f", rangemode: "tozero" } }} />;
}

export const FRONTIER_INFO = (
  <>
    Each point re-solves the whole pipeline exactly with a different RWA budget (0 to 150% of yours, and enough for every deal) and plots the
    best total SVA against the RWA it uses. The star is your budget. Where the curve flattens, more capital adds little value: other limits bind
    first. The shadow prices under the table say what one more unit of each binding limit is worth.
  </>
);

/** The decision table: deal, decision, structure, amount, RAROC, SVA, reason. */
export function DecisionTable({ rows, onOpen }: { rows: Decision[]; onOpen?: (id: string) => void }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className={tableCls} data-testid="dealdesk-pipeline-decisions">
        <thead className="sticky top-0 bg-surface"><tr>
          <th className={thCls}>Deal</th><th className={thCls}>Decision</th><th className={thCls}>Structure</th>
          <th className={cn(thCls, "text-right")}>Amount</th><th className={cn(thCls, "text-right")}>RAROC</th>
          <th className={cn(thCls, "text-right")}>SVA</th><th className={thCls}>Reason</th></tr></thead>
        <tbody>{rows.map((d) => {
          const o = d.option;
          const best = o ?? d.options.filter((x) => x.available).sort((a, b) => b.sva - a.sva)[0] ?? d.options[0];
          return (
            <tr key={d.proposal_id} data-testid={`dealdesk-pipeline-decision-${d.proposal_id}`} className="align-top hover:bg-surface-hover">
              <td className={cn(tdCls, "whitespace-normal")}>
                {/* PLAN_R12 I21: every row opens the full deal page, pipeline-set deals included (one deal registry). */}
                <button type="button" onClick={() => onOpen?.(d.proposal_id)} disabled={!onOpen} data-testid={`dealdesk-pipeline-open-${d.proposal_id}`}
                        className="text-left font-medium text-accent enabled:hover:underline disabled:cursor-default">{d.proposal_id}</button>
                <span className="block max-w-[14rem] truncate text-text-primary" title={d.obligor_name}>{d.obligor_name}</span>
                <span className="block text-[11px] text-text-muted">{d.sector} · {d.rating}</span>
              </td>
              <td className={tdCls}><Chip tone={d.decision === "approve" ? "positive" : "negative"}>{d.decision === "approve" ? "Approve" : "Decline"}</Chip></td>
              <td className={cn(tdCls, "whitespace-normal")}>
                <span className="block">{o ? o.label : "–"}</span>
                <span className="block text-[11px] text-text-muted">{FACILITY[best.facility_type] ?? best.facility_type} · {STRUCTURE[best.structure] ?? best.structure}</span>
              </td>
              <td className={cn(tdCls, "text-right")}>{o ? sar(o.amount_sar_mn) : <span className="text-text-muted">{sar(d.amount_sar_mn)} asked</span>}</td>
              <td className={cn(tdCls, "text-right")}>{pct(best.lifetime_raroc)}</td>
              <td className={cn(tdCls, "text-right", (best.sva ?? 0) < 0 ? "text-negative" : "")}>{sar(best.sva)}</td>
              <td className={cn(tdCls, "min-w-[16rem] whitespace-normal text-text-secondary")}>
                {d.reason}
                {d.gets_in ? <span className="mt-0.5 block text-[11px] text-text-muted" data-testid={`dealdesk-pipeline-getsin-${d.proposal_id}`}>
                  What gets it in: {d.gets_in.text}</span> : null}
              </td>
            </tr>);
        })}</tbody>
      </table>
    </div>
  );
}

/** The pipeline result: answer line, ≤4 tiles, decisions, risk appetite, frontier and shadow prices. */
export function PipelineResultView({ r, onOpen }: { r: PipelineResult; onOpen?: (id: string) => void }) {
  const tiles = resultTiles(r).map((t, i) => ({ ...t, testId: `dealdesk-pipeline-tile-${i}` }));
  const decisions = React.useMemo(() => sortDecisions(r.decisions), [r.decisions]);
  return (
    <div className="space-y-4" data-testid="dealdesk-pipeline-result">
      <p className="text-[15px] font-semibold text-text-primary" data-testid="dealdesk-pipeline-headline">{r.headline}.</p>
      <KpiRow tiles={tiles} testId="dealdesk-pipeline-tiles" />
      <Section title="Decisions" testId="dealdesk-pipeline-decisions-card"
               info={<>One row per pending deal. The optimiser picks, for each deal, decline, the ask, the Optimise recommended structure or a reduced
                 amount, to maximise total SVA with every hard limit and the RWA and EL budgets held, charging soft-limit excesses past their trigger.
                 The solution is exact (branch and bound, checked against brute force). For a declined deal, “what gets it in” is the extra SVA
                 (and the margin that gives it) it needs to make the cut, and the deals it would displace.</>}>
        <DecisionTable rows={decisions} onOpen={onOpen} />
        {r.binding.length ? (
          <div className="mt-3 space-y-1" data-testid="dealdesk-pipeline-shadow">
            <ChartTitle title="Binding limits and shadow prices"
                        info="A binding limit is one the selection uses up. Its shadow price re-solves the pipeline with that limit relaxed by one step and reports the extra SVA: what one more unit of headroom is worth." />
            {r.binding.map((b) => <p key={`${b.name}-${b.scope}`} className="text-[12px] text-text-secondary">{b.text}.</p>)}
          </div>) : null}
      </Section>
      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Section title="Risk appetite after the selection" info={APPETITE_INFO} testId="dealdesk-pipeline-appetite-card">
          <AppetitePanel rows={r.limits} testId="dealdesk-pipeline-appetite" />
        </Section>
        <Section title="Efficient frontier" info={FRONTIER_INFO} testId="dealdesk-pipeline-frontier-card">
          <PipelineFrontier points={r.frontier} />
        </Section>
      </div>
    </div>
  );
}

/** Pipeline mode on the Deal Desk landing. */
export function PipelineMode({ onOpen }: { onOpen: (id: string) => void }) {
  const [list, setList] = React.useState<PipelineListing | null>(null);
  const [error, setError] = React.useState("");
  const [sel, setSel] = React.useState<Set<string>>(new Set());
  const [rwa, setRwa] = React.useState("");
  const [el, setEl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [res, setRes] = React.useState<PipelineResult | null>(null);

  React.useEffect(() => {
    let live = true;
    pipelineApi.list().then((l) => {
      if (!live) return;
      setList(l);
      setSel(allPending(l.deals));
      setRwa(String(l.budgets.rwa));
      setEl(String(l.budgets.el));
    }).catch((e) => { if (live) setError(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, []);

  const deals = list?.deals ?? [];
  const all = deals.length > 0 && sel.size === deals.length;
  const rwaV = parseBudget(rwa);
  const elV = parseBudget(el);
  const run = async () => {
    if (!sel.size || rwaV === null || elV === null) return;
    setBusy(true);
    setError("");
    try {
      setRes(await pipelineApi.optimise({ deal_ids: deals.filter((d) => sel.has(d.proposal_id)).map((d) => d.proposal_id), rwa_budget: rwaV, el_budget: elV }));
    } catch (e) {
      setError(friendlyMessage(e, "Deal Desk"));
    } finally {
      setBusy(false);
    }
  };
  const selAmount = deals.filter((d) => sel.has(d.proposal_id)).reduce((s, d) => s + d.amount_sar_mn, 0);

  return (
    <div className="space-y-4" data-testid="dealdesk-pipeline-mode">
      <Section title="Pending pipeline" testId="dealdesk-pipeline-select"
               info={<>Every pending deal: Deal Desk proposals and uploads that are new, in review or counter-offered, and the pipeline set of pending
                 applications. Tick the deals to consider, set the capital budget (prefilled from the Corporate Banking RWA and EL budgets in the risk
                 appetite) and optimise. Each deal runs through the same engine as a single deal.</>}
               action={
                 <div className="flex flex-wrap items-center gap-2">
                   <label className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-[12px] text-text-muted">
                     RWA budget SAR
                     <input value={rwa} onChange={(e) => setRwa(e.target.value)} inputMode="decimal" aria-label="RWA budget, SAR million"
                            data-testid="dealdesk-pipeline-rwa" className="w-16 bg-transparent text-right tabular-nums text-text-primary outline-none" />m
                   </label>
                   <label className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-[12px] text-text-muted">
                     EL budget SAR
                     <input value={el} onChange={(e) => setEl(e.target.value)} inputMode="decimal" aria-label="EL budget, SAR million"
                            data-testid="dealdesk-pipeline-el" className="w-12 bg-transparent text-right tabular-nums text-text-primary outline-none" />m
                   </label>
                   <PrimaryButton onClick={() => void run()} disabled={busy || !sel.size || rwaV === null || elV === null} data-testid="dealdesk-pipeline-optimise">
                     <Play size={14} /> {busy ? "Optimising…" : "Optimise pipeline"}</PrimaryButton>
                 </div>}>
        {error ? <p className="mb-2 text-[12px] text-negative" role="alert">{error}</p> : null}
        {!list && !error ? <Skeleton className="h-40 w-full" /> : null}
        {list ? (
          <>
            <div className="mb-2 flex flex-wrap items-center gap-3 text-[12px] text-text-secondary">
              <label className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={all} onChange={() => setSel(all ? new Set() : allPending(deals))} data-testid="dealdesk-pipeline-all" />
                All pending
              </label>
              <span className="tabular-nums" data-testid="dealdesk-pipeline-selected">{sel.size} of {deals.length} deals · {sar(selAmount)} asked</span>
            </div>
            <div className={cn("overflow-auto", res ? "max-h-[220px]" : "max-h-[460px]")}>
              <table className={tableCls} data-testid="dealdesk-pipeline-deals">
                <thead className="sticky top-0 bg-surface"><tr>
                  <th className={cn(thCls, "w-8")} /><th className={thCls}>Deal</th><th className={thCls}>Obligor</th><th className={thCls}>Sector</th>
                  <th className={cn(thCls, "text-center")}>Rating</th><th className={thCls}>Facility</th>
                  <th className={cn(thCls, "text-right")}>Amount</th><th className={cn(thCls, "text-right")}>Tenor</th><th className={thCls}>Source</th></tr></thead>
                <tbody>{deals.map((d: PipelineDeal) => (
                  <tr key={d.proposal_id} className="hover:bg-surface-hover" data-testid={`dealdesk-pipeline-deal-${d.proposal_id}`}>
                    <td className={tdCls}><input type="checkbox" checked={sel.has(d.proposal_id)} aria-label={`Include ${d.proposal_id}`}
                                                 onChange={() => setSel((s) => toggle(s, d.proposal_id))} /></td>
                    <td className={cn(tdCls, "font-medium text-accent")}>
                      <button type="button" onClick={() => onOpen(d.proposal_id)} className="font-medium text-accent hover:underline"
                              data-testid={`dealdesk-pipeline-deal-open-${d.proposal_id}`}>{d.proposal_id}</button></td>
                    <td className={cn(tdCls, "max-w-[16rem] truncate")} title={d.obligor_name}>{d.obligor_name}</td>
                    <td className={tdCls}>{d.sector}</td>
                    <td className={cn(tdCls, "text-center font-medium")}>{d.rating}</td>
                    <td className={tdCls}>{FACILITY[d.facility_type] ?? d.facility_type} · {STRUCTURE[d.structure] ?? d.structure}</td>
                    <td className={cn(tdCls, "text-right")}>{sar(d.amount_sar_mn)}</td>
                    <td className={cn(tdCls, "text-right")}>{d.tenor_years}y</td>
                    <td className={tdCls}><Chip tone={SOURCE_TONE[d.source] ?? "neutral"}>{d.source}</Chip></td>
                  </tr>))}</tbody>
              </table>
            </div>
          </>) : null}
      </Section>
      {busy && !res ? <Skeleton className="h-64 w-full" /> : null}
      {res ? <PipelineResultView r={res} onOpen={onOpen} /> : null}
    </div>
  );
}
