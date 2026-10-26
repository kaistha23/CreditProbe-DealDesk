/**
 * PLAN_R12 Session P: the products endpoints (prefix /api/v1/dealdesk/products).
 */
import * as React from "react";

import { DealDeskError, dealdeskOrigin } from "@/lib/v5/dealdesk";
import { friendlyError } from "@/lib/v5/errors";

import type { EscrowResult, ProjectResult, SmeCount, SmeDecision, SmeLane, SyndicationResult } from "./format";

const ENGINE = "/api/v1/dealdesk";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${dealdeskOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new DealDeskError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new DealDeskError(response.status, friendlyError("Deal Desk", response.status, body));
  return body as T;
}

const e = encodeURIComponent;

export const productsApi = {
  project: (pid: string, signal?: AbortSignal) => call<ProjectResult>(`/products/${e(pid)}/project`, { signal }),
  escrow: (pid: string, signal?: AbortSignal) => call<EscrowResult>(`/products/${e(pid)}/escrow`, { signal }),
  syndication: (pid: string, signal?: AbortSignal) => call<SyndicationResult>(`/products/${e(pid)}/syndication`, { signal }),
  sections: (pid: string, signal?: AbortSignal) =>
    call<{ proposal_id: string; product: string; sections: ("project" | "escrow" | "syndication" | "sme")[] }>(`/products/${e(pid)}/sections`, { signal }),
  smeLane: (status = "", signal?: AbortSignal) => call<SmeLane>(`/products/sme/fast-track${status ? `?status=${e(status)}` : ""}`, { signal }),
  smeCount: (signal?: AbortSignal) => call<SmeCount>("/products/sme/fast-track/count", { signal }),
  smeOne: (aid: string, signal?: AbortSignal) => call<SmeDecision>(`/products/sme/fast-track/${e(aid)}`, { signal }),
  smeDecide: (aid: string) => call<SmeDecision & { published: { published: boolean; reason?: string } }>(
    `/products/sme/fast-track/${e(aid)}/decide`, { method: "POST" }),
};

/** Load once per key (and again on `reload`); abort on change. Loading is derived, so no state is set inside the effect body. */
export function useProduct<T>(key: string, load: (signal: AbortSignal) => Promise<T>): { data: T | null; error: string; loading: boolean; reload: () => void } {
  const [n, setN] = React.useState(0);
  const want = `${key}#${n}`;
  const [state, setState] = React.useState<{ key: string; data: T | null; error: string }>({ key: "", data: null, error: "" });
  const loadRef = React.useRef(load);
  React.useEffect(() => { loadRef.current = load; });
  React.useEffect(() => {
    const ac = new AbortController();
    loadRef.current(ac.signal)
      .then((data) => { if (!ac.signal.aborted) setState({ key: want, data, error: "" }); })
      .catch((err: unknown) => {
        if (ac.signal.aborted) return;
        setState({ key: want, data: null, error: err instanceof Error ? err.message : "Could not load." });
      });
    return () => ac.abort();
  }, [want]);
  const fresh = state.key === want;
  const same = state.key.slice(0, state.key.lastIndexOf("#")) === key;   // keep the last answer while reloading the same key
  return { data: same ? state.data : null, error: fresh ? state.error : "", loading: !fresh, reload: () => setN((x) => x + 1) };
}
