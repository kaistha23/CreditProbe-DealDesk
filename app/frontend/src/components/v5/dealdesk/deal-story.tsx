"use client";

/**
 * R15 b (L13, L8): one story on the deal page.
 *
 *   <DealStoryLine e={summary} />      the one sentence that reconciles price and verdict ("Profitable (19.6% vs 16.0%) but
 *                                      not approvable as proposed: …"), the same sentence the Review banner reads
 *   <ReturnViewSwitch e={summary} />   Deal only (used for approval) · Whole relationship · Relationship + deposits, each with
 *                                      one plain line and its formula; the approval basis is the bank's policy setting
 *
 * Every figure comes from the engines summary (one RAROC bridge, one findings engine; PLAN_R14 N2).
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import { type ReturnView, type Summary, approvalView, pct1 } from "@/lib/v5/dealdesk-engines";

const TONE = {
  negative: "border-negative/40 bg-negative/5 text-text-primary",
  warning: "border-warning/40 bg-warning/5 text-text-primary",
  positive: "border-positive/40 bg-positive/5 text-text-primary",
} as const;

export function DealStoryLine({ e, testId = "dealdesk-story" }: { e: Summary | null; testId?: string }) {
  const v = e?.findings.verdict;
  if (!v?.story) return null;
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-[12.5px] leading-5", TONE[v.tone])} data-testid={testId}>
      <span className="font-semibold">{v.decision}.</span>
      <span className="min-w-0 flex-1" data-testid={`${testId}-sentence`}>{v.story}</span>
      {v.price_only ? <span className="w-full text-[11px] text-text-muted" data-testid={`${testId}-price-only`}>{v.price_only}</span> : null}
    </div>
  );
}

export function ReturnViewSwitch({ e, testId = "dealdesk-return-view", compact = false }: { e: Summary | null; testId?: string; compact?: boolean }) {
  const rv = e?.return_views;
  const [key, setKey] = React.useState<ReturnView["key"] | null>(null);
  if (!rv) return null;
  const view = rv.views.find((x) => x.key === key) ?? approvalView(rv);
  if (!view) return null;
  const hurdle = e?.raroc.hurdle ?? 0;
  return (
    <div className="space-y-1.5" data-testid={testId}>
      <div role="radiogroup" aria-label="Return view" className="flex flex-wrap gap-1">
        {rv.views.map((x) => (
          <button key={x.key} type="button" role="radio" aria-checked={x.key === view.key} onClick={() => setKey(x.key)}
                  data-testid={`${testId}-${x.key}`}
                  className={cn("rounded-full border px-2.5 py-0.5 text-[11px]",
                    x.key === view.key ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>
            {x.label}</button>))}
      </div>
      <p className="text-[12px] text-text-primary" data-testid={`${testId}-value`}>
        <b className={view.clears ? "text-positive" : "text-negative"}>{pct1(view.raroc)}</b> vs the {pct1(hurdle)} hurdle
        {view.used_for_approval ? <span className="ml-1.5 rounded bg-accent-muted px-1.5 py-0.5 text-[10px] font-medium text-accent">used for approval</span>
                                : <span className="ml-1.5 rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] text-text-muted">for pricing talks only</span>}
      </p>
      <p className="text-[11.5px] text-text-secondary" data-testid={`${testId}-line`}>{view.line}</p>
      {!compact && view.formula ? <p className="text-[11px] text-text-muted">What it adds: {view.formula}.</p> : null}
      <p className="text-[11px] text-text-muted" data-testid={`${testId}-rule`}>{rv.rule}</p>
    </div>
  );
}
