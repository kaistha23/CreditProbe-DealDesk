"use client";

/**
 * The controls above the grid: search, filter builder and chips, column
 * chooser, density, period and compare, and the exports.
 */

import * as React from "react";
import { Columns3, Download, FileSpreadsheet, Filter as FilterIcon, Plus, Rows3, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type Column, type Filter, type Op, OPS, opLabel } from "@/lib/v5/data-builder";

const field = "h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30";
const label = "text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted";

/** Search: committed after a pause or on Enter, one Back step per committed term. */
export function SearchBox({ value, onCommit }: { value: string; onCommit: (q: string) => void }) {
  const [draft, setDraft] = React.useState({ base: value, text: value });
  // A new term from the address (Back, a link) replaces the draft -- derived
  // during render rather than set in an effect.
  const text = draft.base === value ? draft.text : value;
  const commit = React.useRef(onCommit);
  React.useEffect(() => { commit.current = onCommit; });
  React.useEffect(() => {
    if (text.trim() === value.trim()) return;
    const t = window.setTimeout(() => commit.current(text.trim()), 500);
    return () => window.clearTimeout(t);
  }, [text, value]);
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" aria-hidden />
      <input type="search" value={text} placeholder="Search IDs and text…" aria-label="Search the rows"
             data-testid="db-search" className={cn(field, "w-56 pl-7")}
             onChange={(e) => setDraft({ base: value, text: e.target.value })}
             onKeyDown={(e) => { if (e.key === "Enter") onCommit(text.trim()); }} />
    </div>
  );
}

export function PeriodSelect({ periods, period, latest, onChange }: {
  periods: string[]; period: string; latest: string | null; onChange: (p: string) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className={label}>Period</span>
      <select value={period || latest || "all"} onChange={(e) => onChange(e.target.value)} data-testid="db-period"
              className={field}>
        <option value="all">All periods</option>
        {[...periods].reverse().map((p) => <option key={p} value={p}>{p}{p === latest ? " (latest)" : ""}</option>)}
      </select>
    </label>
  );
}

export function CompareSelect({ periods, period, compare, onChange }: {
  periods: string[]; period: string; compare: string; onChange: (p: string) => void;
}) {
  const disabled = period === "all";
  return (
    <label className="flex flex-col gap-0.5" title={disabled ? "Choose one period to compare it with another" : undefined}>
      <span className={label}>Compare with</span>
      <select value={disabled ? "" : compare} onChange={(e) => onChange(e.target.value)} data-testid="db-compare"
              disabled={disabled} className={cn(field, disabled && "opacity-60")}>
        <option value="">No comparison</option>
        {[...periods].reverse().filter((p) => p !== period).map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
    </label>
  );
}

export function PageSize({ size, sizes, onChange }: { size: number; sizes: readonly number[]; onChange: (n: number) => void }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-text-muted">
      Rows per page
      <select value={size} onChange={(e) => onChange(Number(e.target.value))} data-testid="db-page-size" className={field}>
        {sizes.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
    </label>
  );
}

export function DensityToggle({ view, onChange }: { view: "comfortable" | "compact"; onChange: (v: "comfortable" | "compact") => void }) {
  const compact = view === "compact";
  return (
    <Button variant="outline" size="sm" aria-pressed={compact} data-testid="db-compact"
            onClick={() => onChange(compact ? "comfortable" : "compact")}
            title={compact ? "Switch to the comfortable view" : "Switch to the compact view"}>
      <Rows3 aria-hidden /> {compact ? "Compact" : "Comfortable"}
    </Button>
  );
}

export function ExportLinks({ csv, xlsx, total }: { csv: string; xlsx: string; total: number | null }) {
  const cls = "inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 text-xs font-medium text-text-primary hover:bg-surface-hover";
  const capped = total !== null && total > 200_000;
  return (
    <div className="flex items-center gap-2">
      <a href={csv} download data-testid="db-export-csv" className={cls} title="Every matching row, as CSV">
        <Download className="size-3.5" aria-hidden /> Export CSV
      </a>
      <a href={xlsx} download data-testid="db-export-xlsx" className={cls}
         title={capped ? "Excel holds the first 200,000 matching rows; the About sheet says so. Use CSV for all." :
           "Every matching row, as Excel, with an About sheet and the dictionary"}>
        <FileSpreadsheet className="size-3.5" aria-hidden /> Export Excel
      </a>
    </div>
  );
}

// ---------------------------------------------------------------- filters

export function FilterBar({ columns, filters, onChange }: {
  columns: Column[]; filters: Filter[]; onChange: (f: Filter[]) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const byName = React.useMemo(() => new Map(columns.map((c) => [c.name, c])), [columns]);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                data-testid="db-filter-add">
          <Plus aria-hidden /> Add filter
        </Button>
        {filters.map((f, i) => {
          const col = byName.get(f.column);
          return (
            <span key={`${f.column}-${f.op}-${f.value}-${i}`} data-testid={`db-chip-${i}`}
                  className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent-muted py-0.5 pl-2.5 pr-1 text-xs text-accent">
              <FilterIcon className="size-3" aria-hidden />
              <span className="font-medium">{col?.label ?? f.column}</span>
              <span className="text-text-secondary">{opLabel(f.op)}</span>
              <span className="font-medium">{f.value === "" ? "empty" : f.value}</span>
              <button type="button" onClick={() => onChange(filters.filter((_, j) => j !== i))}
                      aria-label={`Remove the filter on ${col?.label ?? f.column}`} data-testid="db-chip-clear"
                      className="ml-0.5 rounded-full p-0.5 hover:bg-accent/15">
                <X className="size-3" aria-hidden />
              </button>
            </span>
          );
        })}
        {filters.length > 1 ? (
          <button type="button" onClick={() => onChange([])} data-testid="db-filters-clear"
                  className="text-xs text-text-muted underline-offset-2 hover:text-text-primary hover:underline">
            Clear all filters
          </button>
        ) : null}
      </div>
      {open ? (
        <FilterBuilder columns={columns} onCancel={() => setOpen(false)}
                       onApply={(f) => { setOpen(false); onChange([...filters, f]); }} />
      ) : null}
    </div>
  );
}

function FilterBuilder({ columns, onApply, onCancel }: {
  columns: Column[]; onApply: (f: Filter) => void; onCancel: () => void;
}) {
  const [column, setColumn] = React.useState(columns[0]?.name ?? "");
  const [op, setOp] = React.useState<Op>("eq");
  const [value, setValue] = React.useState("");
  const col = columns.find((c) => c.name === column);
  const numeric = col ? col.type !== "text" && col.type !== "date" : false;
  const ops = OPS.filter((o) => (numeric ? o.numeric : o.text));
  const effectiveOp = ops.some((o) => o.op === op) ? op : ops[0].op;
  const invalid = numeric && effectiveOp !== "in" && value.trim() !== "" && !Number.isFinite(Number(value));
  const apply = () => { if (column && !invalid) onApply({ column, op: effectiveOp, value: value.trim() }); };
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border border-border bg-surface-sunken p-2.5" data-testid="db-filter-builder">
      <label className="flex flex-col gap-0.5">
        <span className={label}>Column</span>
        <select value={column} onChange={(e) => setColumn(e.target.value)} data-testid="db-filter-column" className={cn(field, "max-w-64")}>
          {columns.map((c) => <option key={c.name} value={c.name}>{c.label} ({c.name})</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className={label}>Operator</span>
        <select value={effectiveOp} onChange={(e) => setOp(e.target.value as Op)} data-testid="db-filter-op" className={field}>
          {ops.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className={label}>{effectiveOp === "in" ? "Values (comma-separated)" : "Value"}</span>
        <input value={value} onChange={(e) => setValue(e.target.value)} data-testid="db-filter-value"
               onKeyDown={(e) => { if (e.key === "Enter") apply(); }}
               inputMode={numeric && effectiveOp !== "in" ? "decimal" : undefined}
               placeholder={numeric ? (col?.type === "flag" ? "0 or 1" : "a number") : "text"}
               className={cn(field, "w-48", invalid && "border-negative")} aria-invalid={invalid} />
      </label>
      <Button size="sm" onClick={apply} disabled={!column || invalid} data-testid="db-filter-apply">Apply</Button>
      <Button size="sm" variant="ghost" onClick={onCancel} data-testid="db-filter-cancel">Cancel</Button>
      {col ? <p className="basis-full text-[11px] text-text-muted">{col.description}{col.unit ? ` · ${col.unit}` : ""}</p> : null}
    </div>
  );
}

// ---------------------------------------------------------------- columns

export function ColumnChooser({ columns, chosen, onApply }: {
  columns: Column[]; chosen: string[]; onApply: (cols: string[]) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<Set<string>>(new Set());
  const [filter, setFilter] = React.useState("");
  const all = columns.map((c) => c.name);
  const start = () => { setDraft(new Set(chosen.length ? chosen : all)); setFilter(""); setOpen(true); };
  const shown = columns.filter((c) => !filter || `${c.name} ${c.label}`.toLowerCase().includes(filter.toLowerCase()));
  const toggle = (name: string) => setDraft((d) => { const n = new Set(d); if (n.has(name)) n.delete(name); else n.add(name); return n; });
  return (
    <div className="relative">
      <Button variant="outline" size="sm" onClick={() => (open ? setOpen(false) : start())} aria-expanded={open}
              data-testid="db-columns">
        <Columns3 aria-hidden /> Columns {chosen.length ? `(${chosen.length} of ${all.length})` : `(${all.length})`}
      </Button>
      {open ? (
        <div className="absolute right-0 z-30 mt-1 w-80 rounded-lg border border-border bg-surface p-2.5 shadow-lg" data-testid="db-columns-panel">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a column…"
                 aria-label="Find a column" className={cn(field, "mb-2 w-full")} data-testid="db-columns-find" />
          <div className="mb-2 flex gap-2 text-xs">
            <button type="button" className="text-accent hover:underline" data-testid="db-columns-all"
                    onClick={() => setDraft(new Set(all))}>Select all</button>
            <button type="button" className="text-accent hover:underline" data-testid="db-columns-none"
                    onClick={() => setDraft(new Set(columns.filter((c) => c.key).map((c) => c.name)))}>Keys only</button>
          </div>
          <div className="max-h-72 space-y-0.5 overflow-y-auto pr-1">
            {shown.map((c) => (
              <label key={c.name} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-surface-hover">
                <input type="checkbox" checked={draft.has(c.name)} onChange={() => toggle(c.name)}
                       data-testid={`db-column-${c.name}`} />
                <span className="truncate text-text-primary">{c.label}</span>
                <span className="ml-auto truncate font-mono text-[10px] text-text-muted">{c.name}</span>
              </label>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-border pt-2">
            <span className="text-[11px] text-text-muted">{draft.size} of {all.length} chosen</span>
            <div className="flex gap-1.5">
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)} data-testid="db-columns-cancel">Cancel</Button>
              <Button size="sm" disabled={!draft.size} data-testid="db-columns-apply"
                      onClick={() => {
                        setOpen(false);
                        // Keep the relation's own column order; all of them chosen is the default view.
                        const next = all.filter((n) => draft.has(n));
                        onApply(next.length === all.length ? [] : next);
                      }}>
                Apply
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
