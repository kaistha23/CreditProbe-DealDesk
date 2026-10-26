"use client";

/**
 * Adapters from U's slot props (frontend/src/components/v5/dealdesk/r12-slots.tsx) to B's components, so mounting is one line each:
 *
 *   SLOTS.Review = ReviewSlot;          // { proposalId, view }: credit "review" → ReviewStepBody; RM "prepare" → PreflightPanel
 *   SLOTS.Documents = DocumentsSlot;    // { proposalId, onClose }: the checklist (credit can update and query)
 *   SLOT_COUNTS.documentsMissing = documentsMissing;   // B's count: required items pending or expired (B's checklist, not raw rows)
 */

import { DocumentsPanel } from "../documents-panel";
import { review2Api } from "./api";
import { PreflightPanel } from "./preflight-panel";
import { ReviewStepBody } from "./review-step";

export function ReviewSlot({ proposalId, view }: { proposalId: string; view: "prepare" | "review" }) {
  return view === "prepare" ? <PreflightPanel dealId={proposalId} /> : <ReviewStepBody dealId={proposalId} view="review" />;
}

export function DocumentsSlot({ proposalId }: { proposalId: string; onClose?: () => void }) {
  return <DocumentsPanel dealId={proposalId} editable canQuery words />;
}

export const documentsMissing = (proposalId: string): Promise<number> => review2Api.documents(proposalId).then((d) => d.missing_count);
