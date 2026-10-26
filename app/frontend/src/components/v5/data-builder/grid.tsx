"use client";

/**
 * The rows, and the data dictionary.
 *
 * In a comparison each value column is followed by its compare-period column
 * and, for numbers, the change; the change is tinted by sign only (whether a
 * rise is good depends on the column, so no colour claims it is).
 */

import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Column, type Row, cell, signedCell } from "@/lib/v5/data-builder";

export function Grid({ columns, rows, sort, desc, compact, stale, onSort, className }: {
  columns: Column[]; rows: Row[]; sort: string; desc: boolean; compact: boolean; stale: boolean;
  onSort: (column: string) => void;
  /** PLAN_R10 S4: the two-pane view passes "min-h-0 flex-1" so the grid fills the pane and scrolls inside it. */
  className?: string;
}) {
  const pad = compact ? "px-2 py-0.5" : "px-3 py-2";
  return (
    <div className={cn("overflow-auto rounded-lg border border-border bg-surface", className ?? "max-h-[70vh]", stale && "opacity-60")}
         data-testid="db-grid" data-density={compact ? "compact" : "comfortable"} aria-busy={stale}>
      <table className={cn("w-full border-collapse tabular-nums", compact ? "text-[11px]" : "text-[13px]")}>
        <thead className="sticky top-0 z-10 bg-surface-sunken">
          <tr>
            {columns.map((c) => {
              const active = sort === c.name;
              const Icon = active ? (desc ? ArrowDown : ArrowUp) : ArrowUpDown;
              const numeric = c.type !== "text" && c.type !== "date";
              return (
                <th key={c.name} scope="col"
                    className={cn("border-b border-border text-left align-bottom font-semibold text-text-secondary",
                                  numeric && "text-right", c.role === "compare" && "bg-surface-hover",
                                  c.role === "delta" && "bg-accent-muted/60")}
                    aria-sort={active ? (desc ? "descending" : "ascending") : "none"}>
                  <button type="button" onClick={() => onSort(c.name)} data-testid={`db-sort-${c.name}`}
                          title={`${c.description}${c.unit ? ` (${c.unit})` : ""}. Click to sort.`}
                          className={cn("flex w-full items-center gap-1 whitespace-nowrap hover:text-text-primary",
                                        pad, numeric && "justify-end", active && "text-accent")}>
                    <span className="flex flex-col leading-tight">
                      <span>{c.label}</span>
                      <span className="font-mono text-[9px] font-normal text-text-muted">
                        {c.role === "compare" ? `${c.period_of}` : c.role === "delta" ? "change" :
                          c.role === "value" && c.period_of ? c.period_of : c.name}
                        {c.unit && c.unit !== "count" && c.role !== "presence" ? ` · ${c.unit}` : ""}
                      </span>
                    </span>
                    <Icon className={cn("size-3 shrink-0", active ? "opacity-100" : "opacity-40")} aria-hidden />
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/70 last:border-0 hover:bg-surface-hover">
              {columns.map((c) => {
                const v = row[c.name];
                const numeric = c.type !== "text" && c.type !== "date";
                const delta = c.role === "delta";
                return (
                  <td key={c.name}
                      className={cn(pad, "whitespace-nowrap", numeric ? "text-right" : "text-left",
                                    c.key && "font-mono text-[0.95em] text-text-primary",
                                    !c.key && "text-text-primary", c.role === "compare" && "bg-surface-sunken/50 text-text-secondary",
                                    delta && typeof v === "number" && v > 0 && "text-positive",
                                    delta && typeof v === "number" && v < 0 && "text-negative",
                                    c.role === "presence" && v === "new" && "text-warning")}>
                    {delta ? signedCell(v, c.type) : cell(v, c.type)}
                  </td>
                );
              })}
            </tr>
          ))}
          {!rows.length ? (
            <tr><td colSpan={columns.length || 1} className="px-3 py-8 text-center text-sm text-text-muted" data-testid="db-empty">
              No rows match. Clear a filter or the search to see more.
            </td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

export function Dictionary({ columns, keyColumns, periodColumn }: {
  columns: Column[]; keyColumns: string[]; periodColumn: string | null;
}) {
  const [find, setFind] = React.useState("");
  const shown = columns.filter((c) => !find ||
    `${c.name} ${c.label} ${c.description} ${c.unit}`.toLowerCase().includes(find.toLowerCase()));
  const derived = columns.filter((c) => c.source === "derived").length;
  return (
    <div className="space-y-2" data-testid="db-dictionary-panel">
      <div className="flex flex-wrap items-center gap-3">
        <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a field…"
               aria-label="Find a field" data-testid="db-dict-search"
               className="h-8 w-56 rounded-md border border-border bg-surface px-2 text-[13px]" />
        <p className="text-xs text-text-muted">
          {columns.length} fields · key {keyColumns.join(" + ")}{periodColumn ? ` · period ${periodColumn}` : ""}
          {derived ? ` · ${derived} described from the column name (marked "derived")` : " · every description from the release's own manifest or the registry"}
        </p>
      </div>
      <div className="overflow-auto rounded-lg border border-border bg-surface">
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-[0.08em] text-text-muted">
            <tr>
              <th className="px-3 py-2">Field</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Unit</th>
              <th className="px-3 py-2">Description</th><th className="px-3 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.name} className="border-t border-border align-top" data-testid={`db-dict-row-${c.name}`}>
                <td className="px-3 py-2">
                  <p className="font-mono text-[12px] text-text-primary">{c.name}</p>
                  <p className="text-[11px] text-text-muted">{c.label}{c.key ? " · key" : ""}{c.period ? " · period" : ""}</p>
                </td>
                <td className="px-3 py-2 text-text-secondary">{c.type}</td>
                <td className="px-3 py-2 text-text-secondary">{c.unit || "—"}</td>
                <td className="px-3 py-2 text-text-primary">{c.description}</td>
                <td className="px-3 py-2">
                  <span className={cn("rounded-full border px-1.5 py-0.5 text-[10px]",
                                      c.source === "derived" ? "border-warning/30 bg-warning-muted text-warning"
                                        : "border-border text-text-muted")}>
                    {c.source}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
