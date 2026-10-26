"use client";

/**
 * Round K: "Rules applied" on a document (credit request, credit proposal, house-style draft): every rule in force for
 * the writer (theirs, their team's, the bank's), what it did to this document, and who made it when. Collapsed to one line.
 */

import Link from "next/link";
import * as React from "react";
import { ChevronDown, ChevronRight, ListChecks } from "lucide-react";

import { cn } from "@/lib/utils";
import { APPLIED_LABEL, type AppliedStatus, type RuleApplied, appliedLine } from "@/lib/v5/dealdesk-rules";

const TONE: Record<AppliedStatus, string> = {
  applied: "bg-positive-muted text-positive", in_place: "bg-surface-sunken text-text-secondary", flagged: "bg-warning-muted text-warning",
  model: "bg-accent-muted text-accent", noted: "bg-surface-sunken text-text-muted", not_applicable: "bg-surface-sunken text-text-muted",
};

export function RulesApplied({ applied, defaultOpen = false, testId = "rules-applied", className }: {
  applied: RuleApplied[] | undefined | null; defaultOpen?: boolean; testId?: string; className?: string;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  if (!applied || applied.length === 0) return null;
  const order: AppliedStatus[] = ["applied", "flagged", "model", "noted", "in_place", "not_applicable"];
  const rows = [...applied].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  return (
    <section className={cn("rounded-lg border border-border bg-surface", className)} data-testid={testId}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid={`${testId}-toggle`}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px]">
        {open ? <ChevronDown className="size-3.5 text-text-muted" aria-hidden /> : <ChevronRight className="size-3.5 text-text-muted" aria-hidden />}
        <ListChecks className="size-4 text-accent" aria-hidden />
        <span className="font-semibold text-text-primary">Rules applied</span>
        <span className="text-text-secondary" data-testid={`${testId}-line`}>{appliedLine(applied)}</span>
      </button>
      {open ? (
        <ul className="divide-y divide-border border-t border-border">
          {rows.map((a) => (
            <li key={a.rule_id} className="grid gap-x-3 gap-y-0.5 px-3 py-2 text-[12px] md:grid-cols-[120px_minmax(0,1.4fr)_minmax(0,1.6fr)]"
                data-testid={`${testId}-row`} data-rule={a.rule_id} data-status={a.status}>
              <span><span className={cn("rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]", TONE[a.status])}>{APPLIED_LABEL[a.status]}</span></span>
              <span className="min-w-0">
                <span className="block text-text-primary">{a.text}</span>
                <span className="block text-[11px] text-text-muted">{a.scope_label} · {a.author_name}{a.created_at ? `, ${a.created_at.slice(0, 10)}` : ""} · {a.rule_id}</span>
              </span>
              <span className="text-text-secondary">{a.effect}</span>
            </li>
          ))}
          <li className="px-3 py-1.5 text-[11px] text-text-muted">
            Change your rules in <Link href="/deal-desk/rules" className="text-accent hover:underline">My rules</Link>; the bank&apos;s in{" "}
            <Link href="/policy-docs?view=rules" className="text-accent hover:underline">Policy Docs → Global rules</Link>.
          </li>
        </ul>
      ) : null}
    </section>
  );
}
