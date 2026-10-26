"use client";

/**
 * One Deal Desk answer, in the shared answer renderer (PLAN_R12 N2): the
 * headline sentence first, its blocks (text, compact tables, Plotly charts),
 * a compact trace chip, and the follow-up chips in banker language.
 */

import * as React from "react";
import { ShieldCheck } from "lucide-react";

import { ANSWER_STYLE, AnswerChart, AnswerChips, AnswerFrame, AnswerProse, AnswerTable, chipSlug } from "@/components/answer";
import { cn } from "@/lib/utils";
import type { AnswerT, Block } from "@/lib/v5/dealdesk";
import { cell } from "@/lib/v5/format";
import { withoutOfferEnding } from "@/lib/v5/thread-actions";  // R16 t (M7): no "say the word and I'll…" endings

import { Chip } from "./kit";

/** Deal Desk prose (PLAN_R12 N2): the shared answer renderer's prose, shown whole. */
export function Markdown({ text }: { text: string }) {
  return <AnswerProse text={text} fold={false} />;
}

/** The engine commentary puts one statement per line; the Cockpit renderer needs a blank line between paragraphs
 *  (list items and table rows stay together). */
export function paragraphs(md: string): string {
  const lines = md.split("\n");
  const kind = (l: string) => (/^\s*[-•*]\s+/.test(l) ? "li" : /^\s*\|/.test(l) ? "tr" : l.trim() ? "p" : "blank");
  let out = "";
  lines.forEach((l, i) => {
    if (i > 0) {
      const a = kind(lines[i - 1]), b = kind(l);
      out += (a === b && (a === "li" || a === "tr")) || a === "blank" || b === "blank" ? "\n" : "\n\n";
    }
    out += l;
  });
  return out;
}

function BlockView({ b, lead }: { b: Block; lead: boolean }) {
  if (b.type === "text" || b.type === "commentary" || b.type === "draft") {
    return (
      <div className={cn(b.type === "draft" && "rounded-lg border border-border bg-canvas p-3.5")} data-testid={`dealdesk-block-${b.type}`}>
        {b.title ? <p className={cn(ANSWER_STYLE.label, "mb-1.5")}>{b.title}</p> : null}
        {/* PLAN_R12 N2: the answer's first text block leads with its headline sentence; a draft is shown whole. */}
        <AnswerProse text={paragraphs(withoutOfferEnding(b.markdown ?? ""))} headline={lead && b.type !== "draft"} fold={b.type !== "draft"} />
      </div>);
  }
  if (b.type === "table" && b.header && b.rows) {
    const header = b.header;
    return (
      <AnswerTable title={b.title || undefined} testId="dealdesk-block-table"
                   columns={header.map((h, i) => ({ key: String(i), label: h, align: i > 0 ? "right" : "left" }))}
                   rows={b.rows.map((r) => Object.fromEntries(r.map((c, j) => [String(j), cell(c, b.keys?.[j] ?? "", header[j] ?? "")])))} />);
  }
  if (b.type === "chart" && Array.isArray(b.rows) && b.rows.length) {
    return <AnswerChart testId="dealdesk-block-chart"
                        block={{ kind: String(b.kind ?? "bar"), title: b.title, x: String(b.x), y: (b.y as string[]) ?? [],
                                 labels: (b.labels as Record<string, string>) ?? {}, rows: b.rows as unknown as Record<string, unknown>[] }} />;
  }
  if (b.type === "refusal") {
    return <div className="rounded-lg border border-warning/40 bg-warning-muted p-3" data-testid="dealdesk-block-refusal"><AnswerProse text={b.markdown ?? ""} fold={false} /></div>;
  }
  return null;
}

export function AnswerView({ answer, onAsk, busy, chips = true }: { answer: AnswerT; onAsk: (t: string) => void; busy: boolean; chips?: boolean }) {
  const v = answer.validation;
  const traceTip = v ? `${v.checked} figures checked against ${answer.trace_ids.length} engine calls` : "";
  const lead = answer.blocks.findIndex((b) => (b.type === "text" || b.type === "commentary") && (b.markdown ?? "").trim());
  return (
    <AnswerFrame data-intent={answer.intent} testId="dealdesk-answer">
      {answer.blocks.map((b, i) => <BlockView key={i} b={b} lead={i === lead} />)}
      <div className="flex flex-wrap items-center gap-2">
        {v ? <Chip tone={v.passed ? "positive" : "warning"} title={traceTip} testId="dealdesk-trace-chip">
          <ShieldCheck size={12} /> {v.passed ? "Traced" : "Check"}</Chip> : null}
        {/* PLAN_R12 N2 (I9): chips in banker language only, never a tool name. */}
        {chips ? <AnswerChips chips={answer.suggestions} onAsk={(send) => onAsk(send)} busy={busy} testId="dealdesk-chips"
                              chipTestId={(label) => `dealdesk-chip-${chipSlug(label)}`} /> : null}
      </div>
    </AnswerFrame>
  );
}
