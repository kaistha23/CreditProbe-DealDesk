"use client";

/**
 * Small pieces the Data Builder is built from: the
 * domain list on the left, and the domain panel shown before a relation is
 * chosen.
 */

import * as React from "react";
import { Database } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { BOOK_LABEL, count, type DomainInfo, type RelationInfo } from "@/lib/v5/data-builder";

import { ViewLink } from "./state";

/** The order and grouping the left list follows; anything new the service publishes is listed after. */
export const DOMAIN_ORDER = ["cockpit", "ews", "bureau", "open_banking", "borrower_360", "what_if"];

export function sortDomains(domains: DomainInfo[]): DomainInfo[] {
  const rank = (d: string) => { const i = DOMAIN_ORDER.indexOf(d); return i < 0 ? DOMAIN_ORDER.length : i; };
  return [...domains].sort((a, b) => rank(a.domain) - rank(b.domain));
}

export function byBook(relations: RelationInfo[]): [string, RelationInfo[]][] {
  const groups = new Map<string, RelationInfo[]>();
  for (const r of relations) groups.set(r.book, [...(groups.get(r.book) ?? []), r]);
  return [...groups.entries()];
}

export function DomainList({ domains, domain, relation, view }: {
  domains: DomainInfo[]; domain: string; relation: string; view: "comfortable" | "compact";
}) {
  return (
    <nav className="space-y-3" aria-label="Data domains" data-testid="db-domains">
      {sortDomains(domains).map((d) => {
        const coming = d.status !== "live";
        const selected = d.domain === domain;
        return (
          <div key={d.domain}>
            <ViewLink to={{ domain: d.domain, view }} testId={`db-domain-${d.domain}`}
                      className={cn("flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[13px] font-semibold",
                                    selected && !relation ? "bg-accent-muted text-accent" : "text-text-primary hover:bg-surface-hover")}>
              <span className="flex items-center gap-1.5">
                <Database className="size-3.5 text-text-muted" aria-hidden />
                {d.label}
              </span>
              {coming ? (
                <span className="rounded-full border border-border px-1.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                  coming
                </span>
              ) : (
                <span className="text-[10px] font-normal tabular-nums text-text-muted">{d.relations.length}</span>
              )}
            </ViewLink>
            {!coming && (selected || !domain) ? (
              <div className="ml-3 mt-0.5 space-y-1.5 border-l border-border pl-2">
                {byBook(d.relations).map(([book, rels]) => (
                  <div key={book}>
                    <p className="px-1.5 pt-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-text-muted">
                      {BOOK_LABEL[book] ?? book}
                    </p>
                    {rels.map((r) => {
                      const active = selected && r.relation === relation;
                      return (
                        <ViewLink key={r.relation} to={{ domain: d.domain, relation: r.relation, view }}
                                  testId={`db-relation-${d.domain}-${r.relation}`} title={r.description}
                                  className={cn("block truncate rounded px-1.5 py-1 text-[12px]",
                                                active ? "bg-accent-muted font-medium text-accent"
                                                  : "text-text-secondary hover:bg-surface-hover hover:text-text-primary")}>
                          {r.label}
                        </ViewLink>
                      );
                    })}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

/** A domain chosen, no relation yet: what is in it. */
export function DomainPanel({ domain, view }: { domain: DomainInfo; view: "comfortable" | "compact" }) {
  if (domain.status !== "live") {
    return (
      <Card className="space-y-2 p-5" data-testid="db-coming">
        <div className="flex items-center gap-2">
          <p className="text-base font-semibold text-text-primary">{domain.label}</p>
          <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            coming
          </span>
        </div>
        <p className="text-sm text-text-secondary">{domain.description}</p>
        <p className="text-xs text-text-muted">
          No relations are published for this domain yet. When its module is built, its tables are added to the
          Data Domains registry and appear here, browsable like the others.
        </p>
      </Card>
    );
  }
  return (
    <div className="space-y-3" data-testid="db-domain-panel">
      <div>
        <p className="text-base font-semibold text-text-primary">{domain.label}</p>
        <p className="text-sm text-text-secondary">{domain.description}</p>
        <p className="mt-1 text-xs text-text-muted">
          {domain.relations.length} relations · {count(domain.rows)} rows in all
        </p>
      </div>
      {byBook(domain.relations).map(([book, rels]) => (
        <section key={book} className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{BOOK_LABEL[book] ?? book}</p>
          <div className="grid gap-3 md:grid-cols-2">
            {rels.map((r) => (
              <Card key={r.relation} className="p-0">
                <ViewLink to={{ domain: domain.domain, relation: r.relation, view }}
                          testId={`db-card-${domain.domain}-${r.relation}`}
                          className="block space-y-1 p-3.5 transition-colors hover:bg-surface-hover">
                  <p className="text-sm font-semibold text-text-primary">{r.label}</p>
                  <p className="font-mono text-[11px] text-text-muted">{r.relation}</p>
                  {r.description ? <p className="line-clamp-2 text-xs text-text-secondary">{r.description}</p> : null}
                  <p className="text-[11px] text-text-muted">
                    {count(r.rows)} rows · {r.columns} columns · {r.periods.length} periods
                    {r.periods.length ? ` (${r.periods[0]} to ${r.latest_period})` : ""}
                  </p>
                </ViewLink>
              </Card>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
