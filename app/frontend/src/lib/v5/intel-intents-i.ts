/**
 * R14 i: Noor intents for the Deal Desk intelligence D6-D13 (PLAN_R14 i). Each names the API, the deal it needs, the
 * phrasings it answers and the panel key (`?intel=<panel>` on the deal page; More menu, "Intelligence").
 * Self-contained (no path aliases) so the matcher runs under `node --test`; registered in `intel-intents.ts`.
 */

export type IntentI = {
  id: string;
  code: "D6" | "D7" | "D8" | "D9" | "D10" | "D11" | "D12" | "D13";
  label: string;
  path: string;
  panel: string;
  patterns: RegExp[];
  examples: string[];
  answerField: "headline";
};

const P = "/api/v1/dealdesk/intel2/{deal_id}";

export const INTEL_INTENTS_I: IntentI[] = [
  {
    id: "dealdesk.intel2.rehearsal", code: "D13", label: "Committee questions", path: `${P}/rehearsal`, panel: "challenger",
    patterns: [/\brehears\w*\b/i, /\b(how (do|should|would) (we|i) answer|suggested answers?)\b.{0,40}\bcommittee\b/i, /\bcommittee\b.{0,30}\b(answers?|rehears\w*)\b/i],
    examples: ["Rehearse the committee for DD-06.", "What will committee ask and how do we answer?"], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.frontier", code: "D6", label: "Negotiation frontier", path: `${P}/frontier`, panel: "frontier",
    patterns: [/\bnegotiat\w*\b/i, /\bgive[- ]and[- ]get\b/i, /\bwhat is .{0,30}(cash margin|tenor|a year of tenor).{0,20}\bworth\b/i,
      /\bworth in (bps|basis points)\b/i, /\bcounter[- ]offers? .{0,30}(client|accept)/i, /\bcounter[- ]offers? the client\b/i],
    examples: ["What is 10% cash margin worth in bps on DD-06?", "Give me three counter-offers the client will accept."], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.premortem", code: "D7", label: "Default pre-mortem", path: `${P}/premortem`, panel: "premortem",
    patterns: [/\bpre[- ]?mortem\b/i, /\bhow (could|would|might|can) (this|the|it|\w+-\d+) .{0,20}(go bad|default|fail)\b/i,
      /\b(ways?|paths?) (it|this deal|the deal) (goes|could go) bad\b/i, /\bwhat would warn (us )?first\b/i, /\bdefault paths?\b/i],
    examples: ["How could DD-06 go bad?", "Run a default pre-mortem on R12-TWA."], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.precedents", code: "D8", label: "Precedent explorer", path: `${P}/precedents`, panel: "precedents",
    patterns: [/\bprecedents?\b/i, /\bclosest (past )?deals\b/i, /\bpast deals like\b/i, /\bdeals like (this|it)\b.{0,40}\b(decid|perform)\w*/i],
    examples: ["Show me the closest past deals to DD-06.", "What did we decide on deals like this and how did they perform?"], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.pricing", code: "D9", label: "Pricing benchmark", path: `${P}/pricing`, panel: "pricing",
    patterns: [/\bpricing benchmark\b/i, /\b(margin|pricing|price)\b.{0,30}\b(in line with|against|versus|vs\.?|compared? (to|with)) (the )?(book|market|similar|peers)\b/i,
      /\bpercentile\b.{0,20}\b(margin|pricing|price)\b/i, /\b(margin|pricing)\b.{0,20}\bpercentile\b/i, /\bis (the|this) (margin|pricing|price) (too )?(low|high|right|fair)\b/i],
    examples: ["Is this margin in line with the book?", "Where does R12-TWA's pricing sit against similar deals?"], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.revenue", code: "D10", label: "Revenue truth check", path: `${P}/revenue`, panel: "revenue-check",
    patterns: [/\brevenue truth\b/i, /\brevenues? (is |are )?(real|genuine|true|backed by cash)\b/i, /\b(turnover|inflows?|cash)\b.{0,30}\b(support|back|match)\w*\b.{0,20}\brevenue\b/i,
      /\brevenue\b.{0,30}\b(against|vs\.?|versus) (account )?(turnover|inflows?|cash|vat)\b/i, /\bopen banking\b/i],
    examples: ["Is R12-TWA's reported revenue real?", "Does account turnover support the revenue?"], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.renewal_diff", code: "D11", label: "Renewal diff", path: `${P}/renewal-diff`, panel: "renewal-diff",
    patterns: [/\brenewal diff\b/i, /\bwhat (has )?changed since (the )?last (approval|renewal|committee)\b/i, /\bsince (the )?last (approval|renewal)\b/i],
    examples: ["What changed since the last approval of R12-TWA?", "Show the renewal diff for DD-06."], answerField: "headline",
  },
  {
    id: "dealdesk.intel2.contagion", code: "D12", label: "Group contagion on the deal", path: `${P}/contagion`, panel: "group-contagion",
    patterns: [/\bconnected part(y|ies)\b.{0,40}\b(stage 3|litigation|arrears|classified|default|fail)/i, /\bgroup contagion\b/i,
      /\b(what|how) .{0,20}(this|the) deal .{0,20}if .{0,30}(group|connected|related) .{0,20}fail/i],
    examples: ["Are any connected parties of DD-06 in Stage 3 or litigation?", "What happens to this deal if the group fails?"], answerField: "headline",
  },
];

const DEAL_ID = /\b(DD-\d{2}|PL-\d{2}|R12-[A-Z0-9]+|PRP-[AB]-[A-Z]{3}|TWIN-[AB])\b/i;

export function dealIdInI(question: string): string | null {
  const m = question.match(DEAL_ID);
  return m ? m[1].toUpperCase() : null;
}

/** The first D6-D13 intent whose pattern matches, with its call filled in when a deal is known. */
export function matchIntentI(question: string, ctx: { dealId?: string | null } = {}): { intent: IntentI; deal: string | null; url: string | null } | null {
  for (const it of INTEL_INTENTS_I) {
    if (!it.patterns.some((re) => re.test(question))) continue;
    const deal = dealIdInI(question) ?? ctx.dealId ?? null;
    return { intent: it, deal, url: deal ? it.path.replace("{deal_id}", encodeURIComponent(deal)) : null };
  }
  return null;
}
