/**
 * Round A: the agentic intake client. API /api/v1/dealdesk/agent-intake on the Deal Desk service
 * (backend/dealdesk/agent_intake/api.py). A run works in the background; the screen polls it while the steps run.
 */
import { dealdeskOrigin, DealDeskError } from "./dealdesk";
import { friendlyError } from "./errors";

import type { AgentOverview, AgentRun, SampleManifest } from "./dealdesk-agent-intake-model.ts";
export * from "./dealdesk-agent-intake-model.ts";

const BASE = "/api/v1/dealdesk/agent-intake";

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
  if (!r.ok) throw new DealDeskError(r.status, (body && typeof body.detail === "string") ? body.detail : friendlyError("Credit request agent", r.status, body));
  return body as T;
}

export const agentIntake = {
  overview: () => call<AgentOverview>(""),
  sample: () => call<SampleManifest>("/sample"),
  /** The sample pack's files, fetched as real files for the drop (UAT). */
  sampleFiles: async (m: SampleManifest): Promise<File[]> => Promise.all(m.documents.map(async (d) => {
    const r = await fetch(`${dealdeskOrigin()}${BASE}/sample/files/${encodeURIComponent(d.name)}`, { credentials: "include" });
    if (!r.ok) throw new DealDeskError(r.status, `Could not load the sample file ${d.name}.`);
    return new File([await r.blob()], d.name, { type: r.headers.get("content-type") ?? "" });
  })),
  start: (files: File[], f: { ask: string; notes: string; rm?: string; parentRunId?: string }) => {
    const fd = new FormData();
    for (const x of files) fd.append("files", x, x.name);
    fd.append("ask", f.ask);
    if (f.notes) fd.append("notes", f.notes);
    if (f.rm) fd.append("rm", f.rm);
    if (f.parentRunId) fd.append("parent_run_id", f.parentRunId);
    return call<AgentRun>("/runs", { method: "POST", body: fd });
  },
  get: (rid: string) => call<AgentRun>(`/runs/${encodeURIComponent(rid)}`),
  revise: (rid: string, instruction: string) => call<AgentRun>(`/runs/${encodeURIComponent(rid)}/revise`, { method: "POST", body: JSON.stringify({ instruction }) }),
  attach: (rid: string, proposalId: string) => call<AgentRun>(`/runs/${encodeURIComponent(rid)}/attach`, { method: "POST", body: JSON.stringify({ proposal_id: proposalId }) }),
  docxUrl: (rid: string) => `${dealdeskOrigin()}${BASE}/runs/${encodeURIComponent(rid)}.docx`,
};
