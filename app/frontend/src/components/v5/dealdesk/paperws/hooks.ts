/**
 * Rounds W/T integration points on the screen (docs/v5/ROUND_WT.md).
 *
 * onInstructionApplied(section, instruction): called after every instruction that changed the document (an edit or a
 * structure change). Round K mounts its "Save this as a rule?" prompt here, in one of two ways:
 *
 *   1. a listener (no UI of its own in the workspace):
 *        import { registerInstructionApplied } from "@/components/v5/dealdesk/paperws/hooks";
 *        registerInstructionApplied((section, instruction, ctx) => { ... });
 *
 *   2. a component the workspace mounts under Noor's reply to the applied instruction (the prompt "Save this as a rule for
 *      your future documents?" with scope and section):
 *        import { registerAfterInstruction } from "@/components/v5/dealdesk/paperws/hooks";
 *        registerAfterInstruction(SaveAsRulePrompt);   // receives AfterInstructionProps
 *
 * The workspace also takes an `onInstructionApplied` prop (ProposalWorkspace) for a caller that embeds it.
 * Registration is module-level (one import line in the round's own index file, or in r12-slots.tsx); a listener that throws is
 * ignored, and a component that throws leaves its place empty.
 */

export interface AppliedSection { key: string; heading: string }
export interface AppliedContext { wsId: string; kind: "proposal" | "request"; proposalId: string; version: number; structure: boolean }
export type InstructionAppliedFn = (section: AppliedSection, instruction: string, ctx: AppliedContext) => void;

export interface AfterInstructionProps {
  section: AppliedSection; instruction: string; wsId: string; kind: "proposal" | "request"; proposalId: string; version: number;
  onDone: () => void;
}

const listeners = new Set<InstructionAppliedFn>();
let after: ((p: AfterInstructionProps) => unknown) | null = null;

export function registerInstructionApplied(fn: InstructionAppliedFn): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export function emitInstructionApplied(section: AppliedSection, instruction: string, ctx: AppliedContext): void {
  for (const fn of listeners) {
    try { fn(section, instruction, ctx); } catch { /* a listener never breaks the document */ }
  }
}

/** Round K's prompt component (React component typed loosely so this file stays free of JSX). */
export function registerAfterInstruction<P extends AfterInstructionProps>(component: (p: P) => unknown): void {
  after = component as (p: AfterInstructionProps) => unknown;
}

export function afterInstructionComponent(): ((p: AfterInstructionProps) => unknown) | null {
  return after;
}
