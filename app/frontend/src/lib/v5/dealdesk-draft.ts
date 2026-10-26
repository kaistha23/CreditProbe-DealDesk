/**
 * PLAN_R11 Session P: "Draft proposal" in the bank's house style, on the Deal Desk service
 * (/api/v1/dealdesk/house-style/*, /proposals/{id}/draft, /drafts/{id}/*; docs/STATUS_R11_STYLE.md).
 *
 * The API drafts each section from data (every figure a cited fact) in the house language; the screen shows the draft
 * with per-section regenerate and accept, the style score against the house band and the lint, and the Word export.
 * The helpers below are pure and tested (dealdesk-draft.test.ts).
 */
import { friendlyError } from "./errors.ts";

const ENGINE = "/api/v1/dealdesk";

export function draftOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class DraftError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${draftOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new DraftError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new DraftError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

const enc = encodeURIComponent;

// ---------------------------------------------------------------- schemas

export interface Fact {
  id: string; key: string; label: string; value: string | number; unit: string; display: string; source: string;
  derived: string | null; kind: "number" | "text"; section: string;
}
export interface DraftTable { header: string[]; rows: string[][]; cites: string[]; source?: string }
export interface ExemplarRef { doc_id: string; heading: string; similarity: number; primary: boolean }
export interface DraftSection {
  key: string; heading: string; voice: "business" | "credit"; judgement: boolean; paragraphs: string[]; bullets: string[];
  table: DraftTable | null; citations: Fact[]; exemplars: ExemplarRef[]; method: string; status: "draft" | "accepted";
  edited: boolean; version: number; score?: number; figure_checks?: string[];
}
export interface Band { low: number; high: number; mean: number | null; n: number; basis?: string }
export interface StyleScore {
  total: number; structure: number; phrase: number; stylometrics: number; stylometric_parts: Record<string, number>;
  band: Band; within_band: boolean;
}
export interface Lint { id: string; rule: string; severity: "major" | "minor" | "info"; section: string; message: string; excerpt: string; suggestion: string }
export interface Draft {
  draft_id: string; proposal_id: string; title: string; created: string;
  meta: { pid: string; source: string; bank: string; kind: string; segment: string; currency: string; name: string; sector: string; rating: string };
  profile: { group: string; bank_label: string; documents: number; primary_exemplars: string[]; edits_learned: number };
  sections: DraftSection[]; facts: Fact[]; score: StyleScore; lint: Lint[]; methods: string[];
}
export interface ProfileSection { key: string; heading: string; label: string; presence: number; voice: string; openers: { text: string; weight: number }[] }
export interface Rates { sentence_words: number | null; sentence_sd: number | null; hedges_per_100w: number | null; first_person_per_100w: number | null; passive_share: number | null }
export interface Weighted { text: string; weight: number }
export interface ProfileView {
  profile: { group: string; bank_label: string; documents: number; sections: ProfileSection[]; credit_sections: ProfileSection[];
    primary_exemplars: string[]; edits_learned: number; doc_ids: string[];
    numbers: { unit: string; decimals: number; percent: string; multiple: string; trim_integers?: boolean; bn_for_round_billions?: boolean };
    spelling: string; voices: Record<string, Rates>; phrases: Weighted[]; abbreviations: Weighted[]; recommendation_wording: Weighted[];
    learned: { preferred: Weighted[]; avoid: Weighted[] } };
  guide: string;
}
export interface IngestResult { doc_id: string; title: string; profile_group: string; documents_after: number; summary: string }

export const drafting = {
  create: (pid: string, sections?: string[]) => call<Draft>(`/proposals/${enc(pid)}/draft`, { method: "POST", body: JSON.stringify(sections ? { sections } : {}) }),
  latest: (pid: string) => call<Draft>(`/proposals/${enc(pid)}/draft`),
  get: (did: string) => call<Draft>(`/drafts/${enc(did)}`),
  regenerate: (did: string, key: string) => call<Draft>(`/drafts/${enc(did)}/sections/${enc(key)}/regenerate`, { method: "POST", body: "{}" }),
  edit: (did: string, key: string, text: string) => call<Draft>(`/drafts/${enc(did)}/sections/${enc(key)}`, { method: "PATCH", body: JSON.stringify({ text }) }),
  accept: (did: string, key: string, accept = true) => call<Draft>(`/drafts/${enc(did)}/sections/${enc(key)}`, { method: "PATCH", body: JSON.stringify({ accept }) }),
  profile: (pid: string) => call<ProfileView>(`/house-style/profile?proposal_id=${enc(pid)}`),
  ingest: (file: File, bank = "house-uae") => {
    const f = new FormData(); f.append("file", file); f.append("bank", bank);
    return call<IngestResult>("/house-style/corpus", { method: "POST", body: f });
  },
  docxUrl: (did: string) => `${draftOrigin()}${ENGINE}/drafts/${enc(did)}/docx`,
};

// ---------------------------------------------------------------- pure helpers

export type Segment = { kind: "text"; text: string } | { kind: "cite"; id: string };

/** A drafted line split into text and citation chips: "Revenue AED 2,050m [F27]." -> text, cite F27, text. */
export function splitCitations(line: string): Segment[] {
  const out: Segment[] = [];
  const re = /\s?\[(F\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) out.push({ kind: "text", text: line.slice(last, m.index) });
    out.push({ kind: "cite", id: m[1] });
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ kind: "text", text: line.slice(last) });
  return out;
}

/** The editable text of a section: paragraphs, then bullets as "- " lines (the API's PATCH format). */
export function sectionText(s: Pick<DraftSection, "paragraphs" | "bullets">): string {
  return [...s.paragraphs, ...s.bullets.map((b) => `- ${b}`)].join("\n");
}

/** The inverse of sectionText (what the API will store). */
export function parseSectionText(text: string): { paragraphs: string[]; bullets: string[] } {
  const paragraphs: string[] = [];
  const bullets: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (/^[-*•]\s+/.test(line)) bullets.push(line.replace(/^[-*•]\s+/, ""));
    else paragraphs.push(line);
  }
  return { paragraphs, bullets };
}

export type Tone = "positive" | "warning" | "negative";

/** Green at or above the house band's mean, amber within the band, red below it. */
export function scoreTone(score: number, band: Band): Tone {
  if (band.n === 0) return "positive";
  if (score < band.low) return "negative";
  if (band.mean !== null && score >= band.mean) return "positive";
  return score >= band.low ? "warning" : "negative";
}

export function sectionTone(score: number | undefined): Tone {
  if (score === undefined) return "warning";
  return score >= 75 ? "positive" : score >= 55 ? "warning" : "negative";
}

const SEGMENT: Record<string, string> = { contractor: "contractor", trader: "trader", real_estate: "real estate", corporate: "corporate", "*": "all" };
const KIND: Record<string, string> = { new: "new", renewal: "renewal", increase: "increase", "*": "all types" };

/** "UAE house (anonymised) · increase · contractor" from the profile group "house-uae|increase|contractor". */
export function profileLabel(d: Pick<Draft, "profile">): string {
  const [, kind, seg] = d.profile.group.split("|");
  return [d.profile.bank_label, KIND[kind] ?? kind, SEGMENT[seg] ?? seg].join(" · ");
}

/** Lint grouped by section key, majors first. */
export function lintBySection(lint: Lint[]): Record<string, Lint[]> {
  const out: Record<string, Lint[]> = {};
  const rank = { major: 0, minor: 1, info: 2 } as const;
  for (const l of [...lint].sort((a, b) => rank[a.severity] - rank[b.severity])) (out[l.section] ??= []).push(l);
  return out;
}

/** The answer line: what was drafted, how close to the house, what to do next. */
export function answerLine(d: Draft): string {
  const n = d.sections.length;
  const accepted = d.sections.filter((s) => s.status === "accepted").length;
  const judgement = d.sections.filter((s) => s.judgement && s.status !== "accepted").length;
  const sc = d.score;
  const band = sc.band.n ? ` (house band ${fmt1(sc.band.low)}–${fmt1(sc.band.high)})` : "";
  const verdict = sc.within_band ? "reads like the house" : "below the house band";
  const lints = d.lint.length ? `; ${d.lint.length} point${d.lint.length === 1 ? "" : "s"} differ${d.lint.length === 1 ? "s" : ""} from house style` : "";
  const todo = judgement ? `; ${judgement} judgement section${judgement === 1 ? "" : "s"} for the RM` : "";
  return `${n} sections drafted from data, ${verdict}: style score ${fmt1(sc.total)}${band}${lints}${todo}. ${accepted} of ${n} accepted.`;
}

export function fmt1(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** How a section was drafted, in words. */
export function methodLabel(m: string): string {
  if (m === "model") return "Model, figures checked";
  if (m === "RM edit") return "Edited by the RM";
  if (m.startsWith("template")) return "House template";
  return m;
}

/** Facts cited in a section, in citation order. */
export function citedFacts(s: DraftSection): Fact[] {
  const order: string[] = [];
  for (const line of [...s.paragraphs, ...s.bullets]) for (const seg of splitCitations(line)) if (seg.kind === "cite" && !order.includes(seg.id)) order.push(seg.id);
  for (const id of s.table?.cites ?? []) if (!order.includes(id)) order.push(id);
  const by = new Map(s.citations.map((f) => [f.id, f]));
  return order.map((id) => by.get(id)).filter((f): f is Fact => Boolean(f));
}

/** "AED 212.4m · 12.5% · 1.25x · British spelling": the house number format in one line. */
export function numberFormatLine(n: ProfileView["profile"]["numbers"], ccy: string, spelling: string): string {
  const unit = n.unit === "million" ? " million" : n.unit === "none" ? "m" : n.unit;
  const pct = n.percent === "per cent" ? "12.5 per cent" : "12.5%";
  return `${ccy} 212.4${unit}${n.trim_integers ? ` (${ccy} 50${unit})` : ""} · ${pct} · 1.25${n.multiple === "times" ? " times" : "x"} · ${spelling} spelling`;
}

/** "11 words a sentence · no hedging · third person": the voice in one line. */
export function voiceLine(r: Rates | undefined): string {
  if (!r || r.sentence_words === null) return "Not enough prose to measure";
  const hedge = (r.hedges_per_100w ?? 0) < 0.3 ? "plain, unhedged" : `${r.hedges_per_100w} hedges per 100 words`;
  const person = (r.first_person_per_100w ?? 0) < 0.3 ? "third person" : "first person";
  return `${Math.round(r.sentence_words)} words a sentence · ${hedge} · ${person}`;
}

/** Replace one section in a draft immutably (optimistic UI after an edit). */
export function withSection(d: Draft, s: DraftSection): Draft {
  return { ...d, sections: d.sections.map((x) => (x.key === s.key ? s : x)) };
}
