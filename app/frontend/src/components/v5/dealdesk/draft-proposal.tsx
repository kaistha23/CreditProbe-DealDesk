"use client";

/**
 * PLAN_R11 Session P (P5): "Draft proposal" in the bank's house language.
 *
 *   <DraftProposalButton proposalId={id} />   the action for the Proposal step and New proposal (mounted by U or M)
 *   <DraftProposal proposalId={id} />         the drafted memo: answer first, the style score (≤ 4 tiles), the sections
 *                                             (regenerate / edit / accept each), the lint, and the Word export
 *
 * Facts come only from the books and the proposal; every figure cites its source. Judgement sections are suggestions.
 */

import * as React from "react";
import { RulesApplied } from "@/components/v5/rules/rules-applied";  // Round K
import type { RuleApplied } from "@/lib/v5/dealdesk-rules";
import { Download, FileText, RefreshCw, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { type Draft, DraftError, answerLine, drafting, profileLabel } from "@/lib/v5/dealdesk-draft";

import { DraftHouseProfile } from "./draft-profile";
import { DraftLint, DraftScoreTiles } from "./draft-score";
import { DraftSectionCard } from "./draft-section";
import { PrimaryButton, Section, SecondaryButton } from "./kit";

function useDraft(proposalId: string) {
  const [state, setState] = React.useState<{ pid: string; draft: Draft | null }>({ pid: proposalId, draft: null });
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>("load");
  const current = React.useRef(proposalId);
  React.useEffect(() => { current.current = proposalId; }, [proposalId]);
  const run = React.useCallback(async (key: string, fn: () => Promise<Draft>): Promise<boolean> => {
    const pid = current.current;
    setBusy(key);
    setError(null);
    try {
      const d = await fn();
      if (current.current === pid) setState({ pid, draft: d });
      return true;
    } catch (e) {
      if (current.current === pid) setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      if (current.current === pid) setBusy(null);
    }
  }, []);
  React.useEffect(() => {
    let live = true;
    (async () => {
      try {
        const d = await drafting.latest(proposalId).catch((e: unknown) => {
          if (e instanceof DraftError && e.status === 404) return drafting.create(proposalId);  // no draft yet: draft it
          throw e;
        });
        if (live) setState({ pid: proposalId, draft: d });
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (live) setBusy(null);
      }
    })();
    return () => { live = false; };
  }, [proposalId]);
  // a draft of another proposal is never shown
  const draft = state.pid === proposalId ? state.draft : null;
  return { draft, error, busy, run };
}

export function DraftProposal({ proposalId, onClose }: { proposalId: string; onClose?: () => void }) {
  const { draft, error, busy, run } = useDraft(proposalId);
  const [focus, setFocus] = React.useState<string | null>(null);
  return (
    <div className="flex min-h-0 flex-col gap-3" data-testid="draft-proposal">
      <Section title="Draft proposal" testId="draft-proposal-head"
               info="The proposal drafted section by section from the books and the proposal, in the bank's house language (structure, phrasing, tone, number format and abbreviations learned from its own memos and exemplars). Facts never come from an exemplar; every figure cites its source. Your edits teach the house profile."
               action={<>
                 <SecondaryButton onClick={() => run("all", () => drafting.create(proposalId))} disabled={busy !== null} data-testid="draft-redraft-all">
                   <RefreshCw size={13} className={busy === "all" ? "animate-spin" : undefined} /> Redraft all</SecondaryButton>
                 {draft ? (
                   <a href={drafting.docxUrl(draft.draft_id)} data-testid="draft-export-word"
                      className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:bg-accent-hover">
                     <Download size={13} /> Word</a>) : null}
                 {onClose ? <SecondaryButton onClick={onClose} aria-label="Close the draft" data-testid="draft-close"><X size={13} /></SecondaryButton> : null}
               </>}>
        {error ? <p role="alert" className="text-[12px] text-negative" data-testid="draft-error">{error}</p> : null}
        {!draft && !error ? <div className="flex flex-col gap-2"><Skeleton className="h-5 w-3/4" /><Skeleton className="h-16 w-full" /></div> : null}
        {draft ? (
          <div className="flex flex-col gap-3">
            <p className="text-[13px] font-medium leading-snug text-text-primary" data-testid="draft-answer">{answerLine(draft)}</p>
            <p className="truncate text-[11px] text-text-muted" title={draft.title}>
              {draft.title} · house style {profileLabel(draft)} · from {draft.profile.documents} memos
              {draft.profile.primary_exemplars.length ? " · primary exemplar" : ""}{draft.profile.edits_learned ? ` · ${draft.profile.edits_learned} RM edits learned` : ""}</p>
            <DraftScoreTiles draft={draft} />
            <RulesApplied applied={(draft as { rules_applied?: RuleApplied[] }).rules_applied} testId="draft-rules-applied" />
          </div>
        ) : null}
      </Section>
      {draft ? (
        <div className="grid min-h-0 gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="flex min-w-0 flex-col gap-2" data-testid="draft-sections">
            {draft.sections.map((s, i) => (
              <DraftSectionCard key={`${s.key}-${s.version}`} s={s} index={i + 1} busy={busy !== null} spinning={busy === s.key || busy === "all"}
                focused={focus === s.key}
                onRegenerate={() => void run(s.key, () => drafting.regenerate(draft.draft_id, s.key))}
                onAccept={(accept) => void run(s.key, () => drafting.accept(draft.draft_id, s.key, accept))}
                onSave={(text) => run(s.key, () => drafting.edit(draft.draft_id, s.key, text))} />
            ))}
          </div>
          <div className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-0 lg:self-start">
            <DraftLint draft={draft} onFocus={setFocus} />
            <DraftHouseProfile proposalId={proposalId} currency={draft.meta.currency} bank={draft.meta.bank} refreshKey={draft.profile.edits_learned} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The action: opens the drafted proposal in a panel over the deal view (no page scroll; the panel scrolls). */
export function DraftProposalButton({ proposalId, label = "Draft proposal", disabled, secondary = false, testId = "draft-proposal-button" }: {
  proposalId: string; label?: string; disabled?: boolean; secondary?: boolean; testId?: string;
}) {
  const Btn = secondary ? SecondaryButton : PrimaryButton;
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <>
      <Btn onClick={() => setOpen(true)} disabled={disabled || !proposalId} data-testid={testId}>
        <FileText size={14} /> {label}</Btn>
      {open ? (
        <div role="dialog" aria-modal="true" aria-label="Draft proposal" data-testid="draft-proposal-dialog"
             className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4" onClick={() => setOpen(false)}>
          <div className="h-[calc(100vh-2rem)] w-full max-w-[1180px] overflow-y-auto rounded-xl bg-surface-sunken p-3 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <DraftProposal proposalId={proposalId} onClose={() => setOpen(false)} />
          </div>
        </div>
      ) : null}
    </>
  );
}
