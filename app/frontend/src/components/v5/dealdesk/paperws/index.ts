/** Rounds W and T: the living request and proposal (paper workspace) and its provenance. */
export { ProposalWorkspace } from "./workspace";
export { ProvenanceView } from "./provenance-view";
export { DealPapers, OpenPaperButton, PaperTraceList, paperRowTitle, useOpenPaper, usePaperRows } from "./open";
export { registerAfterInstruction, registerInstructionApplied, type AfterInstructionProps, type InstructionAppliedFn } from "./hooks";
export { pwHref, pwUrls, type PaperKind, type PwState, type PwWorkspace } from "./model";
