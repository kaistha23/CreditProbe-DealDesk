/**
 * PLAN_R12 Session G (R11_FEEDBACK I2–I5): Parameters and policy on the Deal Desk service (/api/v1/dealdesk/parameters,
 * /api/v1/dealdesk/policies/*). Upload a policy, review what was found, not found and new, keep or define each value,
 * approve to create a new parameter version with provenance, or reject; the policy library with Word downloads; every
 * parameter's source; the Excel export. The helpers below are pure and tested (dealdesk-params.test.ts).
 */
import { friendlyError } from "./errors.ts";

const ENGINE = "/api/v1/dealdesk";

export function paramsOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class ParamsError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${paramsOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new ParamsError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new ParamsError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

// ---------------------------------------------------------------- schemas

export interface Provenance {
  kind: "policy" | "manual"; text: string;
  policy_id?: string; policy?: string; policy_version?: number; clause?: string; quote?: string; approved_by?: string; approved_on?: string;
  edited_from?: unknown; owner?: string; by?: string; date?: string; note?: string;
}
export interface ParamRow {
  id: string; group: string; table: string; key: string; field: string; label: string; unit: string; value: unknown; display: string;
  version: string; effective_from: string; owner: string; why: string; where: string; editable: boolean; kind?: string;
  appetite?: unknown; trigger?: unknown; basis?: string; provenance: Provenance;
}
export interface ParametersView {
  rows: ParamRow[]; groups: string[]; version: string; from_policy: number; total: number;
  active_policies: { policy_id: string; version: number; title: string }[];
}
export type Change = "same" | "tighter" | "looser" | "changed" | "new" | "";
export type ReviewStatus = "found" | "not_found" | "new";
export type Action = "accept" | "edit" | "keep" | "define" | "skip" | "add_parameter" | "add_rule";
export interface Proposal {
  item_id: string; field: string; subfield: string; proposed: unknown; in_force: unknown; display: string; in_force_display: string;
  change: Change; conversion: string; clause: string; quote: string; label: string; conflict?: { regulation: string; message: string } | null;
}
export interface ReviewRow {
  id: string; group: string; table: string; key: string; field: string; label: string; unit: string; display: string; version: string;
  effective_from: string; owner: string; status: ReviewStatus; change: Change; decision: Action; options: Action[]; proposals: Proposal[];
  item_id?: string; clause?: string; quote?: string; has_rule?: boolean; value?: unknown; edited_value?: number; defined_value?: unknown;
}
export type PolicyStatus = "pending" | "active" | "superseded" | "rejected" | "trial";
export interface PolicyRecord {
  policy_id: string; version: number; title: string; issuer?: string; document_version?: string; original_name: string; format: string;
  sha256: string; effective_date: string; uploaded_by: string; uploaded_at: string; status: PolicyStatus; session_id: string;
  clauses: number; tables: number; conflicts: number; summary: { found: number; changes: number; same: number; not_found: number; new: number; text: string };
  decided_by: string; decided_at: string; param_versions: { table: string; version: string; effective_from: string }[]; note: string;
  review?: ReviewRow[]; self_approved?: boolean; rules_added?: string[];
  /** Held in Data Domains (dd_policy) but not uploaded here: shown read-only, nothing to review. */
  external?: boolean; source_file?: string;
}
export interface PolicyView {
  policy_id: string; version: number; title: string;
  sections: { section: string; title: string; clauses: { clause: string; text: string }[] }[];
  tables: { table: string; caption: string; header: string[]; rows: string[][] }[];
}
export interface ChangeRow {
  at: string; table: string; parameter: string; key: string; from: string; to: string; version: string; previous: string; effective_from: string;
  by: string; reason: string; source: string;
}
export interface Choice { action: Action; text?: string }

export const policiesApi = {
  parameters: () => call<ParametersView>("/parameters"),
  changes: () => call<{ changes: ChangeRow[] }>("/parameters/changes"),
  list: () => call<{ policies: PolicyRecord[] }>("/policies"),
  get: (pid: string, v: number) => call<PolicyRecord>(`/policies/${encodeURIComponent(pid)}/${v}`),
  view: (pid: string, v: number) => call<PolicyView>(`/policies/${encodeURIComponent(pid)}/${v}/view`),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<PolicyRecord>("/policies/upload", { method: "POST", body: f }); },
  sample: () => call<PolicyRecord>("/policies/sample", { method: "POST" }),
  approve: (pid: string, v: number, decisions: Record<string, { action: Action; value?: unknown }>) =>
    call<{ policy: PolicyRecord; parameters: ParametersView }>(`/policies/${encodeURIComponent(pid)}/${v}/approve`,
      { method: "POST", body: JSON.stringify({ decisions }) }),
  reject: (pid: string, v: number, note: string) =>
    call<{ policy: PolicyRecord }>(`/policies/${encodeURIComponent(pid)}/${v}/reject`, { method: "POST", body: JSON.stringify({ note }) }),
  docxUrl: (pid: string, v: number) => `${paramsOrigin()}${ENGINE}/policies/${encodeURIComponent(pid)}/${v}/document.docx`,
  originalUrl: (pid: string, v: number) => `${paramsOrigin()}${ENGINE}/policies/${encodeURIComponent(pid)}/${v}/original`,
  excelUrl: () => `${paramsOrigin()}${ENGINE}/parameters/export.xlsx`,
};

/** Download a file from the service with the session cookie (a link would lose it across ports). */
export async function download(url: string, fallbackName: string): Promise<void> {
  let r: Response;
  try {
    r = await fetch(url, { credentials: "include", cache: "no-store" });
  } catch {
    throw new ParamsError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  if (!r.ok) throw new ParamsError(r.status, friendlyError("Deal Desk", r.status, await r.json().catch(() => null)));
  const cd = r.headers.get("Content-Disposition") ?? "";
  const name = fileName(cd) || fallbackName;
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ---------------------------------------------------------------- pure helpers

/** The file name in a Content-Disposition header (RFC 5987 filename* first). */
export function fileName(cd: string): string {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) { try { return decodeURIComponent(star[1].trim()); } catch { return star[1].trim(); } }
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1].trim() : "";
}

/** The source chip beside a value: "Policy v2 · 4.2" or "Manual". */
export function sourceChip(p: Provenance): { label: string; tone: "accent" | "neutral" } {
  if (p.kind === "policy") return { label: `Policy v${p.policy_version ?? "?"}${p.clause ? ` · ${p.clause}` : ""}`, tone: "accent" };
  return { label: "Manual", tone: "neutral" };
}

/** The first line of every (i): who or what set the value. */
export function provenanceLine(p: Provenance): string {
  if (p.text) return p.text;
  if (p.kind === "policy") return `Set by ${p.policy} v${p.policy_version}, clause ${p.clause}: ‘${p.quote}’`;
  return `Set manually by ${p.owner ?? p.by ?? "its owner"} on ${p.date ?? ""}`.trim();
}

export function groupRows<T extends { group: string }>(rows: T[], groups: string[]): { group: string; rows: T[] }[] {
  const order = groups.length ? groups : [...new Set(rows.map((r) => r.group))];
  return order.map((g) => ({ group: g, rows: rows.filter((r) => r.group === g) })).filter((x) => x.rows.length);
}

export const STATUS_LABEL: Record<ReviewStatus, string> = { found: "Found in the policy", new: "New in the policy", not_found: "Not in the policy" };
export const ACTION_LABEL: Record<Action, string> = {
  accept: "Use the policy's value", edit: "Use another value", keep: "Keep the value in force", define: "Define a value now",
  skip: "Leave out", add_parameter: "Add as a parameter", add_rule: "Add as a review rule",
};

export function countBy(rows: ReviewRow[]): Record<ReviewStatus, number> {
  return { found: rows.filter((r) => r.status === "found").length, new: rows.filter((r) => r.status === "new").length,
           not_found: rows.filter((r) => r.status === "not_found").length };
}

export function changeTone(c: Change): "positive" | "negative" | "warning" | "neutral" | "accent" {
  return c === "tighter" ? "positive" : c === "looser" ? "negative" : c === "changed" ? "warning" : c === "new" ? "accent" : "neutral";
}

export function changeWord(c: Change): string {
  return ({ same: "Same", tighter: "Tighter", looser: "Looser", changed: "Changed", new: "New", "": "" } as const)[c];
}

/** Rates and shares are typed in %; multiples, years, SAR m and bps as they read. */
export function isPercentUnit(unit: string): boolean {
  return ["rate", "share", "ccf", "pct", "rate_map"].includes(unit);
}

/** A typed value for "Use another value" / "Define a value now": one number, or "name: value" lines for a map. */
export function parseValue(text: string, unit: string, current?: unknown): { value?: unknown; error?: string } {
  const t = (text ?? "").trim();
  if (!t) return { error: "Type a value." };
  const num = (s: string): number | null => {
    const x = Number(s.replace(/[%x,\s]|bps|years?|SAR|m$/gi, ""));
    return Number.isFinite(x) ? (isPercentUnit(unit) ? x / 100 : x) : null;
  };
  const isMap = current !== null && typeof current === "object" && !Array.isArray(current);
  if (!isMap) {
    if (unit === "rating") return /^[A-Z]{1,3}[+-]?$/.test(t) ? { value: t } : { error: `"${t}" is not a rating such as BB-.` };
    const v = num(t);
    if (v === null) return { error: `"${t}" is not a number.` };
    if (isPercentUnit(unit) && (v < 0 || v > 1)) return { error: "A share or rate is between 0% and 100%." };
    return { value: v };
  }
  const out: Record<string, unknown> = {};
  for (const line of t.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const i = line.lastIndexOf(":");
    if (i < 0) return { error: `"${line}" needs "name: value".` };
    const k = line.slice(0, i).trim();
    const raw = line.slice(i + 1).trim();
    if (unit === "text_map") { out[k] = raw; continue; }
    const v = num(raw);
    if (v === null) return { error: `"${raw}" is not a number.` };
    out[k] = v;
  }
  return { value: out };
}

/** The value in force as editable text (rates in %). */
export function valueText(value: unknown, unit: string): string {
  const f = (x: unknown) => (typeof x === "number" && isPercentUnit(unit) ? String(+(x * 100).toFixed(4)) : String(x));
  if (value !== null && typeof value === "object" && !Array.isArray(value)) return Object.entries(value as Record<string, unknown>).map(([k, x]) => `${k}: ${f(x)}`).join("\n");
  return f(value);
}

/** The unit a typed value is read in: a found sub-value (one tenor of the tenor caps) is one number, whatever its map's unit. */
export function valueUnit(r: ReviewRow): string {
  if (r.status === "found" && r.proposals[0]?.subfield) return "number";
  return r.unit;
}

/** The shape a typed value must have: the policy's value for a found row, the value in force for a row to define. */
export function valueShape(r: ReviewRow): unknown {
  if (r.status === "found") return r.proposals[0]?.subfield ? undefined : r.proposals[0]?.proposed;
  return r.value;
}

/** Which actions need a typed value. */
export function needsValue(a: Action): boolean {
  return a === "edit" || a === "define";
}

/** The approve body: only rows whose choice differs from the default, with parsed values. Errors keyed by row id. */
export function decisionBody(rows: ReviewRow[], choices: Record<string, Choice>): {
  decisions: Record<string, { action: Action; value?: unknown }>; errors: Record<string, string>;
} {
  const decisions: Record<string, { action: Action; value?: unknown }> = {};
  const errors: Record<string, string> = {};
  for (const r of rows) {
    const c = choices[r.id];
    if (!c || c.action === r.decision) continue;
    if (!r.options.includes(c.action)) { errors[r.id] = `${ACTION_LABEL[c.action]} is not possible here.`; continue; }
    if (needsValue(c.action)) {
      const p = parseValue(c.text ?? "", valueUnit(r), valueShape(r));
      if (p.error) { errors[r.id] = p.error; continue; }
      decisions[r.id] = { action: c.action, value: p.value };
    } else {
      decisions[r.id] = { action: c.action };
    }
  }
  return { decisions, errors };
}

/** What approving will do, in one sentence (shown above the Approve button). */
export function approvePreview(rows: ReviewRow[], choices: Record<string, Choice>): string {
  const act = (r: ReviewRow) => choices[r.id]?.action ?? r.decision;
  const set = rows.filter((r) => r.status === "found" && (act(r) === "accept" || act(r) === "edit") && (act(r) === "edit" || r.change !== "same"));
  const kept = rows.filter((r) => r.status === "found" && act(r) === "keep").length;
  const defined = rows.filter((r) => r.status === "not_found" && act(r) === "define").length;
  const added = rows.filter((r) => r.status === "new" && (act(r) === "add_parameter" || act(r) === "add_rule")).length;
  const tables = new Set([...set, ...rows.filter((r) => r.status === "not_found" && act(r) === "define")].map((r) => r.table));
  if (!set.length && !defined && !added) return "Approving records the policy as active; no parameter value changes.";
  const parts = [`${set.length} value${set.length === 1 ? "" : "s"} from the policy`];
  if (defined) parts.push(`${defined} defined now`);
  if (added) parts.push(`${added} new item${added === 1 ? "" : "s"} added`);
  return `Approving writes ${parts.join(", ")} as a new version of ${tables.size + (added ? 1 : 0)} table${tables.size + (added ? 1 : 0) === 1 ? "" : "s"}`
    + `${kept ? `; ${kept} kept at the value in force` : ""}. Reject changes nothing.`;
}

export function statusTone(s: PolicyStatus): "positive" | "neutral" | "warning" | "negative" {
  return s === "active" ? "positive" : s === "pending" ? "warning" : s === "rejected" ? "negative" : "neutral"; // trial, superseded
}

export function statusWord(s: PolicyStatus): string {
  return ({ pending: "Awaiting approval", active: "Active", superseded: "Superseded", rejected: "Rejected", trial: "Trial only" } as const)[s] ?? s;
}

export function shortDate(iso: string): string {
  const d = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  if (!d) return iso ?? "";
  const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(d[2]) - 1];
  return `${Number(d[3])} ${m} ${d[1]}`;
}

export const ACCEPT = ".docx,.pdf,.md,.txt";
export function acceptable(name: string): boolean {
  return /\.(docx|pdf|md|txt)$/i.test(name);
}
