/**
 * PLAN_R9 Session E: P7 proposal review and Admin → Deal Desk Parameters, on the Deal Desk service
 * (/api/v1/dealdesk/review/*, /api/v1/dealdesk/desk_params). Proposal amounts are AED million; ratios are decimals.
 */
import { dealdeskOrigin } from "./dealdesk.ts";
import { friendlyError } from "./errors.ts";
import { fmt } from "@/lib/v5/format";

const ENGINE = "/api/v1/dealdesk";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${dealdeskOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("Deal Desk", r.status, body));
  return body as T;
}

export interface Facility { name: string; kind: string; existing: number; proposed: number; bps: number; cash_margin?: number }
export interface Check { check: string; result: "Pass" | "Fail"; detail: string; ref: string }
export interface Gap { id: string; item: string; context: string; ref: string; status: string }
export interface Raroc { revenue: number; income: number; fees: number; deposit_value: number; opex: number; el: number; ead: number;
  capital: number; rap: number; raroc: number; hurdle: number; clears_hurdle: boolean; funded: number; nonfunded: number }
export interface Counter { title: string; terms: string[]; total_limits: number; exposure_change: number; ead: number; raroc: number;
  hurdle: number; clears_hurdle: boolean; raroc_change: number; group_cap: number | null }
export interface Review {
  case_id: string | null; as_of: string; file_name: string;
  powered_by: { pack: string; name: string; rules: string[]; confidence: string; trace: string };
  summary: { borrower: string; group: string; profile: string; sector: string; rating: string; tier: string; currency: string;
    request: string[]; facilities: Facility[]; total_existing: number; total_proposed: number; recommendation: string; cro_box: string;
    projects: { name: string; status: string }[] };
  checks: Check[]; score: { total: number; max: number; band: string; subscores: { name: string; max: number; score: number }[] };
  gaps: Gap[]; weaknesses: { weakness: string; mitigant: string | null; covered: boolean }[];
  pre_deal: { raroc: Raroc; raroc_without_deposits: Raroc; verdict: string;
    stressed_cash_flow: { peak_deficit: number; funded_lines: number; month: number; shortfall: number };
    approval_route: { amount_aed_mn: number; amount_sar_mn: number; level: string };
    cro_review: { required: boolean; ref: string; cro_box: string; reason: string };
    debt_capacity: { ebitda_based: number; cash_flow_based: number } };
  counter_proposals: Counter[];
  watch_entry: { name: string; status: string; stage: number; rationale: string; conclusion: string; items: { item: string; due: string; status: string }[] };
  graph: { from: string; to: string; kind: string; label: string }[];
  uploaded?: { file: string; characters: number; matched: boolean };
  message?: string;
}
export interface CaseRow { case_id: string; borrower: string; sector: string; tier: string; file_name: string; total_proposed: number;
  score: number; raroc: number; hurdle: number; verdict: string }
export interface ParamRow { table: string; key: string; label: string; kind: string; value: unknown; why: string; where: string;
  version: string; effective_from: string; owner: string; editable: boolean }

export const review = {
  cases: () => call<{ cases: CaseRow[] }>("/review/cases"),
  get: (id: string) => call<Review>(`/review/${encodeURIComponent(id)}`),
  upload: (file: File) => { const f = new FormData(); f.append("file", file); return call<Review>("/review/upload", { method: "POST", body: f }); },
  query: (id: string, gapId: string) => call<{ status: string; to: string }>(`/review/${encodeURIComponent(id)}/query`,
    { method: "POST", body: JSON.stringify({ gap_id: gapId }) }),
  opinionUrl: (id: string) => `${dealdeskOrigin()}${ENGINE}/review/${encodeURIComponent(id)}/opinion.docx`,
  proposalUrl: (id: string) => `${dealdeskOrigin()}${ENGINE}/review/${encodeURIComponent(id)}/proposal.docx`,
  params: () => call<{ rows: ParamRow[]; history: { version: string; effective_from: string; by: string; reason: string }[] }>("/desk_params"),
  setParam: (table: string, key: string, value: unknown, reason: string) =>
    call<{ version: string; effective_from: string; rows: ParamRow[]; cases: CaseRow[] }>("/desk_params",
      { method: "PUT", body: JSON.stringify({ table, key, value, reason }) }),
};

/** AED millions: "AED 656.8m", "AED 8.20bn". */
export function aed(m: number | null | undefined): string {
  if (m === null || m === undefined || !Number.isFinite(m)) return "–";
  return fmt.sar(m).replace("SAR", "AED");
}
export const pc = (v: number | null | undefined) => fmt.pct(v ?? null);
