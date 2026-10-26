/**
 * R13 M (PLAN_R13 §I): one registry over every CCO intelligence engine, so Noor's Ask box (home Ask tab and the Noor
 * panel) routes a question to the engine that finishes the job.
 *
 * Each §I session keeps its own descriptors and matcher, unchanged, in its own file:
 *   intel-intents-ia.ts  committee challenger, reverse solver, security optimiser, decision consistency
 *   intel-intents-ib.ts  renewal autopilot, covenant designer, who to call today
 *   intel-intents-ic.ts  event translator, contagion map, employer exposure
 *   intel-intents-id.ts  growth headroom, exit list, RWA finder, ECL bridge, workout optimiser
 *   intel-intents-ie.ts  inspection responder, exception intelligence, RM track record, DoA calibration
 *   intel-intents-i.ts   R14 i: negotiation frontier, pre-mortem, precedents, pricing benchmark, revenue truth check,
 *                        renewal diff, group contagion on the deal, committee rehearsal (D6-D13; backlog numbers 106-113)
 * plus R13 Q's financial-quality detector (below). This file normalises them into one `IntelRoute` per engine and one
 * deterministic `routeIntel(question, context)`. Pure (no React, no aliases), so `node --test` covers it.
 *
 * Global routing is stricter than a module's own menu: a question only goes to an engine when its cue is specific
 * (e.g. the portfolio engines need one of their strong phrases, the inspection responder needs more than a borrower id),
 * so ordinary book questions keep going to the Cockpit.
 */

import { INTEL_INTENTS_IA, dealIdIn, matchIntent as matchIA } from "./intel-intents-ia.ts";
import { INTEL_INTENTS as IB_INTENTS, matchIntent as matchIB } from "./intel-intents-ib.ts";
import { IC_INTENTS, matchIntent as matchIC } from "./intel-intents-ic.ts";
import { ID_INTENTS, borrowerIdIn, matchIntelIntent as matchID } from "./intel-intents-id.ts";
import { GOVERNANCE_INTENTS, intentFor as matchIE } from "./intel-intents-ie.ts";
import { INTEL_INTENTS_I, matchIntentI } from "./intel-intents-i.ts";

export type IntelPanelKey =
  | "fin-quality"
  | "challenger" | "reverse" | "security" | "consistency"
  | "renewals" | "covenants" | "calls"
  | "event" | "contagion" | "employer"
  | "headroom" | "exits" | "rwa" | "ecl-bridge" | "workout"
  | "inspection" | "exceptions" | "rm-track" | "doa"
  | "frontier" | "premortem" | "precedents" | "pricing" | "revenue-check" | "renewal-diff" | "group-contagion";

export type IntelNeed = "deal" | "borrower";

export interface IntelRoute {
  key: IntelPanelKey;
  /** The owning session's intent id. */
  id: string;
  session: "Q" | "IA" | "IB" | "IC" | "ID" | "IE" | "I";
  /** docs/v5/R14_BACKLOG_CCO_IDEAS.md item number (R14 i: 100 + the plan's D number). */
  backlog: number;
  label: string;
  /** The module and menu where the panel also lives. */
  home: string;
  needs?: IntelNeed;
  examples: string[];
}

export interface IntelContext { dealId?: string | null; borrowerId?: string | null }

export interface IntelMatch {
  route: IntelRoute;
  question: string;
  deal?: string;
  borrower?: string;
  employer?: string;
  /** Set when the engine needs an id the question and the page do not give. */
  missing?: IntelNeed;
}

const IA_KEY: Record<string, IntelPanelKey> = {
  "dealdesk.approval.challenger": "challenger", "dealdesk.approval.reverse": "reverse",
  "dealdesk.approval.security": "security", "dealdesk.approval.consistency": "consistency",
};
const IB_KEY: Record<string, IntelPanelKey> = { "ib.renewal_autopilot": "renewals", "ib.covenant_designer": "covenants", "ib.who_to_call": "calls" };
const IC_KEY: Record<string, IntelPanelKey> = { "intel.network.contagion": "contagion", "intel.network.employer": "employer", "intel.network.event": "event" };
const ID_KEY: Record<string, IntelPanelKey> = {
  "portfolio.headroom": "headroom", "portfolio.exits": "exits", "portfolio.rwa": "rwa", "portfolio.ecl_bridge": "ecl-bridge", "portfolio.workout": "workout",
};
const IE_KEY: Record<string, IntelPanelKey> = { inspection: "inspection", exceptions: "exceptions", "rm-track": "rm-track", doa: "doa" };

const IA_BACKLOG: Record<string, number> = { challenger: 1, reverse: 4, security: 3, consistency: 20 };
const IB_BACKLOG: Record<string, number> = { renewals: 5, covenants: 2, calls: 7 };

/** R13 Q: financial-quality detector (backlog 6), on the deal page More menu and the Book renewal row. */
export const FIN_QUALITY_ROUTE: IntelRoute = {
  key: "fin-quality", id: "dealdesk.fin_quality", session: "Q", backlog: 6, label: "Financial quality",
  home: "Deal page · More · Financial quality", needs: "deal",
  examples: ["How good are R12-TWA's accounts?", "Are the financials of R12-TWB inflated?"],
};
const FQ_CUES = [/\bfinancial[- ]quality\b/i, /\bquality of (the |its |their )?(accounts|earnings|financials|financial statements)\b/i,
  /\b(accounts|financials|earnings|revenue)\b.{0,30}\b(inflated|window[- ]dress\w*|manipulat\w*|massag\w*|reliable|trustworth\w*)\b/i,
  /\bhow good are\b.{0,40}\b(accounts|financials)\b/i, /\bbeneish\b/i, /\bbenford\b/i, /\brelated[- ]party (balances|receivables)\b/i,
  /\bqualified (audit|opinion)\b/i];

/** Strong phrases a portfolio (ID) question must carry before Noor routes it away from the Cockpit. */
const ID_STRONG: Record<string, RegExp> = {
  "portfolio.headroom": /\b(headroom|where can we (still )?(grow|lend)|can we (still )?lend|lend more|say yes|room to grow|still grow)\b/i,
  "portfolio.exits": /\b(exit list|who should we exit|exit\b.{0,20}\bnames|names to exit|sell[- ]?down|not renew|free (up )?capital|offload)\b/i,
  "portfolio.rwa": /\b(rwa|risk[- ]weighted|save capital|capital saving|exposure class(es)?|unused limits?|not recogni[sz]ed for capital)\b/i,
  "portfolio.ecl_bridge": /\b(ecl bridge|ecl (be )?next quarter|next quarter'?s? ecl|move to stage [23] next quarter|stage movers|overlay justification|forecast (the )?ecl)\b/i,
  "portfolio.workout": /\b(workout|reschedule or|restructure or|legal action|best way to recover)\b/i,
};

const INSPECTION_STRONG = /\b(inspect\w*|auditors?|audit (request|sample|query)|regulator\w*|sama|evidence pack|examiner|evidence)\b/i;

function ia(id: string): IntelRoute {
  const it = INTEL_INTENTS_IA.find((x) => x.id === id)!;
  const key = IA_KEY[id];
  return { key, id, session: "IA", backlog: IA_BACKLOG[key], label: it.label === "Committee challenger" ? "Committee questions" : it.label,
           home: "Deal page · More", needs: key === "consistency" ? undefined : "deal", examples: it.examples };
}
function ib(id: string): IntelRoute {
  const it = IB_INTENTS.find((x) => x.id === id)!;
  const key = IB_KEY[id];
  return { key, id, session: "IB", backlog: IB_BACKLOG[key], label: it.label, home: it.menu, needs: it.needs === "deal" ? "deal" : undefined,
           examples: it.starter ? [it.starter] : [] };
}
function ic(id: string): IntelRoute {
  const it = IC_INTENTS.find((x) => x.id === id)!;
  return { key: IC_KEY[id], id, session: "IC", backlog: it.backlog, label: it.title, home: "Borrower 360 / What-If · Network tools",
           examples: it.examples };
}
function idr(id: string): IntelRoute {
  const it = ID_INTENTS.find((x) => x.id === id)!;
  return { key: ID_KEY[id], id, session: "ID", backlog: it.backlog, label: it.title, home: "Lenses / Book · Portfolio tools",
           needs: it.needs === "borrower_id" ? "borrower" : undefined, examples: it.examples };
}
function ie(id: string): IntelRoute {
  const it = GOVERNANCE_INTENTS.find((x) => x.id === id)!;
  return { key: IE_KEY[id], id, session: "IE", backlog: it.backlog, label: it.label, home: "Deal Desk / Admin · Governance", examples: it.examples };
}

/** R14 i: D6-D12 routes (D13 committee rehearsal answers on the existing "challenger" route and panel). */
function ir(id: string): IntelRoute {
  const it = INTEL_INTENTS_I.find((x) => x.id === id)!;
  return { key: it.panel as IntelPanelKey, id, session: "I", backlog: 100 + Number(it.code.slice(1)), label: it.label,
           home: "Deal page · More · Intelligence", needs: "deal", examples: it.examples };
}

/** Every engine Noor can route to, in backlog order (the Ask box and the UAT list read this). */
export const INTEL_ROUTES: IntelRoute[] = [
  ...INTEL_INTENTS_IA.map((i) => ia(i.id)),
  ...IB_INTENTS.map((i) => ib(i.id)),
  ...IC_INTENTS.map((i) => ic(i.id)),
  ...ID_INTENTS.map((i) => idr(i.id)),
  ...GOVERNANCE_INTENTS.map((i) => ie(i.id)),
  ...INTEL_INTENTS_I.filter((i) => i.panel !== "challenger").map((i) => ir(i.id)),
  FIN_QUALITY_ROUTE,
].sort((a, b) => a.backlog - b.backlog);

/** Kept for the sessions' own imports: the union of every session's intent ids. */
export const INTEL_INTENT_IDS: string[] = INTEL_ROUTES.map((r) => r.id);

export const routeByKey = (key: IntelPanelKey): IntelRoute => INTEL_ROUTES.find((r) => r.key === key)!;

function withIds(route: IntelRoute, q: string, ctx: IntelContext, extra: Partial<IntelMatch> = {}): IntelMatch {
  const m: IntelMatch = { route, question: q, ...extra };
  if (route.needs === "deal") {
    const d = dealIdIn(q) ?? ctx.dealId ?? null;
    if (d) m.deal = d; else m.missing = "deal";
  }
  if (route.needs === "borrower") {
    const b = borrowerIdIn(q) ?? ctx.borrowerId ?? null;
    if (b) m.borrower = b; else m.missing = "borrower";
  }
  return m;
}

/**
 * The engine a question goes to, or null (then the usual Noor routes apply: brief, What-If, Lenses, Deal Desk, Cockpit).
 * Order: network events and failures (they also name "who to call"), who to call / renewals / covenants, the deal-level
 * approval engines, financial quality, portfolio steering, governance.
 */
export function routeIntel(question: string, ctx: IntelContext = {}): IntelMatch | null {
  const q = question.split(/\s+/).filter(Boolean).join(" ");
  if (!q) return null;
  // A calibrated book stress ("mild, moderate and severe") stays with What-If's scenario engine.
  if (/\b(mild|moderate)\b.*\bsevere\b/i.test(q) && !/\b(oil|brent|crude|red sea)\b/i.test(q)) return null;

  // R14 i: the deal-intelligence phrasings are specific; they go first (D13 rehearsal answers on the challenger route).
  const iMatch = matchIntentI(q, { dealId: ctx.dealId ?? null });
  if (iMatch) {
    const route = iMatch.intent.panel === "challenger" ? ia("dealdesk.approval.challenger") : ir(iMatch.intent.id);
    return withIds(route, q, ctx);
  }

  const c = matchIC(q, { borrowerId: ctx.borrowerId ?? undefined });
  // A move "over the next year" is a scenario (What-If, calibrated severities); "this morning" is an event.
  const horizon = /\bover the next\b|\bnext (\d+ )?(years?|months|quarters)\b/i.test(q);
  if (c && !(horizon && c.intent.id === "intel.network.event")) {
    const key = IC_KEY[c.intent.id];
    const extra: Partial<IntelMatch> = {};
    const path = c.request.path;
    const seg = decodeURIComponent(path.split("?")[0].split("/").pop() ?? "");
    if (key === "contagion") extra.borrower = seg;
    if (key === "employer" && !/\/employers$/.test(path.split("?")[0])) extra.employer = seg;
    return { route: ic(c.intent.id), question: q, ...extra };
  }

  const b = matchIB(q);
  if (b) return withIds(ib(b.id), q, ctx);

  const a = matchIA(q, { deal_id: ctx.dealId ?? null });
  if (a) return withIds(ia(a.intent.id), q, ctx);
  // IA returns null when a deal-level question names no deal: still route it, and ask for the deal.
  const aNoDeal = INTEL_INTENTS_IA.find((it) => it.patterns.some((p) => new RegExp(p).test(q.toLowerCase())));
  if (aNoDeal) return withIds(ia(aNoDeal.id), q, ctx);

  if (FQ_CUES.some((re) => re.test(q))) return withIds(FIN_QUALITY_ROUTE, q, ctx);

  const d = matchID(q);
  if (d && ID_STRONG[d.intent.id]?.test(q)) return withIds(idr(d.intent.id), q, ctx);

  const e = matchIE(q);
  if (e && (e.id !== "inspection" || INSPECTION_STRONG.test(q))) return withIds(ie(e.id), q, ctx);
  return null;
}

/** The module page where the engine's panel lives (the "Open in …" link under an answer). */
export function intelHref(m: IntelMatch): string {
  const q = encodeURIComponent(m.question);
  switch (m.route.session) {
    case "Q": case "IA": case "I": return m.deal ? `/deal-desk/${encodeURIComponent(m.deal)}?intel=${m.route.key}` : "/deal-desk";
    case "IB":
      if (m.route.key === "calls") return "/early-warning?intel=calls";
      if (m.route.key === "renewals") return "/deal-desk?tab=book&intel=renewals";
      return m.deal ? `/deal-desk/${encodeURIComponent(m.deal)}?intel=covenants` : "/deal-desk";
    case "IC": return `/borrower-360?intel=${m.route.key}&q=${q}`;
    case "ID": return `/lenses?intel=${m.route.key}${m.borrower ? `&borrower=${encodeURIComponent(m.borrower)}` : ""}`;
    case "IE": return `/deal-desk?gov=${m.route.key}&q=${q}`;
  }
}
