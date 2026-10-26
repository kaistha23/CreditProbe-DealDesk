/**
 * Noor's client: the brief endpoints on the Deal Desk service (`/api/v1/noor`, backend/agents_v5/brief/api.py), with
 * the session cookie. Errors become one plain sentence (lib/v5/errors.ts).
 */
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import { friendlyError } from "@/lib/v5/errors";

import type {
  Brief, BriefItem, CommitteeResult, DecisionOption, DriversAnswer, HereAnswer, HereFix, IssueScript, NoorSettings, OptionsAnswer,
  PageContextLike, Persona, WhyAnswer,
} from "./noor-model";

const BASE = "/api/v1/noor";

export class NoorError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${dealdeskOrigin()}${BASE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new NoorError(0, "Noor is temporarily unavailable. Please try again in a moment.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new NoorError(res.status, friendlyError("Noor", res.status, body));
  return body as T;
}

export const noor = {
  /** R15 L9: the answer in the page context; `{here: false, reason}` when the question belongs elsewhere. */
  here: (question: string, context: PageContextLike, force = false) =>
    call<HereAnswer | { here: false; reason: string | null }>("/here", { method: "POST", body: JSON.stringify({ question, context, force }) }),
  hereFix: (dealId: string, fromKey: string, target = "moderate") =>
    call<HereFix>("/here/fix", { method: "POST", body: JSON.stringify({ deal_id: dealId, from_key: fromKey, target }) }),
  brief: (p: { persona?: Persona | null; module?: string; attention?: unknown[]; top?: number }) =>
    call<Brief>("/brief", { method: "POST", body: JSON.stringify({ persona: p.persona ?? "", module: p.module ?? "",
      attention: p.attention ?? [], top: p.top ?? 5, hour: new Date().getHours() }) }),
  why: (item: BriefItem) => call<WhyAnswer>("/why", { method: "POST", body: JSON.stringify({ item_id: item.id, item }) }),
  /** R14 K10: one line's spoken script (40–70 s, English and Arabic). */
  script: (item: BriefItem) => call<IssueScript>("/script", { method: "POST", body: JSON.stringify({ item_id: item.id, item }) }),
  drivers: (item: BriefItem) =>
    call<DriversAnswer>("/drivers", { method: "POST", body: JSON.stringify({ item_id: item.id, item }) }),
  options: (item: BriefItem) =>
    call<OptionsAnswer>("/options", { method: "POST", body: JSON.stringify({ item_id: item.id, item }) }),
  committee: (item: BriefItem, option: DecisionOption) =>
    call<CommitteeResult>("/committee", { method: "POST", body: JSON.stringify({ item_id: item.id, item, option }) }),
  settings: () => call<NoorSettings>("/settings"),
  /** The reader's own voice choice (R13 H, J1). */
  voice: () => call<{ on: boolean | null; language: "en" | "ar-gulf" | null }>("/voice"),
  saveVoice: (v: { on?: boolean; language?: "en" | "ar-gulf" }) =>
    call<{ on: boolean | null; language: "en" | "ar-gulf" | null }>("/voice", { method: "PUT", body: JSON.stringify(v) }),
  saveSettings: (s: Partial<NoorSettings>) => call<NoorSettings>("/settings", { method: "PUT", body: JSON.stringify(s) }),
};
