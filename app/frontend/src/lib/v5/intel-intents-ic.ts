/**
 * PLAN_R13 §I: intent descriptors for the CCO intelligence pack, so Noor's Ask box can call an engine ("what if oil
 * falls 30% this morning?", "if Al Ahsa Energy fails, who else is hit?") and open its compact panel.
 *
 * Pure data and pure functions (no React, no fetch): a descriptor says which questions it answers (patterns and
 * examples), which request answers them (service, method, path, body), which panel shows the result, and where the
 * deterministic answer sits in the response (`answer`: the engine's own writer; the model only polishes, N3).
 *
 * Session IC owns IC_INTENTS. The other §I sessions add their own arrays; M concatenates them into INTEL_INTENTS
 * (order matters: the first matching intent wins, so specific intents come before broad ones).
 */

export type IntelPack = "IA" | "IB" | "IC" | "ID" | "IE";
export type IntelService = "b360" | "whatif" | "dealdesk" | "cockpit";

export interface IntentContext {
  /** The borrower on screen (Borrower 360 customer page), used when the question names none. */
  borrowerId?: string;
  period?: string;
}

export interface IntentRequest {
  service: IntelService;
  method: "GET" | "POST";
  /** Path under the service origin, query string included. */
  path: string;
  body?: Record<string, unknown>;
}

export interface IntelIntent {
  id: string;
  pack: IntelPack;
  /** docs/v5/R14_BACKLOG_CCO_IDEAS.md item number. */
  backlog: number;
  title: string;
  /** Tools menus the panel is listed in. */
  modules: string[];
  /** Exported panel component (components/v5/intel/network/index.ts). */
  panel: string;
  examples: string[];
  patterns: RegExp[];
  /** Where the deterministic answer is in the response. */
  answer: { headline: string; lines: string };
  request: (question: string, ctx: IntentContext) => IntentRequest | null;
}

export interface IntentMatch { intent: IntelIntent; request: IntentRequest }

const NET = "/api/v1/intel/network";
const BORROWER_ID = /\bCB\d{5}\b/i;
const FAIL_WORDS = "fail(?:s|ed|ing)?|defaults?|default(?:ed|ing)|goes\\s+under|went\\s+under|collapses?|goes\\s+bust|bankrupt\\w*|is\\s+insolvent";

function qs(params: Record<string, string | undefined>): string {
  const parts = Object.entries(params).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

function severityOf(q: string): string | undefined {
  const m = /\b(mild|moderate|severe|extreme)\b/i.exec(q);
  if (!m) return undefined;
  const w = m[1].toLowerCase();
  return w === "extreme" ? "severe" : w;
}

function clean(name: string): string {
  return name.replace(/^(the|a|an)\s+/i, "").replace(/[?.!,;:]+$/, "").trim();
}

/** The borrower a contagion question names: an id, a name before the failure verb, or the one on screen. */
export function failedBorrower(q: string, ctx: IntentContext): string | null {
  const id = BORROWER_ID.exec(q);
  if (id) return id[0].toUpperCase();
  const m = new RegExp(`\\b(?:if|when|should)\\s+(.+?)\\s+(?:${FAIL_WORDS})\\b`, "i").exec(q);
  if (m) {
    const n = clean(m[1]);
    if (n && !/^(this|that|it|they|the borrower|this borrower|the customer|this name)$/i.test(n)) return n;
  }
  return ctx.borrowerId ?? null;
}

/** The employer an employer-exposure question names, or null for the ranking. */
export function employerOf(q: string, ctx: IntentContext): string | null {
  const id = BORROWER_ID.exec(q);
  if (id) return id[0].toUpperCase();
  const m = /\b(?:employer exposure (?:for|of|to)|exposure to|exposed to|employer)\s+(.+?)(?:\s+(?:through|via|held|across|by way of)\b|[?.!]|$)/i.exec(q);
  if (m) {
    const n = clean(m[1]);
    if (n && !/^(exposure|a project employer|project employers?|employers?|exposure|(?:this|the) (?:borrower|employer|developer)|its contractors)$/i.test(n)) return n;
  }
  return /\b(this|the)\s+(borrower|employer|developer)\b/i.test(q) ? ctx.borrowerId ?? null : null;
}

export const IC_INTENTS: readonly IntelIntent[] = [
  {
    id: "intel.network.contagion", pack: "IC", backlog: 9, title: "Contagion map", modules: ["b360"], panel: "ContagionPanel",
    examples: ["If Al Ahsa Energy fails, who else is hit?", "What if CB03184 defaults?", "Show the contagion map for this borrower"],
    patterns: [new RegExp(`\\b(?:if|when|should)\\b.+\\b(?:${FAIL_WORDS})\\b`, "i"), /\bcontagion\b/i, /\bwho else (?:is|gets|would be|will be) (?:hit|hurt|affected)\b/i,
               /\bsecond[-\s]order exposure\b/i],
    answer: { headline: "text.headline", lines: "text.lines" },
    request: (q, ctx) => {
      const b = failedBorrower(q, ctx);
      return b ? { service: "b360", method: "GET", path: `${NET}/contagion/${encodeURIComponent(b)}${qs({ severity: severityOf(q), period: ctx.period })}` } : null;
    },
  },
  {
    id: "intel.network.employer", pack: "IC", backlog: 10, title: "Employer exposure", modules: ["b360", "whatif"], panel: "EmployerPanel",
    examples: ["What is our exposure to Saadiyat Crest Developments through its contractors?", "Employer exposure for Turaif First Properties",
               "Which project employers are we most exposed to?"],
    patterns: [/\bemployer exposure\b/i, /\bproject employers?\b/i, /\bthrough (?:its|their|the) contractors\b/i,
               /\bcontractors? (?:it|they) pays?\b/i, /\bexposure to\b.+\bcontractors\b/i],
    answer: { headline: "text.headline", lines: "text.lines" },
    request: (q, ctx) => {
      const e = employerOf(q, ctx);
      return e
        ? { service: "b360", method: "GET", path: `${NET}/employer/${encodeURIComponent(e)}${qs({ period: ctx.period })}` }
        : { service: "b360", method: "GET", path: `${NET}/employers${qs({ limit: "10", period: ctx.period })}` };
    },
  },
  {
    id: "intel.network.event", pack: "IC", backlog: 8, title: "Event translator", modules: ["b360", "whatif"], panel: "EventTranslatorPanel",
    examples: ["What if oil falls 30% this morning?", "Red Sea shipping disruption, severe", "Tuwaiq First Properties delays payments to contractors",
               "Downgrade the hospitality sector: who do I call?"],
    patterns: [/\b(?:oil|brent|crude)\b.*\b(?:fall|falls|fell|drop|drops|down|crash\w*|plunge\w*|slump\w*|collapse\w*|rise|rises|spike\w*|up)\b/i,
               /\b(?:oil|brent|crude)\b\s*[-−+]\s*\d/i,
               /\b(?:red\s+sea|houthi\w*|bab[\s-]?el[\s-]?mandeb|suez|shipping\s+(?:disruption|route|crisis))\b/i,
               /\bdelay\w*\s+(?:its\s+)?payments?\b/i, /\b(?:sector|industry)\s+downgrade\b|\bdowngrade\s+(?:the\s+)?\w+(?:\s+\w+)?\s+sector\b/i,
               /\bevent\b.*\b(?:hit|impact|translate)\b/i, /\bwho (?:should|do) i call\b.*\b(?:if|after|when)\b/i],
    answer: { headline: "text.headline", lines: "text.lines" },
    request: (q, ctx) => ({ service: "b360", method: "POST", path: `${NET}/event`,
                            body: { text: q, ...(severityOf(q) ? { severity: severityOf(q) } : {}), ...(ctx.period ? { period: ctx.period } : {}) } }),
  },
];

/** The pack's intents in match order (M appends IA, IB, ID and IE here on merge). */
export const INTEL_INTENTS: readonly IntelIntent[] = [...IC_INTENTS];

export function matchIntent(question: string, ctx: IntentContext = {}, intents: readonly IntelIntent[] = INTEL_INTENTS): IntentMatch | null {
  const q = question.trim();
  if (!q) return null;
  for (const intent of intents) {
    if (!intent.patterns.some((p) => p.test(q))) continue;
    const request = intent.request(q, ctx);
    if (request) return { intent, request };
  }
  return null;
}
