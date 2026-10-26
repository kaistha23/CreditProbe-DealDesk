"use client";

/**
 * R13 IA (backlog #1): the committee challenger. The questions committee will ask, ranked, each answered from data with
 * its source; the ones the proposal does not answer are marked. Compact: the question list first, the answer on open.
 */

import * as React from "react";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeChallenger } from "@/lib/v5/plain-words-g/deal";
import { Chip, Section } from "../../kit";
import { useChallenger } from "./api";
import { type Challenger, type Source } from "./model";
import { Answer, Lineage, Loading } from "./parts";

export function ChallengerView({ c }: { c: Challenger }) {
  return (<>
    <Answer testId="ia-challenger-answer">{c.headline}</Answer>
    <ol className="mt-3 space-y-1.5">
      {c.questions.map((q) => (
        <li key={q.id} data-testid={`ia-question-${q.rank}`}>
          <details className="group rounded-md border border-border/70 px-3 py-2 open:bg-surface-hover/40">
            <summary className="flex cursor-pointer list-none items-start gap-2 text-[13px] text-text-primary">
              <span className="w-4 shrink-0 tabular-nums text-text-muted">{q.rank}</span>
              <span className="min-w-0 flex-1">{q.question}</span>
              {q.avoided ? <Chip tone="negative" title={q.avoided_reason}>not answered</Chip> : <Chip tone="positive">on file</Chip>}
            </summary>
            <div className="mt-2 flex items-start gap-1.5 pl-6 text-[12px] leading-5 text-text-secondary">
              <span className="min-w-0 flex-1">{q.answer}</span>
              <Lineage title="Where the answer comes from" sources={q.evidence.map((e) => e.source as Source)}>
                <p>Raised from: {q.source}.{q.avoided ? ` ${q.avoided_reason}` : ""}</p>
              </Lineage>
            </div>
          </details>
        </li>))}
    </ol>
    {c.avoided.length ? (
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Questions the proposal avoids ({c.avoided.length})</summary>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-[12px] text-text-secondary">
          {c.avoided.map((a) => <li key={a.id}>{a.question}</li>)}
        </ul>
      </details>) : null}
  </>);
}

/** Deal page, More menu: "Committee questions". */
export function CommitteeChallengerPanel({ proposalId }: { proposalId: string }) {
  const r = useChallenger(proposalId);
  return (
    <Section title="Committee questions" testId="ia-challenger-panel"
             info={<p>The five to seven questions a credit committee is most likely to ask, scored from the review findings, the SWOT weaknesses,
               the stress verdict, the group exposure, earlier committee conditions and conditions set on similar deals. Each is answered from Data
               Domains with its source; a question no mitigant, condition, query or trigger answers is marked not answered.</p>}>
      <PanelWords panel="challenger" lines={r.data ? () => writeChallenger(r.data!) : r.error ? [] : null} />
      {r.data ? <ChallengerView c={r.data} /> : <Loading error={r.error} />}
    </Section>
  );
}
