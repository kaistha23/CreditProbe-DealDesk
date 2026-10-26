"use client";

/**
 * R12 Session U: where the other R12 sessions' exported components mount in the Deal Desk shell (PLAN_R12 BUILD,
 * "U: Shell": mount behind feature checks; a component not merged yet leaves its slot empty, never an error).
 *
 * The feature check is this registry: a slot is filled by one import line when its session's branch is merged into
 * v5/r12-ui (U integrates at 00:30 and 01:45). An empty slot renders nothing. A filled slot renders inside an error
 * boundary, so a component that throws at run time also leaves its slot empty instead of breaking the deal page.
 */

import { useRouter } from "next/navigation";
import * as React from "react";

import { r12Api } from "@/lib/v5/dealdesk-r12";

// Mounted at U's integration rounds (docs/STATUS_R12_UI.md, "Mounted"): one import per merged session.
import { BookTab } from "./book";                                                   // I (00:30)
import { ParametersTab } from "./parameters";                                       // G (00:30)
import { DocumentsSlot, ReviewSlot, documentsMissing } from "./review2";            // B (00:30)
import { ConductBlock, GroupPanel, SwotPanel, WeaknessMitigantMap } from "./group"; // C (00:30)
import { ProductSection, SmeFastTrack } from "./products";                          // P (00:30)
import { CommitteePaperPanel } from "./papers";                                   // F (01:45); WriteProposal: R14 p
import { FinQualityPanel } from "./fin-quality";                                 // R13 Q
import { CovenantDesignerPanel } from "../intel/ib";                              // R13 IB: deal page More menu
import { BatchCheckButton, CreditProposalPreview, PrepareProposalButton, ProposalCheckStep } from "./proposal"; // R14 p

/** Props each slot passes (the adapters below map them onto each session's own export). */
export interface SlotProps {
  /** Book (Session I): the landing tab; `filter` is the card's filter (going-bad, renewals, ...). */
  BookTab: { filter?: string };
  /** Parameters & policy (Session G): the landing tab. */
  ParametersTab: Record<string, never>;
  /** Papers (Session F): the bank-form proposal and the committee paper, as dialogs over the deal page. */
  WriteProposal: { proposalId: string; onClose: () => void };
  CommitteePaper: { proposalId: string; onClose: () => void };
  /** Review (Session B): the document checklist and the 12-point review. */
  Documents: { proposalId: string; onClose: () => void };
  Review: { proposalId: string; view: "prepare" | "review" };
  /** Group (Session C): group, conduct, SWOT and the weakness-to-mitigant map. */
  Group: { proposalId: string };
  Swot: { proposalId: string; terms?: object | null };
  /** Products (Session P): the product sections of the deal and the SME fast-track lane. */
  Product: { proposalId: string };
  SmeFastTrack: Record<string, never>;
  /** R13 Q: the Financial quality panel (deal page More menu; Session X mounts it). */
  FinQuality: { proposalId: string };
  /** R13 IB: the covenant designer (deal page More menu). */
  CovenantDesigner: { proposalId: string; onClose: () => void };
  /** R14 F places, Session p fills: the Proposal check step (test id dealdesk-step-proposal-check-view wraps it) and the
   * "Prepare the credit proposal" generator on the Recommendation step (its button keeps test id dealdesk-prepare-proposal),
   * fed by the selected structure. */
  ProposalCheck: { proposalId: string; onNext?: () => void };
  PrepareProposal: { proposalId: string; structureKey: string; terms: Record<string, unknown> };
  /** R14 p (K33): "Check all pending proposals" on the landing and the Pipeline tab. */
  BatchCheck: Record<string, never>;
}
export type SlotName = keyof SlotProps;

type Registry = { [K in SlotName]?: React.ComponentType<SlotProps[K]> };

/**
 * The registry. Each line is added when the owning session's branch lands (see docs/STATUS_R12_UI.md, "Mounted").
 * A slot with no line stays empty.
 */
/** P's SME lane; an exception opens in the full Deal Desk flow. */
function SmeLane() {
  const router = useRouter();
  return <SmeFastTrack onOpenFullFlow={(r) => { if (r.proposalId) router.push(`/deal-desk/${encodeURIComponent(r.proposalId)}`); }} />;
}

export const SLOTS: Registry = {
  BookTab: ({ filter }) => <BookTab filter={filter} />,
  ParametersTab: () => <ParametersTab />,
  Review: ReviewSlot,
  Documents: DocumentsSlot,
  Group: ({ proposalId }) => <div className="space-y-4"><GroupPanel proposalId={proposalId} /><ConductBlock proposalId={proposalId} /></div>,
  Swot: ({ proposalId, terms }) => (
    <div className="space-y-4"><SwotPanel proposalId={proposalId} />
      <WeaknessMitigantMap proposalId={proposalId} terms={(terms ?? null) as Record<string, unknown> | null} label="recommended" /></div>),
  Product: ({ proposalId }) => <ProductSection proposalId={proposalId} />,
  SmeFastTrack: () => <SmeLane />,
  // R14 p (K27): More → Write proposal opens the same bank-form proposal as "Prepare the credit proposal" (R12 panel retired)
  WriteProposal: ({ proposalId }) => <div className="h-[calc(100vh-3.5rem)]"><CreditProposalPreview proposalId={proposalId} /></div>,
  CommitteePaper: CommitteePaperPanel,
  FinQuality: ({ proposalId }) => <FinQualityPanel proposalId={proposalId} />,
  CovenantDesigner: CovenantDesignerPanel,
  ProposalCheck: ({ proposalId, onNext }) => <ProposalCheckStep proposalId={proposalId} onNext={onNext} />,
  PrepareProposal: ({ proposalId, structureKey }) => <PrepareProposalButton proposalId={proposalId} structureKey={structureKey} />,
  BatchCheck: () => <BatchCheckButton />,
};

/** Counts the shell shows next to an action (e.g. Documents (n missing)); filled by the owning session's client. */
export const SLOT_COUNTS: { documentsMissing?: (proposalId: string) => Promise<number> } = {
  // The count is U's own read of dd_document (pending or expired); shown once B's checklist is mounted.
  // B's count (required items pending or expired, after its precedence rules); U's raw dd_document read is the fallback.
  documentsMissing: (pid) => documentsMissing(pid).catch(() => r12Api.documentsMissing(pid).then((r) => r.missing ?? 0)),
};

export const hasSlot = (name: SlotName): boolean => Boolean(SLOTS[name]);

class SlotBoundary extends React.Component<{ name: string; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() { /* the slot stays empty; the deal page carries on */ }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function Slot<K extends SlotName>({ name, props }: { name: K; props: SlotProps[K] }) {
  const C = SLOTS[name] as React.ComponentType<SlotProps[K]> | undefined;
  if (!C) return null;
  return (
    <SlotBoundary name={name}>
      <div data-testid={`r12-slot-${name}`} className="min-w-0"><C {...props} /></div>
    </SlotBoundary>
  );
}
