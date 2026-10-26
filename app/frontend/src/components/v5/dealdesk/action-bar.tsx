"use client";

/**
 * R13 Session X (J10): the deal page is the R11 page again; R12's add-ons sit behind one **More** menu in the header:
 *   Documents (n missing) · Group & SWOT · Write proposal · Committee paper · Try it on your documents.
 * R13 M adds the deal-level intelligence below a rule: Financial quality (Q), Committee questions, Make it approvable,
 * Security value, Decision consistency (IA) and Covenant designer (IB); each opens its panel in the same dialog.
 * Optimise and the deal actions (Share, Add to report, Word) are back on the composer bar, as in R11 (`DealBarActions`).
 * Write proposal and Committee paper open Session F's panels when merged, else the R11 drafter and the committee agent;
 * Documents opens Session B's checklist (absent: no item); Group & SWOT opens Session C's panels.
 *
 * Before R13: R12 Session U's action bar (PLAN_R12 §1.2, I23) above the step bar.
 */

import * as React from "react";
import { Building2, FileSearch, FileText, FolderOpen, FolderSearch, Gavel, Lightbulb, MoreHorizontal, Sparkles, X } from "lucide-react";

import { Dropdown, type DropdownItem } from "@/components/v5/ui/dropdown"; // R14 U (K28)
import type { Proposal, Terms } from "@/lib/v5/dealdesk";
import { type View, primaryAction } from "@/lib/v5/dealdesk-r12";

import { PrepareForCommitteeButton } from "./agent-committee";
import { DraftProposalButton } from "./draft-proposal";
import { PrimaryButton } from "./kit";
import { SLOT_COUNTS, Slot, hasSlot } from "./r12-slots";
import { DealActions } from "./share";
import { TryDocsRun } from "./try-docs";
import { APPROVAL_MORE_ITEMS } from "./intel"; // R13 IA
import { CovenantDesignerPanel } from "../intel/ib"; // R13 IB
import { FinQualityPanel } from "./fin-quality"; // R13 Q
import { CommitteeRehearsalPanel, INTEL2_MORE_ITEMS } from "./intel2"; // R14 i: D6-D13 (D13 = Committee questions, K29)
import { CustomerFilePanel } from "./intake"; // R16 i: the customer file (documents, checklist, reconciliation, bank data)
import { DealPapers } from "./paperws/open"; // Round W: the deal's Papers

function Dialog({ label, onClose, children, testId }: { label: string; onClose: () => void; children: React.ReactNode; testId: string }) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={label} data-testid={testId}
         className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="relative h-[calc(100vh-2rem)] w-full max-w-[1180px] overflow-y-auto rounded-xl bg-surface-sunken p-3 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} aria-label="Close" data-testid={`${testId}-close`}
                className="absolute right-3 top-3 z-10 inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={15} /></button>
        {children}
      </div>
    </div>
  );
}

type Item = "documents" | "group" | "write" | "committee" | "try" | string;

/** R13 M: the deal-level intelligence panels (keys match lib/v5/intel-intents.ts so ?intel=<key> names the same panel). */
const INTEL_ITEMS: { key: string; label: string; Panel: React.ComponentType<{ proposalId: string }> }[] = [
  { key: "fin-quality", label: "Financial quality", Panel: ({ proposalId }) => <FinQualityPanel proposalId={proposalId} /> },
  ...APPROVAL_MORE_ITEMS.map((i) => ({
    key: ({ "committee-questions": "challenger", "make-approvable": "reverse", "security-value": "security", "decision-consistency": "consistency" } as Record<string, string>)[i.key] ?? i.key,
    label: i.label, Panel: i.key === "committee-questions" ? CommitteeRehearsalPanel : i.Panel })),
  { key: "covenants", label: "Covenant designer", Panel: ({ proposalId }) => <CovenantDesignerPanel proposalId={proposalId} /> },
  ...INTEL2_MORE_ITEMS, // R14 i
];

/** R14 U (K28): one short muted line per intelligence item, so the menu says what each panel is for. */
const INTEL_HINT: Record<string, string> = {
  "fin-quality": "Red flags in the statements and the audit",
  challenger: "What the committee will ask, and what to prepare",
  reverse: "The smallest change that gets it approved",
  security: "What each piece of security is worth to the bank",
  consistency: "Similar past deals: same decision?",
  covenants: "Covenant levels that would have warned early",
};

export function MoreMenu({ proposal, view, terms }: { proposal: Proposal; view: View; terms: Terms | null }) {
  const pid = proposal.proposal_id;
  const [open, setOpen] = React.useState<Item | null>(null);
  const [missing, setMissing] = React.useState<number | null>(null);
  const primary = primaryAction(view);
  React.useEffect(() => {
    let live = true;
    const count = hasSlot("Documents") ? SLOT_COUNTS.documentsMissing : undefined;
    if (count) void count(pid).then((n) => { if (live) setMissing(n); }).catch(() => null);
    return () => { live = false; };
  }, [pid]);
  const pick = (i: Item) => () => setOpen(i);
  const close = React.useCallback(() => setOpen(null), []);
  // R14 U (K28): the house dropdown, two sections, one-line labels, the count explained ("8 missing documents").
  const dealFile: DropdownItem[] = [
    { key: "customer-file", label: "Customer file", icon: <FolderSearch />, onSelect: pick("customer-file"), testId: "dealdesk-action-customer-file",
      description: "The customer's documents, checklist and bank data" }, // R16 i
    ...(hasSlot("Documents") ? [{ key: "documents", label: "Documents", icon: <FolderOpen />, onSelect: pick("documents"), testId: "dealdesk-action-documents",
                                  description: missing ? undefined : "Checklist of the deal file", badge: { count: missing, noun: "missing document" } }] : []),
    ...(hasSlot("Group") ? [{ key: "group", label: "Group & SWOT", description: "Connected parties, strengths and weaknesses", icon: <Building2 />, onSelect: pick("group"), testId: "dealdesk-action-group" }] : []),
    hasSlot("WriteProposal")
      ? { key: "write", label: "Write proposal", icon: <FileSearch />, onSelect: pick("write"), testId: "dealdesk-action-write", emphasis: primary === "write" }
      : { key: "write", label: "Write proposal", testId: "dealdesk-action-write",
          render: () => <DraftProposalButton proposalId={pid} label="Write proposal" secondary testId="dealdesk-action-write-draft" /> },
    hasSlot("CommitteePaper")
      ? { key: "committee", label: "Committee paper", icon: <Gavel />, onSelect: pick("committee"), testId: "dealdesk-action-committee" }
      : { key: "committee", label: "Committee paper", testId: "dealdesk-action-committee",
          render: () => <PrepareForCommitteeButton proposalId={pid} label="Committee paper" /> },
    { key: "try", label: "Try it on your documents", icon: <FileText />, onSelect: pick("try"), testId: "dealdesk-action-try" },
    { key: "papers", label: "Papers", description: "The deal's living documents: reopen one with Noor", icon: <FileText />, onSelect: pick("papers"), testId: "dealdesk-action-papers" }, // Round W
  ];
  const intelligence: DropdownItem[] = INTEL_ITEMS.map((i) => ({
    key: i.key, label: i.label, description: INTEL_HINT[i.key], icon: <Lightbulb />, onSelect: pick(i.key), testId: `dealdesk-intel-${i.key}` }));
  return (
    <>
      <Dropdown label="More" icon={<MoreHorizontal />} testId="dealdesk-more" buttonTestId="dealdesk-more-button" menuTestId="dealdesk-more-menu"
                badge={{ count: missing, noun: "missing document" }} width={280} wrapperProps={{ "data-view": view }}
                sections={[{ title: "Deal file", items: dealFile }, { title: "Intelligence", items: intelligence }]} />
      {open === "documents" ? <Dialog label="Documents" onClose={close} testId="dealdesk-documents-dialog"><Slot name="Documents" props={{ proposalId: pid, onClose: close }} /></Dialog> : null}
      {open === "group" ? (
        <Dialog label="Group & SWOT" onClose={close} testId="dealdesk-group-dialog">
          <div className="space-y-4 pt-8"><Slot name="Group" props={{ proposalId: pid }} /><Slot name="Swot" props={{ proposalId: pid, terms }} /></div>
        </Dialog>) : null}
      {open === "write" ? <Dialog label="Write proposal" onClose={close} testId="dealdesk-write-dialog"><Slot name="WriteProposal" props={{ proposalId: pid, onClose: close }} /></Dialog> : null}
      {open === "committee" ? <Dialog label="Committee paper" onClose={close} testId="dealdesk-committee-dialog"><Slot name="CommitteePaper" props={{ proposalId: pid, onClose: close }} /></Dialog> : null}
      {open === "customer-file" ? <Dialog label="Customer file" onClose={close} testId="dealdesk-customer-file-dialog"><CustomerFilePanel proposalId={pid} /></Dialog> : null}
      {open === "papers" ? <Dialog label="Papers" onClose={close} testId="dealdesk-papers-dialog"><div className="pt-8"><DealPapers proposalId={pid} /></div></Dialog> : null}
      {open === "try" ? <Dialog label="Try it on your documents" onClose={close} testId="try-docs-dialog"><TryDocsRun onExit={close} /></Dialog> : null}
      {INTEL_ITEMS.filter((i) => i.key === open).map((i) => (
        <Dialog key={i.key} label={i.label} onClose={close} testId={`dealdesk-intel-${i.key}-dialog`}>
          <div className="pt-8"><i.Panel proposalId={pid} /></div></Dialog>))}
    </>
  );
}

/** R11's composer-bar actions, restored: the deal actions (Share, Add to report, Word) and Optimise. */
export function DealBarActions({ proposal, hasRecommendation, busy, optimising, onOptimise, onNotice }: {
  proposal: Proposal; hasRecommendation: boolean; busy: boolean; optimising: boolean; onOptimise: () => void; onNotice: (m: string) => void;
}) {
  return (
    <>
      <DealActions proposal={proposal} hasRecommendation={hasRecommendation} disabled={busy} onNotice={onNotice} compact />
      <PrimaryButton onClick={onOptimise} disabled={busy} data-testid="dealdesk-optimise">
        <Sparkles size={14} /> {optimising ? "Optimising…" : "Optimise"}</PrimaryButton>
    </>
  );
}
