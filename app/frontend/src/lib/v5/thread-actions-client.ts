/**
 * R16 t (M7): the thread-actions API on the Core service (port 8505, backend/thread_actions/api.py), with the
 * session cookie. Errors come back as plain sentences.
 */
import type { ActionDoc, MemoKind, MemoResult } from "./thread-actions";

export function coreOrigin(): string {
  return (process.env.NEXT_PUBLIC_WORKSPACE_API ?? "http://127.0.0.1:8505").replace(/\/$/, "");
}

const BASE = "/api/v1/thread-actions";

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${coreOrigin()}${path}`, { credentials: "include", cache: "no-store", ...init });
  } catch {
    throw new Error("CreditProbe could not reach the document service. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null) as { detail?: unknown } | null;
  if (!r.ok) {
    if (r.status === 401) throw new Error("Sign in to use Share, Trace and Word.");
    const d = body?.detail;
    throw new Error(typeof d === "string" ? d : "The document could not be written. Please try again.");
  }
  return body as T;
}

const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export interface TraceResult {
  plain_words: string[];
  sources: { kind: string; label: string; relation?: string; domain?: string; sql?: string; keys?: Record<string, string>; period?: string; rows?: number; href?: string }[];
  queries: { label: string; sql: string; relations: string[]; rows?: number | null }[];
  relations: { relation: string; domain: string; label: string; registered: boolean; via: string[]; rows: number }[];
  rows: { relation: string; keys: Record<string, string>; period: string; label: string }[];
  counts: { sources: number; queries: number; relations: number; rows: number; tables: number; table_rows: number; unregistered: number };
}

export const threadActions = {
  memo: (doc: ActionDoc, opts: { kind?: MemoKind; scope?: "answer" | "thread"; to?: string; answer_index?: number; trigger?: "word_button" | "memo_intent"; request_text?: string } = {}) =>
    post<MemoResult>(`${BASE}/memo`, { doc, ...opts }),
  trace: (doc: ActionDoc, turn_index?: number) => post<TraceResult>(`${BASE}/trace`, { doc, turn_index }),
  action: (module: string, thread_id: string, action: "share" | "report", target = "", answer_id = "") =>
    post<{ action_id: string }>(`${BASE}/actions`, { module, thread_id, action, target, answer_id }).catch(() => null),
  href: (m: MemoResult) => `${coreOrigin()}${m.href}`,
  /** Fetch the file with the session cookie and save it under its own name. */
  async download(m: MemoResult): Promise<void> {
    const r = await fetch(`${coreOrigin()}${m.href}`, { credentials: "include" });
    if (!r.ok) throw new Error("The Word file could not be downloaded.");
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = m.file_name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
  },
  async blob(m: MemoResult): Promise<Blob> {
    const r = await fetch(`${coreOrigin()}${m.href}`, { credentials: "include" });
    if (!r.ok) throw new Error("The Word file could not be read.");
    return r.blob();
  },
};
