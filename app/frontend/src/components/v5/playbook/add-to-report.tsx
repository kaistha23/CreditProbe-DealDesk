"use client";

/**
 * "Add to report": the one dialog every Add-to-report button in CreditProbe opens (PLAYBOOK_API.md 7).
 * It pushes one section (text, key figures, tables, charts, verdicts) into a report the reader can edit,
 * or into a new report started from a template, through `POST /api/v1/playbook/imports`.
 *
 * The section is built only when the reader confirms (`build`), so a button costs nothing until used.
 * One Idempotency-Key per opened dialog: a retry after a network error never adds the section twice.
 */

import Link from "next/link";
import * as React from "react";
import { FilePlus2, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { cn } from "@/lib/utils";
import {
  type Block, type ImportResult, type PlaybookSource, type ReportRow, type Template, STATUS_LABEL, TEMPLATE_FALLBACK, playbook,
} from "@/lib/v5/playbook";
import { day, useWs } from "@/lib/v5/workspace";
import { friendlyMessage } from "@/lib/v5/errors";

/** What `build` returns: the section of PLAYBOOK_API.md 3.1, plus an optional original file. */
export interface BuiltSection {
  title: string;
  blocks: Block[];
  position?: string;
  attachment?: { name: string; content_type: string; file_base64: string } | null;
  /** The resolved provenance, when building the section learned a better label than the button had. */
  source?: PlaybookSource;
}

export interface AddToReportProps {
  source: PlaybookSource;
  build: () => Promise<BuiltSection> | BuiltSection;
  defaultTemplate?: string;
  defaultTitle?: string;
  onDone?: (result: ImportResult) => void;
}

const NEW = "__new";

export function AddToReportDialog({ source, build, defaultTemplate = "credit-committee-pack", defaultTitle, onDone, onClose }:
  AddToReportProps & { onClose: () => void }) {
  const { viewingAs } = useCoreAuth();
  const reports = useWs(() => playbook.reports({ status: ["draft", "in_review"], editable: true }), "add-report|reports");
  const templates = useWs(() => playbook.templates(), "add-report|templates");
  const templateList: Template[] = templates.data?.templates?.length ? templates.data.templates : TEMPLATE_FALLBACK;
  const rows: ReportRow[] = reports.data?.reports ?? [];

  const [choice, setChoice] = React.useState<string>("");
  const [title, setTitle] = React.useState(defaultTitle ?? source.label ?? "");
  const [template, setTemplate] = React.useState(defaultTemplate);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<ImportResult | null>(null);
  const keyRef = React.useRef<string | null>(null);
  const isNew = choice === "" || choice === NEW;
  const templateKnown = templateList.some((t) => t.id === template);

  React.useEffect(() => {
    // Capture phase and stopped: an Escape that closes this dialog must not also close the drawer under it.
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  async function confirm() {
    if (busy || viewingAs) return;
    setBusy(true);
    setError(null);
    if (!keyRef.current) {
      const rand = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      keyRef.current = `add-report-${rand}`;
    }
    try {
      const section = await build();
      const result = await playbook.importSection({
        report_id: isNew ? null : choice,
        new_report: isNew ? { title: title.trim(), template } : null,
        source: section.source ?? source,
        section: { title: section.title, blocks: section.blocks, position: section.position ?? "end" },
        attachment: section.attachment ?? null,
      }, keyRef.current);
      setDone(result);
      onDone?.(result);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Add to report" data-testid="add-report-dialog"
           className="w-full max-w-[520px] rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-text-primary">Add to report</h2>
            <p className="mt-0.5 truncate text-xs text-text-muted" title={source.label}>{source.label}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="add-report-close"
                  className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        <p className="mt-2 text-xs text-text-secondary">
          The text, figures, tables and charts are added as one section, with a link back to where they came from.
        </p>

        {done ? (
          <div className="mt-4 space-y-3" data-testid="add-report-done">
            <p className="text-sm text-positive">
              Added to <span className="font-semibold">{done.report_title}</span>
              {done.created_report ? " (a new report, in Draft)" : ""}.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline" size="sm">
                <Link href={done.href} data-testid="add-report-open">Open the report</Link>
              </Button>
              <Button size="sm" onClick={onClose} data-testid="add-report-finish">Done</Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            {viewingAs ? (
              <p role="alert" className="text-sm text-warning">You are viewing as {viewingAs.name}. Stop viewing as to add to a report.</p>
            ) : null}
            <fieldset className="max-h-56 space-y-0.5 overflow-y-auto rounded-md border border-border p-2">
              <legend className="px-1 text-[11px] text-text-muted">Which report</legend>
              {reports.loading ? (
                <p className="flex items-center gap-2 px-2 py-1.5 text-xs text-text-muted"><Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading your reports…</p>
              ) : reports.error ? (
                <p className="px-2 py-1.5 text-xs text-negative" role="alert">{reports.error}</p>
              ) : rows.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-text-muted">No report you can add to yet. Start a new one.</p>
              ) : rows.map((r) => (
                <label key={r.id} className={cn("flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover",
                                                choice === r.id && "bg-accent-muted")}>
                  <input type="radio" name="add-report-target" className="mt-1" checked={choice === r.id} onChange={() => setChoice(r.id)}
                         data-testid="add-report-existing" data-id={r.id} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-text-primary">{r.title}</span>
                    <span className="block truncate text-[11px] text-text-muted">
                      {r.template_name || r.template} · {STATUS_LABEL[r.status] ?? r.status}
                      {r.due_date ? ` · due ${day(r.due_date)}` : ""} · {r.section_count} sections
                    </span>
                  </span>
                </label>
              ))}
              <label className={cn("flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover", isNew && "bg-accent-muted")}>
                <input type="radio" name="add-report-target" checked={isNew} onChange={() => setChoice(NEW)} data-testid="add-report-new" />
                <span className="font-medium text-text-primary">A new report</span>
              </label>
            </fieldset>
            {isNew ? (
              <div className="grid gap-2 sm:grid-cols-[3fr_2fr]">
                <label className="block">
                  <span className="mb-1 block text-[11px] font-medium text-text-secondary">Title</span>
                  <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label="Title of the new report"
                         data-testid="add-report-title" placeholder="Title"
                         className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[11px] font-medium text-text-secondary">Template</span>
                  <select value={template} onChange={(e) => setTemplate(e.target.value)} aria-label="Template of the new report"
                          data-testid="add-report-template"
                          className="w-full rounded-md border border-border bg-surface px-2 py-2 text-sm text-text-primary focus:border-accent focus:outline-none">
                    {!templateKnown ? <option value={template}>{template}</option> : null}
                    {templateList.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </label>
              </div>
            ) : null}
            {error ? <p role="alert" className="text-sm text-negative" data-testid="add-report-error">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onClose} data-testid="add-report-cancel">Cancel</Button>
              <Button size="sm" onClick={() => void confirm()} data-testid="add-report-confirm"
                      disabled={busy || !!viewingAs || (isNew && !title.trim())}>
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : <FilePlus2 aria-hidden />} Add to report
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** The Add-to-report button: opens the shared dialog. */
export function AddToReportButton({ source, build, defaultTemplate, defaultTitle, testId = "add-report-button", label = "Add to report",
                                    size = "sm", variant = "outline", disabled, onDone, className }: AddToReportProps & {
  testId?: string; label?: string; size?: "sm" | "default"; variant?: "outline" | "ghost" | "default" | "subtle";
  disabled?: boolean; className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const close = React.useCallback(() => setOpen(false), []);
  return (
    <>
      <Button variant={variant} size={size} onClick={() => setOpen(true)} disabled={disabled} data-testid={testId} className={className}>
        <FilePlus2 aria-hidden /> {label}
      </Button>
      {open ? (
        <AddToReportDialog source={source} build={build} defaultTemplate={defaultTemplate} defaultTitle={defaultTitle}
                           onDone={onDone} onClose={close} />
      ) : null}
    </>
  );
}
