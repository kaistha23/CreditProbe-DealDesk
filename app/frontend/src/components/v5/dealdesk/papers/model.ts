/**
 * PLAN_R12 Session F: types and pure helpers for the papers dialogs (bank-form credit proposal, committee paper, summary memo).
 * The backend is backend/dealdesk/house_style/papers_api.py; no figure is computed here.
 */

export type Block =
  | { t: "p"; text: string; exempt?: boolean }
  | { t: "h"; text: string }
  | { t: "bullets" | "numbered"; items: string[] }
  | { t: "table"; header: string[]; rows: (string | number)[][]; source?: string }
  | { t: "kv"; pairs: [string, string][]; cols?: number }
  | { t: "sign"; rows: [string, string][] }
  | { t: "box"; title: string; lines?: number };

export interface PaperSection {
  key: string; n: number | null; heading: string; voice: "business" | "credit" | "form"; part: string;
  blocks: Block[]; gaps: string[]; contract_met?: boolean; method?: string; sources?: string[];
}

export interface Paper {
  proposal_id: string; title: string; customer: string; group: string; currency: string; as_of_label: string;
  request_kind: string; rating: string; sector: string;
  totals: { existing: number; outstanding: number; proposed: number };
  sections: PaperSection[]; coverage: string[]; voice: string[];
  density: { sentences: number; failing: number; share_ok: number };
  gaps: { section: string; heading: string; missing: string[] }[]; methods: string[];
}

export interface CommitteePaper {
  proposal_id: string; summary: PaperSection[]; paper: Paper; density: string[]; approval_authority: string;
  coverage: string[]; voice: string[]; gaps: Paper["gaps"];
}

export const PAPERS = "/api/v1/dealdesk";
const enc = encodeURIComponent;

export const paperUrls = (pid: string) => ({
  bankForm: `${PAPERS}/proposals/${enc(pid)}/bank-form`,
  bankFormDocx: `${PAPERS}/proposals/${enc(pid)}/bank-form.docx`,
  bankFormPdf: `${PAPERS}/proposals/${enc(pid)}/bank-form.pdf`,
  committee: `${PAPERS}/proposals/${enc(pid)}/committee-paper`,
  committeeDocx: `${PAPERS}/proposals/${enc(pid)}/committee-paper.docx`,
  committeePdf: `${PAPERS}/proposals/${enc(pid)}/committee-paper.pdf`,
  summaryMemo: `${PAPERS}/proposals/${enc(pid)}/draft`,
  summaryMemoDocx: (draftId: string) => `${PAPERS}/drafts/${enc(draftId)}/docx`,
});

/** The voice label shown beside a section heading: who speaks in it. */
export function voiceLabel(s: Pick<PaperSection, "voice" | "part">): string {
  if (s.part === "creditprobe") return "CreditProbe";
  if (s.voice === "business") return "Business";
  if (s.voice === "credit") return "Credit";
  return "Form";
}

/** One line for the paper's checks: coverage, voice and data gaps. */
export function checksLine(p: Pick<Paper, "coverage" | "voice" | "gaps" | "sections">): { tone: "positive" | "warning"; text: string } {
  const n = p.sections.length;
  if (p.coverage.length) return { tone: "warning", text: `${p.coverage.length} section(s) missing of ${n}` };
  const gaps = p.gaps.length;
  const voice = p.voice.length;
  const parts = [`All ${n} sections`, voice ? `${voice} sentence(s) off the house voice` : "every sentence in the house voice"];
  if (gaps) parts.push(`${gaps} section(s) with data not available`);
  return { tone: voice || gaps ? "warning" : "positive", text: parts.join(" · ") };
}

/** Bold runs marked **like this** split into [text, bold] pairs. */
export function boldRuns(text: string): [string, boolean][] {
  return String(text).split("**").map((chunk, i) => [chunk, i % 2 === 1] as [string, boolean]).filter(([c]) => c !== "");
}

export function sectionNumber(i: number, numbered = true): string {
  return numbered ? `${i + 1}. ` : "";
}
