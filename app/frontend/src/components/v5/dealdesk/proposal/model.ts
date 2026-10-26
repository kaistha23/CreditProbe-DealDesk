/**
 * R14 session p: types, URLs and pure helpers for the bank-form credit proposal preview (K26/K27, D15), the proposal check
 * (K31, D1) and the batch check (K33, D2). The backend is backend/dealdesk/house_style/papers_api.py (credit-proposal) and
 * backend/dealdesk/proposal_check/api.py; no figure is computed here.
 */

export type Block =
  | { t: "p"; text: string; exempt?: boolean }
  | { t: "h"; text: string }
  | { t: "bullets" | "numbered"; items: string[] }
  | { t: "table"; header: string[]; rows: (string | number)[][]; source?: string }
  | { t: "kv"; pairs: [string, string][]; cols?: number }
  | { t: "sign"; rows: [string, string][] }
  | { t: "box"; title: string; lines?: number };

export interface ProposalSection {
  key: string; n: number | null; heading: string; voice: "business" | "credit" | "form"; part: string; blocks: Block[]; gaps: string[];
  sources?: string[];
}

export interface CreditProposal {
  proposal_id: string; customer: string; as_of_label: string; sector: string; rating: string; currency: string;
  totals: { existing: number; outstanding: number; proposed: number };
  sections: ProposalSection[]; coverage: string[]; voice: string[]; gaps: { section: string; heading: string; missing: string[] }[];
  header_line: [string, string][];
  feed: null | { structure: { key: string; label: string; source: string; default_note?: string }; raroc: number | null; hurdle: number | null;
                 sva: number | null; basis: string | null; approval: string | null; approval_rule: string | null; capacity: number | null;
                 stress_proofed_to: string | null; regime: string | null };
  pages: { sections: Record<string, number>; total: number };
  parts: { key: string; title: string; subtitle: string; sections: string[] }[];
  links: { docx: string; pdf: string; json: string };
  plain_words: string[];
}

export interface CheckFinding {
  n: number; check: string; category: string; severity: "critical" | "major" | "minor" | "info"; result: "defect" | "observation" | "pass";
  defect_type: string; section_key: string; title: string; claim: string; evidence: string; evidence_relation: string; evidence_key: string; query: string;
}

export interface CheckSection { key: string; n: number; heading: string; present: boolean; applicable: boolean; score: number; defects: number; observations: number; critical: number; words: number }

/** R15 b (L10): the detail behind one section row. */
export interface SectionDetail {
  requires: string; quote: string[]; quote_more: number; why: string; queries: string[]; not_applicable: string | null; draft_from_data: boolean;
  checks: { check: string; result: "defect" | "observation" | "pass"; severity: string; title: string; evidence: string; source: string; key: string }[];
}

/** R15 b (L11): the one-page brief of all issues for the RM, and the RM's document with the comments anchored. */
export interface RmBrief { to: string; subject: string; due: string; count: number; critical: number; text: string;
  groups: { severity: string; label: string; items: { n: number; section: number; heading: string; title: string; query: string; evidence: string; source: string; due: string }[] }[] }
export interface DocSection { key: string; n: number; heading: string; paras: string[]; tables: string[][][];
  comments: { severity: string; result: string; title: string; claim: string; query: string; evidence: string }[] }

export interface CheckResult {
  brief?: RmBrief; document_view?: DocSection[];
  section_detail?: { summary: string; sections: Record<string, SectionDetail> };
  proposal_id: string; run_id: string; document: string; document_kind: "docx" | "record"; customer: string; rm: string; branch: string; sector: string;
  status: string; score: number; grade: string; sections: CheckSection[]; sections_present: number; defects: CheckFinding[]; observations: CheckFinding[];
  critical: number; by_category: Record<string, number>; queries: { n: number; section: number; heading: string; severity: string; title: string; query: string; check: string; defect_type: string }[];
  as_of: string; method: string; elapsed_s: number; headline: string; passes_n: number; checks_n: number;
  sent: { run_id: string; to: string; at: string; queries: unknown[] }[]; links: { annotated: string; queries: string };
}

export interface BatchRow {
  rank: number; proposal_id: string; customer: string; rm: string; branch: string; sector: string; status: string; document: string; document_kind: string;
  score: number; grade: string; defects: number; critical: number; undisclosed: number; contradicted: number; queries_open: number; sections_present: number;
  top_defect: string; previous_score: number | null; score_changed: boolean; headline: string;
}

export interface BatchResult {
  summary: { pending: number; checked: number; errors: number; average_score: number | null; critical: number; with_critical: number; queries_open: number;
             changed: number; elapsed_s: number; method: string };
  table: BatchRow[]; rm: { rm: string; proposals: number; average_score: number; critical: number; queries_open: number; recurring: [string, number][]; deals: string[] }[];
  errors: { proposal_id: string; error: string }[]; filters: { rm: string[]; branch: string[]; sector: string[] };
}

const API = "/api/v1/dealdesk";
const enc = encodeURIComponent;

export const proposalUrls = (pid: string, structure?: string | null) => {
  const q = structure ? `?structure=${enc(structure)}` : "";
  return {
    prepare: `${API}/proposals/${enc(pid)}/credit-proposal${q}`,
    docx: `${API}/proposals/${enc(pid)}/bank-form.docx${q}`,
    pdf: `${API}/proposals/${enc(pid)}/bank-form.pdf${q}`,
  };
};

export const checkUrls = (pid: string) => ({
  run: `${API}/proposals/${enc(pid)}/proposal-check`,
  demo: (which: "half" | "corrected") => `${API}/proposals/${enc(pid)}/proposal-check?demo=${which}`,
  /** R15 b (L7): check the submission record when no RM paper is on file. */
  record: `${API}/proposals/${enc(pid)}/proposal-check?use=record`,
  annotated: `${API}/proposals/${enc(pid)}/proposal-check/annotated.docx`,
  queries: `${API}/proposals/${enc(pid)}/proposal-check/queries.docx`,
  sendBack: `${API}/proposals/${enc(pid)}/proposal-check/send-back`,
});

export const CHECK_API = {
  upload: (pid?: string) => `${API}/proposal-check/upload${pid ? `?proposal_id=${enc(pid)}` : ""}`,
  demo: `${API}/proposal-check/demo`,
  demoFile: (name: string) => `${API}/proposal-check/demo/${enc(name)}`,
  batch: `${API}/proposal-check/batch`,
  batchXlsx: `${API}/proposal-check/batch.xlsx`,
  sendAll: (rm: string) => `${API}/proposal-check/batch/send-all?rm=${enc(rm)}`,
};

/** One preview page card: the sections that start on that page of the Word/PDF layout. */
export interface PageCard { page: number; to: number; sections: ProposalSection[]; landscape: boolean; part?: { title: string; subtitle: string } }

/** Group the sections into page cards by the page each starts on (the backend's page map), in order. A section keeps its
 *  own page; pages with no section start (continuations) are folded into the previous card. */
export function pageCards(p: Pick<CreditProposal, "sections" | "pages" | "parts">): PageCard[] {
  const firstOf = new Map<string, { title: string; subtitle: string }>();
  for (const part of p.parts ?? []) if (part.sections.length) firstOf.set(part.sections[0], { title: part.title, subtitle: part.subtitle });
  const order = new Map<string, number>();
  (p.parts ?? []).forEach((part, i) => part.sections.forEach((k, j) => order.set(k, i * 100 + j)));
  const secs = [...p.sections].sort((a, b) => (a.key === "header" ? -1 : b.key === "header" ? 1 : (order.get(a.key) ?? 9999) - (order.get(b.key) ?? 9999)));
  const cards: PageCard[] = [];
  for (const s of secs) {
    const page = p.pages?.sections?.[s.key] ?? (cards.at(-1)?.page ?? 1);
    let c = cards.at(-1);
    if (!c || c.page !== page) {
      c = { page, to: page, sections: [], landscape: s.key === "facilities" };
      cards.push(c);
    }
    c.sections.push(s);
    const part = firstOf.get(s.key);
    if (part && !c.part) c.part = part;
  }
  cards.forEach((c, i) => { c.to = i + 1 < cards.length ? Math.max(c.page, cards[i + 1].page - 1) : Math.max(c.page, p.pages?.total ?? c.page); });
  return cards;
}

/** "Business" / "Credit division" / "CreditProbe" / "Form" for a section. */
export function voiceOf(s: Pick<ProposalSection, "voice" | "part">): string {
  if (s.part === "creditprobe") return "CreditProbe";
  return s.voice === "business" ? "Business" : s.voice === "credit" ? "Credit division" : "Form";
}

/** Text runs with **bold** and __bold underlined__ (key concerns). */
export function richRuns(text: string): { text: string; bold: boolean; underline: boolean }[] {
  const out: { text: string; bold: boolean; underline: boolean }[] = [];
  for (const chunk of String(text).split(/(\*\*.+?\*\*|__.+?__)/g)) {
    if (!chunk) continue;
    if (chunk.length > 4 && chunk.startsWith("**") && chunk.endsWith("**")) out.push({ text: chunk.slice(2, -2), bold: true, underline: false });
    else if (chunk.length > 4 && chunk.startsWith("__") && chunk.endsWith("__")) out.push({ text: chunk.slice(2, -2).replace(/\*\*/g, ""), bold: true, underline: true });
    else out.push({ text: chunk, bold: false, underline: false });
  }
  return out;
}

export const pct = (x: number | null | undefined, dp = 1) => (x == null ? "–" : `${(x * 100).toFixed(dp)}%`);

/** The section number shown in the preview: 1–20 for the anatomy, CP1.. for CreditProbe's sections (as in the Word). */
export function sectionLabel(sections: Pick<ProposalSection, "key" | "n">[], key: string): string {
  let cp = 0;
  for (const s of sections) {
    if (!s.n) cp += 1;
    if (s.key === key) return s.n ? `${s.n}.` : `CP${cp}.`;
  }
  return "";
}

// ---------------------------------------------------------------- proposal check

export const SEVERITY_TONE: Record<string, "negative" | "warning" | "neutral" | "accent"> = { critical: "negative", major: "warning", minor: "neutral", info: "accent" };
export const CATEGORY_LABEL: Record<string, string> = {
  completeness: "Completeness", accuracy: "Accuracy", consistency: "Consistency", disclosure: "Disclosure", voice: "Voice", policy: "Policy and T&C",
};

export function scoreTone(score: number): "positive" | "warning" | "negative" {
  return score >= 85 ? "positive" : score >= 60 ? "warning" : "negative";
}

/** The check's plain-words lines (≤ 4, with numbers), from the result only. */
export function checkPlainWords(r: Pick<CheckResult, "customer" | "score" | "grade" | "defects" | "critical" | "sections_present" | "queries" | "rm">): string[] {
  const contradicted = r.defects.filter((d) => d.title.startsWith("RM claim contradicted")).length;
  const undisclosed = r.defects.filter((d) => d.category === "disclosure").length;
  return [
    `This grades the RM's paper, not the deal: ${r.customer} scores ${Math.round(r.score)} of 100 (grade ${r.grade}).`,
    r.defects.length ? `${r.defects.length} defects: ${r.critical} critical, ${contradicted} claims the bank's data contradicts, ${undisclosed} facts not disclosed.`
      : "No defect found: every claim checked agrees with the bank's data.",
    `${r.sections_present} of 20 bank-form sections are present.`,
    r.queries.length ? `Send the ${r.queries.length} queries back to ${r.rm || "the RM"} before the deal review.` : "The paper can go to review as it is.",
  ];
}

/** Batch filters (RM, branch, sector, minimum score). */
export function filterBatch(rows: BatchRow[], f: { rm?: string; branch?: string; sector?: string; maxScore?: number | null; criticalOnly?: boolean }): BatchRow[] {
  return rows.filter((r) => (!f.rm || r.rm === f.rm) && (!f.branch || r.branch === f.branch) && (!f.sector || r.sector === f.sector)
    && (f.maxScore == null || r.score <= f.maxScore) && (!f.criticalOnly || r.critical > 0));
}

/** R15 b (L12): how long the writer may take before the wait stops with a reason (a cold first run is 10–90 s in the cloud). */
export const PROPOSAL_TIMEOUT_MS = 180_000;
export const proposalTimeoutText = (ms: number) =>
  `it took longer than ${Math.round(ms / 1000)} seconds, so the wait was stopped. The deal file may still be loading on the server; try again in a moment.`;
/** The waiting line names what the writer is doing (one deterministic pass: deal file, structure, then the 20 sections). */
export function writingLine(seconds: number): string {
  if (seconds < 5) return "Reading the deal file and the selected structure…";
  if (seconds < 20) return "Writing the 20 bank-form sections from the deal file…";
  return "Still writing: the first proposal of the day computes the structures and stress results it quotes…";
}


/** R15 b (L7): the state of a deal with no RM proposal on file: the plain message and its three actions. */
export function noProposalState(renewal: boolean): { title: string; line: string; actions: { key: "upload" | "record" | "draft"; label: string }[] } {
  const what = renewal ? "this renewal" : "this deal";
  return {
    title: `No RM proposal on file for ${what} yet`,
    line: "Nothing to check until the RM's paper arrives. Upload it, check the submission record the desk holds, or draft the "
      + (renewal ? "renewal proposal from data (bank form: last year's file and what changed)." : "proposal from data (bank form)."),
    actions: [
      { key: "upload", label: "Upload the RM's proposal (Word)" },
      { key: "record", label: "Use the submission record" },
      { key: "draft", label: renewal ? "Draft the renewal proposal from data" : "Draft the proposal from data" },
    ],
  };
}

/** R15 b (L11): the brief as Mail HTML (paragraphs; the server sanitises it again). */
export function briefHtml(text: string): string {
  const esc = (x: string) => x.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return text.split(/\n{2,}/).map((block) => `<p>${block.split("\n").map((l) => esc(l.trim())).join("<br>")}</p>`).join("");
}

/** The Mail user for the RM named on the proposal (exact name, then surname), or null. */
export function matchUser<T extends { name: string; username: string }>(rm: string, users: T[]): T | null {
  const n = rm.trim().toLowerCase();
  if (!n) return null;
  const exact = users.find((u) => u.name.toLowerCase() === n || u.username.toLowerCase() === n);
  if (exact) return exact;
  const last = n.split(/\s+/).pop() ?? "";
  const hits = users.filter((u) => u.name.toLowerCase().split(/\s+/).pop() === last);
  return hits.length === 1 ? hits[0] : null;
}
