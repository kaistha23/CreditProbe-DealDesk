"use client";

/**
 * "Save as analysis" and "Save as investigation", for any screen: a small dialog that names the item, saves it to the
 * Workspace and links to it. The caller supplies what to save (`save(title)`), built when the user confirms.
 */

import Link from "next/link";
import * as React from "react";
import { BarChart3, FolderSearch, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/v5/workspace/parts";
import { friendlyMessage } from "@/lib/v5/errors";

export function SaveDialog({ kind, defaultTitle, save, onClose }: {
  kind: "analysis" | "investigation"; defaultTitle: string; save: (title: string) => Promise<{ id: string }>;
  onClose: () => void;
}) {
  const [title, setTitle] = React.useState(defaultTitle.slice(0, 200));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<string | null>(null);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      setDone((await save(title.trim())).id);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const noun = kind === "analysis" ? "analysis" : "investigation";
  const href = done ? `/${kind === "analysis" ? "analyses" : "investigations"}/${encodeURIComponent(done)}` : "";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-label={`Save as ${noun}`} data-testid="ws-save-dialog" data-kind={kind}
           className="w-full max-w-[480px] space-y-3 rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Save as {noun}</h2>
            <p className="text-xs text-text-muted">
              {kind === "analysis"
                ? "Keeps the question with its answer, so it can be reopened and refreshed against any period."
                : "Keeps the whole conversation, its charts and tables, so it can be reopened and continued."}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="ws-save-close"
                  className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        {done ? (
          <div className="space-y-3" data-testid="ws-save-done">
            <p className="text-sm text-positive">Saved as {noun} “{title}”.</p>
            <div className="flex gap-2">
              <Button asChild size="sm" variant="outline"><Link href={href} data-testid="ws-save-open">Open the {noun}</Link></Button>
              <Button size="sm" onClick={onClose} data-testid="ws-save-finish">Done</Button>
            </div>
          </div>
        ) : (
          <>
            <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title" data-testid="ws-save-title" className={inputClass} />
            {error ? <p role="alert" className="text-sm text-negative" data-testid="ws-save-error">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onClose} data-testid="ws-save-cancel">Cancel</Button>
              <Button size="sm" onClick={() => void go()} disabled={busy || !title.trim()} data-testid="ws-save-confirm">
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} Save
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function SaveButton({ kind, defaultTitle, save, testId, disabled, size = "sm", className }: {
  kind: "analysis" | "investigation"; defaultTitle: string; save: (title: string) => Promise<{ id: string }>;
  testId: string; disabled?: boolean; size?: "sm" | "default"; className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const Icon = kind === "analysis" ? BarChart3 : FolderSearch;
  return (
    <>
      <Button variant="outline" size={size} onClick={() => setOpen(true)} disabled={disabled} data-testid={testId} className={className}>
        <Icon aria-hidden /> Save as {kind}
      </Button>
      {open ? <SaveDialog kind={kind} defaultTitle={defaultTitle} save={save} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
