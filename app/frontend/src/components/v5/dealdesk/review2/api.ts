/**
 * PLAN_R12 Session B client: the R12 review on the Deal Desk service (/api/v1/dealdesk/review2, NEXT_PUBLIC_DEALDESK_API).
 */
import { friendlyError } from "@/lib/v5/errors";

import type { DocItem, DocStatus, Documents, Preflight, Queries, Query, Review2, Signoff } from "./helpers";

const BASE = "/api/v1/dealdesk/review2";

export function origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${origin()}${BASE}${path}`, { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" } });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
const enc = encodeURIComponent;

export const review2Api = {
  review: (id: string, opts: { refresh?: boolean; view?: "review" | "prepare" } = {}) => post<Review2>(`/${enc(id)}`, opts),
  preflight: (id: string) => call<Preflight>(`/${enc(id)}/preflight`),
  signoff: (id: string, role: string, decision: string, note: string) => post<Signoff>(`/${enc(id)}/signoff`, { role, decision, note }),
  documents: (id: string) => call<Documents>(`/${enc(id)}/documents`),
  setDocument: (id: string, itemId: string, status: DocStatus, note?: string, date?: string) =>
    call<DocItem>(`/${enc(id)}/documents/${itemId.split("/").map(enc).join("/")}`, { method: "PATCH", body: JSON.stringify({ status, note, date }) }),
  queryMissing: (id: string) => post<{ raised: number; items: Query[] }>(`/${enc(id)}/documents/queries`, {}),
  queries: (id: string) => call<Queries>(`/queries?deal_id=${enc(id)}`),
  raiseQuery: (dealId: string, question: string, kind: "document" | "finding" | "information", refId?: string | null, to?: string) =>
    post<Query>(`/queries`, { deal_id: dealId, question, kind, ref_id: refId ?? null, to }),
  answerQuery: (qid: string, text: string) => post<Query>(`/queries/${enc(qid)}/answer`, { text }),
  closeQuery: (qid: string, note?: string) => post<Query>(`/queries/${enc(qid)}/close`, { note }),
  reopenQuery: (qid: string) => post<Query>(`/queries/${enc(qid)}/reopen`, {}),
};
