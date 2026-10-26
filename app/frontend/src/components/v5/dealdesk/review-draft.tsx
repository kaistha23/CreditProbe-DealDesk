"use client";

/**
 * PLAN_R11 R6: RM drafting, "Draft from data". The factual memo sections (exposure, account conduct, bureau, financial
 * spreading, collateral) are filled from the books and the proposal record, each with its source; the judgement sections
 * (business case, risks and mitigants, recommendation) are left for the RM. Session P's house-style drafter can replace
 * the prose behind the same button.
 */

import * as React from "react";
import { Download, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { reviewApi } from "@/lib/v5/dealdesk-review";

import { Chip, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

export function ReviewDraft({ proposalId, onClose }: { proposalId: string; onClose?: () => void }) {
  const r = useLoad(() => reviewApi.draft(proposalId), `review-draft:${proposalId}`);
  return (
    <Section title="Draft from data" testId="review-draft"
             info="The factual sections of the credit memo filled from the bank's data: existing exposure (the book), account conduct (deposits), bureau, financial spreading and collateral, each with its source. The judgement sections are left for the relationship manager."
             action={<>
               <a href={reviewApi.draftUrl(proposalId)} data-testid="review-draft-docx"><PrimaryButton className="h-8 px-3 text-[12px]"><Download size={13} /> Word</PrimaryButton></a>
               {onClose ? <SecondaryButton onClick={onClose} aria-label="Close the draft"><X size={13} /></SecondaryButton> : null}
             </>}>
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-40 w-full" /> : null}
      {r.data ? (
        <div className="grid gap-3 md:grid-cols-2" data-testid="review-draft-sections">
          {r.data.sections.map((s, i) => (
            <div key={s.key + i} className={cn("min-w-0 rounded-lg border p-3", s.kind === "judgement" ? "border-dashed border-border" : "border-border")}
                 data-testid={s.kind === "fact" ? "draft-fact" : "draft-judgement"}>
              <div className="mb-1 flex items-center gap-2">
                <h3 className="text-[13px] font-semibold text-text-primary">{i + 1}. {s.title}</h3>
                <Chip tone={s.kind === "fact" ? "positive" : "neutral"}>{s.kind === "fact" ? "From data" : "For the RM"}</Chip>
              </div>
              {s.kind === "fact" ? (
                <>
                  <p className="text-[12px] leading-5 text-text-secondary">{s.text}</p>
                  {s.table ? (
                    <div className="mt-2 max-h-48 overflow-auto"><table className={tableCls}>
                      <thead><tr>{s.table.header.map((h, k) => <th key={h} className={cn(thCls, k && "text-right")}>{h}</th>)}</tr></thead>
                      <tbody>{s.table.rows.map((row, j) => <tr key={j}>{row.map((c, k) => <td key={k} className={cn(tdCls, k ? "text-right" : "whitespace-normal")}>{c}</td>)}</tr>)}</tbody>
                    </table></div>) : null}
                  <p className="mt-1 text-[10px] text-text-muted">Source: {s.source}</p>
                </>) : <p className="text-[12px] text-text-muted">The relationship manager writes this section.</p>}
            </div>))}
        </div>) : null}
    </Section>
  );
}
