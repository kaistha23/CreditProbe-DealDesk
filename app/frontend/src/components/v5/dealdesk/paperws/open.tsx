"use client";

/**
 * Rounds W/T entry points: open (or reopen) a document's workspace, and the lists that reopen it.
 *
 *   const open = useOpenPaper();  open("proposal", { proposalId, structure, section })   // "Prepare the credit proposal"
 *                                 open("request", { requestId })                          // the business request studio
 *   <DealPapers proposalId="DD-06" />          the deal's Papers (More → Papers): every workspace of the deal, newest first
 *   usePaperRows(limit)                        the reader's workspaces as rows (Recent work, the Workspace briefing)
 *   <PaperTraceList />                         Trace & Lineage: each paper's Provenance view
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { FileText, ListTree, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { errorText, getJson } from "../papers/paper-view";
import { type PaperKind, type PwState, type PwWorkspace, openBody, pwHref, pwUrls } from "./model";

export function useOpenPaper() {
  const router = useRouter();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const open = React.useCallback(async (kind: PaperKind, ref: { proposalId?: string; structure?: string | null; requestId?: string; fresh?: boolean; section?: string }) => {
    setBusy(true);
    setError("");
    try {
      const st = await getJson<PwState>(pwUrls.open(), { method: "POST", body: JSON.stringify(openBody(kind, ref)) });
      router.push(`${pwHref(st.workspace.ws_id)}${ref.section ? `?section=${encodeURIComponent(ref.section)}` : ""}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }, [router]);
  return { open, busy, error };
}

export function OpenPaperButton({ kind, proposalId, structure, requestId, section, label, primary = false, testId, small = false, fresh }: {
  kind: PaperKind; proposalId?: string; structure?: string | null; requestId?: string; section?: string; label: string; primary?: boolean;
  testId: string; small?: boolean; fresh?: boolean;
}) {
  const { open, busy, error } = useOpenPaper();
  const B = primary ? PrimaryButton : SecondaryButton;
  return (
    <span className="inline-flex flex-col">
      <B onClick={() => void open(kind, { proposalId, structure, requestId, section, fresh })} disabled={busy} data-testid={testId}
         className={small ? "h-7 px-2 text-[11.5px]" : undefined} title={kind === "proposal" ? "Opens the proposal workspace: the document with Noor beside it" : undefined}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} {busy ? "Opening the document…" : label}</B>
      {error ? <span role="alert" className="mt-1 text-[11px] text-negative" data-testid={`${testId}-error`}>{error}</span> : null}
    </span>
  );
}

function when(t: number): string {
  return new Date(t * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function usePaperRows(limit = 6, q: { proposalId?: string; mine?: boolean } = {}) {
  const [rows, setRows] = React.useState<PwWorkspace[] | null>(null);
  const key = `${limit}|${q.proposalId ?? ""}|${q.mine ? 1 : 0}`;
  React.useEffect(() => {
    let live = true;
    getJson<{ workspaces: PwWorkspace[] }>(pwUrls.list({ limit, proposal_id: q.proposalId, mine: q.mine }))
      .then((r) => { if (live) setRows(r.workspaces); }, () => { if (live) setRows([]); });
    return () => { live = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return rows;
}

/** One line per workspace: "Credit proposal · Customer · v3 · final v2 · 24 Oct 10:12". */
export function paperRowTitle(w: PwWorkspace): string {
  return `${w.kind_label} · ${w.customer || w.proposal_id} · v${w.current_version}${w.final_version ? ` · final v${w.final_version}` : ""}`;
}

export function DealPapers({ proposalId }: { proposalId: string }) {
  const rows = usePaperRows(50, { proposalId });
  return (
    <div className="space-y-3 p-1" data-testid="pw-deal-papers">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[14px] font-semibold text-text-primary">Papers · {proposalId}</h3>
        <span className="text-[12px] text-text-muted">the living documents of this deal: reopen one to carry on with Noor</span>
        <div className="ml-auto"><OpenPaperButton kind="proposal" proposalId={proposalId} label="Prepare the credit proposal" primary testId="pw-deal-papers-new" /></div>
      </div>
      {rows === null ? <p className="text-[12px] text-text-muted">Loading…</p> : rows.length ? (
        <ul className="divide-y divide-border rounded-md border border-border bg-surface">
          {rows.map((w) => (
            <li key={w.ws_id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-[12px]" data-testid="pw-deal-paper">
              <Link href={pwHref(w.ws_id)} className="font-medium text-accent hover:underline">{paperRowTitle(w)}</Link>
              <span className="text-text-muted">{w.owner_name} · {when(w.updated)}</span>
              {w.status === "final" ? <Chip tone="positive">committee copy v{w.final_version}</Chip> : <Chip>draft</Chip>}
              <Link href={pwHref(w.ws_id, "provenance")} className="ml-auto inline-flex items-center gap-1 text-[11px] text-accent hover:underline"><ListTree size={12} /> Provenance</Link>
            </li>))}
        </ul>) : <p className="text-[12px] text-text-muted" data-testid="pw-deal-papers-empty">No paper written for this deal yet.</p>}
    </div>
  );
}

export function PaperTraceList() {
  const rows = usePaperRows(12);
  if (!rows?.length) return null;
  return (
    <section data-testid="pw-trace-list">
      <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Papers: provenance for committee and audit</h2>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {rows.map((w) => (
          <li key={w.ws_id}>
            <Link href={pwHref(w.ws_id, "provenance")} className={cn("flex items-center gap-3 px-5 py-3 text-sm hover:bg-surface-hover")}>
              <ListTree className="size-4 shrink-0 text-text-muted" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-medium text-text-primary">{paperRowTitle(w)}</span>
              <span className="text-xs text-text-muted">{when(w.updated)}</span>
            </Link>
          </li>))}
      </ul>
    </section>
  );
}
