"use client";

/** R14 r: "Issues on the books" — every regulatory and data issue open now, largest money first; a click opens its
 * issue view. Read from backend/regulatory/issues (list). */

import * as React from "react";
import { ChevronRight, Loader2 } from "lucide-react";

import { Chip } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";

import { issuesApi, type IssueSummary } from "./issues-api";
import { PlainWords } from "@/components/v5/ui/plain-words";

const SEV_TONE: Record<string, "negative" | "warning" | "neutral"> = { critical: "negative", high: "negative", medium: "warning", low: "neutral" };

export function IssuesList({ onOpen }: { onOpen: (id: string) => void }) {
  const [state, set] = React.useState<{ rows: IssueSummary[] | null; error: string }>({ rows: null, error: "" });
  React.useEffect(() => {
    let live = true;
    issuesApi.list().then((d) => live && set({ rows: d.issues, error: "" }))
      .catch((e: unknown) => live && set({ rows: [], error: e instanceof Error ? e.message : "That did not load." }));
    return () => { live = false; };
  }, []);
  if (state.rows === null) {
    return <p className="flex items-center gap-2 py-8 text-[13px] text-text-muted"><Loader2 size={14} className="animate-spin" />Running the checks on the books…</p>;
  }
  if (state.error) return <p role="alert" className="text-[13px] text-negative">{state.error}</p>;
  const rows = state.rows;
  const crm = rows.filter((r) => r.id.startsWith("crm:"));
  const short = crm.reduce((a, r) => a + (r.shortfall || 0), 0);
  const top = rows[0];
  return (
    <div className="space-y-3" data-testid="issues-list">
      <PlainWords testId="issues-plain-words" speak lines={[
        "These are the places where the books break a regulatory rule or a data control today.",
        `${crm.length} ${crm.length === 1 ? "check is" : "checks are"} in breach; provisions are SAR ${short.toLocaleString("en-US", { maximumFractionDigits: 1 })}m short of the floors.`,
        top ? `Start with the first: ${top.title.toLowerCase()}.` : "Nothing is open.",
        "Click an issue to see why it happens and what to do.",
      ]} />
      <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
        {rows.map((r) => (
          <li key={r.id}>
            <button type="button" onClick={() => onOpen(r.id)} data-testid="issues-row" data-issue={r.id}
                    className="grid w-full grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-hover">
              <span className="justify-self-start"><Chip tone={SEV_TONE[r.severity] ?? "neutral"}>{r.severity}</Chip></span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium text-text-primary">{r.title}</span>
                <span className={cn("block truncate text-[12px] text-text-secondary")}>
                  {r.article.replace("CBUAE CRM ", "")} · {r.book} · {r.period} · {r.line}</span>
              </span>
              <ChevronRight size={14} className="text-text-muted" />
            </button>
          </li>))}
      </ul>
    </div>
  );
}
