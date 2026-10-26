/**
 * PLAN_R12 Session P: types for the product analytics (GET /api/v1/dealdesk/products/...) and the pure read
 * functions the four product sections and their tests share (no fetch, no React). Every figure comes from the
 * server, which reads it from a Data Domains relation; `srcLine` turns its lineage into the (i) text.
 */

export interface Src {
  domain?: string; relation?: string | string[]; key?: Record<string, unknown>; period?: string | null; column?: string;
  derived?: string; note?: string; inputs?: Src[];
}

// ------------------------------------------------------------------ project / contracting

export interface ProjectRow {
  project_id: string; project_name: string; employer: string | null; consultant: string | null; currency: string;
  contract_value_original: number; contract_value_revised: number; variation_pct: number | null;
  start_date: string | null; completion_date_original: string | null; completion_date_revised: string | null;
  wd_pct: number; time_elapsed_pct: number | null; slip_pts: number | null; eot_days: number; eot_formalised: boolean | null;
  eot_label: string; amount_received: number; amount_due: number; days_due: number;
  last_certificate: { no: string | number | null; date: string | null; last_payment?: string | null };
  remaining_proceeds: number; backlog: number; financed: boolean; funded_outstanding: number; flags: string[]; src: Record<string, Src>;
  status?: string | null; planned_pct?: number | null; billed?: number; retention?: number; narrative?: string | null;
}
export interface DelayRow {
  delay_days: number; label: string; peak_deficit: number; peak_month: string | null; extra_funding: number; deficit: number[];
  funded_outstanding: number; cover_ratio: number | null; cover_ok: boolean; within_limit: boolean | null; headroom: number | null;
}
export interface LgRow {
  limit_id: string; type: string; label: string; project_id?: string | null; existing: number; outstanding: number; proposed: number;
  cash_margin_pct: number; ccf_regulatory: number; ccf_economic: number; ead_regulatory: number; ead_economic: number;
}
export interface EmployerRow {
  employer: string; projects: number; backlog: number; backlog_share: number | null; amount_due: number; max_days_due: number;
  contract_value: number; rating: string | null; bureau: { overdue: number; returned_cheques: number; score: unknown; court_cases: number } | null;
}
export interface CoverRatio { remaining_proceeds: number; funded_outstanding: number; ratio: number | null; min: number; ok: boolean; text: string; src?: Src; min_src?: Src }
export interface ProjectResult {
  trace_id?: string | null; proposal_id: string; has_data: boolean; answer: string;
  status?: { as_of: string; rows: ProjectRow[]; totals: Record<string, number> };
  cover_ratio?: CoverRatio;
  cash_flow?: { months: string[]; costs: number[]; receipts: number[]; advance: number[]; retention: number[]; cumulative: number[];
                deficit: number[]; peak_deficit: number; peak_month: string | null; retention_held: number } | null;
  delay_stress?: { months: string[]; rows: DelayRow[]; cover_ratio_min: number; funded_limit: number | null;
                   first_break: { delay_days: number; what: string } | null } | null;
  employer_credit?: { rows: EmployerRow[]; total_backlog: number; top2_share: number; concentration_max: number; concentrated: boolean; text: string };
  lgs?: { rows: LgRow[]; by_type: { type: string; label: string; proposed: number; outstanding: number; ead_regulatory: number; ead_economic: number }[];
          total_proposed: number; total_ead_regulatory: number };
  funded_limit?: number | null;
}

// ------------------------------------------------------------------ escrow

export interface EscrowResult {
  trace_id?: string | null; proposal_id: string; has_data: boolean; answer: string;
  account?: { project_name: string | null; developer: string | null; escrow_agent: string | null; construction_progress_pct: number | null;
              construction_cost: number; currency: string };
  collections?: { units_total: number; units_sold: number; sold_pct: number | null; sales_value_contracted: number; collected_to_date: number;
                  collected_pct: number | null; to_collect: number; unsold_inventory_value: number | null;
                  series: { month: string; collected: number; units_sold_cum?: number | null }[] };
  cover?: { escrow_balance: number; receivable: number; loan_outstanding: number; cost_to_complete: number; ratio: number | null; min: number; ok: boolean; text: string };
  waterfall?: { collections: number; tiers: { priority: number; bucket: string; rule: string; allocated: number | null; share: number | null }[]; unallocated: number };
  releases?: { rows: { release_id: string; date: string; amount: number; construction: number; debt_service: number; developer: number;
                       collections: number; retention: number; progress_pct: number | null; compliant: boolean; breaches: string[] }[];
               released: number; breaches: number; rules: string[] };
}

// ------------------------------------------------------------------ syndication

export interface ShareAnalytics {
  hold_pct_of_commitment: number; held_sar_mn: number; raroc: number; hurdle: number; sva: number; clears_hurdle: boolean;
  ead_y1: number; rwa_y1: number; capital_y1: number; el_y1: number; arranger_skim_sar_mn: number;
}
export interface SyndicationResult {
  trace_id?: string | null; proposal_id: string; has_data: boolean; answer: string;
  facility?: { name: string | null; borrower: string | null; currency: string; facility_total: number; our_commitment: number; final_hold: number;
               our_share: number | null; final_share: number; lenders: number | null; agent: string | null; mla_banks?: string | null; pari_passu: boolean | null;
               margin_bps?: number | null; participation_fee_bps?: number | null; tenor_years?: number | null; sell_down_by?: string | null; security?: string | null };
  role?: { key: "agent" | "lead" | "participant"; label: string; documents: string; fees: string; information: string };
  sell_down?: { step: number; date: string | null; hold: number; buyer_type: string | null; share_of_facility: number | null; analytics: ShareAnalytics | null }[];
  analytics?: ShareAnalytics | null;
  lenders?: { majority_pct: number; our_vote: number; blocking_minority: boolean; info_from_agent?: string | null };
  covenants_text?: string | null;
  covenants?: { covenant: string; threshold: number; actual: number; direction: "max" | "min"; headroom: number | null; ok: boolean }[];
  flags?: string[];
}

// ------------------------------------------------------------------ SME

export type SmeDecisionLabel = "Approve" | "Approve with conditions" | "Refer to full flow" | "Decline";
export interface SmeRule { id: string; rule: string; value: unknown; value_text?: string; threshold: string; pass: boolean; on_fail: "hard" | "exception" }
export interface SmeDecision {
  trace_id?: string | null; application_id: string; programme?: string | null; years_in_business?: number | null; annual_sales_mn?: number | null; applicant: string; sector: string; region: string; amount_sar_mn: number; tenor_years: number;
  product: string | null; existing_exposure_sar_mn: number; received_date: string | null; rm: string | null;
  scorecard: { scorecard: { id: string; name: string; version: string }; score: number; grade: string; pd: number | null; recorded?: boolean;
               lines: { variable: string; label: string; value: unknown; bin: string; points: number }[] };
  rules: SmeRule[]; doa: { level: string; in_lane: boolean; exposure_sar_mn: number; reason: string };
  decision: SmeDecisionLabel; lane: "fast_track" | "full"; conditions: string[]; exceptions: string[];
  route: { to: string; reasons: string[]; proposal_id: string | null } | null;
  paper: { headline: string; lines: string[] }; answer: string;
}
export interface SmeLaneRow {
  application_id: string; applicant: string; sector: string; amount_sar_mn: number; decision: SmeDecisionLabel; lane: string;
  answer: string; grade: string; score: number; doa_level: string; exceptions: number;
}
export interface SmeCounts { total: number; by_decision: Record<SmeDecisionLabel, number>; in_lane: number; to_full_flow: number; ready_to_approve: number }
export interface SmeLane { trace_id?: string | null; applications: SmeLaneRow[]; counts: SmeCounts }
export interface SmeCount extends SmeCounts { card: string; count: number; sub: string }

// ------------------------------------------------------------------ formatting

const DASH = "–";
const ok = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** An amount in millions of the deal currency: "SAR 12.3m", "USD 1.20bn". */
export function amt(v: number | null | undefined, ccy = "SAR"): string {
  if (!ok(v)) return DASH;
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1000) return `${sign}${ccy} ${(a / 1000).toFixed(2)}bn`;
  return `${sign}${ccy} ${a.toLocaleString("en-US", { minimumFractionDigits: a < 10 ? 2 : 1, maximumFractionDigits: a < 10 ? 2 : 1 })}m`;
}
export const pct = (v: number | null | undefined, dp = 0): string => (ok(v) ? `${(v * 100).toFixed(dp)}%` : DASH);
export const times = (v: number | null | undefined): string => (ok(v) ? `${v.toFixed(2)}x` : DASH);
export const days = (v: number | null | undefined): string => (ok(v) ? `${Math.round(v)} ${Math.round(v) === 1 ? "day" : "days"}` : DASH);
export function month(m: string | null | undefined): string {
  if (!m) return DASH;
  const [y, mm] = m.split("-").map(Number);
  if (!y || !mm) return m;
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][mm - 1]} ${y}`;
}

/** The (i) line for a figure: where it comes from in Data Domains. */
export function srcLine(s: Src | null | undefined): string {
  if (!s) return "";
  const rel = Array.isArray(s.relation) ? s.relation.join(", ") : s.relation ?? "";
  const key = s.key && Object.keys(s.key).length ? ` · ${Object.values(s.key).filter((x) => x !== null && x !== undefined).join(" / ")}` : "";
  const col = s.column ? ` · ${s.column}` : "";
  const per = s.period ? ` · ${s.period}` : "";
  const how = s.derived ? ` — ${s.derived}` : "";
  return `${s.domain ?? "Data Domains"} · ${rel}${key}${col}${per}${how}`.trim();
}

export type Tone = "neutral" | "positive" | "negative" | "warning";

export function coverTone(ratio: number | null | undefined, min: number): Tone {
  if (!ok(ratio)) return "neutral";
  if (ratio < min) return "negative";
  return ratio < min * 1.1 ? "warning" : "positive";
}

export function decisionTone(d: SmeDecisionLabel): "positive" | "warning" | "negative" | "accent" {
  return d === "Approve" ? "positive" : d === "Approve with conditions" ? "accent" : d === "Refer to full flow" ? "warning" : "negative";
}

// ------------------------------------------------------------------ project reads

export interface Tile { label: string; value: string; sub?: string; tone?: Tone; info?: string }

export function projectTiles(r: ProjectResult): Tile[] {
  const t: Tile[] = [];
  const st = r.status;
  if (st) {
    const n = st.totals.projects ?? 0;
    t.push({ label: "Financed projects", value: String(n), sub: `${st.totals.with_flags ?? 0} flagged · ${st.totals.eot_not_formalised ?? 0} EOT not formalised`,
             tone: (st.totals.with_flags ?? 0) > 0 ? "warning" : "neutral", info: "Projects in dd_project for this deal; a flag is a slip, an unformalised extension of time, a passed completion date or a certificate unpaid over 90 days." });
  }
  if (r.cover_ratio) {
    const c = r.cover_ratio;
    t.push({ label: "Cover ratio", value: times(c.ratio), sub: `minimum ${times(c.min)}`, tone: coverTone(c.ratio, c.min), info: `${c.text}. ${srcLine(c.src)}` });
  }
  if (r.cash_flow) {
    t.push({ label: "Peak project deficit", value: amt(r.cash_flow.peak_deficit), sub: r.cash_flow.peak_month ? `in ${month(r.cash_flow.peak_month)}` : "no deficit",
             info: "Largest cumulative shortfall of receipts and advance against costs (dd_project_cashflow)." });
  }
  const ds = r.delay_stress;
  if (ds && ds.rows.length > 1) {
    const w = ds.rows[ds.rows.length - 1];
    t.push({ label: `Deficit at ${w.delay_days} days' delay`, value: amt(w.peak_deficit),
             sub: ds.first_break ? `breaks at ${ds.first_break.delay_days} days` : "no break", tone: ds.first_break ? "negative" : "positive",
             info: "Receipts delayed by the days shown; extra funding raises funded outstanding and lowers the cover ratio." });
  }
  return t.slice(0, 4);
}

/** Plotly series for the deficit chart: base and each delay. */
export function deficitSeries(r: ProjectResult): { name: string; x: string[]; y: number[] }[] {
  const ds = r.delay_stress;
  if (!ds) return r.cash_flow ? [{ name: "Base", x: r.cash_flow.months.map(month), y: r.cash_flow.deficit }] : [];
  return ds.rows.map((row) => ({ name: row.delay_days ? `${row.delay_days} days late` : "Base", x: ds.months.map(month), y: row.deficit }));
}

export function slipTone(p: ProjectRow): Tone {
  if (p.flags.length === 0) return "positive";
  return p.flags.some((f) => /not formalised|Past the completion|unpaid/.test(f)) ? "negative" : "warning";
}

// ------------------------------------------------------------------ escrow and syndication reads

export function escrowTiles(r: EscrowResult): Tile[] {
  const t: Tile[] = [];
  const c = r.collections;
  if (c) {
    t.push({ label: "Units sold", value: pct(c.sold_pct), sub: `${c.units_sold} of ${c.units_total}` });
    t.push({ label: "Collected", value: pct(c.collected_pct), sub: `${amt(c.collected_to_date)} of ${amt(c.sales_value_contracted)} sold` });
  }
  if (r.cover) t.push({ label: "Cover ratio", value: times(r.cover.ratio), sub: `minimum ${times(r.cover.min)}`, tone: coverTone(r.cover.ratio, r.cover.min), info: r.cover.text });
  if (r.releases) t.push({ label: "Months outside the rules", value: String(r.releases.breaches), sub: `${amt(r.releases.released)} released`,
                          tone: r.releases.breaches ? "negative" : "positive" });
  return t.slice(0, 4);
}

export function syndicationTiles(r: SyndicationResult): Tile[] {
  const f = r.facility;
  if (!f) return [];
  const t: Tile[] = [
    { label: "Our commitment", value: amt(f.our_commitment, f.currency), sub: `${pct(f.our_share)} of ${amt(f.facility_total, f.currency)}` },
    { label: "Final hold", value: amt(f.final_hold, f.currency), sub: `${pct(f.final_share, 1)} of the facility` },
  ];
  const a = r.analytics;
  if (a) {
    t.push({ label: "RAROC on our hold", value: pct(a.raroc, 1), sub: `hurdle ${pct(a.hurdle, 1)}`, tone: a.clears_hurdle ? "positive" : "negative" });
    t.push({ label: "SVA on our hold", value: amt(a.sva), sub: `RWA ${amt(a.rwa_y1)}`, tone: a.sva >= 0 ? "positive" : "negative" });
  } else if (r.role) {
    t.push({ label: "Role", value: r.role.label, sub: r.role.fees });
  }
  return t.slice(0, 4);
}

// ------------------------------------------------------------------ SME reads

export function smeTiles(c: SmeCounts): Tile[] {
  return [
    { label: "Applications", value: String(c.total), sub: `${c.in_lane} in the fast track` },
    { label: "Ready to approve", value: String(c.ready_to_approve), sub: `${c.by_decision["Approve with conditions"] ?? 0} with conditions`, tone: "positive" },
    { label: "To the full flow", value: String(c.to_full_flow), sub: "exceptions", tone: c.to_full_flow ? "warning" : "neutral" },
    { label: "Declined", value: String(c.by_decision.Decline ?? 0), sub: "hard rule failed", tone: c.by_decision.Decline ? "negative" : "neutral" },
  ];
}

export function ruleValue(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (v === null || v === undefined || v === "") return DASH;
  return String(v);
}

/** The landing card line U shows under the count. */
export function smeCardLine(c: SmeCount): string {
  return c.total === 0 ? "No SME applications in the lane" : c.sub;
}
