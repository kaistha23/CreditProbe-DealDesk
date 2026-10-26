"use client";

/**
 * R6 E4: the (i) on every chart explains it fully, the same way everywhere:
 * what it shows, how each series is calculated, how to read it (with an example
 * from the current figures) and what to look for. The shape and the pure helpers
 * live in ./chart-explain-core.ts; each module builds its explanations there-style
 * (pure functions, tested) and renders them with <ChartInfo>.
 */

import * as React from "react";

import { InfoPopover } from "@/components/ui/info-popover";

import type { ChartExplain } from "./chart-explain-core";

export * from "./chart-explain-core";

/** Renders "**bold**" spans as <strong>. */
export function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) => (p.startsWith("**") && p.endsWith("**") && p.length > 4
        ? <strong key={i} className="font-semibold text-text-primary">{p.slice(2, -2)}</strong>
        : <React.Fragment key={i}>{p}</React.Fragment>))}
    </>
  );
}

const HEAD = "text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted";

/** The four parts, laid out the same way in every popover. */
export function ChartExplainBody({ explain, hint }: { explain: ChartExplain; hint?: string }) {
  return (
    <div className="space-y-2" data-testid="chart-explain">
      <div><p className={HEAD}>What it shows</p><p><Rich text={explain.shows} /></p></div>
      <div><p className={HEAD}>How it is calculated</p>
        <ul className="list-disc space-y-0.5 pl-4">{explain.formula.map((f, i) => <li key={i}><Rich text={f} /></li>)}</ul></div>
      <div><p className={HEAD}>How to read it</p><p><Rich text={explain.read} /></p></div>
      <div><p className={HEAD}>What to look for</p><p><Rich text={explain.lookFor} /></p></div>
      {hint ? <p className="border-t border-border pt-1.5 text-[10px] text-text-muted">{hint}</p> : null}
    </div>
  );
}

/** The (i) beside a chart title, with the full explanation inside. */
export function ChartInfo({ title, explain, hint, className, align }: {
  title?: string; explain: ChartExplain; hint?: string; className?: string; align?: "left" | "right";
}) {
  return (
    <InfoPopover title={title ?? "About this chart"} className={className} align={align}>
      <ChartExplainBody explain={explain} hint={hint} />
    </InfoPopover>
  );
}
