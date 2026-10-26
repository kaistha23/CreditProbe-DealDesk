"use client";

/**
 * The Borrower 360 book list (PLAN_R4 B2): every borrower (corporate) or
 * customer (retail) on the book at the period, paged, sorted, searched and
 * filtered by the Borrower 360 service (GET /list). Nothing is computed here.
 *
 * The list's state is in the address (lib/v5/b360-list.ts), so a row opened
 * from here and Back return to the same list, filters and page. The column
 * choice is kept per user in this browser.
 */

import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Columns3, FileSpreadsheet, Search as SearchIcon, SlidersHorizontal, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/components/system/auth";
import { cn } from "@/lib/utils";
import {
  type DomainId, type ListColumn, type ListOption, type ListOptions, type ListPage, type Unit, b360, listExcelHref,
  useB360,
} from "@/lib/v5/b360";
import {
  type FilterKey, type ListState, PAGE_SIZES, activeFilterCount, apiQuery, columnsStorageKey, emptyFilters, nextSort,
  pageCount, visibleColumns, withFilter,
} from "@/lib/v5/b360-list";
import { count, sar } from "@/lib/v5/ews";

import { SendToWhatIf } from "./intel";
import { Value } from "./table";

const NUMERIC: Unit[] = ["sar_mn", "sar_k", "pct", "prob", "x", "int", "days", "months", "num"];
const DEFAULT_ORDER = { sort: "ews_score", dir: "desc" };
const DPD_LABEL: Record<string, string> = { "0": "Current", "1-29": "1–29 days", "30-59": "30–59 days", "60-89": "60–89 days", "90+": "90+ days" };

export function BookList({ domain, period, list, onChange, onPeriod, onOpen }: {
  domain: DomainId; period: string; list: ListState;
  /** A new list state; `replace` for typing, so every keystroke is not a Back step. */
  onChange: (next: ListState, replace?: boolean) => void;
  onPeriod: (period: string) => void;
  onOpen: (id: string, period: string) => void;
}) {
  const query = apiQuery(list);
  const key = `${domain}|${period}|${JSON.stringify(query)}`;
  const page = useB360<ListPage>(() => b360.list(domain, period, query), key);
  const opts = useB360<ListOptions>(() => b360.listOptions(domain, period), `${domain}|${period}`);
  // Keep the last page on screen while the next one loads (no flash between pages).
  const [last, setLast] = React.useState<ListPage | null>(null);
  if (page.data && page.data !== last) setLast(page.data);
  const data = page.data ?? (last && last.domain_id === domain ? last : null);
  const columns = useColumns(domain, data?.columns ?? opts.data?.columns ?? []);
  const labels = data?.labels ?? opts.data?.labels;
  const owners = labels?.owners ?? (domain === "corporate" ? "borrowers" : "customers");

  return (
    <Card data-testid="b360-list" data-loading={page.loading ? "true" : "false"}
          data-total={data?.total ?? ""} data-page={list.page}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <SearchBox domain={domain} value={list.q} onCommit={(q, replace) => onChange({ ...list, q, page: 1 }, replace)} />
        {data ? (
          <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
            {domain === "corporate" ? "Quarter" : "Month"}
            <select value={data.period} onChange={(e) => onPeriod(e.target.value)} data-testid="b360-list-period"
                    className="h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary">
              {[...data.periods].reverse().map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <ColumnChooser all={columns.all} visible={columns.visible} onToggle={columns.toggle} onReset={columns.reset} />
          {data ? (
            <SendToWhatIf domain={domain} period={data.period} label={`Send ${count(data.total)} to What-If`}
                          query={Object.fromEntries(Object.entries(query).filter(([k]) => k !== "offset" && k !== "limit" && k !== "sort" && k !== "dir"))}
                          testId="b360-list-whatif" />
          ) : null}
          {data ? (
            <Button asChild size="sm">
              <a href={listExcelHref(domain, data.period, query, columns.visible)} download data-testid="b360-list-excel">
                <FileSpreadsheet aria-hidden /> Export to Excel
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      <Filters list={list} options={opts.data} onChange={onChange} />

      {page.error ? <p className="px-4 py-3 text-sm text-negative" data-testid="b360-list-error">{page.error}</p> : null}
      {!data && !page.error ? <div className="p-4"><Skeleton className="h-72 w-full" /></div> : null}
      {data ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-border bg-surface-sunken/60 px-4 py-2"
               data-testid="b360-list-summary">
            <Figure label={owners} value={count(data.total)} testId="b360-list-total" />
            <Figure label="EAD" value={sar(data.totals.ead)} testId="b360-list-ead" />
            <Figure label="ECL" value={sar(data.totals.ecl)} testId="b360-list-ecl" />
            <Figure label={labels?.exposures ?? ""} value={count(data.totals.exposures)} testId="b360-list-exposures" />
            <span className="self-center">
              <InfoPopover title={`The ${domain} book at ${data.period}`}>
                <p>Every {labels?.owner} on the {domain} book at {data.period}: {count(data.book_total)} in all, EAD {sar(data.book_ead)}.</p>
                <p>EAD, ECL and limit are sums over the {labels?.owner}&apos;s {labels?.exposures} at the period; stage and DPD are the worst of them.</p>
                <p>The Early Warning score is the highest score of the {labels?.exposures}, banded by the active rule set&apos;s floors. Amounts in SAR.</p>
              </InfoPopover>
            </span>
          </div>
          <div className={cn("overflow-x-auto transition-opacity", page.loading && "opacity-60")}>
            <table className="w-full text-[12px]" data-testid="b360-list-table">
              <thead className="bg-surface-sunken">
                <tr>
                  {columns.shown.map((c) => (
                    <SortHeader key={c.key} col={c} list={list} active={data.sort} dir={data.dir}
                                onSort={() => onChange(nextSort(list, c.key, NUMERIC.includes(c.unit) || c.unit === "ews_band"
                                                                || c.unit === "rating", DEFAULT_ORDER))} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => {
                  const id = String(r.id);
                  return (
                    <tr key={id} data-testid={`b360-row-${id}`} onClick={() => onOpen(id, data.period)}
                        className="cursor-pointer border-t border-border/70 hover:bg-surface-hover">
                      {columns.shown.map((c) => (
                        <td key={c.key} className={cn("whitespace-nowrap px-2.5 py-1.5", NUMERIC.includes(c.unit) ? "text-right" : "text-left",
                                                      c.key === "products" && "max-w-[12rem] truncate")}
                            title={c.key === "products" || c.key === "name" ? String(r[c.key] ?? "") : undefined}>
                          {c.key === "id" ? (
                            <button type="button" className="font-mono text-[11.5px] text-accent hover:underline"
                                    onClick={(e) => { e.stopPropagation(); onOpen(id, data.period); }}
                                    data-testid={`b360-open-row-${id}`}>{id}</button>
                          ) : c.key === "name" ? <span className="font-medium text-text-primary">{String(r.name ?? "—")}</span>
                            : <Value value={r[c.key]} unit={c.unit} />}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {!data.rows.length ? (
                  <tr><td colSpan={columns.shown.length} className="px-3 py-6 text-center text-[12px] text-text-muted"
                          data-testid="b360-list-empty">No {owners} match.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <Pager list={list} total={data.total} onChange={onChange} />
        </>
      ) : null}
    </Card>
  );
}

function Figure({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <p className="text-[12px] text-text-secondary">
      <span className="mr-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{label}</span>
      <span className="font-semibold tabular-nums text-text-primary" data-testid={testId}>{value}</span>
    </p>
  );
}

// ---------------------------------------------------------------- search

function SearchBox({ domain, value, onCommit }: { domain: DomainId; value: string; onCommit: (q: string, replace: boolean) => void }) {
  const [typed, setTyped] = React.useState({ base: value, text: value });
  const text = typed.base === value ? typed.text : value;
  const commit = React.useRef(onCommit);
  React.useEffect(() => { commit.current = onCommit; });
  React.useEffect(() => {
    if (text.trim() === value) return;
    const t = setTimeout(() => commit.current(text.trim(), true), 350);
    return () => clearTimeout(t);
  }, [text, value]);
  return (
    <form className="flex min-w-[16rem] flex-1 items-center gap-2 rounded-md border border-border bg-surface px-2.5 focus-within:border-accent"
          onSubmit={(e) => { e.preventDefault(); if (text.trim() !== value) onCommit(text.trim(), false); }}>
      <SearchIcon className="size-4 text-text-muted" aria-hidden />
      <input value={text} onChange={(e) => setTyped({ base: value, text: e.target.value })} data-testid="b360-search"
             aria-label={domain === "corporate" ? "Search borrowers" : "Search customers"}
             placeholder={domain === "corporate" ? "Search borrower ID or name" : "Search customer ID"}
             className="h-8 flex-1 bg-transparent text-[13px] outline-none" />
      {text ? (
        <button type="button" aria-label="Clear the search" data-testid="b360-search-clear"
                onClick={() => { setTyped({ base: value, text: "" }); onCommit("", false); }}
                className="rounded p-0.5 text-text-muted hover:text-text-primary"><X className="size-3.5" aria-hidden /></button>
      ) : null}
    </form>
  );
}

// ---------------------------------------------------------------- filters

function Filters({ list, options, onChange }: {
  list: ListState; options: ListOptions | null; onChange: (next: ListState, replace?: boolean) => void;
}) {
  if (!options) return <div className="h-12 border-b border-border" />;
  const l = options.labels;
  const parentOf = (sub: string) => options.subsegment.find((x) => x.value === sub)?.parent;
  const set = (key: FilterKey, value: string) => onChange(withFilter(list, key, value, parentOf));
  const subs = options.subsegment.filter((x) => !list.filters.segment || x.parent === list.filters.segment);
  const fields: { key: FilterKey; label: string; options: ListOption[]; show?: (v: string) => string }[] = [
    { key: "segment", label: l.segment, options: options.segment },
    { key: "subsegment", label: l.subsegment, options: dedupe(subs) },
    { key: "region", label: l.region, options: options.region },
    ...(options.branch_available ? [{ key: "branch" as FilterKey, label: l.branch, options: options.branch }] : []),
    { key: "product", label: l.product, options: options.product },
    { key: "band", label: l.band, options: options.band.filter((x) => x.count > 0) },
    { key: "stage", label: l.stage, options: options.stage },
    { key: "ews", label: l.ews, options: options.ews, show: (v) => v[0].toUpperCase() + v.slice(1) },
    { key: "dpd", label: l.dpd, options: options.dpd, show: (v) => DPD_LABEL[v] ?? v },
    // PLAN_R9 B2: the P2 filters.
    ...(options.sicr?.length ? [{ key: "sicr" as FilterKey, label: "SICR reason", options: options.sicr,
                                  show: (v: string) => options.sicr?.find((x) => x.value === v)?.label ?? v }] : []),
    ...(options.utp?.length ? [{ key: "utp" as FilterKey, label: "UTP reason", options: options.utp,
                                 show: (v: string) => options.utp?.find((x) => x.value === v)?.label ?? v }] : []),
    ...(options.watch?.length ? [{ key: "watch" as FilterKey, label: "Watch status", options: options.watch.filter((x) => x.count > 0) }] : []),
    ...(options.rm?.length ? [{ key: "rm" as FilterKey, label: "Relationship manager", options: options.rm }] : []),
  ];
  const active = activeFilterCount(list) - (list.q ? 1 : 0);
  // PLAN_R10 E2: one row of the main filters plus "More filters"; the rest open on a click (or when one is set).
  const primary = fields.filter((f) => PRIMARY_FILTERS.includes(f.key));
  const secondary = fields.filter((f) => !PRIMARY_FILTERS.includes(f.key));
  const moreActive = secondary.filter((f) => list.filters[f.key]).length
    + (list.filters.ead_min ? 1 : 0) + (list.filters.ead_max ? 1 : 0);
  return (
    <MoreFilters primary={primary} secondary={secondary} moreActive={moreActive} list={list} set={set}
                 extra={<AmountRange list={list} label={l.ead} onChange={onChange} />}
                 clear={active ? (
                   <Button variant="ghost" size="sm" data-testid="b360-filters-clear"
                           onClick={() => onChange({ ...list, filters: emptyFilters(), page: 1 })}>
                     <X aria-hidden /> Clear filters
                   </Button>
                 ) : null} />
  );
}

const PRIMARY_FILTERS: FilterKey[] = ["segment", "region", "stage", "ews"];

type FilterField = { key: FilterKey; label: string; options: ListOption[]; show?: (v: string) => string };

function MoreFilters({ primary, secondary, moreActive, list, set, extra, clear }: {
  primary: FilterField[]; secondary: FilterField[]; moreActive: number; list: ListState;
  set: (key: FilterKey, value: string) => void; extra: React.ReactNode; clear: React.ReactNode;
}) {
  const [userOpen, setOpen] = React.useState(false);
  const open = userOpen || moreActive > 0;
  const select = (f: FilterField) => (
        <select key={f.key} value={list.filters[f.key]} onChange={(e) => set(f.key, e.target.value)}
                aria-label={f.label} data-testid={`b360-filter-${f.key}`}
                className={cn("h-8 max-w-[13rem] rounded-md border bg-surface px-2 text-[12px]",
                              list.filters[f.key] ? "border-accent text-text-primary" : "border-border text-text-secondary")}>
          <option value="">{f.label}: all</option>
          {f.options.map((o) => {
            const text = f.show ? f.show(o.value) : o.value;
            // The chosen value reads with its filter's name ("Branch: Riyadh Olaya"); the open list stays short.
            return <option key={o.value} value={o.value}>{o.value === list.filters[f.key] ? `${f.label}: ${text}` : text}</option>;
          })}
        </select>
  );
  return (
    <div className="border-b border-border px-4 py-2" data-testid="b360-filters">
      <div className="flex flex-wrap items-center gap-2">
        {primary.map(select)}
        <Button variant="outline" size="sm" aria-expanded={open} data-testid="b360-filters-more"
                onClick={() => setOpen(!open)} disabled={open && moreActive > 0}>
          <SlidersHorizontal className="mr-1 size-3.5" aria-hidden />
          {open ? "Fewer filters" : "More filters"}{moreActive ? ` · ${moreActive} set` : ""}
        </Button>
        {clear}
      </div>
      {open ? (
        <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="b360-filters-more-panel">
          {secondary.map(select)}
          {extra}
        </div>
      ) : null}
    </div>
  );
}

function dedupe(xs: ListOption[]): ListOption[] {
  const seen = new Set<string>();
  return xs.filter((x) => (seen.has(x.value) ? false : (seen.add(x.value), true)));
}

function AmountRange({ list, label, onChange }: { list: ListState; label: string; onChange: (next: ListState) => void }) {
  const [draft, setDraft] = React.useState({ base: `${list.filters.ead_min}|${list.filters.ead_max}`,
                                             min: list.filters.ead_min, max: list.filters.ead_max });
  const base = `${list.filters.ead_min}|${list.filters.ead_max}`;
  const min = draft.base === base ? draft.min : list.filters.ead_min;
  const max = draft.base === base ? draft.max : list.filters.ead_max;
  const commit = () => {
    const clean = (v: string) => (v.trim() && Number.isFinite(Number(v)) ? String(Number(v)) : "");
    const next = { ...list, filters: { ...list.filters, ead_min: clean(min), ead_max: clean(max) }, page: 1 };
    if (next.filters.ead_min !== list.filters.ead_min || next.filters.ead_max !== list.filters.ead_max) onChange(next);
  };
  const input = (value: string, key: "min" | "max", placeholder: string) => (
    <input type="number" inputMode="decimal" min={0} step="any" value={value} placeholder={placeholder}
           aria-label={`${label} ${key === "min" ? "from" : "to"}`} data-testid={`b360-filter-ead_${key}`}
           onChange={(e) => setDraft({ base, min: key === "min" ? e.target.value : min, max: key === "max" ? e.target.value : max })}
           onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
           className={cn("h-8 w-[6.5rem] rounded-md border bg-surface px-2 text-[12px] tabular-nums",
                         (key === "min" ? list.filters.ead_min : list.filters.ead_max) ? "border-accent" : "border-border")} />
  );
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-text-muted" data-testid="b360-filter-ead">
      {input(min, "min", "EAD from")}
      <span aria-hidden>–</span>
      {input(max, "max", "EAD to")}
      <span>SAR m</span>
    </span>
  );
}

// ---------------------------------------------------------------- table parts

function SortHeader({ col, list, active, dir, onSort }: {
  col: ListColumn; list: ListState; active: string; dir: string; onSort: () => void;
}) {
  const on = active === col.key;
  const Icon = on ? (dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  const numeric = NUMERIC.includes(col.unit);
  return (
    <th scope="col" aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"}
        className={cn("whitespace-nowrap px-2.5 py-2 font-medium text-text-muted", numeric ? "text-right" : "text-left")}
        data-sorted={on ? dir : undefined}>
      <button type="button" onClick={onSort} data-testid={`b360-sort-${col.key}`}
              className={cn("inline-flex items-center gap-1 text-[10.5px] uppercase tracking-[0.06em] hover:text-text-primary",
                            numeric && "flex-row-reverse", on && "text-text-primary")}
              title={list.sort === col.key ? undefined : `Sort by ${col.label}`}>
        {col.label}
        <Icon className={cn("size-3", !on && "opacity-40")} aria-hidden />
      </button>
    </th>
  );
}

function Pager({ list, total, onChange }: { list: ListState; total: number; onChange: (next: ListState) => void }) {
  const pages = pageCount(total, list.size);
  const first = total ? (list.page - 1) * list.size + 1 : 0;
  const lastRow = Math.min(total, list.page * list.size);
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border px-4 py-2.5 text-[12px] text-text-secondary">
      <span data-testid="b360-page-info">
        {count(first)}–{count(lastRow)} of {count(total)}
      </span>
      <label className="flex items-center gap-1.5 text-text-muted">
        Rows per page
        <select value={list.size} onChange={(e) => onChange({ ...list, size: Number(e.target.value), page: 1 })}
                data-testid="b360-page-size" className="h-7 rounded-md border border-border bg-surface px-1.5 text-[12px] text-text-primary">
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <span className="ml-auto flex items-center gap-1.5">
        <span className="text-text-muted" data-testid="b360-page-of">Page {count(list.page)} of {count(pages)}</span>
        <Button variant="outline" size="sm" disabled={list.page <= 1} data-testid="b360-page-prev"
                onClick={() => onChange({ ...list, page: list.page - 1 })} aria-label="Previous page">
          <ChevronLeft aria-hidden />
        </Button>
        <Button variant="outline" size="sm" disabled={list.page >= pages} data-testid="b360-page-next"
                onClick={() => onChange({ ...list, page: list.page + 1 })} aria-label="Next page">
          <ChevronRight aria-hidden />
        </Button>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------- column chooser

function useColumns(domain: DomainId, all: ListColumn[]) {
  const { user } = useAuth();
  const storageKey = columnsStorageKey(user?.username, domain);
  const [stored, setStored] = React.useState<{ key: string; value: string | null } | null>(null);
  React.useEffect(() => {
    let value: string | null = null;
    try { value = window.localStorage.getItem(storageKey); } catch { value = null; }
    setStored({ key: storageKey, value });
  }, [storageKey]);
  const current = stored && stored.key === storageKey ? stored.value : null;
  const visible = visibleColumns(all, current);
  const save = (keys: string[] | null) => {
    const value = keys ? JSON.stringify(keys) : null;
    try {
      if (value) window.localStorage.setItem(storageKey, value);
      else window.localStorage.removeItem(storageKey);
    } catch { /* a browser without storage keeps the choice for this visit only */ }
    setStored({ key: storageKey, value });
  };
  return {
    all, visible, shown: all.filter((c) => visible.includes(c.key)),
    toggle: (key: string) => save(visible.includes(key) ? visible.filter((k) => k !== key) : [...visible, key]),
    reset: () => save(null),
  };
}

function ColumnChooser({ all, visible, onToggle, onReset }: {
  all: ListColumn[]; visible: string[]; onToggle: (key: string) => void; onReset: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <Button variant="outline" size="sm" onClick={() => setOpen((x) => !x)} aria-expanded={open} data-testid="b360-columns">
        <Columns3 aria-hidden /> Columns
      </Button>
      {open ? (
        <div role="dialog" aria-label="Columns" data-testid="b360-columns-panel"
             className="absolute right-0 top-9 z-30 w-60 rounded-lg border border-border bg-surface-raised p-3 shadow-lg">
          <ul className="max-h-80 space-y-1 overflow-y-auto">
            {all.map((c) => (
              <li key={c.key}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-[12px] text-text-primary hover:bg-surface-hover">
                  <input type="checkbox" checked={visible.includes(c.key)} disabled={c.key === "id"}
                         onChange={() => onToggle(c.key)} data-testid={`b360-column-toggle-${c.key}`} />
                  {c.label}
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-2 border-t border-border pt-2">
            <Button variant="ghost" size="sm" onClick={onReset} data-testid="b360-columns-reset">Default columns</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
