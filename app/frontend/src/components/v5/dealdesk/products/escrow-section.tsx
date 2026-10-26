"use client";

/**
 * PLAN_R12 Session P (I28): the escrow / project-account section (product template "escrow"). Answer first, four
 * tiles, the waterfall of collections, the releases tested against their rules, the collections by month. Every
 * figure from GET /products/{id}/escrow. Renders nothing when the deal has no escrow account.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";

import { C } from "../charts";
import { Chip, Section, tableCls, tdCls, thCls } from "../kit";
import { productsApi, useProduct } from "./api";
import { type EscrowResult, amt, escrowTiles, month, pct } from "./format";
import { Answer, Failed, Flags, Loading, Sub, Tiles, scrollCls } from "./parts";

const TITLE = "Escrow account";

export function EscrowSection({ proposalId, showEmpty = false }: { proposalId: string; showEmpty?: boolean }) {
  const { data, error, loading, reload } = useProduct(`escrow:${proposalId}`, (s) => productsApi.escrow(proposalId, s));
  if (loading && !data) return <Loading title={TITLE} testId="products-escrow-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="products-escrow-error" />;
  if (!data || (!data.has_data && !showEmpty)) return null;
  return <EscrowView r={data} />;
}

export function EscrowView({ r }: { r: EscrowResult }) {
  return (
    <Section title={TITLE} testId="products-escrow"
             info={<>Off-plan sales collections, the escrow waterfall, releases and the cover ratio, from dd_escrow (Deal Desk products domain).</>}>
      <Answer text={r.answer} testId="products-escrow-answer" />
      {r.has_data ? <>
        <Tiles tiles={escrowTiles(r)} testId="products-escrow-tiles" />
        {r.account ? (
          <p className="text-[12px] text-text-secondary">
            Developer {r.account.developer ?? "not provided"} · escrow agent {r.account.escrow_agent ?? "not provided"} · construction {pct(r.account.construction_progress_pct)} complete
            {" "}of {amt(r.account.construction_cost)}
          </p>) : null}
        {r.cover ? <p className="mt-1 text-[12px] text-text-secondary">{r.cover.text}.</p> : null}
        <Waterfall r={r} />
        <Releases r={r} />
        <Collections r={r} />
      </> : null}
    </Section>
  );
}

function Waterfall({ r }: { r: EscrowResult }) {
  const wf = r.waterfall;
  if (!wf || !wf.tiers.length) return null;
  const shown = wf.tiers.filter((t) => t.allocated !== null);
  const data = [{
    type: "bar", orientation: "h", y: shown.map((t) => `${t.priority}. ${t.bucket}`).reverse(), x: shown.map((t) => t.allocated ?? 0).reverse(),
    marker: { color: shown.map((t) => (/developer|surplus/i.test(t.bucket) ? C.best : C.rec)).reverse() },
    text: shown.map((t) => `${amt(t.allocated)} · ${pct(t.share)}`).reverse(), textposition: "auto",
    hovertemplate: "%{y}<br>SAR %{x:,.1f}m<extra></extra>",
  }];
  return (
    <Sub title={`Waterfall: ${amt(wf.collections)} collected, ${amt(wf.unallocated)} in the account`}
         info="The escrow's release order and what each step has received from collections to date (dd_escrow).">
      {shown.length ? <Plot data={data} height={60 + 34 * shown.length} testId="products-escrow-waterfall" filename="deal-desk-escrow-waterfall"
            ariaLabel="Escrow waterfall: what each step has received from collections"
            layout={{ margin: { l: 220, r: 12, t: 8, b: 30 }, xaxis: { tickformat: ",.0f", title: { text: "SAR m" } }, yaxis: { automargin: true } }} /> : null}
      <div className={scrollCls}>
        <table className={tableCls}>
          <thead><tr>{["Step", "Rule", "Received to date", "Share of releases"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{wf.tiers.map((t) => (
            <tr key={t.priority}><td className={tdCls}>{t.priority}. {t.bucket}</td><td className={cn(tdCls, "whitespace-normal")}>{t.rule}</td>
              <td className={tdCls}>{amt(t.allocated)}</td><td className={tdCls}>{pct(t.share)}</td></tr>))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}

function Releases({ r }: { r: EscrowResult }) {
  const rl = r.releases;
  const [showAll, setShowAll] = React.useState(false);
  if (!rl || !rl.rows.length) return null;
  const ok = rl.rows.length - rl.breaches;
  return (
    <Sub title={`Releases: ${amt(rl.released)}; ${rl.breaches} month${rl.breaches === 1 ? "" : "s"} outside the rules`}>
      <Flags items={rl.rules} />
      {rl.breaches || showAll ? <div className={cn(scrollCls, "mt-2")}>
        <table className={tableCls} data-testid="products-escrow-releases">
          <thead><tr>{["Month", "Collections", "Construction", "Debt service", "Developer", "Retention", "Progress", "Within rules"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{rl.rows.filter((x) => !x.compliant || showAll).map((x) => (
            <React.Fragment key={x.release_id}>
              <tr>
                <td className={tdCls}>{month(x.date)}</td><td className={tdCls}>{amt(x.collections)}</td><td className={tdCls}>{amt(x.construction)}</td>
                <td className={tdCls}>{amt(x.debt_service)}</td><td className={tdCls}>{amt(x.developer)}</td><td className={tdCls}>{amt(x.retention)}</td>
                <td className={tdCls}>{pct(x.progress_pct)}</td>
                <td className={tdCls}>{x.compliant ? <Chip tone="positive">Yes</Chip> : <Chip tone="negative">No</Chip>}</td>
              </tr>
              {x.breaches.length ? <tr><td colSpan={8} className="border-b border-border/60 px-2 pb-2"><Flags items={x.breaches} /></td></tr> : null}
            </React.Fragment>))}
          </tbody>
        </table>
      </div> : null}
      {ok ? (
        <button type="button" className="mt-1 text-[12px] text-accent underline" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show only the months outside the rules" : `Show the ${ok} month${ok === 1 ? "" : "s"} within the rules`}
        </button>) : null}
    </Sub>
  );
}

function Collections({ r }: { r: EscrowResult }) {
  const c = r.collections;
  if (!c || !c.series.length) return null;
  const x = c.series.map((s) => month(s.month));
  const data = [
    { type: "bar", name: "Collected", x, y: c.series.map((s) => s.collected), marker: { color: C.rec }, hovertemplate: "Collected SAR %{y:,.1f}m<extra></extra>" },
  ];
  return (
    <Sub title={`Collections: ${amt(c.collected_to_date)} of ${amt(c.sales_value_contracted)} sold; ${amt(c.to_collect)} still to collect`}>
      <Plot data={data} height={200} testId="products-escrow-collections" filename="deal-desk-escrow-collections"
            ariaLabel="Off-plan buyer collections by month"
            layout={{ margin: { l: 52, r: 12, t: 12, b: 36 }, showlegend: false,
                      xaxis: { tickmode: "array", tickangle: 0, tickvals: x.filter((_, i) => i % Math.max(1, Math.ceil(x.length / 12)) === 0) }, yaxis: { rangemode: "tozero", tickformat: ",.0f", title: { text: "SAR m" } } }} />
    </Sub>
  );
}
