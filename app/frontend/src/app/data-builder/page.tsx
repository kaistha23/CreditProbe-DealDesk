"use client";

/**
 * v5 Data Builder · Browse the data.
 *
 * Every v5 data domain -- Cockpit books, Early Warning, Bureau, Open Banking,
 * and Borrower 360 / What-If when they arrive -- read-only, on the Data
 * Builder service (`NEXT_PUBLIC_DATA_API`, port 8504). The workspace keeps
 * the whole view in the address; this page adds the landing overview shown
 * before a domain is chosen: a summary strip, one tile per domain, and (on
 * request) the Cockpit's own catalogue of its two books.
 *
 * The page reads the address, so its client tree sits under a Suspense
 * boundary of its own.
 */

import * as React from "react";
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";

import { DataBooks } from "@/components/cockpit-v4/data-books";
import { Card } from "@/components/ui/card";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { DataBuilderWorkspace, type OverviewProps } from "@/components/v5/data-builder/workspace";
import { byBook, sortDomains } from "@/components/v5/data-builder/parts";
import { ViewLink } from "@/components/v5/data-builder/state";
import { BOOK_LABEL, type DomainInfo, count } from "@/lib/v5/data-builder";

export default function DataBuilderPage() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Data Domains…</p>}>
      <DataBuilderWorkspace overview={(props) => <Overview {...props} />} />
    </React.Suspense>
  );
}

function Overview({ domains, view }: OverviewProps) {
  const live = domains.filter((d) => d.status === "live");
  const relations = live.reduce((n, d) => n + d.relations.length, 0);
  const rows = live.reduce((n, d) => n + d.rows, 0);
  return (
    <div className="space-y-4" data-testid="db-overview" data-tour="data-home">
      <KpiRow testId="db-summary" tiles={[
        { label: "Data domains", value: count(live.length), sub: "published releases", testId: "db-sum-domains" },
        { label: "Datasets", value: count(relations), sub: "tables you can browse", testId: "db-sum-relations" },
        { label: "Rows", value: count(rows), sub: "all periods, all datasets", testId: "db-sum-rows" },
      ]} />
      <div className="grid gap-3 md:grid-cols-2">
        {sortDomains(domains).map((d) => <DomainCard key={d.domain} domain={d} view={view} />)}
      </div>
      <CockpitCatalogue />
    </div>
  );
}

function DomainCard({ domain, view }: { domain: DomainInfo; view: OverviewProps["view"] }) {
  const coming = domain.status !== "live";
  return (
    <Card className="flex flex-col gap-2 p-4" data-testid={`db-domain-card-${domain.domain}`}>
      <div className="flex items-center justify-between gap-2">
        <ViewLink to={{ domain: domain.domain, view }} className="text-sm font-semibold text-text-primary hover:text-accent hover:underline">
          {domain.label}
        </ViewLink>
        {coming ? (
          <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">coming</span>
        ) : (
          <span className="text-[11px] tabular-nums text-text-muted">{domain.relations.length} relations · {count(domain.rows)} rows</span>
        )}
      </div>
      <p className="text-xs text-text-secondary">{domain.description}</p>
      {byBook(domain.relations).map(([book, rels]) => (
        <div key={book} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{BOOK_LABEL[book] ?? book}</span>
          {rels.map((r) => (
            <ViewLink key={r.relation} to={{ domain: domain.domain, relation: r.relation, view }}
                      className="text-xs text-accent hover:underline">
              {r.label}
            </ViewLink>
          ))}
        </div>
      ))}
    </Card>
  );
}

/**
 * The Cockpit's own catalogue of its two books (subject areas, governed
 * values), from the Cockpit service. Opened on request, so the Data Builder
 * itself depends on nothing but its own service.
 */
function CockpitCatalogue() {
  const [open, setOpen] = React.useState(false);
  return (
    <Card className="p-0">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="db-cockpit-catalogue"
              className="flex w-full items-center gap-2 p-3.5 text-left text-sm font-semibold text-text-primary hover:bg-surface-hover">
        {open ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
        <BookOpen className="size-4 text-text-muted" aria-hidden />
        The Cockpit&apos;s catalogue of its two books
        <span className="ml-auto text-[11px] font-normal text-text-muted">subject areas and governed values, from the Cockpit service</span>
      </button>
      {open ? (
        <section className="border-t border-border p-3.5" data-testid="data-builder-analytical-books">
          <DataBooks />
        </section>
      ) : null}
    </Card>
  );
}
