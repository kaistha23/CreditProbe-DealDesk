/**
 * Noor, the pure part (PLAN_R12 N1; R11_FEEDBACK I11–I13, I17 switch): the brief's types, the personas and who may
 * switch between them, the module a page belongs to, the thread's turns, the live-trace schedule and the scripted
 * 90-second demo. No React and no fetch, so `node --test` covers it (noor-model.test.ts).
 */

export type Persona = "cro" | "reviewer" | "rm" | "analyst";
export type Severity = "critical" | "high" | "medium" | "low";

export interface BriefNumber { label: string; value: number | null; unit: string; display: string }
export interface TraceStamp { domain: string; relation: string; keys: Record<string, unknown>; period: string; status: string }
export interface Link { href: string; label: string }

export interface BriefItem {
  id: string; source: string; source_label: string; module: string; title: string; detail: string;
  severity: Severity; materiality_sar_mn: number | null; due: string | null; since: string | null; kind: string;
  owner: string | null; numbers: BriefNumber[]; trace: TraceStamp[]; show_me: Link; open: Link;
  entity: Record<string, unknown>; rank: number; score: number;
  /** R14 K9: shown as "New" only when this line's source refreshed since the reader's last visit. */
  new?: boolean;
  /** The deterministic Cockpit attention card(s) behind the line (R13 H, J2 (a)): what Why? opens as evidence. */
  evidence?: { kind: string; item_id: string; label: string; href: string }[];
}

export interface Brief {
  assistant: string; persona: Persona; persona_label: string; title: string; module: string | null;
  date: string; date_label: string; opening: string; opening_ar?: string; wording: string;
  /** The headline sentence (R13 H, J3): what the brief amounts to, without the greeting. */
  headline?: string;
  items: BriefItem[]; more: BriefItem[]; n_more: number; n_total: number;
  /** R14 K9: the eyebrow's data dates per source family ("Corporate 2026Q2 · Deal Desk today"). */
  data_dates?: { label: string; date: string; text: string }[];
  headline_ar?: string;
  /** R14 K10: the brief-level spoken script (headline, then one sentence per line), English and Arabic. */
  script?: { en: string; ar: string; seconds_en: number; seconds_ar: number };
  sources: Record<string, { status: string; rows?: number; note?: string }>; ms: number;
}

export interface TraceStep { label: string; count: number | null; unit: string; note: string; ms: number; source: TraceStamp | Record<string, never> }
export interface Figure { data: Record<string, unknown>[]; layout: Record<string, unknown> }
/** R14 K10: one line's spoken script (40–70 s): what, bank vs requirement, reasons with shares, impact, action. */
export interface IssueScript { item_id: string; en: string; ar: string; seconds_en: number; seconds_ar: number; kind: string }

export interface WhyAnswer {
  spoken?: string; spoken_ar?: string;
  /** "In plain words": 3–4 lines, ≤ ~60 words, from the line's facts (K34 block, R14 n content). */
  plain_words?: string[];
  item_id: string; answer: string; steps: TraceStep[]; figure: Figure | null; numbers: BriefNumber[];
  trace: TraceStamp[]; follow_ups: string[]; ms: number;
}
export interface DecisionOption {
  key: string; title: string; how: string; effect: string; recommended: boolean; numbers: BriefNumber[];
  figures: Record<string, number | null>; deals?: string[];
}
export interface OptionsAnswer {
  spoken?: string; plain_words?: string[];
  item_id: string; answer: string; options: DecisionOption[]; recommended: string; engine: string;
  trace: TraceStamp[]; ms: number;
}
export interface DriverRow { name: string; borrower_id: string; band: string; ead: string; stage: number; dpd: number; href: string }
export interface DriversAnswer {
  spoken?: string;
  item_id: string; answer: string; rows: DriverRow[]; columns: { key: string; label: string; align?: "left" | "right" }[];
  trace: TraceStamp[]; show_me?: Link; ms: number;
}
export interface CommitteeResult {
  message: string; open: Link;
  committee_item: { committee_item_id: string; title: string; created_at: string; status: string };
}
/** The brief's headline: the server's, else the opening without its greeting and its "First: …" clause. */
export function headlineOf(brief: Pick<Brief, "headline" | "opening">): string {
  if (brief.headline) return brief.headline;
  return brief.opening.replace(/^Good (morning|afternoon|evening)(, [^.]+)?\.\s*/, "").replace(/\s*First: .*$/, "")
    .replace(/\.?$/, ".");
}

/** R15 L9: the page a question was asked on (noor-context.ts PageContext). */
export interface PageContextLike {
  module: string; path: string; deal_id: string | null; step: string | null; structures: string[]; stress_on_screen: boolean;
}

export interface HereCell { passes: boolean | null; first: string; tests?: string[]; breaking?: number; applicable?: number; min_dscr?: number | null }

/** R15 L9: Noor's answer in the page context (POST /api/v1/noor/here, backend/agents_v5/brief/here.py). */
export interface HereAnswer {
  here: boolean; reason: string; question?: string; topic: "stress" | "deal"; deal_id: string; obligor: string; step: string | null;
  title: string; lines: string[]; plain_words: string[];
  rows: { structure: string; key: string; status: string; survives_up_to: string; cells: Record<string, HereCell>; broken?: number; applicable?: number }[];
  drivers?: string[]; fix_from?: string | null; fix_target?: string | null; regime?: string; regime_line?: string; basis: string;
  actions: { label: string; kind: "scroll" | "book" | "dealdesk"; target?: string; href?: string }[]; spoken: string;
}

export interface HereFix {
  deal_id: string; from_key: string; target: string; line: string; changes: { text: string; client: string; cost: string }[];
  uncured: string[]; asks: string[]; survives: boolean; basis: string;
}

export interface NoorSettings {
  name: string; speak_first: boolean;
  voice: { enabled: boolean; gender: "male"; language: "en" | "ar-gulf"; rate?: number; pitch?: number;
           /** R15 L2: the voice chosen per language in Settings -> Voice; null until chosen. */
           chosen?: Partial<Record<"en" | "ar-gulf", { name: string; lang: string; rate: number; pitch: number; chosen_by?: string; chosen_at?: string } | null>> };
}

export type Turn =
  | { id: string; kind: "brief"; brief: Brief; module: string }
  | { id: string; kind: "ask"; text: string; module: string }
  | { id: string; kind: "why"; item: BriefItem; answer: WhyAnswer }
  | { id: string; kind: "options"; item: BriefItem; answer: OptionsAnswer }
  | { id: string; kind: "drivers"; item: BriefItem; answer: DriversAnswer }
  | { id: string; kind: "committee"; item: BriefItem; option: DecisionOption; result: CommitteeResult }
  | { id: string; kind: "note"; text: string; module: string }
  | { id: string; kind: "routed"; engine: string; label: string; question: string; href: string; module: string;
      /** R15 L9: why the question left the page it was asked on, and that page's context (for "Answer here instead"). */
      why?: string; here?: PageContextLike | null }
  | { id: string; kind: "here"; question: string; answer: HereAnswer; fix?: HereFix | null; module: string }
  | { id: string; kind: "pending"; text: string }
  | { id: string; kind: "error"; text: string };

// ---------------------------------------------------------------- personas (I13.4, I17)

export const PERSONAS: { id: Persona; label: string; short: string; brief: string }[] = [
  { id: "rm", label: "Relationship manager", short: "RM", brief: "Your clients today" },
  { id: "reviewer", label: "Credit reviewer", short: "Credit reviewer", brief: "Your review desk today" },
  { id: "cro", label: "CRO", short: "CRO", brief: "The bank" },
  { id: "analyst", label: "Analyst", short: "Analyst", brief: "Your work today" },
];

const ROLE_PERSONA: Record<string, Persona> = {
  "administrator": "cro", "head of risk": "cro", "head of credit": "cro", "chief risk officer": "cro",
  "chief credit officer": "cro", "cro": "cro", "cco": "cro",
  "corporate credit manager": "reviewer", "retail credit manager": "reviewer", "credit reviewer": "reviewer",
  "credit officer": "reviewer",
  "relationship manager": "rm", "rm": "rm",
};

/** The persona of an identity role (backend/agents_v5/brief/items.py ROLE_PERSONA is the same table). */
export function personaFor(role: string | null | undefined): Persona {
  return ROLE_PERSONA[String(role ?? "").trim().toLowerCase()] ?? "analyst";
}

export function isPersona(v: unknown): v is Persona {
  return v === "cro" || v === "reviewer" || v === "rm" || v === "analyst";
}

/** The "Viewing as" switch is for demo and admin accounts only (I17); normal users never see it. */
export function canSwitch(user: { is_admin?: boolean; username?: string; role?: string } | null | undefined,
                          demoMode = false): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  if (String(user.username ?? "").toLowerCase().startsWith("demo")) return true;
  if (String(user.role ?? "").toLowerCase().includes("demo")) return true;
  return demoMode;
}

/** Who the screens are drawn for: the switch when allowed and set, else the login's own role. */
export function effectivePersona(role: string | null | undefined, chosen: Persona | null, allowed: boolean): Persona {
  return allowed && chosen ? chosen : personaFor(role);
}

/** Deal Desk's view for a persona (I17): an RM prepares, everyone else on the credit side reviews. */
export function dealDeskView(p: Persona): "prepare" | "review" {
  return p === "rm" ? "prepare" : "review";
}

// ---------------------------------------------------------------- modules (one thread across them)

export const MODULES: { prefix: string; id: string; label: string }[] = [
  { prefix: "/deal-desk", id: "dealdesk", label: "Deal Desk" },
  { prefix: "/early-warning", id: "ews", label: "Early Warning" },
  { prefix: "/what-if", id: "whatif", label: "What-If" },
  { prefix: "/lenses", id: "lenses", label: "Lenses" },
  { prefix: "/borrower-360", id: "b360", label: "Borrower 360" },
  { prefix: "/playbook", id: "playbook", label: "Playbook" },
  { prefix: "/workspace", id: "workspace", label: "Workspace" },
  { prefix: "/messages", id: "mail", label: "Mail" },
  { prefix: "/cockpit", id: "cockpit", label: "the Cockpit" },
];

export function moduleOf(pathname: string | null | undefined): { id: string; label: string } {
  const p = String(pathname ?? "/");
  if (p === "/" || p === "") return { id: "cockpit", label: "the Cockpit" };
  const m = MODULES.find((x) => p === x.prefix || p.startsWith(`${x.prefix}/`) || p.startsWith(`${x.prefix}?`));
  return m ? { id: m.id, label: m.label } : { id: "other", label: "this screen" };
}

// ---------------------------------------------------------------- the thread

export const MAX_TURNS = 40;

let seq = 0;
export function turnId(prefix = "t"): string {
  seq += 1;
  return `${prefix}-${Date.now().toString(36)}-${seq}`;
}

/** Add a turn; a `pending` turn is replaced by the next turn that settles it. Keeps the last MAX_TURNS. */
export function addTurn(turns: Turn[], turn: Turn, replacing?: string): Turn[] {
  const base = replacing ? turns.filter((t) => t.id !== replacing) : turns;
  const next = [...base, turn];
  return next.length > MAX_TURNS ? next.slice(next.length - MAX_TURNS) : next;
}

/** A thread read back from storage, with anything malformed or still pending dropped. */
export function restoreTurns(raw: string | null): Turn[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw) as unknown;
    if (!Array.isArray(v)) return [];
    return v.filter((t): t is Turn => Boolean(t) && typeof t === "object" && typeof (t as Turn).id === "string"
      && typeof (t as Turn).kind === "string" && (t as Turn).kind !== "pending").slice(-MAX_TURNS);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------- threads (R14 n: K5, K7, K16)

/**
 * Noor's threads. One per question started from a fresh panel, one per brief line (keyed `line:<id>`: Why, What to
 * do and Open on that line all land in it, and reopening the line resumes it), one per brief read. Earlier threads
 * live in the panel's history list, never in the same scroll.
 */
export interface NoorThread {
  id: string; title: string; key: string | null; module: string; created: number; updated: number; turns: Turn[];
}

export const MAX_THREADS = 20;

export function newThread(module: string, key: string | null = null, title = "New thread", now = Date.now()): NoorThread {
  return { id: turnId("th"), title, key, module, created: now, updated: now, turns: [] };
}

export function lineKey(item: Pick<BriefItem, "id">): string { return `line:${item.id}`; }

export function findThread(threads: NoorThread[], key: string): NoorThread | null {
  return threads.find((t) => t.key === key) ?? null;
}

/** Replace one thread (by id) and keep at most MAX_THREADS, dropping the oldest. */
export function putThread(threads: NoorThread[], th: NoorThread): NoorThread[] {
  const rest = threads.filter((t) => t.id !== th.id);
  const all = [th, ...rest];
  if (all.length <= MAX_THREADS) return all;
  return [...all].sort((a, b) => b.updated - a.updated).slice(0, MAX_THREADS);
}

/** Add a turn to one thread; its title becomes the first question when it had none. */
export function addThreadTurn(th: NoorThread, turn: Turn, replacing?: string, now = Date.now()): NoorThread {
  const title = th.title === "New thread" && turn.kind === "ask" ? titleOf(turn.text) : th.title;
  return { ...th, title, updated: now, turns: addTurn(th.turns, turn, replacing) };
}

function titleOf(text: string): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > 70 ? `${t.slice(0, 68)}…` : t || "New thread";
}

/** The panel's history: threads that hold something, newest first, the open one excluded. */
export function historyOf(threads: NoorThread[], currentId: string | null): NoorThread[] {
  return threads.filter((t) => t.id !== currentId && t.turns.some((x) => x.kind !== "pending"))
    .sort((a, b) => b.updated - a.updated);
}

export function restoreThreads(raw: string | null): { threads: NoorThread[]; current: string | null } {
  if (!raw) return { threads: [], current: null };
  try {
    const v = JSON.parse(raw) as { threads?: unknown; current?: unknown };
    const threads = (Array.isArray(v.threads) ? v.threads : []).filter((t): t is NoorThread =>
      Boolean(t) && typeof (t as NoorThread).id === "string" && Array.isArray((t as NoorThread).turns))
      .map((t) => ({ ...t, turns: restoreTurns(JSON.stringify(t.turns)) })).slice(0, MAX_THREADS);
    const current = typeof v.current === "string" && threads.some((t) => t.id === v.current) ? v.current : null;
    return { threads, current };
  } catch {
    return { threads: [], current: null };
  }
}

/** Typed text matched to a brief line (no model): the line sharing most words with the question. */
export function matchItem(text: string, items: BriefItem[]): BriefItem | null {
  const words = (s: string) => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w.length > 3));
  const q = words(text);
  if (!q.size) return null;
  let best: BriefItem | null = null;
  let bestScore = 0;
  for (const it of items) {
    const w = words(`${it.title} ${String(it.entity?.name ?? "")} ${it.source_label}`);
    let s = 0;
    q.forEach((x) => { if (w.has(x)) s += 1; });
    if (s > bestScore) { best = it; bestScore = s; }
  }
  return bestScore > 0 ? best : null;
}

/** What a typed question asks for. */
export function intentOf(text: string): "why" | "options" | "drivers" | "show" | "brief" | "unknown" {
  const t = text.toLowerCase();
  if (/\b(who drives|who is behind|which (names|borrowers)|names behind)\b/.test(t)) return "drivers";
  if (/\b(what should|what do we|options?|recommend|do about)\b/.test(t)) return "options";
  if (/\b(why|explain|how come|what drove|driver)\b/.test(t)) return "why";
  if (/\b(show|open|take me|go to|list)\b/.test(t)) return "show";
  if (/\b(brief|today|morning|what's new|whats new|since yesterday)\b/.test(t)) return "brief";
  return "unknown";
}

// ---------------------------------------------------------------- live trace (I12 step 3)

/**
 * When each step appears and how long its counter ticks, so the thinking plays out live but quickly: each step
 * takes its measured time, but at least `minMs` and at most `maxMs`, and the counter ticks up to its number.
 */
export function traceSchedule(steps: TraceStep[], minMs = 550, maxMs = 1100): { startMs: number; durationMs: number }[] {
  let t = 0;
  return steps.map((s) => {
    const d = Math.max(minMs, Math.min(maxMs, s.ms || 0));
    const out = { startMs: t, durationMs: d };
    t += d;
    return out;
  });
}

/** The counter's value `elapsed` ms into a step that ends on `count`. */
export function tickValue(count: number | null, elapsed: number, duration: number): number | null {
  if (count === null || !Number.isFinite(count)) return null;
  if (elapsed >= duration) return count;
  const f = Math.max(0, elapsed) / duration;
  return Math.round(count * (1 - (1 - f) ** 2));
}

// ---------------------------------------------------------------- presentation helpers

/** The figures in a sentence (money, percentages, counts), split out so they can be emphasised; never a stage
 *  number, a period such as 2026Q2 or a digit inside a name. Odd indexes of the result are figures. */
export const FIGURE = /((?:−|-)?SAR [\d,.]+(?:bn|m)|(?<![A-Za-z\d-])(?<!Stage )\d[\d,.]*(?:%|pp|x(?![a-z]))?(?![\dA-Za-z]))/g;

export function splitFigures(text: string): string[] {
  return text.split(FIGURE);
}

export function severityTone(s: Severity): "negative" | "warning" | "neutral" | "muted" {
  return s === "critical" ? "negative" : s === "high" ? "warning" : s === "medium" ? "neutral" : "muted";
}

export function severityLabel(s: Severity): string {
  return s === "critical" ? "Critical" : s === "high" ? "High" : s === "medium" ? "Medium" : "Low";
}

/** "Data Domains: deal_desk · dd_result · 2026Q2" in banker words for the (i). */
export function traceLine(t: TraceStamp): string {
  const where = t.status === "agent_store" ? "Agent record" : t.status === "frozen_feed" ? "Cockpit attention card" : "Data Domains";
  return [where, t.domain, t.relation, t.period].filter(Boolean).join(" · ");
}

/** The words a speaking voice reads (I13.1): the opening only, without symbols a voice reads badly. */
/** What the voice reads for a brief: the Arabic opening for the Gulf Arabic voice when there is one. */
export function spokenOpening(brief: Pick<Brief, "opening" | "opening_ar">, lang: NoorSettings["voice"]["language"]): string {
  return lang === "ar-gulf" && brief.opening_ar ? brief.opening_ar : brief.opening;
}

export function speakable(text: string): string {
  return text.replace(/SAR ([\d,.]+)bn/g, "$1 billion riyals").replace(/SAR ([\d,.]+)m\b/g, "$1 million riyals")
    .replace(/(\d)pp\b/g, "$1 percentage points").replace(/−/g, "minus ").replace(/\s+/g, " ").trim();
}

/**
 * An answer's spoken summary (K10): its prose, not its tables. Drops lines that read like table rows (mostly numbers
 * or separated cells), keeps whole sentences up to `maxWords`, and makes figures sayable.
 */
export function spokenSummary(prose: string, maxWords = 90): string {
  const lines = String(prose ?? "").split(/\n+/).map((l) => l.trim()).filter(Boolean)
    .filter((l) => !/\t|\s\|\s/.test(l))
    .filter((l) => {
      const words = l.split(/\s+/);
      const numeric = words.filter((w) => /^[−\-+]?(SAR)?[\d,.]+(%|x|bn|m|pp)?$/.test(w)).length;
      return words.length >= 3 && numeric / words.length < 0.5;
    });
  const out: string[] = [];
  let n = 0;
  for (const sentence of lines.join(" ").split(/(?<=[.!?])\s+/)) {
    const w = sentence.split(/\s+/).length;
    if (n && n + w > maxWords) break;
    out.push(sentence);
    n += w;
  }
  return speakable(out.join(" "));
}

export function voiceLang(lang: NoorSettings["voice"]["language"]): string {
  return lang === "ar-gulf" ? "ar-SA" : "en-GB";
}

// ---------------------------------------------------------------- the scripted 90-second demo (I12)

export interface DemoStep { at: number; action: "brief" | "why" | "options" | "committee" | "done"; say: string }

/** The no-typing demo path and its planned clock (seconds); R12_UAT.md §Demo records the measured one. */
export const DEMO_SCRIPT: DemoStep[] = [
  { at: 0, action: "brief", say: "Noor speaks first: the brief for the CRO, three to five lines ranked from every source." },
  { at: 12, action: "why", say: "Why? on the Construction line: the trace plays out live (facilities read, limits checked, breaches found)." },
  { at: 30, action: "options", say: "One line and one chart answer it; What should we do? gives three options priced by the engines." },
  { at: 55, action: "committee", say: "Send to committee on the recommended option creates the committee item." },
  { at: 70, action: "done", say: "The item is waiting for the committee chair; the panel stays open on any screen." },
];

export const DEMO_ITEM = "appetite:Construction";
export const DEMO_BUDGET_S = 90;
