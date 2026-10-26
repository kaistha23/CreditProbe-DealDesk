"use client";

import * as React from "react";

import { PoweredBy } from "@/components/v5/core/powered-by";
import { boldParts, confidence, type Powered, type Table, type Trace } from "@/lib/v5/queries";
import { cn } from "@/lib/utils";

/** Text with its key figures in bold ("**SAR 1.2bn**"). */
export function Rich({ text, className }: { text: string; className?: string }) {
  return (
    <p className={cn("text-[14px] leading-relaxed text-text-primary", className)}>
      {boldParts(text).map((p, i) => (p.bold ? <strong key={i} className="font-semibold">{p.text}</strong> : <React.Fragment key={i}>{p.text}</React.Fragment>))}
    </p>
  );
}

const RIGHT = new Set(["sar", "pct", "count", "days", "ratio"]);

export function DataTable({ table, testId, max = 25 }: { table: Table; testId: string; max?: number }) {
  const [all, setAll] = React.useState(false);
  const rows = all ? table.rows : table.rows.slice(0, max);
  return (
    <div className="overflow-x-auto rounded-md border border-border" data-testid={testId}>
      <table className="w-full text-[12px]">
        <thead className="bg-surface-hover text-text-secondary">
          <tr>{table.columns.map((c) => <th key={c.key} className={cn("px-2 py-1.5 font-medium", RIGHT.has(c.kind) ? "text-right" : "text-left")}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              {table.columns.map((c) => <td key={c.key} className={cn("px-2 py-1", RIGHT.has(c.kind) ? "text-right tabular-nums" : "text-left")}>{String(r[`${c.key}__d`] ?? "")}</td>)}
            </tr>
          ))}
          {table.total ? (
            <tr className="border-t-2 border-border font-semibold">
              {table.columns.map((c) => <td key={c.key} className={cn("px-2 py-1", RIGHT.has(c.kind) ? "text-right tabular-nums" : "text-left")}>{String(table.total?.[`${c.key}__d`] ?? "")}</td>)}
            </tr>
          ) : null}
        </tbody>
      </table>
      {table.rows.length > max ? (
        <button type="button" onClick={() => setAll(!all)} className="w-full border-t border-border py-1 text-[12px] text-accent hover:bg-surface-hover" data-testid={`${testId}-more`}>
          {all ? "Show fewer" : `Show all ${table.rows.length.toLocaleString("en-US")} rows`}
        </button>
      ) : null}
    </div>
  );
}

/** Powered by P7 plus the Trace, opened in place. */
export function PoweredTrace({ powered, trace, testId }: { powered: Powered; trace: Trace; testId: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <PoweredBy pack={powered.pack_id} rule={powered.rule} article={powered.article} confidence={confidence(powered.confidence)} testId={`${testId}-pb`} />
        <button type="button" onClick={() => setOpen(!open)} className="rounded border border-border px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover" data-testid={`${testId}-trace`}>
          {open ? "Hide trace" : "Trace"}
        </button>
      </div>
      {open ? (
        <div className="rounded-md border border-border bg-surface-hover/50 p-3 text-[12px] text-text-secondary" data-testid={`${testId}-trace-panel`}>
          <div><span className="font-medium text-text-primary">Rule</span> {trace.rule} · {trace.article}</div>
          <div><span className="font-medium text-text-primary">Sources</span> {trace.sources.join(", ")} · period {trace.period} · {trace.row_count.toLocaleString("en-US")} rows read</div>
          <ol className="mt-1 list-decimal pl-5">{trace.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <div className="mt-1 text-text-muted">{trace.engine}</div>
        </div>
      ) : null}
    </div>
  );
}

export function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "info" }) {
  const c = {
    neutral: "bg-surface-hover text-text-secondary",
    good: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
    warn: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
    bad: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
    info: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200",
  }[tone];
  return <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium", c)}>{children}</span>;
}

export const STATUS_TONE: Record<string, "neutral" | "good" | "warn" | "bad" | "info"> = {
  Open: "warn", Drafted: "info", Reviewed: "neutral", Sent: "good", Draft: "neutral", Locked: "info", Run: "warn", Published: "good", PASS: "good", FAIL: "bad",
};
