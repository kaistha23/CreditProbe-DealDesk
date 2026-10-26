/**
 * Rounds K and P (Deal Desk edition): the analysts' rules and Policy Docs as the rulebook, on the Deal Desk service
 * (`/api/v1/dealdesk/rules`, `/api/v1/dealdesk/rulebook`). Identity is the `cp_session` cookie.
 */
import { friendlyError } from "./errors.ts";

/** The Deal Desk service (same as `dealdesk.ts::dealdeskOrigin`, kept here so this module stays importable on its own). */
function dealdeskOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class RulesError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, init: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${dealdeskOrigin()}/api/v1/dealdesk${path}`, {
      method: init.method ?? "GET", credentials: "include", cache: "no-store",
      headers: init.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: init.form ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new RulesError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new RulesError(r.status, friendlyError("Deal Desk", r.status, body));
  return body as T;
}

const q = (p: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "" && v !== false) s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};

// ---------------------------------------------------------------- rules (Round K)

export type Scope = "me" | "team" | "bank";
export type DocType = "request" | "proposal" | "both";
export type RuleKind = "wording" | "avoid" | "units" | "include_section" | "section_order" | "heading" | "table" | "must_mention" | "instruction";
export type RuleStatus = "active" | "paused" | "removed";

export interface Rule {
  id: string; text: string; kind: RuleKind; kind_label: string; params: Record<string, unknown>; scope: Scope; scope_label: string;
  team: string; document: DocType; document_label: string; section: string; section_label: string; author: string; author_name: string;
  created_at: string; updated_at: string; updated_by: string; source_instruction: string; source: Record<string, unknown>;
  status: RuleStatus; origin: string; version: number; can_edit: boolean; deterministic: boolean;
}

export interface Suggestion {
  kind: RuleKind; kind_label: string; params: Record<string, unknown>; section: string; section_label: string; text: string;
  method: "rules" | "model"; deterministic: boolean; document: DocType; scope: Scope;
}

export interface SuggestResult {
  ask: boolean; question: string; why_not: string; suggestion: Suggestion; existing: Rule[];
  scopes: { id: Scope; label: string }[]; documents: { id: DocType; label: string }[];
}

export type AppliedStatus = "applied" | "in_place" | "flagged" | "model" | "noted" | "not_applicable";
export interface RuleApplied {
  rule_id: string; text: string; kind: RuleKind; scope: Scope; scope_label: string; author: string; author_name: string;
  document: DocType; section: string; origin: string; created_at: string; status: AppliedStatus; effect: string; count: number;
}

export interface RuleEvent { n: number; rule_id: string; at: string; by: string; by_name: string; action: string; before: unknown; after: unknown }

export const rules = {
  list: (p: { scope?: Scope | ""; document?: DocType | ""; mine?: boolean; status?: string } = {}) =>
    call<{ rules: Rule[]; counts: Record<Scope, number>; user: { username: string; name: string; team: string } }>(`/rules${q(p)}`),
  suggest: (b: { instruction: string; section?: string; section_label?: string; document?: DocType }) =>
    call<SuggestResult>("/rules/suggest", { method: "POST", body: b }),
  create: (b: { instruction?: string; text?: string; kind?: RuleKind; params?: Record<string, unknown>; scope: Scope; document: DocType;
    section?: string; section_label?: string; source?: Record<string, unknown> }) =>
    call<{ rule: Rule; message: string }>("/rules", { method: "POST", body: b }),
  update: (id: string, b: Partial<Pick<Rule, "text" | "scope" | "document" | "section" | "status">>) =>
    call<{ rule: Rule }>(`/rules/${encodeURIComponent(id)}`, { method: "PATCH", body: b }),
  remove: (id: string) => call<{ rule: Rule; message: string }>(`/rules/${encodeURIComponent(id)}`, { method: "DELETE" }),
  history: (id: string) => call<{ events: RuleEvent[] }>(`/rules/${encodeURIComponent(id)}/history`),
};

export const APPLIED_LABEL: Record<AppliedStatus, string> = {
  applied: "Applied", in_place: "Already followed", flagged: "For you to fix", model: "Given to the model", noted: "Check yourself",
  not_applicable: "Not relevant here",
};

/** The one line above the list: how many rules shaped this document and how many need the analyst. */
export function appliedLine(a: RuleApplied[]): string {
  const n = (s: AppliedStatus) => a.filter((x) => x.status === s).length;
  const changed = n("applied");
  const fix = n("flagged");
  const followed = n("in_place");
  const parts = [`${a.length} rule${a.length === 1 ? "" : "s"} in force`, `${changed} changed this document`, `${followed} already followed`];
  if (fix) parts.push(`${fix} for you to fix`);
  return parts.join(" · ");
}

// ---------------------------------------------------------------- rulebook (Round P)

export type AssessKind = "regulation" | "policy";
export interface ParamChange {
  param: string; check: string; label: string; segment: string; unit: string; current: unknown; current_display: string; proposed: unknown;
  proposed_display: string; direction: "tighter" | "looser" | "same" | "new"; where: string; source_in_force: string; clause: string; quote: string;
}
export interface DealImpact {
  proposal_id: string; customer: string; rm: string; status: string; sector: string; product: string; amount: number | null; currency: string;
  today: "pass" | "fail"; if_applied: "pass" | "fail";
  new_failures: { check: string; label: string; why: string; clause: string; quote: string }[];
  already_failing: { check: string; label: string; why: string }[];
}
export interface Impact {
  pipeline: { pending: number; reached: number; would_fail: number; headline: string;
    by_sector: { sector: string; pending: number; reached: number; would_fail: number }[] };
  deals: DealImpact[]; if_applied: string[]; if_not_applied: string[]; parameters: ParamChange[];
  checks: { check: string; label: string; param: string }[]; deal_types: { sectors: string[]; products: string[] }; method: string;
  written?: { table: string; key: string; version?: string; error?: string }[];
}
export interface Assessment {
  id: string; kind: AssessKind; title: string; reference: string; policy_doc_id: string; file_name: string; summary: string;
  reading: { summary: string; issuer: string; effective: string; method: "rules" | "model";
    changes: { param: string; label: string; segment: string; display: string; clause: string; quote: string }[];
    unread: { clause: string; quote: string }[] };
  impact: Impact; status: "pending" | "approved" | "rejected"; uploaded_by: string; uploaded_at: string; decided_by: string;
  decided_at: string; note: string; flagged: number;
}
export interface Flag { n: number; proposal_id: string; assessment_id: string; check_id: string; label: string; why: string; clause: string;
  quote: string; reference: string; status: "open" | "cleared"; at: string; by: string }
export interface GoldDiff { id: string; area: string; finding: string; today: string; gold: string;
  rule: { kind: RuleKind; params: Record<string, unknown>; text: string; document: DocType; section: string; section_label: string } }
export interface Gold { id: string; title: string; file_name: string; status: "pending" | "applied" | "dismissed"; uploaded_by: string;
  uploaded_at: string; applied_by: string; applied_at: string; applied: string[];
  comparison: { differences: GoldDiff[]; summary: string; today: { sample: string; sections: string[] }; gold: { sections: string[] } } }
export interface Kind { id: "regulation" | "policy" | "gold" | "rules"; label: string; about: string; count: number }

export const rulebook = {
  kinds: () => call<{ kinds: Kind[] }>("/rulebook/kinds"),
  assess: (file: File, meta: { kind: AssessKind; title?: string; reference?: string; policy_doc_id?: string }) => {
    const f = new FormData();
    f.append("file", file);
    f.append("kind", meta.kind);
    if (meta.title) f.append("title", meta.title);
    if (meta.reference) f.append("reference", meta.reference);
    if (meta.policy_doc_id) f.append("policy_doc_id", meta.policy_doc_id);
    return call<{ assessment: Assessment; question: string }>("/rulebook/assess", { method: "POST", form: f });
  },
  assessments: (p: { kind?: AssessKind | ""; policy_doc_id?: string; status?: string } = {}) =>
    call<{ assessments: Assessment[] }>(`/rulebook/assessments${q(p)}`),
  assessment: (id: string) => call<{ assessment: Assessment }>(`/rulebook/assessments/${encodeURIComponent(id)}`),
  decide: (id: string, approve: boolean, note = "", policy_doc_id = "") =>
    call<{ assessment: Assessment; flagged: number; message: string }>(`/rulebook/assessments/${encodeURIComponent(id)}/decision`,
      { method: "POST", body: { approve, note, policy_doc_id } }),
  flags: (p: { proposal_id?: string; assessment_id?: string; status?: string } = {}) => call<{ flags: Flag[] }>(`/rulebook/flags${q(p)}`),
  deal: (pid: string) => call<{ flags: Flag[] }>(`/rulebook/deals/${encodeURIComponent(pid)}`),
  gold: () => call<{ gold: Gold[] }>("/rulebook/gold"),
  goldUpload: (file: File) => {
    const f = new FormData();
    f.append("file", file);
    return call<{ gold: Gold; question: string }>("/rulebook/gold", { method: "POST", form: f });
  },
  goldApply: (id: string, ids: string[]) =>
    call<{ gold: Gold; rules: Rule[]; message: string }>(`/rulebook/gold/${encodeURIComponent(id)}/apply`, { method: "POST", body: { ids } }),
  goldDismiss: (id: string) => call<{ gold: Gold }>(`/rulebook/gold/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: {} }),
};

/** Which rulebook kind a Policy Docs document is: circulars and regulations are regulation; policies and guidelines are policy. */
export function assessKindOf(docKind: string): AssessKind {
  return docKind === "circular" || docKind === "regulation" ? "regulation" : "policy";
}
