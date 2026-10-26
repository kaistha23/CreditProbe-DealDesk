/**
 * PLAN_R12 Session B: types and pure helpers for the R12 review (unit-tested in helpers.test.ts; no imports so node can run them).
 *
 * Amounts are millions in the deal currency; shares and ratios are decimals.
 */

export type Severity = "critical" | "major" | "minor" | "info";
export type PointStatus = "pass" | "attention" | "fail" | "not assessed";
export type DocStatus = "received" | "pending" | "expired" | "waived";
export type QueryStatus = "queued" | "sent" | "answered" | "closed";

export interface Lineage { relation: string; key: Record<string, unknown>; period: string | null; via?: string }
export interface Evidence { source: string; text: string; ref?: Lineage | null }
export interface Finding {
  finding_id: string; deal_id: string; point: number; point_name: string; code: string; author: string | null; severity: Severity;
  title: string; finding: string; evidence: Evidence[]; measured: unknown; threshold: unknown; policy_ref: string; crm_article: string;
  doa_level: string | null; rule_ids: string[]; line_ids: string[]; status: string; query_id?: string | null; document_items?: string[];
}
export interface Point {
  point: number; name: string; scope: string; status: PointStatus; summary: string; counts: Record<Severity, number>; finding_ids: string[];
  analysis: string[];
}
export interface AdjRow { ratio: string; reported: number | null; adjusted: number | null; change: number | null; unit: string; prior: number | null }
export interface Adjustment { item: string; field: string; amount: number; applies_to: string[]; year: number | null }
export interface DocItem {
  item_id: string; rule_id: string; name: string; group: string; for: string; for_kind: string; status: DocStatus; date: string | null;
  expires: string | null; clause: string; policy: string; mandatory: boolean; severity: Severity; note: string | null; updated_by: string | null;
  updated_at: string | null; status_source: string;
}
export interface Documents {
  deal_id: string; product: string; segment: string; items: DocItem[]; counts: Record<DocStatus, number>; missing: string[]; missing_count: number;
  completeness: number; headline: string; badge: number; rules_version: string; policy: { id: string; name: string; version: string };
}
export interface Query {
  query_id: string; deal_id: string; kind: string; ref_id: string | null; question: string; to_user: string; from_user: string;
  thread_id: string | null; status: QueryStatus; sent_at: string | null; answered_at: string | null; reply_text: string | null; reply_by: string | null;
  closed_at: string | null; closed_by: string | null; note: string | null; created_at: string; mail_href: string | null;
}
export interface Queries { deal_id: string | null; items: Query[]; counts: Record<QueryStatus, number>; open: number; headline: string }
export interface QualityPart { part: string; weight: number; share: number; points: number; basis: string }
export interface Quality { score: number; grade: string; parts: QualityPart[]; headline: string }
export interface OpinionPara { title: string; text: string; underline: string[] }
export interface Opinion { voice: string; author: string; paragraphs: OpinionPara[]; text: string; writer: string; polished: boolean; words: number }
export interface Reconciliation { bank: string; entity: string; declared: number | null; bureau: number | null; gap: number | null; gap_share: number | null; status: string; letter: boolean | null }
export interface BureauEntity { entity: string; role: string; outstanding: number | null; overdue: number | null; returned_cheques: number | null; score: number | null; court_cases: number | null; provided: boolean; classification?: string | null }
export interface Analytics {
  adjusted: { year: number | null; rows: AdjRow[]; adjustments: Adjustment[]; missing: string[]; headline: string; source: Lineage };
  receivables: { year: number | null; total: number | null; ageing: { bucket: string; amount: number; share: number | null }[]; over_365_share: number | null;
    concentration: { top1_share: number | null; top2_share: number | null; topn_share: number | null; topn_n: number | null; names: { name: string; share: number }[]; basis: string };
    retention: { receivable: number | null; overdue: number | null; by_year: { year: number; amount: number }[] };
    related_party: { amount: number | null; share_of_current_assets: number | null }; cash_cycle_days: number | null; headline: string; source: Lineage };
  auditor: { auditor: string | null; approved_panel: boolean | null; opinion: string | null; qualification_basis: string | null; qualification_amount: number | null;
    entity_scope: string | null; grade: string | null; headline: string; source: Lineage };
  bureau: { entities: BureauEntity[]; cbrbr: Record<string, unknown>[]; matrix: { banks: string[]; entities: string[]; rows: Record<string, unknown>[] };
    reconciliation: Reconciliation[]; totals: { declared: number | null; bureau: number | null; gap: number | null }; not_provided: string[]; headline: string };
  earlier: { rows: { condition_id: string; text: string; kind: string; status: string; measure: string; achieved_share: number | null; committee_ref?: string }[];
    promises?: { promise_id: string; kind: string; text: string; promised: number | null; delivered: number | null; delivered_share: number | null; status: string; window: string }[];
    headline: string; source: Lineage };
  conduct?: { turnover: number | null; revenue: number | null; turnover_to_revenue: number | null; months: number | null; headline: string };
  projections?: { historical: { year: number; revenue: number; ebitda: number | null }[]; projected: { year: number; revenue: number; ebitda: number | null }[];
    revenue_cagr_history?: number; revenue_cagr_projected?: number; headline: string };
  insider: { rows: { party: string; person: string; link: string; share: number | null; kind: string }[]; headline: string; source: Lineage };
  language: { lines_checked: number; unevidenced: { line_id: string; text: string; words: string[] }[]; one_sided: boolean; headline: string };
  versions: { versions: { version: string; file: string; at?: string }[]; queries: { open: number; answered: number; closed: number }; headline: string };
  precedent: { line?: string };
}
export interface Signoff { roles: string[]; latest: Record<string, { role: string; by: string; decision: string; note: string; at: string }>; trail: { role: string; by: string; decision: string; note: string; at: string }[] }
export interface Review2 {
  deal_id: string; version: string; view: "review" | "prepare"; currency: string; as_of: string; reviewed_at: string;
  subject: { id: string; name: string; group: string | null; sector: string; rating: string; currency: string; product: string; segment: string; amount_ccy: number };
  answer: { decision: string; tone: "negative" | "warning" | "positive"; headline: string; counts: Record<Severity, number>; approval: string; counter_proposal: string | null };
  points: Point[]; findings: Finding[]; counts: Record<Severity, number>; analytics: Analytics; documents: Documents; queries: Queries; quality: Quality;
  opinion: Opinion | null; signoff: Signoff | null; lineage: Record<string, Lineage>; seconds: number; basis: string;
}
export interface PreflightItem { finding_id: string; point: number; point_name: string; code: string; severity: Severity; title: string; finding: string; policy_ref: string; status: string; document_items?: string[] }
export interface Preflight {
  deal_id: string; ready: boolean; headline: string; blockers: PreflightItem[]; warnings: PreflightItem[]; notes: PreflightItem[]; documents: Documents;
  queries: Queries; quality: Quality; points: { point: number; name: string; status: PointStatus; counts: Record<Severity, number> }[]; basis: string;
}

export const SEVERITIES: Severity[] = ["critical", "major", "minor", "info"];
export const SEV_LABEL: Record<Severity, string> = { critical: "Critical", major: "Major", minor: "Minor", info: "Note" };
export const SEV_TONE: Record<Severity, "negative" | "warning" | "neutral" | "accent"> = { critical: "negative", major: "warning", minor: "neutral", info: "accent" };
export const POINT_TONE: Record<PointStatus, "negative" | "warning" | "positive" | "neutral"> = { fail: "negative", attention: "warning", pass: "positive", "not assessed": "neutral" };
export const POINT_LABEL: Record<PointStatus, string> = { fail: "Fail", attention: "Attention", pass: "Pass", "not assessed": "Not assessed" };
export const DOC_TONE: Record<DocStatus, "positive" | "warning" | "negative" | "neutral"> = { received: "positive", pending: "warning", expired: "negative", waived: "neutral" };
export const DOC_LABEL: Record<DocStatus, string> = { received: "Received", pending: "Pending", expired: "Expired", waived: "Waived" };
export const QUERY_LABEL: Record<QueryStatus, string> = { queued: "Queued", sent: "With RM", answered: "Answered", closed: "Closed" };
export const QUERY_TONE: Record<QueryStatus, "warning" | "accent" | "positive" | "neutral"> = { queued: "neutral", sent: "warning", answered: "accent", closed: "positive" };

const SEV_ORDER: Record<Severity, number> = { critical: 0, major: 1, minor: 2, info: 3 };

/** Findings grouped by severity, critical first; empty groups dropped. */
export function groupBySeverity(fs: Finding[]): { severity: Severity; items: Finding[] }[] {
  return SEVERITIES.map((s) => ({ severity: s, items: fs.filter((f) => f.severity === s).sort((a, b) => a.point - b.point || a.code.localeCompare(b.code)) }))
    .filter((g) => g.items.length);
}

export function sortFindings(fs: Finding[]): Finding[] {
  return [...fs].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || a.point - b.point || a.code.localeCompare(b.code));
}

/** "3 critical · 5 major · 1 minor"; "No findings". Notes (info) are not counted. */
export function severityLine(c: Partial<Record<Severity, number>>): string {
  const parts = (["critical", "major", "minor"] as Severity[]).filter((s) => (c[s] ?? 0) > 0).map((s) => `${c[s]} ${s}`);
  return parts.length ? parts.join(" · ") : "No findings";
}

/** "AED 117.7m", "−AED 10.0m", "—" for null. Input in millions. */
export function money(v: number | null | undefined, ccy: string, dp = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = `${ccy ? ccy + " " : ""}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp })}m`;
  return v < 0 ? `−${s}` : s;
}

export function pct(v: number | null | undefined, dp = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(dp)}%`;
}

export function times(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toFixed(2)}x`;
}

/** A ratio row's value in its unit ("x" for multiples, otherwise money). */
export function ratioValue(v: number | null, unit: string, ccy: string): string {
  return unit === "x" ? times(v) : money(v, ccy);
}

/** Documents grouped by their checklist group, keeping the rule order. */
export function groupDocs(items: DocItem[]): { group: string; items: DocItem[] }[] {
  const out: { group: string; items: DocItem[] }[] = [];
  for (const i of items) {
    let g = out.find((x) => x.group === i.group);
    if (!g) { g = { group: i.group, items: [] }; out.push(g); }
    g.items.push(i);
  }
  return out;
}

/** The badge on the action bar: "Documents (3)" or "Documents" when nothing is missing. */
export function docsBadge(d: Pick<Documents, "missing_count"> | null | undefined): string {
  return d && d.missing_count > 0 ? `Documents (${d.missing_count})` : "Documents";
}

/** The query a reviewer would send for a missing document. */
export function queryForDoc(i: Pick<DocItem, "name" | "for" | "status" | "clause">): string {
  return `Please provide the ${i.name.toLowerCase()} for ${i.for}${i.status === "expired" ? " (the copy on file has expired)" : ""}; required by ${i.clause}.`;
}

/** The query a reviewer would send for a finding. */
export function queryForFinding(f: Pick<Finding, "title" | "finding">): string {
  return `${f.title}: ${f.finding} Please explain and provide the supporting evidence.`;
}

/** "Al Sahel Building Materials": the open query count on a deal for the landing card. */
export function openQueries(q: Pick<Queries, "items"> | null | undefined): number {
  return q ? q.items.filter((x) => x.status === "queued" || x.status === "sent").length : 0;
}

/** Split a paragraph so the underlined key concerns can be rendered underlined. */
export function underlineParts(text: string, marks: string[]): { text: string; underline: boolean }[] {
  const ms = marks.filter((m) => m && text.includes(m));
  if (!ms.length) return [{ text, underline: false }];
  const out: { text: string; underline: boolean }[] = [];
  let rest = text;
  while (rest.length) {
    let best = -1;
    let mark = "";
    for (const m of ms) {
      const i = rest.indexOf(m);
      if (i >= 0 && (best < 0 || i < best)) { best = i; mark = m; }
    }
    if (best < 0) { out.push({ text: rest, underline: false }); break; }
    if (best > 0) out.push({ text: rest.slice(0, best), underline: false });
    out.push({ text: mark, underline: true });
    rest = rest.slice(best + mark.length);
  }
  return out;
}

/** A lineage tag in words: "dd_obligor_financials · proposal_id PRP-B-ASB · 2026-10-13". */
export function lineageText(l: Lineage | null | undefined): string {
  if (!l) return "";
  const k = Object.entries(l.key ?? {}).map(([a, b]) => `${a} ${String(b)}`).join(", ");
  return [l.relation, k, l.period].filter(Boolean).join(" · ") + (l.via === "r11-evidence" ? " (from the bank's review evidence until the relation is populated)" : "");
}
