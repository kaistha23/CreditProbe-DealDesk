/**
 * R14 i exports: the D6-D13 deal-intelligence panels, the More-menu items ("Intelligence" section) and the per-step
 * strip (`StepIntel`) that opens the panels the plan places in each step.
 *
 *   <NegotiationFrontierPanel proposalId="DD-06" />   D6  Structure
 *   <DefaultPremortemPanel …/>                        D7  Analysis + Recommendation
 *   <PrecedentExplorerPanel …/>                       D8  Review (with Decision consistency)
 *   <PricingBenchmarkPanel …/>                        D9  Proposal + Structure
 *   <RevenueTruthPanel …/>                            D10 Proposal check + Financial quality
 *   <RenewalDiffPanel …/>                             D11 Proposal step on renewals
 *   <GroupContagionPanel …/>                          D12 Review + Group & SWOT
 *   <CommitteeRehearsalPanel …/>                      D13 More · Committee questions (K29; replaces R13 IA's challenger panel)
 */
import type * as React from "react";

import { INTEL2_PANELS } from "./panels";
import { INTEL2_FEATURES } from "./model";

export {
  CommitteeRehearsalPanel, DefaultPremortemPanel, GroupContagionPanel, NegotiationFrontierPanel, PrecedentExplorerPanel, PricingBenchmarkPanel,
  RenewalDiffPanel, RevenueTruthPanel, INTEL2_PANELS,
} from "./panels";
export { StepIntel } from "./step-intel";
export { INTEL2_FEATURES, featuresForStep } from "./model";
export type { Intel2Key } from "./model";

export type Intel2MoreItem = { key: string; label: string; Panel: React.ComponentType<{ proposalId: string }> };

/** More menu, "Intelligence": the seven new panels (D13 replaces the R13 "Committee questions" entry under its key "challenger"). */
export const INTEL2_MORE_ITEMS: Intel2MoreItem[] = INTEL2_FEATURES.filter((f) => f.key !== "rehearsal")
  .map((f) => ({ key: f.panel, label: f.label, Panel: INTEL2_PANELS[f.key] }));
