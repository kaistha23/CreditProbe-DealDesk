/**
 * R13 §I: intent descriptors so Noor's Ask box can call the CCO intelligence engines (PLAN_R13 §I). Each entry names
 * the API it calls, the parameters it needs, the phrasings it answers and the panel that shows the full result.
 * Self-contained (no path aliases) so the matcher runs under `node --test`. Sessions add their own arrays below and
 * concatenate them into INTEL_INTENTS.
 */

export type IntelParam = "deal_id";

export type IntelIntent = {
  id: string;
  module: "dealdesk" | "book" | "ews" | "b360" | "whatif" | "lenses" | "admin";
  label: string;
  /** Method and path under the API origin; {deal_id} is filled from the context or the question. */
  method: "GET" | "POST";
  path: string;
  needs: IntelParam[];
  /** Lower-case regular expressions; any match is a hit. */
  patterns: string[];
  examples: string[];
  /** The field of the response that is the one-line answer. */
  answerField: string;
  /** The More-menu panel key that shows the full result. */
  panel: string;
};

// ---------------------------------------------------------------- R13 IA: approval intelligence
export const INTEL_INTENTS_IA: IntelIntent[] = [
  {
    id: "dealdesk.approval.challenger", module: "dealdesk", label: "Committee challenger", method: "GET",
    path: "/api/v1/dealdesk/intel/approval/{deal_id}/challenger", needs: ["deal_id"],
    patterns: ["what (will|would) (the )?committee ask", "committee (questions|challenge)", "questions? .*(proposal )?avoid", "prepare .*for committee",
      "challenge (this|the) (deal|proposal)"],
    examples: ["What will committee ask about R12-TWA?", "Which questions does the proposal avoid?"],
    answerField: "headline", panel: "committee-questions",
  },
  {
    id: "dealdesk.approval.reverse", module: "dealdesk", label: "Reverse solver", method: "GET",
    path: "/api/v1/dealdesk/intel/approval/{deal_id}/reverse", needs: ["deal_id"],
    patterns: ["smallest change", "make (it|this|the deal) approvable", "counter[- ]?offer", "what would it take to approve", "how (do|can) (we|i) get .*approved",
      "reverse solve"],
    examples: ["What is the smallest change that gets DD-05 approved?", "Give me a counter-offer for this deal."],
    answerField: "headline", panel: "make-approvable",
  },
  {
    id: "dealdesk.approval.security", module: "dealdesk", label: "Security optimiser", method: "GET",
    path: "/api/v1/dealdesk/intel/approval/{deal_id}/security", needs: ["deal_id"],
    patterns: ["cheapest (security|collateral)", "(which|what) (collateral|security) (actually )?(helps|is worth)", "security (package|value|optimi[sz])",
      "crm eligib", "collateral .*(rwa|capital|lgd)"],
    examples: ["Which collateral actually helps on R12-TWB?", "What is the cheapest security package that clears the hurdle?"],
    answerField: "headline", panel: "security-value",
  },
  {
    id: "dealdesk.approval.consistency", module: "dealdesk", label: "Decision consistency", method: "GET",
    path: "/api/v1/dealdesk/intel/approval/{deal_id}/consistency", needs: ["deal_id"],
    patterns: ["decided differently", "(decision|approval)s? consisten", "similar deals", "inconsisten", "same deal .*different decision"],
    examples: ["Were similar deals decided differently?", "Are our approvals consistent?"],
    answerField: "headline", panel: "decision-consistency",
  },
];

export const INTEL_INTENTS: IntelIntent[] = [...INTEL_INTENTS_IA];

const DEAL_ID = /\b(DD-\d{2}|PL-\d{2}|R12-[A-Z0-9]+|PRP-[AB]-[A-Z]{3})\b/i;

/** The deal id named in a question, if any ("r12-twa" -> "R12-TWA"). */
export function dealIdIn(question: string): string | null {
  const m = question.match(DEAL_ID);
  return m ? m[1].toUpperCase() : null;
}

/** The first intent whose pattern matches the question, with its call filled in; null when none matches or a parameter is missing. */
export function matchIntent(question: string, context: { deal_id?: string | null } = {}, intents: IntelIntent[] = INTEL_INTENTS):
  { intent: IntelIntent; url: string } | null {
  const q = question.toLowerCase();
  for (const it of intents) {
    if (!it.patterns.some((p) => new RegExp(p).test(q))) continue;
    const deal = dealIdIn(question) ?? context.deal_id ?? null;
    if (it.needs.includes("deal_id") && !deal) {
      if (it.id === "dealdesk.approval.consistency" && /\b(our|book|all)\b/.test(q)) return { intent: it, url: it.path.replace("{deal_id}", "book") };
      return null;
    }
    return { intent: it, url: it.path.replace("{deal_id}", encodeURIComponent(deal ?? "")) };
  }
  return null;
}
