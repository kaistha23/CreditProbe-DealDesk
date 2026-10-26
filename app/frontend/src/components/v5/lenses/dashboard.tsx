"use client";

/**
 * R13 L (J8): the top of a lens, as a professional dashboard reads.
 *
 *  - `LensInterpretation`  3-5 lines from the deterministic writer (backend/lenses_v5/interpret.py): where the scope
 *                          stands, then the two or three movements that matter with their numbers and periods
 *  - `KpiStrip`            6-8 small tiles in one row (two even rows beside the assistant): label, value, change on
 *                          the prior period with its arrow and tone, a tiny sparkline, the (i) with the query
 *
 * House kit tokens only (text-*, border-border, bg-surface*); the sparkline is the shared Plotly spark.
 */

import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { deltaArrow, periodLine, stripCols, toneOf } from "@/lib/v5/lens-dashboard";
import type { Interpretation, Kpi, Trace } from "@/lib/v5/lenses";

import { Spark } from "./home";
import { TraceInfo } from "./tile";

const TONE_TEXT = { good: "text-positive", bad: "text-negative", neutral: "text-text-muted" } as const;
const TONE_DOT = { good: "bg-positive", bad: "bg-negative", neutral: "bg-border-strong" } as const;

export function LensInterpretation({ it }: { it: Interpretation }) {
  if (!it.headline && !it.lines.length) return null;
  return (
    <Card className="px-4 py-3" data-testid="lens-interpretation" data-lines={(it.headline ? 1 : 0) + it.lines.length}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Reading · {periodLine(it.period, it.prior)}</p>
        <TraceInfo trace={it.trace.sql ? { sql: it.trace.sql, period: it.period, row_count: 0, sources: ["KPI strip", "Books"],
                                           relations: [], engine: "duckdb", at: "" } satisfies Trace : null}
                   explain={{ shows: "Where the lens scope stands and the movements that matter most, ranked by size against their own level.",
                              formula: it.trace.note, read: "Each line names the figure, its value now, the change on the prior period and, where the window holds it, on a year before.",
                              look_for: "Red markers are adverse moves; the ECL line names the segment behind the move." }}
                   testId="lens-interpretation-trace" />
      </div>
      {it.headline ? <p className="mt-1 text-[14px] font-semibold leading-snug text-text-primary" data-testid="lens-interpretation-headline">{it.headline}</p> : null}
      {it.lines.length ? (
        <ul className="mt-1.5 space-y-1" data-testid="lens-interpretation-lines">
          {it.lines.map((l) => (
            <li key={l.metric + l.text.slice(0, 12)} className="flex gap-2 text-[13px] leading-snug text-text-secondary" data-tone={l.tone}>
              <span aria-hidden className={cn("mt-[7px] size-1.5 shrink-0 rounded-full", TONE_DOT[toneOf(l.tone)])} />
              <span>{l.text}</span>
            </li>))}
        </ul>) : null}
    </Card>
  );
}

function KpiTile({ k }: { k: Kpi }) {
  const tone = toneOf(k.tone);
  return (
    <div className="flex min-w-0 flex-col rounded-md border border-border bg-surface px-2.5 py-2" data-testid={`lens-kpi-${k.key}`}>
      <div className="flex items-start justify-between gap-1">
        <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-text-muted" title={k.label}>{k.label}</p>
        <TraceInfo trace={k.trace} explain={k.explain} testId={`lens-kpi-trace-${k.key}`} />
      </div>
      <p className="mt-0.5 truncate text-[17px] font-semibold leading-tight tabular-nums text-text-primary">{k.display}</p>
      <p className={cn("truncate text-[11px] tabular-nums", TONE_TEXT[tone])} data-testid={`lens-kpi-change-${k.key}`}>
        {k.change_display ? <>{deltaArrow(k.change)} {k.change_display.replace(/^\+/, "")} <span className="text-text-muted">on prior</span></> : <span className="text-text-muted">No prior period</span>}
      </p>
      <div className="mt-1 h-7"><Spark values={k.spark.map((s) => s.value)} ariaLabel={`${k.label} trend`} /></div>
    </div>
  );
}

export function KpiStrip({ kpis, panelOpen }: { kpis: Kpi[]; panelOpen: boolean }) {
  if (!kpis.length) return null;
  return (
    <div className={cn("grid gap-2", stripCols(kpis.length, panelOpen))} data-testid="lens-kpis" data-count={kpis.length}>
      {kpis.map((k) => <KpiTile key={k.key} k={k} />)}
    </div>
  );
}
