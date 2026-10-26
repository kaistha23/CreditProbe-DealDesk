/**
 * Rounds W and T: the paper workspace (the living business request and credit proposal). Types, URLs and pure helpers; the
 * backend is backend/dealdesk/paperws (no figure is computed here: the document, its versions and its provenance come from it).
 */

import type { Block } from "../proposal/model.ts";

export const PW_BASE = "/api/v1/dealdesk/paper-workspaces";
const enc = encodeURIComponent;

export type PaperKind = "proposal" | "request";

export interface PwSection {
  key: string; n: number | null; heading: string; voice: string; part: string; blocks: Block[]; gaps: string[];
  sources?: string[]; edited?: boolean; edited_by?: { author: string; at: number; instruction: string };
}

export interface PwPaper {
  doc_kind: PaperKind; proposal_id: string; request_id?: string; customer: string; as_of_label?: string;
  sections: PwSection[]; parts: { key: string; title: string; subtitle: string; sections: string[] }[];
  header_line?: [string, string][];
  feed?: null | { structure?: { key: string; label: string }; raroc?: number | null; hurdle?: number | null; approval?: string | null };
  ask_text?: string;
}

export interface PwChangeSection { key: string; heading: string; before: Block[]; after: Block[] }
export interface PwChange {
  sections: PwChangeSection[]; status: "pending" | "accepted" | "undone"; note?: string; method?: string; op?: string;
  fields?: { field: string; label: string; from: unknown; to: unknown }[]; undo_of?: number;
}
export interface PwVersion { ws_id: string; n: number; author: string; at: number; action: string; instruction: string; section: string; note: string; change: PwChange | null }
export interface PwPending { version: number; action: string; instruction: string; author: string; at: number; note?: string; fields?: PwChange["fields"]; sections: PwChangeSection[] }
export interface PwTurn { turn_id: string; role: "user" | "noor"; text: string; author: string; at: number; version: number | null; section: string; meta: Record<string, unknown> }
export interface PwRule { rule_id: string; text: string; author: string; at: string; scope: string; section: string }

export interface PwWorkspace {
  ws_id: string; kind: PaperKind; kind_label: string; proposal_id: string; ref: string; title: string; customer: string; owner: string;
  owner_name: string; created: number; updated: number; status: "draft" | "final"; final_version: number | null; current_version: number; href: string;
}

export interface PwLast { kind: "edit" | "structure" | "reply" | "rejected" | "accepted" | "undone" | "final"; text: string; version?: number; section?: string; heading?: string; instruction?: string }

export interface PwState {
  workspace: PwWorkspace; version: { n: number; author: string; at: number; action: string; instruction: string; section: string; note: string };
  paper: PwPaper; versions: PwVersion[]; turns: PwTurn[]; pending: PwPending[]; rules_applied: PwRule[]; model: boolean;
  links: { self: string; open: string; instruct: string; versions: string; provenance: string; docx: string; pdf: string; final_docx: string; mark_final: string };
  last?: PwLast;
}

export interface Evidence {
  kind: "document" | "data" | "engine" | "rule" | "analyst" | "rm"; label?: string; doc_id?: string; page?: number | null; status?: string;
  relation?: string; domain?: string; row?: string; column?: string; value?: unknown; period?: string; engine?: string; printed?: string;
  text?: string; author?: string; at?: string | number; scope?: string; instruction?: string; version?: number; figure?: string;
}
export interface PvPoint { id: string; block: number; item: number | null; kind: string; text: string; evidence: Evidence[]; traced: boolean; has_figure: boolean }
export interface PvSection { key: string; heading: string; n: number | null; voice: string; sources: Evidence[]; points: PvPoint[]; rules: (PwRule & { kind: "rule" })[]; edits: Evidence[]; gaps: string[] }
export interface Provenance {
  kind: PaperKind; proposal_id: string; customer: string; ws_id?: string; version?: number; final_version?: number | null;
  sections: PvSection[]; plain_words: string[];
  summary: { points: number; with_figures: number; figures_traced: number; untraced: { section: string; point: string; text: string }[];
             by_kind: Record<string, number>; documents: { doc_id: string; label: string }[]; relations: string[]; engine: string[]; rules: PwRule[]; edits: number };
}

export const pwUrls = {
  open: () => PW_BASE,
  list: (q: { proposal_id?: string; kind?: PaperKind; mine?: boolean; limit?: number } = {}) => {
    const p = new URLSearchParams();
    if (q.proposal_id) p.set("proposal_id", q.proposal_id);
    if (q.kind) p.set("kind", q.kind);
    if (q.mine) p.set("mine", "true");
    if (q.limit) p.set("limit", String(q.limit));
    const s = p.toString();
    return `${PW_BASE}${s ? `?${s}` : ""}`;
  },
  one: (ws: string, version?: number | null) => `${PW_BASE}/${enc(ws)}${version ? `?version=${version}` : ""}`,
  instruct: (ws: string) => `${PW_BASE}/${enc(ws)}/instruct`,
  accept: (ws: string, n: number) => `${PW_BASE}/${enc(ws)}/versions/${n}/accept`,
  undo: (ws: string, n: number) => `${PW_BASE}/${enc(ws)}/versions/${n}/undo`,
  final: (ws: string) => `${PW_BASE}/${enc(ws)}/final`,
  provenance: (ws: string, version?: number | string | null) => `${PW_BASE}/${enc(ws)}/provenance${version ? `?version=${version}` : ""}`,
  docx: (ws: string, version?: number | string | null) => `${PW_BASE}/${enc(ws)}/export.docx${version ? `?version=${version}` : ""}`,
  pdf: (ws: string, version?: number | string | null) => `${PW_BASE}/${enc(ws)}/export.pdf${version ? `?version=${version}` : ""}`,
};

/** Where a workspace opens (its own page: a thread reopened from Recent work, the deal's Papers and the Workspace). */
export const pwHref = (ws: string, view?: "provenance") => `/deal-desk/paper/${enc(ws)}${view ? `?view=${view}` : ""}`;

/** The body that opens (or reopens) the workspace of a deal's credit proposal, or of a written business request. */
export function openBody(kind: PaperKind, ref: { proposalId?: string; structure?: string | null; requestId?: string; fresh?: boolean }): Record<string, unknown> {
  return kind === "proposal"
    ? { kind, proposal_id: ref.proposalId, ...(ref.structure ? { structure: ref.structure } : {}), ...(ref.fresh ? { fresh: true } : {}) }
    : { kind, ref: ref.requestId, ...(ref.fresh ? { fresh: true } : {}) };
}

/** "1." … "20." for the anatomy, "CP1." … for CreditProbe's sections (as in the Word). */
export function sectionNo(sections: Pick<PwSection, "key" | "n">[], key: string, kind: PaperKind = "proposal"): string {
  if (kind === "request") {
    const i = sections.findIndex((s) => s.key === key);
    return i >= 0 ? `${i + 1}.` : "";
  }
  let cp = 0;
  for (const s of sections) {
    if (!s.n) cp += 1;
    if (s.key === key) return s.n ? `${s.n}.` : `CP${cp}.`;
  }
  return "";
}

/** Sections in the order the paper prints them: the header, then each part's sections. */
export function ordered(p: Pick<PwPaper, "sections" | "parts">): { part: { key: string; title: string; subtitle: string } | null; section: PwSection }[] {
  const by = new Map(p.sections.map((s) => [s.key, s] as const));
  const out: { part: { key: string; title: string; subtitle: string } | null; section: PwSection }[] = [];
  const used = new Set<string>();
  const head = by.get("header");
  if (head) { out.push({ part: null, section: head }); used.add("header"); }
  for (const part of p.parts ?? []) {
    let first = true;
    for (const k of part.sections) {
      const s = by.get(k);
      if (!s || used.has(k)) continue;
      out.push({ part: first ? { key: part.key, title: part.title, subtitle: part.subtitle } : null, section: s });
      used.add(k);
      first = false;
    }
  }
  for (const s of p.sections) if (!used.has(s.key)) out.push({ part: null, section: s });
  return out;
}

/** The pending change marked on each section (the newest when a section has more than one). */
export function pendingBySection(pending: PwPending[]): Map<string, { version: number; change: PwChangeSection; pending: PwPending }> {
  const m = new Map<string, { version: number; change: PwChangeSection; pending: PwPending }>();
  for (const p of pending) for (const s of p.sections) {
    const cur = m.get(s.key);
    if (!cur || cur.version < p.version) m.set(s.key, { version: p.version, change: s, pending: p });
  }
  return m;
}

/** Plain lines of a list of blocks (the before/after mark compares lines). */
export function blockLines(blocks: Block[]): string[] {
  const out: string[] = [];
  for (const b of blocks) {
    if (b.t === "p" || b.t === "h") out.push(b.text);
    else if (b.t === "bullets" || b.t === "numbered") out.push(...b.items.map((x) => `• ${x}`));
    else if (b.t === "table") out.push(`[table: ${b.header.join(" | ")}; ${b.rows.length} rows]`);
    else if (b.t === "kv") out.push(...b.pairs.map(([k, v]) => `${k}: ${v}`));
  }
  return out;
}

/** Line diff for the mark: lines removed (in before only) and added (in after only), in order. */
export function lineDiff(before: Block[], after: Block[]): { removed: string[]; added: string[] } {
  const a = blockLines(before), b = blockLines(after);
  const inB = new Set(b), inA = new Set(a);
  return { removed: a.filter((x) => !inB.has(x)), added: b.filter((x) => !inA.has(x)) };
}

export const ACTION_LABEL: Record<string, string> = { created: "Written", edit: "Edited", structure: "Structure step", undo: "Undo", refresh: "Refreshed" };

export function versionLine(v: Pick<PwVersion, "n" | "action" | "instruction" | "author" | "at">, finalVersion: number | null): string {
  const when = new Date(v.at * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `v${v.n}${finalVersion === v.n ? " (final)" : ""} · ${ACTION_LABEL[v.action] ?? v.action} · ${v.author || "—"} · ${when}`;
}

export const EVIDENCE_LABEL: Record<Evidence["kind"], string> = {
  document: "Document", data: "Bank data", engine: "Engine", rule: "Rule", analyst: "Instruction", rm: "RM",
};

/** One line for an evidence item (the click-through on a point and the provenance view). */
export function evidenceText(e: Evidence): string {
  switch (e.kind) {
    case "document":
      return `${e.label ?? "Document"}${e.doc_id ? ` [${e.doc_id}]` : ""}${e.page ? `, page ${e.page}` : ""}${e.status ? ` (${e.status})` : ""}`;
    case "data":
      if (e.relation && e.column) return `${e.relation}${e.row ? ` · ${e.row}` : ""} · ${e.column}${e.value != null ? ` = ${fmtVal(e.value)}` : ""}`;
      return e.label ?? e.relation ?? "";
    case "engine":
      return `${e.label ?? ""}${e.engine ? ` — ${e.engine}` : ""}`;
    case "rule":
      return `${e.text ?? e.label ?? ""}${e.author || e.at ? ` (${[e.author, String(e.at ?? "").slice(0, 10), e.scope].filter(Boolean).join(", ")})` : ""}`;
    case "analyst":
      return `v${e.version ?? "?"} · ${e.author || "analyst"} · “${e.instruction ?? ""}”`;
    default:
      return e.label ?? "";
  }
}

function fmtVal(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return String(v);
}

/** The points of a section by block (and item), for the click-through. */
export function pointIndex(pv: Provenance | null): Map<string, PvPoint> {
  const m = new Map<string, PvPoint>();
  for (const s of pv?.sections ?? []) for (const p of s.points) m.set(p.id, p);
  return m;
}

/** Instructions offered under the box (the fixed set that works with no model key). */
export function suggestions(kind: PaperKind, focus: string | null, heading: string | null): string[] {
  const where = heading ? ` the ${heading.replace(/\s*\(CreditProbe\)$/, "").toLowerCase()}` : " the financial synopsis";
  const base = [`Shorten${where}`, `Add to${where}: `, `Make${where} bullet points`];
  return kind === "proposal"
    ? [...base, "Set the amount to SAR 20m", "Set the tenor to 5 years"]
    : [...base, "Increase the overdraft to SAR 35m"];
  void focus;
}

/** The busy line while an instruction runs (the structure step re-prices with the engine: tens of seconds). */
export function busyLine(text: string, kind: PaperKind): string {
  const number = kind === "proposal"
    ? /\b(set|change|increase|raise|reduce|lower|cut|make|move)\b.*\b(amount|limit|tenor|margin|pricing|fee|cash margin)\b.*\d/i.test(text)
    : /\b(increase|reduce|renew|new|add)\b.*\d/i.test(text) && /\b(overdraft|murabaha|lc|letters? of|guarantee|loan|facility|line|limit)\b/i.test(text);
  return number ? "Sending it to the structure step: the engine re-prices the terms and the paper is re-rendered (up to a minute)…"
    : "Noor is editing the section…";
}
