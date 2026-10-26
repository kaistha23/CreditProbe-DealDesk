"use client";

/**
 * PLAN_R12 Session P (I28): the syndicated-facility section (product template "syndicated"). Answer first, four
 * tiles on our share, the role, the sell-down plan with RAROC and SVA at each step, lenders (pari passu, voting
 * share, information from the agent) and the agent's covenants. Every figure from GET /products/{id}/syndication.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { Chip, Section, tableCls, tdCls, thCls } from "../kit";
import { productsApi, useProduct } from "./api";
import { type SyndicationResult, amt, pct, syndicationTiles, times } from "./format";
import { Answer, Failed, Flags, Loading, Sub, Tiles, scrollCls } from "./parts";

const TITLE = "Syndicated facility: our share";

export function SyndicationSection({ proposalId, showEmpty = false }: { proposalId: string; showEmpty?: boolean }) {
  const { data, error, loading, reload } = useProduct(`synd:${proposalId}`, (s) => productsApi.syndication(proposalId, s));
  if (loading && !data) return <Loading title={TITLE} testId="products-synd-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="products-synd-error" />;
  if (!data || (!data.has_data && !showEmpty)) return null;
  return <SyndicationView r={data} />;
}

export function SyndicationView({ r }: { r: SyndicationResult }) {
  const f = r.facility;
  return (
    <Section title={TITLE} testId="products-synd"
             info={<>Our commitment, hold and sell-down from dd_syndication; RAROC, SVA and RWA are computed by the Deal Desk engine on our share only.</>}>
      <Answer text={r.answer} testId="products-synd-answer" />
      {r.has_data && f ? <>
        <Tiles tiles={syndicationTiles(r)} testId="products-synd-tiles" />
        {r.role ? (
          <p className="text-[12px] text-text-secondary">
            <span className="font-medium text-text-primary">{r.role.label}</span> · documents: {r.role.documents} · fees: {r.role.fees} · information: {r.role.information}
            {f.agent ? ` · agent ${f.agent}` : ""}{f.lenders ? ` · ${f.lenders} lenders` : ""}
          </p>) : null}
        {r.flags?.length ? <Flags items={r.flags} /> : null}
        <SellDown r={r} />
        <Lenders r={r} />
      </> : null}
    </Section>
  );
}

function SellDown({ r }: { r: SyndicationResult }) {
  const s = r.sell_down ?? [];
  const ccy = r.facility?.currency ?? "SAR";
  if (!s.length) return null;
  return (
    <Sub title="Hold and sell-down" info="Each step re-runs the engine on our commitment at that hold; the arranger skim applies to the share we sell down.">
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-synd-selldown">
          <thead><tr>{["Step", "Date", "Our hold", "Share of facility", "RAROC", "SVA", "RWA (year 1)", "EL (year 1)"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{s.map((x) => (
            <tr key={x.step}>
              <td className={tdCls}>{x.buyer_type ? x.buyer_type.charAt(0).toUpperCase() + x.buyer_type.slice(1) : (x.step === 0 ? "At signing" : `Step ${x.step}`)}</td>
              <td className={tdCls}>{x.date ?? "–"}</td>
              <td className={tdCls}>{amt(x.hold, ccy)}</td>
              <td className={tdCls}>{pct(x.share_of_facility, 1)}</td>
              <td className={cn(tdCls, x.analytics && !x.analytics.clears_hurdle && "text-negative")}>{x.analytics ? pct(x.analytics.raroc, 1) : "–"}</td>
              <td className={tdCls}>{x.analytics ? amt(x.analytics.sva) : "–"}</td>
              <td className={tdCls}>{x.analytics ? amt(x.analytics.rwa_y1) : "–"}</td>
              <td className={tdCls}>{x.analytics ? amt(x.analytics.el_y1) : "–"}</td>
            </tr>))}
          </tbody>
        </table>
      </div>
      {s.every((x) => !x.analytics) ? <p className="mt-1 text-[12px] text-text-muted">RAROC on our share appears once the deal is priced in Deal Desk.</p> : null}
    </Sub>
  );
}

function Lenders({ r }: { r: SyndicationResult }) {
  const l = r.lenders;
  const cov = r.covenants ?? [];
  if (!l) return null;
  return (
    <Sub title="Lenders and covenants">
      <p className="text-[12px] text-text-secondary">
        Pari passu: {r.facility?.pari_passu === null || r.facility?.pari_passu === undefined ? "not provided" : r.facility.pari_passu ? "yes" : "no"} ·
        our vote {pct(l.our_vote, 1)} against a {pct(l.majority_pct)} majority ({l.blocking_minority ? "blocking minority" : "no blocking minority"}) ·
        information from the agent: {l.info_from_agent ?? "not provided"}
      </p>
      {r.covenants_text ? <p className="mt-1 text-[12px] text-text-secondary">Covenants (facility agreement): {r.covenants_text}</p> : null}
      {r.facility?.security ? <p className="mt-1 text-[12px] text-text-secondary">Security: {r.facility.security}</p> : null}
      {cov.length ? (
        <div className={cn(scrollCls, "mt-2")}>
          <table className={tableCls} data-testid="products-synd-covenants">
            <thead><tr>{["Covenant (as reported by the agent)", "Threshold", "Actual", "Headroom", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{cov.map((c) => (
              <tr key={c.covenant}>
                <td className={tdCls}>{c.covenant}</td><td className={tdCls}>{c.direction === "max" ? "≤ " : "≥ "}{times(c.threshold)}</td>
                <td className={tdCls}>{times(c.actual)}</td><td className={tdCls}>{pct(c.headroom)}</td>
                <td className={tdCls}>{c.ok ? <Chip tone="positive">Met</Chip> : <Chip tone="negative">Breached</Chip>}</td>
              </tr>))}
            </tbody>
          </table>
        </div>) : null}
    </Sub>
  );
}
