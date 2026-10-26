/** R13 IB client: renewal autopilot, covenant designer, who to call today (all on the Deal Desk service). */
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import {
  type CallList, type CovenantDesign, type RenewalClass, type RenewalItem, type RenewalPaper, type RenewalQueue, callsQuery, renewalQuery,
} from "@/lib/v5/intel-ib";

async function call<T>(path: string, init?: RequestInit, what = "This tool"): Promise<T> {
  const r = await fetch(`${dealdeskOrigin()}${path}`, { credentials: "include", cache: "no-store", ...init });
  if (!r.ok) {
    let msg = `${what} is temporarily unavailable.`;
    try { const j = (await r.json()) as { detail?: unknown }; if (typeof j.detail === "string") msg = j.detail; } catch { /* keep the default */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

const REN = "/api/v1/dealdesk/intel/renewals";
const COV = "/api/v1/dealdesk/intel/covenants";
const CALLS = "/api/v1/intel/calls";

export const ibApi = {
  renewals: (p: { cls?: "all" | RenewalClass; q?: string; limit?: number; offset?: number; scope?: "material" | "all" }) =>
    call<RenewalQueue>(`${REN}${renewalQuery(p)}`, undefined, "The renewal autopilot"),
  renewal: (fid: string) => call<RenewalItem>(`${REN}/${encodeURIComponent(fid)}`, undefined, "The renewal autopilot"),
  renewalPaper: (fid: string) => call<RenewalPaper>(`${REN}/${encodeURIComponent(fid)}/paper`, { method: "POST" }, "The papers engine"),
  noteDocxHref: (fid: string) => `${dealdeskOrigin()}${REN}/${encodeURIComponent(fid)}/note.docx`,
  href: (path: string) => `${dealdeskOrigin()}${path}`,
  covenants: (deal: string, minHeadroom = 15) =>
    call<CovenantDesign>(`${COV}/${encodeURIComponent(deal)}?grid=false&min_headroom=${minHeadroom}`, undefined, "The covenant designer"),
  calls: (p: { limit?: number; offset?: number; signal?: string; minWeight?: number; scope?: "material" | "all" }) =>
    call<CallList>(`${CALLS}${callsQuery(p)}`, undefined, "Who to call today"),
};
