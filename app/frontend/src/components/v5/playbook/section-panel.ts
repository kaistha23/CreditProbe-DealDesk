/**
 * R10 C2: the per-section "Ask AI" side panel. Pure helpers, kept apart from the React code so they run under
 * `node --test` without a bundler.
 */
import type { Message } from "../../../lib/v5/playbook.ts";

/** The merge recorded on a message: from this session, or from the stored thread (a `merged` action). */
export function mergedOf(m: Message, merged: Record<string, { version: number; where?: string }>): { version: number; where?: string } | null {
  if (merged[m.id]) return merged[m.id];
  const a = (m.actions ?? []).find((x) => x.kind === "merged") as { version?: number; where?: string } | undefined;
  return a?.version ? { version: a.version, where: a.where } : null;
}

/** Whether an assistant answer can still be inserted into its section ("Insert into this section"). */
export function canInsert(m: Message, merged: Record<string, { version: number; where?: string }>): boolean {
  return m.role === "assistant" && !merged[m.id] && (m.actions ?? []).some((a) => a.kind === "can_apply");
}

/** The chips under the panel's input: the last answer's follow-ups, else the section's own starters (at most 4). */
export function panelChips(messages: Message[], starters: string[] | undefined): string[] {
  const last = [...messages].reverse().find((m) => m.role === "assistant");
  return ((last?.suggestions?.length ? last.suggestions : starters) ?? []).slice(0, 4);
}
