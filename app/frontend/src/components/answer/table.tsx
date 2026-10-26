"use client";

/**
 * A table in an answer (PLAN_R12 N2): the house kit, compact by default. The first rows show; the rest sit behind
 * "Show more" so a long result never pushes the answer off screen. Numbers right-aligned and tabular; a rating table
 * reads AAA to D.
 */

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";

import { A } from "./styles";

export interface AnswerColumn { key: string; label: React.ReactNode; align?: "left" | "right" }

export function AnswerTable({ title, columns, rows, max = 6, testId = "answer-table", footnote, rowCount, cellClass, bare = false }: {
  title?: React.ReactNode;
  columns: AnswerColumn[];
  /** Cells already formatted (strings or nodes), by column key. */
  rows: Record<string, React.ReactNode>[];
  /** Rows shown before "Show more" (0 = all). */
  max?: number;
  testId?: string;
  footnote?: React.ReactNode;
  /** The total row count when the server sent only a slice. */
  rowCount?: number;
  cellClass?: (key: string, row: Record<string, React.ReactNode>) => string | undefined;
  /** No card around it (a table inside prose). */
  bare?: boolean;
}) {
  const [all, setAll] = React.useState(false);
  // Fold only when it hides at least two rows: "Show 1 more" is noise.
  const folds = max > 0 && rows.length > max + 1;
  const shown = folds && !all ? rows.slice(0, max) : rows;
  return (
    <div className={cn(!bare && A.card, "min-w-0")} data-testid={testId} data-rows={rows.length}>
      {title ? <p className={cn("px-3 pt-2.5 pb-1 text-[12.5px] font-semibold text-text-primary", bare && "px-0")}>{title}</p> : null}
      <div className="overflow-x-auto">
        <table className={A.table}>
          <thead>
            <tr>{columns.map((c) => <th key={c.key} className={cn(A.th, c.align === "right" && "text-right")}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i} className="hover:bg-surface-hover/50">
                {columns.map((c) => (
                  <td key={c.key} className={cn(A.td, c.align === "right" ? "whitespace-nowrap text-right" : "whitespace-normal", cellClass?.(c.key, r))}>
                    {r[c.key] ?? ""}</td>))}
              </tr>))}
          </tbody>
        </table>
      </div>
      {folds || footnote || (rowCount && rowCount > rows.length) ? (
        <div className={cn("flex flex-wrap items-center gap-3 px-3 py-1.5", bare && "px-0")}>
          {folds ? (
            <button type="button" className={A.more} onClick={() => setAll((x) => !x)} aria-expanded={all} data-testid={`${testId}-more`}>
              {all ? <><ChevronUp size={13} aria-hidden /> Show fewer</> : <><ChevronDown size={13} aria-hidden /> Show {rows.length - max} more</>}
            </button>) : null}
          {rowCount && rowCount > rows.length ? <span className="text-[11px] text-text-muted">{rows.length} of {rowCount.toLocaleString("en-US")} rows</span> : null}
          {footnote ? <span className="text-[11px] text-text-muted">{footnote}</span> : null}
        </div>) : null}
    </div>
  );
}

/** True when a formatted cell reads as a number (right-aligned). */
export function looksNumeric(v: unknown): boolean {
  if (typeof v === "number") return true;
  return typeof v === "string" && /^\s*[-+−(]?\s*(?:SAR|USD|AED|OMR)?\s?[-+−]?\d[\d,]*(?:\.\d+)?\s?(?:%|pp|bps|x|m|bn|mn|k)?\)?\s*$/i.test(v);
}
