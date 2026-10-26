"use client";

/**
 * An answer's blocks, in order (docs/v5/THREAD_API.md 1.4), in the shared answer renderer (PLAN_R12 N2): markdown through the frozen Cockpit `Markdown`
 * (real tables, lists, headings), tables and Plotly charts as the convo layer draws them, KPI tiles, and the
 * evidence behind one (i) (G1). A module's own block types go to `renderBlock`.
 */

import * as React from "react";

import { AnswerFigures, AnswerFrame, type AnswerFigure } from "@/components/answer";
import { ConvoChart, ConvoTable, EvidenceInfo } from "@/components/v5/convo/blocks";
import type { ConvoAnswer, ConvoBlock } from "@/lib/v5/convo";

import { AnswerMarkdown } from "./markdown";

export { AnswerMarkdown };

export type KpiItem = AnswerFigure;

/** Key figures (PLAN_R12 N2: the shared answer renderer's tiles). */
export function Kpis({ items, compact = false }: { items: KpiItem[]; compact?: boolean }) {
  return <AnswerFigures items={items} compact={compact} />;
}

export function AnswerBlocks({ blocks, evidence, renderBlock, onAsk, compact = false, testId = "answer-blocks" }: {
  blocks: ConvoBlock[]; evidence?: ConvoAnswer["evidence"];
  renderBlock?: (block: ConvoBlock, index: number, ask: (text: string) => void) => React.ReactNode | null;
  onAsk?: (text: string) => void; compact?: boolean; testId?: string;
}) {
  const ask = onAsk ?? (() => undefined);
  // PLAN_R12 N2: the first prose block carries the answer's headline sentence.
  const lead = blocks.findIndex((b) => ["answer", "markdown", "text"].includes(b.type) && String((b as Record<string, unknown>).markdown ?? (b as Record<string, unknown>).text ?? "").trim());
  return (
    <AnswerFrame compact={compact} testId={testId}>
      {blocks.map((b, i) => {
        const custom = renderBlock?.(b, i, ask);
        if (custom !== undefined && custom !== null) return <React.Fragment key={i}>{custom}</React.Fragment>;
        const any = b as Record<string, unknown>;
        switch (b.type) {
          case "answer":
          case "markdown":
          case "text": {
            const text = String(any.markdown ?? any.text ?? "");
            return text.trim() ? <AnswerMarkdown key={i} text={text} headline={i === lead} compact={compact} /> : null;
          }
          case "table":
            return <ConvoTable key={i} block={b as Extract<ConvoBlock, { type: "table" }>} testId="answer-table" />;
          case "chart":
            return <ConvoChart key={i} block={b as Extract<ConvoBlock, { type: "chart" }>} testId="answer-chart" />;
          case "kpis":
            return <Kpis key={i} items={(any.items as KpiItem[]) ?? []} compact={compact} />;
          case "error":
            return <p key={i} className="text-[13px] text-negative" role="alert">{String(any.text ?? "")}</p>;
          default:
            return null;
        }
      })}
      {evidence?.length ? <EvidenceInfo answer={{ blocks: [], suggestions: [], question_display: "", evidence }} /> : null}
    </AnswerFrame>
  );
}
