/**
 * R13 IE client: governance and team intelligence (/api/v1/intel/governance), served by the Deal Desk service
 * (NEXT_PUBLIC_DEALDESK_API, :8508) and the Admin service (NEXT_PUBLIC_ADMIN_API, :8510); each tools menu calls its own
 * module's origin. Types mirror backend/intel/governance; helpers below are pure (node --test).
 */
import { friendlyError } from "./errors.ts";

export type GovOrigin = "dealdesk" | "admin";
const PATH = "/api/v1/intel/governance";

export function govOrigin(where: GovOrigin): string {
  const env = where === "admin" ? process.env.NEXT_PUBLIC_ADMIN_API : process.env.NEXT_PUBLIC_DEALDESK_API;
  const dflt = where === "admin" ? "http://127.0.0.1:8510" : "http://127.0.0.1:8508";
  return (env ?? dflt).replace(/\/$/, "");
}

export class GovError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call(where: GovOrigin, path: string, init?: RequestInit): Promise<Response> {
  let r: Response;
  try {
    r = await fetch(`${govOrigin(where)}${PATH}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new GovError(0, "Governance intelligence is temporarily unavailable. Please try again in a moment.");
  }
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new GovError(r.status, friendlyError("Governance intelligence", r.status, body));
  }
  return r;
}

// ---------------------------------------------------------------- types

export interface Rate { pct: number | null; k: number; n: number; ci_low_pct: number; ci_high_pct: number }
export interface Source { domain?: string; relation: string; key?: Record<string, unknown>; filter?: Record<string, unknown>; period?: string; column?: string }
export interface Fig { value: number | string | null; unit: string; source?: Source; basis?: { relations: string[]; rows: number; method: string } }
interface Base { available: boolean; lines: string[]; method?: string; data_note: string; trace_id?: string | null; as_of?: string }

export interface ExceptionType {
  type: string; label: string; n: number; n_all?: number; n_sole?: number; judged_on?: string; verdict: string;
  default?: Rate; migration?: Rate; expected_default_pct?: number; oe_default?: number; oe_default_ci?: [number, number];
  mean_notches?: number; measured_on?: string; note?: string;
}
export interface LedgerRow {
  exception_id: string; borrower_name: string; quarter: string; label: string; clause: string; approved_by: string; rm: string;
  measured: Fig; after: { stage_at_decision: number; worst_stage: number; max_dpd: number; default: number; notches: number; to_quarter: string };
}
export interface ExceptionIntel extends Base {
  peers: { exception: { n: number; default: Rate; migration: Rate }; no_exception: { n: number; default: Rate; migration: Rate } };
  types: ExceptionType[]; tighten: string[]; ledger: LedgerRow[]; ledger_total: number; window: string;
}

export interface RmRow {
  id: string; name: string; branch?: string; region?: string; decisions: number; approved: number; declined: number;
  quality: Fig; queries_per_file: number; conditions: Rate | null; promises: Rate | null; defaults: number; expected_defaults: number;
  oe: number | null; oe_ci: [number, number]; score: number | null; thin: boolean; flag: string;
}
export interface RmTrack extends Base { group: "rm" | "branch"; rows: RmRow[]; total: number; min_n: number; pd_calibration: number }

export interface LevelRow {
  rank: number; level: string; files: number; median_days: number; p75_days: number; share_of_turnaround_pct: number | null;
  pass_through: { n: number; changed: Rate | null; median_days: number | null };
  deciding: { n: number; changed: Rate | null; declined: Rate | null; overturned: Rate | null; amended: Rate | null };
}
export interface DoaProposal {
  rule: "pass_through" | "delegation_lift"; level: string; change: string; why: string; days_saved_per_year: number;
  days_saved_per_file: number; files_per_year: number; control_given_up: number; changed: Rate;
}
export interface DoaCalibration extends Base { levels: LevelRow[]; proposals: DoaProposal[] }

export type EvidenceKind = "corporate book" | "governance register (demo seed)" | "deal file" | "policy library" | "none";
export interface Coverage {
  item: string; kind: string; topic: string; topic_label: string; status: "answered" | "partial" | "not_available"; reason: string;
  /** R14 G (K15): where the answer comes from; the governance register is a demo seed */
  evidence?: EvidenceKind;
}
/** R14 G (K15): one item's answer — name → Borrower 360, EAD, stage path, approval, conditions. */
export interface InspectionAnswer {
  item: string; kind: string; found: boolean; borrower_id: string | null; name: string; href?: string; note?: string;
  ead?: { value: number; unit: string }; facilities?: number; stage_now?: number; max_dpd?: number; stage_path?: string;
  approval?: { ref: string; level: string; date: string; decision: string; text: string; evidence: string };
  conditions?: { set: number; met: number; breached?: number; open?: number; overdue?: number; text: string; evidence: string };
  exceptions?: number; decisions?: number; line: string;
}
export interface InspectionSample { key: string; who: string; label: string; request: string }
export interface InspectionPack extends Base {
  pack_id: string; request: string; sample: string[]; sample_rule: string | null;
  ask: { topics: string[]; topics_implied: boolean };
  items: { kind: string; id: string; evidence: Record<string, unknown> | null }[];
  clauses: { clause: string; heading: string; quote: string }[];
  coverage: Coverage[]; coverage_summary: { answered: number; partial: number; not_available: number };
  /** R14 G (K14, K15) */
  pack_note?: string; summary?: string; answers?: InspectionAnswer[]; samples?: InspectionSample[]; sections?: string[];
}

// ---------------------------------------------------------------- calls

export const gov = {
  exceptions: async (where: GovOrigin): Promise<ExceptionIntel> => (await call(where, "/exceptions?limit=40")).json(),
  rmTrack: async (where: GovOrigin, group: "rm" | "branch"): Promise<RmTrack> => (await call(where, `/rm-track?group=${group}`)).json(),
  doa: async (where: GovOrigin): Promise<DoaCalibration> => (await call(where, "/doa")).json(),
  /** R14 G (K14): the three sample requests and the pack sections, for the empty state. */
  inspectionSamples: async (where: GovOrigin): Promise<{ samples: InspectionSample[]; sections: string[] }> =>
    (await call(where, "/inspection/samples")).json(),
  inspection: async (where: GovOrigin, request: string, sample: string[]): Promise<InspectionPack> =>
    (await call(where, "/inspection", { method: "POST", body: JSON.stringify({ request, sample }) })).json(),
  /** Downloads a house-style file (Word or Excel). */
  download: async (where: GovOrigin, what: "inspection-docx" | "inspection-xlsx" | "exceptions" | "rm-track" | "doa",
                   body?: { request: string; sample: string[] }, group: "rm" | "branch" = "rm"): Promise<void> => {
    const r = what.startsWith("inspection")
      ? await call(where, `/inspection/export?fmt=${what.endsWith("docx") ? "docx" : "xlsx"}`, { method: "POST", body: JSON.stringify(body) })
      : await call(where, `/${what}/export?group=${group}`);
    const blob = await r.blob();
    const name = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") ?? "")?.[1] ?? `${what}.${what.endsWith("docx") ? "docx" : "xlsx"}`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  },
};

// ---------------------------------------------------------------- pure helpers

/** Sample identifiers typed by the user: commas, spaces or new lines; upper-cased; de-duplicated. */
export function parseSample(text: string): string[] {
  const out: string[] = [];
  for (const t of (text ?? "").split(/[\s,;]+/)) {
    const u = t.trim().toUpperCase();
    if (u && !out.includes(u)) out.push(u);
  }
  return out.slice(0, 200);
}

export function pctText(v: number | null | undefined, nd = 1): string {
  return v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(nd)}%`;
}

export function rateText(r: Rate | null | undefined): string {
  if (!r || r.pct == null) return "—";
  return `${r.pct.toFixed(1)}% (${r.ci_low_pct.toFixed(1)}–${r.ci_high_pct.toFixed(1)})`;
}

export function ratioText(v: number | null | undefined, ci?: [number, number]): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return ci ? `${v.toFixed(2)}× (${ci[0].toFixed(2)}–${ci[1].toFixed(2)})` : `${v.toFixed(2)}×`;
}

export type Tone = "positive" | "negative" | "warning" | "neutral" | "accent";
export function verdictTone(v: string): Tone {
  return v === "tighten" ? "negative" : v === "watch" ? "warning" : v === "keep" ? "positive" : "neutral";
}
export function coverageTone(s: Coverage["status"]): Tone {
  return s === "answered" ? "positive" : s === "partial" ? "warning" : "negative";
}
export function flagTone(f: string): Tone {
  return f.startsWith("worse") ? "negative" : f.startsWith("better") ? "positive" : f ? "warning" : "neutral";
}
export const COVERAGE_LABEL: Record<Coverage["status"], string> = { answered: "Answered", partial: "Partly", not_available: "Not available" };

/** Item × topic grid for the coverage matrix (rows keep request order). */
export function coverageGrid(cov: Coverage[]): { items: string[]; topics: { key: string; label: string }[]; cell: (i: string, t: string) => Coverage | undefined } {
  const items: string[] = [];
  const topics: { key: string; label: string }[] = [];
  const m = new Map<string, Coverage>();
  for (const c of cov) {
    if (!items.includes(c.item)) items.push(c.item);
    if (!topics.some((t) => t.key === c.topic)) topics.push({ key: c.topic, label: c.topic_label });
    m.set(`${c.item}|${c.topic}`, c);
  }
  return { items, topics, cell: (i, t) => m.get(`${i}|${t}`) };
}

/** The panels a tools menu lists, in order. */
export const GOV_PANELS = ["inspection", "exceptions", "rm-track", "doa"] as const;
export type GovPanel = (typeof GOV_PANELS)[number];
export function parseGovPanel(v: string | null | undefined): GovPanel | null {
  return (GOV_PANELS as readonly string[]).includes(v ?? "") ? (v as GovPanel) : null;
}
