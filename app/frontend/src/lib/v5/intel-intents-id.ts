/**
 * PLAN_R13 §I: intents Noor's Ask box can call — one descriptor per CCO intelligence engine. Session M wires them
 * into Noor; each session adds its own block. A descriptor names the engine's API, the panel that renders it and the
 * module menus it lives in, plus the phrases that should route to it.
 *
 * Pure data and a deterministic matcher (no React, no path aliases), so node --test can run it.
 */

export type IntelSession = "IA" | "IB" | "IC" | "ID" | "IE";
export type IntelMenu = "lenses" | "book" | "deal_more" | "ews" | "b360" | "whatif" | "admin" | "dealdesk";

export interface IntelIntent {
  id: string;
  session: IntelSession;
  backlog: number;
  title: string;
  /** What the engine answers, in the CCO's words. */
  question: string;
  /** Starter prompts for the Ask box. */
  examples: string[];
  /** Lower-case keywords; a match on more of them ranks higher. */
  keywords: string[];
  /** Deal Desk service path; `{borrower_id}` is filled from the question or asked for. */
  endpoint: string;
  method: "GET" | "POST";
  /** Named parameter the intent needs from the question, if any. */
  needs?: "borrower_id";
  /** Exported panel component and the module menus it appears in. */
  panel: string;
  menus: IntelMenu[];
}

// ------------------------------------------------------------------ ID: portfolio steering (backend/intel/portfolio)

export const ID_INTENTS: IntelIntent[] = [
  {
    id: "portfolio.headroom", session: "ID", backlog: 14, title: "Growth headroom map",
    question: "Where can the bank still lend next quarter, by sector, rating band and group, within appetite, capital and concentration?",
    examples: ["Where can we still grow next quarter?", "Which sectors have headroom within appetite?", "How much more can we lend to IG manufacturing?"],
    keywords: ["headroom", "grow", "growth", "room", "lend more", "where can we lend", "appetite", "capacity", "say yes", "next quarter", "more can we lend", "can we lend"],
    endpoint: "/api/v1/intel/portfolio/headroom", method: "GET", panel: "HeadroomPanel", menus: ["lenses", "book"],
  },
  {
    id: "portfolio.exits", session: "ID", backlog: 15, title: "Exit and sell-down list",
    question: "Which names should we reduce, sell down or not renew, and what capital and ECL does that free?",
    examples: ["Who should we exit?", "Which names should we not renew?", "Where do we free capital by selling down?"],
    keywords: ["exit", "sell down", "sell-down", "not renew", "reduce", "run off", "free capital", "shrink", "offload"],
    endpoint: "/api/v1/intel/portfolio/exits", method: "GET", panel: "ExitsPanel", menus: ["lenses", "book"],
  },
  {
    id: "portfolio.rwa", session: "ID", backlog: 16, title: "RWA finder",
    question: "Where can we save capital in the book: unrecognised collateral and guarantees, wrong exposure classes, unused limits?",
    examples: ["Where can we save RWA?", "Which guarantees are not recognised for capital?", "How much capital do unused limits cost us?"],
    keywords: ["rwa", "risk-weighted", "risk weighted", "capital saving", "save capital", "guarantee", "exposure class", "undrawn", "ccf", "crm", "unused limit", "capital do"],
    endpoint: "/api/v1/intel/portfolio/rwa", method: "GET", panel: "RwaPanel", menus: ["lenses", "book"],
  },
  {
    id: "portfolio.ecl_bridge", session: "ID", backlog: 17, title: "ECL bridge forecast",
    question: "What will next quarter's ECL be before the run, who moves stage, and what overlay do we justify?",
    examples: ["What will ECL be next quarter?", "Who will move to Stage 2 next quarter?", "Draft the overlay justification"],
    keywords: ["ecl", "provision", "bridge", "next quarter", "stage 2", "stage 3", "stage movers", "overlay", "forecast"],
    endpoint: "/api/v1/intel/portfolio/ecl-bridge", method: "GET", panel: "EclBridgePanel", menus: ["lenses", "book"],
  },
  {
    id: "portfolio.workout", session: "ID", backlog: 11, title: "Workout optimiser",
    question: "For a stressed name, which is best: reschedule, extra collateral, partial exit, sale or legal action?",
    examples: ["What is the best workout for Tuwaiq Construction?", "Should we reschedule or sell CB00002?", "Workout options for our stressed names"],
    keywords: ["workout", "reschedule", "restructure", "restructuring", "legal action", "enforce", "recovery", "stressed", "npl", "sale"],
    endpoint: "/api/v1/intel/portfolio/workout/{borrower_id}", method: "GET", needs: "borrower_id", panel: "WorkoutPanel", menus: ["lenses", "book"],
  },
];

/** Every session's intents (M concatenates the other sessions' blocks here when merging). */
export const INTEL_INTENTS: IntelIntent[] = [...ID_INTENTS];

export interface IntentMatch { intent: IntelIntent; score: number; borrowerId: string | null }

/** Deterministic keyword match: the intent with the most (longest-first) keyword hits; ties by list order. */
export function matchIntelIntent(text: string, intents: IntelIntent[] = INTEL_INTENTS): IntentMatch | null {
  const t = ` ${text.toLowerCase().replace(/\s+/g, " ")} `;
  let best: IntentMatch | null = null;
  for (const intent of intents) {
    let score = 0;
    for (const k of intent.keywords) if (t.includes(k)) score += k.split(" ").length;
    if (score > 0 && (!best || score > best.score)) best = { intent, score, borrowerId: null };
  }
  if (best && best.intent.needs === "borrower_id") best.borrowerId = borrowerIdIn(text);
  return best;
}

/** A corporate obligor id in the question (CB followed by digits), if any. */
export function borrowerIdIn(text: string): string | null {
  const m = /\b(CB\d{4,})\b/i.exec(text);
  return m ? m[1].toUpperCase() : null;
}

/** The endpoint with its parameter filled, or null when the intent needs one the question does not give. */
export function intentUrl(m: IntentMatch): string | null {
  if (m.intent.needs === "borrower_id") {
    return m.borrowerId ? m.intent.endpoint.replace("{borrower_id}", encodeURIComponent(m.borrowerId)) : null;
  }
  return m.intent.endpoint;
}

export function intentsForMenu(menu: IntelMenu, intents: IntelIntent[] = INTEL_INTENTS): IntelIntent[] {
  return intents.filter((i) => i.menus.includes(menu));
}
