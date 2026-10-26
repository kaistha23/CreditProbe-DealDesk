/**
 * v5 Core client: sign-in, users and CreditProbe Mail (docs/v5/MAIL_API.md).
 *
 * Talks ONLY to the Core service (backend/workspace_v5, port 8505 by default,
 * `NEXT_PUBLIC_WORKSPACE_API`). Identity is the `cp_session` cookie, so every call
 * sends credentials. No call names the user: the server knows who is signed in.
 */
import { friendlyError } from "./errors.ts";
import * as React from "react";

export function coreOrigin(): string {
  return (process.env.NEXT_PUBLIC_WORKSPACE_API ?? "http://127.0.0.1:8505").replace(/\/$/, "");
}

export class CoreError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Init = { method?: string; body?: unknown; form?: FormData; headers?: Record<string, string> };

export async function coreRequest<T>(path: string, init: Init = {}): Promise<T> {
  let response: Response;
  const headers: Record<string, string> = { ...(init.headers ?? {}) };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  try {
    response = await fetch(`${coreOrigin()}${path}`, {
      method: init.method ?? "GET",
      credentials: "include",
      cache: "no-store",
      headers,
      body: init.form ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new CoreError(0, `Sign-in and Mail are temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Sign-in and Mail", response.status, body);
    throw new CoreError(response.status, message);
  }
  return body as T;
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

// ---------------------------------------------------------------- types

export type Team = "admin" | "risk" | "corporate" | "retail" | "validation" | "audit";
export interface User {
  username: string; name: string; role: string; title: string; department: string; initials: string;
  books: ("corporate" | "retail")[]; team: Team; is_admin: boolean;
}
/** Per-user preferences kept by the Core service (PLAN_R6 B4). */
export interface Preferences { presenter_name: string }

export interface Me { user: User; effective_user: User; viewing_as: User | null; is_admin: boolean }

export type ObjectType =
  | "investigation" | "project" | "cockpit-thread" | "attention-item" | "early-warning-list" | "borrower"
  | "whatif-thread" | "whatif-scenario" | "report" | "analysis" | "document" | "scorecard-validation"
  | "dealdesk-proposal" | "dealdesk-analysis" | "lens" | "crm-compliance"
  | "thread-answer";  // R16 t (M7): one answer or a whole thread, any module

export interface MailObject {
  type: ObjectType; id: string; label: string; href: string; summary?: string; meta?: Record<string, unknown>;
}
export type MailAttachment =
  | { kind: "object"; object: MailObject }
  | { kind: "file"; file_id: string; name: string; size: number; content_type: string; href: string };
export type OutAttachment = { kind: "object"; object: MailObject } | { kind: "file"; file_id: string };

export type Folder = "inbox" | "sent" | "drafts" | "archive" | "starred" | "all";
export interface MailCounts {
  inbox: number; unread: number; drafts: number; starred: number; archive: number; sent: number; notifications: number;
  /** Conversations in All mail (R3). */
  all?: number;
  /** Unread conversations per folder (R3). */
  unread_by_folder?: Partial<Record<Folder, number>>;
}
export interface ThreadSummary {
  thread_id: string | null; draft_id?: string; subject: string; snippet: string; last_at: string;
  last_sender?: User; participants: User[]; message_count: number; unread: boolean; starred: boolean;
  archived?: boolean; labels: string[]; has_attachments: boolean;
  /** Everyone who wrote in the conversation, in order (R3). */
  senders?: User[]; first_at?: string; has_files?: boolean;
}
export interface MailMessage {
  message_id: string; sender: User; to: User[]; cc: User[]; sent_at: string; body_html: string; body_text: string;
  /** Only the sender sees every Bcc recipient; a Bcc recipient sees only themself; everyone else none. */
  bcc?: User[];
  kind: "message" | "share"; in_reply_to: string | null; attachments: MailAttachment[]; unread: boolean;
}
export interface MailThread {
  thread_id: string; subject: string; messages: MailMessage[]; starred: boolean; archived: boolean; labels: string[];
  unread: boolean; mailbox: string;
}
export interface Draft {
  draft_id: string; to: string[]; cc: string[]; bcc?: string[]; subject: string; body_html: string; attachments: OutAttachment[];
  mode: Mode; thread_id: string | null; in_reply_to: string | null; updated_at?: string;
  files?: Record<string, { name: string; size: number }>;
}
export type Mode = "new" | "reply" | "reply_all" | "forward";
export interface Label { name: string; color: string; count: number; unread?: number }
/** Search filters, all optional; the server applies them (MAIL_API section 5.4). */
export type MailFilters = {
  q?: string; from?: string; to?: string; has_attachment?: boolean; label?: string; date_from?: string; date_to?: string;
};
export type BulkAction = "archive" | "unarchive" | "read" | "unread" | "star" | "unstar" | "label" | "unlabel" | "move";
export interface Notification {
  id: number; kind: string; title: string; href: string; from: User | null; created_at: string; read: boolean;
}
export interface SendPayload {
  to: string[]; cc: string[]; bcc?: string[]; subject: string; body_html: string; attachments: OutAttachment[]; mode: Mode;
  thread_id?: string | null; in_reply_to?: string | null; draft_id?: string | null;
}
export interface AuditEvent {
  id: number; at: string; actor: string | null; effective_user: string | null; action: string; target: string;
  detail: Record<string, unknown>;
}
export interface Mailbox { user: User; counts: MailCounts }

// ---------------------------------------------------------------- calls

const M = "/api/v1/mail";

export const core = {
  me: () => coreRequest<Me>("/api/v1/auth/me"),
  /** The first check on a page load: 200 whether or not anyone is signed in. */
  session: () => coreRequest<Me & { authenticated: boolean }>("/api/v1/auth/session"),
  login: (username: string, password: string) =>
    coreRequest<Me>("/api/v1/auth/login", { method: "POST", body: { username, password } }),
  logout: () => coreRequest<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  viewAs: (username: string | null) => coreRequest<Me>("/api/v1/auth/view-as", { method: "POST", body: { username } }),
  users: () => coreRequest<{ users: User[]; count: number }>("/api/v1/users"),
  preferences: () => coreRequest<{ preferences: Preferences }>("/api/v1/auth/preferences"),
  setPreferences: (p: Partial<Preferences>) =>
    coreRequest<{ preferences: Preferences }>("/api/v1/auth/preferences", { method: "PUT", body: p }),

  counts: (mailbox = "") => coreRequest<MailCounts>(`${M}/counts${qs({ mailbox })}`),
  folders: (mailbox = "") => coreRequest<{ folders: Folder[]; labels: Label[]; counts: MailCounts }>(`${M}/folders${qs({ mailbox })}`),
  threads: (p: { folder: Folder; unread?: boolean; mailbox?: string; limit?: number; offset?: number } & MailFilters) =>
    coreRequest<{ threads: ThreadSummary[]; total: number; mailbox: string }>(`${M}/threads${qs(p)}`),
  bulk: (thread_ids: string[], action: BulkAction, label = "") =>
    coreRequest<{ updated: number; thread_ids: string[] }>(`${M}/bulk`, { method: "POST", body: { thread_ids, action, label } }),
  thread: (id: string, mailbox = "") =>
    coreRequest<MailThread>(`${M}/threads/${encodeURIComponent(id)}${qs({ mailbox })}`),
  send: (payload: SendPayload, key?: string) =>
    coreRequest<{ thread_id: string; message_id: string; recipients: string[] }>(`${M}/send`,
      { method: "POST", body: payload, headers: key ? { "Idempotency-Key": key } : undefined }),
  share: (p: { to: string[]; cc?: string[]; note?: string; objects: MailObject[]; subject?: string }, key?: string) =>
    coreRequest<{ thread_id: string; message_id: string; recipients: string[]; audit_id: number; replayed?: boolean }>(
      `${M}/share`, { method: "POST", body: { cc: [], note: "", ...p }, headers: key ? { "Idempotency-Key": key } : undefined }),
  saveDraft: (d: Omit<Draft, "draft_id">, id?: string) =>
    id ? coreRequest<Draft>(`${M}/drafts/${id}`, { method: "PUT", body: d })
       : coreRequest<Draft>(`${M}/drafts`, { method: "POST", body: d }),
  draft: (id: string) => coreRequest<Draft>(`${M}/drafts/${id}`),
  deleteDraft: (id: string) => coreRequest<{ ok: boolean }>(`${M}/drafts/${id}`, { method: "DELETE" }),
  setRead: (id: string, read: boolean) =>
    coreRequest<unknown>(`${M}/threads/${encodeURIComponent(id)}/read`, { method: "POST", body: { read } }),
  setStar: (id: string, value: boolean) =>
    coreRequest<unknown>(`${M}/threads/${encodeURIComponent(id)}/star`, { method: "POST", body: { value } }),
  setArchive: (id: string, value: boolean) =>
    coreRequest<unknown>(`${M}/threads/${encodeURIComponent(id)}/archive`, { method: "POST", body: { value } }),
  setLabels: (id: string, add: string[], remove: string[]) =>
    coreRequest<{ labels: string[] }>(`${M}/threads/${encodeURIComponent(id)}/labels`, { method: "POST", body: { add, remove } }),
  createLabel: (name: string, color: string) => coreRequest<Label>(`${M}/labels`, { method: "POST", body: { name, color } }),
  deleteLabel: (name: string) => coreRequest<unknown>(`${M}/labels/${encodeURIComponent(name)}`, { method: "DELETE" }),
  notifications: (unread = false) =>
    coreRequest<{ notifications: Notification[]; unread: number }>(`${M}/notifications${qs({ unread })}`),
  notificationsRead: (id?: number) => coreRequest<unknown>(`${M}/notifications/read${qs({ id })}`, { method: "POST" }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return coreRequest<{ file_id: string; name: string; size: number; content_type: string }>(`${M}/files`, { method: "POST", form });
  },
  attentionCharts: (p: { domain: string; family: string; segment: string; period?: string; comparison?: string }) =>
    coreRequest<import("@/lib/v5/attention-figures").ChartsPayload>(`/api/v1/attention/charts${qs(p)}`),
  fileUrl: (fileId: string) => `${coreOrigin()}${M}/files/${fileId}`,
  mailboxes: () => coreRequest<{ mailboxes: Mailbox[] }>(`${M}/admin/mailboxes`),
  audit: (p: { actor?: string; action?: string; limit?: number; offset?: number }) =>
    coreRequest<{ events: AuditEvent[]; total: number }>(`${M}/audit${qs(p)}`),
};

/** Tell the sidebar and the header to re-read the unread counts. */
export const MAIL_CHANGED = "cp-v5-mail-changed";
export function mailChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(MAIL_CHANGED));
}

export function useMailCounts(enabled: boolean): MailCounts | null {
  const [counts, setCounts] = React.useState<MailCounts | null>(null);
  React.useEffect(() => {
    if (!enabled) return;
    let live = true;
    const load = () => core.counts().then((c) => { if (live) setCounts(c); }, () => undefined);
    void load();
    const t = window.setInterval(load, 15000);
    window.addEventListener(MAIL_CHANGED, load);
    return () => { live = false; window.clearInterval(t); window.removeEventListener(MAIL_CHANGED, load); };
  }, [enabled]);
  return enabled ? counts : null;
}

// ---------------------------------------------------------------- words

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "7 Jul 2026, 08:31" in UTC: a fixed format and zone, so server and browser agree. */
export function mailWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${hh}:${mm}`;
}

export function fileSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const OBJECT_LABEL: Record<ObjectType, string> = {
  investigation: "Investigation", project: "Project", "cockpit-thread": "Cockpit answer",
  "attention-item": "Attention item", "early-warning-list": "Early Warning list", borrower: "Borrower",
  "whatif-thread": "What-If thread", "whatif-scenario": "What-If scenario", report: "Word report",
  analysis: "Analysis", document: "Document", "scorecard-validation": "Scorecard validation",
  "dealdesk-proposal": "Deal Desk proposal", "dealdesk-analysis": "Deal Desk analysis", lens: "Lens",
  "crm-compliance": "CBUAE CRM compliance", "thread-answer": "Thread answer",
};

/** The message list's time: HH:MM (UTC) for today, "7 Jul" this year, "7 Jul 2025" before. */
export function listWhen(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (d.getUTCFullYear() === now.getUTCFullYear() && d.getUTCMonth() === now.getUTCMonth() && d.getUTCDate() === now.getUTCDate()) {
    return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
  }
  const day = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  return d.getUTCFullYear() === now.getUTCFullYear() ? day : `${day} ${d.getUTCFullYear()}`;
}

/** A message body split at its quoted reply: what the sender wrote, and the quoted text (shown on request). */
export function splitQuoted(html: string): { main: string; quoted: string } {
  const i = html.search(/<blockquote[\s>]/i);
  if (i < 0) return { main: html, quoted: "" };
  return { main: html.slice(0, i), quoted: html.slice(i) };
}

/** True when any search filter beyond the free text is set. */
export function hasFilters(f: MailFilters): boolean {
  return !!(f.from || f.to || f.has_attachment || f.label || f.date_from || f.date_to);
}

/** Frame an in-app path without its sidebar and header. */
export function embedHref(href: string): string {
  return href + (href.includes("?") ? "&" : "?") + "embed=1";
}

/** A reply's quoted text and subject, kept in one place so compose and tests agree. */
export function replySubject(subject: string): string {
  return /^re:/i.test(subject) ? subject : `Re: ${subject}`;
}

/** Who a reply-all addresses: everyone on the message but me. */
export function replyAllRecipients(msg: Pick<MailMessage, "sender" | "to" | "cc">, me: string): { to: string[]; cc: string[] } {
  const to = [msg.sender.username, ...msg.to.map((u) => u.username)].filter((u, i, a) => u !== me && a.indexOf(u) === i);
  const cc = msg.cc.map((u) => u.username).filter((u) => u !== me && !to.includes(u));
  return { to, cc };
}
