"use client";

/**
 * R13 Session IA: one GET per panel against /api/v1/dealdesk/intel/approval/{id}/{challenger|reverse|security|consistency},
 * cached per deal for a minute (the reverse solver runs the Optimise engine and the stress ladder, so it is not re-asked
 * on every open).
 */

import { dealdeskOrigin, useLoad } from "@/lib/v5/dealdesk";

import type { Challenger, Consistency, Reverse, Security } from "./model";

export const INTEL_APPROVAL_PATH = "/api/v1/dealdesk/intel/approval";
export type ApprovalTool = "challenger" | "reverse" | "security" | "consistency";

const cache = new Map<string, { at: number; p: Promise<unknown> }>();
const TTL_MS = 60_000;
const UNAVAILABLE: Record<ApprovalTool, string> = {
  challenger: "The committee challenger is temporarily unavailable.",
  reverse: "The reverse solver is temporarily unavailable.",
  security: "The security optimiser is temporarily unavailable.",
  consistency: "Decision consistency is temporarily unavailable.",
};

export function approvalUrl(proposalId: string, tool: ApprovalTool): string {
  return `${dealdeskOrigin()}${INTEL_APPROVAL_PATH}/${encodeURIComponent(proposalId)}/${tool}`;
}

export function loadApproval<T>(proposalId: string, tool: ApprovalTool, refresh = false): Promise<T> {
  const k = `${tool}:${proposalId}`;
  const hit = cache.get(k);
  if (hit && !refresh && Date.now() - hit.at < TTL_MS) return hit.p as Promise<T>;
  const p = fetch(approvalUrl(proposalId, tool), { credentials: "include", cache: "no-store" }).then(async (r) => {
    if (r.status === 404) throw new Error("This deal is not in Data Domains yet.");
    if (!r.ok) throw new Error(UNAVAILABLE[tool]);
    return (await r.json()) as T;
  });
  cache.set(k, { at: Date.now(), p });
  p.catch(() => cache.delete(k));
  return p;
}

export const useChallenger = (id: string) => useLoad(() => loadApproval<Challenger>(id, "challenger"), `ia-challenger:${id}`);
export const useReverse = (id: string) => useLoad(() => loadApproval<Reverse>(id, "reverse"), `ia-reverse:${id}`);
export const useSecurity = (id: string) => useLoad(() => loadApproval<Security>(id, "security"), `ia-security:${id}`);
export const useConsistency = (id: string) => useLoad(() => loadApproval<Consistency>(id, "consistency"), `ia-consistency:${id}`);
