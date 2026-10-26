/**
 * PLAN_R13 §I: intent descriptors for the CCO intelligence engines, so Noor's Ask box can call an engine
 * ("who should I call today?", "what if oil falls 30% this morning?"). Pure data and pure functions (node --test).
 *
 * One descriptor per engine: what it answers, the words that route a question to it (regex strings, matched
 * case-insensitively on the question), the one API that answers it, the panel that shows it and the tools menus
 * the panel is exported to. M merges the sessions' lists into INTEL_INTENTS and wires them into Noor's router.
 *
 * Session IE (governance and team): items 18 inspection responder, 19 exception intelligence, 21 RM track record,
 * 22 DoA calibration. Their panels live in components/v5/intel/governance and open from the Admin and Deal Desk
 * tools menus (?gov=<panel>).
 */

export type IntelMenu = "admin-tools" | "dealdesk-tools" | "dealdesk-more" | "book-tools" | "ews-tools" | "b360-tools" | "whatif-tools" | "lenses-tools";

export interface IntelIntent {
  /** Stable id, also the ?gov= / panel key. */
  id: string;
  /** Session that owns the engine (PLAN_R13 §I). */
  session: "IA" | "IB" | "IC" | "ID" | "IE";
  /** R14 backlog number (docs/v5/R14_BACKLOG_CCO_IDEAS.md). */
  backlog: number;
  label: string;
  /** One line: the job the engine finishes. */
  job: string;
  /** Regex strings; any match routes the question here. */
  cues: string[];
  api: { method: "GET" | "POST"; path: string; body?: "question" | "none" };
  /** Exported panel component name. */
  panel: string;
  menus: IntelMenu[];
  /** Where the panel opens from Noor (the module page with the panel query). */
  href: string;
  /** Starter questions for Noor's Ask box. */
  examples: string[];
}

export const GOVERNANCE_INTENTS: readonly IntelIntent[] = [
  {
    id: "inspection", session: "IE", backlog: 18, label: "Inspection responder",
    job: "Answers a regulator's or auditor's request with a traced evidence pack (Word and Excel) and a coverage check.",
    cues: ["\\binspect", "\\bauditor?s?\\b", "\\baudit (request|sample|query)", "\\bregulator", "\\bSAMA\\b", "evidence pack",
           "sample (of|list)", "\\bexaminer", "\\bevidence\\b", "\\b(CB\\d{5}|CF\\d{6}|R12-[A-Z0-9]+|DD-\\d{2}|PL-\\d{2})\\b"],
    api: { method: "POST", path: "/api/v1/intel/governance/inspection", body: "question" },
    panel: "InspectionPanel", menus: ["admin-tools", "dealdesk-tools"], href: "/deal-desk?gov=inspection",
    examples: ["The auditor wants approvals, conditions and stage for the 5 largest Stage 3 borrowers",
               "Prepare the evidence for CB00039 and R12-TWA: exposure, ECL and exceptions"],
  },
  {
    id: "exceptions", session: "IE", backlog: 19, label: "Exception intelligence",
    job: "Every approved policy exception and what happened after; which exception types lead to losses and should tighten.",
    cues: ["\\bexceptions?\\b", "\\bdeviations?\\b", "\\bwaivers?\\b", "policy override", "which (policy )?exceptions"],
    api: { method: "GET", path: "/api/v1/intel/governance/exceptions", body: "none" },
    panel: "ExceptionPanel", menus: ["admin-tools", "dealdesk-tools"], href: "/deal-desk?gov=exceptions",
    examples: ["Which policy exceptions lead to defaults?", "Should we tighten any exception types?"],
  },
  {
    id: "rm-track", session: "IE", backlog: 21, label: "RM track record",
    job: "Proposal quality, conditions met, promises delivered and later performance by RM and branch, risk-adjusted.",
    cues: ["track record", "\\bRMs?\\b.*(perform|quality|best|worst|rank|worse|better|risk they)", "\\brank (the )?(rms|branches)\\b", "(best|worst|weakest|strongest) (rm|relationship manager|branch)",
           "relationship managers?", "branch (performance|ranking|league)", "promises delivered"],
    api: { method: "GET", path: "/api/v1/intel/governance/rm-track", body: "none" },
    panel: "RmTrackPanel", menus: ["admin-tools", "dealdesk-tools"], href: "/deal-desk?gov=rm-track",
    examples: ["Which RMs book worse than the risk they take?", "Rank the branches on conditions met and later defaults"],
  },
  {
    id: "doa", session: "IE", backlog: 22, label: "DoA calibration",
    job: "Where approval levels add delay without changing decisions, with a proposed delegation redesign.",
    cues: ["\\bDoA\\b", "delegation", "approval (level|levels|authority|chain)", "turnaround", "slow(s|er)? (deals|approvals)",
           "(committee|level) adds? (delay|time)"],
    api: { method: "GET", path: "/api/v1/intel/governance/doa", body: "none" },
    panel: "DoaPanel", menus: ["admin-tools", "dealdesk-tools"], href: "/deal-desk?gov=doa",
    examples: ["Which approval levels slow deals without changing them?", "Propose a new delegation of authority"],
  },
];

/** Every session's descriptors (M appends IA–ID when merging). */
export const INTEL_INTENTS: readonly IntelIntent[] = [...GOVERNANCE_INTENTS];

const compiled = new Map<string, RegExp[]>();
function cuesOf(i: IntelIntent): RegExp[] {
  let r = compiled.get(i.id);
  if (!r) { r = i.cues.map((c) => new RegExp(c, "i")); compiled.set(i.id, r); }
  return r;
}

/** The intent a question routes to (most cue hits wins; ties keep list order), or null. */
export function intentFor(text: string, intents: readonly IntelIntent[] = INTEL_INTENTS): IntelIntent | null {
  const q = (text ?? "").trim();
  if (!q) return null;
  let best: IntelIntent | null = null;
  let hits = 0;
  for (const i of intents) {
    const n = cuesOf(i).filter((re) => re.test(q)).length;
    if (n > hits) { best = i; hits = n; }
  }
  return best;
}

/** The page that opens the panel with the question carried (?q=). */
export function intentHref(intent: IntelIntent, text = ""): string {
  const q = text.trim();
  return q ? `${intent.href}&q=${encodeURIComponent(q)}` : intent.href;
}

export function intentsForMenu(menu: IntelMenu, intents: readonly IntelIntent[] = INTEL_INTENTS): IntelIntent[] {
  return intents.filter((i) => i.menus.includes(menu));
}
