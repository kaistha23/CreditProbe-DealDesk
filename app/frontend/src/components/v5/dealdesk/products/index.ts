/**
 * PLAN_R12 Session P: the product components Session U mounts per product template.
 *
 *   contracting  <ProjectSection proposalId={id} />
 *   escrow       <EscrowSection proposalId={id} />
 *   syndicated   <SyndicationSection proposalId={id} />
 *   sme          <SmeFastTrack onOpenFullFlow={...} />   and the landing card: useSmeFastTrackCount()
 *
 * Session U's slots: `Product` → <ProductSection proposalId /> (picks the sections by the deal's template and data);
 * `SmeFastTrack` → <SmeFastTrack /> (the whole lane).
 *
 * Each deal section renders nothing when the deal has no data for its product (so a template can mount it safely).
 */
export { ProductSection } from "./product-section";
export { ProjectSection, ProjectView } from "./project-section";
export { EscrowSection, EscrowView } from "./escrow-section";
export { SyndicationSection, SyndicationView } from "./syndication-section";
export { SmeFastTrack, useSmeFastTrackCount } from "./sme-fast-track";
export { productsApi } from "./api";
export type { EscrowResult, ProjectResult, SmeCount, SmeDecision, SmeLane, SyndicationResult } from "./format";

/** Which section a product template mounts (template keys as in E's templates.py). */
export const PRODUCT_SECTIONS = {
  contracting: "ProjectSection", project: "ProjectSection", escrow: "EscrowSection", syndicated: "SyndicationSection", sme: "SmeFastTrack",
} as const;
