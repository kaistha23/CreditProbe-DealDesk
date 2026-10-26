"use client";

/**
 * A sparkline small enough to put three of them on a customer row.
 *
 * Ported unchanged in behaviour from the Retail Demo (c0db151f,
 * app/early-warning/spark.tsx); a point is a period, not only a month.
 *
 * Drawn with Plotly (static, through the shared surface) but mounted only
 * when the card comes near the viewport: fifty customer cards carrying three
 * live charts each would stop the list scrolling. The figure, label and change
 * text render immediately; the line and, where a threshold matters, a dotted
 * reference line across it, arrive as the card scrolls into view.
 *
 * A point with no value is a GAP, not a zero: a customer with no behavioural
 * score in their first month on book has not scored zero, and drawing it that
 * way would invent a fall.
 */

import * as React from "react";

import { PlotlySpark } from "@/components/answer/spark";
import { cn } from "@/lib/utils";

export interface SparkPoint {
  period: string;
  value: number | null;
}

export function Spark({
  points, label, unit = "", tone = "accent", bands, height = 34,
  testId, empty = "no history", directional = false,
}: {
  points: SparkPoint[];
  label: string;
  unit?: string;
  tone?: "accent" | "negative" | "warning" | "positive";
  /** Horizontal reference lines, in the series' own units. */
  bands?: { value: number; label: string }[];
  height?: number;
  /** Kept for callers; the Plotly sparkline fills its column. */
  width?: number;
  testId?: string;
  empty?: string;
  /**
   * PLAN_R5 (Session E): a series where higher is worse, read on its LAST move. The figure shows
   * the change on the previous period, and the line is green when it fell, red when it rose, so
   * an improving card reads as improving at a glance. Off: the change over the whole window, in
   * the series' own tone.
   */
  directional?: boolean;
}) {
  const usable = points.filter((p) => p.value !== null && Number.isFinite(p.value));
  const last = usable.length ? usable[usable.length - 1].value : null;
  const first = usable.length ? usable[0].value : null;
  const previous = usable.length > 1 ? usable[usable.length - 2].value : null;
  const moved = directional
    ? (last !== null && previous !== null ? last - previous : null)
    : (last !== null && first !== null ? last - first : null);
  const direction = moved === null || Math.abs(moved) < 0.05 ? "flat" : moved > 0 ? "up" : "down";
  const shown = directional ? (direction === "up" ? "negative" : direction === "down" ? "positive" : "accent") : tone;

  const stroke = {
    accent: "var(--ipm-accent)",
    negative: "var(--ipm-negative)",
    warning: "var(--ipm-warning)",
    positive: "var(--ipm-positive)",
  }[shown];

  // Each point is a period; a missing value stays null so the line breaks there.
  const values = points.map((p) => (p.value !== null && Number.isFinite(p.value) ? p.value : null));

  return (
    <div className="min-w-0" data-testid={testId} data-direction={direction}>
      {/* The label sits on its own line rather than beside the figure. Three
          of these across a customer card leaves about eight characters on the
          same row as the number, and "Behavioural" was rendering as
          "BEHAVIO…" on every card in the list. */}
      <p className="truncate text-[9px] font-medium uppercase tracking-[0.06em] text-text-muted">
        {label}
      </p>
      <div className="flex items-baseline justify-between gap-1.5">
        <span className="shrink-0 text-[11px] font-medium tabular-nums text-text-primary">
          {last === null ? "—" : `${last.toLocaleString(undefined, {
            maximumFractionDigits: unit === "%" ? 1 : 0 })}${unit}`}
          {moved !== null && Math.abs(moved) >= 0.05 ? (
            <span className={cn(
              "ml-1 text-[9px]",
              moved > 0 ? "text-negative" : "text-positive",
            )}>
              {moved > 0 ? "+" : "\u2212"}{Math.abs(moved).toLocaleString("en-US", {
                minimumFractionDigits: unit === "%" ? 1 : 0, maximumFractionDigits: unit === "%" ? 1 : 0 })}
            </span>
          ) : null}
        </span>
      </div>
      {usable.length ? (
        <PlotlySpark values={values} color={stroke} bands={(bands ?? []).map((b) => b.value)} height={height}
                     className="mt-0.5 w-full"
                     ariaLabel={`${label}: ${usable.length} periods, latest ${last}`} />
      ) : (
        <p className="mt-1 text-[10px] italic text-text-muted">{empty}</p>
      )}
    </div>
  );
}
