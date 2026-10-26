"use client";

import * as React from "react";
import { Info, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The small "i" next to a screen title.
 *
 * CreditProbe used to open every screen with a line of standfirst explaining what the
 * screen was for. Fourteen screens of that is fourteen paragraphs a CRO has read
 * once and then reads past forever — it makes a serious product look like it is
 * still introducing itself.
 *
 * So the explanation moves in here. It is one click away, it is the same
 * explanation, and the screen opens with its title and its content instead.
 */

export function InfoPopover({
  title,
  children,
  className,
  align = "left",
}: {
  /** Heading inside the panel. Defaults to "About this screen". */
  title?: string;
  children: React.ReactNode;
  className?: string;
  /** Which edge the panel lines up with; "right" for an (i) at the right of a card. */
  align?: "left" | "right";
}) {
  const [open, setOpen] = React.useState(false);
  const container = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    // R14 U (K8): spans, not divs. The (i) sits inside a <p> on many screens ("Sent to What-If (i)"), and a <div>
    // inside a <p> is invalid HTML: React raised it as a hydration error (one of the two behind the dev "Issues" badge).
    <span ref={container} className={cn("relative inline-flex", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Hide the explanation" : "What is this screen for?"}
        className={cn(
          "inline-flex size-5 items-center justify-center rounded-full border transition-colors",
          open
            ? "border-accent text-accent"
            : "border-border text-text-muted hover:border-border-strong hover:text-text-secondary",
        )}
      >
        <Info className="size-3" aria-hidden />
      </button>

      {open && (
        <span
          role="dialog"
          aria-label={title ?? "About this screen"}
          className={cn("absolute top-7 z-30 block w-[22rem] max-w-[calc(100vw-3rem)] rounded-lg border border-border bg-surface-raised p-4 shadow-lg", align === "right" ? "right-0" : "left-0")}
        >
          <span className="flex items-start justify-between gap-3">
            <span className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">
              {title ?? "About this screen"}
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="-mr-1 -mt-1 rounded p-1 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary"
              aria-label="Close"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
          <span className="mt-2 block space-y-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-text-secondary">
            {children}
          </span>
        </span>
      )}
    </span>
  );
}
