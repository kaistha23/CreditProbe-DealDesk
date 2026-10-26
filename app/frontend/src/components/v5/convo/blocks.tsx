"use client";

/**
 * The shared renderer for the conversational layer's answer blocks
 * (docs/v5/CONVO_API.md section 6): the written answer (markdown), tables and
 * Plotly charts drawn from the run's own query results. Modules render their
 * own block types beside these. Executive Ivory: one card, table and chart
 * style; the evidence (queries run) sits behind an (i), never inline.
 */

import * as React from "react";
import { Info } from "lucide-react";

import { type ConvoAnswer, type ConvoBlock, formatCell } from "@/lib/v5/convo";
import { header as plainHeader } from "@/lib/v5/format";
import { orderRatingTable } from "@/lib/v5/ratings";

import { AnswerChart, AnswerProse, AnswerTable, bankerLabel, bankerText } from "@/components/answer";

/** PLAN_R12 N2: tables, charts and prose are the shared answer renderer's (components/answer). */
export { seriesHover } from "@/components/answer";
export { AnswerMarkdown as ConvoMarkdown } from "@/components/v5/thread/markdown";

export function ConvoTable({ block, testId }: { block: Extract<ConvoBlock, { type: "table" }>; testId?: string }) {
  const rows = orderRatingTable(block.rows, block.columns);
  const numeric = (k: string) => rows.some((r) => typeof r[k] === "number" || typeof r[k] === "boolean");
  return (
    <AnswerTable title={block.title || undefined} testId={testId ?? "convo-table"} rowCount={block.row_count ?? undefined}
                 columns={block.columns.map((c) => ({ key: c.key, label: c.label && c.label !== c.key ? c.label : plainHeader(c.key), align: numeric(c.key) ? "right" : "left" }))}
                 rows={rows.map((r) => Object.fromEntries(block.columns.map((c) => [c.key, formatCell(r[c.key], c.key)])))} />
  );
}

export function ConvoChart({ block, testId }: { block: Extract<ConvoBlock, { type: "chart" }>; testId?: string }) {
  return <AnswerChart block={block as never} testId={testId ?? "convo-chart"} />;
}

/** The (i) behind which the queries and tools of an answer are listed (G1: never inline). */
export function EvidenceInfo({ answer }: { answer: ConvoAnswer }) {
  const [open, setOpen] = React.useState(false);
  const ev = answer.evidence ?? [];
  if (!ev.length) return null;
  return (
    <div className="text-[11px] text-text-muted">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid="convo-evidence-toggle"
              className="inline-flex items-center gap-1 hover:text-text-secondary" title="How this answer was computed">
        <Info size={12} /> {ev.length} {ev.length === 1 ? "query" : "queries"}</button>
      {open ? (
        <ol className="mt-1 space-y-1 rounded-md border border-border bg-surface-hover/40 p-2" data-testid="convo-evidence">
          {ev.map((e) => (
            <li key={e.artifact_id}>
              <span className="font-semibold">{e.artifact_id}</span> · {e.purpose ? bankerText(e.purpose) : e.tool ? bankerLabel(`\`${e.tool}\``) : "query"} · {e.row_count} rows
              {e.sql ? <pre className="mt-0.5 whitespace-pre-wrap font-mono text-[10px]">{e.sql}</pre> : null}
            </li>))}
        </ol>) : null}
    </div>
  );
}

/** Render one shared block; returns null for a module's own block type. */
export function ConvoBlockView({ block, index }: { block: ConvoBlock; index: number }) {
  switch (block.type) {
    case "answer":
      // PLAN_R12 N2: the answer block leads with its headline sentence.
      return <AnswerProse text={String((block as { markdown: string }).markdown ?? "")} headline />;
    case "table":
      return <ConvoTable block={block as Extract<ConvoBlock, { type: "table" }>} testId={`convo-table-${index}`} />;
    case "chart":
      return <ConvoChart block={block as Extract<ConvoBlock, { type: "chart" }>} testId={`convo-chart-${index}`} />;
    case "error":
      return <p className="text-[13px] text-negative" role="alert">{String((block as { text: string }).text)}</p>;
    default:
      return null;
  }
}

export function isConvoBlock(b: { type: string }): boolean {
  return b.type === "answer" || b.type === "table" || b.type === "chart";
}
