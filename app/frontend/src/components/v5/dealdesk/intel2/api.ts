"use client";

/** R14 i: one GET per panel against /api/v1/dealdesk/intel2/{id}/{feature}, cached per deal for a minute. */

import { dealdeskOrigin, useLoad } from "@/lib/v5/dealdesk";

import type { Intel2Key } from "./model";

export const INTEL2_PATH = "/api/v1/dealdesk/intel2";
const cache = new Map<string, { at: number; p: Promise<unknown> }>();
const TTL_MS = 60_000;

export function intel2Url(proposalId: string, key: Intel2Key, structure?: string): string {
  const q = structure ? `?structure=${encodeURIComponent(structure)}` : "";
  return `${dealdeskOrigin()}${INTEL2_PATH}/${encodeURIComponent(proposalId)}/${key}${q}`;
}

export function loadIntel2<T>(proposalId: string, key: Intel2Key, structure?: string): Promise<T> {
  const k = `${key}:${proposalId}:${structure ?? ""}`;
  const hit = cache.get(k);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.p as Promise<T>;
  const p = fetch(intel2Url(proposalId, key, structure), { credentials: "include", cache: "no-store" }).then(async (r) => {
    if (r.status === 404) throw new Error("This deal is not in Data Domains yet.");
    if (!r.ok) throw new Error("This intelligence panel is temporarily unavailable.");
    return (await r.json()) as T;
  });
  cache.set(k, { at: Date.now(), p });
  p.catch(() => cache.delete(k));
  return p;
}

export const useIntel2 = <T,>(proposalId: string, key: Intel2Key, structure?: string) =>
  useLoad(() => loadIntel2<T>(proposalId, key, structure), `intel2:${key}:${proposalId}:${structure ?? ""}`);
