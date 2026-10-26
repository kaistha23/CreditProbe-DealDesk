/**
 * The Ask tab's starter prompts (PLAN_R13 Session H): five or six, one per engine family (R13 M: plus "Who should I call today?", §I), on the calendar of the book they
 * are offered in ({period} is filled from the `/domains` payload, as the Cockpit's own chips are). Pure, so
 * `node --test` covers it (starters.test.ts).
 */

export type Book = "corporate" | "retail";

export const STARTERS: Record<Book, readonly string[]> = {
  corporate: [
    "Decompose the ECL movement this {period}",
    "Which borrowers moved into Stage 2 this {period}?",
    "Where are early-warning signals building in the corporate book?",
    "What if Brent falls 30% over the next year?",
    "Which proposals are waiting for a credit decision?",
    "Who should I call today?",
  ],
  retail: [
    "Decompose the retail ECL movement this {period}",
    "Which products saw the largest Stage 2 increase this {period}?",
    "Where is delinquency building?",
    "What if unemployment rises by 2 points?",
    "Build a dashboard of retail delinquency by product",
  ],
};

export function startersFor(book: Book, periodNoun: string): string[] {
  const noun = periodNoun.trim() || "period";
  return STARTERS[book].map((s) => s.replaceAll("{period}", noun));
}

export const ASK_PLACEHOLDER = "Ask me anything, from ECL decomposition to early warning…";

/** Deal Desk edition: the Ask tab's starters and placeholder are Deal Desk's own (the chips its home offers, plus
 *  the CCO intelligence intents that answer in place). */
export const DEALDESK_STARTERS: readonly string[] = [
  "Which proposals breach a hard limit?",
  "How much real-estate headroom is left this quarter?",
  "How much sector headroom is left?",
  "Which proposals are waiting for a credit decision?",
  "Who should I call today?",
];
export const DEALDESK_ASK_PLACEHOLDER = "Ask Deal Desk, e.g. “Why does DD-03 fail?”";

export type HomeTab = "brief" | "ask";

/** The tab in the address: `?tab=ask`, or a question arriving in `?q=`, opens Ask; everything else opens Brief. */
export function tabFrom(params: { get(name: string): string | null }): HomeTab {
  const t = params.get("tab");
  if (t === "ask") return "ask";
  if (t === "brief") return "brief";
  return params.get("q") ? "ask" : "brief";
}
