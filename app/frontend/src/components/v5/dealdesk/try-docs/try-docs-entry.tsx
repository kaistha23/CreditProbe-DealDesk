"use client";

/**
 * PLAN_R12 Session T (I18): the one entry point to "Try it on your documents", for U's Deal Desk landing page and for
 * Noor (N1). It opens the live run in a panel over the page; closing the panel wipes the demo session.
 *
 *   <TryDocsEntry />                       a landing card
 *   <TryDocsEntry variant="button" />      a button (Noor's suggestions, toolbars)
 *   <TryDocsEntry open onOpenChange={…} /> controlled (Noor opens it from a chip)
 */

import * as React from "react";
import { FileSearch } from "lucide-react";

import { cn } from "@/lib/utils";

import { PrimaryButton, SecondaryButton } from "../kit";
import { TryDocsRun } from "./try-docs-run";

export function TryDocsEntry({ variant = "card", label = "Try it on your documents", open: openProp, onOpenChange, className, testId = "try-docs-entry" }: {
  variant?: "card" | "button" | "secondary"; label?: string; open?: boolean; onOpenChange?: (open: boolean) => void; className?: string; testId?: string;
}) {
  const [own, setOwn] = React.useState(false);
  const open = openProp ?? own;
  const setOpen = React.useCallback((v: boolean) => { setOwn(v); onOpenChange?.(v); }, [onOpenChange]);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const trigger = variant === "card" ? (
    <button type="button" onClick={() => setOpen(true)} data-testid={testId}
            className={cn("flex w-full min-w-0 items-start gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 text-left hover:bg-surface-hover", className)}>
      <FileSearch size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold text-text-primary">{label}</span>
        <span className="block truncate text-[12px] text-text-secondary">Reviewed live, wiped when you leave</span>
      </span>
    </button>
  ) : variant === "button" ? (
    <PrimaryButton onClick={() => setOpen(true)} data-testid={testId} className={className}><FileSearch size={14} aria-hidden /> {label}</PrimaryButton>
  ) : (
    <SecondaryButton onClick={() => setOpen(true)} data-testid={testId} className={className}><FileSearch size={14} aria-hidden /> {label}</SecondaryButton>
  );

  return (
    <>
      {trigger}
      {open ? (
        <div role="dialog" aria-modal="true" aria-label={label} data-testid="try-docs-dialog"
             className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4">
          <div className="h-[calc(100vh-2rem)] w-full max-w-[1180px] overflow-y-auto rounded-xl bg-surface-sunken p-3 shadow-xl">
            <TryDocsRun onExit={() => setOpen(false)} />
          </div>
        </div>
      ) : null}
    </>
  );
}

export { TryDocsRun };
