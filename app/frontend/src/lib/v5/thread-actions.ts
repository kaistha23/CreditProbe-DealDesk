/**
 * R16 t (M7): the shared thread actions on every answer in every module (pure; node --test covers it).
 *
 *   Share   link / CreditProbe Mail (object type "thread-answer", optionally with the Word memo attached)
 *   Trace   sources, queries, relations and rows of the answer (Core :8505 /api/v1/thread-actions/trace)
 *   Word    the house-style memo of this answer or the whole thread (/api/v1/thread-actions/memo)
 *   Add to report   the answer as Playbook blocks (Playbook /imports)
 *
 * and the "write a memo / note / paper" intent: typed in any thread it writes the Word document and offers the
 * download instead of replying in prose (`memoIntent`, `planMemo`; the same rule as backend/thread_actions/intent.py,
 * the same case list tests/v5/thread_actions/intent_cases.json).
 *
 * One document shape for every module (`ActionDoc`, backend/thread_actions/doc.py): the blocks are read from the
 * answer as the reader sees it (`domBlocks`, so every figure is as the thread showed it), the sources from the module's
 * own answer object (one extractor per module below).
 */

export type ModuleKey = "cockpit" | "noor" | "dealdesk" | "whatif" | "lenses" | "ews" | "b360" | "scorecard" | "playbook" | "intel" | "agents";

export const MODULE_LABEL: Record<ModuleKey, string> = {
  cockpit: "Cockpit", noor: "Noor", dealdesk: "Deal Desk", whatif: "What-If", lenses: "Lenses", ews: "Early Warning",
  b360: "Borrower 360", scorecard: "Scorecard Validation", playbook: "Playbook", intel: "Intelligence", agents: "Agents",
};

export type ActionBlock =
  | { kind: "text"; text: string }
  | { kind: "bullets"; items: string[]; title?: string }
  | { kind: "figures"; items: { label: string; value: string }[] }
  | { kind: "table"; title: string; columns: string[]; rows: (string | number)[][]; row_count?: number };

export interface ActionSource {
  kind: "relation" | "query" | "row" | "document" | "run" | "engine";
  label: string; relation?: string; domain?: string; sql?: string; keys?: Record<string, string>; period?: string;
  rows?: number; href?: string; status?: string; method?: string;
}
export interface ActionTurn { question: string; answer_id: string; blocks: ActionBlock[]; sources: ActionSource[] }
export interface ActionDoc { module: ModuleKey; thread_id: string; title: string; href: string; turns: ActionTurn[] }

// ------------------------------------------------------------------ the memo intent

const VERBS = String.raw`(?:write|prepare|draft|make|create|produce|compose|put\s+together|turn\s+(?:this|it|that)\s+into|give\s+me|send\s+me|generate|do|need|want)`;
const NOUN = String.raw`(memo(?:randum)?|briefing\s+note|credit\s+note|board\s+note|note|paper|committee\s+paper|board\s+paper|position\s+paper|word\s+(?:doc(?:ument)?|file|version|report)|docx)`;
const RX = new RegExp(String.raw`\b${VERBS}\b(?:\s+(?:me|us|up))?(?:\s+(?:a|an|the|this|that|it|one|my|our))?(?:\s+(?:as|in(?:to)?|into))?(?:\s+(?:a|an|the))?` +
  String.raw`(?:\s+(?:short|brief|quick|one[- ]page|formal|credit|risk|internal|full|detailed|summary|cro|board|committee|house[- ]style))*\s+${NOUN}\b`, "i");
const BARE = new RegExp(String.raw`^\s*(?:please\s+)?(?:a|an|the)?\s*(?:short\s+|brief\s+|quick\s+)?${NOUN}\s+(?:on|about|of|for|to|summari[sz]ing)\b`, "i");
const EXPORT = /\b(?:export|download|save)\b.{0,30}\b(?:as|to|in)\s+(?:a\s+)?(?:word|docx)\b/i;
const NOT = /^\s*(?:what|which|who|why|how|when|where|does|do|is|are|was|were|did|can\s+you\s+explain|explain|summari[sz]e\s+the)\b(?!.*\b(?:write|prepare|draft)\b)/i;
const ANSWER = /\b(?:this|that|the\s+last|the\s+above|above|previous|latest)\s+(?:answer|reply|response|result|table)\b/i;
const TO = /\b(?:to|for|addressed\s+to)\s+(?:the\s+)?(cro|cfo|ceo|cco|cio|board(?:\s+risk\s+committee)?|credit\s+committee|risk\s+committee|committee|head\s+of\s+credit|chief\s+risk\s+officer|management|alco|rm|relationship\s+manager)\b/i;
const REFERS = /^\s*(?:(?:on|about|of|for|summari[sz]ing|covering)\s+)?(?:this|that|it|the\s+above|above|the\s+thread|this\s+thread|the\s+conversation|this\s+conversation|the\s+answers?|these\s+answers|what\s+we\s+(?:found|discussed)|(?:this|that|the\s+last|the\s+above|above|previous|latest)\s+(?:answer|reply|response|result|table))\b[\s.!?]*$/i;
const LEAD = /^\s*(?:on|about|of|for|summari[sz]ing|covering|explaining|showing|setting\s+out|that\s+(?:shows|explains|sets\s+out))\s+/i;
const TAIL = /\b(?:as\s+(?:a\s+)?word(?:\s+document)?|in\s+word|in\s+house\s+style|please|thanks?(?:\s+you)?)\b[\s.!?]*$/i;

export type MemoKind = "memo" | "note" | "paper";
export interface MemoIntent { kind: MemoKind; scope: "thread" | "answer"; to: string; question: string | null; subject: string }

function kindOf(noun: string): MemoKind {
  const n = noun.toLowerCase().replace(/\s+/g, " ");
  if (n.startsWith("word") || n === "docx") return "memo";
  const last = n.split(" ").pop() ?? "";
  return last === "note" ? "note" : last === "paper" ? "paper" : "memo";
}

function addressee(raw: string): string {
  const r = raw.trim().replace(/\s+/g, " ").toLowerCase();
  const caps: Record<string, string> = { cro: "CRO", cfo: "CFO", ceo: "CEO", cco: "CCO", cio: "CIO", alco: "ALCO", rm: "RM", "chief risk officer": "CRO" };
  if (caps[r]) return caps[r];
  return r.split(" ").map((w) => (w === "of" ? w : w[0].toUpperCase() + w.slice(1))).join(" ");
}

/** null, or what document the text asks for (kind, scope, addressee, a question to ask first). */
export function memoIntent(text: string): MemoIntent | null {
  const t = String(text ?? "").trim();
  if (!t || t.length > 600) return null;
  const m = RX.exec(t) ?? BARE.exec(t);
  const exp = m ? null : EXPORT.exec(t);
  if (!m && !exp) return null;
  if (m && NOT.test(t) && !/^\s*(?:can|could|would|will)\s+you\b/i.test(t)) return null;
  const kind = m ? kindOf(m[1] ?? "memo") : "memo";
  const scope = ANSWER.test(t) ? "answer" : "thread";
  const toM = TO.exec(t);
  const to = toM ? addressee(toM[1] ?? "") : "";
  const end = m ? m.index + m[0].length : 0;
  let rest = m ? t.slice(end) : "";
  if (toM && toM.index >= end) rest = rest.replace(new RegExp(TO.source, "i"), " ");
  rest = rest.replace(TAIL, "").trim().replace(/^[\s,.;:-]+|[\s,.;:-]+$/g, "");
  let question: string | null = null;
  let subject = "";
  if (rest && !REFERS.test(rest)) {
    let body = rest.replace(LEAD, "").replace(/^[\s,.;:?-]+|[\s,.;:?-]+$/g, "");
    body = body.replace(/^(?:and\s+)?(?:the\s+)?(?:question\s+)?/i, "").trim();
    if (body.split(/\s+/).length >= 2) {
      question = body[0].toUpperCase() + body.slice(1);
      if (!question.endsWith("?") && /^(?:which|what|who|why|how|when|where|is|are|does|do|can|show|list|rank|compare)\b/i.test(body)) question += "?";
      subject = body;
    }
  }
  return { kind, scope, to, question, subject };
}

/** What a submitted text does in a thread with `answers` answers so far. */
export type MemoPlan =
  | { action: "none" }
  | { action: "write"; intent: MemoIntent }
  | { action: "ask-then-write"; intent: MemoIntent; question: string }
  | { action: "empty"; intent: MemoIntent; message: string };

export function planMemo(text: string, answers: number): MemoPlan {
  const intent = memoIntent(text);
  if (!intent) return { action: "none" };
  if (intent.question) return { action: "ask-then-write", intent, question: intent.question };
  if (answers < 1) {
    return { action: "empty", intent,
             message: `There is no answer in this thread to write up yet. Ask your question, then ask for the ${intent.kind}; or type it in one go, e.g. "write a ${intent.kind} on which proposals breach a hard limit".` };
  }
  return { action: "write", intent };
}

// ------------------------------------------------------------------ "say the word and I'll …" endings (M7: do it)

const OFFER = /(^|\n|[.!?]\s+)(?:say the word[^.!?\n]*|(?:do you |would you )?want me to [^.!?\n]*\?|shall i [^.!?\n]*\?|should i [^.!?\n]*\?|(?:just )?let me know if you(?:'d| would)? like[^.!?\n]*|if you(?:'d| would)? like,? i can[^.!?\n]*|i can (?:also )?(?:prepare|draft|write|turn this into) (?:a |the )?(?:memo|note|paper|word)[^.!?\n]*)[.!?]?\s*$/i;

/** The answer text without a closing offer ("Say the word and I'll prepare a memo."): the bar does it instead. */
export function withoutOfferEnding(text: string): string {
  let t = String(text ?? "");
  for (let i = 0; i < 3; i += 1) {
    const n = t.replace(OFFER, (_m, lead: string) => lead.trimEnd()).trimEnd();
    if (n === t.trimEnd()) break;
    t = n;
  }
  return t;
}

// ------------------------------------------------------------------ blocks from the rendered answer

/** The DOM surface `domBlocks` reads (an Element satisfies it; tests pass plain objects). */
export interface DomLike {
  tagName: string; children: ArrayLike<DomLike>; textContent: string | null;
  getAttribute(name: string): string | null;
  /** In a browser: every child node, text nodes included (nodeType 3), so buttons inside a line are left out. */
  childNodes?: ArrayLike<{ nodeType: number; nodeValue: string | null } | DomLike>;
}

const BLOCK_TAGS = new Set(["DIV", "P", "LI", "UL", "OL", "SECTION", "ARTICLE", "HEADER", "FOOTER", "H1", "H2", "H3", "H4", "H5", "H6", "TR", "TABLE", "DL", "DT", "DD", "BR", "BLOCKQUOTE", "PRE"]);

/** The visible words of an element: text nodes, minus buttons, traces and other controls; block children apart. */
function textOf(n: DomLike): string {
  const nodes = n.childNodes;
  if (!nodes) return clean(n.textContent);
  let out = "";
  for (const c of Array.from(nodes)) {
    if ((c as { nodeType: number }).nodeType === 3) { out += (c as { nodeValue: string | null }).nodeValue ?? ""; continue; }
    if ((c as { nodeType: number }).nodeType !== 1) continue;
    const e = c as DomLike;
    if (skip(e)) continue;
    const block = BLOCK_TAGS.has(e.tagName.toUpperCase());
    out += block ? ` ${textOf(e)} ` : textOf(e);
  }
  return clean(out);
}

const SKIP_TAGS = new Set(["BUTTON", "SVG", "NAV", "SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "FORM", "CANVAS", "IMG", "FIGCAPTION"]);
const clean = (s: string | null | undefined) => String(s ?? "").replace(/\s+/g, " ").trim();

function skip(n: DomLike): boolean {
  if (SKIP_TAGS.has(n.tagName.toUpperCase())) return true;
  if (n.getAttribute("data-no-doc") !== null || n.getAttribute("data-thread-actions") !== null) return true;
  if (n.getAttribute("aria-hidden") === "true" || n.getAttribute("role") === "dialog") return true;
  if (/(^|\s)sr-only(\s|$)/.test(n.getAttribute("class") ?? "")) return true;  // screen-reader copies repeat the answer
  const tid = n.getAttribute("data-testid") ?? "";
  return /(^|-)(speaker|trace|chips|composer|actions|action-bar|process)(-|$)/.test(tid) && !/^thread-turn/.test(tid);
}

function tableOf(n: DomLike, title: string): ActionBlock | null {
  const rows: string[][] = [];
  let header: string[] = [];
  const walk = (x: DomLike) => {
    const tag = x.tagName.toUpperCase();
    if (tag === "TR") {
      const cells = Array.from(x.children).filter((c) => ["TD", "TH"].includes(c.tagName.toUpperCase())).map((c) => textOf(c));
      const isHead = Array.from(x.children).every((c) => c.tagName.toUpperCase() === "TH");
      if (isHead && !header.length) header = cells; else if (cells.some(Boolean)) rows.push(cells);
      return;
    }
    Array.from(x.children).forEach(walk);
  };
  walk(n);
  if (!header.length && rows.length) header = rows.shift() as string[];
  if (!header.length) return null;
  return { kind: "table", title, columns: header.slice(0, 14), rows: rows.slice(0, 200).map((r) => r.slice(0, 14)), row_count: rows.length };
}

/** The answer as the reader sees it: paragraphs, headings, lists, key figures and tables, in order. */
export function domBlocks(root: DomLike | null): ActionBlock[] {
  const out: ActionBlock[] = [];
  if (!root) return out;
  let lastHeading = "";
  const push = (b: ActionBlock) => {
    const prev = out[out.length - 1];
    if (b.kind === "text" && prev?.kind === "text" && prev.text.length + b.text.length < 1500) { prev.text += `\n${b.text}`; return; }
    out.push(b);
  };
  const walk = (n: DomLike, isRoot = false) => {
    if (!isRoot && skip(n)) return;
    const tag = n.tagName.toUpperCase();
    if (tag === "TABLE") { const t = tableOf(n, lastHeading); if (t) out.push(t); lastHeading = ""; return; }
    if (/^H[1-6]$/.test(tag)) { const t = textOf(n); if (t) { lastHeading = t; push({ kind: "text", text: `### ${t}` }); } return; }
    if (tag === "UL" || tag === "OL") {
      const items = Array.from(n.children).filter((c) => c.tagName.toUpperCase() === "LI" && !skip(c)).map((c) => textOf(c)).filter(Boolean);
      if (items.length) out.push({ kind: "bullets", items });
      return;
    }
    if (tag === "DL") {
      const kids = Array.from(n.children);
      const items: { label: string; value: string }[] = [];
      for (let i = 0; i < kids.length; i += 1) {
        if (kids[i].tagName.toUpperCase() === "DT") items.push({ label: textOf(kids[i]), value: kids[i + 1] ? textOf(kids[i + 1]) : "" });
      }
      if (items.length) out.push({ kind: "figures", items: items.slice(0, 24) });
      return;
    }
    if (tag === "P" || tag === "LI" || tag === "BLOCKQUOTE" || tag === "PRE") { const t = textOf(n); if (t) push({ kind: "text", text: t }); return; }
    const kids = Array.from(n.children);
    if (!kids.length) {
      const t = textOf(n);
      if (t && t.length > 1) push({ kind: "text", text: t });
      return;
    }
    kids.forEach((k) => walk(k));
  };
  walk(root, true);
  // drop the closing offer from the last text block (M7: no "say the word and I'll …")
  for (let i = out.length - 1; i >= 0; i -= 1) {
    const b = out[i];
    if (b.kind === "text") { b.text = withoutOfferEnding(b.text); if (!b.text.trim()) out.splice(i, 1); break; }
  }
  return out.filter((b) => b.kind !== "text" || b.text.trim());
}

/** Blocks from a module's markdown when the answer is not on screen (earlier turns of a closed panel, tests). */
export function textBlocks(markdown: string): ActionBlock[] {
  const t = withoutOfferEnding(markdown).trim();
  return t ? [{ kind: "text", text: t }] : [];
}

/** A module table ({columns: [{key,label}], rows: [{...}]}) as a document table. */
export function keyedTable(title: string, columns: { key: string; label: string }[], rows: Record<string, unknown>[], rowCount?: number): ActionBlock {
  return { kind: "table", title, columns: columns.map((c) => c.label), row_count: rowCount ?? rows.length,
           rows: rows.slice(0, 200).map((r) => columns.map((c) => cell(r[c.key]))) };
}

function cell(v: unknown): string | number {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return Number.isFinite(v) ? v : "";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return typeof v === "object" ? JSON.stringify(v).slice(0, 200) : String(v);
}

// ------------------------------------------------------------------ sources, one extractor per module

export interface Evidence { artifact_id?: string; kind?: string; sql?: string | null; tool?: string | null; purpose?: string; row_count?: number }

/** Convo evidence (What-If, Lenses, Scorecard): the SQL that ran, with its row count. */
/** Data Domains relation names mentioned in a text (a trace step's detail, an engine note). */
export function relationsInText(text: string): string[] {
  const out: string[] = [];
  for (const m of String(text ?? "").matchAll(/\b(?:dd|corp|retail|b360|bureau|rel|gov|net|whatif|ta|ews|other_bank)_[a-z0-9_]{2,}\b/g)) if (!out.includes(m[0])) out.push(m[0]);
  return out.slice(0, 20);
}

/** The process trace drawn above an answer (understand, plan, query, …) as engine steps and the relations they name. */
export function traceSources(trace: { trace_id?: string; steps?: { label: string; detail?: string; state?: string }[] } | null | undefined): ActionSource[] {
  const out: ActionSource[] = [];
  for (const st of trace?.steps ?? []) {
    if (!st.detail) continue;
    out.push({ kind: "engine", label: `${st.label}: ${st.detail}`.slice(0, 200), status: st.state });
    for (const r of relationsInText(st.detail)) out.push({ kind: "relation", label: r, relation: r });
  }
  return out;
}

export function evidenceSources(evidence: Evidence[] | undefined | null): ActionSource[] {
  return (evidence ?? []).map((e) => (e.sql
    ? { kind: "query" as const, label: e.purpose || e.tool || "Query", sql: e.sql, rows: e.row_count }
    : { kind: "engine" as const, label: e.purpose || e.tool || e.kind || "Engine", rows: e.row_count, method: e.tool ?? undefined }));
}

const DEAL_ID = /^(?:DD|PL|R1\d|DN|DP)-[A-Z0-9-]+$/;

export function dealdeskSources(answer: { trace_ids?: string[]; validation?: { checked: number; untraced: string[]; passed: boolean }; source?: string; intent?: string;
                                          blocks?: readonly { type: string }[] } | null | undefined,
                                proposalId?: string | null): ActionSource[] {
  const out: ActionSource[] = [];
  const deals = new Set<string>(proposalId ? [proposalId] : []);
  // the deals a table names (its proposal column): each is a dd_deal row
  for (const raw of answer?.blocks ?? []) {
    const b = raw as unknown as { type: string; rows?: unknown[][]; keys?: string[] };
    if (b.type !== "table" || !b.rows) continue;
    const col = Math.max(0, (b.keys ?? []).indexOf("proposal_id"));
    for (const r of b.rows.slice(0, 40)) { const v = String(r?.[col] ?? "").trim(); if (DEAL_ID.test(v)) deals.add(v); }
  }
  for (const d of [...deals].slice(0, 20)) out.push({ kind: "row", label: `Deal ${d}`, relation: "dd_deal", domain: "deal_desk", keys: { proposal_id: d } });
  if (answer?.validation?.checked) {
    out.push({ kind: "engine", label: `${answer.validation.checked} figures checked against Data Domains` + (answer.validation.passed ? "" : `, ${answer.validation.untraced.length} not traced`),
               status: answer.validation.passed ? "traced" : "partly traced", method: answer.intent });
  }
  for (const id of (answer?.trace_ids ?? []).slice(0, 20)) out.push({ kind: "run", label: `Engine run ${id}`, method: answer?.source });
  return out;
}

export function whatifSources(answer: { evidence?: Evidence[]; blocks?: readonly { type: string }[] } | null | undefined): ActionSource[] {
  const out = evidenceSources(answer?.evidence);
  for (const raw of answer?.blocks ?? []) {
    const b = raw as unknown as Record<string, unknown> & { type: string };
    if (b.type === "scenario_set") {
      for (const r of (b.relations as string[] | undefined) ?? []) out.push({ kind: "relation", label: r, relation: r, period: String(b.as_of ?? "") });
      if (b.engine_version) out.push({ kind: "engine", label: `Scenario engine ${b.engine_version}`, method: String(b.fingerprint ?? "") });
    }
    if (b.type === "result") {
      const r = b.result as { domain?: string; period?: string } | undefined;
      if (r?.domain) out.push({ kind: "relation", label: `What-If ${r.domain} book`, domain: "what_if", relation: `${r.domain}_borrower_quarter`, period: r.period });
    }
  }
  return out;
}

export function convoSources(answer: { evidence?: Evidence[] } | null | undefined): ActionSource[] {
  return evidenceSources(answer?.evidence);
}

export function scorecardSources(answer: { evidence?: Evidence[]; blocks?: readonly { type: string }[] } | null | undefined, scorecardId?: string | null): ActionSource[] {
  const out = evidenceSources(answer?.evidence);
  const v = (answer?.blocks ?? []).find((b) => b.type === "validation" || b.type === "report") as Record<string, unknown> | undefined;
  if (v?.validation_id) out.push({ kind: "run", label: `Validation ${String(v.validation_id)}`, domain: "scorecard", keys: { validation_id: String(v.validation_id) } });
  if (scorecardId) out.push({ kind: "row", label: `Scorecard ${scorecardId}`, domain: "scorecard", keys: { scorecard_id: scorecardId } });
  return out;
}

export function playbookSources(actions: { citations?: { kind: string; label: string; href?: string; doc_id?: string }[]; source?: string }[] | undefined): ActionSource[] {
  const out: ActionSource[] = [];
  for (const a of actions ?? []) {
    for (const c of a.citations ?? []) out.push({ kind: "document", label: c.label, href: c.href, keys: c.doc_id ? { doc_id: c.doc_id } : undefined });
    if (a.source && !out.some((s) => s.label === a.source)) out.push({ kind: "engine", label: a.source });
  }
  return out;
}

export function noorSources(trace: { domain: string; relation: string; keys: Record<string, unknown>; period: string; status: string }[] | undefined): ActionSource[] {
  // a stamp whose "relation" is a feed name ("attention feed") is a source, not a Data Domains relation
  return (trace ?? []).map((t): ActionSource => (/^[a-z][a-z0-9_]*$/.test(t.relation ?? "")
    ? { kind: "row", label: t.relation, relation: t.relation, domain: t.domain, period: t.period, status: t.status,
        keys: Object.fromEntries(Object.entries(t.keys ?? {}).map(([k, v]) => [k, String(v)])) }
    : { kind: "engine", label: `${t.domain ? `${t.domain}: ` : ""}${t.relation}`, period: t.period, status: t.status }));
}

/** Cockpit: the committed run events (readTrace: the public operations, any SQL) and the numeric claims' evidence rows. */
export function cockpitSources(events: { type?: string; kind?: string; stage?: string; operation?: string; status?: string; public_message?: string;
                                         payload?: Record<string, unknown>; data?: Record<string, unknown> }[] | undefined,
                               claims?: { evidence?: { artifact_id: string; row_key: string; column_id: string } | null }[],
                               tables?: { title: string; artifact_id: string; row_count?: number }[]): ActionSource[] {
  const out: ActionSource[] = [];
  const ops = new Set<string>();
  for (const e of events ?? []) {
    const p = (e.payload ?? e.data ?? {}) as Record<string, unknown>;
    const q = p.query as Record<string, unknown> | undefined;
    const sql = typeof p.sql === "string" ? p.sql : typeof q?.sql === "string" ? String(q.sql) : "";
    if (sql) { out.push({ kind: "query", label: String(p.purpose ?? p.title ?? e.operation ?? e.type ?? "Query"), sql, rows: typeof p.row_count === "number" ? p.row_count : undefined }); continue; }
    if (e.operation && e.status === "ok" && !ops.has(e.operation) && ops.size < 12) {
      ops.add(e.operation);
      out.push({ kind: "engine", label: `${e.stage ? `${e.stage}: ` : ""}${e.public_message || e.operation}`.slice(0, 200), method: e.operation });
    }
  }
  for (const t of tables ?? []) out.push({ kind: "run", label: t.title || "Result table", keys: { artifact: t.artifact_id }, rows: t.row_count });
  const seen = new Set<string>();
  for (const c of claims ?? []) {
    const ev = c.evidence;
    if (!ev || seen.has(`${ev.artifact_id}|${ev.row_key}`)) continue;
    seen.add(`${ev.artifact_id}|${ev.row_key}`);
    out.push({ kind: "row", label: `${ev.column_id} of row ${ev.row_key}`, keys: { artifact: ev.artifact_id, row: ev.row_key } });
    if (seen.size > 30) break;
  }
  return out;
}

/** A Cockpit transcript turn (FinalResponse) as document blocks: the narrative and the published tables. */
export function cockpitBlocks(answer: { narrative?: string; tables?: { title: string; columns: string[]; rows?: { display: Record<string, unknown> }[]; row_count?: number }[] }): ActionBlock[] {
  const out: ActionBlock[] = textBlocks(answer.narrative ?? "");
  for (const t of answer.tables ?? []) {
    if (!t.columns?.length) continue;
    out.push({ kind: "table", title: t.title, columns: t.columns.slice(0, 14), row_count: t.row_count ?? t.rows?.length ?? 0,
               rows: (t.rows ?? []).slice(0, 200).map((r) => t.columns.slice(0, 14).map((c) => cell(r.display?.[c]))) });
  }
  return out;
}

export function intelSources(m: { route: { key: string; label: string; home?: string }; deal?: string; borrower?: string; employer?: string }): ActionSource[] {
  const out: ActionSource[] = [{ kind: "engine", label: `${m.route.label} engine`, method: m.route.key, href: m.route.home }];
  if (m.deal) out.push({ kind: "row", label: `Deal ${m.deal}`, relation: "dd_deal", domain: "deal_desk", keys: { proposal_id: m.deal } });
  if (m.borrower) out.push({ kind: "row", label: `Borrower ${m.borrower}`, relation: "corp_borrower_quarter", keys: { borrower_id: m.borrower } });
  if (m.employer) out.push({ kind: "row", label: `Employer ${m.employer}`, relation: "net_employer_view", domain: "network_intel", keys: { employer_id: m.employer } });
  return out;
}

export function b360Sources(borrowerId: string | null | undefined): ActionSource[] {
  if (!borrowerId) return [];
  return [{ kind: "row", label: `Borrower ${borrowerId}`, relation: "corp_borrower_quarter", keys: { borrower_id: borrowerId } },
          { kind: "relation", label: "Relationship edges", relation: "rel_edge_quarter", keys: { borrower_id: borrowerId } }];
}

/** Early Warning: the book's registered relations (Data Domains "ews"): exposures, reasons and the segment series. */
export function ewsSources(list: { id?: string; domain?: string; relations?: string[]; customer?: string } | null | undefined): ActionSource[] {
  const retail = list?.domain === "retail";
  const rels = list?.relations?.length ? list.relations
    : retail ? ["retail_exposure", "retail_behaviour"] : ["corp_exposure", "corp_reason_period", "corp_series_segment"];
  const keys: Record<string, string> | undefined = list?.customer ? { customer_id: list.customer } : list?.id ? { list: list.id } : undefined;
  return rels.map((r): ActionSource => ({ kind: "relation", label: r, relation: r, domain: "ews", keys }));
}

// ------------------------------------------------------------------ the document, report blocks, share object

export function composeDoc(module: ModuleKey, threadId: string, title: string, href: string, turns: ActionTurn[]): ActionDoc {
  const kept = turns.filter((t) => t.blocks.length || t.question);
  // a placeholder title ("New What-If thread", "Lens thread") gives way to the first question
  const generic = !title || /^(new\b.*|.*\bthread)$/i.test(title.trim());
  let t = (generic ? kept[0]?.question : title) || title || MODULE_LABEL[module];
  // a thread titled by a memo request ("prepare a memo on X") is about X
  const mi = memoIntent(t);
  if (mi?.question) t = mi.question.replace(/\?$/, "");
  return { module, thread_id: threadId, title: t.slice(0, 200), href, turns: kept };
}

/** One answer of a thread document (Word "this answer", Trace). */
export function answerDoc(doc: ActionDoc, index: number): ActionDoc {
  const t = doc.turns[index];
  return { ...doc, title: t?.question ? t.question.slice(0, 200) : doc.title, turns: t ? [t] : [] };
}

export type PlaybookBlockOut =
  | { kind: "paragraph"; text: string }
  | { kind: "heading"; text: string; level: 3 }
  | { kind: "bullets"; items: string[] }
  | { kind: "kpis"; items: { label: string; value: string; format: "text" }[] }
  | { kind: "table"; title?: string; columns: { key: string; label: string; format: "text" | "num" }[]; rows: Record<string, string | number>[] };

function pbTable(title: string | undefined, columns: string[], rows: (string | number)[][]): PlaybookBlockOut {
  const cols = columns.slice(0, 30).map((label, i) => ({
    key: `c${i + 1}`, label: label || `Column ${i + 1}`,
    format: (rows.length && rows.every((r) => typeof r[i] === "number" || r[i] === "") && rows.some((r) => typeof r[i] === "number") ? "num" : "text") as "text" | "num",
  }));
  return { kind: "table", title: title || undefined, columns: cols,
           rows: rows.slice(0, 50).map((r) => Object.fromEntries(cols.map((c, i) => [c.key, r[i] ?? ""]))) };
}

/** The document as Playbook section blocks (Add to report; at most 60 blocks, the import limit). */
export function toPlaybookBlocks(doc: ActionDoc): PlaybookBlockOut[] {
  const out: PlaybookBlockOut[] = [];
  const many = doc.turns.length > 1;
  for (const t of doc.turns) {
    if (many && t.question) out.push({ kind: "heading", text: t.question.slice(0, 200), level: 3 });
    for (const b of t.blocks) {
      if (b.kind === "text") {
        for (const line of b.text.split("\n")) {
          const s = line.trim();
          if (!s) continue;
          if (s.startsWith("#")) out.push({ kind: "heading", text: s.replace(/^#+\s*/, "").slice(0, 200), level: 3 });
          else out.push({ kind: "paragraph", text: s.slice(0, 8000) });
        }
      } else if (b.kind === "bullets") out.push({ kind: "bullets", items: b.items.slice(0, 40) });
      else if (b.kind === "figures") out.push({ kind: "kpis", items: b.items.slice(0, 8).map((x) => ({ label: x.label, value: x.value, format: "text" as const })) });
      else out.push(pbTable(b.title, b.columns, b.rows));
    }
    const src = t.sources.slice(0, 8).map((s) => [s.kind, s.label, s.relation ?? "", s.rows ?? ""] as (string | number)[]);
    if (src.length) out.push(pbTable("Sources", ["Kind", "Source", "Relation", "Rows"], src));
  }
  return out.slice(0, 60);
}

export interface ShareObject { type: "thread-answer"; id: string; label: string; href: string; summary?: string; meta?: Record<string, unknown> }

export function shareObject(doc: ActionDoc, scope: "answer" | "thread", answerId = ""): ShareObject {
  const first = doc.turns[doc.turns.length - 1]?.blocks.find((b) => b.kind === "text") as { text: string } | undefined;
  const href = doc.href && doc.href.startsWith("/") && !doc.href.startsWith("//") ? doc.href : "/";
  const label = `${MODULE_LABEL[doc.module]}: ${doc.title}`.slice(0, 190);
  return { type: "thread-answer", id: `${doc.module}:${doc.thread_id || "view"}${scope === "answer" && answerId ? `:${answerId}` : ""}`.slice(0, 120),
           label, href: href.slice(0, 480), summary: (first?.text ?? "").replace(/^#+\s*/, "").slice(0, 300),
           meta: { module: doc.module, thread_id: doc.thread_id, scope, answers: doc.turns.length } };
}

/** Plain words for the Share panel, the Trace panel and the memo card (3 lines, deterministic). */
export function sharePlainWords(doc: ActionDoc, scope: "answer" | "thread"): string[] {
  const n = doc.turns.length;
  return [
    scope === "answer" ? "Send this answer to colleagues in CreditProbe Mail, or copy its link." : `Send the whole thread (${n} answer${n === 1 ? "" : "s"}) to colleagues.`,
    "They open the same thread in CreditProbe, with its sources; nothing leaves the bank.",
    "Tick “Attach the Word memo” to add the house-style document.",
  ];
}

export interface MemoResult {
  memo_id: string; kind: MemoKind; scope: "answer" | "thread"; title: string; addressee: string; file_name: string; href: string;
  bytes: number; answers: number; tables: number; sources: number; recorded: boolean; plain_words: string[]; module_label: string;
}

export function memoPlainWords(r: MemoResult): string[] {
  const label = r.kind === "note" ? "note" : r.kind === "paper" ? "paper" : "memo";
  return [
    `A Word ${label}${r.addressee ? ` to the ${r.addressee}` : ""} is ready: “${r.title.slice(0, 80)}”.`,
    `It covers ${r.answers === 1 ? "one answer" : `${r.answers} answers`} with ${r.tables} table${r.tables === 1 ? "" : "s"} and lists ${r.sources} source${r.sources === 1 ? "" : "s"} at the end.`,
    "Download it below, or share it in Mail with the file attached.",
  ];
}

/** The text the thread shows for a memo request (never "say the word": the document is already written). */
export function memoReply(r: MemoResult): string {
  const label = r.kind === "note" ? "Note" : r.kind === "paper" ? "Paper" : "Memo";
  return `${label} written: ${r.file_name} (${Math.max(1, Math.round(r.bytes / 1024))} KB).`;
}
