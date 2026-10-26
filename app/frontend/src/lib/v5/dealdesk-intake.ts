/**
 * R16 i: the customer file (document intake) client and its pure helpers.
 *
 * API: /api/v1/dealdesk/intake on the Deal Desk service (backend/dealdesk/intake/api.py). Upload many files at once
 * (Word, PDF, photos); the service reads, classifies, extracts, judges the checklist, reconciles across documents and
 * pulls the Bank's data when the customer already banks with us. Helpers here are pure (node --test).
 */
import { dealdeskOrigin, DealDeskError } from "./dealdesk";
import { friendlyError } from "./errors";

const BASE = "/api/v1/dealdesk/intake";

import { type CustomerFile, type Facts, type IntakeOverview, batchFiles } from "./dealdesk-intake-model.ts";
export * from "./dealdesk-intake-model.ts";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${dealdeskOrigin()}${BASE}${path}`, {
      ...init, credentials: "include", cache: "no-store",
      headers: init?.body instanceof FormData || !init?.body ? init?.headers : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new DealDeskError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new DealDeskError(r.status, friendlyError("Customer file", r.status, body));
  return body as T;
}

function form(files: File[], extra: Record<string, string> = {}): FormData {
  const f = new FormData();
  for (const x of files) f.append("files", x, x.name);
  for (const [k, v] of Object.entries(extra)) if (v) f.append(k, v);
  return f;
}

export const intake = {
  overview: () => call<IntakeOverview>(""),
  open: (files: File[], proposalId = "") => call<CustomerFile>("/files", { method: "POST", body: form(files, { proposal_id: proposalId }) }),
  add: (iid: string, files: File[]) => call<CustomerFile>(`/files/${encodeURIComponent(iid)}/documents`, { method: "POST", body: form(files) }),
  get: (iid: string) => call<CustomerFile>(`/files/${encodeURIComponent(iid)}`),
  byDeal: (pid: string) => call<CustomerFile>(`/by-deal/${encodeURIComponent(pid)}`),
  facts: (iid: string) => call<Facts>(`/files/${encodeURIComponent(iid)}/facts`),
  document: (iid: string, docId: string) =>
    call<{ doc_id: string; file_name: string; read_method: string; doc_label: string; fields: Record<string, { value: unknown; label: string; type: string; line: number; raw: string }>; text: string; error?: string }>(
      `/files/${encodeURIComponent(iid)}/documents/${encodeURIComponent(docId)}`),
  rawUrl: (iid: string, docId: string) => `${dealdeskOrigin()}${BASE}/files/${encodeURIComponent(iid)}/documents/${encodeURIComponent(docId)}/raw`,
  setType: (iid: string, docId: string, docType: string) =>
    call<CustomerFile>(`/files/${encodeURIComponent(iid)}/documents/${encodeURIComponent(docId)}/type`, { method: "POST", body: JSON.stringify({ doc_type: docType }) }),
  remove: (iid: string, docId: string) => call<CustomerFile>(`/files/${encodeURIComponent(iid)}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" }),
  attach: (iid: string, proposalId: string) =>
    call<CustomerFile>(`/files/${encodeURIComponent(iid)}/attach`, { method: "POST", body: JSON.stringify({ proposal_id: proposalId }) }),
};

/** Upload in small batches so the screen can say how far it got ("Read 12 of 38 …"); photos of one document stay in one batch. */
export async function uploadInBatches(files: File[], opts: { intakeId?: string; proposalId?: string; size?: number;
  onProgress?: (done: number, total: number, file: CustomerFile) => void }): Promise<CustomerFile> {
  const batches = batchFiles(files, opts.size ?? 6);
  let v: CustomerFile | null = null;
  let iid = opts.intakeId ?? "";
  let done = 0;
  for (const b of batches) {
    v = iid ? await intake.add(iid, b) : await intake.open(b, opts.proposalId ?? "");
    iid = v.intake_id;
    done += b.length;
    opts.onProgress?.(done, files.length, v);
  }
  return v!;
}

