"use client";

import * as React from "react";
import { ArrowLeft } from "lucide-react";

import { useSearchParams } from "next/navigation";

import { readFrom } from "@/components/v5/ui/back-link-model";
import { cn } from "@/lib/utils";
import { useBack } from "@/lib/v5/back";

/**
 * R7: the v5 Back button. Goes to the exact previous screen and step of this tab; with none (a new tab, a pasted
 * link), to the link's `returnTo`, else to `fallback`. The href is the fallback, so a middle-click still works.
 */
export function BackButton({ fallback, label, testId, className, onBefore }: {
  fallback: { href: string; label: string };
  /** Text on the button; "Back" by default (it may return to another module than the fallback). */
  label?: string;
  testId: string;
  className?: string;
  /** Runs before navigating (for example, to reset a thread). */
  onBefore?: () => void;
}) {
  const b = useBack(fallback);
  // R14 U (K1): one way back. When the page was reached from Noor, a drawer or a list (from=<origin>), the shell's
  // "← Back to <origin>" is the way back, so this generic Back steps aside (the pipeline banner keeps its own).
  const params = useSearchParams();
  if (readFrom(params) && params.get("from") !== "pipeline") return null;
  return (
    <a href={b.href} data-testid={testId} title={`Back (with no earlier page in this tab: ${b.label})`}
       onClick={(e) => { onBefore?.(); b.go(e); }}
       className={cn("inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-[12px] text-text-secondary hover:bg-surface-hover", className)}>
      <ArrowLeft size={14} aria-hidden /> {label ?? "Back"}
    </a>
  );
}
