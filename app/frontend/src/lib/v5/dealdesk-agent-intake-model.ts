/**
 * Round A: the agentic intake (the Credit Request Agent on every new proposal). Types and pure helpers, no imports, so
 * node --test runs them: the run's shape, the completeness meter ("20% → 35% (+15)"), the step tones and timings, and a
 * small markdown reader for the drafted business request (headings, paragraphs, bullets, tables, **bold**, citations
 * [D3] / [RM] / [Ask], "[figure removed]", and the system's completeness line and could-not-assess block).
 */

export type StepStatus = "pending" | "running" | "done" | "warn" | "failed";
export interface AgentStep { key: "read" | "check" | "draft"; title: string; status: StepStatus; detail: string; ms: number | null; started_at: string | null }
export interface KeyFigure { label: string; value: string; page?: number | null; source?: "model" | "rule" | "both" }
export interface IntakeRecord {
  doc_type: string; checklist_ids: string[]; entity: string | null; period_or_date: string | null; expiry_date: string | null;
  summary: string; key_figures: KeyFigure[]; observations: string[];
}
export interface Recon {
  status: "confirmed" | "offered" | "flagged" | "rule"; label: string; notes: string[]; confirmed: number;
  offered: KeyFigure[]; rejected: (KeyFigure & { why: string })[]; rule_ids?: string[]; model_ids?: string[];
}
export interface AgentDoc {
  id: string; name: string; files: string[]; kind: string; method: string; status: "reading" | "read" | "failed"; new: boolean; error: string;
  result: IntakeRecord | null; recon: Recon | null; r16_doc_id: string; r16_type: string; model_error?: string;
}
export interface Gap { sec: string; item: string; cannot: string; w: number; crit: boolean; because: string; blocking: string[]; partial: boolean }
export interface CheckLine { id: string; label: string; status: "received" | "missing" | "expired"; docs: string[]; note: string }
export interface AgentCheck {
  received: string[]; missing: string[]; expired: string[]; total: number; lines: CheckLine[];
  comp: { pct: number; gaps: Gap[]; crit: number };
  prev_pct: number | null; delta_pts: number | null; prev_crit: number | null;
  now_covered: { item: string; cannot: string; in_part: boolean; text: string }[];
}
export interface Rejected { line: number; figure: string; cited: string[]; text: string }
export interface AgentDraft {
  text: string; md: string; source: "model" | "deterministic" | ""; status: "pending" | "streaming" | "done"; words: number;
  rejected: Rejected[]; versions: { n: number; at: string; instruction: string; source: string; words: number; by?: string }[];
  model_error?: string; revise_error?: string;
}
export interface AgentRun {
  run_id: string; parent_run_id: string; intake_id: string; proposal_id: string; created_at: string; created_by: string;
  status: "queued" | "running" | "revising" | "done" | "failed"; error: string; as_of: string; market: "KSA" | "UAE" | "";
  ask: string; notes: string; rm: string; customer: string; cr: string; existing: boolean; request_type: string;
  model: { model_available: boolean; provider: string | null; model: string | null };
  steps: AgentStep[]; documents: AgentDoc[]; skipped: string[]; check: AgentCheck | null; draft: AgentDraft;
  bank: { existing?: boolean; how?: string; proposal_id?: string; cif?: string; name?: string };
  elapsed_ms: number | null; model_summary: { calls: number; input_tokens: number; output_tokens: number; ms: number };
}
export interface SampleManifest {
  customer: string; market: string; request_type: string; relationship: string; rm: string; ask: string; notes: string; note: string;
  documents: { name: string; kind: string; bytes: number }[];
}
export interface AgentOverview {
  model: AgentRun["model"]; checklists: Record<string, { id: string; label: string }[]>; accepted: string[]; sample: SampleManifest | null;
}

export const ACCEPT = ".zip,.pdf,.docx,.xlsx,.xlsm,.xls,.csv,.txt,.md,.png,.jpg,.jpeg,.webp,.tif,.tiff";
const ACCEPT_RX = /\.(zip|pdf|docx|xlsx|xlsm|xls|csv|txt|md|png|jpe?g|webp|tiff?)$/i;

export const isAccepted = (name: string): boolean => ACCEPT_RX.test(name);
export const isLive = (r: Pick<AgentRun, "status"> | null | undefined): boolean => !!r && ["queued", "running", "revising"].includes(r.status);

/** Files dropped again (same name and size) are not added twice. */
export function mergeFiles<T extends { name: string; size: number }>(have: T[], add: T[]): { files: T[]; dup: number } {
  const key = (f: T) => `${f.name}\u0000${f.size}`;
  const seen = new Set(have.map(key));
  const out = [...have];
  let dup = 0;
  for (const f of add) {
    if (seen.has(key(f))) { dup++; continue; }
    seen.add(key(f)); out.push(f);
  }
  return { files: out, dup };
}

export function secs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  return `${(ms / 1000).toFixed(1)}s`;
}

export const STEP_TONE: Record<StepStatus, "neutral" | "accent" | "positive" | "warning" | "negative"> = {
  pending: "neutral", running: "accent", done: "positive", warn: "warning", failed: "negative",
};

/** The completeness meter: "Completeness 20% → 35% (+15)", the bar's colour band, and the critical count before → after. */
export function meter(c: AgentCheck): { title: string; pct: number; prev: number | null; delta: number | null; band: "hi" | "mid" | "lo"; crit: string } {
  const pct = c.comp.pct;
  const d = c.prev_pct !== null && c.delta_pts ? c.delta_pts : null;
  const title = d !== null ? `Completeness ${c.prev_pct}% → ${pct}% (${d > 0 ? "+" : ""}${d})` : `Completeness ${pct}%`;
  const n = c.comp.crit;
  const crit = `${c.prev_crit !== null && c.prev_crit !== n ? `${c.prev_crit} → ` : ""}${n} critical gap${n === 1 ? "" : "s"}`;
  return { title, pct, prev: d !== null ? c.prev_pct : null, delta: d, band: pct >= 85 ? "hi" : pct >= 60 ? "mid" : "lo", crit };
}

export const isCritical = (g: Gap): boolean => g.crit && !g.partial;

/** One line of "What I cannot assess with this file": the analysis, why (the blocking document), the section. */
export function gapLine(g: Gap): string {
  return `${isCritical(g) ? "Critical: " : ""}${g.cannot}${g.partial ? " (only in part)" : ""} — ${g.because}. [Section ${g.sec}]`;
}

/** Per reconciliation status: the chip's tone and words. */
export const RECON: Record<Recon["status"], { tone: "positive" | "accent" | "warning" | "neutral"; label: string }> = {
  confirmed: { tone: "positive", label: "Confirmed" }, offered: { tone: "accent", label: "Model found more" },
  flagged: { tone: "warning", label: "Flagged" }, rule: { tone: "neutral", label: "Rule reader" },
};

export function readCounts(docs: AgentDoc[]): Record<Recon["status"] | "failed", number> {
  const out = { confirmed: 0, offered: 0, flagged: 0, rule: 0, failed: 0 };
  for (const d of docs) {
    if (d.status === "failed") out.failed++;
    else if (d.recon) out[d.recon.status]++;
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ the paper
export type Seg = { t: "text" | "bold" | "cite" | "removed"; text: string };
export type MdBlock =
  | { t: "h1"; text: string }
  | { t: "h2"; text: string; gaps: boolean }
  | { t: "h3"; text: string }
  | { t: "p"; text: string; completeness: boolean; inGaps: boolean }
  | { t: "ul"; items: string[]; inGaps: boolean }
  | { t: "table"; header: string[]; rows: string[][]; inGaps: boolean };

const SEG_RX = /(\*\*[^*]+\*\*|\[(?:D\d+|RM|Ask)(?:\s*,\s*(?:D\d+|RM|Ask))*\]|\[figure removed\])/g;

export function inline(text: string): Seg[] {
  const out: Seg[] = [];
  for (const part of text.split(SEG_RX)) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**")) out.push({ t: "bold", text: part.slice(2, -2) });
    else if (part === "[figure removed]") out.push({ t: "removed", text: part });
    else if (/^\[(?:D\d+|RM|Ask)/.test(part)) out.push({ t: "cite", text: part });
    else out.push({ t: "text", text: part });
  }
  return out;
}

const cells = (line: string): string[] => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export function parseMd(md: string): MdBlock[] {
  const src = md.replace(/^```(?:markdown|md)?\s*/i, "").replace(/```\s*$/, "").split(/\r?\n/);
  const out: MdBlock[] = [];
  let inGaps = false;
  let i = 0;
  while (i < src.length) {
    const ln = src[i];
    if (!ln.trim()) { i++; continue; }
    if (ln.startsWith("# ")) { out.push({ t: "h1", text: ln.slice(2).trim() }); i++; continue; }
    if (ln.startsWith("## ")) {
      const text = ln.slice(3).trim();
      inGaps = /could not assess/i.test(text);
      out.push({ t: "h2", text, gaps: inGaps }); i++; continue;
    }
    if (ln.startsWith("### ")) { out.push({ t: "h3", text: ln.slice(4).trim() }); i++; continue; }
    if (ln.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < src.length && src[i].trim().startsWith("|")) {
        if (!/^\|?\s*:?-{2,}/.test(src[i].trim())) rows.push(cells(src[i]));
        i++;
      }
      if (rows.length) out.push({ t: "table", header: rows[0], rows: rows.slice(1), inGaps });
      continue;
    }
    if (/^\s*[-*] /.test(ln)) {
      const items: string[] = [];
      while (i < src.length && /^\s*[-*] /.test(src[i])) { items.push(src[i].replace(/^\s*[-*] /, "").trim()); i++; }
      out.push({ t: "ul", items, inGaps }); continue;
    }
    const buf = [ln.trim()];
    i++;
    while (i < src.length && src[i].trim() && !/^(#|\||\s*[-*] )/.test(src[i])) { buf.push(src[i].trim()); i++; }
    const text = buf.join(" ");
    out.push({ t: "p", text, completeness: /^\*\*Completeness:/.test(text), inGaps });
  }
  return out;
}

/** Words in the paper (the 650-word rule), citations not counted. */
export function wordCount(md: string): number {
  const t = md.replace(/\[(?:D\d+|RM|Ask)(?:\s*,\s*(?:D\d+|RM|Ask))*\]/g, "").replace(/[#*|`-]+/g, " ");
  return (t.match(/\w[\w.,%/'’]*/g) ?? []).length;
}

/** "D3 · Audited financial statements FY2025" for a citation's tooltip. */
export function citeTitle(cite: string, docs: AgentDoc[]): string {
  const ids = cite.replace(/[[\]]/g, "").split(",").map((x) => x.trim());
  return ids.map((id) => (id === "RM" ? "RM notes" : id === "Ask" ? "The ask" : (() => {
    const d = docs.find((x) => x.id === id);
    return d ? `${id} · ${d.name}` : id;
  })())).join("; ");
}
