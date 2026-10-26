"use client";

/**
 * Policy Docs (PLAN_R3 S1-2): every credit policy document and circular, stored and versioned, and the active
 * policy pack the Cockpit cites. `/policy-docs` is the library; `/policy-docs?doc=<id>` opens one document.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { useUrlState } from "@/lib/v5/back";
import { ChevronDown, ChevronRight, Layers, Plus, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorBox, Loading, PageTop, SectionTitle } from "@/components/v5/workspace/parts";
import { cn } from "@/lib/utils";
import {
  type DocKind, type DocRow, KIND_LABEL, type PackVersionRow, bookLabel, clauseWord, packClauses, policy,
} from "@/lib/v5/policy";
import { day, useWs, when } from "@/lib/v5/workspace";

import { AddPolicyDialog, DocStatusPill, KindBadge, personName } from "./add-flow";
import { PolicyDocument } from "./document";
import { AssessmentsPanel, GlobalRulesPanel, GoldPanel, KindTabs, type View } from "./rulebook";  // Round P
import { edition } from "@/lib/navigation";
const READER = edition() === "dealdesk" ? "Deal Desk" : "the Cockpit";


/** The route: `?doc=` opens one document, otherwise the library. */
export function PolicyDocsRoute() {
  const params = useSearchParams();
  const doc = params.get("doc");
  if (doc) return <PolicyDocument key={doc} id={doc} clause={params.get("clause")} />;
  return <PolicyLibrary />;
}

type Filter = "all" | "policy" | "circular" | "regulation";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "policy", label: "Policies" },
  { id: "circular", label: "Circulars" },
  { id: "regulation", label: "Regulatory" },
];

export function PolicyLibrary() {
  // R7: the filter and the search are in the address, so Back from a document returns to the library as it was.
  const [filter, setFilter] = useUrlState<Filter>("filter", "all");
  const [view, setView] = useUrlState<View>("view", "all");  // Round P: the four kinds
  const [q, setQ] = useUrlState<string>("q", "");
  const [text, setText] = React.useState(q);
  const [reload, setReload] = React.useState(0);
  const [adding, setAdding] = React.useState(false);
  const [changed, setChanged] = React.useState(false);

  // Search as the reader types, a moment after the last key.
  React.useEffect(() => {
    const t = window.setTimeout(() => setQ(text.trim()), 250);
    return () => window.clearTimeout(t);
  }, [text]);

  const kind: DocKind | "" = filter === "all" ? "" : filter;
  const docs = useWs(() => policy.documents({ kind, q }), `policy-docs|${kind}|${q}|${reload}`, "policy-docs");
  const versions = useWs(() => policy.versions(), `policy-versions|${reload}`, "policy-versions");

  const closeAdd = () => {
    setAdding(false);
    if (changed) { setChanged(false); setReload((n) => n + 1); }
  };

  return (
    <div className="space-y-5" data-testid="policy-library" data-tour="policy-home">
      <PageTop eyebrow="Work" title="Policy Docs"
               about={`All credit policy documents and circulars: stored, versioned, and the active pack ${READER} cites.`}
               actions={
                 <Button onClick={() => setAdding(true)} data-testid="policy-add">
                   <Plus aria-hidden /> Add a policy or circular
                 </Button>
               } />

      <PackSummary versions={versions.data?.versions ?? null} error={versions.error} />

      <KindTabs view={view} onView={setView} />
      {view === "gold" ? <GoldPanel /> : view === "rules" ? <GlobalRulesPanel /> : <>
      {view === "regulation" || view === "policy" ? <AssessmentsPanel kind={view} /> : null}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Kind of document">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" role="tab" aria-selected={filter === f.id} data-testid={`policy-filter-${f.id}`}
                    onClick={() => setFilter(f.id)}
                    className={cn("-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                                  filter === f.id ? "border-accent text-accent" : "border-transparent text-text-secondary hover:text-text-primary")}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-text-muted" aria-hidden />
          <Input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search title, reference or clause"
                 aria-label="Search policy documents" className="pl-8" data-testid="policy-search" />
        </div>
      </div>

      {docs.error ? <ErrorBox error={docs.error} /> : !docs.data ? <Loading what="Loading the policy library…" /> : (
        <DocList rows={docs.data.documents.filter((d) => view === "regulation" ? ["circular", "regulation"].includes(d.kind)
                                                           : view === "policy" ? ["policy", "guideline"].includes(d.kind) : true)}
                 filtered={!!q || filter !== "all" || view !== "all"} />
      )}

      <PackVersions versions={versions.data?.versions ?? null} error={versions.error} />
      </>}

      {adding ? <AddPolicyDialog onClose={closeAdd} onChanged={() => setChanged(true)} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------- summary strip

function PackSummary({ versions, error }: { versions: PackVersionRow[] | null; error: string | null }) {
  const active = versions?.find((v) => v.active) ?? null;
  return (
    <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3" data-testid="policy-summary">
      <span className="flex items-center gap-2">
        <Layers className="size-4 text-accent" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Active policy pack</span>
      </span>
      {error ? (
        <span className="text-sm text-negative" role="alert">{error}</span>
      ) : !versions ? (
        <span className="text-sm text-text-muted">Loading…</span>
      ) : !active ? (
        <span className="text-sm text-text-muted">No pack version is active.</span>
      ) : (
        <>
          <span className="font-mono text-sm font-semibold text-text-primary" data-testid="policy-active-pack">{active.label}</span>
          <span className="text-sm text-text-secondary">Effective {day(active.effective_from)}</span>
          <span className="text-sm tabular-nums text-text-secondary">{clauseWord(active.clause_count)}</span>
          {active.approved_by ? <span className="text-sm text-text-secondary">Approved by {active.approved_by.name}</span> : null}
        </>
      )}
      <a href="#policy-versions" className="ml-auto text-sm text-accent hover:underline" data-testid="policy-summary-versions">
        {versions ? `${versions.length} version${versions.length === 1 ? "" : "s"}` : "Versions"}
      </a>
    </Card>
  );
}

// ---------------------------------------------------------------- documents

function DocList({ rows, filtered }: { rows: DocRow[]; filtered: boolean }) {
  if (rows.length === 0) {
    return <Empty>{filtered ? "No documents match this view." : "No policy documents are stored yet. Add a policy or circular to start."}</Empty>;
  }
  return (
    <Card className="overflow-hidden p-0" data-testid="policy-doc-list">
      <div className="hidden grid-cols-[minmax(0,2.4fr)_minmax(0,1fr)_120px_110px_minmax(0,1fr)_70px] gap-3 border-b border-border px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-muted lg:grid">
        <span>Document</span>
        <span>Book</span>
        <span>Status</span>
        <span>Effective</span>
        <span>Approver</span>
        <span className="text-right">Clauses</span>
      </div>
      <ul className="divide-y divide-border">
        {rows.map((d) => (
          <li key={d.id}>
            <Link href={`/policy-docs?doc=${encodeURIComponent(d.id)}`} data-testid="policy-doc-row" data-id={d.id} data-kind={d.kind} data-status={d.status}
                  className="grid gap-x-3 gap-y-1.5 px-4 py-3 transition-colors hover:bg-surface-hover lg:grid-cols-[minmax(0,2.4fr)_minmax(0,1fr)_120px_110px_minmax(0,1fr)_70px] lg:items-center">
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold text-text-primary">{d.title}</span>
                  <KindBadge kind={d.kind} />
                </span>
                <span className="mt-0.5 block text-xs text-text-muted">
                  {d.reference ? <span className="font-mono text-text-secondary">{d.reference}</span> : null}
                  {d.reference ? " · " : ""}uploaded by {personName(d.uploaded_by)}, {day(d.uploaded_at)}
                </span>
              </span>
              <span className="text-sm text-text-secondary"><span className="text-text-muted lg:hidden">Book: </span>{bookLabel(d.book)}</span>
              <span><DocStatusPill status={d.status} /></span>
              <span className="text-sm tabular-nums text-text-secondary"><span className="text-text-muted lg:hidden">Effective: </span>{day(d.effective_from)}</span>
              <span className="truncate text-sm text-text-secondary"><span className="text-text-muted lg:hidden">Approver: </span>{personName(d.approved_by)}</span>
              <span className="text-sm tabular-nums text-text-primary lg:text-right"><span className="text-text-muted lg:hidden">Clauses: </span>{d.clause_count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------- pack versions

function PackVersions({ versions, error }: { versions: PackVersionRow[] | null; error: string | null }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <section id="policy-versions" className="scroll-mt-24" data-testid="policy-versions">
      <div className="flex items-center gap-2">
        <SectionTitle>Pack versions</SectionTitle>
        <InfoPopover title="Pack versions">
          Every change to the policy pack {READER} reads is a new version, with its effective date and approver. Older versions stay on record and can be opened read-only.
        </InfoPopover>
      </div>
      {error ? <ErrorBox error={error} /> : !versions ? <Loading what="Loading pack versions…" /> : versions.length === 0 ? <Empty>No pack versions yet.</Empty> : (
        <Card className="overflow-hidden p-0">
          <ul className="divide-y divide-border">
            {versions.map((v) => {
              const key = String(v.version);
              const expanded = open === key;
              return (
                <li key={key}>
                  <button type="button" onClick={() => setOpen(expanded ? null : key)} aria-expanded={expanded}
                          data-testid="policy-version-row" data-version={key} data-active={v.active ? "true" : "false"}
                          className="grid w-full gap-x-3 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-surface-hover md:grid-cols-[20px_minmax(0,1fr)_minmax(0,2.5fr)_110px_minmax(0,1fr)_80px] md:items-center">
                    {expanded ? <ChevronDown className="hidden size-4 text-text-muted md:block" aria-hidden /> : <ChevronRight className="hidden size-4 text-text-muted md:block" aria-hidden />}
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-text-primary">{v.label}</span>
                      {v.active ? <Badge variant="positive" className="rounded-full text-[10px] font-semibold uppercase tracking-[0.06em]" data-testid="policy-version-active">Active</Badge> : null}
                    </span>
                    <span className="text-sm text-text-secondary">{v.change}</span>
                    <span className="text-sm tabular-nums text-text-secondary">{day(v.effective_from)}</span>
                    <span className="truncate text-sm text-text-secondary">{personName(v.approved_by ?? v.created_by)}</span>
                    <span className="text-sm tabular-nums text-text-primary md:text-right">{clauseWord(v.clause_count)}</span>
                  </button>
                  {expanded ? <VersionClauses row={v} /> : null}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </section>
  );
}

function VersionClauses({ row }: { row: PackVersionRow }) {
  const v = useWs(() => policy.version(row.version), `policy-version|${String(row.version)}`);
  return (
    <div className="border-t border-border bg-surface-sunken px-4 py-3" data-testid="policy-version-clauses" data-version={String(row.version)}>
      <p className="mb-2 text-xs text-text-muted">
        Read-only. Made {when(row.created_at)} by {personName(row.created_by)}
        {row.approved_by ? `, approved by ${row.approved_by.name}` : ""}.
      </p>
      {v.error ? <ErrorBox error={v.error} /> : !v.data ? <Loading what="Opening this version…" /> : (() => {
        const clauses = packClauses(v.data);
        if (!clauses.length) return <Empty>This version holds no clauses.</Empty>;
        return (
          <div className="max-h-[420px] overflow-y-auto rounded-md border border-border bg-surface">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Clause</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Book</TableHead>
                  <TableHead>Effective</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clauses.map((c, i) => (
                  <TableRow key={`${c.book}|${c.clause_id}|${i}`} data-testid="policy-version-clause" data-id={c.clause_id}>
                    <TableCell className="whitespace-nowrap py-2 font-mono text-xs font-semibold text-text-primary">{c.clause_id}</TableCell>
                    <TableCell className="py-2 text-sm">{c.title}</TableCell>
                    <TableCell className="py-2 text-sm text-text-secondary">{bookLabel(c.book)}</TableCell>
                    <TableCell className="whitespace-nowrap py-2 text-sm tabular-nums text-text-secondary">{day(c.effective_from)}</TableCell>
                    <TableCell className="py-2 text-sm">
                      {c.source?.doc_id ? (
                        <Link href={`/policy-docs?doc=${encodeURIComponent(c.source.doc_id)}&clause=${encodeURIComponent(c.clause_id)}`}
                              className="text-accent hover:underline">
                          {[KIND_LABEL[c.source.kind as DocKind] ?? c.source.kind, c.source.reference].filter(Boolean).join(" ") || "Open"}
                        </Link>
                      ) : <span className="text-text-muted">—</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        );
      })()}
    </div>
  );
}
