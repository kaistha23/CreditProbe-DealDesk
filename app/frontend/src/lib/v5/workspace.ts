/**
 * v5 Workspace client: My workspace / Inbox, Projects, Investigations, Analyses
 * and Documents. (Messages are CreditProbe Mail: lib/v5/core.ts.)
 *
 * Talks ONLY to the Core service (port 8505 by default, `NEXT_PUBLIC_WORKSPACE_API`).
 * It never imports the Cockpit client or the legacy `lib/api.ts`. Every call is
 * answered for the signed-in user (session cookie); nothing names a user.
 * Amounts arrive in SAR million, as the books publish them.
 */
import { friendlyError } from "./errors.ts";
import * as React from "react";

import { core } from "@/lib/v5/core";

export function wsOrigin(): string {
  return (process.env.NEXT_PUBLIC_WORKSPACE_API ?? "http://127.0.0.1:8505").replace(/\/$/, "");
}

export class WsError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${wsOrigin()}/api/v1/workspace${path}`, {
      method: init?.method ?? "GET",
      cache: "no-store",
      credentials: "include",
      headers: init?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new WsError(0, `Workspace is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = friendlyError("Workspace", response.status, body);
    throw new WsError(response.status, message);
  }
  return body as T;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "" && v !== false) out.set(k, String(v));
  const s = out.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- types

export interface Person { id: string; name: string; title: string; initials: string }
export interface WsLink { label: string; href: string; type: string }
export type Labelled = object;
export type Envelope = object;

export type InboxKind = "message" | "mention" | "assignment" | "notification";
export interface InboxItem extends Labelled {
  id: string; kind: InboxKind; title: string; body: string; href: string; actor: Person | null; created_at: string;
  read: boolean; unread: number; source: string;
}
export interface Inbox extends Envelope {
  user: Person; items: InboxItem[]; total: number; unread: Record<InboxKind, number>; unread_total: number;
}

export type RequestType = "fyi" | "review" | "action";
export type RequestStatus = "open" | "in_review" | "responded" | "closed";

export interface MailCountsLite { inbox: number; unread: number; drafts: number; starred: number; archive: number; sent: number; notifications: number }
export interface Summary extends Envelope {
  user: Person; messages: MailCountsLite; inbox: Record<InboxKind, number>; inbox_unread: number;
  counts: { projects: number; investigations: number; analyses: number; documents: number };
}

/** My workspace as the home page (PLAN_R3 S3-4): GET /api/v1/workspace/home. */
export interface HomeItem { id: string; title: string; kind: string; status?: string | null; period?: string | null;
  owner?: Person | null; when: string; href: string }
export interface Home extends Envelope {
  user: Person & { books: string[]; team?: string; role?: string };
  tasks: { open: { id: number; title: string; detail: string; status: string; project: { id: string; name: string };
                   href: string; link_label: string }[];
           assignments: InboxItem[]; total: number };
  mentions: { items: InboxItem[]; unread: number };
  mail: { unread: number; items: InboxItem[] };
  mine: { analyses: HomeItem[]; investigations: HomeItem[]; projects: HomeItem[];
          counts: { analyses: number; investigations: number; projects: number } };
  recent: HomeItem[];
  reviews: { available: boolean; items: { id: string; title: string; status: string; due_date: string | null;
                                           owner?: { name: string } | null; href: string }[] };
}

export type TaskStatus = "todo" | "in_progress" | "done";
export interface Task {
  id: number; title: string; detail: string; kind: string; status: TaskStatus; assignee: Person | null; href: string;
  link_label: string; demo: boolean;
}
export interface Project extends Labelled {
  id: string; name: string; description: string; owner: Person | null; status: string; due_at: string | null;
  period: string | null; members: Person[]; created_at: string; updated_at: string; items: number; items_done: number;
}
export interface ProjectDetail extends Project, Envelope {
  links: WsLink[]; tasks: Task[];
  investigations: { id: string; title: string; status: string }[];
  analyses: { id: string; title: string; period: string }[];
  documents: { id: string; title: string; status: string }[];
}

export type Unit = "text" | "sar_mn" | "pct" | "int";
export interface Figure { key: string; label: string; period: string; value: number; unit: Unit; source: string }
export interface Investigation extends Labelled {
  id: string; title: string; summary: string; sector: string | null; period: string | null;
  compare_period: string | null; status: string; owner: Person | null; project_id: string | null; figures: Figure[];
  notes: number; created_at: string; updated_at: string;
}
export interface TimelineEntry { id: number; author: Person; body: string; kind: "note" | "status"; created_at: string; demo: boolean }
export interface InvestigationDetail extends Investigation, Envelope {
  links: WsLink[]; timeline: TimelineEntry[]; analyses: { id: string; title: string; period: string }[];
  statuses: string[]; project?: { id: string; name: string } | null;
}

export interface Column { key: string; label: string; unit: Unit }
export interface Analysis extends Labelled {
  id: string; title: string; description: string; period: string | null; source: string; owner: Person | null;
  project_id: string | null; investigation_id: string | null; created_at: string;
}
export interface AnalysisListItem extends Analysis { rows: number }
export interface AnalysisDetail extends Analysis, Envelope {
  columns: Column[]; rows: Record<string, string | number>[]; totals: Record<string, string | number> | null;
  notes: string; links: WsLink[];
}

export interface Section { heading: string; body: string }
export interface DocumentItem extends Labelled {
  id: string; title: string; kind: string; status: string; owner: Person | null; project_id: string | null;
  summary: string; created_at: string; updated_at: string; section_count: number; words: number;
}
export interface DocumentDetail extends DocumentItem, Envelope { sections: Section[]; links: WsLink[] }

/** Something from another screen added to an investigation or a report: text and a link back. */
export interface AddItem { title: string; body: string; href: string; label: string; type: string }
export const DOCUMENT_KINDS = ["Report", "Committee pack", "Risk committee report", "Portfolio review", "Credit memo", "Scenario report"] as const;

// ---------------------------------------------------------------- calls

export const ws = {
  /** The user directory as workspace people (id is the username). */
  users: async () => {
    const r = await core.users();
    return { users: r.users.map((u): Person => ({ id: u.username, name: u.name, title: u.role, initials: u.initials })) };
  },
  summary: () => request<Summary>("/summary"),
  home: () => request<Home>("/home"),
  inbox: (kind = "") => request<Inbox>(`/inbox${qs({ kind })}`),
  inboxRead: (id: string) => request<unknown>(`/inbox/${encodeURIComponent(id)}/read`, { method: "POST" }),

  projects: () => request<{ projects: Project[] }>("/projects"),
  project: (id: string) => request<ProjectDetail>(`/projects/${encodeURIComponent(id)}`),
  createProject: (payload: { name: string; description: string; period: string; members: string[]; domains?: string[]; instructions?: string }) =>
    request<ProjectDetail>(`/projects`, { method: "POST", body: payload }),
  addTask: (id: string, payload: { title: string; detail: string; assignee_id: string | null }) =>
    request<ProjectDetail>(`/projects/${encodeURIComponent(id)}/tasks`, { method: "POST", body: payload }),
  taskStatus: (id: string, taskId: number, status: TaskStatus) =>
    request<ProjectDetail>(`/projects/${encodeURIComponent(id)}/tasks/${taskId}/status`,
      { method: "POST", body: { status } }),

  investigations: () => request<Envelope & { investigations: Investigation[]; statuses: string[] }>("/investigations"),
  investigation: (id: string) => request<InvestigationDetail>(`/investigations/${encodeURIComponent(id)}`),
  addNote: (id: string, body: string, mentions: string[] = []) =>
    request<InvestigationDetail>(`/investigations/${encodeURIComponent(id)}/notes`,
      { method: "POST", body: { body, mentions } }),
  investigationStatus: (id: string, status: string, note = "") =>
    request<InvestigationDetail>(`/investigations/${encodeURIComponent(id)}/status`,
      { method: "POST", body: { status, note } }),

  createInvestigation: (title: string, summary = "") =>
    request<InvestigationDetail>("/investigations", { method: "POST", body: { title, summary } }),
  addToInvestigation: (id: string, item: AddItem) =>
    request<InvestigationDetail>(`/investigations/${encodeURIComponent(id)}/items`, { method: "POST", body: item }),
  createDocument: (title: string, kind: string) =>
    request<DocumentDetail>("/documents", { method: "POST", body: { title, kind } }),
  addToDocument: (id: string, item: AddItem) =>
    request<DocumentDetail>(`/documents/${encodeURIComponent(id)}/sections`, { method: "POST", body: item }),

  analyses: () => request<Envelope & { analyses: AnalysisListItem[] }>("/analyses"),
  analysis: (id: string) => request<AnalysisDetail>(`/analyses/${encodeURIComponent(id)}`),
  documents: () => request<Envelope & { documents: DocumentItem[] }>("/documents"),
  document: (id: string) => request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`),
};

// ---------------------------------------------------------------- loading

/**
 * Load once per key. Results are stored WITH the key they answer, so a view
 * whose key has changed reads as loading until its own answer arrives -- no
 * state is set synchronously inside the effect.
 */
export function useWs<T>(load: () => Promise<T>, key: string, group?: string) {
  const [state, setState] = React.useState<{ key: string | null; group?: string; data: T | null; error: string | null }>(
    { key: null, data: null, error: null });
  const ref = React.useRef(load);
  React.useEffect(() => { ref.current = load; });
  React.useEffect(() => {
    let live = true;
    ref.current().then(
      (data) => { if (live) setState({ key, group, data, error: null }); },
      (err: unknown) => { if (live) setState({ key, group, data: null, error: err instanceof Error ? err.message : String(err) }); },
    );
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const current = state.key === key;
  // `group`: while a key of the same group reloads, keep showing its last answer (a conversation after a star).
  const stale = !current && group !== undefined && state.group === group;
  return { data: current || stale ? state.data : null, error: current ? state.error : null, loading: !current };
}

// ---------------------------------------------------------------- words

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "7 Jul 2026, 08:31 UTC" -- fixed format and zone, so server and browser agree. */
export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${hh}:${mm} UTC`;
}

/** "9 Jul 2026" for a date or a timestamp. */
export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "SAR 18,695.2m" -- SAR million, as the books publish them. */
export function sarMn(v: number | null | undefined, places = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `SAR ${Number(v).toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places })}m`;
}

export function formatValue(v: unknown, unit: Unit): string {
  if (v === null || v === undefined || v === "") return "—";
  if (unit === "text") return String(v);
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (unit === "sar_mn") return sarMn(n, Math.abs(n) < 10 ? 2 : 1);
  if (unit === "pct") return `${n.toFixed(2)}%`;
  return n.toLocaleString("en-US");
}

export function words(status: string | null | undefined): string {
  if (!status) return "";
  const s = status.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const KIND_LABEL: Record<InboxKind, string> = {
  message: "Message",
  mention: "Mention",
  assignment: "Assignment",
  notification: "Notification",
};
