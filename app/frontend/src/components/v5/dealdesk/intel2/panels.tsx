"use client";

/**
 * R14 i: the D6-D13 panels. Each is compact: the plain-words block first (K34), one headline sentence, then the table
 * or list that carries the numbers, every number with its (i) lineage. The full method sits in the (i) of the title.
 */

import * as React from "react";
import Link from "next/link";

import { Chip, Section, tableCls, tdCls, thCls } from "../kit";
import { useIntel2 } from "./api";
import {
  type Contagion, type Frontier, type Precedents, type Premortem, type Pricing, type Rehearsal, type RenewalDiff, type Revenue,
  bps, directionTone, mn, pct, signedBps, verdictTone,
} from "./model";
import { Headline, Lineage, Loading, Num, PlainWords, StructureLine } from "./parts";

type P = { proposalId: string; structure?: string };

function Shell<T extends { plain: { lines: string[] }; headline: string; structure?: Rehearsal["structure"] }>({ title, testId, info, r, children }: {
  title: string; testId: string; info: React.ReactNode; r: { data: T | null; error: string | null }; children: (d: T) => React.ReactNode;
}) {
  return (
    <Section title={title} testId={testId} info={info}>
      {r.data ? (<>
        <PlainWords lines={r.data.plain.lines} speak testId={`${testId}-plain`} />
        <StructureLine s={r.data.structure} />
        {children(r.data)}
      </>) : <Loading error={r.error} />}
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ D6
export function FrontierView({ d }: { d: Frontier }) {
  const word = d.price_lever === "margin_bps" ? "margin" : "commission";
  return (<>
    <Headline testId="i-frontier-headline">{d.headline}</Headline>
    <h3 className="mb-1 mt-3 text-[12px] font-medium text-text-secondary">What each concession is worth (bps of {word} at the same value to the bank)</h3>
    <table className={tableCls} data-testid="i-frontier-worth">
      <thead><tr><th className={thCls}>The client gives</th><th className={thCls}>Worth</th><th className={thCls}>RAROC after</th></tr></thead>
      <tbody>{d.worth.map((w) => (
        <tr key={w.key}><td className={tdCls}>{w.label}</td>
          <td className={tdCls}>{w.available && w.worth_bps ? <Num f={w.worth_bps}>{signedBps(w.worth_bps.value)}</Num> : <span className="text-text-muted">{w.why ?? "n/a"}</span>}</td>
          <td className={tdCls}>{w.raroc_after ? <Num f={w.raroc_after}>{pct(w.raroc_after.value)}</Num> : "–"}</td></tr>))}
      </tbody>
    </table>
    <h3 className="mb-1 mt-3 text-[12px] font-medium text-text-secondary">Three counter-offers, best for the bank first</h3>
    <ol className="space-y-1.5" data-testid="i-frontier-offers">
      {d.offers.map((o) => (
        <li key={o.key} className="flex flex-wrap items-center gap-2 rounded-md border border-border/70 px-3 py-2 text-[12.5px]" data-testid={`i-offer-${o.rank}`}>
          <span className="w-4 tabular-nums text-text-muted">{o.rank}</span>
          <span className="min-w-0 flex-1 font-medium text-text-primary">{o.label}</span>
          <Num f={o.raroc}>RAROC {pct(o.raroc.value)}</Num>
          <Num f={o.sva}>SVA {mn(o.sva.value, 2)}</Num>
          <Num f={o.client_cost}><span className="text-text-muted">client cost {mn(o.client_cost.value, 2)} a year</span></Num>
          {o.acceptable ? <Chip tone="positive">clears the hurdle</Chip> : <Chip tone="negative">does not clear</Chip>}
        </li>))}
    </ol>
  </>);
}

export function NegotiationFrontierPanel({ proposalId, structure }: P) {
  const r = useIntel2<Frontier>(proposalId, "frontier", structure);
  return <Shell title="Negotiation frontier" testId="i-frontier-panel" r={r}
                info={<p>What each thing the client can give (10% cash margin, a year less tenor, SAR 10m less amount) is worth in basis points of
                  price at the same value to the bank, and three ready counter-offers a client usually accepts (price at most +25 bps), each priced by the
                  deal engine and ranked by SVA. Client cost uses labelled assumptions: 2% carry on cash margin, 0.5% a year for a shorter tenor, 1% of an amount cut.</p>}>
    {(d) => <FrontierView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D7
export function PremortemView({ d }: { d: Premortem }) {
  return (<>
    <Headline testId="i-premortem-headline">{d.headline}</Headline>
    <ol className="mt-3 space-y-2" data-testid="i-premortem-paths">
      {d.paths.map((x) => (
        <li key={x.key} className="rounded-md border border-border/70 px-3 py-2 text-[12.5px]" data-testid={`i-path-${x.rank}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-4 tabular-nums text-text-muted">{x.rank}</span>
            <span className="min-w-0 flex-1 font-medium text-text-primary">{x.driver}</span>
            <Num f={x.probability}>{pct(x.probability.value)} a year</Num>
            <Chip tone={x.speed_class === "fast" ? "negative" : x.speed_class === "medium" ? "warning" : "neutral"}>{x.speed}</Chip>
          </div>
          <p className="mt-1 pl-6 text-[12px] leading-5 text-text-secondary">
            {x.breaking_severity === "beyond severe"
              ? `Does not go bad even at severe stress${x.what_breaks.length ? ` (at severe only ${x.what_breaks.join(", ")} break)` : ""}. `
              : x.breaking_severity === "already failed" ? "The party has already failed. "
              : `Goes bad at ${x.breaking_severity} stress${x.what_breaks.length ? ` (${x.what_breaks.join(", ")})` : ""}. `}
            First warning: <span className="text-text-primary">{x.first_warning}</span>{x.lead.startsWith("no break") ? "." : `; ${x.lead}.`}
          </p>
        </li>))}
    </ol>
    <p className="mt-2 text-[11px] text-text-muted">{d.note}</p>
  </>);
}

export function DefaultPremortemPanel({ proposalId, structure }: P) {
  const r = useIntel2<Premortem>(proposalId, "premortem", structure);
  return <Shell title="Default pre-mortem" testId="i-premortem-panel" r={r}
                info={<p>The deal's own stress ladder, one path per driver: the mildest severity at which DSCR falls below 1.0x or the deal goes to Stage 2 or
                  is downgraded. Probability = how often the driver moved that much in one year (calibrated severities, data window in each source); group
                  contagion uses an expert transmission by status. The first warning is the covenant or trigger that breaks at a milder severity.</p>}>
    {(d) => <PremortemView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D8
export function PrecedentsView({ d }: { d: Precedents }) {
  return (<>
    <Headline testId="i-precedents-headline">{d.headline}</Headline>
    {d.inconsistent ? <div className="mt-2"><Chip tone="warning">Decision would be inconsistent with the precedents</Chip></div> : null}
    <ol className="mt-3 space-y-1.5" data-testid="i-precedents-list">
      {d.precedents.map((x, i) => (
        <li key={x.id} data-testid={`i-precedent-${i + 1}`}>
          <details className="rounded-md border border-border/70 px-3 py-2 open:bg-surface-hover/40">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 text-[12.5px]">
              <span className="w-4 tabular-nums text-text-muted">{i + 1}</span>
              <Link href={x.href} className="min-w-0 flex-1 truncate font-medium text-text-primary hover:underline">{x.name}</Link>
              <Chip tone={x.decision.startsWith("declined") ? "negative" : x.decision.startsWith("approved") ? "positive" : "warning"}>{x.decision}</Chip>
              <Num f={x.similarity}><span className="text-text-muted">similarity {(x.similarity.value ?? 0).toFixed(2)}</span></Num>
            </summary>
            <div className="mt-1.5 space-y-0.5 pl-6 text-[12px] leading-5 text-text-secondary">
              <p>{x.sector} · {x.rating} · <Num f={x.amount}>{mn(x.amount.value, 0)}</Num> · {x.date}{x.level ? ` · ${x.level}` : ""}</p>
              <p>Conditions: {x.conditions}</p>
              <p>Performance: {x.performance}</p>
              <p className="text-text-muted">Similarity basis: {x.basis_text}</p>
            </div>
          </details>
        </li>))}
    </ol>
    <p className="mt-2 text-[11px] text-text-muted">{d.note}</p>
  </>);
}

export function PrecedentExplorerPanel({ proposalId, structure }: P) {
  const r = useIntel2<Precedents>(proposalId, "precedents", structure);
  return <Shell title="Precedent explorer" testId="i-precedents-panel" r={r}
                info={<p>The five past deals closest to this one: sector 35%, rating 25% (less a quarter per notch), product family 15%, size 15% and main
                  collateral 10%. Past deals are the bank's credit-decision history (performance over the next four quarters from the book) and decided Deal Desk deals.</p>}>
    {(d) => <PrecedentsView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D9
export function PricingView({ d }: { d: Pricing }) {
  const max = Math.max(1, ...d.histogram.map((h) => h.n));
  return (<>
    <Headline testId="i-pricing-headline">{d.headline}</Headline>
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px]">
      <Num f={d.price}>Proposed {bps(d.price.value)}</Num>
      <Num f={d.percentile}>Percentile {Math.round(d.percentile.value ?? 0)}</Num>
      <Num f={d.quartiles.p50}>Median {bps(d.quartiles.p50.value)}</Num>
      <Num f={d.breakeven}>Breakeven {bps(d.breakeven.value)}</Num>
      <Num f={d.peers}><span className="text-text-muted">{d.peers.value} peers</span></Num>
    </div>
    <div className="mt-3 flex h-16 items-end gap-[2px]" data-testid="i-pricing-histogram" aria-label="Peers by price band">
      {d.histogram.map((h) => (
        <div key={h.from_bps} title={`${h.from_bps}–${h.to_bps} bps: ${h.n} facilities${h.deal ? " (this deal)" : ""}`}
             className={h.deal ? "flex-1 rounded-t bg-accent" : "flex-1 rounded-t bg-border"} style={{ height: `${Math.max(3, (h.n / max) * 100)}%` }} />))}
    </div>
    <div className="mt-0.5 flex justify-between text-[10.5px] tabular-nums text-text-muted">
      <span>{d.histogram[0]?.from_bps ?? ""} bps</span><span>{d.histogram[d.histogram.length - 1]?.to_bps ?? ""} bps</span>
    </div>
    <p className="mt-2 text-[11.5px] text-text-muted">Peers: {Object.entries(d.basis_used).map(([k, v]) => `${k} ${v}`).join(" · ")}
      {d.dropped.length ? ` (dropped for too few peers: ${d.dropped.join(", ")})` : ""}</p>
  </>);
}

export function PricingBenchmarkPanel({ proposalId, structure }: P) {
  const r = useIntel2<Pricing>(proposalId, "pricing", structure);
  return <Shell title="Pricing benchmark" testId="i-pricing-panel" r={r}
                info={<p>The proposed margin (commission on an unfunded line) against the margins the bank set at origination on similar corporate facilities:
                  same rating bucket, sector, product family and tenor band, relaxed in that order when fewer than 30 match. Breakeven is the price at
                  which the deal just earns its hurdle on the same structure.</p>}>
    {(d) => <PricingView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D10
export function RevenueView({ d }: { d: Revenue }) {
  return (<>
    <div className="mb-2"><Chip tone={verdictTone(d.verdict)} testId="i-revenue-verdict">Revenue {d.verdict}</Chip></div>
    <Headline testId="i-revenue-headline">{d.headline}</Headline>
    <table className={`${tableCls} mt-3`} data-testid="i-revenue-bridge">
      <tbody>
        {d.revenue ? <tr><td className={tdCls}>Reported revenue ({d.period.revenue})</td><td className={`${tdCls} text-right`}><Num f={d.revenue}>{mn(d.revenue.value)}</Num></td></tr> : null}
        {d.inflows.map((x) => (
          <tr key={x.label}><td className={tdCls}>{x.label}</td><td className={`${tdCls} text-right`}><Num f={x.value}>{mn(x.value.value)}</Num></td></tr>))}
        <tr><td className={`${tdCls} font-medium`}>Sales-backed inflows (after 15% VAT)</td><td className={`${tdCls} text-right font-medium`}><Num f={d.sales_backed}>{mn(d.sales_backed.value)}</Num></td></tr>
        <tr><td className={`${tdCls} font-medium`}>Covers</td><td className={`${tdCls} text-right font-medium`}><Num f={d.coverage}>{pct(d.coverage.value, 0)}</Num></td></tr>
        {d.gap.value ? <tr><td className={tdCls}>Revenue not backed by cash</td><td className={`${tdCls} text-right text-negative`}><Num f={d.gap}>{mn(d.gap.value)}</Num></td></tr> : null}
        {d.vat_coverage ? <tr><td className={tdCls}>VAT returns declare</td><td className={`${tdCls} text-right`}><Num f={d.vat_coverage}>{pct(d.vat_coverage.value, 0)}</Num></td></tr> : null}
      </tbody>
    </table>
    {d.implied ? (
      <p className="mt-2 text-[12px] text-text-secondary" data-testid="i-revenue-implied">If the gap is not real revenue: DSCR <Num f={d.implied.dscr_now}>{d.implied.dscr_now.value?.toFixed(2)}x</Num> →{" "}
        <Num f={d.implied.dscr_after}>{d.implied.dscr_after.value?.toFixed(2)}x</Num>, Debt/EBITDA <Num f={d.implied.leverage_now}>{d.implied.leverage_now.value?.toFixed(2)}x</Num> →{" "}
        <Num f={d.implied.leverage_after}>{d.implied.leverage_after.value?.toFixed(2)}x</Num>.</p>) : null}
    <p className="mt-2 text-[11px] text-text-muted">Inflows {d.period.inflows}. {d.note}</p>
  </>);
}

export function RevenueTruthPanel({ proposalId, structure }: P) {
  const r = useIntel2<Revenue>(proposalId, "revenue", structure);
  return <Shell title="Revenue truth check" testId="i-revenue-panel" r={r}
                info={<p>Reported revenue against the money that came into the client's accounts over the last 12 months: credit turnover at this bank, inflows
                  at other banks through open banking (less transfers between the client's own accounts), divided by 1.15 for VAT; and the sales declared in
                  the four VAT returns. Supported from 95%, partly supported from 85%.</p>}>
    {(d) => <RevenueView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D11
export function RenewalDiffView({ d }: { d: RenewalDiff }) {
  if (!d.applies) return <Headline testId="i-renewal-headline">{d.headline}</Headline>;
  return (<>
    <Headline testId="i-renewal-headline">{d.headline}</Headline>
    {d.approval ? <p className="mt-1 text-[11.5px] text-text-muted">Last approval: {d.approval.ref} · {d.approval.date}{d.approval.authority ? ` · ${d.approval.authority}` : ""} ({d.approval.basis})</p> : null}
    <div className="mt-3 max-w-full overflow-x-auto">
      <table className={tableCls} data-testid="i-renewal-table">
        <thead><tr><th className={thCls}>Area</th><th className={thCls}>Item</th><th className={thCls}>Then</th><th className={thCls}>Now</th><th className={thCls}>Change</th></tr></thead>
        <tbody>{d.rows.map((x, i) => (
          <tr key={i} data-direction={x.direction}>
            <td className={`${tdCls} text-text-muted`}>{x.area}</td>
            <td className={`${tdCls} max-w-[340px] whitespace-normal`}><span className="block max-w-[340px] break-words">{x.item}</span>
              {x.note ? <span className="line-clamp-2 block max-w-[340px] whitespace-normal break-words text-[11px] text-text-muted" title={x.note}>{x.note}</span> : null}</td>
            <td className={tdCls}>{x.then}</td>
            <td className={`${tdCls} max-w-[260px] whitespace-normal`}>{x.now}</td>
            <td className={tdCls}><span className="inline-flex items-center gap-1"><Chip tone={directionTone(x.direction)}>{x.change}</Chip>
              {x.evidence.length ? <Lineage title={x.item} sources={x.evidence.map((e) => e.source)} /> : null}</span></td>
          </tr>))}
        </tbody>
      </table>
    </div>
  </>);
}

export function RenewalDiffPanel({ proposalId }: P) {
  const r = useIntel2<RenewalDiff>(proposalId, "renewal-diff");
  return <Shell title="Renewal diff" testId="i-renewal-panel" r={r}
                info={<p>For a renewal: what changed since the last approval on file (committee decision, or the bank's decision history for book clients):
                  limits, rating, financials, account conduct, the conditions that approval set, covenant tests and the group. A change counts from 5%
                  (0.1x on ratios, one notch, one event).</p>}>
    {(d) => <RenewalDiffView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D12
export function ContagionView({ d }: { d: Contagion }) {
  const adverse = d.parties.filter((x) => x.adverse);
  const rest = d.parties.filter((x) => !x.adverse);
  return (<>
    <Headline testId="i-contagion-headline">{d.headline}</Headline>
    {adverse.length ? (
      <ul className="mt-3 space-y-2" data-testid="i-contagion-adverse">
        {adverse.map((x) => (
          <li key={x.borrower_id} className="rounded-md border border-negative/30 px-3 py-2 text-[12.5px]" data-testid="i-contagion-party">
            <div className="flex flex-wrap items-center gap-2">
              {x.href ? <Link href={x.href} className="font-medium text-text-primary hover:underline">{x.name}</Link> : <span className="font-medium">{x.name}</span>}
              <Chip tone="negative">{x.status}{x.worst_stage ? ` · stage ${x.worst_stage}` : ""}</Chip>
              <span className="text-text-muted">linked by {x.links.join(", ")}</span>
              <span className="ml-auto"><Num f={x.exposure}>{mn(x.exposure.value)} with us</Num></span>
            </div>
            {x.effect ? (
              <p className="mt-1 text-[12px] leading-5 text-text-secondary">If it fails: {x.effect.channels.join("; ")}. RAROC{" "}
                <Num f={x.effect.raroc_after}>{pct(x.effect.raroc_after.value)}</Num>, {x.effect.clears_after ? "still clears the hurdle" : "no longer clears the hurdle"};
                approval {x.effect.approval_after}.</p>) : null}
          </li>))}
      </ul>) : null}
    {d.combined && adverse.length > 1 ? (
      <p className="mt-2 text-[12px] text-text-secondary">All together: RAROC <Num f={d.combined.raroc_after}>{pct(d.combined.raroc_after.value)}</Num>
        {" "}({d.combined.notches} notches), {d.combined.clears_after ? "still clears" : "does not clear"}.</p>) : null}
    {d.conditions.length ? (
      <div className="mt-2 text-[12px]"><span className="font-medium text-text-primary">Condition: </span><span className="text-text-secondary">{d.conditions[0].text}</span></div>) : null}
    {rest.length ? (
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Other connected parties ({rest.length})</summary>
        <ul className="mt-1 space-y-0.5 text-[12px] text-text-secondary">
          {rest.map((x) => <li key={x.borrower_id}>{x.name} · {x.status} · linked by {x.links.join(", ")} · <Num f={x.exposure}>{mn(x.exposure.value)}</Num></li>)}
        </ul>
      </details>) : null}
  </>);
}

export function GroupContagionPanel({ proposalId, structure }: P) {
  const r = useIntel2<Contagion>(proposalId, "contagion", structure);
  return <Shell title="Group contagion on the deal" testId="i-contagion-panel" r={r}
                info={<p>Every company linked to the borrower (group, guarantee, shared collateral, board, ownership) with its status in the bank's book today.
                  For each one in Stage 3, litigation or arrears, the deal is re-priced as if it failed: a guarantee the borrower gave is called, a guarantee
                  it received is lost, and the rating drops by association (2 notches for a group link, 1 otherwise).</p>}>
    {(d) => <ContagionView d={d} />}
  </Shell>;
}

// ------------------------------------------------------------------------------------------------ D13 (K29)
export function RehearsalView({ d }: { d: Rehearsal }) {
  return (<>
    <p className="mb-2 rounded-md bg-surface-hover/60 px-3 py-2 text-[12px] leading-5 text-text-secondary" data-testid="i-rehearsal-header">{d.header}</p>
    <Headline testId="i-rehearsal-headline">{d.headline}</Headline>
    <ol className="mt-3 space-y-1.5">
      {d.questions.map((q) => (
        <li key={q.id} data-testid={`i-question-${q.rank}`}>
          <details className="group rounded-md border border-border/70 px-3 py-2 open:bg-surface-hover/40">
            <summary className="flex cursor-pointer list-none items-start gap-2 text-[13px] text-text-primary">
              <span className="w-4 shrink-0 tabular-nums text-text-muted">{q.rank}</span>
              <span className="min-w-0 flex-1">{q.question}</span>
              <Chip tone={q.avoided ? "warning" : "positive"} title={q.avoided ? q.avoided_reason : undefined} testId={`i-question-${q.rank}-status`}>{q.status}</Chip>
            </summary>
            <div className="mt-2 space-y-1.5 pl-6 text-[12px] leading-5">
              <p className="text-text-primary"><span className="font-medium">Suggested answer: </span>{q.suggested_answer}</p>
              <div className="flex items-start gap-1.5 text-text-secondary">
                <span className="min-w-0 flex-1"><span className="font-medium">Evidence: </span>{q.fact}</span>
                <Lineage title="Where the evidence comes from" sources={q.evidence.map((e) => e.source)}>
                  <p>Raised from: {q.source}.{q.avoided ? ` ${q.avoided_reason}` : ""}</p>
                </Lineage>
              </div>
            </div>
          </details>
        </li>))}
    </ol>
    {d.avoids.items.length ? (
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Questions the proposal avoids ({d.avoids.items.length})</summary>
        <p className="mt-1 text-[11.5px] text-text-muted">{d.avoids.note}</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-[12px] text-text-secondary">
          {d.avoids.items.map((a) => <li key={a.id}>{a.question} <span className="text-text-muted">({a.reason})</span></li>)}
        </ul>
      </details>) : null}
  </>);
}

export function CommitteeRehearsalPanel({ proposalId, structure }: P) {
  const r = useIntel2<Rehearsal>(proposalId, "rehearsal", structure);
  return <Shell title="Committee questions" testId="i-rehearsal-panel" r={r}
                info={<p>The five to seven questions a credit committee is most likely to ask, scored from the review findings, the SWOT, the stress verdict,
                  the group, earlier committee conditions and conditions set on similar deals (same sector, stated basis), on the selected structure. Each has a
                  suggested answer written from the other intelligence panels and the evidence behind it.</p>}>
    {(d) => <RehearsalView d={d} />}
  </Shell>;
}

export const INTEL2_PANELS = {
  frontier: NegotiationFrontierPanel, premortem: DefaultPremortemPanel, precedents: PrecedentExplorerPanel, pricing: PricingBenchmarkPanel,
  revenue: RevenueTruthPanel, "renewal-diff": RenewalDiffPanel, contagion: GroupContagionPanel, rehearsal: CommitteeRehearsalPanel,
} as const;

