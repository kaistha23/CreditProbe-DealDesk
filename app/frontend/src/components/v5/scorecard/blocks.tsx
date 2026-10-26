"use client";

/** What an answer in a validation thread is made of: words, the scorecard choice, the plan, the results, findings. */

import * as React from "react";

import { AnswerFrame } from "@/components/answer";
import { Card } from "@/components/ui/card";
import { ConvoBlockView, EvidenceInfo } from "@/components/v5/convo/blocks";
import { Markdown } from "@/components/v5/whatif/blocks";
import { cn } from "@/lib/utils";
import type { ConvoAnswer } from "@/lib/v5/convo";
import { type Answer, type Block, type PlanGroup, type ScorecardInfo, reportHref } from "@/lib/v5/scorecard";

import { MmsgPanel } from "./mmsg-panel";
import { Rag, ValidationView } from "./validation-view";

type Ask = (text: string) => void;

const GROUP_ASK: Record<string, string> = { discrimination: "discrimination", calibration: "calibration", stability: "stability", variables: "the variables", overrides: "overrides" };

function ChooseCards({ scorecards, onAsk, busy }: { scorecards: ScorecardInfo[]; onAsk: Ask; busy: boolean }) {
  return (
    <div className="grid gap-3 md:grid-cols-3" data-testid="sv-choose">
      {scorecards.map((s) => (
        <Card key={s.scorecard_id} className="flex flex-col gap-2 p-3" data-testid={`sv-card-${s.scorecard_id}`}>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{s.segment} · {s.type}</p>
            <h4 className="text-[14px] font-semibold text-text-primary">{s.name} <span className="text-text-muted">v{s.version}</span></h4>
          </div>
          <p className="text-[12px] text-text-secondary">{s.description}</p>
          <p className="text-[11px] text-text-muted">{s.rows.toLocaleString("en-US")} scored rows · {s.periods[0]} to {s.periods[1]} · {s.variables.length} variables</p>
          <button type="button" disabled={busy} onClick={() => onAsk(`Validate the ${s.name}`)} data-testid={`sv-choose-${s.scorecard_id}`}
                  className="mt-auto rounded-md border border-accent px-3 py-1.5 text-[12px] font-medium text-accent hover:bg-surface-hover disabled:opacity-40">Validate this scorecard</button>
        </Card>))}
    </div>
  );
}

function PlanCard({ block, onAsk, busy, live }: { block: Extract<Block, { type: "plan" }>; onAsk: Ask; busy: boolean; live: boolean }) {
  const p = block.plan;
  return (
    <Card className="space-y-3 p-4" data-testid="sv-plan">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[14px] font-semibold text-text-primary">Validation plan</h4>
        <span className="text-[11px] text-text-muted">{p.scorecard_id}</span>
      </div>
      <dl className="grid gap-x-6 gap-y-1 text-[12px] sm:grid-cols-2 lg:grid-cols-4" data-testid="sv-plan-windows">
        <div><dt className="text-text-muted">Development</dt><dd>{p.development[0]} to {p.development[1]}</dd></div>
        <div><dt className="text-text-muted">Monitoring</dt><dd>{p.monitoring[0]} to {p.monitoring[1]}</dd></div>
        <div><dt className="text-text-muted">As of</dt><dd data-testid="sv-plan-asof">{p.as_of}</dd></div>
        <div><dt className="text-text-muted">Segment cut</dt><dd data-testid="sv-plan-segment">{p.segment_by.replace(/_/g, " ")}</dd></div>
      </dl>
      <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-text-secondary" data-testid="sv-plan-readiness">{block.readiness.map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="space-y-1.5" data-testid="sv-plan-groups">
        {block.groups.map((g: PlanGroup) => (
          <div key={g.group} className="flex items-start gap-2 rounded-md border border-border p-2" data-testid={`sv-plan-group-${g.group}`} data-enabled={g.enabled}>
            <button type="button" disabled={!live || busy} onClick={() => onAsk(`${g.enabled ? "Skip" : "Include"} ${GROUP_ASK[g.group]}`)} data-testid={`sv-plan-toggle-${g.group}`}
                    aria-pressed={g.enabled} title={live ? (g.enabled ? "Leave this group out" : "Include this group") : ""}
                    className={cn("mt-0.5 inline-flex h-5 min-w-[44px] items-center justify-center rounded-full border px-2 text-[10px] font-semibold",
                                  g.enabled ? "border-positive/40 bg-positive-muted text-positive" : "border-border bg-surface-sunken text-text-muted", !live && "cursor-default")}>
              {g.enabled ? "On" : "Off"}</button>
            <div className="min-w-0 text-[12px]">
              <p className="font-medium text-text-primary">{g.title}</p>
              <p className="text-text-secondary">{g.what}</p>
              <details className="mt-0.5 text-text-muted"><summary className="cursor-pointer text-[11px]">Stated thresholds</summary>
                <ul className="mt-1 space-y-0.5 text-[11px]">{g.thresholds.map((t) => <li key={t.label}><span className="text-text-secondary">{t.label}:</span> {t.text}</li>)}</ul></details>
            </div>
          </div>))}
      </div>
      {live ? (
        <button type="button" disabled={busy} onClick={() => onAsk("Run it")} data-testid="sv-plan-run"
                className="rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-accent-contrast disabled:opacity-40">Run the validation</button>) : null}
    </Card>
  );
}

export function AnswerView({ answer, onAsk, busy, isLast }: { answer: Answer; onAsk: Ask; busy: boolean; isLast: boolean }) {
  // PLAN_R12 N2: the first text block leads with the answer's headline sentence.
  const lead = answer.blocks.findIndex((b: Block) => b.type === "text");
  return (
    <AnswerFrame testId="sv-answer">
      {answer.blocks.map((b: Block, i: number) => {
        switch (b.type) {
          case "text": return <Markdown key={i} text={b.markdown} headline={i === lead} className="rounded-lg border border-border bg-surface p-3.5" />;
          case "choose": return <ChooseCards key={i} scorecards={b.scorecards} onAsk={onAsk} busy={busy} />;
          case "plan": return <PlanCard key={i} block={b} onAsk={onAsk} busy={busy} live={isLast} />;
          case "validation": return <ValidationView key={i} id={b.validation_id} charts={(b as { charts?: string[] }).charts} />;
          case "findings": return (
            <div key={i} className="space-y-2" data-testid="sv-findings-block">
              {b.items.map((f) => (
                <div key={f.test} className="flex gap-2 rounded-md border border-border bg-surface p-2.5 text-[12px]" data-status={f.status}>
                  <Rag status={f.status} />
                  <div><p className="font-medium text-text-primary">{f.label}</p><p className="text-text-secondary">{f.text}</p>
                    {f.action ? <p className="mt-0.5 text-text-muted">Action: {f.action}</p> : null}</div>
                </div>))}
            </div>);
          case "report": return (
            <Card key={i} className="space-y-2 p-3" data-testid="sv-report-block">
              <p className="text-[13px] text-text-secondary">{b.text}</p>
              <a href={reportHref(b.validation_id)} data-testid="sv-report-download" className="inline-block rounded-md border border-accent px-3 py-1.5 text-[12px] font-medium text-accent hover:bg-surface-hover">Download the Word report</a>
            </Card>);
          case "mmsg": return <MmsgPanel key={i} validationId={b.validation_id} text={b.text} />;
          case "answer":
          case "table":
          case "chart":
            return <ConvoBlockView key={i} block={b as never} index={i} />;
          default: return null;
        }
      })}
      {answer.evidence?.length ? <EvidenceInfo answer={answer as unknown as ConvoAnswer} /> : null}
    </AnswerFrame>
  );
}
