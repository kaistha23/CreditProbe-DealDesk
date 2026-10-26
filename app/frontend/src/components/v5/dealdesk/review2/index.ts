/**
 * PLAN_R12 Session B exports for U's shell (mount behind a feature check):
 *
 *   ReviewStepBody   the Review step body (credit view; view="prepare" for the RM)
 *   PreflightPanel   the Prepare view's pre-flight check, with documents and credit's queries
 *   DocumentsPanel   the document checklist (also from ../documents-panel)
 *   DocumentsBadge   the action-bar button "Documents (n)"
 *   QueriesPanel     RM queries through Mail
 *   review2Api       the client; types in ./helpers
 */
export { ReviewStepBody } from "./review-step";
export { PreflightPanel } from "./preflight-panel";
export { QueriesPanel } from "./queries-panel";
export { DocumentsBadge, DocumentsPanel } from "../documents-panel";
export { review2Api } from "./api";
export type { Documents, Finding, Preflight, Queries, Query, Review2 } from "./helpers";

// ---------------------------------------------------------------- adapters for U's slots (r12-slots.tsx SlotProps)
export { DocumentsSlot, ReviewSlot, documentsMissing } from "./slots";
