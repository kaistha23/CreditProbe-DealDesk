/**
 * R16 t (M7): a memo asked for together with its question from a landing or Noor ("prepare a memo on which
 * proposals breach a hard limit"). The landing asks only the question part in the new thread and leaves the request
 * here; the thread (useThreadActions / CockpitMemo) writes the Word document once that answer is on screen.
 * sessionStorage: per tab, gone when the tab closes; every access guarded.
 */
import { type ModuleKey, memoIntent } from "./thread-actions.ts";

const key = (module: ModuleKey, threadId: string) => `ta.pending.${module}.${threadId}`;

export function rememberPendingMemo(module: ModuleKey, threadId: string, request: string): void {
  try { window.sessionStorage.setItem(key(module, threadId), request.slice(0, 600)); } catch { /* private window */ }
}

/** The pending request for this thread (read once: it is removed). */
export function takePendingMemo(module: ModuleKey, threadId: string): string | null {
  try {
    const k = key(module, threadId);
    const v = window.sessionStorage.getItem(k);
    if (v !== null) window.sessionStorage.removeItem(k);
    return v;
  } catch { return null; }
}

/** What a landing asks for a typed text: the question part of a memo request, or the text as it is. */
export function landingQuestion(text: string): { ask: string; memo: string | null } {
  const mi = memoIntent(text);
  return mi?.question ? { ask: mi.question, memo: text } : { ask: text, memo: null };
}
