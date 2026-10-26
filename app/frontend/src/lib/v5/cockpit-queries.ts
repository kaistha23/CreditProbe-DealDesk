/**
 * R10 Q1: auditor and regulator queries answered from the Cockpit chat.
 *
 * The standalone /queries screen is gone (Session S redirects it to the Cockpit). The Cockpit's frozen Ask box hands a
 * question here first through the registered exception FX-R10-Q1 (docs/v5/FROZEN_EXCEPTIONS.md): when it reads as an
 * auditor or regulator query, the Queries service (backend.queries_v5.api, port 8516) answers it on the books and the
 * Cockpit renders the answer in place; anything else goes to the Cockpit's own agent exactly as before.
 *
 * `isQueryQuestion` mirrors `QUERY_CUES` and the letter reference in backend/queries_v5/api.py, so an ordinary
 * portfolio question never waits on the Queries service. The service has the last word (422 = not a query).
 */
import { qUrl, type QueryItem } from "./queries.ts";
import { friendlyError } from "./errors.ts";

export const QUERY_CUES = [
  "auditor", "audit ", "internal audit", "cbuae", "central bank", "regulator", "regulatory query",
  "letter", "query", "queries", "response pack", "draft answer", "draft a response", "respond to", "reply to",
] as const;

const CASE_REF = /\b(?:letter|query|case)\s*(?:q)?([1-5])\b|\bq([1-5])\b/i;

/** Does this Cockpit question read as an auditor or regulator query, or name a prepared letter (Q1–Q5)? */
export function isQueryQuestion(question: string): boolean {
  const t = ` ${question.toLowerCase()} `;
  if (!question.trim()) return false;
  return CASE_REF.test(t) || QUERY_CUES.some((c) => t.includes(c));
}

/** The five prepared letters, as questions the Cockpit can be asked. */
export const PREPARED_QUESTIONS: { case: string; label: string; question: string }[] = [
  { case: "Q1", label: "Auditor · 30+ DPD in Stage 1", question: "Answer the auditor's question on 30+ DPD loans still in Stage 1" },
  { case: "Q2", label: "CBUAE · Stage 3 floors", question: "Answer the CBUAE letter on the top 20 Stage 3 exposures against the minimum floors" },
  { case: "Q3", label: "Auditor · Construction ECL", question: "Answer the auditor's query on the construction Stage 2 ECL movement" },
  { case: "Q4", label: "CBUAE · 1.5% of CRWA", question: "Answer the CBUAE query on Stage 1 + 2 provisions against 1.5% of CRWA" },
  { case: "Q5", label: "Internal Audit · Restructured", question: "Answer the internal audit letter on facilities restructured in the last 12 months" },
];

export interface QueryAsk { question: string; case: string; focus: number; item: QueryItem }

/** Thrown when the service says the question is not a query: the Cockpit asks it instead. */
export class NotAQuery extends Error {}

export async function askQuery(question: string, itemId?: string): Promise<QueryAsk> {
  let response: Response;
  try {
    response = await fetch(qUrl("/ask"), {
      method: "POST", credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, item_id: itemId ?? null }),
    });
  } catch {
    throw new Error("Queries is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (response.status === 422 && /Not an auditor or regulator query/.test(String(body?.detail ?? ""))) throw new NotAQuery();
  if (!response.ok) throw new Error(friendlyError("Queries", response.status, body));
  return body as QueryAsk;
}

/** The answers in reading order: the one that answers the question first, then the rest of the letter. */
export function answerOrder<T extends { n: number }>(answers: T[], focus: number): T[] {
  const lead = answers.find((a) => a.n === focus);
  return lead ? [lead, ...answers.filter((a) => a.n !== focus)] : answers;
}

/** First sentence of a draft answer: the headline the Cockpit leads with (keeps **bold** key figures intact). */
export function headline(draft: string): string {
  const text = draft.trim();
  const m = text.match(/^([\s\S]+?[.!?])(\s|$)/);
  return (m ? m[1] : text).trim();
}
