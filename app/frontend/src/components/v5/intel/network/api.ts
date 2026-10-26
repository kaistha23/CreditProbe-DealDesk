/**
 * PLAN_R13 §I Session IC: the network and events endpoints (prefix /api/v1/intel/network, on the Borrower 360 service).
 */
import { B360Error, b360Origin } from "@/lib/v5/b360";
import { friendlyError } from "@/lib/v5/errors";

import type { ContagionResult, EmployerRanking, EmployerResult, EventCatalogue, EventRequest, EventResult, Severity } from "./format";

export const NETWORK_PREFIX = "/api/v1/intel/network";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${b360Origin()}${NETWORK_PREFIX}${path}`, {
      ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new B360Error(0, "Network intelligence is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new B360Error(response.status, friendlyError("Network intelligence", response.status, body));
  return body as T;
}

const e = encodeURIComponent;

function q(params: Record<string, string | number | undefined | null>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
}

export const networkApi = {
  catalogue: (signal?: AbortSignal) => call<EventCatalogue>("/events/catalogue", { signal }),
  event: (req: EventRequest, signal?: AbortSignal) => call<EventResult>("/event", { method: "POST", body: JSON.stringify(req), signal }),
  contagion: (borrower: string, severity: Severity = "moderate", period?: string, signal?: AbortSignal) =>
    call<ContagionResult>(`/contagion/${e(borrower)}${q({ severity, period })}`, { signal }),
  employers: (limit = 10, period?: string, signal?: AbortSignal) => call<EmployerRanking>(`/employers${q({ limit, period })}`, { signal }),
  employer: (employer: string, period?: string, signal?: AbortSignal) => call<EmployerResult>(`/employer/${e(employer)}${q({ period })}`, { signal }),
};
