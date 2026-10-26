"use client";

/**
 * The one answer renderer (PLAN_R12 N2, R11_FEEDBACK I9 and I10): every conversational layer (Cockpit through
 * FX-R12-02, Deal Desk, What-If, Lenses, Playbook, Projects, Scorecard, Admin, BRF and the agents' drawers) shows its
 * answers in this shape:
 *
 *   1. the headline sentence, first and in the headline type;
 *   2. the key figures, as tiles;
 *   3. the body in the refined type scale, key figures in bold, anything past a screenful behind "Show more";
 *   4. tables compact in the house kit (first rows, then "Show more") and charts in Plotly with the shared theme;
 *   5. the module's own blocks, in order;
 *   6. follow-up chips in banker language, then the footer (trace chip, evidence (i)).
 *
 * Modules with their own block types wrap them in `AnswerFrame` (the spacing and type scale) and use the pieces
 * (`AnswerProse`, `AnswerTable`, `AnswerChart`, `AnswerFigures`, `AnswerChips`) for the shared ones.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { type AnswerChartBlock, AnswerChart } from "./chart";
import { AnswerChips } from "./chips";
import { type AnswerFigure, AnswerFigures } from "./figures";
import { AnswerHeadline, AnswerProse } from "./prose";
import { A } from "./styles";
import { type AnswerColumn, AnswerTable } from "./table";

/** The container every answer sits in: one stack rhythm, one type scale. */
export function AnswerFrame({ children, compact = false, className, testId, ...rest }: {
  children: React.ReactNode; compact?: boolean; className?: string; testId?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children" | "className">) {
  return (
    <div className={cn("min-w-0", compact ? A.stackCompact : A.stack, className)} data-testid={testId} data-answer-style="r12" {...rest}>
      {children}
    </div>
  );
}

export interface AnswerTableData { title?: string; columns: AnswerColumn[]; rows: Record<string, React.ReactNode>[]; rowCount?: number }

export function Answer({ headline, markdown, figures, tables, charts, children, chips, onAsk, busy = false, footer, compact = false, testId = "answer" }: {
  /** The headline sentence; when absent, the first sentence of `markdown` is used. */
  headline?: string;
  markdown?: string;
  figures?: AnswerFigure[];
  tables?: AnswerTableData[];
  charts?: AnswerChartBlock[];
  /** The module's own blocks, after the shared ones. */
  children?: React.ReactNode;
  chips?: readonly { label: string; send?: string }[];
  onAsk?: (text: string) => void;
  busy?: boolean;
  footer?: React.ReactNode;
  compact?: boolean;
  testId?: string;
}) {
  return (
    <AnswerFrame compact={compact} testId={testId}>
      {headline ? <AnswerHeadline text={headline} compact={compact} /> : null}
      {figures?.length ? <AnswerFigures items={figures} compact={compact} /> : null}
      {markdown ? <AnswerProse text={markdown} headline={!headline} compact={compact} /> : null}
      {(charts ?? []).map((c, i) => <AnswerChart key={`c${i}`} block={c} testId={`${testId}-chart-${i}`} />)}
      {(tables ?? []).map((t, i) => <AnswerTable key={`t${i}`} title={t.title} columns={t.columns} rows={t.rows} rowCount={t.rowCount} testId={`${testId}-table-${i}`} />)}
      {children}
      {chips?.length && onAsk ? <AnswerChips chips={chips} onAsk={(s) => onAsk(s)} busy={busy} testId={`${testId}-chips`} /> : null}
      {footer ? <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">{footer}</div> : null}
    </AnswerFrame>
  );
}
