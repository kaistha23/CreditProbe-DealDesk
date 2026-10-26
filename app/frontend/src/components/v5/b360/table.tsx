"use client";

/**
 * The tables and figures every Borrower 360 tab is built from.
 *
 * The service names each column's unit, so a value is formatted the same way
 * on every tab and in the workbook: SAR million, per cent, probability, times,
 * a rating on the global scale, an Early Warning band.
 */

import * as React from "react";

import { InfoPopover } from "@/components/ui/info-popover";
import { cn } from "@/lib/utils";
import { type Column, type Row, type SummaryFigure, type Table, type Unit, formatValue } from "@/lib/v5/b360";

export function bandTone(band: string): string {
  switch ((band || "").toLowerCase()) {
    case "critical":
      return "bg-negative-muted text-negative border-negative/30";
    case "high":
      return "bg-warning-muted text-warning border-warning/30";
    case "moderate":
      return "bg-accent-muted text-accent border-accent/30";
    default:
      return "bg-surface-sunken text-text-secondary border-border";
  }
}

export function EwsBand({ band, testId }: { band: string | null | undefined; testId?: string }) {
  const b = band || "none";
  return (
    <span data-testid={testId}
          className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase"
                        + " tracking-[0.08em]", bandTone(b))}>
      {b}
    </span>
  );
}

export function Value({ value, unit }: { value: unknown; unit: Unit }) {
  if (unit === "ews_band") return <EwsBand band={value === null || value === undefined ? "none" : String(value)} />;
  if (unit === "chips") return <ReasonChips codes={value} />;
  const text = formatValue(value, unit);
  if (unit === "rating") return <span className="font-semibold tabular-nums">{text}</span>;
  if (unit === "id" || unit === "code") return <span className="font-mono text-[11px]">{text}</span>;
  return <span className="tabular-nums">{text}</span>;
}

const NUMERIC: Unit[] = ["sar_mn", "sar_k", "pct", "prob", "x", "int", "days", "months", "num"];

export function Summary({ figures, testId }: { figures: SummaryFigure[]; testId?: string }) {
  if (!figures.length) return null;
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6" data-testid={testId}>
      {figures.map((f, i) => (
        <div key={`${i}-${f.label}`} className="min-w-0">
          <p className="truncate text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">{f.label}</p>
          <p className="text-[15px] font-medium text-text-primary"><Value value={f.value} unit={f.unit} /></p>
        </div>
      ))}
    </div>
  );
}

const PAGE = 25;

export function DataTable({ table, testId, onOpenId, highlight }: {
  table: Table; testId?: string;
  /** Make the first id column a link (e.g. open a group member). */
  onOpenId?: (id: string) => void;
  highlight?: (row: Row) => boolean;
}) {
  const [all, setAll] = React.useState(false);
  const rows = all ? table.rows : table.rows.slice(0, PAGE);
  const idCol = onOpenId ? table.columns.find((c) => c.unit === "id")?.key : undefined;
  return (
    <div className="space-y-1.5" data-testid={testId}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <p className="text-[13px] font-semibold text-text-primary">{table.title}</p>
        <p className="text-[11px] text-text-muted">{table.rows.length.toLocaleString("en-US")} rows</p>
        {table.note ? <InfoPopover title={table.title}><p>{table.note}</p></InfoPopover> : null}
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-[11.5px]">
          <thead className="bg-surface-sunken">
            <tr>
              {table.columns.map((c: Column) => (
                <th key={c.key} scope="col"
                    className={cn("whitespace-nowrap px-2 py-1.5 font-medium text-text-muted",
                                  NUMERIC.includes(c.unit) ? "text-right" : "text-left")}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={cn("border-t border-border/70", highlight?.(r) && "bg-accent-muted/40")}>
                {table.columns.map((c) => {
                  const unit = c.unit === "@unit" ? ((r.unit as Unit) || "text") : c.unit;
                  const v = r[c.key];
                  return (
                    <td key={c.key}
                        className={cn("px-2 py-1 align-top", NUMERIC.includes(unit) ? "text-right" : "text-left",
                                      unit === "code" ? "max-w-[22rem] break-words" : "whitespace-nowrap")}>
                      {idCol === c.key && onOpenId && typeof v === "string" ? (
                        <button type="button" onClick={() => onOpenId(v)} data-testid={`b360-open-${v}`}
                                className="font-mono text-[11px] text-accent hover:underline">{v}</button>
                      ) : <Value value={v} unit={unit} />}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!table.rows.length ? (
              <tr><td colSpan={table.columns.length} className="px-2 py-2 text-[11px] italic text-text-muted">No rows.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {table.rows.length > PAGE ? (
        <button type="button" onClick={() => setAll((x) => !x)} data-testid={testId ? `${testId}-more` : undefined}
                className="text-[11px] text-accent hover:underline">
          {all ? `Show the first ${PAGE}` : `Show all ${table.rows.length.toLocaleString("en-US")} rows`}
        </button>
      ) : null}
    </div>
  );
}

/** PLAN_R9 B3: SICR / UTP reason codes as short chips ("DPD30", "COVENANT"); the full code is the title. */
export function ReasonChips({ codes }: { codes: unknown }) {
  const list = String(codes ?? "").split(",").map((x) => x.trim()).filter(Boolean);
  if (!list.length) return <span className="text-text-muted">—</span>;
  return (
    <span className="inline-flex flex-nowrap gap-1" title={list.join(", ")}>
      {list.slice(0, 2).map((c) => {
        const utp = /^UTP[-_]/.test(c);
        return (
          <span key={c} title={c} data-testid={`chip-${c}`}
                className={utp ? "rounded bg-negative/10 px-1.5 py-0.5 text-[10px] font-medium text-negative"
                               : "rounded bg-warning-muted px-1.5 py-0.5 text-[10px] font-medium text-warning"}>
            {c.replace(/^(SICR|UTP)[-_]/, "").replace(/[_-]/g, " ")}
          </span>
        );
      })}
      {list.length > 2 ? <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] text-text-secondary">+{list.length - 2}</span> : null}
    </span>
  );
}
