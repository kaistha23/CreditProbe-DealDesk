/**
 * R16 b: the RM business request. Types, URLs and pure helpers (no figure is computed here: the backend is
 * backend/dealdesk/rm_request/api.py, every figure there carries its source).
 */

import type { Block } from "../proposal/model.ts";

export const BR_BASE = "/api/v1/dealdesk/business-requests";

export interface BrCustomer {
  key: string; proposal_id: string; cif: string; name: string; short?: string; cr_number: string; city?: string; sector?: string;
  sub_sector?: string; case?: string; case_label?: string; group_name?: string; existing: boolean;
}

export interface ChecklistItem { doc_type: string; label: string; subject: string; status: "received" | "expired" | "missing"; doc_id?: string; date?: string; expiry?: string; why?: string }

export interface CustomerFile {
  customer: BrCustomer & Record<string, unknown>; origin: string; existing: boolean;
  facilities: { facility: string; existing_mn: number | null; outstanding_mn: number | null; source: string }[];
  conduct_12m: { credit_turnover_mn: number | null; returned_cheques_n: number | null; source: string };
  accounts_n: number; checklist: ChecklistItem[]; documents_n: number; counts: { received: number; expired: number; missing: number };
  requests: BrListRow[]; ask_hint: string;
}

export interface BrSection { key: string; n: number | null; heading: string; voice: string; part: string; blocks: Block[]; gaps: string[]; method: string }
export interface BrFigure { section: string; label: string; value: number | string; text: string; source: string }
export interface AskItem { action: string; facility: string; amount?: number; from_amount?: number; tenor_months?: number; margin_pct?: number; clause: string }

export interface BusinessRequest {
  request_id: string; proposal_id: string; customer: string; customer_key: string; cif: string; cr_number: string; group: string; sector: string;
  existing: boolean; as_of_label: string; rm: string; ask_text: string; notes_text: string;
  ask: { items: AskItem[]; security: string[]; total_proposed: number };
  totals: { existing: number | null; proposed: number | null; change: number | null };
  sections: BrSection[]; parts: { key: string; title: string; subtitle: string; sections: string[] }[];
  figures: BrFigure[]; notes_used: { text: string; topic: string; section: string }[];
  checklist: { received: number; expired: number; missing: number; total: number };
  disclosures: string[]; plain_words: string[]; header_line: [string, string][]; untraced: BrFigure[];
  status?: string; shared_with?: string; written_at?: string;
  links: { self: string; docx: string; trace: string; share: string; open: string };
}

export interface BrListRow { request_id: string; proposal_id: string; customer: string; rm: string; ask_text: string; written_at: string; status: string; shared_with: string; total_proposed: number | null }

export const brUrls = {
  customers: () => `${BR_BASE}/customers`,
  customer: (ref: string) => `${BR_BASE}/customer/${encodeURIComponent(ref)}`,
  write: () => BR_BASE,
  one: (rid: string) => `${BR_BASE}/${encodeURIComponent(rid)}`,
  docx: (rid: string) => `${BR_BASE}/${encodeURIComponent(rid)}.docx`,
  trace: (rid: string) => `${BR_BASE}/${encodeURIComponent(rid)}/trace`,
  share: (rid: string) => `${BR_BASE}/${encodeURIComponent(rid)}/share`,
  list: (pid?: string) => `${BR_BASE}${pid ? `?proposal_id=${encodeURIComponent(pid)}` : ""}`,
};

/** Where a shared request opens (clicks, not URLs: the Mail object links here and the Deal Desk landing opens the studio). */
export const brHref = (rid: string) => `/deal-desk?br=${encodeURIComponent(rid)}`;
export const brStudioHref = (customer: string, ask?: string) =>
  `/deal-desk?brc=${encodeURIComponent(customer)}${ask ? `&ask=${encodeURIComponent(ask)}` : ""}`;

const VERB = /\b(renew|increase|enhance|raise|reduce|take ?over|takeover|top[- ]?up|add (?:a )?new|new\s+(?:sar|usd|\d)|grant|approve a new|one[- ]off)\b/i;
const FACILITY = /\b(overdraft|od|lcs?|letters? of (?:credit|guarantee)|lgs?|guarantees?|murabaha|tawarruq|term loan|stl|working capital|trade (?:finance|line|limit)|general limit|limits?|facilit(?:y|ies)|line|trust receipts?|bid bonds?|performance bonds?|project limit)\b/i;
const QUESTION = /^(what|why|how|which|who|when|where|is|are|does|do|can|should|could|would|show|list|explain)\b/i;

/** True when a chat-box line is an RM's ask (a business request to write), not a question to answer. */
export function isBusinessAsk(q: string): boolean {
  const t = q.trim();
  if (!t || t.endsWith("?") || QUESTION.test(t)) return /\bbusiness request\b/i.test(t) && !t.endsWith("?");
  if (/\b(write|draft|prepare)\b.*\bbusiness request\b/i.test(t)) return true;
  const money = /\b(?:sar|usd|aed)\s*\d|\d\s*(?:m|mn|million|bn)\b/i.test(t);
  return FACILITY.test(t) && (VERB.test(t) || money);
}

/** The customer a line names (key, proposal id, CR number, CIF, or a word of the name), from the list the API gives. */
export function customerIn(q: string, customers: BrCustomer[]): BrCustomer | null {
  const t = q.toLowerCase();
  for (const c of customers) {
    const ids = [c.proposal_id, c.cr_number, c.cif].filter(Boolean).map((x) => x.toLowerCase());
    if (ids.some((x) => t.includes(x))) return c;
  }
  for (const c of customers) {
    const names = [c.short ?? "", c.name.replace(/\b(co|company|llc|est)\.?$/i, "").trim()].filter((x) => x.length > 3).map((x) => x.toLowerCase());
    if (names.some((x) => t.includes(x))) return c;
  }
  return null;
}

/** The ask without a leading customer name ("Dar Al Naseem: renew all ..." -> "renew all ..."); a name inside the sentence stays. */
export function stripCustomer(q: string, c: BrCustomer | null): string {
  const t = q.trim();
  if (!c) return t;
  for (const n of [c.name, c.short ?? "", c.proposal_id].filter(Boolean)) {
    const esc = n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const m = new RegExp(`^(?:for\\s+)?${esc}\\s*[:,\\-–]\\s*`, "i").exec(t);
    if (m) return t.slice(m[0].length).trim();
  }
  return t;
}

export function money(v: number | null | undefined): string {
  return v === null || v === undefined ? "–" : `SAR ${v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`;
}

/** The request laid out as pages: page 1 = header + Action requested, then one page per part (as in the Word file). */
export function pagesOf(p: Pick<BusinessRequest, "sections" | "parts">): { key: string; title: string; subtitle: string; sections: BrSection[] }[] {
  const by = new Map(p.sections.map((s) => [s.key, s]));
  const pages = p.parts.map((x) => ({ key: x.key, title: x.title, subtitle: x.subtitle, sections: x.sections.map((k) => by.get(k)).filter(Boolean) as BrSection[] }));
  const header = by.get("header");
  if (header && pages.length) pages[0] = { ...pages[0], sections: [header, ...pages[0].sections] };
  return pages;
}

/** Figures grouped by source (the Trace view), most used first. */
export function traceGroups(figs: BrFigure[]): { source: string; figures: BrFigure[] }[] {
  const m = new Map<string, BrFigure[]>();
  for (const f of figs) m.set(f.source, [...(m.get(f.source) ?? []), f]);
  return [...m.entries()].map(([source, figures]) => ({ source, figures })).sort((a, b) => b.figures.length - a.figures.length || a.source.localeCompare(b.source));
}

export const STATUS_TONE: Record<ChecklistItem["status"], "positive" | "warning" | "negative"> = { received: "positive", expired: "warning", missing: "negative" };
