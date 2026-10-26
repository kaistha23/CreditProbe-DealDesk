/**
 * The one thread rule, system-wide (R14 n, K16; like a chat app):
 *
 *   every NEW question submitted from a landing, an Ask box, the Cockpit Ask or the Noor panel's start opens a NEW
 *   thread (its own id and URL `/…/thread/<id>`, a title from the question, top of Recent work);
 *   an old thread is opened only from Recent work (or the panel's history);
 *   only a question typed INSIDE an open thread continues it.
 *
 * Pure (node --test covers it: thread-rule.test.ts). Every module's ask handler asks `threadFor` what to do.
 */

export type AskOrigin =
  | "landing"   // a module landing's ask box or starter chip
  | "ask-bar"   // a one-line ask bar over a module table (Early Warning, Borrower 360)
  | "cockpit"   // the Cockpit Ask tab
  | "noor"      // the Noor panel opened fresh (an empty thread)
  | "thread";   // the composer inside an open thread

export type ThreadDecision = { kind: "new" } | { kind: "continue"; threadId: string };

/** What a submitted question does: a new thread, unless it was typed inside an open thread. */
export function threadFor(origin: AskOrigin, openThreadId?: string | null): ThreadDecision {
  if (origin === "thread" && openThreadId) return { kind: "continue", threadId: openThreadId };
  return { kind: "new" };
}

/** R16 m (M6): true for every input that is not a thread's own composer: a landing box, a starter chip, a library
 *  card, an ask bar, the Cockpit Ask, Noor. Such input always opens a NEW thread. */
export function isLandingInput(origin: AskOrigin): boolean {
  return origin !== "thread";
}

/** The thread id to send with a question: the open thread's id only for input typed inside it; otherwise null (the
 *  service creates a new thread). Every module's ask path goes through this (or `startFresh`). */
export function threadIdFor(origin: AskOrigin, openThreadId?: string | null): string | null {
  const d = threadFor(origin, openThreadId);
  return d.kind === "continue" ? d.threadId : null;
}

/**
 * R16 m (M6): the body of a "create thread" request from a landing (or any non-thread input): never carries a thread
 * id, a run id or a "continue" flag, so the service can only create. `module` names the caller (kept for tests and
 * logs, never sent).
 */
export function startFresh<T extends Record<string, unknown>>(module: string, body: T): Omit<T, "thread_id" | "threadId" | "continue" | "run_id"> {
  void module;
  const { thread_id: _a, threadId: _b, continue: _c, run_id: _d, ...rest } = body as Record<string, unknown>;
  void _a; void _b; void _c; void _d;
  return rest as Omit<T, "thread_id" | "threadId" | "continue" | "run_id">;
}

/** A React key for a thread view, so opening another thread never reuses the previous thread's state (its turns, its
 *  "asked once" guard, its live run). */
export function threadViewKey(module: string, threadId: string): string {
  return `${module}:${threadId}`;
}

/** A thread title from its first question: one line, at most `max` characters, cut at a word. */
export function titleFrom(question: string, max = 80): string {
  const t = String(question ?? "").replace(/\s+/g, " ").trim();
  if (!t) return "New thread";
  if (t.length <= max) return t;
  const cut = t.slice(0, max - 1);
  const at = cut.lastIndexOf(" ");
  return `${(at > 20 ? cut.slice(0, at) : cut).replace(/[\s,;:.-]+$/, "")}…`;
}

/** Recent work order: the newest thread first. */
export function recentFirst<T extends { updated?: number | string | null; created?: number | string | null }>(rows: T[]): T[] {
  const t = (x: T) => {
    const v = x.updated ?? x.created ?? 0;
    return typeof v === "number" ? v : Date.parse(String(v)) / 1000 || 0;
  };
  return [...rows].sort((a, b) => t(b) - t(a));
}

/** Deal Desk's thread URL (K16: `thread=desk` is gone; each question has its own thread). */
export function deskThreadHref(threadId: string, question?: string): string {
  const base = `/deal-desk/thread/${encodeURIComponent(threadId)}`;
  return question ? `${base}?q=${encodeURIComponent(question)}` : base;
}
