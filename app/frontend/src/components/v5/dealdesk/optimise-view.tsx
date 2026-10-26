"use client";

/**
 * PLAN_R10 D4: what Optimise shows, with the same structure for every deal (DD-01..15 and uploaded proposals):
 *
 *   1. the best tenor and price we can offer (one line, from the iso-RAROC grid and the engine breakeven);
 *   2. three offers side by side: the recommended structure and two alternatives, each with RAROC, SVA, approval
 *      and the terms changed from the ask (or the smallest relaxations when nothing clears);
 *   3. the hurdle-rate chart (iso-RAROC heatmap over price × tenor with the hurdle contour, the ask and the
 *      recommendation marked), RAROC against tenor and RAROC against amount.
 */

import * as React from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Bundle, type OptimizeResult, type Solution, type Terms, bps, cap, leverRead, money, rate, years } from "@/lib/v5/dealdesk";
import { bestOffers, bestTenorRate, rarocByTenor } from "@/lib/v5/dealdesk-offer";

import { IsoRarocHeatmap, RarocAmountCurve, RarocTenorCurve } from "./charts";
import { AmountInfo, HeatmapInfo } from "./explain";
import { ChartTitle, Chip, PrimaryButton, Section } from "./kit";
import { SHORT } from "./alternatives";
import { relaxRead } from "./steps";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

export const KEY_TERMS: [string, string][] = [
  ["amount", "Amount"], ["tenor_years", "Tenor"], ["margin_bps", "Margin"], ["commission_bps", "Commission"], ["upfront_fee_bps", "Upfront fee"],
];

function OfferTile({ s, title, recommended, ask, active, onUse, testId }: {
  s: Solution; title: string; recommended: boolean; ask: Terms; active: boolean; onUse: () => void; testId: string;
}) {
  const changes = s.changes.filter((c) => !KEY_TERMS.some(([k]) => k === c.field)).map((c) => `${leverRead(c.field, c.ask, ask.currency)} → ${leverRead(c.field, c.value, ask.currency)}`);
  const changedLabel = (k: string) => s.changes.find((c) => c.field === k) ? "font-semibold text-accent" : "text-text-primary";
  const price = ask.facility_type === "term_loan" || ask.facility_type === "revolver" ? "margin_bps" : "commission_bps";
  return (
    <div className={cn("flex min-w-0 flex-col rounded-lg border bg-surface p-3", active ? "border-accent ring-1 ring-accent" : "border-border")} data-testid={testId}>
      <div className="flex items-center gap-2">
        <p className="min-w-0 truncate text-[12px] font-semibold text-text-primary" title={title}>{title}</p>
        {recommended ? <Chip tone="accent">Recommended</Chip> : <Chip>Alternative</Chip>}
      </div>
      <div className="mt-1 flex items-baseline gap-3">
        <p className={cn("text-[20px] font-bold tabular-nums", s.metrics.clears_hurdle ? "text-positive" : "text-negative")} data-testid={`${testId}-raroc`}>{rate(s.metrics.lifetime_raroc)}</p>
        <p className="text-[12px] tabular-nums text-text-secondary">SVA <b className="text-text-primary" data-testid={`${testId}-sva`}>{money(s.metrics.sva)}</b></p>
      </div>
      <p className="mt-1 break-words text-[12px] tabular-nums text-text-secondary" data-testid={`${testId}-terms`}>
        <span className={changedLabel("amount")}>{money(s.terms.amount, s.terms.currency)}</span> ·{" "}
        <span className={changedLabel("tenor_years")}>{years(s.terms.tenor_years)}</span> ·{" "}
        <span className={changedLabel(price)}>{price === "margin_bps" ? "margin" : "commission"} {bps(s.terms[price])}</span> ·{" "}
        <span className={changedLabel("upfront_fee_bps")}>fee {bps(s.terms.upfront_fee_bps)}</span>
      </p>
      <p className="truncate text-[12px] text-text-muted" title={s.approval.level}>Approval: {s.approval.level}</p>
      {changes.length ? <p className="mt-1 line-clamp-2 break-words text-[11px] text-text-secondary" title={changes.join(" · ")}>Also: {changes.join(" · ")}</p> : null}
      <button type="button" onClick={onUse} className="mt-auto pt-1 text-left text-[12px] text-accent hover:underline" data-testid={`${testId}-use`}>
        Load in the term panel</button>
    </div>
  );
}

export function OptimiseView({ b, opt, picked, onUse, onRecommend, busy }: {
  b: Bundle; opt: OptimizeResult; picked: string; onUse: (t: Terms, label: string) => void; onRecommend?: (t: Terms) => void; busy?: boolean;
}) {
  const p = b.proposal;
  const ask = p.ask;
  const offers = bestOffers(opt);
  const tr = bestTenorRate(b.heatmap, ask, b.ask.metrics.breakeven_margin_bps);
  const tenorRows = rarocByTenor(b.heatmap, ask);
  const rec = offers[0]?.solution.terms ?? null;
  const priceWord = tr.priceKey === "margin_bps" ? "margin" : "commission";
  return (
    <Section title="Optimise: the best tenor and rates we can offer" testId="dealdesk-optimise-view"
             info="The recommended structure is the one closest to the ask that clears the hurdle and every hard limit; the two alternatives are the maximum-value structure and the next distinct structure the optimiser found. Every figure is an engine result."
             action={rec && onRecommend ? (
               <PrimaryButton onClick={() => onRecommend(rec)} disabled={busy || !offers[0].solution.metrics.clears_hurdle} data-testid="dealdesk-recommend-best">
                 Recommend this structure <ArrowRight size={14} /></PrimaryButton>) : null}>
      <p className="mb-3 break-words text-[13px] text-text-primary" data-testid="dealdesk-best-tenor-rate">
        <b>Best tenor</b> at the asked {priceWord} of {bps(ask[tr.priceKey])}: {tr.maxTenor === null ? <b className="text-negative">none clears the {rate(b.ask.metrics.hurdle)} hurdle</b> : <b>up to {years(tr.maxTenor)}</b>}
        <span className="text-text-muted"> · </span>
        <b>Best rate</b> at the asked {years(ask.tenor_years)}: {tr.minPrice === null ? <b className="text-negative">no {priceWord} on the grid clears</b>
          : <><b>{priceWord} from {bps(tr.minPrice)}</b> <span className="text-text-muted">(ask {bps(ask[tr.priceKey])})</span></>}
      </p>
      {offers.length ? (
        <div className="grid gap-3 md:grid-cols-3" data-testid="dealdesk-best-offers">
          {offers.map((o, i) => (
            <OfferTile key={o.title} s={o.solution} title={o.title} recommended={i === 0} ask={ask} active={picked === o.title}
                       onUse={() => onUse(o.solution.terms, o.title)} testId={`dealdesk-best-offer-${i + 1}`} />))}
        </div>
      ) : (
        <div className="rounded-lg border border-warning/40 bg-warning-muted p-3 text-[12px]" data-testid="dealdesk-best-offers-none">
          <p className="flex items-center gap-1 font-semibold text-warning">No structure clears the hurdle and every limit. Smallest relaxation per lever:<InfoPopover title="No structure clears">No structure inside the market bounds clears the hurdle and every limit the optimiser holds (hard limits and risk appetite). Each line is the smallest relaxation of one lever that would clear.</InfoPopover></p>
          <ul className="mt-1 space-y-0.5 text-text-secondary">
            {(opt.relaxation ?? []).slice(0, 4).map((r, i) => (
              <li key={`${r.lever}-${i}`}><b className="text-text-primary">{SHORT[r.lever] ?? (r.lever === "dscr" ? "Client DSCR" : cap(r.lever.replace(/_/g, " ")))}</b>: {relaxRead(r.unit, r.from)} → {r.to === null ? "not reachable" : relaxRead(r.unit, r.to)}{r.beyond_market ? " (beyond market)" : ""}</li>))}
          </ul>
        </div>)}
      <div className="mt-4 grid gap-4 xl:grid-cols-3" data-testid="dealdesk-optimise-charts">
        <div className="min-w-0">
          <ChartTitle title="Hurdle-rate chart" info={<HeatmapInfo grid={b.heatmap} ask={ask} />} />
          <IsoRarocHeatmap grid={b.heatmap} ask={ask} rec={rec} height={300} />
        </div>
        <div className="min-w-0">
          <ChartTitle title={`RAROC against tenor at ${bps(ask[tr.priceKey])}`} info="Lifetime RAROC at the asked price for each tenor on the grid; green points clear the hurdle (dashed). The dotted lines mark the asked and recommended tenors." />
          {tenorRows.length ? <RarocTenorCurve rows={tenorRows} hurdle={b.heatmap.hurdle} askTenor={ask.tenor_years} recTenor={rec?.tenor_years ?? null} />
            : <p className="text-[12px] text-text-muted">No tenor grid for this facility.</p>}
        </div>
        <div className="min-w-0">
          <ChartTitle title="RAROC against amount" info={<AmountInfo grid={b.amount_curve} ask={ask} ccy={ask.currency} />} />
          <RarocAmountCurve grid={b.amount_curve} ask={ask} rec={rec} ccy={ask.currency} height={260} />
        </div>
      </div>
    </Section>
  );
}
