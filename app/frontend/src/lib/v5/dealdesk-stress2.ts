/**
 * PLAN_R12 Session D: the Stress Lab ladder client and the pure functions its screens read (no React).
 *
 *   stress2Api       POST /proposals/{id}/stress2, chain, ask, catalogue, editor, sets, sensitivities,
 *                    monitoring plan and the EWS panel (engine service, /api/v1/dealdesk)
 *   ladderGroups     rows by family (mild -> moderate -> severe), not-applicable rows kept with their reason
 *   visibleCols      the tests shown for this deal (LTV only where collateral is pledged)
 *   verdictTone      the verdict and tier colours; reverseLines the reverse-stress sentences
 *
 * Every number is the engine's (backend/dealdesk/stress2); this file only selects and words it.
 */
import { friendlyError } from "./errors.ts";
import { pct, ratio, sar } from "./format.ts";
import type { Terms } from "./dealdesk.ts";

export type Severity = "mild" | "moderate" | "severe" | "none" | "custom";
export type Tone = "pass" | "amber" | "breach" | "na";
export type Col = "dscr" | "debt_ebitda" | "ltv" | "covenants" | "rating" | "stage" | "raroc" | "limits" | "ltv_cover";
export type Tier = "High" | "Medium" | "Standard";
export type Verdict = "Restructure" | "Approve with enhanced monitoring" | "Approve, standard monitoring" | "Approve";

export interface Step { step: string; value: unknown; display: string; source: string; relation: string; row: string; deal_fact: boolean; band: [number | null, number | null] | null; part?: string }
export interface ChainStep { stage: string; label: string; before: unknown; after: unknown; display: string; source: string; relation: string; row: string; domain?: string | null; period?: string | null; deal_fact?: boolean; band?: unknown }

/** "Open in Data Domains" for a chain step: the Data Builder on its domain, relation and period. */
export function dataDomainsHref(c: Pick<ChainStep, "domain" | "relation" | "period">): string | null {
  if (!c.domain || !c.relation) return null;
  const p = new URLSearchParams({ domain: c.domain, relation: c.relation });
  if (c.period) p.set("period", c.period);
  return `/data-builder?${p.toString()}`;
}
export interface RarocCheck {
  r11_raroc: number | null; raroc: number | null; sva: number; hurdle: number; clears_hurdle: boolean; rating: string; external_rating: string | null;
  capital_y1: number; margin_bps: number; provision_build_y1: number; market_margin_bps: number[] | null; attribution_ok: boolean;
  steps: { step: string; raroc: number | null; delta: number | null; basis: string }[];
}
export interface Metrics {
  dscr: number | null; debt_ebitda: number | null; ltv: number | null; ltv_cover: number | null; interest_cover: number | null;
  pd_12m: number; rating: string; notches: { scenario: number; implied: number; total: number }; stage: 1 | 2 | 3; stage_reason: string;
  ecl: number; ecl_basis: string; lifetime_raroc: number | null; lifetime_raroc_r11?: number | null; hurdle: number; sva: number; clears_hurdle: boolean;
}
export interface LadderRow {
  id: string; family: string; label: string; severity: Severity; basis: string; scope?: string; version?: number; applicable: boolean;
  na_reason: string | null; steps: Step[]; shocks: string[]; cells: Partial<Record<Col, Tone>>; fails_on: string[]; breaks: string[];
  survives: boolean; metrics?: Metrics; raroc_check?: RarocCheck; chain?: ChainStep[]; source?: string;
  covenants?: { type: string; threshold: number; value: number | null; status: string; basis: string }[];
}
export interface Criterion { criterion: "dscr" | "covenant" | "stage2" | "raroc" | "ltv"; label: string; status: "found" | "already" | "beyond" | "na"; value: number | null; passes_at?: number }
export interface Reverse {
  drivers: { driver: "revenue_pct" | "ebitda_margin_bps" | "rate_bps" | "collateral_pct"; label: string; criteria: Criterion[]; range: [number, number] }[];
  notches: { breaks_at: Record<"raroc" | "stage2" | "dscr" | "covenant", number | null>; survives_up_to: number; searched_to: number };
  headline: string;
}
export interface Trigger { trigger_id: string; driver: string; label: string; metric: string; source: string; op: string; threshold: number; unit: string; action: "alert" | "watch"; basis: string; observed?: number | null; fired?: boolean | null }
export interface TierInfo {
  tier: Tier; review_frequency_months: number; provisional: boolean; drivers: string[]; driver_labels: string[]; triggers: Trigger[];
  ews_thresholds: { override: boolean; band_floors: Record<string, number>; book_floors: Record<string, number>; basis?: string }; reason: string; note: string;
}
export interface VerdictInfo { verdict: Verdict; action: string; worst_breaking_severity: Severity; first_break: { id: string; label: string; tests: string[]; severity: string } | null; why: string; drivers: string[]; driver_labels: string[]; restructure: boolean }
export interface Stress2Result {
  trace_id: string; proposal_id: string; obligor: string; obligor_id: string | null; sector: string; run_id: string;
  structure: { label: string; terms: Terms };
  base: LadderRow; families: { id: string; label: string; row_ids: string[] }[]; rows: LadderRow[];
  columns: { key: Col; label: string }[]; show_ltv: boolean; reverse: Reverse | null; verdict: VerdictInfo; tier: TierInfo;
  commentary: { text: string; words: number; verdict: string; tier: string; writer: string; polished: boolean };
  deal_facts: Record<string, { value: number; source: string } | null>; sensitivity_version: string;
  /** The scenario sets in force (R12-L1 hand-set, R13-S1 calibrated on history, deal scope). */
  scenario_set?: string[];
  counts: { applicable: number; not_applicable: number; breaking: number }; backend: string;
  /** R14 m (K12): the current macro regime, read first (backend/scenarios/regime.py). */
  regime?: import("./regime").RegimeBlock | null;
}
export interface ScenarioDef { scenario_id: string; version: number; scope: "bank" | "deal"; proposal_id: string | null; family: string; severity: Severity; label: string; shocks: Record<string, unknown>; basis: string; status: string; maker: string; made_at: string; checker: string | null; checked_at: string | null; reason: string; set_id: string; source: string }
export interface Catalogue { trace_id: string; families: { id: string; label: string }[]; severities: string[]; scenarios: ScenarioDef[]; sensitivity_version: string; shock_keys: Record<string, string>; backend: string }
export interface Plan {
  plan_id: string; proposal_id: string; facility_id: string; obligor_id: string | null; obligor_name: string; tier: Tier; verdict: string;
  drivers: string[]; driver_labels: string[]; triggers: Trigger[]; ews_thresholds: TierInfo["ews_thresholds"]; review_frequency_months: number;
  next_review_date: string; set_by: string; set_on: string; reason: string; source: string; version: number; previous_tier: Tier | null; condition: string;
}
export interface EwsPanel {
  trace_id: string; customer_id: string; has_plan: boolean; sentence: string; tier?: Tier; set_by?: string; set_on?: string; reason?: string;
  verdict?: string; review_frequency_months?: number; next_review_date?: string; proposal_id?: string; drivers?: string[];
  thresholds?: TierInfo["ews_thresholds"]; book_band?: string | null; band_with_override?: string | null; override_raises_band?: boolean;
  score?: number | null; period?: string | null; in_ews_book?: boolean; triggers?: Trigger[]; alerts?: { alert_id: string; trigger: string; observed: number | null; period: string }[];
}
export interface StressBody2 {
  terms?: Partial<Terms> | null; scenarios?: string[]; structure_label?: string; reverse?: boolean; publish?: boolean; sensitivity_version?: string;
  /** Client only: bump to run again (not sent). */
  refresh?: number;
}

// ---------------------------------------------------------------- client

const ENGINE = "/api/v1/dealdesk";
function origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class Stress2Error extends Error {
  status: number;
  errors: { field: string; message: string }[];
  constructor(status: number, message: string, errors: { field: string; message: string }[] = []) { super(message); this.status = status; this.errors = errors; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${origin()}${ENGINE}${path}`, { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" } });
  } catch {
    throw new Stress2Error(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const det = (body as { detail?: { errors?: { field: string; message: string }[]; message?: string } } | null)?.detail;
    if (det && typeof det === "object" && det.errors) throw new Stress2Error(r.status, det.message ?? "Please check the fields.", det.errors);
    throw new Stress2Error(r.status, friendlyError("Deal Desk", r.status, body));
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const enc = encodeURIComponent;

export const stress2Api = {
  run: (pid: string, body: StressBody2) => call<Stress2Result>(`/proposals/${enc(pid)}/stress2`, post(body)),
  chain: (pid: string, sid: string, terms?: Partial<Terms> | null) => call<{ answer: string; chain: ChainStep[]; row: Partial<LadderRow> | null }>(`/proposals/${enc(pid)}/stress2/chain/${enc(sid)}`, post({ terms: terms ?? null })),
  ask: (pid: string, question: string, terms?: Partial<Terms> | null) => call<{ answer: string; scenario_id: string | null; chain: ChainStep[] }>(`/stress2/ask`, post({ proposal_id: pid, question, terms: terms ?? null })),
  catalogue: (pid?: string) => call<Catalogue>(`/stress2/catalogue${pid ? `?proposal_id=${enc(pid)}` : ""}`),
  save: (body: { scope: "deal" | "bank"; proposal_id?: string; scenario: Partial<ScenarioDef>; scenario_id?: string; reason?: string; maker?: string }) =>
    call<{ scenario: ScenarioDef }>(`/stress2/scenarios`, post(body)),
  pending: () => call<{ pending: ScenarioDef[] }>(`/stress2/scenarios/pending`),
  decide: (sid: string, version: number, approve: boolean, reason = "", checker?: string) => call<{ scenario: ScenarioDef }>(`/stress2/scenarios/${enc(sid)}/decide`, post({ version, approve, reason, checker })),
  template: (fmt: "csv" | "json") => call<{ format: string; content: string; rules: Record<string, unknown> }>(`/stress2/import/template?fmt=${fmt}`),
  importSet: (content: string, set: string, authority: string, fmt?: string, maker?: string) => call<{ set_id: string; rows: number; status: string }>(`/stress2/import`, post({ content, set, authority, fmt, maker })),
  plan: (pid: string) => call<{ plan: Plan | null; history: Plan[] }>(`/proposals/${enc(pid)}/monitoring-plan`),
  publishPlan: (pid: string, body: { terms?: Partial<Terms> | null; reason?: string; approved_by?: string }) => call<{ plan: Plan }>(`/proposals/${enc(pid)}/monitoring-plan`, post(body)),
  changeTier: (pid: string, tier: Tier, reason: string, by?: string) => call<{ plan: Plan; change: { from: Tier; to: Tier } }>(`/proposals/${enc(pid)}/monitoring-plan/tier`, post({ tier, reason, by })),
  ewsPanel: (customerId: string, period = "") => call<EwsPanel>(`/monitoring/ews/${enc(customerId)}${period ? `?period=${enc(period)}` : ""}`),
};

/** One request per (proposal, structure, scenario set). */
export function stress2Key(pid: string, body: StressBody2): string {
  const norm = (t: unknown) => (t ? JSON.stringify(t, Object.keys(t as object).sort()) : "");
  return [pid, norm(body.terms), (body.scenarios ?? []).join(","), body.sensitivity_version ?? "", body.refresh ?? ""].join("|");
}
const CACHE = new Map<string, Promise<Stress2Result>>();
export function runStress2Cached(pid: string, body: StressBody2, fresh = false): Promise<Stress2Result> {
  const k = stress2Key(pid, body);
  let p = fresh ? undefined : CACHE.get(k);
  if (!p) {
    const { refresh: _r, ...send } = body;
    void _r;
    p = stress2Api.run(pid, send);
    CACHE.set(k, p);
    p.catch(() => CACHE.delete(k));
    if (CACHE.size > 24) CACHE.delete(CACHE.keys().next().value as string);
  }
  return p;
}

// ---------------------------------------------------------------- words and numbers

export const COL_LABEL: Record<Col, string> = {
  dscr: "DSCR", debt_ebitda: "Debt/EBITDA", ltv: "LTV limit", covenants: "Covenants", rating: "Rating / PD", stage: "Stage",
  raroc: "RAROC", limits: "Limits", ltv_cover: "LTV",
};
export const COL_ORDER: Col[] = ["dscr", "debt_ebitda", "ltv_cover", "covenants", "rating", "stage", "raroc", "limits"];
export const SEV_LABEL: Record<string, string> = { mild: "Mild", moderate: "Moderate", severe: "Severe", none: "Base", custom: "Custom" };
export const TONE_WORD: Record<Tone, string> = { pass: "Pass", amber: "Close", breach: "Breach", na: "n/a" };

const x = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "–" : `${ratio(v)}x`);

/** Columns shown for this deal: LTV (all collateral) only where collateral is pledged; covenants where the file has them. */
export function visibleCols(r: Stress2Result): Col[] {
  const rows = [r.base, ...r.rows.filter((s) => s.applicable)];
  return COL_ORDER.filter((k) => {
    if (k === "ltv_cover") return r.show_ltv;
    return rows.some((s) => s.cells[k] && s.cells[k] !== "na");
  });
}

/** The tone of a cell: the engine's, except LTV (all collateral) which is information (pass) unless the LTV limit breaches. */
const shown = (s: LadderRow) => s.applicable || s.id === "base";

/** The tone of a cell. LTV (all collateral) is information (no tone) unless an LTV limit applies (real estate). */
export function cellTone(c: Col, s: LadderRow): Tone {
  if (!shown(s)) return "na";
  if (c === "ltv_cover") {
    if (s.metrics?.ltv_cover === null || s.metrics?.ltv_cover === undefined) return "na";
    return s.cells.ltv === "breach" ? "breach" : s.cells.ltv === "amber" ? "amber" : s.cells.ltv === "pass" ? "pass" : "na";
  }
  return s.cells[c] ?? "na";
}

export function cellValue(c: Col, s: LadderRow): string {
  const m = s.metrics;
  if (!shown(s) || !m) return "";
  switch (c) {
    case "dscr": return x(m.dscr);
    case "debt_ebitda": return m.debt_ebitda === null || !Number.isFinite(m.debt_ebitda) ? "EBITDA ≤ 0" : x(m.debt_ebitda);
    case "ltv": return m.ltv === null ? "–" : pct(m.ltv, { dp: 0 });
    case "ltv_cover": return m.ltv_cover === null || m.ltv_cover === undefined ? "–" : Number.isFinite(m.ltv_cover) ? pct(m.ltv_cover, { dp: 0 }) : "no cover";
    case "covenants": {
      const cv = (s.covenants ?? []).filter((k) => k.status !== "not_modelled");
      const b = cv.filter((k) => k.status === "breach").length;
      return cv.length ? (b ? `${b}/${cv.length} broken` : "met") : "–";
    }
    case "rating": return m.notches.total ? `${m.rating} (−${m.notches.total})` : m.rating;
    case "stage": return `Stage ${m.stage}`;
    case "raroc": return m.lifetime_raroc === null ? "–" : pct(m.lifetime_raroc, { dp: 1 });
    case "limits": return s.cells.limits === "breach" ? "hard" : s.cells.limits === "amber" ? "soft / DoA" : "none new";
  }
}

export interface LadderGroup { id: string; label: string; rows: LadderRow[]; breaking: number; notApplicable: number }

export function ladderGroups(r: Stress2Result): LadderGroup[] {
  const by = new Map(r.rows.map((s) => [s.id, s]));
  return r.families.map((f) => {
    const rows = f.row_ids.map((i) => by.get(i)).filter((s): s is LadderRow => Boolean(s));
    return {
      id: f.id, label: f.label, rows,
      breaking: rows.filter((s) => s.applicable && s.breaks.length).length,
      notApplicable: rows.filter((s) => !s.applicable).length,
    };
  });
}

export const VERDICT_TONE: Record<Verdict, "negative" | "warning" | "neutral" | "positive"> = {
  "Restructure": "negative", "Approve with enhanced monitoring": "warning", "Approve, standard monitoring": "neutral", "Approve": "positive",
};
export const TIER_TONE: Record<Tier, "negative" | "warning" | "positive"> = { High: "negative", Medium: "warning", Standard: "positive" };

export function driverText(d: Reverse["drivers"][number]["driver"], v: number | null): string {
  if (v === null) return "–";
  const s = d === "revenue_pct" || d === "collateral_pct" ? pct(v, { dp: 0, signed: true }) : `${v > 0 ? "+" : ""}${Math.round(v)} bps`;
  return s.replace(/^-/, "−");
}

/** Reverse stress as short lines: "Revenue: DSCR below 1.0 at −22%; a covenant break at −8%". */
export function reverseLines(r: Stress2Result): { label: string; text: string; tone: "breach" | "amber" | "pass" }[] {
  const rv = r.reverse;
  if (!rv) return [];
  const out: { label: string; text: string; tone: "breach" | "amber" | "pass" }[] = [];
  const n = rv.notches;
  out.push({
    label: "Rating", tone: n.breaks_at.raroc === 0 ? "breach" : n.breaks_at.raroc !== null && n.breaks_at.raroc <= 2 ? "amber" : "pass",
    text: n.breaks_at.raroc === 0 ? "RAROC is below the hurdle before any downgrade"
      : n.breaks_at.raroc === null ? `RAROC clears the hurdle through ${n.searched_to} notches`
        : `survives ${n.survives_up_to} notch${n.survives_up_to === 1 ? "" : "es"}; RAROC below the hurdle at −${n.breaks_at.raroc} notch${n.breaks_at.raroc === 1 ? "" : "es"}`,
  });
  for (const d of rv.drivers) {
    const parts = d.criteria.filter((c) => c.status !== "na").map((c) =>
      c.status === "found" ? `${c.label} at ${driverText(d.driver, c.value)}` : c.status === "already" ? `${c.label} before any shock`
        : `${c.label}: not reached`);
    if (!parts.length) continue;
    const found = d.criteria.filter((c) => c.status === "found").map((c) => Math.abs(c.value ?? 0));
    const already = d.criteria.some((c) => c.status === "already");
    const near = d.driver === "revenue_pct" ? 0.15 : d.driver === "ebitda_margin_bps" ? 300 : d.driver === "rate_bps" ? 200 : 0.3;
    out.push({ label: d.label, text: parts.join("; "), tone: already ? "breach" : found.some((v) => v <= near) ? "amber" : "pass" });
  }
  return out;
}

export function fmtTrigger(t: Trigger): string {
  return t.label;
}

export function observedText(t: Trigger): string {
  const v = t.observed;
  if (v === null || v === undefined) return "not observed yet";
  if (t.unit === "share") return pct(v, { dp: 0 });
  if (t.unit === "%") return `${v.toFixed(1)}%`;
  if (t.unit === "x") return `${ratio(v)}x`;
  if (t.unit === "months") return `${v.toFixed(1)} months`;
  if (t.unit === "bps") return `${Math.round(v)} bps`;
  if (t.unit === "notches") return `${Math.round(v)} notch${Math.abs(Math.round(v)) === 1 ? "" : "es"}`;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export function eclText(v: number | null | undefined): string {
  return sar(v ?? null);
}

/** The plan sentence for the EWS page and the Book: "Monitoring tier High, set by Deal Desk on 2026-10-19 because revenue". */
export function tierSentence(p: Pick<Plan, "tier" | "set_on" | "driver_labels">): string {
  const because = (p.driver_labels ?? []).map((d) => (d.length > 1 && d[1] === d[1].toUpperCase() && /[A-Z]/.test(d[1]) ? d : d.charAt(0).toLowerCase() + d.slice(1))).join(", ") || "the stress verdict";
  return `Monitoring tier ${p.tier}, set by Deal Desk on ${p.set_on} because ${because}`;
}

// ---------------------------------------------------------------- the scenario editor

/** The shock fields of the form: key, label, unit, how the typed value maps to the engine's value. */
export const SHOCK_FIELDS: { key: string; label: string; unit: string; scale: number; placeholder: string }[] = [
  { key: "oil_pct", label: "Oil price", unit: "%", scale: 1, placeholder: "−30" },
  { key: "gdp_pct", label: "Non-oil GDP", unit: "%", scale: 1, placeholder: "−3" },
  { key: "rate_bps", label: "Benchmark rate", unit: "bps", scale: 1, placeholder: "+200" },
  { key: "sector_downturn", label: "Own-sector downturn", unit: "×", scale: 1, placeholder: "1" },
  { key: "revenue_pct", label: "Revenue", unit: "%", scale: 0.01, placeholder: "−20" },
  { key: "ebitda_margin_bps", label: "EBITDA margin", unit: "bps", scale: 1, placeholder: "−300" },
  { key: "customer_loss_share", label: "Largest customer lost", unit: "%", scale: 0.01, placeholder: "100" },
  { key: "receivable_days", label: "Payment delay", unit: "days", scale: 1, placeholder: "60" },
  { key: "delay_months", label: "Project delay", unit: "months", scale: 1, placeholder: "6" },
  { key: "collateral_pct", label: "Collateral value", unit: "%", scale: 0.01, placeholder: "−30" },
  { key: "real_estate_pct", label: "Real-estate prices", unit: "%", scale: 1, placeholder: "−20" },
  { key: "notches", label: "Rating", unit: "notches", scale: 1, placeholder: "2" },
];

/** Typed form values -> the engine's shock object (numbers only; blanks dropped; "−" accepted). */
export function shocksFrom(values: Record<string, string>, guaranteeVoid = false): Record<string, number | boolean> {
  const out: Record<string, number | boolean> = {};
  for (const f of SHOCK_FIELDS) {
    const raw = (values[f.key] ?? "").replace("−", "-").replace(/\s/g, "");
    if (!raw) continue;
    const v = Number(raw);
    if (!Number.isFinite(v) || v === 0) continue;
    out[f.key] = f.key === "notches" ? Math.abs(Math.round(v)) : Math.round(v * f.scale * 1e6) / 1e6;
  }
  if (guaranteeVoid) out.guarantee_unenforceable = true;
  return out;
}

