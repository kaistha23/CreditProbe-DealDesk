/**
 * R16 d: customer packs on the Deal Desk service (/api/v1/dealdesk/customer-packs): the four customers' document packs
 * (Word, PDF, photos), the ask and RM notes to type, the document checklist, and the Bank's file on existing customers.
 * The helpers below are pure and tested (dealdesk-packs.test.ts).
 */
import { friendlyError } from "./errors.ts";

const BASE = "/api/v1/dealdesk/customer-packs";

export function packsOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export interface PackCounts { documents: number; images: number; expired: number; missing: number }
export interface PackSummary {
  key: string; customer_name: string; cr_number: string; proposal_id: string; cif: string | null; existing: boolean; case: string;
  sector: string; city: string; part: string; ask: string; rm_notes: string; business_request: boolean; counts: PackCounts;
}
export interface PackFiles { docx: string; pdf: string; images: string[] }
export interface PackDocument {
  doc_id: string | null; doc_type: string; label: string; subject: string | null; title: string; issuer: string | null;
  issue_date: string | null; expiry_date: string | null; status: "received" | "expired" | "missing"; status_label: string; why?: string;
  files: PackFiles | null;
}
export interface PackDetail {
  key: string; customer_name: string; cr_number: string; proposal_id: string; cif: string | null; existing: boolean; case: string;
  ask: string; rm_notes: string; documents: PackDocument[]; plain_words: string[];
  business_request?: { docx: string; pdf: string; images: string[] }; reference?: { docx: string; pdf: string };
}
export interface Trace { domain: string; relation: string; key: Record<string, unknown>; period: string | null; version: number | null }
export interface BankFile {
  key: string; customer_name: string; existing: boolean; cif?: string; proposal_id?: string; plain_words: string[];
  summary?: { accounts_n: number; balances_mn: number; deposits_mn: number; credit_turnover_12m_mn: number; avg_utilisation_12m_pct: number;
              limits_mn: number | null; outstanding_mn: number | null; returned_cheques_12m: number; past_due_days_max_12m: number };
  accounts?: Array<{ account_no: string; label: string; account_type: string; obligor_id: string; balance_mn: number; avg_balance_12m_mn: number;
                     credits_12m_mn: number; opened: string; trace: Trace }>;
  limits?: Array<{ limit_id: string; limit_name: string; level: number; existing_mn: number; outstanding_mn: number; trace: Trace }>;
  group?: Array<{ entity_id: string; entity_name: string; role: string; credit_status: string; credit_status_note: string; borrower_id: string; trace: Trace }>;
  borrower_360?: { customer_id: string; domain: string };
}

async function call<T>(path: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${packsOrigin()}${BASE}${path}`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export const packsApi = {
  list: () => call<{ packs: PackSummary[]; plain_words: string[]; as_of: string | null }>(""),
  get: (key: string) => call<PackDetail>(`/${encodeURIComponent(key)}`),
  bank: (key: string) => call<BankFile>(`/${encodeURIComponent(key)}/bank`),
};

/** The download link of one file of a pack (served by the Deal Desk service). */
export function fileHref(key: string, path: string): string {
  return `${packsOrigin()}${BASE}/${encodeURIComponent(key)}/file?path=${encodeURIComponent(path)}`;
}

/** "SAR 12.4m" for a SAR-million figure. */
export function mn(v: number | null | undefined, digits = 1): string {
  return v == null || Number.isNaN(v) ? "–" : `SAR ${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}m`;
}

/** Checklist order: missing first, then expired, then received; within a status, the pack's own order. */
export function checklist(docs: PackDocument[]): PackDocument[] {
  const rank = { missing: 0, expired: 1, received: 2 } as const;
  return docs.map((d, i) => ({ d, i })).sort((a, b) => rank[a.d.status] - rank[b.d.status] || a.i - b.i).map((x) => x.d);
}

/** One line under a customer's name: case, documents, gaps. */
export function packLine(p: PackSummary): string {
  const gaps = [p.counts.expired ? `${p.counts.expired} expired` : "", p.counts.missing ? `${p.counts.missing} missing` : ""].filter(Boolean).join(", ");
  return `${p.case} · ${p.counts.documents} documents, ${p.counts.images} photos${gaps ? ` · ${gaps}` : ""}`;
}

/** "DD/MM/YYYY" from an ISO date (null-safe). */
export function dmy(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}
