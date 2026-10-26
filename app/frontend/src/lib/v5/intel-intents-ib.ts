/**
 * R13 §I: intent descriptors so Noor's Ask box can call the CCO intelligence engines ("who should I call today?").
 *
 * Each intent names the phrases that should route to it, the engine's API, and the compact panel and menu it opens. Pure
 * data plus `matchIntent` (no React), so `node --test` covers it. Sessions IA–IE each add their own entries; M wires
 * the Ask box to `matchIntent` when it merges.
 */

export type IntelModule = "deal-desk-book" | "early-warning" | "deal-page" | "borrower-360" | "what-if" | "lenses" | "admin";

export interface IntelIntent {
  id: string;
  session: "IA" | "IB" | "IC" | "ID" | "IE";
  label: string;
  /** Lower-case phrases; a question containing any of them (after normalising) matches. */
  phrases: string[];
  module: IntelModule;
  /** The tools/More menu item that opens the panel. */
  menu: string;
  /** The exported panel component. */
  panel: string;
  api: { method: "GET" | "POST"; path: string; service: "dealdesk" };
  /** The intent needs a deal or facility id (the Ask box takes it from the open page or asks for it). */
  needs?: "deal" | "facility";
  starter?: string;
}

export const INTEL_INTENTS: IntelIntent[] = [
  {
    id: "ib.renewal_autopilot", session: "IB", label: "Renewal autopilot",
    phrases: ["renewal autopilot", "renewals due", "renewals coming", "annual review", "annual reviews", "which renewals", "clean renewals",
      "renewal exceptions", "prepare the renewals", "upcoming renewals"],
    module: "deal-desk-book", menu: "Book · Tools · Renewal autopilot", panel: "RenewalAutopilotPanel",
    api: { method: "GET", path: "/api/v1/dealdesk/intel/renewals", service: "dealdesk" },
    starter: "Which renewals in the next 90 days are exceptions?",
  },
  {
    id: "ib.covenant_designer", session: "IB", label: "Covenant designer",
    phrases: ["covenant designer", "design covenants", "which covenants", "covenant thresholds", "set the covenants", "propose covenants",
      "calibrate covenants", "covenant package"],
    module: "deal-page", menu: "Deal page · More · Covenant designer", panel: "CovenantDesignerPanel",
    api: { method: "GET", path: "/api/v1/dealdesk/intel/covenants/{deal}", service: "dealdesk" }, needs: "deal",
    starter: "Which covenants would have warned us 2–3 quarters early on this deal?",
  },
  {
    id: "ib.who_to_call", session: "IB", label: "Who to call today",
    phrases: ["who should i call", "who to call", "who do i call", "call today", "calls this week", "names needing action", "who needs a call",
      "which clients should i call"],
    module: "early-warning", menu: "Early Warning · Tools · Who to call today", panel: "WhoToCallPanel",
    api: { method: "GET", path: "/api/v1/intel/calls", service: "dealdesk" },
    starter: "Who should I call today?",
  },
];

const norm = (s: string): string => s.toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9' ]+/g, " ").replace(/\s+/g, " ").trim();

/** The best intent for a question: the one whose longest matching phrase is longest (ties: list order). */
export function matchIntent(text: string, intents: IntelIntent[] = INTEL_INTENTS): IntelIntent | null {
  const t = ` ${norm(text)} `;
  let best: IntelIntent | null = null;
  let len = 0;
  for (const it of intents) {
    for (const p of it.phrases) {
      const q = norm(p);
      if (q && t.includes(` ${q} `) && q.length > len) { best = it; len = q.length; }
    }
  }
  return best;
}

/** The API path with its id filled in (`{deal}` → the open deal). */
export function intentPath(it: IntelIntent, id?: string): string {
  if (it.needs && !id) throw new Error(`${it.label} needs a ${it.needs} id`);
  return id ? it.api.path.replace(/\{deal\}|\{facility\}/, encodeURIComponent(id)) : it.api.path;
}

export const findIntent = (id: string): IntelIntent | undefined => INTEL_INTENTS.find((i) => i.id === id);
