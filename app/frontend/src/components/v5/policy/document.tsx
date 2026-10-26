"use client";

/**
 * One policy document or circular: `/policy-docs?doc=<id>[&clause=<clause id>]`.
 *
 * Its header and files, its clauses grouped by book and section (the clause in the address is highlighted and
 * scrolled to), CreditProbe's interpretation, the "Add this to the Cockpit?" decision while it is pending,
 * Withdraw for an active circular, and the pack versions that involve it.
 */

import { parseExcerpt } from "@/lib/v5/policy-excerpt";
import Link from "next/link";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { Download, FileText, Loader2, Undo2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCoreAuth } from "@/components/v5/core/auth";
import { ShareButton } from "@/components/v5/mail/share";
import { Empty, ErrorBox, Loading, SectionTitle } from "@/components/v5/workspace/parts";
import { cn } from "@/lib/utils";
import { fileSize } from "@/lib/v5/core";
import { cell as cellFmt } from "@/lib/v5/format";
import {
  type Clause, type Doc, type DocFile, KIND_LABEL, type PackVersion, bookLabel, clauseWord, policy,
} from "@/lib/v5/policy";
import { day, useWs, when } from "@/lib/v5/workspace";

import { DecisionBlock, DocStatusPill, InterpretationView, KindBadge, personName } from "./add-flow";
import { DocImpact } from "./rulebook";
import { friendlyMessage } from "@/lib/v5/errors";
import { edition } from "@/lib/navigation";
const READER = edition() === "dealdesk" ? "Deal Desk" : "the Cockpit";


function BackLink() {
  return (
    <BackButton fallback={{ href: "/policy-docs", label: "Policy Docs" }} testId="policy-back" />
  );
}

export function PolicyDocument({ id, clause }: { id: string; clause?: string | null }) {
  const [reload, setReload] = React.useState(0);
  const doc = useWs(() => policy.document(id), `policy-doc|${id}|${reload}`, `policy-doc|${id}`);

  if (doc.error) {
    return (
      <div className="space-y-4" data-testid="policy-document">
        <BackLink />
        <ErrorBox error={doc.error} />
      </div>
    );
  }
  if (!doc.data) {
    return (
      <div className="space-y-4" data-testid="policy-document">
        <BackLink />
        <Loading what="Opening the document…" />
      </div>
    );
  }
  return <DocumentView d={doc.data} clause={clause ?? null} onChanged={() => setReload((n) => n + 1)} />;
}

function DocumentView({ d, clause, onChanged }: { d: Doc; clause: string | null; onChanged: () => void }) {
  // A decision or a withdrawal made on this page keeps its result on screen after the document reloads.
  const [decidedHere, setDecidedHere] = React.useState(false);
  const [withdrawnHere, setWithdrawnHere] = React.useState(false);
  const clauses = React.useMemo(() => d.clauses ?? [], [d.clauses]);

  // Bring the clause named in the address into view once the clauses are on screen.
  React.useEffect(() => {
    if (!clause) return;
    const el = document.getElementById(clauseAnchor(clause));
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [clause, clauses.length]);

  const href = `/policy-docs?doc=${encodeURIComponent(d.id)}`;
  const summary = d.summary && d.summary.length > 280 ? `${d.summary.slice(0, 277)}…` : d.summary;

  return (
    <div className="space-y-5" data-testid="policy-document" data-id={d.id} data-status={d.status}>
      <header className="space-y-2">
        <BackLink />
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Policy Docs · {KIND_LABEL[d.kind] ?? d.kind}</p>
            <h1 className="text-2xl font-semibold text-text-primary" data-testid="policy-doc-title">{d.title}</h1>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2 pb-1">
            <ShareButton testId="policy-share"
                         object={{ type: "document", id: d.id, label: d.title, href, summary: summary || undefined }} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-text-secondary">
          <KindBadge kind={d.kind} />
          {d.reference ? <span className="font-mono text-text-primary">{d.reference}</span> : null}
          <DocStatusPill status={d.status} testId="policy-doc-status" />
          <span>{bookLabel(d.book)}</span>
          <span>Effective {day(d.effective_from)}</span>
          <span>Approved by {personName(d.approved_by)}</span>
          <span>Uploaded by {personName(d.uploaded_by)}, {when(d.uploaded_at)}</span>
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          {d.summary ? (
            <Card className="p-5" data-testid="policy-doc-summary">
              <SectionTitle>Summary</SectionTitle>
              <p className="whitespace-pre-line text-sm leading-[1.65] text-text-primary">{d.summary}</p>
            </Card>
          ) : null}

          {d.status === "pending" || decidedHere ? (
            <DecisionBlock docId={d.id} question={d.interpretation?.question} showOpen={false}
                           onDecided={() => { setDecidedHere(true); onChanged(); }} />
          ) : null}

          <DocImpact docId={d.id} />{/* Round P: the Deal Desk impact of this document (decidable while pending) */}

          {(d.status === "active" && d.kind === "circular") || withdrawnHere
            ? <WithdrawBlock d={d} onChanged={() => { setWithdrawnHere(true); onChanged(); }} /> : null}

          <section data-testid="policy-clauses">
            <SectionTitle right={<span className="text-xs text-text-muted">{clauseWord(clauses.length)}</span>}>Clauses</SectionTitle>
            {clauses.length === 0 ? <Empty>No clauses are recorded for this document.</Empty> : <ClauseGroups clauses={clauses} highlight={clause} docId={d.id} />}
          </section>

          {d.interpretation ? (
            <details className="group rounded-lg border border-border bg-surface" data-testid="policy-doc-interpretation">
              <summary className="cursor-pointer select-none px-5 py-3 text-sm font-semibold text-text-primary hover:bg-surface-hover">
                CreditProbe&apos;s interpretation
                <span className="ml-2 text-xs font-normal text-text-muted">summary, clauses found, what changes and what it affects</span>
              </summary>
              <div className="border-t border-border px-5 py-4">
                <InterpretationView interp={d.interpretation} />
              </div>
            </details>
          ) : null}

          {d.text_excerpt ? (
            <details className="rounded-lg border border-border bg-surface" data-testid="policy-doc-excerpt">
              <summary className="cursor-pointer select-none px-5 py-3 text-sm font-semibold text-text-primary hover:bg-surface-hover">
                Text of the document (excerpt)
              </summary>
              <div className="space-y-1.5 border-t border-border px-5 py-4 text-sm leading-[1.65] text-text-secondary" data-testid="policy-doc-excerpt-text">
                {parseExcerpt(d.text_excerpt).map((p, i) => p.kind === "heading"
                  ? <h4 key={i} className="pt-2 text-[13px] font-semibold uppercase tracking-[0.06em] text-text-primary">{p.text}</h4>
                  : p.kind === "clause"
                    ? <p key={i}><strong className="policy-clause-id font-mono text-accent">{p.id}</strong>{" "}<strong className="policy-clause-title">{p.title}.</strong>{" "}{p.rest}</p>
                    : <p key={i}>{p.text}</p>)}
              </div>
            </details>
          ) : null}
        </div>

        <aside className="space-y-5">
          <Card className="p-4" data-testid="policy-files">
            <SectionTitle>Files</SectionTitle>
            {(d.files ?? []).length === 0 ? (
              <p className="text-sm text-text-muted">No files are kept with this document.</p>
            ) : (
              <ul className="space-y-2">
                {d.files.map((f) => <FileRow key={f.id} docId={d.id} f={f} />)}
              </ul>
            )}
          </Card>
          <VersionHistory versions={d.versions ?? []} />
        </aside>
      </div>
    </div>
  );
}

function fileKind(f: DocFile): string {
  const n = f.name.toLowerCase();
  if (n.endsWith(".docx") || f.content_type.includes("wordprocessingml")) return "Word";
  if (n.endsWith(".pdf") || f.content_type === "application/pdf") return "PDF";
  if (n.endsWith(".md")) return "Markdown";
  if (n.endsWith(".txt") || f.content_type.startsWith("text/")) return "Text";
  return "File";
}

function FileRow({ docId, f }: { docId: string; f: DocFile }) {
  const kind = fileKind(f);
  return (
    <li>
      <a href={policy.fileUrl(docId, f.id)} download={f.name} data-testid="policy-file" data-id={f.id}
         className="flex items-center gap-2.5 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-surface-hover"
         aria-label={`Download ${kind}: ${f.name}`}>
        <FileText className="size-4 shrink-0 text-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium text-text-primary">{f.name}</span>
          <span className="block text-xs text-text-muted">{kind} · {fileSize(f.size)}</span>
        </span>
        <Download className="size-4 shrink-0 text-text-muted" aria-hidden />
      </a>
    </li>
  );
}

// ---------------------------------------------------------------- clauses

export function clauseAnchor(id: string): string {
  return `clause-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

/** Clauses grouped by book, then section, in the order the document gives them. */
export function ClauseGroups({ clauses, highlight, docId }: { clauses: Clause[]; highlight?: string | null; docId?: string }) {
  const groups = React.useMemo(() => {
    const books = new Map<string, Map<string, { title: string; clauses: Clause[] }>>();
    for (const c of clauses) {
      const b = c.book || "";
      if (!books.has(b)) books.set(b, new Map());
      const sections = books.get(b)!;
      const s = c.section || "";
      if (!sections.has(s)) sections.set(s, { title: c.section_title, clauses: [] });
      sections.get(s)!.clauses.push(c);
    }
    return [...books.entries()];
  }, [clauses]);

  return (
    <div className="space-y-6">
      {groups.map(([book, sections]) => (
        <div key={book || "none"} className="space-y-4" data-testid="policy-clause-book" data-book={book}>
          {groups.length > 1 || book ? (
            <h2 className="text-[15px] font-semibold text-text-primary">{book ? `${bookLabel(book)} book` : "Clauses"}</h2>
          ) : null}
          {[...sections.entries()].map(([section, s]) => (
            <div key={section || "none"} className="space-y-2">
              {section || s.title ? (
                <h3 className="text-sm font-semibold text-text-secondary">
                  {section ? <span className="mr-1.5 font-mono text-text-primary">{section}</span> : null}{s.title}
                </h3>
              ) : null}
              <div className="space-y-2">
                {s.clauses.map((c, i) => (
                  <ClauseCard key={`${c.clause_id}|${i}`} c={c} highlighted={!!highlight && c.clause_id === highlight} docId={docId} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function ClauseCard({ c, highlighted, docId }: { c: Clause; highlighted: boolean; docId?: string }) {
  const thresholds = Object.entries(c.thresholds ?? {});
  const fromElsewhere = c.source?.doc_id && c.source.doc_id !== docId;
  return (
    <article id={clauseAnchor(c.clause_id)} data-testid="policy-clause" data-id={c.clause_id} data-highlighted={highlighted ? "true" : undefined}
             className={cn("scroll-mt-24 rounded-lg border bg-surface p-4 transition-colors",
                           highlighted ? "border-accent ring-2 ring-accent/30" : "border-border")}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-mono text-xs font-semibold text-accent">{c.clause_id}</span>
        <h4 className="text-sm font-semibold text-text-primary">{c.title}</h4>
        {c.status && c.status !== "active" ? (
          <Badge variant={c.status === "proposed" ? "warning" : "default"} className="text-[10px]">{c.status === "proposed" ? "Proposed" : "Superseded"}</Badge>
        ) : null}
      </div>
      <p className="mt-1.5 text-sm leading-[1.6] text-text-primary">{c.rule}</p>
      {thresholds.length ? (
        <div className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Thresholds">
          {thresholds.map(([k, v]) => (
            <span key={k} className="inline-flex items-baseline gap-1 rounded-md border border-border bg-surface-sunken px-2 py-0.5 text-xs">
              <span className="text-text-muted">{k}</span>
              <span className="font-medium tabular-nums text-text-primary">{cellFmt(v, k)}</span>
            </span>
          ))}
        </div>
      ) : null}
      <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {c.applies_to?.length ? <Meta label="Applies to" value={c.applies_to.map((x) => x.replace(/_/g, " ")).join(", ")} /> : null}
        {c.owner ? <Meta label="Owner" value={c.owner} /> : null}
        <Meta label="Last reviewed" value={day(c.last_reviewed)} />
        <Meta label="Effective" value={day(c.effective_from)} />
        {c.source ? (
          <Meta label="Source" value={
            fromElsewhere ? (
              <Link href={`/policy-docs?doc=${encodeURIComponent(c.source.doc_id)}`} className="text-accent hover:underline">
                {[KIND_LABEL[c.source.kind as keyof typeof KIND_LABEL] ?? c.source.kind, c.source.reference].filter(Boolean).join(" ")}
              </Link>
            ) : [KIND_LABEL[c.source.kind as keyof typeof KIND_LABEL] ?? c.source.kind, c.source.reference].filter(Boolean).join(" ") || "—"
          } />
        ) : null}
      </dl>
    </article>
  );
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-1.5">
      <dt className="shrink-0 text-text-muted">{label}</dt>
      <dd className="min-w-0 text-text-secondary">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------- withdraw

function WithdrawBlock({ d, onChanged }: { d: Doc; onChanged: () => void }) {
  const { viewingAs } = useCoreAuth();
  const [open, setOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<PackVersion | null>(null);

  async function withdraw() {
    if (busy || viewingAs) return;
    setBusy(true);
    setError(null);
    try {
      const r = await policy.withdraw(d.id, note.trim());
      setDone(r.pack);
      onChanged();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <p role="status" className="rounded-lg border border-border bg-surface-sunken p-4 text-sm text-text-primary" data-testid="policy-withdraw-done">
        Withdrawn. Pack {done.label} is now active without this circular&apos;s clauses; earlier versions stay on record.
      </p>
    );
  }

  return (
    <Card className="p-4" data-testid="policy-withdraw-block">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-sm text-text-secondary">
          This circular&apos;s clauses are in the active policy pack, and {READER} cites them.
        </p>
        {!open ? (
          <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={!!viewingAs} data-testid="policy-withdraw">
            <Undo2 aria-hidden /> Withdraw from {READER}
          </Button>
        ) : null}
      </div>
      {viewingAs ? (
        <p role="alert" className="mt-2 text-sm text-warning" data-testid="policy-readonly">
          You are viewing as {viewingAs.name}. Stop viewing as to withdraw this circular.
        </p>
      ) : null}
      {open ? (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <p className="text-sm text-text-primary">
            Withdraw <span className="font-medium">{d.title}</span>? A new pack version is made without its clauses; older versions stay on record.
          </p>
          <div>
            <Label htmlFor="policy-withdraw-note">Note (optional)</Label>
            <Textarea id="policy-withdraw-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
                      data-testid="policy-withdraw-note" />
          </div>
          <div className="flex gap-2">
            <Button variant="destructive" size="sm" onClick={() => void withdraw()} disabled={busy || !!viewingAs} data-testid="policy-withdraw-confirm">
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} Withdraw
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)} disabled={busy} data-testid="policy-withdraw-cancel">Cancel</Button>
          </div>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-2 text-sm text-negative" data-testid="policy-withdraw-error">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------- versions

function VersionHistory({ versions }: { versions: Doc["versions"] }) {
  return (
    <Card className="p-4" data-testid="policy-doc-versions">
      <SectionTitle>Pack versions with this document</SectionTitle>
      {versions.length === 0 ? (
        <p className="text-sm text-text-muted">This document is not in any pack version.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Effective</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {versions.map((v) => (
              <TableRow key={String(v.version)} className="align-top" data-testid="policy-doc-version" data-version={String(v.version)}>
                <TableCell className="py-2">
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-xs font-semibold text-text-primary">{v.label}</span>
                    {v.active ? <Badge variant="positive" className="text-[10px]">Active</Badge> : null}
                  </span>
                  <span className="mt-0.5 block text-xs text-text-secondary">{v.change}</span>
                  <span className="block text-xs text-text-muted">{personName(v.approved_by ?? v.created_by)}</span>
                </TableCell>
                <TableCell className="whitespace-nowrap py-2 text-xs">{day(v.effective_from)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
