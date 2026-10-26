/**
 * Where a typed question goes (PLAN_R13 Session H, R12_FEEDBACK J2 (b)): Noor answers any question by routing it to
 * an engine that already exists, never with "I could not tie that to a line in today's brief".
 *
 *   brief     Why? / What should we do? / Who drives it? / Show me on a line of today's brief
 *   whatif    a scenario or stress question (What-If opens a thread on it)
 *   lenses    a request to build a dashboard or lens
 *   dealdesk  a deal, proposal or pipeline question (Deal Desk's desk thread)
 *   cockpit   everything else (the Cockpit engine, with its Trace and its auditor-query hand-off)
 *
 * The cue table is the same as `backend/agents_v5/brief/route.py` ROUTES (kept equal by tests/v5/noor/test_route.py);
 * pure, so `node --test` covers it (noor-route.test.ts).
 */

import { type BriefItem, intentOf } from "./noor-model.ts";

export type Engine = "brief" | "cockpit" | "whatif" | "lenses" | "dealdesk";

// ROUTES-BEGIN (the cue patterns; order is precedence; equal to route.py)
export const ROUTES: [Exclude<Engine, "brief" | "cockpit">, string[]][] = [
  ["lenses", [
    String.raw`\b(build|create|make|design|set up)\b.{0,40}\b(dashboard|lens)\b`,
    String.raw`\blens(es)? (for|on|of)\b`,
    String.raw`\bdashboard (for|on|of)\b`,
  ]],
  ["whatif", [
    String.raw`\bwhat[- ]if\b`,
    String.raw`\bstress(ed|ing)?\b`,
    String.raw`\bscenarios?\b`,
    String.raw`\bshock(s|ed)?\b`,
    String.raw`\b(oil|brent) (price )?(falls?|drops?|declines?|crash(es)?)\b`,
    String.raw`\b(gdp|unemployment|rates?) (falls?|rises?|drops?|contracts?|shocks?)\b`,
    String.raw`\b(mild|moderate|severe) (downturn|recession|scenario)\b`,
    String.raw`\bsensitivity\b`,
  ]],
  ["dealdesk", [
    String.raw`\bdeal desk\b`,
    String.raw`\b(proposal|proposals|credit application|term sheet)\b`,
    String.raw`\b(pipeline|new deals?|this deal|the deal)\b`,
    String.raw`\braroc\b.{0,30}\b(deal|proposal|pricing|price)\b`,
    String.raw`\b(price|pricing) (this|the|a) (deal|facility|loan)\b`,
    String.raw`\bcommittee paper\b`,
  ]],
];
// ROUTES-END

const COMPILED = ROUTES.map(([e, pats]) => [e, pats.map((p) => new RegExp(p, "i"))] as const);

export const ENGINE_LABEL: Record<Engine, string> = {
  brief: "today's brief", cockpit: "the Cockpit", whatif: "What-If", lenses: "Lenses", dealdesk: "Deal Desk",
};

export const ENGINE_VERB: Record<Engine, string> = {
  brief: "Answering from today's brief", cockpit: "Answering in the Cockpit", whatif: "Running it in What-If",
  lenses: "Building it in Lenses", dealdesk: "Asking Deal Desk",
};

export function engineFor(text: string): Exclude<Engine, "brief"> {
  for (const [engine, pats] of COMPILED) if (pats.some((p) => p.test(text))) return engine;
  return "cockpit";
}

/** Words every book question shares with every line; they do not tie a question to a line. Equal to route.py STOP. */
export const STOP = new Set(["stage", "stages", "sector", "sectors", "limit", "limits", "book", "books", "today",
  "borrower", "borrowers", "coverage", "quarter", "month", "what", "which", "about", "with", "this", "that", "there",
  "their", "from", "have", "does", "into", "more", "much", "many", "show", "open", "please", "brief", "should", "would",
  "could", "drives", "driving", "explain"]);

const words = (s: string) => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/)
  .filter((w) => w.length > 3 && !STOP.has(w)));

/** The brief line sharing most words with the question, how many it shares, and whether the line's name is among
 *  them (a sector, a borrower: the strongest tie). */
export function matchLine(text: string, items: BriefItem[]): { item: BriefItem | null; shared: number; named: boolean } {
  const q = words(text);
  let item: BriefItem | null = null;
  let shared = 0;
  let named = false;
  for (const it of items) {
    const w = words(`${it.title} ${String(it.entity?.name ?? "")} ${it.source_label}`);
    const n = words(String(it.entity?.name ?? ""));
    let s = 0;
    let hasName = false;
    q.forEach((x) => { if (w.has(x)) s += 1; if (n.has(x)) hasName = true; });
    if (s > shared || (s === shared && s > 0 && hasName && !named)) { item = it; shared = s; named = hasName; }
  }
  return { item, shared, named };
}

export interface Routed {
  engine: Engine | "none";
  intent: ReturnType<typeof intentOf>;
  item: BriefItem | null;
  question: string;
}

const BOOK_WORDS = /\b(ecl|stage|pd|lgd|ead|provision|exposure)\b/i;

/** Where a question is answered. Nothing is refused: only an empty question is not routed. */
export function routeQuestion(text: string, items: BriefItem[] = []): Routed {
  const q = text.split(/\s+/).filter(Boolean).join(" ");
  if (!q) return { engine: "none", intent: "unknown", item: null, question: "" };
  const intent = intentOf(q);
  const { item, shared, named } = matchLine(q, items);
  const engine = engineFor(q);
  // A line answers only when the question is plainly about it: an action word with the line's name or two of its
  // words, or three of its words without any book measure (ECL, stage, PD...), which the Cockpit answers better.
  const action = ["why", "options", "drivers", "show"].includes(intent);
  if (item && engine === "cockpit"
      && ((action && (named || shared >= 2)) || (shared >= 3 && !BOOK_WORDS.test(q)))) {
    return { engine: "brief", intent: intent === "unknown" ? "why" : intent, item, question: q };
  }
  if (intent === "brief" && !BOOK_WORDS.test(q)) return { engine: "brief", intent, item: null, question: q };
  return { engine, intent, item: null, question: q };
}
