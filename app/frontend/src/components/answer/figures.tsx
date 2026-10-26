"use client";

/**
 * Key figures of an answer (PLAN_R12 N2): a row of tiles, label above value, the value in the figure style. Used
 * by every conversational layer for its headline numbers (the shared `Kpis` re-exports this).
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import { fmt } from "@/lib/v5/format";

import { A } from "./styles";

export interface AnswerFigure {
  label: string;
  value: number | string | null;
  unit?: string;
  key?: string;
  hint?: string;
  /** A short line under the value ("from 14.2%", "vs hurdle 15%"). */
  sub?: string;
  tone?: "positive" | "negative" | "warning" | "plain";
}

const TONE: Record<string, string> = { positive: "text-positive", negative: "text-negative", warning: "text-warning", plain: "text-text-primary" };

export function AnswerFigures({ items, compact = false, testId = "answer-kpis" }: { items: AnswerFigure[]; compact?: boolean; testId?: string }) {
  if (!items?.length) return null;
  const n = items.length;
  const cols = compact ? "grid-cols-2" : n <= 2 ? "grid-cols-2" : n === 3 ? "grid-cols-2 sm:grid-cols-3" : n === 4 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5";
  return (
    <div className={cn("grid gap-2.5", cols)} data-testid={testId}>
      {items.map((k) => (
        <div key={k.label} className="min-w-0 rounded-lg border border-border bg-surface px-3.5 py-2.5" title={k.hint || undefined} data-testid="answer-kpi">
          <p className={cn(A.kpiLabel, "truncate")}>{k.label}</p>
          <p className={cn(A.kpiValue, compact && "text-[16px]", TONE[k.tone ?? "plain"])}>
            {typeof k.value === "number" ? fmt.auto(k.value, k.unit || k.key || k.label) : k.value ?? "–"}</p>
          {k.sub ? <p className="mt-1 truncate text-[11px] text-text-muted">{k.sub}</p> : null}
        </div>))}
    </div>
  );
}
