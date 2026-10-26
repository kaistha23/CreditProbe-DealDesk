/**
 * The Guided Risk Workspace API client.
 *
 * Talks to the V4 API origin (`NEXT_PUBLIC_COCKPIT_V4_API`) under
 * `/api/v1/cockpit-v4/workspace/` -- a V4-served prefix, so the runtime guard
 * in `lib/runtime.ts` lets every call through. It never falls back to the
 * legacy backend: an unconfigured origin is an error the page shows.
 *
 * Identity is never sent: the server derives the principal and tenant.
 */

/* PREVIEW WIRING. The Cockpit API client is NOT imported: an Early Warning
   request goes to the Early Warning domain app on its own port and nowhere
   else, so the frozen Cockpit's API origin is neither read nor rewired. */
function apiOrigin(): { ok: boolean; origin: string; reason: string } {
  const origin = process.env.NEXT_PUBLIC_EWS_API ?? process.env.NEXT_PUBLIC_EWS_DOMAIN_API ?? "http://127.0.0.1:8501";
  return origin
    ? { ok: true, origin, reason: "" }
    : { ok: false, origin: "", reason: "The Early Warning preview API origin is not configured." };
}

export const WORKSPACE_PREFIX = "/api/v1/ews-domain/workspace";

export class WorkspaceError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? describe((detail as { detail: unknown }).detail)
        : describe(detail);
    super(message || `request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

function describe(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return JSON.stringify(detail);
}

export function workspaceUrl(path: string): string {
  const origin = apiOrigin();
  if (!origin.ok) throw new Error(origin.reason);
  return `${origin.origin}${WORKSPACE_PREFIX}${path}`;
}

export function workspaceConfigured(): boolean {
  return apiOrigin().ok;
}

export async function wsGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(workspaceUrl(path), {
    credentials: "include",
    signal,
  });
  return parse<T>(response);
}

export async function wsSend<T>(
  path: string,
  body: unknown,
  method: "POST" | "PUT" | "PATCH" | "DELETE" = "POST",
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(workspaceUrl(path), {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  return parse<T>(response);
}

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!response.ok) {
    let detail: unknown = text;
    try {
      detail = JSON.parse(text);
    } catch {
      /* not JSON; the text is the detail */
    }
    throw new WorkspaceError(response.status, detail);
  }
  return (text ? JSON.parse(text) : null) as T;
}

/** Build a query string from defined, non-empty values only. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}
