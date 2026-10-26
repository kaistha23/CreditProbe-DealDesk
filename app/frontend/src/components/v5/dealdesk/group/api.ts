"use client";

/**
 * R12 Session C: one request per deal for the group, conduct, governance and SWOT panels (GET /group/all), shared by
 * every panel mounted on the page; the weakness-to-mitigant map re-asks for a chosen structure (POST /group/mitigants).
 */

import { dealdeskOrigin, useLoad } from "@/lib/v5/dealdesk";

import type { GroupAll, Mitigants } from "./model";

const BASE = "/api/v1/dealdesk/proposals";
const inflight = new Map<string, { at: number; p: Promise<GroupAll> }>();
const TTL_MS = 60_000;

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "include", cache: "no-store", ...init });
  if (r.status === 404) throw new Error("This deal has no group record yet.");
  if (!r.ok) throw new Error("Group and governance are temporarily unavailable.");
  return (await r.json()) as T;
}

export function loadGroupAll(proposalId: string, refresh = false): Promise<GroupAll> {
  const hit = inflight.get(proposalId);
  if (hit && !refresh && Date.now() - hit.at < TTL_MS) return hit.p;
  const p = getJson<GroupAll>(`${dealdeskOrigin()}${BASE}/${encodeURIComponent(proposalId)}/group/all${refresh ? "?refresh=true" : ""}`);
  inflight.set(proposalId, { at: Date.now(), p });
  p.catch(() => inflight.delete(proposalId));
  return p;
}

export function useGroupAll(proposalId: string) {
  return useLoad(() => loadGroupAll(proposalId), `group-all:${proposalId}`);
}

export async function loadMitigants(proposalId: string, terms: Record<string, unknown> | null, label: string): Promise<Mitigants> {
  const r = await getJson<{ mitigants: Mitigants }>(`${dealdeskOrigin()}${BASE}/${encodeURIComponent(proposalId)}/group/mitigants`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(terms ? { terms, label } : { label }),
  });
  return r.mitigants;
}

export async function publishGroup(proposalId: string): Promise<{ findings: { rows: number; version?: number }; swot: { rows: number; version?: number } }> {
  return getJson(`${dealdeskOrigin()}${BASE}/${encodeURIComponent(proposalId)}/group/publish`, { method: "POST" });
}
