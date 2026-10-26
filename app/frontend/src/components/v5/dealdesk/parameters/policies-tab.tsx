"use client";

/**
 * PLAN_R12 Session G (I3): the policy library. Every uploaded policy with its version, effective date, uploader and
 * status (awaiting approval, active, superseded, rejected); each opens in a viewer (its numbered clauses by section and
 * its tables) and downloads as Word (.docx). A PDF, Markdown or text upload is rebuilt as Word for the download, and the
 * original file is kept and downloadable too.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type PolicyRecord, type PolicyView, download, policiesApi, shortDate, statusTone, statusWord,
} from "@/lib/v5/dealdesk-params";

import { Chip, Empty, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";

export function PolicyViewer({ rec, onClose }: { rec: PolicyRecord; onClose: () => void }) {
  const [v, setV] = React.useState<PolicyView | null>(null);
  const [err, setErr] = React.useState("");
  React.useEffect(() => {
    let live = true;
    policiesApi.view(rec.policy_id, rec.version).then((x) => { if (live) setV(x); }, (e: unknown) => { if (live) setErr(e instanceof Error ? e.message : String(e)); });
    return () => { live = false; };
  }, [rec.policy_id, rec.version]);
  return (
    <Section title={`${rec.title} v${rec.version}`} testId="policy-viewer"
             action={<SecondaryButton onClick={onClose} data-testid="policy-viewer-close">Close</SecondaryButton>}
             info="The policy as read from the uploaded file: its numbered clauses by section and its tables. The Word download holds the same text; the original is kept as uploaded.">
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      {!v && !err ? <Skeleton className="h-64 w-full" /> : null}
      {v ? (
        <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-2">
          {v.sections.map((s) => (
            <div key={`${s.section}-${s.title}`}>
              <h3 className="text-[13px] font-semibold text-text-primary">{s.section ? `${s.section}. ` : ""}{s.title}</h3>
              <ol className="mt-1 space-y-1.5">
                {s.clauses.map((c) => (
                  <li key={c.clause} className="grid grid-cols-[3.25rem_1fr] gap-2 text-[12px] leading-5 text-text-secondary" data-testid="policy-clause">
                    <span className="font-semibold tabular-nums text-text-primary">{c.clause}</span><span>{c.text}</span></li>))}
              </ol>
            </div>))}
          {v.tables.map((t) => (
            <div key={t.table}>
              <h3 className="text-[13px] font-semibold text-text-primary">{t.caption || t.table}</h3>
              <div className="overflow-x-auto"><table className={tableCls}>
                <thead><tr>{t.header.map((h, i) => <th key={`${h}-${i}`} className={thCls}>{h}</th>)}</tr></thead>
                <tbody>{t.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={cn(tdCls, "whitespace-normal")}>{c}</td>)}</tr>)}</tbody>
              </table></div>
            </div>))}
        </div>) : null}
    </Section>
  );
}

export function PoliciesTab({ policies, onReview, onError }: {
  policies: PolicyRecord[] | null; onReview: (r: PolicyRecord) => void; onError: (m: string) => void;
}) {
  const [open, setOpen] = React.useState<PolicyRecord | null>(null);
  const get = (url: string, name: string) => { download(url, name).catch((e: unknown) => onError(e instanceof Error ? e.message : String(e))); };
  if (!policies) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="space-y-4" data-testid="policies-tab">
      <Section title="Policy library" testId="policy-library"
               info="Every policy uploaded on this page, newest first. Approving a policy makes it active and the earlier version of the same policy superseded; a rejected upload stays in the library with who rejected it and why.">
        {!policies.length ? <Empty>No policy uploaded yet. Use Upload policy above, or the sample policy, to start.</Empty> : (
          <div className="overflow-x-auto">
            <table className={tableCls} data-testid="policy-library-table">
              <thead><tr>{["Policy", "Version", "Effective", "Uploaded by", "Uploaded", "Status", "Parameters", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{policies.map((p) => (
                <tr key={`${p.policy_id}-${p.version}`} data-testid="policy-library-row" data-status={p.status}>
                  <td className={cn(tdCls, "whitespace-normal font-medium")}>{p.title}
                    <span className="block text-[11px] font-normal text-text-muted">{p.issuer ? `${p.issuer} · ` : ""}{p.original_name}</span></td>
                  <td className={tdCls}>v{p.version}{p.document_version ? <span className="block text-[11px] text-text-muted">doc. {p.document_version}</span> : null}</td>
                  <td className={tdCls}>{shortDate(p.effective_date)}</td>
                  <td className={tdCls}>{p.uploaded_by || "–"}</td>
                  <td className={tdCls}>{shortDate(p.uploaded_at)}</td>
                  <td className={tdCls}><Chip tone={statusTone(p.status)} testId="policy-status">{statusWord(p.status)}</Chip></td>
                  <td className={cn(tdCls, "text-text-secondary")}>{p.external ? <span title="Held in Data Domains (dd_policy); not uploaded on this page, so there is no review.">From Data Domains</span>
                    : `${p.summary.found} found · ${p.summary.changes} change${p.summary.changes === 1 ? "" : "s"}`}</td>
                  <td className={tdCls}>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <SecondaryButton onClick={() => setOpen(p)} data-testid="policy-view">View</SecondaryButton>
                      {!p.external ? <SecondaryButton onClick={() => onReview(p)} data-testid="policy-open-review">{p.status === "pending" ? "Review" : "Decisions"}</SecondaryButton> : null}
                      <SecondaryButton onClick={() => get(policiesApi.docxUrl(p.policy_id, p.version), `${p.title}.docx`)} data-testid="policy-docx">Word</SecondaryButton>
                      {p.format !== "docx" ? <SecondaryButton onClick={() => get(policiesApi.originalUrl(p.policy_id, p.version), p.original_name)}
                                                              data-testid="policy-original">Original ({p.format.toUpperCase()})</SecondaryButton> : null}
                    </div></td>
                </tr>))}</tbody>
            </table>
          </div>)}
      </Section>
      {open ? <PolicyViewer rec={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
