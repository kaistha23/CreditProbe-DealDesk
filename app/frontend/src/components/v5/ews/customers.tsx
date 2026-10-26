"use client";

/**
 * The customer list at any level: who is warned, why, and how they moved.
 *
 * Layout ported from the Retail Demo's customer list and card (c0db151f,
 * app/early-warning/workspace.tsx CustomerList, customer-card.tsx): cohort
 * pills, filters, one card per customer with three sparklines. Rows come from
 * the Early Warning service; nothing is computed here.
 */

import * as React from "react";

import { Borrower360Button, BorrowerNameLink } from "@/components/v5/ui/borrower-360-link"; // R14 U (K11)
import { ProposeMonitoringButton } from "@/components/v5/dealdesk/flow-monitoring"; // R14 F (K35)
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type CustomerRow, type Customers, type DomainId, type ExcelParams, count, ews, pct, sar, useEws,
} from "@/lib/v5/ews";

import { ShareCurrent } from "@/components/v5/mail/share";
import { compareRatings } from "@/lib/v5/ratings";

import { ActiveFilters, Band, ExcelLink, ExportToWhatIf, Figure } from "./parts";
import { Spark } from "./spark";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { customerHistoryExplain } from "./explain";
import { VerdictChip, useTriageVerdicts } from "./agent-triage";
import type { Verdict } from "./agent-verdict-core";

export interface ListFilters {
  cohort: string; reason: string; layer: string; dpd: string; stage: string; band: string; q: string;
}

const PAGE = 25;

export function CustomerList({ domain, period, segment, classification, subsegment, filters,
                               scopeLabel, onFilters, onOpen, onBack, onUp, dims }: {
  domain: DomainId; period: string; segment: string; classification: string; subsegment: string;
  filters: ListFilters; scopeLabel: string;
  /** The level drill filter (PLAN_R4 B4), e.g. {region, branch, sector}; carried to the list, Excel and What-If. */
  dims?: Record<string, string | undefined>;
  onFilters: (next: Partial<ListFilters>) => void; onOpen: (id: string) => void; onBack: () => void; onUp?: () => void;
}) {
  const [search, setSearch] = React.useState(filters.q);
  const view = {
    domain, period, segment, classification, subsegment, cohort: filters.cohort || "warned",
    reason: filters.reason, layer: filters.layer, dpd: filters.dpd, stage: filters.stage,
    band_min: filters.band, search: filters.q, limit: PAGE,
    ...(dims && Object.keys(dims).length ? { dims: JSON.stringify(dims) } : {}),
  };
  const viewKey = JSON.stringify(view);
  // The page number belongs to the view it was chosen in: a new filter starts at page one.
  const [paging, setPaging] = React.useState({ view: viewKey, page: 0 });
  const page = paging.view === viewKey ? paging.page : 0;
  const setPage = (next: (p: number) => number) => setPaging({ view: viewKey, page: next(page) });
  const query = { ...view, offset: page * PAGE };
  const key = JSON.stringify(query);
  const { data, error, loading } = useEws<Customers>(() => ews.customers(query), key);
  const { verdicts } = useTriageVerdicts(domain, data?.period ?? period);

  const chips: { label: string; onClear?: () => void }[] = [{ label: scopeLabel }];
  if (filters.reason) chips.push({ label: `Reason: ${filters.reason}`, onClear: () => onFilters({ reason: "" }) });
  if (filters.layer) chips.push({ label: `Layer: ${data?.layer_labels[filters.layer] ?? filters.layer}`, onClear: () => onFilters({ layer: "" }) });
  if (filters.dpd) chips.push({ label: `DPD ${filters.dpd}`, onClear: () => onFilters({ dpd: "" }) });
  if (filters.stage) chips.push({ label: `Stage ${filters.stage}`, onClear: () => onFilters({ stage: "" }) });
  if (filters.band) chips.push({ label: `Band ≥ ${filters.band}`, onClear: () => onFilters({ band: "" }) });
  if (filters.q) chips.push({ label: `Search: ${filters.q}`, onClear: () => { setSearch(""); onFilters({ q: "" }); } });

  const owners = data?.labels.owners ?? "customers";
  return (
    <div className="space-y-4" data-testid="ews-customer-list">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={onBack} data-testid="ews-list-back">
          <ArrowLeft className="mr-1 size-3.5" aria-hidden /> Back
        </Button>
        {/* R7: Back is the exact previous step (a filter you changed included); Up leaves the list for its level. */}
        {onUp ? <Button variant="outline" size="sm" onClick={onUp} data-testid="ews-list-up">Up</Button> : null}
        <ActiveFilters chips={chips} />
        <span className="ml-auto flex flex-wrap items-start gap-2">
          <ExcelLink testId="ews-excel-list"
                     params={{ domain, period: data?.period ?? period, segment, classification, subsegment,
                               cohort: filters.cohort || "warned", reason: filters.reason, layer: filters.layer,
                               dpd: filters.dpd, stage: filters.stage, band_min: filters.band, search: filters.q,
                               ...(view.dims ? { dims: view.dims } : {}) } as ExcelParams} />
          <ShareCurrent type="early-warning-list" testId="ews-share-list" id={`${domain}|${data?.period ?? period}|${scopeLabel}|${filters.cohort || "warned"}`}
                        label={`Early Warning list: ${scopeLabel}, ${data?.period ?? period}`}
                        summary={data ? `${count(data.total)} ${owners} on the list.` : undefined}
                        meta={{ domain, period: data?.period ?? period }} />
          <ExportToWhatIf testId="ews-export-list"
                          label={data ? `Export ${count(data.total)} ${owners} to What-If` : "Export to What-If"}
                          body={{ domain, period, segment, classification, subsegment,
                                  cohort: filters.cohort || "warned", reason: filters.reason, layer: filters.layer,
                                  dpd: filters.dpd, stage: filters.stage ? Number(filters.stage) : undefined,
                                  band_min: filters.band, search: filters.q,
                                  ...(dims && Object.keys(dims).length ? { dims } : {}) }} />
        </span>
      </div>

      {data ? (
        <div className="flex flex-wrap gap-1.5" data-testid="ews-cohorts">
          {data.cohorts.map((c) => (
            <button key={c.key} type="button" onClick={() => onFilters({ cohort: c.key })}
                    data-testid={`ews-cohort-${c.key}`}
                    className={cn("rounded-full border px-3 py-1 text-[12px] transition-colors",
                                  (filters.cohort || "warned") === c.key
                                    ? "border-accent bg-accent text-accent-contrast" : "border-border text-text-secondary hover:bg-surface-muted")}>
              {c.label} <span className="tabular-nums opacity-80">{count(c.customers)}</span>
            </button>
          ))}
        </div>
      ) : null}

      {data ? (
        <Card className="flex flex-wrap items-end gap-3 p-3" data-testid="ews-list-filters">
          <Select label="Layer" value={filters.layer} onChange={(v) => onFilters({ layer: v })}
                  options={data.layers.map((l) => ({ value: l, label: data.layer_labels[l] ?? l }))} />
          <Select label="Days past due" value={filters.dpd} onChange={(v) => onFilters({ dpd: v })}
                  options={data.dpd_buckets.map((b) => ({ value: b.key, label: b.label }))} />
          <Select label="Stage" value={filters.stage} onChange={(v) => onFilters({ stage: v })}
                  options={["1", "2", "3"].map((s) => ({ value: s, label: `Stage ${s}` }))} />
          <Select label="Minimum band" value={filters.band} onChange={(v) => onFilters({ band: v })}
                  options={["moderate", "high", "critical"].map((b) => ({ value: b, label: b }))} />
          <Select label="Reason" value={filters.reason} onChange={(v) => onFilters({ reason: v })}
                  options={data.reasons.map((r) => ({ value: r, label: r }))} />
          <form className="flex items-end gap-1.5" onSubmit={(e) => { e.preventDefault(); onFilters({ q: search.trim() }); }}>
            <label className="text-[10px] uppercase tracking-[0.08em] text-text-muted">
              Search
              <input value={search} onChange={(e) => setSearch(e.target.value)} data-testid="ews-search"
                     placeholder={domain === "corporate" ? "CB… or name" : "RC…"}
                     className="mt-0.5 block w-40 rounded border border-border bg-surface px-2 py-1 text-[12px] normal-case tracking-normal text-text-primary" />
            </label>
          </form>
        </Card>
      ) : null}

      {error ? <p className="text-sm text-negative" data-testid="ews-list-error">{error}</p> : null}
      {loading && !data ? <Skeleton className="h-40 w-full" /> : null}

      {data ? (
        <>
          <p className="text-[12px] text-text-secondary" data-testid="ews-list-total">
            {count(data.total)} {owners} · {sar(data.total_exposure)} exposure · sorted by score, then exposure.
            {" "}{data.definitions.customer_score}
          </p>
          <div className="space-y-2">
            {data.customers.map((c) => (
              <CustomerCard key={c.customer_id} row={c} domain={domain} warnedMin={data.warned_min}
                            verdict={verdicts[c.customer_id]} period={data.period}
                            onOpen={() => onOpen(c.customer_id)} />
            ))}
          </div>
          {data.total > PAGE ? (
            <div className="flex items-center gap-2 text-[12px]" data-testid="ews-list-pager">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span className="tabular-nums text-text-secondary">
                {count(page * PAGE + 1)}–{count(Math.min(data.total, (page + 1) * PAGE))} of {count(data.total)}
              </span>
              <Button variant="outline" size="sm" disabled={(page + 1) * PAGE >= data.total}
                      onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          ) : null}
          {!data.customers.length ? <p className="text-sm text-text-muted">No {owners} match this view.</p> : null}
        </>
      ) : null}
    </div>
  );
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <label className="text-[10px] uppercase tracking-[0.08em] text-text-muted">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
              className="mt-0.5 block rounded border border-border bg-surface px-2 py-1 text-[12px] normal-case tracking-normal text-text-primary">
        <option value="">All</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function CustomerCard({ row, domain, warnedMin, onOpen, verdict, period = "" }: {
  row: CustomerRow; domain: DomainId; warnedMin: number; onOpen: () => void;
  /** R11 E4: the triage agent's verdict for this name (latest period run), when there is one. */
  verdict?: Verdict; period?: string;
}) {
  const corporate = domain === "corporate";
  return (
    <Card className="p-0" data-testid={`ews-customer-${row.customer_id}`}>
      {/* R10: a div with the button role, so the (i) button inside is not a button nested in a button (hydration error). */}
      <div role="button" tabIndex={0} onClick={onOpen}
           onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpen(); } }}
           className="w-full cursor-pointer p-3.5 text-left transition-colors hover:bg-surface-muted/50">
        <div className="flex flex-wrap items-center gap-2">
          {/* R14 U (K11): the name links to Borrower 360 too */}
          {corporate ? <BorrowerNameLink customerId={row.customer_id} name={row.customer_name} period={period} from="ews" className="font-semibold" />
            : <span className="font-semibold text-text-primary">{row.customer_name ?? row.customer_id}</span>}
          {row.customer_name ? <span className="font-mono text-[11px] text-text-muted">{row.customer_id}</span> : null}
          <Band band={row.band} />
          <span className="text-[11px] tabular-nums text-text-secondary">score {row.score}</span>
          {row.current_bad ? <span className="rounded bg-negative-muted px-1.5 py-0.5 text-[10px] text-negative">Already bad</span> : null}
          {row.forward_risk ? <span className="rounded bg-warning-muted px-1.5 py-0.5 text-[10px] text-warning">Forward risk</span> : null}
          <VerdictChip verdict={verdict} domain={domain} period={period} customerId={row.customer_id} />
          <span className="ml-auto text-[11px] text-text-muted">{row.subsegments}</span>
          {/* R14 U (K11): Borrower 360 on every borrower card, top-right beside the sector; Back returns to this list */}
          {corporate ? <Borrower360Button customerId={row.customer_id} period={period} from="ews" /> : null}
          {/* R14 F (K35): Propose for monitoring on every Early Warning card */}
          {corporate ? <ProposeMonitoringButton compact testId={`ews-monitor-${row.customer_id}`} subject={{ obligorId: row.customer_id,
            obligorName: row.customer_name ?? row.customer_id, source: "ews", reason: `EWS band ${String(row.band)}, score ${row.score}, worst DPD ${row.dpd}, stage ${row.stage}` }} /> : null}
        </div>
        <div className="mt-2 grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-6">
          <Figure label="Exposure" value={sar(row.exposure)} />
          <Figure label={corporate ? "Facilities" : "Accounts"} value={count(row.facilities)} />
          <Figure label="Worst DPD" value={count(row.dpd)} tone={row.dpd >= 30 ? "negative" : undefined} />
          <Figure label="Worst stage" value={row.stage} tone={row.stage === 3 ? "negative" : row.stage === 2 ? "warning" : undefined} />
          {corporate ? (
            <Figure label="Rating" value={`${String(row.rating_current ?? "—")}${row.rating_previous && row.rating_previous !== row.rating_current ? ` (was ${String(row.rating_previous)})` : ""}`}
                    tone={row.rating_previous && compareRatings(String(row.rating_current ?? ""), String(row.rating_previous)) > 0 ? "negative" : undefined} />
          ) : (
            <Figure label="Behaviour score" value={`${row.behaviour_score != null ? Math.round(Number(row.behaviour_score)) : "—"} · ${String(row.score_band ?? "—")}`} />
          )}
          <Figure label="Share of view" value={pct(row.share_of_scope_pct, 2)} />
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {row.reasons.map((r) => (
            <span key={r.key} className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary" title={r.layer_name}>
              <span className="font-mono text-text-muted">{r.key}</span> {r.name}
            </span>
          ))}
          {!row.reasons.length ? <span className="text-[10px] text-text-muted">No warning rule fired.</span> : null}
        </div>
        <div className="mt-2 flex justify-end" onClick={(e) => e.stopPropagation()}>
          <ChartInfo title="Score, days past due and exposure" align="right"
                     explain={customerHistoryExplain(row.series, warnedMin, corporate ? "borrower" : "customer")} />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Spark label="Score" tone="warning" bands={[{ value: warnedMin, label: "warning" }]}
                 points={row.series.map((p) => ({ period: p.period, value: p.score }))} />
          <Spark label="Days past due" tone="negative" bands={[{ value: 30, label: "30 DPD" }]}
                 points={row.series.map((p) => ({ period: p.period, value: p.dpd }))} />
          <Spark label="Exposure (SAR m)" tone="accent"
                 points={row.series.map((p) => ({ period: p.period, value: p.exposure }))} />
        </div>
        <p className="mt-1 text-[10px] text-text-muted">
          {corporate
            ? `${String(row.group_name ?? "")}${row.watchlist_flag ? " · on watchlist" : ""}`
            : `${String(row.customer_segment ?? "")} · ${String(row.employment_type ?? "")} · ${String(row.region ?? "")}`}
        </p>
      </div>
    </Card>
  );
}
