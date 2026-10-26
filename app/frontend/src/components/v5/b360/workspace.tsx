"use client";

/**
 * v5 Borrower 360 (module 2): one customer, everything the v5 books know.
 *
 * Without a customer the page is the book list (PLAN_R4 B2, ./list.tsx): every
 * borrower or customer, paged, sorted, searched and filtered by the service.
 * With one, a header and a tab bar (from the 5318 build's Borrower 360), with
 * Corporate and Retail as a selector on one screen (repair-t's Guided Workspace). The data is v5's own: the corporate and retail
 * books, the Early Warning releases and the synthetic Bureau and Open Banking
 * domains, served by the Borrower 360 service (backend/b360, port 8502).
 *
 * The book, the customer, the period, the tab and the list's state live in the
 * address, so the browser's Back walks tabs one step at a time and back to the
 * same list, and a link from Early Warning (?domain=&customer_id=&period=)
 * opens that exact customer and period.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { FileSpreadsheet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { ShareCurrent } from "@/components/v5/mail/share";
import { AddCurrentToReport } from "@/components/v5/playbook/add-current";
import { PanelActions } from "@/components/v5/thread/panel-actions";
import { b360Sources } from "@/lib/v5/thread-actions";
import { cn } from "@/lib/utils";
import {
  type Customer, type DomainId, type Tab, b360, excelHref, useB360,
} from "@/lib/v5/b360";
import { type ListState, listEntries, readList } from "@/lib/v5/b360-list";
import { asOfLabel, count, sar } from "@/lib/v5/ews";

import { TabChart } from "./charts";
import { ClassificationPanel, TopCards } from "./intel";
import { BookList } from "./list";
import { RelationshipsTab } from "./relationships";
import { NetworkToolsMenu } from "@/components/v5/intel/network";
import { DataTable, EwsBand, Summary } from "./table";
import { CockpitAskBar } from "@/components/v5/landing/module-landing";
import { MonitoringLine } from "@/components/v5/dealdesk/flow-monitoring"; // R14 F (K35)

const KEYS = ["domain", "customer_id", "period", "tab"] as const;
type State = Record<(typeof KEYS)[number], string>;

export function Borrower360Workspace() {
  const query = useSearchParams();
  const state = React.useMemo<State>(() => ({
    domain: query.get("domain") === "retail" ? "retail" : "corporate",
    customer_id: query.get("customer_id") ?? query.get("borrower") ?? query.get("customer") ?? "",
    period: query.get("period") ?? "",
    tab: query.get("tab") ?? "",
  }), [query]);
  const list = React.useMemo(() => readList(query), [query]);
  const domain = state.domain as DomainId;

  /** Write the view to the address. The list's keys ride along, so a customer opened from the list and Back keep it. */
  const go = React.useCallback((next: Partial<State>, nextList: ListState | null, replace = false) => {
    const params = new URLSearchParams();
    for (const k of KEYS) if (next[k]) params.set(k, next[k] as string);
    if (nextList) for (const [k, v] of listEntries(nextList)) params.set(k, v);
    const search = params.toString();
    if (search === new URLSearchParams(window.location.search).toString()) return;
    const url = search ? `?${search}` : window.location.pathname;
    if (replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
  }, []);
  const push = React.useCallback((next: Partial<State>) => go(next, list), [go, list]);

  const openCustomer = React.useCallback((id: string, period: string, tab = "") =>
    push({ domain, customer_id: id, period, tab }), [push, domain]);

  return (
    <div className="space-y-4" data-testid="b360-workspace">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <h1 className="text-2xl font-semibold text-text-primary">Borrower 360</h1>
        </div>
        <BookToggle domain={domain} onChange={(d) => go({ domain: d }, null)} />
        {state.customer_id ? <Context domain={domain} id={state.customer_id} period={state.period} /> : null}
      </div>

      {state.customer_id ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
          {/* R7: Back is the exact previous screen (Early Warning, Workspace, What-If, a lens…); the list is its own link. */}
          <BackButton fallback={{ href: `/borrower-360?domain=${domain}`, label: domain === "corporate" ? "All borrowers" : "All customers" }}
                      testId="b360-back" />
          <Button variant="ghost" size="sm" data-testid="b360-back-to-list"
                  onClick={() => push({ domain, period: state.period })}>
            {domain === "corporate" ? "All borrowers" : "All customers"}
          </Button>
          {domain === "corporate" ? (
            <NetworkToolsMenu module="b360" borrowerId={state.customer_id} period={state.period || undefined} className="ml-auto"
                              onOpenBorrower={(id) => openCustomer(id, state.period, "profile")} />) : null}
          </div>
          <CustomerView key={`${domain}|${state.customer_id}`} domain={domain} id={state.customer_id}
                        period={state.period} tab={state.tab}
                        onTab={(t) => push({ ...state, tab: t })}
                        onPeriod={(p) => push({ ...state, period: p })}
                        onOpen={(id, period) => openCustomer(id, period, "profile")}
                        onOpenAny={(id, d, period, tab) => go({ domain: d, customer_id: id, period, tab }, d === domain ? list : null)} />
        </>
      ) : (
        <>
        {/* R13 X (J7): table-first module; the ask box is one line above the table. */}
        <CockpitAskBar ids="b360" placeholder={domain === "corporate" ? "Ask about a borrower or the book: “who is drawing more?”"
          : "Ask about a customer or the book: “who missed a payment?”"} />
        <TopCards domain={domain} period={state.period} active={list.filters.card}
                  onPick={(card) => go({ domain, period: state.period }, { ...list, filters: { ...list.filters, card }, page: 1 })} />
        <BookList domain={domain} period={state.period} list={list}
                  onChange={(next, replace) => go({ domain, period: state.period }, next, replace)}
                  onPeriod={(p) => go({ domain, period: p }, { ...list, page: 1 })}
                  onOpen={(id, period) => openCustomer(id, period)} />
        </>
      )}
    </div>
  );
}

/** What the page was handed: book, customer and period (testids kept from the landing page). */
function Context({ domain, id, period }: { domain: DomainId; id: string; period: string }) {
  return (
    <dl className="ml-auto flex flex-wrap gap-x-5 gap-y-1 text-[12px]" data-testid="b360-context">
      <div><dt className="text-[9px] uppercase tracking-[0.08em] text-text-muted">Book</dt>
        <dd data-testid="b360-domain">{domain}</dd></div>
      <div><dt className="text-[9px] uppercase tracking-[0.08em] text-text-muted">{domain === "corporate" ? "Borrower" : "Customer"}</dt>
        <dd className="font-mono" data-testid="b360-id">{id || "—"}</dd></div>
      <div><dt className="text-[9px] uppercase tracking-[0.08em] text-text-muted">Period</dt>
        <dd data-testid="b360-period">{period || "latest"}</dd></div>
    </dl>
  );
}

function BookToggle({ domain, onChange }: { domain: DomainId; onChange: (d: DomainId) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Book" data-testid="b360-book-toggle">
      {(["corporate", "retail"] as const).map((d) => (
        <button key={d} type="button" role="tab" aria-selected={domain === d} onClick={() => onChange(d)}
                data-testid={`b360-book-${d}`}
                className={cn("rounded px-3 py-1 text-[13px] font-medium transition-colors",
                              domain === d ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
          {d === "corporate" ? "Corporate" : "Retail"}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- one customer

function CustomerView({ domain, id, period, tab, onTab, onPeriod, onOpen, onOpenAny }: {
  domain: DomainId; id: string; period: string; tab: string;
  onTab: (t: string) => void; onPeriod: (p: string) => void; onOpen: (id: string, period: string) => void;
  /** Open any borrower or customer, in either book, on a given tab (a click in the relationship graph). */
  onOpenAny: (id: string, domain: DomainId, period: string, tab: string) => void;
}) {
  const { data, error, loading } = useB360<Customer>(() => b360.customer(domain, id, period), `${domain}|${id}|${period}`);
  if (error) {
    return (
      <Card className="border-negative/40 p-4" data-testid="b360-error">
        <p className="text-sm font-semibold text-text-primary">This {domain === "corporate" ? "borrower" : "customer"} could not be opened.</p>
        <p className="mt-1 text-[13px] text-negative">{error}</p>
      </Card>
    );
  }
  if (loading || !data) return <Skeleton className="h-72 w-full" data-testid="b360-loading" />;
  const p = data.profile;
  const active = data.tabs[tab] ? tab : "profile";
  const t = data.tabs[active];
  const corporate = domain === "corporate";
  return (
    <div className="space-y-3" data-testid="b360-customer" data-customer={p.customer_id} data-period={p.period}>
      <Card className="p-4" data-testid="b360-header">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-text-primary" data-testid="b360-name">{p.name ?? p.customer_id}</h2>
              {p.name ? <span className="font-mono text-[12px] text-text-muted">{p.customer_id}</span> : null}
              <span className="rounded border border-border px-1.5 py-0.5 text-[11px]" data-testid="b360-rating"
                    title={corporate ? "Rating on the global scale AAA (best) to D (worst)" : "Behaviour band, A (best) to E (worst)"}>
                {p.rating_label} <b>{p.rating ?? "—"}</b>
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] text-text-secondary">
                Early Warning <EwsBand band={p.ews_band} testId="b360-ews-band" /> score {p.ews_score ?? 0}
              </span>
              {p.watchlist ? <span className="rounded bg-warning-muted px-1.5 py-0.5 text-[10px] text-warning">Watchlist</span> : null}
            </div>
            <p className="mt-1 text-[13px] text-text-secondary" data-testid="b360-exposure">
              {sar(p.exposure)} exposure (EAD) across {count(p.facilities)} {p.facilities === 1 ? p.labels.exposure : p.labels.exposures}
              {" · "}ECL {sar(p.ecl)}{p.segment ? ` · ${p.segment}` : ""}{p.subsegment ? ` · ${p.subsegment}` : ""}
              {corporate && p.group_id ? ` · group ${p.group_id} (${p.group_name})` : ""}
            </p>
            {corporate ? <MonitoringLine obligorId={p.customer_id} className="mt-1.5" /> /* R14 F (K35): proposed for or under Deal Desk monitoring */ : null}
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-text-muted" data-testid="b360-as-of">
              <span><span className="font-semibold uppercase tracking-[0.08em] text-text-secondary">As of</span>{" "}
                {asOfLabel(p.period)} · {corporate ? "Corporate · quarterly" : "Retail · monthly"} · SAR</span>
              <InfoPopover title="Sources">
                <p>Book <span className="font-mono">{p.releases.book}</span></p>
                <p>Early Warning <span className="font-mono">{p.releases.ews}</span> ({p.ews_ruleset})</p>
                <p>Bureau <span className="font-mono">{p.releases.bureau}</span> · Open Banking <span className="font-mono">{p.releases.open_banking}</span></p>
              </InfoPopover>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label className="text-[10px] uppercase tracking-[0.08em] text-text-muted">
              {corporate ? "Quarter" : "Month"}
              <select value={p.period} onChange={(e) => onPeriod(e.target.value)} data-testid="b360-period-select"
                      className="mt-0.5 block rounded border border-border bg-surface px-2 py-1 text-[13px] normal-case tracking-normal text-text-primary">
                {[...p.periods].reverse().map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </label>
            <Link href={data.links.early_warning} data-testid="b360-back-to-ews"
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-hover">
              Open in Early Warning
            </Link>
            <ShareCurrent type="borrower" testId="b360-share" id={p.customer_id}
                          label={`${p.customer_id}${p.name ? ` ${p.name}` : ""} (Borrower 360, ${p.period})`}
                          summary={`${sar(p.exposure)} exposure, ECL ${sar(p.ecl)}; Early Warning ${p.ews_band ?? "n/a"} (score ${p.ews_score ?? 0}).`}
                          meta={{ domain, period: p.period }} />
            <AddCurrentToReport type="borrower" id={p.customer_id} testId="b360-add-report" defaultTemplate="borrower-credit-memo"
                                label={`Borrower 360: ${p.name ? `${p.name} ` : ""}(${p.customer_id})`} />
            {/* R16 t (M7): Trace and Word on this borrower's view (Share and Add to report are beside it) */}
            <PanelActions module="b360" id={p.customer_id} title={`Borrower 360: ${p.name ? `${p.name} ` : ""}(${p.customer_id}), ${p.period}`}
                          container='[data-testid="b360-workspace"]' share={false} report={false} testId="b360-actions" sources={b360Sources(p.customer_id)} />
            <a href={excelHref(domain, p.customer_id, p.period)} download data-testid="b360-excel-all"
               className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-hover">
              <FileSpreadsheet className="size-3.5" aria-hidden /> Export all tabs
            </a>
          </div>
        </div>
      </Card>

      <ClassificationPanel domain={domain} id={p.customer_id} period={p.period} />

      <nav className="flex flex-wrap gap-0.5 border-b border-border" aria-label="Borrower 360 sections" data-testid="b360-tabs">
        {data.tab_list.map((x) => (
          <button key={x.key} type="button" onClick={() => onTab(x.key)} data-testid={`b360-tab-${x.key}`}
                  aria-current={x.key === active ? "page" : undefined}
                  className={cn("-mb-px border-b-2 px-2.5 py-1.5 text-[13px] transition-colors",
                                x.key === active ? "border-accent font-medium text-accent"
                                                 : "border-transparent text-text-secondary hover:text-text-primary")}>
            {x.label}
          </button>
        ))}
      </nav>

      <TabPanel key={t.key} domain={domain} id={p.customer_id} tab={t} selfId={p.customer_id}
                onOpen={(other) => onOpen(other, p.period)}
                onOpenAny={(other, d, per) => onOpenAny(other, d ?? domain, per ?? p.period, "relationships")} />
    </div>
  );
}

function TabPanel({ domain, id, tab, selfId, onOpen, onOpenAny }: {
  domain: DomainId; id: string; tab: Tab; selfId: string; onOpen: (id: string) => void;
  onOpenAny: (id: string, domain?: DomainId, period?: string) => void;
}) {
  return (
    <Card className="space-y-4 p-4" data-testid={`b360-panel-${tab.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold text-text-primary">{tab.label}</h3>
        <span className="text-[11px] text-text-muted">at {tab.period}</span>
        {tab.note ? (
          <span data-testid={`b360-note-${tab.key}`}><InfoPopover title={tab.label}><p>{tab.note}</p></InfoPopover></span>
        ) : null}
        <a href={excelHref(domain, id, tab.period, tab.key)} download data-testid={`b360-excel-${tab.key}`}
           title="Download this tab as an Excel workbook"
           className="ml-auto inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-hover">
          <FileSpreadsheet className="size-3.5" aria-hidden /> Export to Excel
        </a>
      </div>
      <Summary figures={tab.summary} testId={`b360-summary-${tab.key}`} />
      {tab.key === "relationships" && tab.graph ? (
        <RelationshipsTab domain={domain} id={id} tab={tab} onOpen={(nid, d, p) => onOpenAny(nid, d, p)} />
      ) : <TabChart domain={domain} tab={tab} />}
      {tab.tables.map((tb) => (
        <DataTable key={tb.id} table={tb} testId={`b360-table-${tab.key}-${tb.id}`}
                   onOpenId={tab.key === "group" && tb.id === "members" ? onOpen : undefined}
                   highlight={tab.key === "group" ? (r) => r.borrower_id === selfId : undefined} />
      ))}
    </Card>
  );
}
