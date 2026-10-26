"use client";

/**
 * v5 Data Builder · Browse the data.
 *
 * Every v5 data domain -- the Cockpit books, Early Warning, Bureau, Open
 * Banking, and the domains still to come -- on the Data Builder service's own
 * read-only backend. Left: the domains and their relations. Right: the chosen
 * relation's rows (search, filters, columns, period and comparison, paging,
 * sort, export) or its data dictionary. The view lives in the address.
 */

import * as React from "react";
import { ChevronRight, LayoutGrid } from "lucide-react";

import { useWideContent } from "@/components/layout/content-width";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  BOOK_LABEL, type DomainInfo, type Query, type RelationInfo, count, dataApi, exportHref, useData,
} from "@/lib/v5/data-builder";

import {
  ColumnChooser, CompareSelect, DensityToggle, ExportLinks, FilterBar, PageSize, PeriodSelect, SearchBox,
} from "./controls";
import { Dictionary, Grid } from "./grid";
import { DomainList, DomainPanel, sortDomains } from "./parts";
import { PAGE_SIZES, type ViewState, ViewLink, useViewState } from "./state";

export interface OverviewProps { domains: DomainInfo[]; view: "comfortable" | "compact" }

/** PLAN_R10 S4: `?domain=overview` shows the summary of every domain; with no domain chosen, the first dataset opens. */
export const OVERVIEW = "overview";

export function DataBuilderWorkspace({ overview }: { overview: (props: OverviewProps) => React.ReactNode }) {
  // Two panes need the width of the content column.
  useWideContent();
  const { state: asked, go, replace } = useViewState();
  const domains = useData(() => dataApi.domains(), "domains");
  // Only the domains that hold data: a placeholder for a module that has not published tables is not shown (PLAN_R4 G1).
  const list = sortDomains((domains.data?.domains ?? []).filter((d) => d.status === "live"));
  // PLAN_R10 S4: no scrolling to reach the data. With nothing chosen, the first domain's first dataset is open.
  const first = list[0];
  const state: ViewState = !asked.domain && first?.relations[0]
    ? { ...asked, domain: first.domain, relation: first.relations[0].relation }
    : asked;
  const showOverview = state.domain === OVERVIEW;
  const domain = list.find((d) => d.domain === state.domain) ?? null;
  const relation = domain?.relations.find((r) => r.relation === state.relation) ?? null;

  return (
    <div className="flex flex-col gap-3 md:h-[calc(100dvh-8.5rem)] md:min-h-[520px]" data-testid="db-workspace">
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-1">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Data</p>
          <h1 className="text-xl font-semibold text-text-primary">Data Domains</h1>
        </div>
        <Crumbs domain={domain} relation={relation} view={state.view} />
      </header>

      {domains.error && !domains.data ? (
        <Card className="space-y-2 border-negative/30 p-5" data-testid="db-error">
          <p className="text-sm font-semibold text-negative">The Data Domains service did not answer.</p>
          <p className="text-sm text-text-secondary">{domains.error}</p>
        </Card>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[250px_minmax(0,1fr)]" data-testid="db-panes">
        {/* Left: the tree of domains → datasets, scrolling inside its own pane. */}
        <aside className="min-h-0 overflow-y-auto rounded-lg border border-border bg-surface p-2 max-md:max-h-72" data-testid="db-tree">
          {domains.data ? (
            <>
              <ViewLink to={{ domain: OVERVIEW, view: state.view }} testId="db-tree-overview"
                        className={cn("mb-2 flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px]",
                                      showOverview ? "bg-accent-muted font-medium text-accent" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary")}>
                <LayoutGrid className="size-3.5" aria-hidden /> Overview of all domains
              </ViewLink>
              <DomainList domains={list} domain={state.domain} relation={state.relation} view={state.view} />
            </>
          ) : domains.loading ? <Skeleton className="h-80 w-full" /> : null}
        </aside>
        {/* Right: the selected dataset — fields, row count and its data grid, filling the pane. */}
        <main className={cn("min-h-0 min-w-0", relation && !showOverview ? "flex flex-col" : "overflow-y-auto")} data-testid="db-main">
          {!domains.data ? (domains.loading ? <Skeleton className="h-96 w-full" /> : null)
            : showOverview ? overview({ domains: list, view: state.view })
            : relation && domain ? (
              <RelationView key={`${domain.domain}/${relation.relation}`} domain={domain} relation={relation}
                            state={state} go={go} replace={replace} />
            ) : domain ? (
              <>
                {state.relation ? <Unknown what={`relation “${state.relation}”`} domain={domain.domain} view={state.view} /> : null}
                <DomainPanel domain={domain} view={state.view} />
              </>
            ) : state.domain ? (
              <Unknown what={`domain “${state.domain}”`} view={state.view} />
            ) : overview({ domains: list, view: state.view })}
        </main>
      </div>
    </div>
  );
}

function Crumbs({ domain, relation, view }: { domain: DomainInfo | null; relation: RelationInfo | null; view: ViewState["view"] }) {
  if (!domain) return null;
  return (
    <nav className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-text-muted" aria-label="Breadcrumb" data-testid="db-crumbs">
      <ViewLink to={{ domain: OVERVIEW, view }} testId="db-crumb-home" className="hover:text-text-primary hover:underline">All domains</ViewLink>
      <ChevronRight className="size-3" aria-hidden />
      {relation ? (
        <>
          <ViewLink to={{ domain: domain.domain, view }} testId="db-crumb-domain" className="hover:text-text-primary hover:underline">
            {domain.label}
          </ViewLink>
          <ChevronRight className="size-3" aria-hidden />
          <span className="text-text-secondary">{relation.label}</span>
        </>
      ) : <span className="text-text-secondary">{domain.label}</span>}
    </nav>
  );
}

function Unknown({ what, domain, view }: { what: string; domain?: string; view: ViewState["view"] }) {
  return (
    <Card className="mb-3 p-4 text-sm text-text-secondary" data-testid="db-unknown">
      There is no {what} in Data Domains.{" "}
      <ViewLink to={domain ? { domain, view } : { domain: OVERVIEW, view }} className="text-accent hover:underline">
        {domain ? "Show this domain" : "Show every domain"}
      </ViewLink>
    </Card>
  );
}

// ---------------------------------------------------------------- one relation

/** Release bookkeeping columns, the same on every row: hidden until chosen in Columns (PLAN_R10 S4, G-MINIMAL). */
export const SYSTEM_COLUMNS = new Set(["tenant_id", "dataset_release_id", "domain_id", "release_id", "reporting_currency"]);

/** The default columns of the grid: every column but the release bookkeeping; [] (all) when that would leave none. */
export function businessColumns(columns: { name: string }[]): string[] {
  const keep = columns.map((c) => c.name).filter((n) => !SYSTEM_COLUMNS.has(n));
  return keep.length && keep.length < columns.length ? keep : [];
}

function RelationView({ domain, relation, state, go, replace }: {
  domain: DomainInfo; relation: RelationInfo; state: ViewState;
  go: (patch: Partial<ViewState>) => void; replace: (patch: Partial<ViewState>) => void;
}) {
  const schema = useData(() => dataApi.schema(domain.domain, relation.relation), `${domain.domain}/${relation.relation}`);
  const columns = schema.data?.columns ?? [];

  const period = state.period === "all" ? "" : state.period || relation.latest_period || "";
  const compare = period && state.compare && state.compare !== period ? state.compare : "";
  const query: Query = {
    period: period || undefined, compare: compare || undefined, search: state.q || undefined,
    filters: state.filters, columns: state.cols.length ? state.cols : businessColumns(columns), sort: state.sort || undefined, desc: state.desc,
  };
  const offset = (state.page - 1) * state.size;
  const rowsKey = JSON.stringify([domain.domain, relation.relation, query, state.size, offset]);
  const rows = useData(() => dataApi.rows(domain.domain, relation.relation, query, state.size, offset),
                       state.tab === "rows" && (schema.data || schema.error) ? rowsKey : null);
  const total = rows.data?.total ?? null;
  const shownColumns = rows.data?.columns ?? [];

  /** A change to which rows match: back to page one. */
  const refine = (patch: Partial<ViewState>) => go({ ...patch, page: 1 });
  const sortBy = (name: string) => go({ sort: name, desc: state.sort === name ? !state.desc : false, page: 1 });
  const setCompare = (next: string) =>
    refine({ compare: next, sort: state.sort.includes("__") ? "" : state.sort, desc: state.sort.includes("__") ? false : state.desc });
  const setPeriod = (next: string) => refine({
    period: next === relation.latest_period ? "" : next,
    compare: next === "all" || next === compare ? "" : state.compare,
    sort: next === "all" && state.sort.includes("__") ? "" : state.sort,
  });
  const setColumns = (cols: string[]) => {
    // Without a comparison any column may sort; with one, only a column still shown (or a key).
    const base = state.sort.split("__")[0];
    const keep = !state.sort || !compare || !cols.length || cols.includes(base) || relation.key_columns.includes(base);
    go({ cols, sort: keep ? state.sort : "", desc: keep ? state.desc : false });
  };

  const lastPage = total !== null ? Math.max(1, Math.ceil(total / state.size)) : null;
  const from = total ? offset + 1 : 0;
  const to = total !== null ? Math.min(offset + state.size, total) : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2" data-testid="db-relation">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-text-primary" title={relation.description || undefined}>
            {relation.label}
            <span className="ml-2 text-[11px] font-normal text-text-muted">{domain.label} · {BOOK_LABEL[relation.book] ?? relation.book}</span>
          </h2>
          <p className="truncate text-[11px] text-text-muted" data-testid="db-relation-meta">
            <b className="font-semibold text-text-secondary">{count(relation.rows)} rows</b> · {columns.length || relation.columns} fields · {relation.periods.length} periods
            {relation.grain ? ` · ${relation.grain}` : ""} · <span className="font-mono">{relation.relation}</span>
          </p>
        </div>
        <div role="tablist" aria-label="Data or fields" className="flex rounded-md border border-border bg-surface-sunken p-0.5">
          {(["rows", "dictionary"] as const).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={state.tab === t}
                    data-testid={t === "rows" ? "db-tab-rows" : "db-dictionary"}
                    onClick={() => state.tab !== t && go({ tab: t })}
                    className={cn("rounded px-3 py-1 text-xs font-medium",
                                  state.tab === t ? "bg-surface text-text-primary shadow-sm" : "text-text-muted hover:text-text-primary")}>
              {t === "rows" ? "Data" : `Fields${columns.length ? ` (${columns.length})` : ""}`}
            </button>
          ))}
        </div>
      </div>

      {schema.error ? <p className="text-sm text-negative" data-testid="db-schema-error">{schema.error}</p> : null}

      {state.tab === "dictionary" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {schema.data ? (
            <Dictionary columns={columns} keyColumns={schema.data.key_columns} periodColumn={schema.data.period_column} />
          ) : <Skeleton className="h-64 w-full" />}
        </div>
      ) : (
        <>
          <div className="shrink-0 space-y-2">
            <div className="flex flex-wrap items-end gap-2">
              <SearchBox value={state.q} onCommit={(q) => refine({ q })} />
              <PeriodSelect periods={relation.periods} period={state.period} latest={relation.latest_period} onChange={setPeriod} />
              <CompareSelect periods={relation.periods} period={state.period === "all" ? "all" : period}
                             compare={compare} onChange={setCompare} />
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <ColumnChooser columns={columns} chosen={state.cols.length ? state.cols : businessColumns(columns)} onApply={setColumns} />
                <DensityToggle view={state.view} onChange={(view) => replace({ view })} />
                <ExportLinks total={total}
                             csv={exportHref(domain.domain, relation.relation, query, "csv")}
                             xlsx={exportHref(domain.domain, relation.relation, query, "xlsx")} />
              </div>
            </div>
            <FilterBar columns={columns} filters={state.filters} onChange={(filters) => refine({ filters })} />
          </div>

          {rows.error ? (
            <Card className="shrink-0 border-negative/30 p-3 text-sm text-negative" data-testid="db-rows-error">{rows.error}</Card>
          ) : null}

          {rows.data ? (
            <Grid columns={shownColumns} rows={rows.data.rows} sort={state.sort} desc={state.desc}
                  compact={state.view === "compact"} stale={rows.stale} onSort={sortBy}
                  className="min-h-[240px] flex-1 md:min-h-0" />
          ) : rows.loading ? <Skeleton className="min-h-[240px] w-full flex-1" /> : null}

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
            <p title={`Read-only from release ${relation.release_id}. Exports carry every matching row (Excel up to 200,000, with an About sheet and the dictionary).`}>
              <span className="font-semibold text-text-primary" data-testid="db-total">
                {total === null ? "…" : `${count(total)} rows`}
              </span>{" "}
              {period ? <>in {period}</> : <>across all periods</>}
              {compare ? <> · compared with {compare}</> : null}
              {state.q ? <> · matching “{state.q}”</> : null}
              {state.filters.length ? <> · {state.filters.length} filter{state.filters.length > 1 ? "s" : ""}</> : null}
              {rows.data?.compare_basis ? <span className="ml-1" data-testid="db-compare-basis">· {rows.data.compare_basis}</span> : null}
              <span className="ml-2" data-testid="db-page-info">
                {total ? `· rows ${count(from)}–${count(to)} · page ${state.page} of ${count(lastPage)}` : ""}
              </span>
            </p>
            <div className="flex items-center gap-2">
              <PageSize size={state.size} sizes={PAGE_SIZES} onChange={(size) => go({ size, page: 1 })} />
              <Button variant="outline" size="sm" disabled={state.page <= 1} onClick={() => go({ page: state.page - 1 })}
                      data-testid="db-page-prev">Previous</Button>
              <Button variant="outline" size="sm" disabled={lastPage === null || state.page >= lastPage}
                      onClick={() => go({ page: state.page + 1 })} data-testid="db-page-next">Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
