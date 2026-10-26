/**
 * R16 c: credit response from an uploaded business request, on the Deal Desk service (/api/v1/dealdesk/credit-response/*).
 *
 * Credit uploads the RM's business request (Word, PDF or photos of its pages) with the customer's documents; the UI
 * runs the steps one by one (read, deal, proposal check, review, analysis, structure, stress, stress-proof,
 * recommendation, RM brief, response), each timed with its plain words, then previews the bank-form response and
 * offers Word and PDF. The helpers below are pure and tested (dealdesk-credit-response.test.ts).
 */
import { friendlyError } from "./errors.ts";

const ENGINE = "/api/v1/dealdesk";

export function crOrigin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

export class CrError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${crOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new CrError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string" ? (body as { detail: string }).detail : "";
    throw new CrError(r.status, r.status === 400 && detail ? detail : friendlyError("Deal Desk", r.status, body));
  }
  return body as T;
}

// ---------------------------------------------------------------- schemas

export type CrStepKey = "read" | "deal" | "check" | "review" | "analysis" | "structure" | "stress" | "proof" | "recommendation" | "brief" | "response";
export type CrStatus = "pending" | "running" | "done" | "error";

export interface CrStep {
  key: CrStepKey; label: string; status: CrStatus; seconds?: number; plain_words?: string[]; headline?: string;
  data?: Record<string, unknown>; at?: string;
}

export interface CrCase {
  case_id: string; created: string; by: string; status: string; customer?: string; proposal_id?: string; decision?: string;
  files: { name: string; bytes: number }[]; steps: CrStep[]; next: CrStepKey | null;
}

export interface CrOverview {
  steps: { key: CrStepKey; label: string }[]; accepted: string[]; ocr: { available?: boolean; engine?: string };
  cases: { case_id: string; created: string; customer?: string; proposal_id?: string; status: string; decision?: string }[];
  demo: { customer: string; request: string[]; documents: Record<string, number> } | null; plain_words: string[];
}

export type Block =
  | { t: "p"; text: string; exempt?: boolean }
  | { t: "bullets" | "numbered"; items: string[] }
  | { t: "table"; header: string[]; rows: (string | number)[][]; source?: string }
  | { t: "kv"; pairs: [string, string][]; cols?: number }
  | { t: "h"; text: string }
  | { t: "sign"; rows: [string, string][] }
  | { t: "box"; title: string; lines?: number };

export interface PaperSection { key: string; n: number | null; heading: string; voice: string; blocks: Block[]; sources?: string[] }
export interface PaperPart { key: string; title: string; subtitle: string; sections: PaperSection[] }
export interface CrPaper {
  proposal_id: string; customer: string; title: string; form_title?: string; as_of_label?: string; parts: PaperPart[];
  header_line: [string, string][];
  summary: { decision: string; head: string; recommendation: string[]; conditions: string[]; monitoring: string[];
             observations: { title: string; text: string; severity: string; source: string }[]; plain_words: string[]; sections: number };
}

export interface BriefItem { n: number; severity: string; section: string; title: string; query: string; evidence: string; source: string }
export interface Brief { to: string; subject: string; due: string; count: number; critical: number; major: number; text: string;
                         groups: { severity: string; label: string; items: BriefItem[] }[] }

// ---------------------------------------------------------------- calls

export const creditResponse = {
  overview: () => call<CrOverview>("/credit-response"),
  start: (files: File[], requestName?: string) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    if (requestName) fd.append("request_name", requestName);
    return call<CrCase>("/credit-response/cases", { method: "POST", body: fd });
  },
  startDemo: (kind: "docx" | "pdf" | "jpg", documents: "pdf" | "word" | "images" = "pdf") =>
    call<CrCase>("/credit-response/cases/demo", { method: "POST", body: JSON.stringify({ kind, documents }) }),
  get: (cid: string) => call<CrCase>(`/credit-response/cases/${encodeURIComponent(cid)}`),
  step: (cid: string, step: CrStepKey) => call<CrCase>(`/credit-response/cases/${encodeURIComponent(cid)}/steps/${step}`, { method: "POST" }),
  paper: (cid: string) => call<CrPaper>(`/credit-response/cases/${encodeURIComponent(cid)}/paper`),
  fileUrl: (cid: string, file: "response.docx" | "response.pdf" | "brief.docx") =>
    `${crOrigin()}${ENGINE}/credit-response/cases/${encodeURIComponent(cid)}/${file}`,
};

// ---------------------------------------------------------------- pure helpers (tested)

/** The next step to run, or null when the case is finished or a step failed in a way the next cannot pass. */
export function nextStep(c: Pick<CrCase, "steps">): CrStepKey | null {
  for (const s of c.steps) {
    if (s.status === "pending") return s.key;
    if (s.status === "error" && (s.key === "read" || s.key === "deal")) return null;
  }
  return null;
}

/** Progress as done / total and a percentage (an error counts as finished: the response says why). */
export function progress(c: Pick<CrCase, "steps">): { done: number; total: number; pct: number } {
  const total = c.steps.length;
  const done = c.steps.filter((s) => s.status === "done" || s.status === "error").length;
  return { done, total, pct: total ? Math.round((100 * done) / total) : 0 };
}

/** Text markup of the bank form: **bold** and __bold underlined__ as runs. */
export function runs(text: string): { text: string; bold: boolean; underline: boolean }[] {
  const out: { text: string; bold: boolean; underline: boolean }[] = [];
  for (const chunk of String(text).split(/(\*\*.+?\*\*|__.+?__)/g)) {
    if (!chunk) continue;
    if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 4) out.push({ text: chunk.slice(2, -2), bold: true, underline: false });
    else if (chunk.startsWith("__") && chunk.endsWith("__") && chunk.length > 4) out.push({ text: chunk.slice(2, -2).replace(/\*\*/g, ""), bold: true, underline: true });
    else out.push({ text: chunk, bold: false, underline: false });
  }
  return out;
}

/** A severity as a chip tone. */
export function severityTone(s: string): "negative" | "warning" | "neutral" {
  return s === "critical" ? "negative" : s === "major" ? "warning" : "neutral";
}

/** Which uploaded file names look like the business request (the server decides from the content too). */
export function looksLikeRequest(name: string): boolean {
  const n = name.toLowerCase();
  return n.includes("business_request") || n.includes("business-request") || n.startsWith("request");
}
