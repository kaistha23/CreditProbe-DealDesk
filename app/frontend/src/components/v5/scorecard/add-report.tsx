"use client";

/**
 * Add a validation to a Playbook report (docs/v5/PLAYBOOK_API.md). The service builds the section (verdicts,
 * tables, charts) and attaches the Word report; this dialog only chooses where it goes. The test IDs are the
 * ones the contract names for the Playbook dialog.
 */

import Link from "next/link";
import * as React from "react";
import { FilePlus2, X } from "lucide-react";

import { type PlaybookReport, scorecard } from "@/lib/v5/scorecard";

import { InfoTip } from "./validation-view";
import { friendlyMessage } from "@/lib/v5/errors";

export function AddToReport({ validationId, defaultTitle, book, disabled }: { validationId: string; defaultTitle: string; book: string; disabled?: boolean }) {
  const [open, setOpen] = React.useState(false);
  const [reports, setReports] = React.useState<PlaybookReport[] | null>(null);
  const [error, setError] = React.useState("");
  const [choice, setChoice] = React.useState<string>("new");
  const [title, setTitle] = React.useState(defaultTitle);
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState<{ title: string; href: string } | null>(null);

  React.useEffect(() => {
    if (!open) return;
    let live = true;
    scorecard.playbookReports().then((r) => { if (live) { setReports(r.reports); if (r.reports.length) setChoice(r.reports[0].id); } })
      .catch((e: unknown) => { if (live) { setReports([]); setError(friendlyMessage(e)); } });
    return () => { live = false; };
  }, [open]);

  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      const out = await scorecard.toPlaybook(validationId, choice === "new" ? { new_report: { title, template: "validation-report", book } } : { report_id: choice });
      setDone({ title: out.report_title, href: out.href });
    } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <button type="button" disabled={disabled} onClick={() => { setDone(null); setError(""); setReports(null); setOpen(true); }} data-testid="scorecard-add-report"
              className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover disabled:opacity-40">
        <FilePlus2 size={13} /> Add to report</button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Add to report" data-testid="add-report-dialog">
          <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-surface p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-[14px] font-semibold text-text-primary">Add to a report
                <InfoTip align="left" text="The results, charts and verdicts go into the report as a section, with the Word validation report attached." /></h2>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close" data-testid="add-report-close"><X size={16} /></button>
            </div>
            {done ? (
              <div className="space-y-2" data-testid="add-report-done">
                <p className="text-[13px] text-positive">Added to {done.title}.</p>
                <Link href={done.href} data-testid="add-report-open" className="text-[12px] text-accent underline">Open the report</Link>
              </div>) : (
              <>
                {error ? <p className="text-[12px] text-negative" role="alert" data-testid="add-report-error">{error}</p> : null}
                {!reports && !error ? <p className="text-[12px] text-text-muted">Loading the reports you can edit…</p> : null}
                <div className="max-h-48 space-y-1 overflow-auto">
                  {(reports ?? []).map((r) => (
                    <label key={r.id} className="flex items-start gap-2 text-[12px]">
                      <input type="radio" name="report" checked={choice === r.id} onChange={() => setChoice(r.id)} data-testid="add-report-existing" data-id={r.id} />
                      <span><span className="text-text-primary">{r.title}</span> <span className="text-text-muted">· {r.status.replace("_", " ")}</span></span>
                    </label>))}
                  <label className="flex items-center gap-2 text-[12px]">
                    <input type="radio" name="report" checked={choice === "new"} onChange={() => setChoice("new")} data-testid="add-report-new" /> A new validation report</label>
                </div>
                {choice === "new" ? (
                  <input value={title} onChange={(e) => setTitle(e.target.value)} data-testid="add-report-title" aria-label="Title of the new report"
                         className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]" />) : null}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setOpen(false)} className="rounded-md border border-border px-3 py-1 text-[12px]">Cancel</button>
                  <button type="button" onClick={confirm} disabled={busy || (choice === "new" && !title.trim())} data-testid="add-report-confirm"
                          className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40">{busy ? "Adding…" : "Add"}</button>
                </div>
              </>)}
          </div>
        </div>) : null}
    </>
  );
}
