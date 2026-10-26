"use client";

/**
 * PLAN_R12 Session F (I23, I25): "Write proposal". The full bank-form credit proposal drafted from Data Domains on the
 * 20-section anatomy plus the CreditProbe sections: business voice for the action requested, credit voice for the comments
 * and the recommendation. Downloads in Word and PDF. The R11 short memo stays one click away as "Summary memo".
 * U mounts it from the action bar: <WriteProposalDialog proposalId={id} onClose={...} />.
 */

import * as React from "react";
import { Download, FileText, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { checksLine, type Paper, paperUrls } from "./model";
import { errorText, fileHref, getJson, SectionView } from "./paper-view";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeWriteProposal } from "@/lib/v5/plain-words-g/deal";

type Tab = "bank_form" | "summary_memo";

export function WriteProposalPanel({ proposalId, onClose, initialTab = "bank_form" }: { proposalId: string; onClose: () => void; initialTab?: Tab }) {
  const urls = paperUrls(proposalId);
  const [tab, setTab] = React.useState<Tab>(initialTab);
  const [paper, setPaper] = React.useState<Paper | null>(null);
  const [error, setError] = React.useState("");
  const [polish, setPolish] = React.useState(false);
  const [memo, setMemo] = React.useState<{ draft_id: string; sections: { heading: string }[] } | null>(null);
  const [memoBusy, setMemoBusy] = React.useState(false);
  const [memoError, setMemoError] = React.useState("");

  React.useEffect(() => {
    let live = true;
    getJson<Paper>(`${urls.bankForm}${polish ? "?polish=true" : ""}`).then((p) => { if (live) setPaper(p); }, (e: unknown) => { if (live) setError(errorText(e)); });
    return () => { live = false; };
  }, [urls.bankForm, polish]);

  React.useEffect(() => {
    if (tab !== "summary_memo" || memo) return;
    let live = true;
    getJson<{ draft_id: string; sections: { heading: string }[] }>(urls.summaryMemo).then((d) => { if (live) setMemo(d); }, () => undefined);
    return () => { live = false; };
  }, [tab, memo, urls.summaryMemo]);

  const draftMemo = () => {
    setMemoBusy(true);
    setMemoError("");
    getJson<{ draft_id: string; sections: { heading: string }[] }>(urls.summaryMemo, { method: "POST", body: JSON.stringify({}) })
      .then(setMemo, (e: unknown) => setMemoError(errorText(e))).finally(() => setMemoBusy(false));
  };

  const checks = paper ? checksLine(paper) : null;
  const q = polish ? "?polish=true" : "";
  return (
      <Card className="w-full max-w-5xl space-y-4 p-6" data-testid="dealdesk-write-proposal">
        <div className="flex flex-wrap items-center gap-2">
          <FileText size={16} className="text-accent" aria-hidden />
          <h2 className="text-[16px] font-semibold text-text-primary">Write proposal</h2>
          {paper ? <span className="text-[12px] text-text-muted">{paper.customer} · as at {paper.as_of_label}</span> : null}
          <button type="button" onClick={onClose} aria-label="Close" data-testid="dealdesk-write-proposal-close"
                  className="ml-auto rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>
        <PanelWords panel="write" className="" lines={paper ? () => writeWriteProposal(paper) : error ? [] : null} />
        <div className="flex gap-1 border-b border-border" role="tablist">
          {([["bank_form", "Credit proposal (bank form)"], ["summary_memo", "Summary memo"]] as [Tab, string][]).map(([k, lab]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`dealdesk-write-proposal-tab-${k}`}
                    className={`-mb-px border-b-2 px-3 py-2 text-[12px] font-medium ${tab === k ? "border-accent text-text-primary" : "border-transparent text-text-muted hover:text-text-secondary"}`}>{lab}</button>))}
        </div>

        {tab === "bank_form" ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {checks ? <Chip tone={checks.tone} testId="dealdesk-write-proposal-checks">{checks.text}</Chip> : null}
              <label className="ml-auto flex items-center gap-1 text-[12px] text-text-secondary">
                <input type="checkbox" checked={polish} onChange={(e) => { setPaper(null); setError(""); setPolish(e.target.checked); }} data-testid="dealdesk-write-proposal-polish" />
                Polish wording (figures never change)
              </label>
              <a href={fileHref(urls.bankFormDocx + q)} data-testid="dealdesk-write-proposal-docx"><PrimaryButton type="button"><Download size={14} aria-hidden /> Word</PrimaryButton></a>
              <a href={fileHref(urls.bankFormPdf + q)} data-testid="dealdesk-write-proposal-pdf"><SecondaryButton type="button"><Download size={14} aria-hidden /> PDF</SecondaryButton></a>
            </div>
            {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
            {!paper && !error ? <Skeleton className="h-96 w-full" /> : null}
            {paper ? (
              <div className="space-y-4" data-testid="dealdesk-write-proposal-paper">
                {paper.gaps.length ? (
                  <p className="text-[12px] text-text-secondary">Data not yet in Data Domains for {paper.gaps.length} section(s); those sections say so rather than estimate:{" "}
                    {paper.gaps.map((g) => g.heading).join("; ")}.</p>) : null}
                {paper.sections.map((s, i) => <SectionView key={s.key} s={s} index={i} />)}
              </div>) : null}
          </>
        ) : (
          <div className="space-y-3" data-testid="dealdesk-write-proposal-memo">
            <p className="flex items-center gap-1 text-[12px] text-text-secondary">Summary memo in the house style<InfoPopover title="Summary memo">The short memo in the house style, drafted from the same data: request, facilities, financials, security, risks and recommendation.</InfoPopover></p>
            <div className="flex items-center gap-2">
              <PrimaryButton type="button" onClick={draftMemo} disabled={memoBusy} data-testid="dealdesk-write-proposal-memo-draft">{memo ? "Redraft summary memo" : "Draft summary memo"}</PrimaryButton>
              {memo ? <a href={fileHref(urls.summaryMemoDocx(memo.draft_id))} data-testid="dealdesk-write-proposal-memo-docx"><SecondaryButton type="button"><Download size={14} aria-hidden /> Word</SecondaryButton></a> : null}
            </div>
            {memoError ? <p className="text-[12px] text-negative" role="alert">{memoError}</p> : null}
            {memo ? <p className="text-[12px] text-text-primary">Draft {memo.draft_id}: {memo.sections.length} sections ({memo.sections.map((s) => s.heading).join(", ")}).</p> : null}
          </div>)}
      </Card>);
}

/** The panel inside its own modal overlay (stand-alone use). U's action bar mounts `WriteProposalPanel` inside its own dialog. */
export function WriteProposalDialog(props: { proposalId: string; onClose: () => void; initialTab?: Tab }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-4 sm:p-8" role="dialog" aria-modal="true"
         aria-label="Write proposal" data-testid="dealdesk-write-proposal-dialog" onClick={props.onClose}>
      <div className="w-full max-w-5xl" onClick={(e) => e.stopPropagation()}><WriteProposalPanel {...props} /></div>
    </div>);
}
