"use client";

/**
 * PLAN_R12 §1.4 (I24), Session C: SWOT in Structure. Four quadrants; every point financial or qualitative, with its
 * number and period, its evidence (i) (Data Domains relation and row keys) and a link to the finding or step behind it.
 * Written deterministically on the server (N6).
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { Chip, Section } from "../kit";
import { useGroupAll } from "./api";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeSwot } from "@/lib/v5/plain-words-g/deal";
import { QUADRANTS, type Swot, byQuadrant, stepLabel } from "./model";
import { Answer, Loading, SourceInfo } from "./parts";

export function SwotView({ s, onOpenStep }: { s: Swot; onOpenStep?: (step: string) => void }) {
  const q = byQuadrant(s.points);
  return (<>
    <Answer testId="dealdesk-swot-answer">{s.summary}</Answer>
    <div className="mt-3 grid gap-3 lg:grid-cols-2">
      {QUADRANTS.map((x) => (
        <div key={x.key} className={cn("rounded-lg border p-3", x.tone === "positive" ? "border-positive/30" : x.tone === "negative" ? "border-negative/30"
          : x.tone === "warning" ? "border-warning/30" : "border-accent/30")} data-testid={`dealdesk-swot-${x.key}`}>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-[13px] font-semibold text-text-primary">{x.label}</h3>
            <Chip tone={x.tone}>{q[x.key].length}</Chip>
          </div>
          {q[x.key].length ? (
            <ul className="space-y-2">
              {q[x.key].map((p) => (
                <li key={p.id} className="text-[12px] leading-5 text-text-primary">
                  <div className="flex items-start gap-1.5">
                    <span className="min-w-0 flex-1">{p.text}</span>
                    <SourceInfo title={p.theme.charAt(0).toUpperCase() + p.theme.slice(1)} sources={p.evidence}>
                      <p>{p.kind === "financial" ? "Financial" : "Qualitative"} point{p.link.id ? `, from finding ${p.link.id}` : ""}.</p>
                    </SourceInfo>
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    <Chip tone="neutral">{p.kind}</Chip>
                    <Chip tone="neutral">{p.theme}</Chip>
                    {p.link.step ? (onOpenStep
                      ? <button type="button" onClick={() => onOpenStep(p.link.step as string)} className="text-[11px] text-accent hover:underline">Open {stepLabel(p.link.step)}</button>
                      : <span className="text-[11px] text-text-muted">{stepLabel(p.link.step)}</span>) : null}
                  </div>
                </li>))}
            </ul>) : <p className="text-[12px] text-text-muted">None found.</p>}
        </div>))}
    </div>
  </>);
}

/** SWOT for one deal (Structure step). `onOpenStep` lets the shell jump to the step a point links to. */
export function SwotPanel({ proposalId, onOpenStep }: { proposalId: string; onOpenStep?: (step: string) => void }) {
  const r = useGroupAll(proposalId);
  return (
    <Section title="SWOT" testId="dealdesk-swot-panel"
             info={<p>Strengths, weaknesses, opportunities and threats, financial and qualitative (management, ownership, governance, track record, market
               position, concentration, geopolitics). Each point carries the figure behind it and its source in Data Domains; it is published to dd_swot.</p>}>
      <PanelWords panel="swot" lines={r.data ? () => writeSwot(r.data!.swot) : r.error ? [] : null} />
      {r.data ? <SwotView s={r.data.swot} onOpenStep={onOpenStep} /> : <Loading error={r.error} />}
    </Section>
  );
}
