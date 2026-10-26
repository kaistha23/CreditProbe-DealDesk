/**
 * R16 i: the customer file types and pure helpers (no imports, so node --test runs them).
 */

export type CheckStatus = "received" | "missing" | "expired" | "not_applicable";
export interface IntakeDoc {
  doc_id: string; file_name: string; file_kind: string; read_method: string; ocr_engine: string; pages: number; title?: string;
  doc_type: string; doc_label: string; confidence: number; why?: string[]; subject: string; status: string; status_reason: string;
  valid_until: string; error?: string | null; fields_n: number; customer_name?: string | null; cr_number?: string | null;
}
export interface CheckLine {
  req_group: string; doc_type: string; requirement: string; subject: string; status: CheckStatus; doc_ids: string; reason: string;
  valid_until: string; rule_ref: string;
}
export interface ReconTest {
  test: string; topic: string; title: string; status: "agrees" | "differs" | "flag" | "info"; severity: number;
  a: number | null; b: number | null; c: number | null; gap_pct: number | null; unit_note: string; sentence: string;
  evidence: { doc_id?: string; file?: string; field?: string; relation?: string }[];
}
export interface BankPull {
  existing: boolean; how: string; proposal_id?: string; cif?: string; name?: string; since?: string; rating?: string; rm?: string;
  group_id?: string; group_name?: string; sources: string[];
  accounts?: Record<string, unknown>[];
  conduct?: { month: string; credit_turnover_mn: number; debit_turnover_mn: number; avg_balance_mn: number; utilisation_pct: number;
              past_due_days_max: number; returned_cheques_n: number }[];
  last12?: { credits_mn: number; debits_mn: number; avg_balance_mn: number; utilisation_avg_pct: number; utilisation_peak_pct: number;
             past_due_months: number; past_due_days_max: number; returned_cheques_n: number; returned_cheques_mn: number; from: string; to: string };
  credits_by_year?: Record<string, number>;
  facilities?: { limit_id: string; parent_limit_id?: string; level: number; limit_name: string; existing_mn: number; outstanding_mn: number;
                 cash_margin_pct?: number; tenor_text?: string }[];
  facilities_total?: { existing_mn: number; outstanding_mn: number; utilisation_pct: number | null };
  security?: { kind: string; provider: string; amount_mn: number; value_mn: number; perfection_status: string }[];
  limit_history?: { kind: string; ref_no: string; ref_date: string; authority: string; amount_mn: number; text: string }[];
  group_exposure?: { entity_name: string; funded_existing_mn: number; total_existing_mn: number; total_proposed_mn: number; outstanding_mn: number }[];
  group?: { entities: { entity_id: string; entity_name: string; role: string; parent_entity_id: string; activity: string; borrower_id: string;
                        credit_status: string; credit_status_note: string }[];
            edges: { rel_type: string; source_id: string; target_id: string; ownership_pct: number; detail: string }[];
            shareholders: { entity_id: string; holder_name: string; holder_kind: string; share_pct: number }[] };
  connected_weak?: { id: string; name: string; relation: string; status: string }[];
  bureau?: { entity_name: string; bureau: string; report_date: string; outstanding_mn: number; overdue_mn: number; worst_status: string; score: number }[];
  other_banks?: { bank_name: string; declared_limit_mn: number; bureau_limit_mn: number; bureau_outstanding_mn: number }[];
  returned_cheques?: { return_date: string; amount_mn: number; reason: string; regularised_flag: number }[];
  b360?: { profile?: Record<string, unknown>; rating_history?: Record<string, unknown>[]; ews?: Record<string, unknown> };
}
export interface Profile { customer_name: string; cr_number: string; city: string; activity: string; legal_form: string; sector: string; contractor: boolean }
export interface CustomerFile {
  intake_id: string; proposal_id: string; as_of: string; created_at: string; profile: Profile; bank: BankPull; documents_n: number;
  by_method: Record<string, number>; by_method_text: string; documents: IntakeDoc[]; checklist: CheckLine[];
  counts: { received: number; missing: number; expired: number; not_applicable: number; required: number };
  groups: { key: string; label: string }[]; reconciliation: ReconTest[]; plain_words: string[]; skipped?: string[];
}
export interface IntakeOverview {
  ocr: { available: boolean; engine: string; install: string }; accepted: string[]; max_mb: number;
  doc_types: { code: string; label: string; group: string }[]; recent: { intake_id: string; proposal_id: string; customer_name: string; documents_n: number; created_at: string }[];
  plain_words: string[];
}
export interface Facts {
  intake_id: string; proposal_id: string; profile: Profile; bank: BankPull;
  financials: Record<string, Record<string, unknown>>; latest: Record<string, Record<string, unknown>>;
}

// ------------------------------------------------------------------------------------------------ pure helpers
export const STATUS_LABEL: Record<string, string> = {
  received: "Received", missing: "Missing", expired: "Expired", not_applicable: "Not needed", stale: "Expired", unreadable: "Not read",
};
export function statusTone(s: string): "positive" | "negative" | "warning" | "neutral" {
  return s === "received" ? "positive" : s === "missing" ? "negative" : s === "expired" || s === "stale" ? "warning" : "neutral";
}
export function reconTone(t: Pick<ReconTest, "status" | "severity">): "positive" | "negative" | "warning" | "neutral" {
  if (t.status === "agrees") return "positive";
  if (t.severity >= 3) return "negative";
  if (t.severity >= 2) return "warning";
  return "neutral";
}
export const RECON_LABEL: Record<string, string> = { agrees: "Agrees", differs: "Differs", flag: "Ask", info: "Note" };

export function groupChecklist(lines: CheckLine[], groups: { key: string; label: string }[]) {
  return groups.map((g) => {
    const ls = lines.filter((l) => l.req_group === g.key);
    const need = ls.filter((l) => l.status !== "not_applicable");
    return { ...g, lines: ls, received: need.filter((l) => l.status === "received").length, required: need.length };
  }).filter((g) => g.lines.length);
}

const words = (s: string) => s.split(/\s+/).filter(Boolean).length;

/** The plain-words block (≤ 4 lines, ≤ 60 words) from the file view. */
export function plainWords(v: CustomerFile): string[] {
  const c = v.counts;
  const flags = v.reconciliation.filter((t) => t.severity >= 2);
  const out = [
    `${v.documents_n} files read for ${v.profile.customer_name || "the customer"}${v.by_method["photo (OCR)"] ? `, ${v.by_method["photo (OCR)"]} of them photos` : ""}.`,
    `${c.received} of ${c.required} required documents received; ${c.missing} missing, ${c.expired} expired.`,
    v.bank.existing ? "Already banks with us: accounts, facilities, conduct and group pulled in." : "New to the Bank.",
    flags.length ? `${flags.length} points to ask about, first: ${flags[0].title.replace(/\.+$/, "")}.` : "Key figures agree across documents.",
  ];
  while (out.length > 1 && out.reduce((n, l) => n + words(l), 0) > 60) out.pop();
  return out;
}

/** Short-form values for a new proposal, from the customer file's facts (amounts in SAR million). */
export function prefillFromFacts(f: Facts, sectors: string[]): Record<string, string> {
  const mn = (x: unknown) => (typeof x === "number" && Number.isFinite(x) ? (x / 1e6).toFixed(1) : "");
  const years = Object.keys(f.financials).filter((k) => k.startsWith("FY")).sort();
  const fy = years.length ? f.financials[years[years.length - 1]] : {};
  const n = (k: string) => (typeof fy[k] === "number" ? (fy[k] as number) : 0);
  const out: Record<string, string> = {};
  if (f.profile.customer_name) out.name = f.profile.customer_name;
  if (f.profile.cr_number) out.cr_number = f.profile.cr_number;
  if (f.profile.sector && sectors.includes(f.profile.sector)) out.sector = f.profile.sector;
  if (fy.revenue !== undefined) out.revenue = mn(fy.revenue);
  if (fy.operating_profit !== undefined) out.ebitda = mn(n("operating_profit") + n("depreciation"));
  const debt = n("short_term_borrowings") + n("long_term_borrowings") + n("current_portion_ltd");
  if (debt) out.total_debt = mn(debt);
  const ask = (f.latest.business_request?.total_proposed ?? f.latest.facility_request_letter?.requested_total) as unknown;
  if (typeof ask === "number" && ask > 0) out.amount = mn(ask);
  if (f.bank.existing && f.bank.group_name) out.group_name = f.bank.group_name;
  return out;
}

export function fmtMn(x: number | null | undefined, d = 1): string {
  return x === null || x === undefined || !Number.isFinite(x) ? "–" : `${x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

export const ACCEPT = ".docx,.pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,.txt";

/** Batches of at most `size` files, the photographed pages of one document ("…_p1.jpg", "…_p2.jpg") always together. */
export function batchFiles<T extends { name: string }>(files: T[], size = 6): T[][] {
  const stem = (n: string) => n.replace(/[_\- ]p(?:age)?[_\- ]?\d{1,2}(\.[a-z]+)$/i, "$1");
  const groups: T[][] = [];
  const at = new Map<string, number>();
  for (const f of files) {
    const k = stem(f.name);
    const i = at.get(k);
    if (i !== undefined) groups[i].push(f); else { at.set(k, groups.length); groups.push([f]); }
  }
  const batches: T[][] = [];
  for (const g of groups) {
    const last = batches[batches.length - 1];
    if (last && last.length + g.length <= size) last.push(...g); else batches.push([...g]);
  }
  return batches;
}

