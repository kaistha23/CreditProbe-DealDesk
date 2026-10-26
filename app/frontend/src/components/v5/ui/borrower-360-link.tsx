"use client";

/**
 * R14 U (K11): "Borrower 360 →" on every borrower card and row, and the borrower's name as a link.
 *
 *   <Borrower360Button customerId="CB00020" period="Q2 2026" from="ews" />     top-right of a card, beside the sector
 *   <BorrowerNameLink customerId="CB00020" name="Al Fanar Hospitality" from="who-to-call" />
 *
 * Both open Borrower 360 on that borrower and quarter (lib/borrower-link.ts: the one place that knows the URL) and
 * carry `from=<origin>` plus this exact screen as `back`, so Borrower 360 shows "← Back to Early Warning" and returns
 * to the same filtered list (K1). Clicks never bubble to the card (a card click still opens its own drill-down).
 * Only corporate borrowers (CB ids) have a Borrower 360 page: for any other id the controls render nothing / plain text.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

import { useFromHere } from "./back-link";
import { b360Href, hasBorrower360 } from "./borrower-360-model";

export { b360Href, hasBorrower360 } from "./borrower-360-model";

export function useBorrower360Href(customerId: string, period: string | null | undefined, from: string): string {
  const link = useFromHere(from);
  return link(b360Href(customerId, period));
}

export function Borrower360Button({ customerId, period, from, className, label = "Borrower 360", testId }: {
  customerId: string; period?: string | null; from: string; className?: string; label?: string; testId?: string;
}) {
  const href = useBorrower360Href(customerId, period, from);
  if (!hasBorrower360(customerId)) return null;
  return (
    <Link href={href} onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}
          data-testid={testId ?? `b360-button-${customerId}`} data-b360-button="1" title={`Open ${customerId} in Borrower 360`}
          className={cn("inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-border bg-surface px-2 text-[11.5px] font-medium text-accent transition-colors hover:border-accent hover:bg-accent-muted", className)}>
      {label} <ArrowRight className="size-3" aria-hidden />
    </Link>
  );
}

export function BorrowerNameLink({ customerId, name, period, from, className, testId }: {
  customerId: string; name?: string | null; period?: string | null; from: string; className?: string; testId?: string;
}) {
  const href = useBorrower360Href(customerId, period, from);
  const text = name || customerId;
  if (!hasBorrower360(customerId)) return <span className={className}>{text}</span>;
  return (
    <Link href={href} onClick={(e) => e.stopPropagation()} data-testid={testId ?? `b360-name-${customerId}`}
          className={cn("text-text-primary underline-offset-2 hover:text-accent hover:underline", className)}>{text}</Link>
  );
}
