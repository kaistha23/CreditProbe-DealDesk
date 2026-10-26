/**
 * Rounds B and G: Borrower 360 inside the deal and the customer file, and the counterparty graph's cross-deal signals, on the
 * Deal Desk service (/api/v1/dealdesk/borrower-360, /api/v1/dealdesk/graph). The helpers below are pure and tested
 * (dealdesk-b360.test.ts).
 */
import { friendlyError } from "./errors.ts";

const B360 = "/api/v1/dealdesk/borrower-360";
const GRAPH = "/api/v1/dealdesk/graph";

export function b360Origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export interface Source {
  kind: "bank" | "upload" | "agent" | "engine" | "deal" | string; label: string; date: string | null; date_label: string | null;
  relation?: string; domain?: string; doc_id?: string; doc_label?: string; page?: number | null; line?: number | null; synthetic?: boolean;
}
export interface Fact { label: string; value: unknown; unit: string; source: Source; note?: string }
export interface Column { key: string; label: string; unit: string }
export interface Table { id: string; title: string; columns: Column[]; rows: Record<string, unknown>[]; source: Source }
export interface B360Section { key: string; title: string; facts: Fact[]; tables: Table[]; plain_words: string[]; empty: string; n: number }

export interface Evidence {
  edge_id: string; rel: string; source_kind: string; source_label: string; doc_id?: string | null; doc_label?: string | null;
  page?: number | null; line?: number | null; date?: string | null; author?: string; synthetic: boolean; proposal_id?: string | null;
}
export interface Standing {
  status: string; label: string; note: string; source_kind: string; source_label: string; doc_label?: string | null; page?: number | null;
  date?: string | null; synthetic?: boolean; proposal_id?: string;
}
export interface Signal {
  signal_id: string; rule: "counterparty_distress" | "borrower_is_counterparty" | "counterparty_in_pipeline" | string;
  severity: "high" | "medium" | "low"; title: string; sentence: string;
  focal: { node_id: string; name: string; proposal_id: string | null; cif?: string | null };
  counterparty: { node_id: string; name: string; kind: string; role: string; roles: string[]; role_label: string; cif?: string | null; via: string };
  standing: Standing[]; other_deals: { proposal_id: string; status: string | null; name?: string | null }[]; evidence: Evidence[];
  synthetic: boolean; href: string;
}
export interface SignalSummary { high: number; medium: number; low: number; total: number }

export interface Borrower360 {
  subject: { cif: string; name: string; cr_number: string; group_id: string; group_name: string; sector: string; rating: string; existing: boolean;
             proposal_id: string; pack_key: string | null; node_id: string | null };
  as_of: string; as_of_label: string; plain_words: string[]; sections: B360Section[]; signals: Signal[]; signals_summary: SignalSummary; ms: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${b360Origin()}${path}`, { credentials: "include", cache: "no-store", ...init });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export const b360Api = {
  deal: (pid: string, refresh = false) => call<Borrower360>(`${B360}/deal/${encodeURIComponent(pid)}${refresh ? "?refresh=true" : ""}`),
  customer: (cif: string, refresh = false) => call<Borrower360>(`${B360}?cif=${encodeURIComponent(cif)}${refresh ? "&refresh=true" : ""}`),
  dealSignals: (pid: string) => call<{ signals: Signal[]; summary: SignalSummary }>(`${GRAPH}/deal/${encodeURIComponent(pid)}`),
  removeLink: (edgeId: string) => call<{ removed: string }>(`${GRAPH}/edge/${encodeURIComponent(edgeId)}`, { method: "DELETE" }),
};

// ------------------------------------------------------------------------------------------------ pure helpers

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-21" → "21 Oct 2026"; anything else as given. */
export function dmy(v: unknown): string {
  const s = String(v ?? "");
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(s);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : s;
}

function n(v: unknown): number | null {
  if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

/** A value in its unit: sar_mn → "SAR 12.4m", sar → "SAR 1.2m" (from units), pct → "81.2%", count/days/number → "12", date → "21 Oct 2026". */
export function fmtValue(v: unknown, unit: string): string {
  if (v === null || v === undefined || v === "") return "–";
  const x = n(v);
  switch (unit) {
    case "sar_mn":
    case "money":
      return x === null ? String(v) : `SAR ${x.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`;
    case "sar":
      if (x === null) return String(v);
      return Math.abs(x) >= 1e6 ? `SAR ${(x / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`
        : `SAR ${x.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    case "pct":
    case "percent":
      return x === null ? String(v) : `${x.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
    case "count":
    case "days":
    case "number":
    case "int":
      return x === null ? String(v) : x.toLocaleString("en-US", { maximumFractionDigits: Number.isInteger(x) ? 0 : 2 });
    case "ratio":
    case "x":
      return x === null ? String(v) : `${x.toFixed(2)}x`;
    case "date":
      return dmy(v);
    default:
      if (x !== null && typeof v === "number") return x.toLocaleString("en-US", { maximumFractionDigits: 2 });
      return String(v).replace(/_/g, " ");
  }
}

/** The unit of a table cell ("@unit": the row carries its own; the b360 units sar_mn / pct / ratio / text). */
export function cellUnit(col: Column, row: Record<string, unknown>): string {
  if (col.unit === "@unit") return String(row.unit ?? "text");
  return col.unit;
}

/** Where a fact or a link was read: "C2-25 · Top customers and suppliers, page 1, line 18 · 30 Sep 2026" or "Account conduct · deal_desk.dd_account_conduct · 31 Aug 2026". */
export function sourceLine(s: Pick<Source, "label" | "doc_label" | "page" | "line" | "relation" | "domain" | "date"> & { synthetic?: boolean }): string {
  const bits: string[] = [];
  if (s.doc_label) {
    bits.push(s.doc_label + (s.page ? `, page ${s.page}` : "") + (s.line ? `, line ${s.line}` : ""));
  } else {
    bits.push(s.label);
    if (s.relation) bits.push(s.domain ? `${s.domain}.${s.relation}` : s.relation);
  }
  if (s.date) bits.push(dmy(s.date));
  return bits.join(" · ") + (s.synthetic ? " · seeded link" : "");
}

/** The evidence of a link as a source line. */
export function evidenceLine(e: Evidence): string {
  return sourceLine({ label: e.source_label, doc_label: e.doc_label ?? undefined, page: e.page, line: e.line, date: e.date ?? null, synthetic: e.synthetic });
}

export const SEVERITY_TONE = { high: "negative", medium: "warning", low: "neutral" } as const;

export const RULE_LABEL: Record<string, string> = {
  counterparty_distress: "Counterparty in difficulty",
  borrower_is_counterparty: "This borrower is their counterparty",
  counterparty_in_pipeline: "Counterparty in another deal",
};

/** The line on the deal: "2 counterparty signals, 1 high: Al Kharj United Contracting, a supplier, is …". Empty when there is nothing to say. */
export function signalLine(sig: Signal[]): string {
  const hard = sig.filter((s) => s.severity !== "low");
  if (!sig.length) return "";
  const high = sig.filter((s) => s.severity === "high").length;
  const lead = (hard[0] ?? sig[0]).title;
  return `${sig.length} counterparty signal${sig.length === 1 ? "" : "s"}${high ? `, ${high} high` : ""}: ${lead}.`;
}

/** Sections in the order the panel tabs show them, with their tab label and count. */
export const TAB_LABEL: Record<string, string> = {
  deals: "Deals and proposals", core: "Core banking", limits: "Limits", bureau: "Bureau", collateral: "Collateral", group: "Group",
  financials: "Financials", learned: "Learned from uploads",
};

export function tabs(sections: B360Section[], summary: SignalSummary | null): { key: string; label: string; count: number }[] {
  const out = [{ key: "overview", label: "Overview", count: 0 }, { key: "counterparty", label: "Counterparty exposure", count: summary?.total ?? 0 }];
  for (const s of sections) out.push({ key: s.key, label: TAB_LABEL[s.key] ?? s.title, count: s.n });
  return out;
}

/** The deal page's ?b360 switch: "1" opens the panel; any other value (or none) keeps it closed. */
export function isOpen(v: string | null | undefined): boolean {
  return v === "1" || v === "true" || v === "open";
}
