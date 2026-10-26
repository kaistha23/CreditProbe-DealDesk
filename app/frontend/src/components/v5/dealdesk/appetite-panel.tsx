"use client";

/**
 * R11 Session L (PLAN_R11 L3, L6): the risk-appetite panel. One horizontal bullet bar per limit with its
 * appetite, trigger and limit markers, the book before (hollow) and after the selection (solid), and the status.
 * Used by Pipeline mode, the pipeline test and the book view (GET /risk-appetite).
 */

import * as React from "react";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { cn } from "@/lib/utils";
import { type LimitRow, STATUS_TONE, STATUS_WORD, bullet, limitValue, panelRows } from "@/lib/v5/dealdesk-pipeline";

import { Chip } from "./kit";

const FILL: Record<string, string> = {
  green: "bg-positive", amber: "bg-warning", red: "bg-negative", "n/a": "bg-border-strong",
};

function Marker({ at, cls, label }: { at: number | null; cls: string; label: string }) {
  if (at === null) return null;
  return <span aria-hidden title={label} className={cn("absolute top-[-3px] h-[14px] w-[2px] rounded-sm", cls)} style={{ left: `calc(${at * 100}% - 1px)` }} />;
}

export function BulletRow({ r, showBefore = true, testId }: { r: LimitRow; showBefore?: boolean; testId?: string }) {
  const g = bullet(r);
  const v = r.after ?? r.before ?? null;
  const isMin = r.direction === "min";
  return (
    <div className="grid grid-cols-[minmax(0,12rem)_minmax(4rem,1fr)_minmax(0,12rem)] items-center gap-3 py-1.5" data-testid={testId}
         data-status={r.status}>
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-1">
          <p className="truncate text-[12px] font-medium text-text-primary" title={r.label}>{r.label}</p>
          <InfoPopover title={r.label}>
            <span className="block">{r.definition}</span>
            <span className="mt-1 block">Appetite {limitValue(r.appetite, r.unit)} · trigger {limitValue(r.trigger, r.unit)} ·
              limit {limitValue(r.limit, r.unit)} ({r.kind}){isMin ? ", a floor" : ""}.</span>
            <span className="mt-1 block text-text-muted">{r.basis}</span>
          </InfoPopover>
        </div>
        <p className="truncate text-[11px] text-text-muted" title={r.scope}>{r.scope}</p>
      </div>
      <div className="relative h-2 rounded-full bg-surface-hover" aria-label={`${r.label}: ${limitValue(v, r.unit)} against limit ${limitValue(r.limit, r.unit)}`}>
        {g ? (
          <>
            <span className="absolute inset-y-0 left-0 rounded-full bg-positive/15" style={{ width: `${(isMin ? 1 - (g.trigger ?? 0) : g.trigger ?? 0) * 100}%`, left: isMin ? `${(g.trigger ?? 0) * 100}%` : 0 }} />
            {g.after !== null ? <span className={cn("absolute inset-y-0 left-0 rounded-full", FILL[r.status])} style={{ width: `${g.after * 100}%` }} /> : null}
            {showBefore && g.before !== null ? (
              <span aria-hidden title={`Before ${limitValue(r.before, r.unit)}`}
                    className="absolute top-[-4px] h-4 w-2.5 -translate-x-1/2 rounded-sm border-2 border-text-secondary bg-surface"
                    style={{ left: `${g.before * 100}%` }} />) : null}
            <Marker at={g.appetite} cls="bg-positive" label={`Appetite ${limitValue(r.appetite, r.unit)}`} />
            <Marker at={g.trigger} cls="bg-warning" label={`Trigger ${limitValue(r.trigger, r.unit)}`} />
            <Marker at={g.limit} cls="bg-negative" label={`Limit ${limitValue(r.limit, r.unit)}`} />
          </>) : null}
      </div>
      <div className="flex min-w-0 items-center justify-end gap-2">
        <span className="truncate text-right text-[11.5px] tabular-nums text-text-secondary" title={showBefore && r.before !== null ? `${limitValue(r.before, r.unit)} to ${limitValue(v, r.unit)}` : undefined}>
          {showBefore && r.before !== null && r.after !== null && Math.abs((r.after ?? 0) - (r.before ?? 0)) > 1e-9
            ? <>{limitValue(r.before, r.unit)} → <span className="font-semibold text-text-primary">{limitValue(r.after, r.unit)}</span></>
            : <span className="font-semibold text-text-primary">{limitValue(v, r.unit)}</span>}
        </span>
        <Chip tone={STATUS_TONE[r.status]} title={STATUS_WORD[r.status]}>{r.status === "n/a" ? "–" : r.status === "green" ? "G" : r.status === "amber" ? "A" : "R"}</Chip>
      </div>
    </div>
  );
}

export const APPETITE_INFO = (
  <>
    Each bar is one risk-appetite limit measured on the live corporate book plus the selected new business. The hollow mark is
    the book today, the filled bar the book after the selection; green, amber and red ticks are the appetite, trigger and limit.
    Green up to the trigger, amber to the limit, red beyond it (for floors such as the RAROC floor, the other way round).
    Hard limits are never breached by a selection; a limit already past its level on the book may not get worse.
  </>
);

/** The panel: the rows that moved or are not green first, then the rest behind "Show all". */
export function AppetitePanel({ rows, showBefore = true, compact = false, testId = "dealdesk-appetite" }: {
  rows: LimitRow[]; showBefore?: boolean; compact?: boolean; testId?: string;
}) {
  const [all, setAll] = React.useState(false);
  const ordered = panelRows(rows);
  const head = compact ? 6 : 10;
  const shown = all ? ordered : ordered.slice(0, head);
  return (
    <div data-testid={testId}>
      <div className="divide-y divide-border/60">
        {shown.map((r) => <BulletRow key={`${r.name}-${r.scope}`} r={r} showBefore={showBefore} testId={`${testId}-row-${r.name}`} />)}
      </div>
      {ordered.length > head ? (
        <button type="button" onClick={() => setAll((a) => !a)} data-testid={`${testId}-toggle`}
                className="mt-2 text-[12px] text-accent hover:underline">
          {all ? "Show fewer limits" : `Show all ${ordered.length} limits`}
        </button>) : null}
    </div>
  );
}
