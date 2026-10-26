/**
 * v5 Playbook client: committee packs, risk reports, credit memos and validation reports
 * (docs/v5/PLAYBOOK_SERVICE.md, docs/v5/PLAYBOOK_API.md).
 *
 * Talks ONLY to the Playbook and Policy Docs service (backend.playbook_v5.api, port 8506 by default,
 * `NEXT_PUBLIC_PLAYBOOK_API`). Identity is the `cp_session` cookie, so every call sends credentials.
 * No call names the user: the server knows who is signed in. Writes return 403 while viewing as.
 */
import { friendlyError } from "./errors.ts";
import type { MailObject, ObjectType } from "@/lib/v5/core";

export function playbookOrigin(): string {
  return (process.env.NEXT_PUBLIC_PLAYBOOK_API ?? "http://127.0.0.1:8506").replace(/\/$/, "");
}

const BASE = "/api/v1/playbook";

export class PlaybookError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Init = { method?: string; body?: unknown; form?: FormData; headers?: Record<string, string> };

async function request<T>(path: string, init: Init = {}): Promise<T> {
  let response: Response;
  const headers: Record<string, string> = { ...(init.headers ?? {}) };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  try {
    response = await fetch(`${playbookOrigin()}${BASE}${path}`, {
      method: init.method ?? "GET",
      credentials: "include",
      cache: "no-store",
      headers,
      body: init.form ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new PlaybookError(0, `Playbook is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Playbook", response.status, body);
    throw new PlaybookError(response.status, message);
  }
  return body as T;
}

function traced(traceId?: string): Record<string, string> | undefined {
  return traceId ? { "X-Trace-Id": traceId } : undefined;
}

/** The service base the live process trace is polled under (docs/v5/THREAD_API.md 2.2). */
export function traceBase(): string {
  return `${playbookOrigin()}${BASE}`;
}

/** The settled process trace an assistant message carries (PLAN_R5 G4). */
export function messageTrace(m: Message): import("./thread").TraceSnapshot | null {
  const a = (m.actions ?? []).find((x) => (x as { kind: string }).kind === "trace") as { trace?: import("./thread").TraceSnapshot } | undefined;
  return a?.trace ?? null;
}

function qs(params: Record<string, string | number | boolean | string[] | null | undefined>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => out.append(k, x));
    else if (v !== undefined && v !== null && v !== "" && v !== false) out.set(k, String(v));
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

// ---------------------------------------------------------------- types

export interface Person { username: string; name: string; initials?: string; title?: string }

export type ReportStatus = "draft" | "in_review" | "approved" | "presented";
export const WORKFLOW: ReportStatus[] = ["draft", "in_review", "approved", "presented"];
export const STATUS_LABEL: Record<ReportStatus, string> = {
  draft: "Draft", in_review: "In review", approved: "Approved", presented: "Presented",
};

export type Book = "corporate" | "retail" | "both";
export type ValueFormat = "sar" | "pct" | "bps" | "int" | "num" | "num4" | "rating" | "date" | "text";
export type Rag = "green" | "amber" | "red";

/** A Mail type, or one of the extra source types Playbook accepts (PLAYBOOK_API.md 3.1). */
export type SourceType =
  | ObjectType | "scorecard-validation" | "data-extract" | "policy-document" | "circular" | "upload"
  | (string & Record<never, never>);

/** The provenance of an imported section: a MailObject whose type may also be a Playbook-only type. */
export interface PlaybookSource extends Omit<MailObject, "type"> { type: SourceType }

interface BlockBase { id?: string }
export interface ParagraphBlock extends BlockBase { kind: "paragraph"; text: string }
export interface HeadingBlock extends BlockBase { kind: "heading"; text: string; level?: 2 | 3 }
export interface BulletsBlock extends BlockBase { kind: "bullets"; items: string[] }
export interface Kpi { label: string; value: number | string | null; format: ValueFormat; delta?: number | null; status?: Rag | null }
export interface KpisBlock extends BlockBase { kind: "kpis"; items: Kpi[] }
export interface TableColumn { key: string; label: string; format: ValueFormat }
export interface TableBlock extends BlockBase {
  kind: "table"; title?: string | null; columns: TableColumn[]; rows: Record<string, unknown>[]; note?: string | null;
}
export interface ChartBlock extends BlockBase {
  kind: "chart"; title: string; figure: { data?: Record<string, unknown>[]; layout?: Record<string, unknown> } | null;
  png_base64?: string | null; note?: string | null;
}
export interface RagItem {
  test: string; value: number | string | null; format: ValueFormat; threshold: string; status: Rag; comment?: string | null;
}
export interface RagBlock extends BlockBase { kind: "rag"; title?: string | null; items: RagItem[] }
export interface CalloutBlock extends BlockBase { kind: "callout"; tone: "info" | "warning" | "critical"; text: string }

export type Block =
  | ParagraphBlock | HeadingBlock | BulletsBlock | KpisBlock | TableBlock | ChartBlock | RagBlock | CalloutBlock;
export type BlockKind = Block["kind"];

export type SectionStatus = "empty" | "drafted" | "imported" | "edited";
export interface Section {
  id: string; title: string; blocks: Block[]; source: PlaybookSource | null; status: SectionStatus;
  updated_at: string | null; updated_by: Person | null;
}

export interface ReportRow {
  id: string; title: string; template: string; template_name: string; status: ReportStatus; status_label: string;
  owner: Person | null; reviewers: Person[]; due_date: string | null; overdue: boolean; updated_at: string;
  version: number; section_count: number; book: Book | string | null; period: string | null;
  origin: "template" | "upload" | "import"; href: string;
}
export interface HistoryEntry { at: string; who: Person | null; from: ReportStatus | null; to: ReportStatus; note: string }
export interface Comment { id: string; at: string; author: Person | null; body: string; section_id: string | null; resolved: boolean }
export interface ReportFile {
  id: string; name: string; size: number; content_type: string; uploaded_at: string; uploaded_by: Person | null;
  section_id: string | null;
}
export interface Report extends ReportRow {
  sections: Section[]; history: HistoryEntry[]; comments: Comment[]; files: ReportFile[]; thread_id: string | null;
  allowed_transitions: ReportStatus[]; can_edit: boolean; workflow: ReportStatus[];
}

export interface Template { id: string; name: string; description: string; sections: string[] }
export interface Summary {
  by_status: Record<ReportStatus, number>; awaiting_my_review: number; mine: number; overdue: number;
}
export interface VersionRow { version: number; at: string; who: Person | null; action: string; summary: string }

export type ActionKind = "section_drafted" | "section_revised" | "imported" | "status" | "created";
export interface MessageAction {
  kind: ActionKind | string; section_id?: string | null; label: string; report_id?: string;
  /** kind "answer": what the conversation found (tables as report blocks, charts, links). */
  table_blocks?: Block[]; blocks?: Block[]; citations?: { kind: string; label: string; href?: string; doc_id?: string }[];
  refused?: boolean; source?: string; stages?: string[]; removed?: string[];
  /** kind "proposal": a report the top chat proposes before it creates it. */
  title?: string; book?: string; period?: string; sections?: { title: string; kind: string; covers: string }[];
}
export interface SectionThread {
  thread_id: string; report_id: string; section_id: string; kind: string; data_access: string; domains: string[];
  suggestions: string[]; messages: Message[];
}
export interface Message {
  id: string; role: "user" | "assistant"; at: string; author: Person | null; text: string;
  actions: MessageAction[]; suggestions: string[];
}
export interface Thread { thread_id: string; report_id: string; messages: Message[] }

export interface Source {
  type: string; type_label: string; id: string; label: string; summary: string; href: string; available: boolean;
}
export interface Sources { sources: Source[]; unavailable: { type: string; reason: string }[] }

export interface NewReport {
  title: string; template: string; book?: Book; period?: string; due_date?: string | null; reviewers?: string[];
}
export interface SectionInput { title: string; blocks: Block[]; position?: string }
export interface ImportBody {
  report_id: string | null;
  new_report: NewReport | null;
  source: PlaybookSource;
  section: SectionInput;
  attachment?: { name: string; content_type: string; file_base64: string } | null;
}
export interface ImportResult {
  report_id: string; report_title: string; section_id: string; version: number; created_report: boolean; href: string;
  replayed?: boolean;
}

/** The templates of PLAYBOOK_API.md section 5, shown if the service's list cannot be read. */
export const TEMPLATE_FALLBACK: Template[] = [
  { id: "credit-committee-pack", name: "Credit committee pack", description: "The quarterly pack for the credit committee.",
    sections: ["Executive summary", "Portfolio overview", "Early Warning", "Borrowers for decision", "Scenarios", "Recommendations"] },
  { id: "risk-committee-report", name: "Risk committee report", description: "Risk appetite, credit quality and emerging risks.",
    sections: ["Executive summary", "Risk appetite", "Credit quality and ECL", "Concentrations", "Emerging risks", "Actions"] },
  { id: "portfolio-review", name: "Portfolio review", description: "Composition, quality and movements of a book.",
    sections: ["Summary", "Composition", "Credit quality", "Movements", "Outlook"] },
  { id: "borrower-credit-memo", name: "Borrower credit memo", description: "A request and recommendation for one borrower.",
    sections: ["Request and recommendation", "Borrower profile", "Financial analysis", "Facilities and security", "Risk rating",
               "Early Warning", "Policy compliance", "Conditions"] },
  { id: "scenario-report", name: "Scenario report", description: "A What-If scenario, its results and the actions it calls for.",
    sections: ["Summary", "Scenario definition", "Results", "Drivers", "Management actions"] },
];

// ---------------------------------------------------------------- calls

export interface ReportsParams { status?: ReportStatus | ReportStatus[]; template?: string; q?: string; editable?: boolean }

const reportPath = (id: string) => `/reports/${enc(id)}`;
const sectionPath = (id: string, sid: string) => `${reportPath(id)}/sections/${enc(sid)}`;

export const playbook = {
  health: () => request<{ status: string; service: string; port: number; counts: Record<string, number> }>("/health"),
  templates: () => request<{ templates: Template[] }>("/templates"),
  summary: () => request<Summary>("/summary"),
  reports: (params: ReportsParams = {}) =>
    request<{ reports: ReportRow[]; total: number }>(`/reports${qs({
      status: params.status === undefined ? undefined : Array.isArray(params.status) ? params.status : [params.status],
      template: params.template, q: params.q, editable: params.editable,
    })}`),
  createReport: (body: NewReport) => request<Report>("/reports", { method: "POST", body }),
  upload: (file: File, opts: { title?: string; template?: string } = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (opts.title) form.append("title", opts.title);
    if (opts.template) form.append("template", opts.template);
    return request<Report>("/reports/upload", { method: "POST", form });
  },
  report: (id: string) => request<Report>(reportPath(id)),
  update: (id: string, body: Partial<{ title: string; due_date: string | null; reviewers: string[]; owner: string; book: string; period: string }>) =>
    request<Report>(reportPath(id), { method: "PATCH", body }),
  setStatus: (id: string, to: ReportStatus, note = "") =>
    request<Report>(`${reportPath(id)}/status`, { method: "POST", body: { to, note } }),

  addSection: (id: string, body: SectionInput) =>
    request<Report>(`${reportPath(id)}/sections`, { method: "POST", body: { position: "end", ...body } }),
  updateSection: (id: string, sid: string, body: { title?: string; blocks?: Block[] }) =>
    request<Report>(sectionPath(id, sid), { method: "PUT", body }),
  deleteSection: (id: string, sid: string) => request<Report>(sectionPath(id, sid), { method: "DELETE" }),
  moveSection: (id: string, sid: string, direction: "up" | "down") =>
    request<Report>(`${sectionPath(id, sid)}/move`, { method: "POST", body: { direction } }),

  addComment: (id: string, body: string, sectionId?: string | null) =>
    request<Comment>(`${reportPath(id)}/comments`, { method: "POST", body: sectionId ? { body, section_id: sectionId } : { body } }),
  resolveComment: (id: string, cid: string) =>
    request<Comment>(`${reportPath(id)}/comments/${enc(cid)}/resolve`, { method: "POST" }),

  versions: (id: string) => request<{ versions: VersionRow[] }>(`${reportPath(id)}/versions`),
  version: (id: string, n: number) => request<{ version: number; report: Report }>(`${reportPath(id)}/versions/${n}`),
  restore: (id: string, n: number) => request<Report>(`${reportPath(id)}/versions/${n}/restore`, { method: "POST" }),

  thread: (id: string) => request<Thread>(`${reportPath(id)}/thread`),
  say: (id: string, text: string, traceId?: string) =>
    request<{ messages: Message[]; report: Report }>(`${reportPath(id)}/thread`, { method: "POST", body: { text }, headers: traced(traceId) }),
  /** The chat box at the top of the Playbook home: starts a report or answers. */
  start: (text: string, threadId?: string | null, traceId?: string) =>
    request<{ thread_id: string; report: Report | null; messages: Message[] }>("/threads",
      { method: "POST", body: { text, thread_id: threadId ?? null }, headers: traced(traceId) }),
  /** A home conversation, reopened from its URL (/playbook?thread=<id>). */
  startThread: (threadId: string) => request<{ thread_id: string; messages: Message[] }>(`/threads/${enc(threadId)}`),
  /** Each section's own assistant thread (data matched to the section). */
  sectionThread: (id: string, sid: string) => request<SectionThread>(`${reportPath(id)}/sections/${enc(sid)}/thread`),
  sectionSay: (id: string, sid: string, text: string, traceId?: string) =>
    request<{ thread_id: string; messages: Message[]; report: Report }>(`${reportPath(id)}/sections/${enc(sid)}/thread`,
      { method: "POST", body: { text }, headers: traced(traceId) }),
  applyAnswer: (id: string, sid: string, messageId: string) =>
    request<Report & { merged?: { section_id: string; version: number; where: string } }>(
      `${reportPath(id)}/sections/${enc(sid)}/thread/apply`, { method: "POST", body: { message_id: messageId } }),
  /** PLAN_R5 P3: one undo of an assistant merge (restores the section as it was; a new version). */
  undoMerge: (id: string, sid: string, version?: number) =>
    request<Report>(`${reportPath(id)}/sections/${enc(sid)}/undo`, { method: "POST", body: version ? { version } : {} }),

  sources: (p: { type?: string; q?: string } = {}) => request<Sources>(`/sources${qs(p)}`),
  importSource: (id: string, type: string, sourceId: string) =>
    request<Report>(`${reportPath(id)}/import`, { method: "POST", body: { type, id: sourceId } }),
  /** The call behind every "Add to report" button (PLAYBOOK_API.md 3). */
  /** One CreditProbe object as a ready section, resolved by Playbook (for an Add to report button's `build`). */
  section: (type: string, id: string) =>
    request<{ source: MailObject; section: { title: string; blocks: Block[] } }>(`/section${qs({ type, id })}`),
  importSection: (body: ImportBody, idempotencyKey?: string) =>
    request<ImportResult>("/imports", {
      method: "POST", body, headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey.slice(0, 80) } : undefined,
    }),
  share: (id: string, to: string[], note = "") =>
    request<{ thread_id: string; message_id: string; recipients: string[] }>(`${reportPath(id)}/share`,
      { method: "POST", body: { to, note } }),

  exportUrl: (id: string) => `${playbookOrigin()}${BASE}${reportPath(id)}/export.docx`,
  fileUrl: (id: string, fid: string) => `${playbookOrigin()}${BASE}${reportPath(id)}/files/${enc(fid)}`,
};

export const reportHref = (id: string, section?: string | null) =>
  `/playbook?report=${enc(id)}${section ? `&section=${enc(section)}` : ""}`;

// ---------------------------------------------------------------- words

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function dateWords(v: string): string {
  const d = new Date(v.length === 10 ? `${v}T00:00:00Z` : v);
  if (Number.isNaN(d.getTime())) return v;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function grouped(n: number, places: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places });
}

/** Formats that are numbers (right-aligned in tables). */
export function isNumericFormat(format: ValueFormat | string | undefined): boolean {
  return format === "sar" || format === "pct" || format === "bps" || format === "int" || format === "num" || format === "num4";
}

/**
 * A raw value in a block format (PLAYBOOK_API.md 3.2): `sar` in riyals (SAR 1.23bn, SAR 45.6m, SAR 12.3k),
 * `pct` a fraction (0.123 is 12.3%), `bps` basis points, `int` with thousands separators, `num` 2 dp,
 * `num4` 4 dp, `rating` as given, `date` YYYY-MM-DD as "9 Jul 2026", `text` as given.
 */
export function formatValue(value: unknown, format: ValueFormat | string | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (format === "text" || format === "rating" || format === undefined) return String(value);
  if (format === "date") return dateWords(String(value));
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  switch (format) {
    case "sar": {
      const a = Math.abs(n);
      const sign = n < 0 ? "-" : "";
      if (a >= 1e9) return `SAR ${sign}${(a / 1e9).toFixed(2)}bn`;
      if (a >= 1e6) return `SAR ${sign}${(a / 1e6).toFixed(1)}m`;
      if (a >= 1e3) return `SAR ${sign}${(a / 1e3).toFixed(1)}k`;
      return `SAR ${sign}${a.toFixed(0)}`;
    }
    case "pct": return `${(n * 100).toFixed(1)}%`;
    case "bps": return `${grouped(n, 0)} bps`;
    case "int": return grouped(Math.round(n), 0);
    case "num": return grouped(n, 2);
    case "num4": return grouped(n, 4);
    default: return String(value);
  }
}

/** A change in a KPI, signed: percentage points for a `pct`, otherwise the value's own format. */
export function formatDelta(delta: number | null | undefined, format: ValueFormat | string | undefined): string {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return "";
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
  const a = Math.abs(delta);
  if (format === "pct") return `${sign}${(a * 100).toFixed(1)}pp`;
  if (format === "sar" || format === "bps" || format === "int" || format === "num" || format === "num4") {
    return `${sign}${formatValue(a, format)}`;
  }
  return `${sign}${grouped(a, 2)}`;
}

export const RAG_LABEL: Record<Rag, string> = { green: "Green", amber: "Amber", red: "Red" };
export const BOOK_LABEL: Record<string, string> = { corporate: "Corporate", retail: "Retail", both: "Corporate and Retail" };
export const SECTION_STATUS_LABEL: Record<SectionStatus, string> = {
  empty: "Not written", drafted: "Drafted", imported: "Imported", edited: "Edited",
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "";
  return STATUS_LABEL[status as ReportStatus] ?? status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Initials for a person whose record arrived without them. */
export function initialsOf(p: Pick<Person, "name" | "initials" | "username"> | null | undefined): string {
  if (!p) return "CP";
  if (p.initials) return p.initials;
  const parts = (p.name || p.username || "").split(/[\s.]+/).filter(Boolean);
  return (parts.slice(0, 2).map((x) => x[0]?.toUpperCase() ?? "").join("")) || "?";
}

/** What a workflow move is called on its button. */
export function transitionLabel(from: ReportStatus, to: ReportStatus): string {
  if (to === "in_review") return "Send for review";
  if (to === "approved") return "Approve";
  if (to === "presented") return "Mark presented";
  if (to === "draft") return from === "in_review" ? "Send back to draft" : "Reopen as draft";
  return STATUS_LABEL[to] ?? to;
}
