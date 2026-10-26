/**
 * R13 Session Q exports (PLAN_R13 §Q): the compact Financial quality panel.
 *
 *   <FinQualityPanel proposalId="R12-TWA" />            deal page, More menu (slot "FinQuality" in r12-slots.tsx)
 *   <FinQualityPanel facilityId="CF000011" compact />   Book renewal row (the facility detail)
 */
export { FinQualityPanel, FinQualityView, loadFinQuality, publishFinQuality } from "./panel";
export { countsLine, finQualityUrl, gradeTone, ordered, sevTone, statusLabel } from "./model";
export type { FinQuality, FamilySummary, GradeInfo, Signal, Severity, Grade } from "./model";
