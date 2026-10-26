"use client";

/**
 * PLAN_R11 R7: every proposal the review workspace can open (the prepared cases and the Deal Desk proposals), with the
 * rule book's decision for each. Shown under the R9 case list on /deal-desk/review.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { countsLine, money, reviewApi } from "@/lib/v5/dealdesk-review";

import { ConditionsDueLine } from "./review-conditions";
import { Chip, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

const TONE = { negative: "negative", warning: "warning", positive: "positive" } as const;

export function ReviewSubjects({ onOpen }: { onOpen: (id: string) => void }) {
  const r = useLoad(() => reviewApi.subjects(), "review-subjects");
  return (
    <Section title="Review workspace" testId="review-subjects"
             info="Every proposal checked against the bank's review rule book: the memo's claims against the books, account conduct, bureau, audited financials and project data; internal consistency; policy and CBUAE CRM exceptions with their approval level; connected parties. Open one for the line-by-line review, counter-proposals, conditions and the committee sheet."
             action={<ConditionsDueLine />}>
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-32 w-full" /> : null}
      {r.data ? (
        <div className="max-h-[420px] overflow-auto">
          <table className={tableCls} data-testid="review-subjects-table">
            <thead className="sticky top-0 bg-surface"><tr>{["Proposal", "Borrower", "Sector", "Rating", "Amount", "Decision", "Findings", "Approval", ""].map((h) =>
              <th key={h} className={cn(thCls, h === "Amount" && "text-right")}>{h}</th>)}</tr></thead>
            <tbody>{r.data.subjects.map((s) => (
              <tr key={s.id} className="cursor-pointer hover:bg-surface-muted" onClick={() => onOpen(s.id)} data-testid="review-subject-row">
                <td className={tdCls}>{s.id}</td>
                <td className={cn(tdCls, "max-w-[220px] truncate font-medium")} title={s.name}>{s.name}</td>
                <td className={cn(tdCls, "max-w-[140px] truncate")}>{s.sector}</td><td className={tdCls}>{s.rating}</td>
                <td className={cn(tdCls, "text-right")}>{money(s.amount, s.currency)}</td>
                <td className={tdCls}>{s.decision ? <Chip tone={TONE[(s.tone ?? "positive") as keyof typeof TONE] ?? "neutral"}>{s.decision}</Chip> : "–"}</td>
                <td className={cn(tdCls, "text-text-secondary")}>{s.counts ? countsLine(s.counts) : "–"}</td>
                <td className={cn(tdCls, "max-w-[160px] truncate")} title={s.approval}>{s.approval ?? "–"}</td>
                <td className={tdCls}><SecondaryButton onClick={(e) => { e.stopPropagation(); onOpen(s.id); }}>Open</SecondaryButton></td>
              </tr>))}</tbody>
          </table>
        </div>) : null}
    </Section>
  );
}
