/**
 * R15 a (L9): context-aware Noor. Before a question is routed, Noor reads the page it is asked on: the module, the
 * deal, the step and (on a deal's Stress step) the structures of the stress run on screen. "This", "it", "here" are
 * the object on screen. On a deal page a question is answered there, about that deal and its numbers, unless it asks
 * about the book or explicitly for a (book) scenario; then it goes to What-If (or wherever the old routes send it),
 * and the routed answer says why and offers "Answer here instead".
 *
 * The cue table (HERE-BEGIN … HERE-END) equals `backend/agents_v5/brief/here.py` (tests/v5/noor/test_r15_here.py
 * checks it). Pure, except `readPageContext` (it reads the location and the stress run's rows from the page).
 */

export interface PageContext {
  module: string;
  path: string;
  deal_id: string | null;
  step: string | null;
  /** The structures in the stress run on screen (or ticked for it), in order. */
  structures: string[];
  /** True when the stress matrix is on screen (a run was made). */
  stress_on_screen: boolean;
}

export type HereTopic = "stress" | "deal";

// HERE-BEGIN (the cues; equal to here.py)
export const HERE_CUES = {
  /** The question is about the book (What-If's or the Cockpit's), not the deal on screen. */
  book: [
    String.raw`\b(the|our|whole|entire|total) (book|portfolio)\b`,
    String.raw`\bbook[- ](level|wide)\b`,
    String.raw`\bbank[- ]wide\b`,
    String.raw`\bacross (the )?(book|portfolio|bank|sectors|all (deals|borrowers|clients))\b`,
    String.raw`\b(all|every) (our )?(borrowers|obligors|clients|counterparties|sectors)\b`,
    String.raw`\bin what[- ]if\b`,
    String.raw`\b(open|start|run|create|build) (a |an )?(new )?(book )?(what[- ]if|scenario)\b`,
    String.raw`\bwhat[- ]if (the|oil|gdp|rates?|brent|unemployment)\b`,
  ],
  /** Words that point at the object on screen. */
  deictic: [
    String.raw`\b(this|it|its|it's|here|these|those|that one|this one|on screen|on the screen)\b`,
  ],
  /** A question about the stress run. */
  stress: [
    String.raw`\bstress(ed|es|ing)?\b`,
    String.raw`\bscenarios?\b`,
    String.raw`\b(fail|fails|failing|failed|break|breaks|breaking|broke|survive|survives|surviving)\b`,
    String.raw`\b(mild|moderate|severe)\b`,
    String.raw`\bstress[- ]?proof\b`,
    String.raw`\b(shock|shocks|downturn)\b`,
  ],
  /** The deal's own terms and economics (on the Stress step, "this" with these words is the deal, not the run). */
  deal_terms: [
    String.raw`\b(raroc|sva|pricing|priced|price|margin|approval|approve|approver|hurdle|fees?|tenor|amount|collateral|guarantee|limit)\b`,
  ],
  /** Another module's job, asked by name: never answered "here". */
  elsewhere: [
    String.raw`\b(build|create|make|design|set up)\b.{0,40}\b(dashboard|lens)\b`,
  ],
};
// HERE-END

const C = Object.fromEntries(Object.entries(HERE_CUES).map(([k, v]) => [k, v.map((p) => new RegExp(p, "i"))])) as
  Record<keyof typeof HERE_CUES, RegExp[]>;
const any = (k: keyof typeof HERE_CUES, q: string) => C[k].some((re) => re.test(q));

/** The page context from the location alone (what any page gives). */
export function contextFromLocation(pathname: string, search: string): PageContext {
  const path = pathname || "/";
  const sp = new URLSearchParams(search || "");
  const deal = /^\/deal-desk\/(?!thread\/|parameters\b|portfolio-raroc\b|raroc-drift\b|review\b)([^/?#]+)\/?$/.exec(path)?.[1] ?? null;
  const mod = path === "/" ? "cockpit" : path.split("/")[1] || "cockpit";
  return { module: mod, path, deal_id: deal ? decodeURIComponent(deal) : null, step: deal ? (sp.get("step") || null) : null,
           structures: [], stress_on_screen: false };
}

export interface HereRoute { here: true; topic: HereTopic; reason: string }
export interface AwayRoute { here: false; reason: string | null }

/**
 * Whether the question is answered here, in the page context. On a deal page: yes unless it is about the book, asks
 * for a book scenario, or names another module's job. Off a deal page: never (the usual routes apply).
 */
export function routeHere(question: string, ctx: PageContext | null): HereRoute | AwayRoute {
  const q = question.split(/\s+/).filter(Boolean).join(" ");
  if (!q || !ctx?.deal_id) return { here: false, reason: null };
  const deal = ctx.deal_id;
  if (any("elsewhere", q)) return { here: false, reason: `Asks for a dashboard, so Lenses builds it rather than answering on ${deal}.` };
  if (any("book", q) && !q.toLowerCase().includes(deal.toLowerCase())) {
    return { here: false, reason: `Asks about the book, not ${deal}, so the book engines answer it.` };
  }
  const onStress = ctx.step === "stress" || ctx.stress_on_screen;
  const stressy = any("stress", q);
  const topic: HereTopic = stressy || (onStress && any("deictic", q) && !any("deal_terms", q)) ? "stress" : "deal";
  const where = ctx.step ? `${deal}, ${stepLabel(ctx.step)} step` : deal;
  return { here: true, topic,
           reason: topic === "stress" ? `About the stress run on screen (${where}).` : `About the deal on screen (${where}).` };
}

export function stepLabel(step: string): string {
  const L: Record<string, string> = { proposal: "Proposal", review: "Review", analysis: "Analysis", structure: "Structure",
    stress: "Stress", recommendation: "Recommendation", monitoring: "Monitoring" };
  return L[step] ?? step.charAt(0).toUpperCase() + step.slice(1);
}

/** The page context now: the location, plus the stress run's structures read from the page (rows of the matrix, else
 *  the ticked structures). */
export function readPageContext(): PageContext | null {
  if (typeof window === "undefined") return null;
  const ctx = contextFromLocation(window.location.pathname, window.location.search);
  if (!ctx.deal_id) return ctx;
  try {
    const rows = Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="flow-matrix-row-"]'))
      .map((el) => el.dataset.testid!.slice("flow-matrix-row-".length));
    const picks = Array.from(document.querySelectorAll<HTMLInputElement>('input[data-testid^="flow-stress-pick-"]:checked'))
      .map((el) => el.dataset.testid!.slice("flow-stress-pick-".length));
    ctx.structures = rows.length ? rows : picks;
    ctx.stress_on_screen = rows.length > 0;
    if (!ctx.step && document.querySelector('[data-testid="flow-stress"]')) ctx.step = "stress";
  } catch { /* a page without the run: the location is enough */ }
  return ctx;
}
