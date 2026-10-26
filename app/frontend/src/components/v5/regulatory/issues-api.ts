/**
 * R14 r (K2, K4): the issue-view client. The endpoints live on the Deal Desk service next to Noor's brief
 * (backend/regulatory/issues/api.py): GET /api/v1/regulatory/issues and /api/v1/regulatory/issues/{id}.
 */
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import { friendlyError } from "@/lib/v5/errors";

export interface Source { domain: string; relation: string; key?: Record<string, unknown>; column?: string; period?: string; method?: string }
export interface Fig { label: string; value: number | null; unit: string; display: string; source?: Source }
export interface Column { key: string; label: string; unit: "" | "SAR mn" | "%" | "n" | "text" | string }
export interface IssueTable {
  id: string; title: string; columns: Column[]; rows: Record<string, unknown>[]; total: Record<string, unknown> | null; note: string;
}
export interface BridgeStep {
  key: string; label: string; value: number; display: string; share_pct: number | null; explain: string;
  facilities: number | null; ead: number | null; rows: string[]; link: { issue: string; href: string } | null;
}
export interface Bridge {
  title: string; total: number; total_display: string; unit: string; steps: BridgeStep[]; sums_to_total: boolean; method: string;
}
export interface Split { name: string; value: number; display: string; share_pct: number | null; borrowers: number }
export interface Concentration {
  label: string; borrowers: number; total: number; total_display: string; top10_share_pct: number | null;
  top: { borrower_id: string; name: string; value: number; display: string; share_pct: number | null; sector: string;
         branch: string; rm: string; href: string }[];
  by_sector: Split[]; by_branch: Split[]; by_rm: Split[];
}
export interface IssueAction {
  n: number; action: string; owner: string; due: string; why: string; figure?: Fig; link?: { label: string; href: string };
}
export interface IssueView {
  id: string; kind: string; check_id?: string; module: string; title: string; period: string; severity: string;
  headline: string; plain_words: string[];
  rule: { article: string; text: string; href: string; detail: string };
  comparison: { sentence: string; bank: Fig; required: Fig; model: Fig | null; figures: Fig[] } | null;
  tables: IssueTable[]; bridge: Bridge | null; concentration: Concentration | null; impact: Fig[];
  actions: IssueAction[]; exposures: IssueTable | null;
  source: { label: string; domain: string; relation: string; href: string } | null;
  cannot_tell: string[]; href: string;
}
export interface IssueSummary {
  id: string; kind: string; title: string; article: string; book: string; period: string; n: number | null;
  ead: number | null; shortfall: number; severity: string; line: string; href: string;
}

const BASE = "/api/v1/regulatory/issues";

async function call<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${dealdeskOrigin()}${BASE}${path}`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new Error("The regulatory issues are temporarily unavailable. Please try again in a moment.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(friendlyError("Regulatory issues", res.status, body));
  return body as T;
}

export const issuesApi = {
  list: () => call<{ issues: IssueSummary[]; count: number }>(""),
  get: (id: string) => call<IssueView>(`/${encodeURIComponent(id)}`),
};
