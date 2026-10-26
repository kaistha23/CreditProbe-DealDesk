"use client";

/**
 * PLAN_R12 Session F (I27): the committee paper. A 2-page decision summary (ask, verdict, key numbers, conditions, monitoring
 * tier, approval authority and signatures), then the full bank-form paper in committee order. Word and PDF.
 * U mounts it from the action bar: <CommitteePaperDialog proposalId={id} onClose={...} />.
 */

import * as React from "react";
import { ChevronDown, Download, Gavel, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { checksLine, type CommitteePaper, paperUrls } from "./model";
import { errorText, fileHref, getJson, SectionView } from "./paper-view";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeCommitteePaper } from "@/lib/v5/plain-words-g/deal";

export function CommitteePaperPanel({ proposalId, onClose }: { proposalId: string; onClose: () => void }) {
  const urls = paperUrls(proposalId);
  const [cp, setCp] = React.useState<CommitteePaper | null>(null);
  const [error, setError] = React.useState("");
  const [full, setFull] = React.useState(false);
  React.useEffect(() => {
    let live = true;
    getJson<CommitteePaper>(urls.committee).then((c) => { if (live) setCp(c); }, (e: unknown) => { if (live) setError(errorText(e)); });
    return () => { live = false; };
  }, [urls.committee]);
  const checks = cp ? checksLine(cp.paper) : null;
  return (
      <Card className="w-full max-w-5xl space-y-4 p-6" data-testid="dealdesk-committee-paper">
        <div className="flex flex-wrap items-center gap-2">
          <Gavel size={16} className="text-accent" aria-hidden />
          <h2 className="text-[16px] font-semibold text-text-primary">Committee paper</h2>
          {cp ? <span className="text-[12px] text-text-muted">{cp.paper.customer} · as at {cp.paper.as_of_label}</span> : null}
          <button type="button" onClick={onClose} aria-label="Close" data-testid="dealdesk-committee-paper-close"
                  className="ml-auto rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>
        <PanelWords panel="committee" className="" lines={cp ? () => writeCommitteePaper(cp) : error ? [] : null} />
        <div className="flex flex-wrap items-center gap-2">
          {cp ? <Chip tone="accent" testId="dealdesk-committee-paper-authority">Approval authority: {cp.approval_authority}</Chip> : null}
          {cp ? <Chip tone={cp.density.length ? "warning" : "positive"} testId="dealdesk-committee-paper-density">
            {cp.density.length ? `${cp.density.length} summary line(s) without a figure or source` : "Every summary line has a figure or a source"}</Chip> : null}
          {checks ? <Chip tone={checks.tone}>{checks.text}</Chip> : null}
          <a className="ml-auto" href={fileHref(urls.committeeDocx)} data-testid="dealdesk-committee-paper-docx"><PrimaryButton type="button"><Download size={14} aria-hidden /> Word</PrimaryButton></a>
          <a href={fileHref(urls.committeePdf)} data-testid="dealdesk-committee-paper-pdf"><SecondaryButton type="button"><Download size={14} aria-hidden /> PDF</SecondaryButton></a>
        </div>
        {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        {!cp && !error ? <Skeleton className="h-96 w-full" /> : null}
        {cp ? (
          <div className="space-y-4">
            <h3 className="text-[14px] font-semibold text-text-primary">Decision summary</h3>
            <div className="space-y-4" data-testid="dealdesk-committee-paper-summary">
              {cp.summary.map((s, i) => <SectionView key={s.key} s={s} index={i} numbered={false} />)}
            </div>
            <button type="button" onClick={() => setFull((v) => !v)} aria-expanded={full} data-testid="dealdesk-committee-paper-full-toggle"
                    className="flex items-center gap-1 text-[13px] font-semibold text-text-primary">
              <ChevronDown size={14} aria-hidden className={cn("transition-transform", !full && "-rotate-90")} />
              Full paper ({cp.paper.sections.length} sections in committee order)
            </button>
            {full ? (
              <div className="space-y-4" data-testid="dealdesk-committee-paper-full">
                {cp.paper.sections.map((s, i) => <SectionView key={s.key} s={s} index={i} />)}
              </div>) : null}
          </div>) : null}
      </Card>);
}

/** The panel inside its own modal overlay (stand-alone use). U's action bar mounts `CommitteePaperPanel` inside its own dialog. */
export function CommitteePaperDialog(props: { proposalId: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-4 sm:p-8" role="dialog" aria-modal="true"
         aria-label="Committee paper" data-testid="dealdesk-committee-paper-dialog" onClick={props.onClose}>
      <div className="w-full max-w-5xl" onClick={(e) => e.stopPropagation()}><CommitteePaperPanel {...props} /></div>
    </div>);
}
