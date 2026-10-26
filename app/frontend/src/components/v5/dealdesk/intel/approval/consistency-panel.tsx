"use client";

/**
 * R13 IA (backlog #20): decision consistency. Similar deals decided differently, worst-explained first, each with the
 * differences that explain the decision or fail to; and the desk's recommendation against the committee's decision.
 */

import * as React from "react";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeConsistency } from "@/lib/v5/plain-words-g/deal";
import { Chip, Section } from "../../kit";
import { useConsistency } from "./api";
import { type Consistency, decisionTone, pairCounts, statusTone } from "./model";
import { Answer, Loading } from "./parts";

export function ConsistencyView({ c }: { c: Consistency }) {
  const n = pairCounts(c.decided_differently);
  return (<>
    <Answer testId="ia-consistency-answer">{c.headline}</Answer>
    <div className="mt-2 flex flex-wrap gap-1.5">
      <Chip tone={decisionTone(c.decision.decision)}>{c.decision.decision} · {c.decision.by}</Chip>
      {n["not explained"] ? <Chip tone="negative">{n["not explained"]} not explained</Chip> : null}
      {n["partly explained"] ? <Chip tone="warning">{n["partly explained"]} partly explained</Chip> : null}
      {n["explained"] ? <Chip tone="positive">{n["explained"]} explained</Chip> : null}
    </div>
    {c.decided_differently.length ? (
      <ul className="mt-3 space-y-2">
        {c.decided_differently.map((p) => (
          <li key={`${p.better}-${p.worse}`} className="rounded-md border border-border/70 px-3 py-2 text-[12px] leading-5 text-text-primary">
            <div className="mb-0.5 flex items-center gap-2">
              <Chip tone={statusTone(p.status)}>{p.status}</Chip>
              <span className="text-text-muted">similarity {p.similarity.toFixed(2)}</span>
            </div>
            {p.text}
          </li>))}
      </ul>) : null}
    {c.similar.length ? (
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Similar decided deals ({c.similar.length})</summary>
        <ul className="mt-1 space-y-0.5 text-[12px] text-text-secondary">
          {c.similar.map((d) => (
            <li key={d.proposal_id}>{d.proposal_id} {d.obligor} · {d.sector} · {d.rating} · {d.decision.decision} ({d.decision.by}) · similarity {(d.similarity ?? 0).toFixed(2)}</li>))}
        </ul>
      </details>) : null}
    {c.data_note ? <p className="mt-2 text-[11px] text-text-muted">{c.data_note}</p> : null}
  </>);
}

/** Deal page, More menu: "Decision consistency". */
export function DecisionConsistencyPanel({ proposalId }: { proposalId: string }) {
  const r = useConsistency(proposalId);
  return (
    <Section title="Decision consistency" testId="ia-consistency-panel"
             info={<p>Deals similar in sector, rating, size and structure that were decided differently (committee, SME lane or desk), with the
               differences in rating, returns, limits, SIMAH, cover, LGD, open findings and stress that explain the decision, or fail to.</p>}>
      <PanelWords panel="consistency" lines={r.data ? () => writeConsistency(r.data!) : r.error ? [] : null} />
      {r.data ? <ConsistencyView c={r.data} /> : <Loading error={r.error} />}
    </Section>
  );
}
