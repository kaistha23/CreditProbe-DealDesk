/**
 * R12 Session C exports for U's shell (Review and Structure steps):
 *
 *   <GroupPanel proposalId="R12-TWA" />                       group, cap test and increase-cap ask, red flags, overlay
 *   <ConductBlock proposalId="R12-TWA" />                     turnover vs limits, returned cheques, utilisation, past dues, bureau
 *   <SwotPanel proposalId="R12-TWA" onOpenStep={go} />        SWOT with evidence links
 *   <WeaknessMitigantMap proposalId="R12-TWA" terms={rec.terms} label="recommended" />
 *
 * All four share one GET /api/v1/dealdesk/proposals/{id}/group/all per deal.
 */
export { GroupPanel, GroupPanelView, FlagList } from "./group-panel";
export { ConductBlock, ConductBlockView } from "./conduct-block";
export { SwotPanel, SwotView } from "./swot-panel";
export { WeaknessMitigantMap, MitigantTable } from "./weakness-mitigant-map";
export { loadGroupAll, publishGroup } from "./api";
export type { GroupAll, GroupFacts, CapTest, Conduct, Governance, Swot, Mitigants } from "./model";
