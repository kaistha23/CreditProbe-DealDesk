"use client";

/**
 * R14 session p (K33, D2): "Check all pending proposals" — the proposal check on every pending deal (deterministic rules +
 * bank data), ranked by critical defects and score, with filters (RM, branch, sector, score), the RM view (average score,
 * recurring defects: feeds the RM track record), "Send all queries" per RM and the Excel export. Results are published to
 * Data Domains (dd_proposal_quality).
 *
 *   <BatchCheckButton />    // on the Deal Desk landing and the Pipeline tab; data-testid="dealdesk-batch-check"
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { ClipboardCheck, Download, Loader2, Send } from "lucide-react";

import { cn } from "@/lib/utils";
import { PlainWords } from "@/components/v5/ui/plain-words";

import { Chip, PrimaryButton, SecondaryButton, tableCls, tdCls, thCls } from "../kit";
import { errorText, fileHref, getJson } from "../papers/paper-view";
import { ProposalDialog } from "./credit-proposal";
import { type BatchResult, CHECK_API, filterBatch, scoreTone } from "./model";

export function BatchCheckButton({ label = "Check all pending proposals" }: { label?: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <SecondaryButton onClick={() => setOpen(true)} data-testid="dealdesk-batch-check" data-tour="batch-check"><ClipboardCheck size={13} /> {label}</SecondaryButton>
      {open ? <ProposalDialog onClose={() => setOpen(false)} testId="dealdesk-batch-check-dialog" label="Proposal check, all pending"><BatchCheckPanel /></ProposalDialog> : null}
    </>
  );
}

export function BatchCheckPanel() {
  const router = useRouter();
  const [b, setB] = React.useState<BatchResult | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(true);
  const [f, setF] = React.useState<{ rm: string; branch: string; sector: string; maxScore: number | null; criticalOnly: boolean }>({ rm: "", branch: "", sector: "", maxScore: null, criticalOnly: false });
  const [view, setView] = React.useState<"deals" | "rm">("deals");
  const [msg, setMsg] = React.useState("");

  React.useEffect(() => {
    let live = true;
    getJson<BatchResult>(CHECK_API.batch, { method: "POST" }).then((x) => { if (live) setB(x); }, (e: unknown) => { if (live) setError(errorText(e)); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, []);

  const rows = b ? filterBatch(b.table, { ...f, rm: f.rm || undefined, branch: f.branch || undefined, sector: f.sector || undefined }) : [];
  const sendAll = (rm: string) => {
    getJson<{ message: string }>(CHECK_API.sendAll(rm), { method: "POST" }).then((x) => setMsg(x.message), (e: unknown) => setError(errorText(e)));
  };
  const s = b?.summary;
  return (
    <div className="flex h-full flex-col" data-testid="dealdesk-batch-check-panel">
      <div className="space-y-2 border-b border-border bg-surface px-5 py-3 pr-12">
        <div className="flex flex-wrap items-center gap-2">
          <ClipboardCheck size={16} className="text-accent" aria-hidden />
          <h2 className="text-[16px] font-semibold text-text-primary">Proposal check · all pending proposals</h2>
          {s ? <span className="text-[12px] text-text-muted">{s.checked} checked in {s.elapsed_s.toFixed(1)} s · published to dd_proposal_quality</span> : null}
          <div className="ml-auto flex gap-2">
            {b ? <a href={fileHref(CHECK_API.batchXlsx)} data-testid="dealdesk-batch-check-xlsx"><SecondaryButton className="h-9"><Download size={13} /> Excel</SecondaryButton></a> : null}
          </div>
        </div>
        {s ? <PlainWords speak testId="dealdesk-batch-check-plain" lines={[
          `This grades the RMs' papers on all ${s.checked} pending proposals against the bank's data, ranked worst first.`,
          `${s.with_critical} proposals carry critical defects (${s.critical} in all); the average score is ${s.average_score ?? 0} of 100.`,
          `${s.queries_open} queries are open; send them per RM before the deal reviews.`]} /> : null}
        {b ? (
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <div className="inline-flex rounded-md border border-border p-0.5" role="tablist">
              {(["deals", "rm"] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)} data-testid={`dealdesk-batch-check-view-${k}`}
                        className={cn("h-7 rounded px-3 text-[12px]", view === k ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
                  {k === "deals" ? "Proposals" : "By RM"}</button>))}
            </div>
            {view === "deals" ? (<>
              {(["rm", "branch", "sector"] as const).map((k) => (
                <select key={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-label={k} data-testid={`dealdesk-batch-check-filter-${k}`}
                        className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]">
                  <option value="">{k === "rm" ? "All RMs" : k === "branch" ? "All branches" : "All sectors"}</option>
                  {b.filters[k].filter(Boolean).map((v) => <option key={v} value={v}>{v}</option>)}
                </select>))}
              <select value={f.maxScore ?? ""} onChange={(e) => setF({ ...f, maxScore: e.target.value ? Number(e.target.value) : null })} aria-label="score"
                      data-testid="dealdesk-batch-check-filter-score" className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]">
                <option value="">Any score</option><option value="85">Score ≤ 85</option><option value="70">Score ≤ 70</option><option value="50">Score ≤ 50</option>
              </select>
              <label className="inline-flex items-center gap-1 text-text-secondary"><input type="checkbox" checked={f.criticalOnly} onChange={(e) => setF({ ...f, criticalOnly: e.target.checked })}
                                                                                          data-testid="dealdesk-batch-check-filter-critical" /> Critical only</label>
              <span className="ml-auto text-text-muted">{rows.length} of {b.table.length}</span></>) : null}
          </div>) : null}
        {msg ? <p className="text-[12px] text-positive" data-testid="dealdesk-batch-check-sent">{msg}</p> : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-5 py-3">
        {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
        {busy ? <div className="flex items-center gap-2 py-8 text-[12px] text-text-muted"><Loader2 size={14} className="animate-spin" /> Checking every pending proposal…</div> : null}
        {b && view === "deals" ? (
          <table className={tableCls} data-testid="dealdesk-batch-check-table">
            <thead><tr>{["#", "Proposal", "RM", "Branch", "Score", "Defects", "Critical", "Not disclosed", "Contradicted", "Queries open", "Sections", "Main defect"].map((h) =>
              <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.proposal_id} className="cursor-pointer hover:bg-surface-hover" data-testid="dealdesk-batch-check-row" data-pid={r.proposal_id}
                  onClick={() => router.push(`/deal-desk/${encodeURIComponent(r.proposal_id)}?step=proposal-check`)}>
                <td className={tdCls}>{r.rank}</td>
                <td className={cn(tdCls, "max-w-[250px] truncate")} title={r.headline}><span className="font-medium text-text-primary">{r.customer}</span>
                  <span className="ml-1 text-text-muted">{r.proposal_id}</span></td>
                <td className={tdCls}>{r.rm}</td><td className={cn(tdCls, "max-w-[130px] truncate")} title={r.branch}>{r.branch}</td>
                <td className={tdCls}><Chip tone={scoreTone(r.score)}>{Math.round(r.score)} · {r.grade}</Chip>
                  {r.score_changed && r.previous_score != null ? <span className="ml-1 text-[10px] text-text-muted" title="score changed since the last check">was {Math.round(r.previous_score)}</span> : null}</td>
                <td className={cn(tdCls, "text-right")}>{r.defects}</td>
                <td className={cn(tdCls, "text-right", r.critical ? "font-semibold text-negative" : "")}>{r.critical}</td>
                <td className={cn(tdCls, "text-right")}>{r.undisclosed}</td><td className={cn(tdCls, "text-right")}>{r.contradicted}</td>
                <td className={cn(tdCls, "text-right")}>{r.queries_open}</td><td className={cn(tdCls, "text-right")}>{r.sections_present}/20</td>
                <td className={cn(tdCls, "max-w-[190px] truncate")} title={`${r.top_defect} · status ${r.status.replace(/_/g, " ")}`}>{r.top_defect || "—"}</td>
              </tr>))}</tbody>
          </table>) : null}
        {b && view === "rm" ? (
          <table className={tableCls} data-testid="dealdesk-batch-check-rm">
            <thead><tr>{["RM", "Proposals", "Average score", "Critical", "Queries open", "Recurring defects", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{b.rm.map((r) => (
              <tr key={r.rm} data-testid="dealdesk-batch-check-rm-row">
                <td className={cn(tdCls, "font-medium text-text-primary")}>{r.rm}</td><td className={cn(tdCls, "text-right")}>{r.proposals}</td>
                <td className={tdCls}><Chip tone={scoreTone(r.average_score)}>{r.average_score.toFixed(1)}</Chip></td>
                <td className={cn(tdCls, "text-right", r.critical ? "font-semibold text-negative" : "")}>{r.critical}</td>
                <td className={cn(tdCls, "text-right")}>{r.queries_open}</td>
                <td className={cn(tdCls, "max-w-[360px] truncate")} title={r.recurring.map(([k, v]) => `${k} (${v})`).join("; ")}>{r.recurring.map(([k, v]) => `${k} (${v})`).join(" · ")}</td>
                <td className={tdCls}><PrimaryButton className="h-7 px-2.5 text-[12px]" disabled={!r.queries_open} onClick={() => sendAll(r.rm)}
                                                     data-testid="dealdesk-batch-check-send-all"><Send size={12} /> Send all queries</PrimaryButton></td>
              </tr>))}</tbody>
          </table>) : null}
      </div>
    </div>
  );
}
