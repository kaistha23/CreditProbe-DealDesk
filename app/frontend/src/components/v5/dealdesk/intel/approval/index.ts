/**
 * R13 Session IA exports for the deal page More menu (X's R11 deal page; first screens unchanged):
 *
 *   <CommitteeChallengerPanel proposalId="R12-TWA" />   the 5-7 questions committee will ask, answered from data; what the proposal avoids
 *   <ReverseSolverPanel proposalId="R12-TWA" />         the smallest change that makes a failing deal approvable, as a counter-offer
 *   <SecurityOptimiserPanel proposalId="R12-TWA" />     recovery and capital value of each security item; the cheapest package that clears
 *   <DecisionConsistencyPanel proposalId="R12-TWA" />   similar deals decided differently, explained or not
 *
 * APPROVAL_MORE_ITEMS lists them as More-menu entries (key, label, panel) so the shell mounts one on demand.
 */
import type * as React from "react";

import { CommitteeChallengerPanel } from "./challenger-panel";
import { DecisionConsistencyPanel } from "./consistency-panel";
import { ReverseSolverPanel } from "./reverse-panel";
import { SecurityOptimiserPanel } from "./security-panel";

export { CommitteeChallengerPanel, ChallengerView } from "./challenger-panel";
export { ReverseSolverPanel, ReverseView } from "./reverse-panel";
export { SecurityOptimiserPanel, SecurityView } from "./security-panel";
export { DecisionConsistencyPanel, ConsistencyView } from "./consistency-panel";
export { loadApproval, approvalUrl, INTEL_APPROVAL_PATH } from "./api";
export type { Challenger, Reverse, Security, Consistency } from "./model";

export type MoreItem = { key: string; label: string; Panel: React.ComponentType<{ proposalId: string }> };

export const APPROVAL_MORE_ITEMS: MoreItem[] = [
  { key: "committee-questions", label: "Committee questions", Panel: CommitteeChallengerPanel },
  { key: "make-approvable", label: "Make it approvable", Panel: ReverseSolverPanel },
  { key: "security-value", label: "Security value", Panel: SecurityOptimiserPanel },
  { key: "decision-consistency", label: "Decision consistency", Panel: DecisionConsistencyPanel },
];
