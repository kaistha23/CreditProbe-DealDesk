"use client";

/**
 * PLAN_R12 §1.4 and I16-3, Session C: which structure answers which weakness. For the ask (default) or any structure the
 * shell passes in (`terms`, e.g. the optimiser's recommended structure or the user's own), every weakness and threat
 * with the lever or condition that answers it, or "open" with what would.
 */

import * as React from "react";

import { useLoad } from "@/lib/v5/dealdesk";
import { cn } from "@/lib/utils";

import { Chip, Section, tableCls, tdCls, thCls } from "../kit";
import { loadGroupAll, loadMitigants } from "./api";
import { type Mitigants, mitigantTone } from "./model";
import { Answer, Loading } from "./parts";

export function MitigantTable({ m }: { m: Mitigants }) {
  return (<>
    <Answer testId="dealdesk-mitigants-answer">{m.headline}</Answer>
    {m.rows.length ? (
      <div className="mt-3 overflow-x-auto">
        <table className={tableCls}>
          <thead><tr>{["Weakness or threat", `Answered by (${m.structure_label})`, "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{m.rows.map((r) => (
            <tr key={r.swot_id} data-testid={`dealdesk-mitigant-${r.swot_id}`}>
              <td className={cn(tdCls, "max-w-[28rem] whitespace-normal align-top")}>
                <span className="block text-[11px] uppercase tracking-[0.06em] text-text-muted">{r.theme}</span>{r.weakness}</td>
              <td className={cn(tdCls, "whitespace-normal align-top")}>
                {r.structure.map((s, i) => <p key={`s${i}`}><span className="font-medium">{s.lever}:</span> {s.text}</p>)}
                {r.conditions.map((c) => <p key={c.condition_id} className="text-text-secondary"><span className="font-medium">Condition ({c.kind}, {c.due}):</span> {c.text}</p>)}
                {r.suggestion ? <p className="text-text-secondary">Not answered yet. {r.suggestion}</p> : null}
              </td>
              <td className={cn(tdCls, "align-top")}><Chip tone={mitigantTone(r.status)}>{r.status === "open" ? "open" : r.status.replace("answered by ", "")}</Chip></td>
            </tr>))}</tbody>
        </table>
      </div>) : null}
  </>);
}

/** The weakness-to-mitigant map (Structure step). Without `terms` it reads the ask. */
export function WeaknessMitigantMap({ proposalId, terms, label }: { proposalId: string; terms?: Record<string, unknown> | null; label?: string }) {
  const key = `mitigants:${proposalId}:${terms ? JSON.stringify(terms) : "ask"}:${label ?? ""}`;
  const r = useLoad<Mitigants>(async () => {
    if (!terms) return (await loadGroupAll(proposalId)).mitigants;
    return loadMitigants(proposalId, terms, label ?? "chosen");
  }, key);
  return (
    <Section title="Which structure answers which weakness" testId="dealdesk-weakness-mitigant-map"
             info={<p>Each weakness and threat from the SWOT, and what answers it: a structure lever (amount, tenor, repayment, covenants, collateral,
               cash margin, guarantee, pricing) compared with the ask, a condition raised by a red flag, or nothing yet, with the lever that would.</p>}>
      {r.data ? <MitigantTable m={r.data} /> : <Loading error={r.error} height="h-24" />}
    </Section>
  );
}
