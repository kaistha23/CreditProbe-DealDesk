"use client";

/**
 * The steps of a deal (PLAN_R12 §1.2, I15): 1 Proposal, 2 Review, 3 Analysis, 4 Stress, 5 Structure (Optimise),
 * 6 Recommendation. Diagnose, then cure. Each step keeps its R11 content, has one purpose and one primary action.
 */

import * as React from "react";
import { ArrowRight, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  type Analysis, type Bundle, type Constraint, type OptimizeResult, type Proposal, type ProposalFull, type Solution, type Terms,
  AMORTISATION, COLLATERAL, FACILITY, GUARANTEE_LABEL, RATINGS, STRUCTURE, TERM_ROWS, bps, cap, constraintRead, dealdesk, headroomRead,
  isFunded, leverRead, money, pctPts, rate, withNeutral, years,
} from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { depositRead, hasDeposit } from "@/lib/v5/dealdesk-deposit";  // Round D

import {
  FrontierChart, HeadroomChart, IsoRarocHeatmap, RarocAmountCurve, RatingChart, TornadoChart, WaterfallChart,
} from "./charts";
import { AlternativeCards, SingleLeverTable } from "./alternatives";
import { AmountInfo, FrontierInfo, HeadroomInfo, HeatmapInfo, RatingInfo, StressInfo, TornadoInfo, WaterfallInfo } from "./explain";
import { ChartTitle, Chip, Collapsible, Empty, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";
import { ApprovalInfo, RwaElInfo, SvaInfo, useEngineEconomics } from "./engine-info";  // R14 E
import { DealStoryLine, ReturnViewSwitch } from "./deal-story";  // R15 b (L13)
import { rarocTileSub } from "@/lib/v5/dealdesk-engines";
import { KpiRow as SharedKpiRow } from "@/components/v5/core/kpi-row";
import { ModelCardDialog } from "./model-card";
import { StructureItYourself } from "./term-panel";
import { OptimiseView } from "./optimise-view";
import { bestOffers } from "@/lib/v5/dealdesk-offer";
import type { ForwardStructureInput } from "@/lib/v5/dealdesk-forward";
// PLAN_R11: the component sessions' exports (F forward risk, S Stress Lab, L pipeline test, R review).
import { ForwardRiskPanel } from "./forward-risk";
import { PipelineLinesPanel, PipelineTestButton } from "./pipeline-test";
import { ReviewWorkspace } from "./review-workspace";
import { hasSlot } from "./r12-slots";
import { StressSummary } from "./stress-lab";
// PLAN_R12 (Session D, mounted by U): the R12 Stress step (ladder, reverse stress, chain, editor, verdict and tier) in place of the R11 Stress Lab.
import { StressLabStep } from "./stress-lab-r12";

/** One structure of the Optimise output as the forward-risk panel scores it (asked, recommended, alternatives). */
export type R11Structure = ForwardStructureInput & { key: string };

// ------------------------------------------------------------------ shared

/**
 * PLAN_R10 D5 (G-TILES): four tiles in one row: RAROC against the hurdle, SVA, RWA, approval. Amount, tenor,
 * price and breakeven are in the ask line and the term sheet, not in tiles.
 */
export function KpiRow({ ask, rec }: { ask: Analysis; rec: Analysis | null }) {
  const r = rec ?? ask;
  const m = r.metrics;
  const e = useEngineEconomics(r);  // R14 E (K18): the engines' (i) for RWA/EL/PD/LGD and the SVA basis
  const hard = r.constraints.some((c) => c.status === "breach" && c.kind === "hard");
  // The one shared tile row (PLAN_R10 S2, components/v5/core/kpi-row): max 4, one row, 2 × 2 only below 900 px.
  return (
    <div className="space-y-2">
    <SharedKpiRow testId="dealdesk-kpis" tiles={[
      { label: "RAROC (price only)", value: rate(m.lifetime_raroc), tone: m.clears_hurdle ? "positive" : "negative", testId: "dealdesk-kpi-raroc",
        sub: `${rarocTileSub(m.clears_hurdle, m.hurdle)}${rec ? ` · ask ${rate(ask.metrics.lifetime_raroc)}` : ""}`,
        info: (
          <span className="block space-y-2" data-testid="dealdesk-kpi-raroc-info">
            <span className="block">Lifetime RAROC of the deal: PV of risk-adjusted profit over PV of allocated capital, over the life of the deal, against the hurdle.
              It measures <b>price only</b>; the verdict also reads capacity, bureau, connected parties and documents.</span>
            {e?.findings.verdict.story ? <span className="block font-medium" data-testid="dealdesk-kpi-raroc-story">{e.findings.verdict.story}</span> : null}
            {e?.return_views ? <span className="block"><ReturnViewSwitch e={e} testId="dealdesk-kpi-return-view" compact /></span> : null}
          </span>) },
      { label: "SVA", value: money(m.sva), tone: m.sva >= 0 ? "positive" : "negative", testId: "dealdesk-kpi-sva",
        sub: `Lifetime · ${rec ? `ask ${money(ask.metrics.sva)}` : `relationship ${money(m.relationship_sva)}`}`,
        info: e ? <SvaInfo e={e} /> : "PV of risk-adjusted profit less the hurdle charge on capital over the life of the deal, SAR million." },
      { label: "RWA", value: money(m.rwa_y1), sub: `EL ${money(m.el_y1)} · ECL ${money(m.day_one_ecl)}`, testId: "dealdesk-kpi-rwa",
        info: e ? <RwaElInfo e={e} /> : "Year-one RWA, year-one EL and day-one IFRS 9 Stage 1 ECL, SAR million." },
      { label: "Approval", value: <span className="text-[15px]" title={r.approval.level}>{r.approval.level}</span>, testId: "dealdesk-kpi-approval",
        sub: hard ? "Hard limit breached" : r.approval.binding?.label ? `Set by: ${r.approval.binding.label.toLowerCase()}` : "Within hard limits",
        info: e ? <ApprovalInfo e={e} /> : r.approval.reasons.join(" · ") || undefined },
    ]} />
    {/* R15 b (L13 (1)): one story on the page: the same sentence as the Review banner, under the tiles */}
    {!rec ? <DealStoryLine e={e} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ the ask (PLAN_R10 D3)

const priceRead = (t: Terms) => (isFunded(t) ? `${t.currency === "USD" ? "SOFR" : "SAIBOR"} + ${bps(t.margin_bps)}` : `Commission ${bps(t.commission_bps)}`);

/** The client's ask as requested, in labelled rows: amount, tenor, pricing, fees, security, covenants, purpose. */
export function askRows(p: Proposal): { label: string; value: string }[] {
  const t = p.ask;
  const fees = [t.upfront_fee_bps ? `Upfront ${bps(t.upfront_fee_bps)}` : "", t.commitment_fee_bps ? `commitment ${bps(t.commitment_fee_bps)}` : "",
                !isFunded(t) && t.commission_bps ? `commission ${bps(t.commission_bps)}` : ""].filter(Boolean).join(" · ") || "None";
  const coll = p.security.collateral.filter((c) => c.pledged_in_ask || t.collateral_ids?.includes(c.collateral_id))
    .map((c) => `${COLLATERAL[c.type] ?? cap(c.type.replace(/_/g, " "))} ${money(c.value, c.currency)} (${c.collateral_id})`);
  const guar = p.security.guarantees.filter((g) => g.offered_in_ask || g.guarantee_id === t.guarantee_id)
    .map((g) => `${cap(g.type.replace(/_/g, " "))} guarantee, ${g.guarantor} (${g.guarantor_rating}), ${pctPts(g.coverage_pct)}`);
  if (!guar.length && t.guarantee_id) guar.push(`${GUARANTEE_LABEL[t.guarantee_id] ?? t.guarantee_id} · ${pctPts(t.guarantee_coverage_pct)}`);
  if (t.cash_margin_pct) coll.push(`Cash margin ${pctPts(t.cash_margin_pct)}`);
  const covs = [cap(t.covenant_package), ...p.security.covenants.map((c) => `${cap(c.type.replace(/_/g, " "))} ${fmt.ratio(c.threshold)}x`)];
  const repay = t.amortisation === "balloon" ? `balloon ${pctPts(t.balloon_pct)}` : (AMORTISATION[t.amortisation] ?? cap(t.amortisation)).toLowerCase();
  return [
    { label: "Amount", value: `${money(t.amount, t.currency)} · ${FACILITY[t.facility_type] ?? t.facility_type}, ${STRUCTURE[t.structure] ?? t.structure}` },
    { label: "Tenor", value: `${years(t.tenor_years)}${t.grace_years ? `, ${years(t.grace_years)} grace` : ""}, ${repay}` },
    { label: "Pricing", value: priceRead(t) },
    { label: "Fees", value: fees },
    { label: "Security", value: [...coll, ...guar].join(" · ") || "Unsecured" },
    ...(hasDeposit(t) ? [{ label: "Deposit", value: depositRead(t) }] : []),  // Round D: the Deposit requirement term
    { label: "Covenants", value: covs.join(" · ") },
    { label: "Purpose", value: p.purpose || "Not stated" },
  ];
}

/** One summary line of the ask, kept at the top of Analysis. */
export function askLine(p: Proposal): string {
  const t = p.ask;
  return `${money(t.amount, t.currency)} over ${years(t.tenor_years)} at ${priceRead(t)}${t.upfront_fee_bps ? `, upfront ${bps(t.upfront_fee_bps)}` : ""}`;
}

export function AskCard({ p, action }: { p: Proposal; action?: React.ReactNode }) {
  return (
    <Section title="The ask, as the client requested" testId="dealdesk-ask" action={action}
             info="The terms the relationship manager submitted for the client, before any analysis or counter-offer.">
      <dl className="grid gap-x-6 gap-y-2 text-[13px] md:grid-cols-[110px_1fr]" data-testid="dealdesk-ask-rows">
        {askRows(p).map((r) => (
          <React.Fragment key={r.label}>
            <dt className="text-text-muted">{r.label}</dt>
            <dd className="min-w-0 break-words font-medium text-text-primary" data-testid={`dealdesk-ask-${r.label.toLowerCase()}`}>{r.value}</dd>
          </React.Fragment>))}
      </dl>
    </Section>
  );
}

export function AskLine({ p, onOpen }: { p: Proposal; onOpen?: () => void }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 rounded-lg border border-border bg-surface px-3 py-2 text-[13px]" data-testid="dealdesk-ask-line">
      <span className="font-semibold text-text-primary">The ask:</span>
      <span className="min-w-0 break-words text-text-primary"><b>{askLine(p)}</b>{p.purpose ? <span className="text-text-secondary"> · {p.purpose}</span> : null}</span>
      {onOpen ? <button type="button" onClick={onOpen} className="ml-auto text-[12px] text-accent hover:underline" data-testid="dealdesk-ask-open">Full ask</button> : null}
    </div>
  );
}

export function TermSheet({ cols }: { cols: { name: string; terms: Terms; res?: Analysis | Solution | null }[] }) {
  const base = cols[0].terms;
  const metricRows: [string, (c: Analysis | Solution) => string][] = [
    ["Lifetime RAROC", (c) => rate(c.metrics.lifetime_raroc)], ["Relationship RAROC", (c) => rate(c.metrics.relationship_raroc)],
    ["SVA", (c) => money(c.metrics.sva)], ["RWA (year one)", (c) => money(c.metrics.rwa_y1)],
    ["EL (PV)", (c) => money(c.metrics.el_lifetime_pv)], ["Approval", (c) => c.approval.level],
  ];
  return (
    <div className="overflow-auto">
      <table className={tableCls} data-testid="dealdesk-term-sheet">
        <thead><tr><th className={thCls}>Term</th>{cols.map((c) => <th key={c.name} className={cn(thCls, "text-right")}>{c.name}</th>)}</tr></thead>
        <tbody>
          {TERM_ROWS.map(([label, read]) => (
            <tr key={label}><td className={tdCls}>{label}</td>
              {cols.map((c, i) => {
                const changed = i > 0 && read(c.terms) !== read(base);
                return <td key={c.name} data-changed={changed || undefined}
                           className={cn(tdCls, "text-right", changed && "bg-accent-muted font-semibold text-accent")}>{read(c.terms)}</td>;
              })}</tr>))}
          {metricRows.map(([label, read]) => (
            <tr key={label} className="bg-canvas"><td className={cn(tdCls, "font-medium")}>{label}</td>
              {cols.map((c) => <td key={c.name} className={cn(tdCls, "text-right font-medium")}>{c.res ? read(c.res) : "—"}</td>)}</tr>))}
        </tbody>
      </table>
    </div>
  );
}

export function ConstraintTable({ rows }: { rows: Constraint[] }) {
  return (
    <table className={tableCls} data-testid="dealdesk-constraints">
      <thead><tr><th className={thCls}>Limit</th><th className={thCls}>Scope</th><th className={cn(thCls, "text-right")}>After the deal</th>
        <th className={cn(thCls, "text-right")}>Limit</th><th className={cn(thCls, "text-right")}>Headroom</th><th className={thCls}>Type</th><th className={thCls}>Result</th></tr></thead>
      <tbody>{rows.map((c) => (
        <tr key={c.name} data-testid={`dealdesk-constraint-${c.name}`}>
          <td className={tdCls} title={c.basis}>{c.label}</td>
          <td className={cn(tdCls, "text-text-muted")}>{c.scope}</td>
          <td className={cn(tdCls, "text-right")}>{constraintRead(c)}</td>
          <td className={cn(tdCls, "text-right")}>{constraintRead(c, c.limit)}</td>
          <td className={cn(tdCls, "text-right")}>{headroomRead(c)}</td>
          <td className={tdCls}>{cap(c.kind)}</td>
          <td className={tdCls}>{c.status === "pass" ? <Chip tone="positive">Pass</Chip> : <Chip tone={c.kind === "hard" ? "negative" : "warning"}>Breach</Chip>}</td>
        </tr>))}</tbody>
    </table>
  );
}

export function Verdict({ res }: { res: Analysis }) {
  const [card, setCard] = React.useState(false);
  const soft = res.constraints.filter((c) => c.status === "breach" && c.kind === "soft");
  const hard = res.constraints.filter((c) => c.status === "breach" && c.kind === "hard");
  const oor = res.pd.out_of_range;
  const e = useEngineEconomics(res);
  return (
    <div className="flex flex-wrap gap-2" data-testid="dealdesk-verdict">
      <Chip tone={res.metrics.clears_hurdle ? "positive" : "negative"}>{res.metrics.clears_hurdle ? "Price clears the hurdle" : "Price below the hurdle"}</Chip>
      <Chip tone={hard.length ? "negative" : "positive"} title={hard.map((c) => c.label).join(" · ")}>
        {hard.length ? `${hard.length} hard limit${hard.length > 1 ? "s" : ""} breached` : "Hard limits pass"}</Chip>
      {soft.length ? <Chip tone="warning" title={soft.map((c) => c.label).join(" · ")}>{soft.length} soft breach{soft.length > 1 ? "es" : ""}</Chip> : null}
      <button type="button" onClick={() => setCard(true)} data-testid="dealdesk-pd-chip" className="rounded-full">
        <Chip title={`Model PD ${rate(res.pd.model_pd_12m, 2)} · master scale ${rate(res.pd.master_scale_pd_12m, 2)} · ${res.pd.model_version} · open the model card`}>
          PD {rate(res.pd.model_pd_12m, 2)}</Chip></button>
      {card ? <ModelCardDialog proposalId={res.proposal_id} onClose={() => setCard(false)} /> : null}
      {oor.status !== "in_range" ? (
        // R15 b (L13 (4)): what it means and what was done, in words (the engines' note; the raw ranges stay in the title)
        <Chip tone="warning" testId="dealdesk-oor"
              title={`${e?.pd_range ? `${e.pd_range.meaning} ${e.pd_range.done} · ` : ""}`
                + oor.features.filter((f) => f.status !== "in_range").map((f) => `${f.feature} ${f.value} outside ${f.p01}–${f.p99}`).join(" · ")
                + ` · master-scale PD ${rate(res.pd.master_scale_pd_12m, 2)}`}>
          {e?.pd_range?.label ?? (oor.status === "edge" ? "PD less certain: borrower at the edge of the model's range" : "PD less certain: borrower outside the model's range")}</Chip>) : null}
      {oor.status !== "in_range" && e?.pd_range ? (
        <p className="w-full text-[11.5px] text-text-secondary" data-testid="dealdesk-oor-note">{e.pd_range.meaning} {e.pd_range.done}</p>) : null}
    </div>
  );
}

// ------------------------------------------------------------------ 1 Proposal

function Rows({ rows, testId }: { rows: { label: string; value: string }[]; testId?: string }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,40%)_1fr] gap-x-4 gap-y-2 text-[12px]" data-testid={testId}>
      {rows.map((r) => (<React.Fragment key={r.label}><dt className="text-text-muted">{r.label}</dt><dd className="font-medium text-text-primary">{r.value}</dd></React.Fragment>))}
    </dl>
  );
}

/** PLAN_R5 D5: the complete proposal as submitted by the business, before any analysis. */
export function ProposalInFull({ full }: { full: ProposalFull }) {
  return (
    <div className="space-y-4" data-testid="dealdesk-proposal-full">
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Obligor and group"><Rows rows={full.obligor} testId="dealdesk-proposal-obligor" /></Section>
        <Section title="The deal" action={<a href={full.memo_href.startsWith("http") ? full.memo_href : `${dealdeskOriginSafe()}${full.memo_href}`}
                                              className="text-[12px] text-accent hover:underline" data-testid="dealdesk-memo-link">Credit memo</a>}>
          <Rows rows={full.deal} testId="dealdesk-proposal-deal" /></Section>
      </div>
      <Section title="Facility lines as submitted">
        <div className="overflow-auto">
          <table className={tableCls} data-testid="dealdesk-facility-lines">
            <thead><tr>{["Line", "Facility", "Amount", "Tenor", "Pricing", "Fees", "Repayment", "Security", "Guarantees", "Covenants"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{full.facility_lines.map((l) => (
              <tr key={l.line_id}>
                <td className={tdCls}>{l.line_id}</td><td className={cn(tdCls, "whitespace-normal")}>{l.facility} · {l.structure}</td><td className={cn(tdCls, "tabular-nums")}>{l.amount}</td>
                <td className={tdCls}>{l.tenor}</td><td className={cn(tdCls, "whitespace-normal")}>{l.pricing}</td><td className={cn(tdCls, "whitespace-normal")}>{l.fees}</td>
                <td className={cn(tdCls, "min-w-[140px] whitespace-normal")}>{l.repayment}</td><td className={cn(tdCls, "min-w-[160px] whitespace-normal")}>{l.security}</td>
                <td className={cn(tdCls, "min-w-[140px] whitespace-normal")}>{l.guarantees}</td><td className={cn(tdCls, "min-w-[180px] whitespace-normal")}>{l.covenants}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Section>
      {full.existing_facilities.length ? (
        <Section title="Existing exposure">
          <table className={tableCls} data-testid="dealdesk-existing-facilities">
            <thead><tr><th className={thCls}>Facility</th><th className={thCls}>Product</th><th className={cn(thCls, "text-right")}>Limit</th>
              <th className={cn(thCls, "text-right")}>Drawn</th><th className={cn(thCls, "text-right")}>EAD</th><th className={thCls}>Stage</th></tr></thead>
            <tbody>{full.existing_facilities.map((f) => (
              <tr key={f.facility_id}><td className={tdCls}>{f.facility_id}</td><td className={tdCls}>{f.product}</td><td className={cn(tdCls, "text-right")}>{f.limit}</td>
                <td className={cn(tdCls, "text-right")}>{f.drawn}</td><td className={cn(tdCls, "text-right")}>{f.ead}</td><td className={tdCls}>{f.stage}</td></tr>))}</tbody>
          </table>
        </Section>) : null}
    </div>
  );
}

function dealdeskOriginSafe(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export function ProposalStep({ p, full, onNext }: { p: Proposal; full?: ProposalFull; onNext: () => void }) {
  return (
    <div className="space-y-4" data-testid="dealdesk-step-proposal-view">
      {/* PLAN_R10 D3: the ask first, as the client requested it; the way to the charts is on it. */}
      {/* PLAN_R12 I23: drafting is "Write proposal" on the action bar; the step's one action is the next step, Review (I15). */}
      <AskCard p={p} action={<div className="flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={onNext} data-testid="dealdesk-analyse">Check the proposal <ArrowRight size={14} /></PrimaryButton></div>} />
      {full ? <ProposalInFull full={full} /> : null}
      <Section title="Financials">
        <div className="overflow-auto">
          <table className={tableCls} data-testid="dealdesk-financials">
            <thead><tr><th className={thCls}>{p.financials.currency} million</th>
              {p.financials.years.map((f) => <th key={f.year} className={cn(thCls, "text-right")}>{f.year}{f.kind === "projection" ? " P" : ""}</th>)}</tr></thead>
            <tbody>
              {([["Revenue", "revenue"], ["EBITDA", "ebitda"], ["Total debt", "total_debt"], ["Debt service", "debt_service"], ["Net worth", "net_worth"]] as const).map(([label, k]) => (
                <tr key={k}><td className={tdCls}>{label}</td>{p.financials.years.map((f) => (
                  <td key={f.year} className={cn(tdCls, "text-right", f.kind === "projection" && "text-text-muted")}>{f[k].toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>))}</tr>))}
              <tr><td className={tdCls}>Current ratio</td>{p.financials.years.map((f) => <td key={f.year} className={cn(tdCls, "text-right", f.kind === "projection" && "text-text-muted")}>{fmt.ratio(f.current_ratio)}x</td>)}</tr>
              <tr><td className={tdCls}>Debt / EBITDA</td>{p.financials.years.map((f) => <td key={f.year} className={cn(tdCls, "text-right", f.kind === "projection" && "text-text-muted")}>{f.ebitda ? `${fmt.ratio(f.total_debt / f.ebitda)}x` : "–"}</td>)}</tr>
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ 2 Analysis

function ratingRows(b: Bundle): { rating: string; raroc: number }[] {
  const i = RATINGS.indexOf(b.proposal.obligor.internal_rating as (typeof RATINGS)[number]);
  const rows = [{ rating: RATINGS[i], raroc: b.stress.base.lifetime_raroc }];
  for (const [k, n] of [["downgrade_1", 1], ["downgrade_2", 2]] as const) {
    const r = b.stress.rows.find((x) => x.scenario === k);
    if (r && RATINGS[i + n]) rows.push({ rating: RATINGS[i + n], raroc: r.lifetime_raroc });
  }
  return rows;
}

export function AnalysisStep({ b, onOptimise, busy, settings, onRecommendation, onAsk }: {
  b: Bundle; onOptimise?: () => void; busy?: boolean; settings?: React.ReactNode; onRecommendation?: () => void; onAsk?: () => void;
}) {
  const ask = b.ask;
  return (
    <div className="space-y-4" data-testid="dealdesk-step-analysis-view">
      <AskLine p={b.proposal} onOpen={onAsk} />
      <Section title="The ask against the hurdle and appetite" testId="dealdesk-ask-verdict"
               info="Lifetime RAROC on the ask, its components in present value, and every risk-appetite and regulatory limit measured on the corporate book after the deal."
               action={
                 // R7 (screen 01): Settings and Optimise on the chart card, as in R5; a saved recommendation is one click away.
                 <div className="flex flex-wrap items-center gap-2" data-testid="dealdesk-analysis-actions">
                   {onRecommendation ? (
                     <SecondaryButton onClick={onRecommendation} data-testid="dealdesk-open-recommendation">Saved recommendation <ArrowRight size={13} /></SecondaryButton>
                   ) : null}
                   {settings}
                   {onOptimise ? (
                     <PrimaryButton onClick={onOptimise} disabled={busy} data-testid="dealdesk-analysis-optimise"><Sparkles size={14} /> Optimise</PrimaryButton>
                   ) : null}
                 </div>}>
        <Verdict res={ask} />
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="min-w-0"><ChartTitle title="RAROC waterfall" info={<WaterfallInfo res={ask} />} /><WaterfallChart res={ask} /></div>
          <div className="min-w-0"><ChartTitle title={b.heatmap.x === "commission_bps" ? "RAROC over commission and tenor" : "RAROC over margin and tenor"} info={<HeatmapInfo grid={b.heatmap} ask={b.proposal.ask} />} /><IsoRarocHeatmap grid={b.heatmap} ask={b.proposal.ask} rec={b.state.recommended ?? null} /></div>
        </div>
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="RAROC against amount" className="min-w-0" info={<AmountInfo grid={b.amount_curve} ask={b.proposal.ask} ccy={b.proposal.ask.currency} />}><RarocAmountCurve grid={b.amount_curve} ask={b.proposal.ask} rec={b.state.recommended ?? null} ccy={b.proposal.ask.currency} /></Section>
        <Section title="Lever impact on RAROC" className="min-w-0" info={<TornadoInfo t={b.tornado} />}><TornadoChart t={b.tornado} /></Section>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Constraint headroom" className="min-w-0" info={<HeadroomInfo rows={ask.constraints} />}>
          <HeadroomChart rows={ask.constraints} /></Section>
        <Section title="RAROC by obligor grade" className="min-w-0" info={<RatingInfo rows={ratingRows(b)} hurdle={ask.metrics.hurdle} />}>
          <RatingChart rows={ratingRows(b)} hurdle={ask.metrics.hurdle} /></Section>
      </div>
      <Section title="Limits after the deal" className="min-w-0"><div className="overflow-x-auto"><ConstraintTable rows={ask.constraints} /></div></Section>
    </div>
  );
}

// ------------------------------------------------------------------ 3 Structure

const CHANGE_LABEL: Record<string, [string, string]> = {
  amount: ["Amount", "m"], tenor_years: ["Tenor", " years"], grace_years: ["Grace", " years"], margin_bps: ["Margin", " bps"],
  upfront_fee_bps: ["Upfront fee", " bps"], commitment_fee_bps: ["Commitment fee", " bps"], commission_bps: ["Commission", " bps"],
  cash_margin_pct: ["Cash margin", "%"], guarantee_coverage_pct: ["Guarantee cover", "%"], balloon_pct: ["Balloon", "%"],
  amortisation: ["Repayment", ""], structure: ["Structure", ""], covenant_package: ["Covenants", ""],
  funded_share_pct: ["Funded share", "%"], utilisation_pct: ["Utilisation", "%"],
  // Round D: the Deposit requirement term
  deposit_type: ["Deposit requirement", ""], deposit_pct: ["Deposit (% of limit)", "%"], deposit: ["Deposit requirement", ""],
};

function changeText(c: Solution["changes"][number]): string {
  if (c.field === "collateral_ids") return "Additional collateral";
  if (c.field === "guarantee_id") return c.value ? "Guarantee added" : "Guarantee released";
  const [label, unit] = CHANGE_LABEL[c.field] ?? [cap(c.field.replace(/_/g, " ")), ""];
  void unit;
  return `${label} ${leverRead(c.field, c.ask)} → ${leverRead(c.field, c.value)}`;
}

function OfferCard({ o, onUse, active }: { o: Solution; onUse: () => void; active: boolean }) {
  const changes = o.changes.filter((c) => c.field !== "guarantee_id" || !o.changes.some((x) => x.field === "guarantee_coverage_pct")).map(changeText);
  return (
    <button type="button" onClick={onUse} data-testid={`dealdesk-offer-${o.label.toLowerCase().replace(/\W+/g, "-")}`}
            className={cn("flex h-full flex-col rounded-lg border bg-surface p-4 text-left hover:border-accent", active ? "border-accent ring-1 ring-accent" : "border-border")}>
      <p className="text-[13px] font-semibold text-text-primary">{o.label}</p>
      <p className="mt-2 text-[20px] font-semibold tabular-nums text-text-primary">{rate(o.metrics.lifetime_raroc)}</p>
      <p className="text-[12px] tabular-nums text-text-secondary">SVA {money(o.metrics.sva)} · {o.approval.level}</p>
      <ul className="mt-2 space-y-0.5 text-[12px] text-text-secondary">{changes.length ? changes.map((c) => <li key={c}>{c}</li>) : <li>As asked</li>}</ul>
    </button>
  );
}

export function StructureStep({ b, opt, current, onCurrent, onRecommend, busy, onPick, onStress, structureKey, structureLabel, onSave }: {
  b: Bundle; opt: OptimizeResult | null; current: Analysis; onCurrent: (r: Analysis) => void;
  onRecommend: (t: Terms) => void; onOptimise?: () => void; busy: boolean; settings?: React.ReactNode;
  onPick?: (t: Terms | null) => void; onStress?: () => void;
  /** R14 F: the selected structure of the set (pipeline test), and "Save to Your structures" from Structure it yourself. */
  structureKey?: string | null; structureLabel?: string; onSave?: (t: Terms) => void;
}) {
  const p = b.proposal;
  const [picked, setPicked] = React.useState("");
  const pickedTerms = r11PickedTerms(opt, picked, current.terms);
  React.useEffect(() => { onPick?.(pickedTerms); }, [onPick, pickedTerms]);
  const [panelTerms, setPanelTerms] = React.useState<Terms>(current.terms);
  const [panelKey, setPanelKey] = React.useState(0);
  const applyOffer = (t: Terms) => { setPanelTerms(t); setPanelKey((k) => k + 1); void dealdesk.compute(p.proposal_id, t).then(onCurrent); };
  if (!opt) {
    return (
      <Section title="Structure">
        <Empty>Optimise to see the charts, the counter-offers and Structure it yourself (the structure set above is already measured).</Empty></Section>);
  }
  const seen = new Set<string>();
  const offers = [opt.closest, opt.max_sva, ...(opt.counter_offers ?? [])].filter((x): x is Solution => {
    if (!x) return false;
    const k = JSON.stringify(x.terms);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  }).slice(0, 5);
  const cols: { name: string; terms: Terms; res?: Analysis | Solution | null }[] = [{ name: "Ask", terms: p.ask, res: b.ask }];
  bestOffers(opt).forEach((o, i) => cols.push({ name: i === 0 ? "Recommended" : `Alternative ${i}`, terms: o.solution.terms, res: o.solution }));
  cols.push({ name: "Structure it yourself", terms: current.terms, res: current });
  const hardOk = !current.constraints.some((c) => c.status === "breach" && c.kind === "hard");
  const ccy = p.ask.currency;
  const alts = (
    <>
      <AlternativeCards alts={opt.alternatives ?? []} ccy={ccy} base={b.ask.metrics} picked={picked}
                        onUse={(t, label) => { setPicked(label); applyOffer(withNeutral(t)); }} />
      <SingleLeverTable rows={opt.single_lever ?? []} ccy={ccy} onUse={(r) => {
        const t: Terms = { ...withNeutral(p.ask), [r.lever]: r.to } as Terms;
        if (r.lever === "guarantee_coverage_pct" && r.guarantee_id) t.guarantee_id = r.guarantee_id;
        setPicked(r.label); applyOffer(t);
      }} />
    </>
  );
  return (
    <div className="space-y-4" data-testid="dealdesk-step-structure-view">
      {/* PLAN_R10 D4: the same Optimise view for every deal: best tenor and rate, recommended + two alternatives, the charts. */}
      <OptimiseView b={b} opt={opt} picked={picked} busy={busy} onRecommend={onRecommend}
                    onUse={(t, label) => { setPicked(label); applyOffer(withNeutral(t)); }} />
      {/* PLAN_R11 U2: under the structures, in order: forward risk, the stress summary, Test against pipeline. */}
      <R11OptimisePanels b={b} opt={opt} terms={pickedTerms} pickedLabel={picked && pickedTerms !== bestOffers(opt)[0]?.solution.terms ? "Picked" : "Recommended"} onStress={onStress}
                         structureKey={structureKey} structureLabel={structureLabel} />
      <Section title="Term sheet: the ask, the offers and your structure" className="min-w-0"><TermSheet cols={cols} /></Section>
      {/* PLAN_R12 I14 (Session G, mounted by U): "Structure it yourself" with a live comparison against the recommended structure. */}
      <StructureItYourself key={panelKey} proposal={p} terms={panelTerms} onResult={onCurrent} recommended={bestOffers(opt)[0]?.solution ?? null}
               action={<><Chip tone={current.metrics.clears_hurdle ? "positive" : "negative"} testId="dealdesk-panel-raroc">RAROC {rate(current.metrics.lifetime_raroc)}</Chip>
                 <Chip tone={hardOk ? "positive" : "negative"}>{hardOk ? "Hard limits pass" : "Hard limit breached"}</Chip>
                 {onSave ? <SecondaryButton onClick={() => onSave(current.terms)} disabled={busy} data-testid="flow-save-structure">Save to Your structures</SecondaryButton> : null}
                 <PrimaryButton onClick={() => onRecommend(current.terms)} disabled={busy || !current.metrics.clears_hurdle || !hardOk} data-testid="dealdesk-recommend"
                                title={!current.metrics.clears_hurdle ? `RAROC ${rate(current.metrics.lifetime_raroc)} < ${rate(current.metrics.hurdle)} hurdle` : !hardOk ? "A hard limit is breached" : undefined}>
                   Recommend <ArrowRight size={14} /></PrimaryButton></>} />
      <details className="rounded-lg border border-border bg-surface" data-testid="dealdesk-more-structures">
        <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-text-secondary">More structures: every counter-offer, alternatives, single levers, the frontier and binding constraints</summary>
        <div className="space-y-4 p-4 pt-0">
          {opt.feasible ? (
            <Section title="Counter-offers" testId="dealdesk-offers">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {offers.slice(0, 4).map((o, i) => <OfferCard key={`${o.label}-${i}`} o={o} active={picked === o.label} onUse={() => { setPicked(o.label); applyOffer(o.terms); }} />)}
              </div>
            </Section>
          ) : (
            <Section title="No structure clears" testId="dealdesk-relaxation"
                     info="No combination of the levers inside the market bounds clears the hurdle and every hard limit. These are the smallest relaxations, lever by lever: the decline rationale.">
              <table className={tableCls}>
                <thead><tr><th className={thCls}>Lever</th><th className={cn(thCls, "text-right")}>Now</th><th className={cn(thCls, "text-right")}>Needed</th><th className={thCls}></th></tr></thead>
                <tbody>{(opt.relaxation ?? []).map((r, i) => (
                  <tr key={`${r.lever}-${i}`}><td className={tdCls}>{cap(r.lever.replace(/_/g, " "))}</td>
                    <td className={cn(tdCls, "text-right")}>{relaxRead(r.unit, r.from)}</td>
                    <td className={cn(tdCls, "text-right")}>{r.to === null ? "Not reachable" : relaxRead(r.unit, r.to)}</td>
                    <td className={tdCls}>{r.beyond_market ? <Chip tone="warning">Beyond market</Chip> : null}</td></tr>))}</tbody>
              </table>
            </Section>)}
          {alts}
          <div className="grid gap-4 xl:grid-cols-2">
            <Section title="Distance from the ask against value" className="min-w-0" info={opt.frontier.length ? <FrontierInfo opt={opt} /> : undefined}>
              {opt.frontier.length ? <FrontierChart opt={opt} /> : <Empty>No feasible structure.</Empty>}</Section>
            {opt.binding.length ? (
              <Section title="Binding constraints" className="min-w-0" info="The constraints that hold the closest-to-ask structure where it is, and the SVA gained per unit of relaxation.">
                <table className={tableCls} data-testid="dealdesk-binding">
                  <thead><tr><th className={thCls}>Constraint</th><th className={cn(thCls, "text-right")}>SVA gained per unit</th><th className={thCls}>Per</th></tr></thead>
                  <tbody>{opt.binding.map((x, i) => (
                    <tr key={`${x.constraint}-${i}`}><td className={cn(tdCls, "whitespace-normal")}>{x.label ?? cap(x.constraint.replace(/_/g, " "))}</td><td className={cn(tdCls, "text-right")}>{x.shadow_price === null || x.shadow_price === undefined ? "–" : `SAR ${fmt.count(x.shadow_price * 1e6)}`}</td>
                      <td className={tdCls}>{x.unit === "SAR m" ? "SAR million" : x.unit}</td></tr>))}</tbody>
                </table>
              </Section>) : null}
          </div>
        </div>
      </details>
    </div>
  );
}

// ------------------------------------------------------------------ 3a Under the structures (PLAN_R11 U2)

/** The structures the forward-risk panel scores: the ask, the recommended structure and the alternatives. */
export function r11Structures(b: Bundle, opt: OptimizeResult | null): R11Structure[] {
  const out: R11Structure[] = [{ key: "ask", label: "Ask", role: "asked", terms: b.proposal.ask }];
  bestOffers(opt).forEach((o, i) => out.push(i === 0 ? { key: "recommended", label: "Recommended", role: "recommended", terms: o.solution.terms }
    : { key: `alternative_${i}`, label: o.title, role: "alternative", terms: o.solution.terms }));
  return out;
}

/**
 * The structure picked in Optimise: an offer tile by its title, the term panel when an alternative or a single lever
 * was loaded into it, else the recommended structure (null when nothing clears).
 */
export function r11PickedTerms(opt: OptimizeResult | null, picked: string, panel: Terms): Terms | null {
  const offers = bestOffers(opt);
  if (!offers.length) return null;
  const hit = offers.find((o) => o.title === picked);
  if (hit) return hit.solution.terms;
  return picked ? panel : offers[0].solution.terms;
}

export function R11OptimisePanels({ b, opt, terms, pickedLabel, onStress, structureKey, structureLabel }: {
  b: Bundle; opt: OptimizeResult | null; terms: Terms | null; pickedLabel: string; onStress?: () => void;
  /** R14 F (K21): the structure selected in the structure set; the pipeline test runs on it and says so. */
  structureKey?: string | null; structureLabel?: string;
}) {
  const pid = b.proposal.proposal_id;
  const ready = Boolean(opt && terms);
  const structures = React.useMemo(() => r11Structures(b, opt), [b, opt]);
  const recommended = bestOffers(opt)[0]?.solution.terms ?? null;
  return (
    <div className="space-y-4" data-testid="dealdesk-r11-panels">
      <Collapsible id="forward-risk" testId="dealdesk-panel-forward">
        <ForwardRiskPanel proposalId={pid} structures={structures} />
      </Collapsible>
      <Collapsible id="stress-summary" testId="dealdesk-panel-stress">
        <StressSummary proposalId={pid} terms={terms ?? b.proposal.ask} recommendedTerms={recommended} label={pickedLabel} onOpen={onStress} />
      </Collapsible>
      <Collapsible id="pipeline-test" testId="dealdesk-panel-pipeline">
        <Section title="Test against pipeline" testId="dealdesk-pipeline-bar">
          <div className="min-w-0" data-ready={ready ? "true" : "false"} data-structure={structureLabel ?? pickedLabel}>
            {/* R14 F (K21): on the selected structure, labelled, with this deal's own lines; R11's button when no set is loaded. */}
            {structureLabel ? <PipelineLinesPanel proposalId={pid} structureKey={structureKey ?? null} structureLabel={structureLabel} />
              : <PipelineTestButton proposalId={pid} terms={terms} ready={ready} />}
          </div>
        </Section>
      </Collapsible>
    </div>
  );
}

// ------------------------------------------------------------------ 4 Stress (PLAN_R11 U1, Session S)

export function StressStep({ b, terms, recommendedTerms, label }: { b: Bundle; terms: Terms; recommendedTerms: Terms | null; label: string }) {
  return (
    <div className="space-y-4" data-testid="dealdesk-step-stress-view">
      <AskLine p={b.proposal} />
      {/* The Stress Lab is its own Section (answer, tiles, heatmap, distance to failure, resilience); the Analysis step keeps its stress table. */}
      <StressLabStep proposalId={b.proposal.proposal_id} terms={terms} recommendedTerms={recommendedTerms} label={label} />
    </div>
  );
}

// ------------------------------------------------------------------ 5 Review (PLAN_R11 U1, Session R)

/**
 * The review workspace: the answer bar, its tiles, the memo line by line, findings, counter-proposals, conditions, precedent.
 * PLAN_R12 I17: it is credit's workspace; in the Prepare view (business) it gives way to Session B's pre-flight once mounted.
 */
export function ReviewStep({ b, view = "review" }: { b: Bundle; view?: "prepare" | "review" }) {
  if (view === "prepare" && hasSlot("Review")) return null;
  return (
    <div className="space-y-4" data-testid="dealdesk-step-review-view">
      <ReviewWorkspace proposalId={b.proposal.proposal_id} />
    </div>
  );
}

export function relaxRead(unit: string, v: number | string): string {
  if (typeof v === "string") return v;
  if (unit === "ratio" || unit === "share") return rate(v);
  if (unit === "SAR m") return money(v);
  if (unit === "x") return `${fmt.ratio(v)}x`;
  if (unit === "bps") return bps(v);
  return `${fmt.num(v)} ${unit}`.trim();
}

// ------------------------------------------------------------------ 6 Recommendation

export function RecommendationStep({ b, rec, onDraft, onSave, busy }: {
  b: Bundle; rec: Analysis; onDraft: () => void; onSave: () => void; busy: boolean;
}) {
  const soft = rec.constraints.filter((c) => c.status === "breach" && c.kind === "soft");
  const s = b.stress;
  return (
    <div className="space-y-4" data-testid="dealdesk-step-recommendation-view">
      <Section title="Recommendation" testId="dealdesk-recommendation"
               action={<PrimaryButton onClick={onSave} disabled={busy} data-testid="dealdesk-save">Save analysis</PrimaryButton>}>
        <div className="grid gap-4 xl:grid-cols-5">
          <div className="min-w-0 xl:col-span-3"><TermSheet cols={[{ name: "Ask", terms: b.proposal.ask, res: b.ask }, { name: "Recommended", terms: rec.terms, res: rec }]} /></div>
          <div className="min-w-0 space-y-3 xl:col-span-2">
            <Verdict res={rec} />
            <div className="rounded-lg border border-border p-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Required approval</p>
              <p className="mt-1 text-[18px] font-semibold text-text-primary" data-testid="dealdesk-approval">{rec.approval.level}</p>
              <ul className="mt-2 space-y-0.5 text-[12px] text-text-secondary">{rec.approval.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
            {soft.length ? (
              <div className="rounded-lg border border-warning/40 bg-warning-muted p-4" data-testid="dealdesk-soft">
                <p className="text-[12px] font-semibold text-warning">Soft breaches for escalation</p>
                <ul className="mt-1 space-y-0.5 text-[12px] text-text-secondary">{soft.map((c) => <li key={c.name}>{c.label}: {constraintRead(c)} against {constraintRead(c, c.limit)}</li>)}</ul>
              </div>) : null}
            <button type="button" onClick={onDraft} disabled={busy} data-testid="dealdesk-draft"
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[12px] text-text-secondary hover:border-accent disabled:opacity-40">
              <Sparkles size={13} /> Draft the risk opinion</button>
          </div>
        </div>
      </Section>
      <Section title="Stress" info={<StressInfo s={s} />}
               action={<Chip tone={s.robustness_notches >= 2 ? "positive" : "warning"} testId="dealdesk-robustness">Robust to {s.robustness_notches} notch{s.robustness_notches === 1 ? "" : "es"}</Chip>}>
        <div className="overflow-x-auto"><table className={tableCls} data-testid="dealdesk-stress">
          <thead><tr><th className={thCls}>Scenario</th><th className={cn(thCls, "text-right")}>RAROC</th><th className={cn(thCls, "text-right")}>SVA</th>
            <th className={cn(thCls, "text-right")}>EL (PV)</th><th className={cn(thCls, "text-right")}>Client DSCR</th><th className={thCls}>Hurdle</th></tr></thead>
          <tbody>
            <tr className="bg-canvas"><td className={cn(tdCls, "font-medium")}>Base</td><td className={cn(tdCls, "text-right")}>{rate(s.base.lifetime_raroc)}</td>
              <td className={cn(tdCls, "text-right")}>{money(s.base.sva)}</td><td className={tdCls} /><td className={tdCls} /><td className={tdCls} /></tr>
            {s.rows.map((r) => (
              <tr key={r.scenario}><td className={tdCls}>{r.label}</td><td className={cn(tdCls, "text-right")}>{rate(r.lifetime_raroc)}</td>
                <td className={cn(tdCls, "text-right")}>{money(r.sva)}</td><td className={cn(tdCls, "text-right")}>{money(r.el_lifetime_pv)}</td>
                <td className={cn(tdCls, "text-right")}>{r.dscr_post === null ? "–" : `${fmt.ratio(r.dscr_post)}x`}</td>
                <td className={tdCls}>{r.clears_hurdle ? <Chip tone="positive">Clears</Chip> : <Chip tone="negative">Below</Chip>}</td></tr>))}
          </tbody>
        </table></div>
      </Section>
    </div>
  );
}
