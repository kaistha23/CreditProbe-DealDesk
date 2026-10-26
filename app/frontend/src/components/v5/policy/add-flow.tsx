"use client";

/**
 * Add a policy or circular (PLAN_R3 S1-2):
 *   1. upload a .docx, .pdf or text file;
 *   2. CreditProbe's interpretation: summary, clauses found, what changes against the current policy, and the
 *      books, segments and Early Warning rules it affects;
 *   3. "Add this to the Cockpit?" Yes activates the clauses in a new pack version (effective date, approver);
 *      No keeps the document on record without adding it.
 *
 * Also holds the small pieces the library and the document page share (status pill, kind badge), so the
 * three screens read the same.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowRight, Check, CircleCheck, FileUp, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCoreAuth } from "@/components/v5/core/auth";
import { useDirectory } from "@/components/v5/mail/people";
import { cn } from "@/lib/utils";
import {
  type ClauseChange, type Doc, type DocKind, type DocStatus, type Interpretation, KIND_LABEL, type PackVersion,
  type Person, STATUS_LABEL, bookLabel, clauseWord, policy, todayIso,
} from "@/lib/v5/policy";
import { day } from "@/lib/v5/workspace";
import { friendlyMessage } from "@/lib/v5/errors";
import { type Assessment, rulebook } from "@/lib/v5/dealdesk-rules";
import { DealDeskImpact } from "./rulebook";  // Round P
import { edition } from "@/lib/navigation";
/** Who reads the active policy pack: Deal Desk (its proposal checks and the brief) in the Deal Desk edition, the Cockpit in the full product. */
const READER = edition() === "dealdesk" ? "Deal Desk" : "the Cockpit";
const READER_CAP = edition() === "dealdesk" ? "Deal Desk" : "The Cockpit";


// ---------------------------------------------------------------- shared atoms

const STATUS_VARIANT: Record<DocStatus, "positive" | "warning" | "default" | "negative" | "info"> = {
  active: "positive", pending: "warning", superseded: "default", withdrawn: "default", rejected: "negative",
  reference: "info",
};

export function DocStatusPill({ status, testId }: { status: DocStatus; testId?: string }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "default"} data-testid={testId} data-status={status}
           className="shrink-0 rounded-full text-[10px] font-semibold uppercase tracking-[0.06em]">
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function KindBadge({ kind }: { kind: DocKind }) {
  return (
    <Badge variant={kind === "circular" ? "accent" : "outline"} className="shrink-0 text-[11px]" data-kind={kind}>
      {KIND_LABEL[kind] ?? kind}
    </Badge>
  );
}

export function personName(p: Person | null | undefined): string {
  return p?.name ?? "—";
}

const CHANGE_LABEL: Record<ClauseChange, string> = { new: "New", amends: "Amends", unchanged: "Unchanged" };
const CHANGE_VARIANT: Record<ClauseChange, "accent" | "warning" | "default"> = { new: "accent", amends: "warning", unchanged: "default" };

export function ChangeBadge({ change }: { change: ClauseChange }) {
  return <Badge variant={CHANGE_VARIANT[change] ?? "default"} className="shrink-0 text-[11px]" data-change={change}>{CHANGE_LABEL[change] ?? change}</Badge>;
}

function Chips({ items, empty = "None named" }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="text-sm text-text-muted">{empty}.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((x) => (
        <span key={x} className="rounded-md border border-border bg-surface-sunken px-2 py-0.5 text-xs text-text-primary">{x}</span>
      ))}
    </div>
  );
}

function SubTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{children}</h3>;
}

// ---------------------------------------------------------------- interpretation (step 2)

export function InterpretationView({ interp, className }: { interp: Interpretation; className?: string }) {
  const clauses = interp.clauses ?? [];
  const changes = interp.changes ?? [];
  const affects = interp.affects ?? { books: [], segments: [], ews_rules: [] };
  return (
    <div className={cn("space-y-5", className)} data-testid="policy-interpretation" data-method={interp.method}>
      <section>
        <SubTitle>Summary</SubTitle>
        <p className="whitespace-pre-line text-sm leading-[1.65] text-text-primary" data-testid="policy-interpretation-summary">{interp.summary}</p>
        <p className="mt-1 text-xs text-text-muted">
          {interp.method === "model" ? "Read by the AI model against the active policy pack." : "Read by CreditProbe's policy reader against the active policy pack."}
        </p>
      </section>

      <section>
        <SubTitle>Clauses found ({clauses.length})</SubTitle>
        {clauses.length === 0 ? (
          <p className="text-sm text-text-muted">No clauses were found in this document.</p>
        ) : (
          <div className="rounded-lg border border-border">
            <Table data-testid="policy-interpretation-clauses">
              <TableHeader>
                <TableRow>
                  <TableHead>Clause</TableHead>
                  <TableHead>Limit</TableHead>
                  <TableHead>Threshold</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Change</TableHead>
                  <TableHead className="min-w-[260px]">Rule</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clauses.map((c, i) => (
                  <TableRow key={`${c.clause_id}|${i}`} className="align-top" data-testid="policy-interpretation-clause" data-id={c.clause_id}>
                    <TableCell className="py-2.5">
                      <span className="block font-mono text-xs font-semibold text-text-primary">{c.clause_id}</span>
                      <span className="block text-sm text-text-primary">{c.title}</span>
                      {c.book ? <span className="block text-xs text-text-muted">{bookLabel(c.book)}</span> : null}
                    </TableCell>
                    <TableCell className="py-2.5 text-sm">{c.limit ?? <span className="text-text-muted">—</span>}</TableCell>
                    <TableCell className="py-2.5 text-sm">{c.threshold ?? <span className="text-text-muted">—</span>}</TableCell>
                    <TableCell className="py-2.5 text-sm">{c.scope || <span className="text-text-muted">—</span>}</TableCell>
                    <TableCell className="py-2.5"><ChangeBadge change={c.change} /></TableCell>
                    <TableCell className="py-2.5 text-sm">
                      {c.change === "amends" && c.current_rule ? (
                        <span className="block space-y-1">
                          <span className="block text-text-muted"><span className="font-medium">Now:</span> {c.current_rule}</span>
                          <span className="flex items-start gap-1 text-text-primary">
                            <ArrowRight className="mt-0.5 size-3.5 shrink-0 text-warning" aria-label="becomes" />
                            <span>{c.rule}</span>
                          </span>
                        </span>
                      ) : (
                        <span className={cn(c.change === "unchanged" ? "text-text-secondary" : "text-text-primary")}>{c.rule}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section data-testid="policy-interpretation-changes">
        <SubTitle>What changes against the current policy</SubTitle>
        {changes.length === 0 ? (
          <p className="text-sm text-text-muted">Nothing in the active policy changes.</p>
        ) : (
          <ul className="space-y-2">
            {changes.map((ch, i) => (
              <li key={`${ch.clause_id}|${i}`} className="rounded-md border border-border p-3 text-sm">
                <span className="font-mono text-xs font-semibold text-text-primary">{ch.clause_id}</span>
                <span className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="text-text-muted line-through decoration-text-muted/60">{ch.before || "Not in the policy"}</span>
                  <ArrowRight className="size-3.5 shrink-0 self-center text-warning" aria-label="becomes" />
                  <span className="font-medium text-text-primary">{ch.after}</span>
                </span>
                {ch.effect ? <span className="mt-1 block text-text-secondary">{ch.effect}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="policy-interpretation-affects">
        <SubTitle>Affects</SubTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium text-text-secondary">Books</p>
            <Chips items={(affects.books ?? []).map(bookLabel)} />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-text-secondary">Segments</p>
            <Chips items={affects.segments ?? []} />
          </div>
        </div>
        {edition() === "dealdesk" ? null : <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-text-secondary">Early Warning rules</p>
          {(affects.ews_rules ?? []).length === 0 ? (
            <p className="text-sm text-text-muted">No Early Warning rule is affected.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {affects.ews_rules.map((r) => (
                <li key={r.rule_id} className="flex flex-wrap gap-x-3 gap-y-0.5 px-3 py-2 text-sm" data-testid="policy-interpretation-ews" data-id={r.rule_id}>
                  <span className="font-mono text-xs font-semibold text-text-primary">{r.rule_id}</span>
                  <span className="font-medium text-text-primary">{r.name}</span>
                  <span className="basis-full text-text-secondary">{r.why}</span>
                </li>
              ))}
            </ul>
          )}
        </div>}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- decision (step 3)

export type DecisionResult =
  | { added: true; document: Doc; pack: PackVersion; effective: string }
  | { added: false; document: Doc; pack: PackVersion };

const HEAD_OF_CREDIT = "noura.alharbi";

/** "Add this to the Cockpit?" with Yes (effective date and approver) and No. Used by the add flow and the document page. */
export function DecisionBlock({ docId, question, showOpen = true, onDecided, className }: {
  docId: string; question?: string; showOpen?: boolean; onDecided?: (r: DecisionResult) => void; className?: string;
}) {
  const { viewingAs, effective } = useCoreAuth();
  const users = useDirectory();
  const [mode, setMode] = React.useState<"ask" | "yes">("ask");
  const [effectiveFrom, setEffectiveFrom] = React.useState<string>(() => todayIso());
  const [approver, setApprover] = React.useState("");
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState<"yes" | "no" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<DecisionResult | null>(null);

  const defaultApprover = users.some((u) => u.username === HEAD_OF_CREDIT) ? HEAD_OF_CREDIT
    : users.some((u) => u.username === effective?.username) ? (effective?.username ?? "") : (users[0]?.username ?? "");
  const approverValue = approver || defaultApprover;
  const readOnly = !!viewingAs;

  async function decide(add: boolean) {
    if (busy || readOnly) return;
    if (add && (!effectiveFrom || !approverValue)) return;
    setBusy(add ? "yes" : "no");
    setError(null);
    try {
      const r = await policy.decision(docId, add
        ? { add: true, effective_from: effectiveFrom, approver: approverValue, note: note.trim() }
        : { add: false, note: note.trim() });
      const out: DecisionResult = add ? { added: true, document: r.document, pack: r.pack, effective: effectiveFrom }
        : { added: false, document: r.document, pack: r.pack };
      setResult(out);
      onDecided?.(out);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(null);
    }
  }

  if (result) {
    const href = `/policy-docs?doc=${encodeURIComponent(docId)}`;
    return (
      <div className={cn("rounded-lg border p-4", result.added ? "border-positive/40 bg-positive-muted" : "border-border bg-surface-sunken", className)}
           role="status" data-testid="policy-decision-result" data-added={result.added ? "true" : "false"}>
        <p className="flex items-start gap-2 text-sm font-medium text-text-primary">
          <CircleCheck className={cn("mt-0.5 size-4 shrink-0", result.added ? "text-positive" : "text-text-muted")} aria-hidden />
          {result.added
            ? <span>Added. Pack {result.pack?.label ?? "—"} is now active from {day(result.pack?.effective_from ?? result.effective)}; {READER_CAP}&apos;s policy checks cite these clauses from now on.</span>
            : <span>Kept on record, not added. The active policy pack and {READER}&apos;s checks are unchanged.</span>}
        </p>
        {showOpen ? (
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link href={href} data-testid="policy-add-open">Open the document</Link>
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border border-accent/30 bg-accent-muted/40 p-4", className)} data-testid="policy-decision">
      <h3 className="text-[15px] font-semibold text-text-primary">{question || `Add this to ${READER}?`}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Yes adds its clauses to the active policy pack as a new version, with an effective date and an approver. Older versions stay on record.
      </p>
      {readOnly ? (
        <p role="alert" className="mt-3 text-sm text-warning" data-testid="policy-readonly">
          You are viewing as {viewingAs?.name}. Stop viewing as to decide on this document.
        </p>
      ) : null}

      {mode === "ask" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setMode("yes")} disabled={readOnly || !!busy} data-testid="policy-add-yes">
            <Check aria-hidden /> Yes, add it
          </Button>
          <Button size="sm" variant="outline" onClick={() => void decide(false)} disabled={readOnly || !!busy} data-testid="policy-add-no">
            {busy === "no" ? <Loader2 className="animate-spin" aria-hidden /> : null} No, keep on record
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor={`policy-effective-${docId}`}>Effective from</Label>
              <Input id={`policy-effective-${docId}`} type="date" value={effectiveFrom} required
                     onChange={(e) => setEffectiveFrom(e.target.value)} data-testid="policy-effective" />
            </div>
            <div>
              <Label htmlFor={`policy-approver-${docId}`}>Approver</Label>
              <Select id={`policy-approver-${docId}`} value={approverValue} onChange={(e) => setApprover(e.target.value)}
                      data-testid="policy-approver" required>
                {users.length === 0 ? <option value="">Loading the directory…</option> : null}
                {users.map((u) => <option key={u.username} value={u.username}>{u.name} · {u.title || u.role}</option>)}
              </Select>
            </div>
          </div>
          <div>
            <Label htmlFor={`policy-note-${docId}`}>Note (optional)</Label>
            <Textarea id={`policy-note-${docId}`} value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
                      placeholder="For example: approved at the Credit Committee of 9 Oct 2026" data-testid="policy-decision-note" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => void decide(true)} disabled={readOnly || !!busy || !effectiveFrom || !approverValue}
                    data-testid="policy-add-confirm">
              {busy === "yes" ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Add to {READER}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("ask")} disabled={!!busy} data-testid="policy-add-cancel">Back</Button>
          </div>
        </div>
      )}
      {error ? <p role="alert" className="mt-3 text-sm text-negative" data-testid="policy-decision-error">{error}</p> : null}
    </div>
  );
}

// ---------------------------------------------------------------- the dialog

const ACCEPT = ".docx,.pdf,.txt,.md";
const ACCEPT_RE = /\.(docx|pdf|txt|md)$/i;
const STEPS = ["Upload", "Interpretation", `Add to ${READER}`];

export function AddPolicyDialog({ onClose, onChanged }: { onClose: () => void; onChanged?: () => void }) {
  const { viewingAs } = useCoreAuth();
  const [file, setFile] = React.useState<File | null>(null);
  const [title, setTitle] = React.useState("");
  const [kind, setKind] = React.useState<DocKind | "">("");
  const [reference, setReference] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [uploaded, setUploaded] = React.useState<{ document: Doc; interpretation: Interpretation } | null>(null);
  const [decided, setDecided] = React.useState(false);
  const [assessment, setAssessment] = React.useState<Assessment | null>(null);  // Round P: the upload read for Deal Desk
  const [applied, setApplied] = React.useState<string | null>(null);
  const readOnly = !!viewingAs;
  const step = !uploaded ? 0 : decided ? 3 : 2;

  const close = React.useCallback(() => { if (!busy) onClose(); }, [busy, onClose]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [close]);

  function pick(f: File | null) {
    setError(null);
    if (f && !ACCEPT_RE.test(f.name)) {
      setFile(null);
      setError("Choose a Word (.docx), PDF (.pdf) or text (.txt, .md) file.");
      return;
    }
    setFile(f);
  }

  async function upload() {
    if (!file || busy || readOnly) return;
    setBusy(true);
    setError(null);
    try {
      const r = await policy.upload(file, { title, kind, reference });
      setUploaded(r);
      onChanged?.();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const doc = uploaded?.document;
  const interp = uploaded?.interpretation ?? doc?.interpretation ?? null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation"
         onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="policy-add-title" data-testid="policy-add-dialog"
           className="flex max-h-[92vh] w-full max-w-4xl flex-col rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h2 id="policy-add-title" className="text-base font-semibold text-text-primary">Add a policy or circular</h2>
            <p className="text-xs text-text-muted">CreditProbe reads it, shows what it changes, and asks before anything reaches {READER}.</p>
          </div>
          <button type="button" onClick={close} aria-label="Close" data-testid="policy-add-close" disabled={busy}
                  className="rounded-md p-1 text-text-muted hover:bg-surface-hover disabled:opacity-50"><X className="size-4" /></button>
        </div>

        <ol className="flex flex-wrap gap-x-5 gap-y-1 border-b border-border px-5 py-2.5 text-xs" aria-label="Steps">
          {STEPS.map((s, i) => {
            const done = i < step;
            const current = i === Math.min(step, 2);
            return (
              <li key={s} className={cn("flex items-center gap-1.5", current ? "font-semibold text-text-primary" : done ? "text-positive" : "text-text-muted")}
                  aria-current={current ? "step" : undefined}>
                <span className={cn("inline-flex size-5 items-center justify-center rounded-full border text-[10px]",
                                    done ? "border-positive bg-positive-muted" : current ? "border-accent bg-accent-muted text-accent" : "border-border")}>
                  {done ? <Check className="size-3" aria-hidden /> : i + 1}
                </span>
                {s}
              </li>
            );
          })}
        </ol>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {readOnly && !uploaded ? (
            <p role="alert" className="mb-3 text-sm text-warning" data-testid="policy-readonly">
              You are viewing as {viewingAs?.name}. Stop viewing as to add a policy or circular.
            </p>
          ) : null}

          {!uploaded ? (
            <div className="space-y-4">
              <div>
                <Label htmlFor="policy-upload-input">Document</Label>
                <label htmlFor="policy-upload-input"
                       className={cn("flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-border-strong px-4 py-5 transition-colors hover:bg-surface-hover",
                                     (busy || readOnly) && "pointer-events-none opacity-60")}>
                  <FileUp className="size-5 shrink-0 text-accent" aria-hidden />
                  <span className="min-w-0 text-sm">
                    <span className="block font-medium text-text-primary">{file ? file.name : "Choose a Word, PDF or text file"}</span>
                    <span className="block text-xs text-text-muted">{file ? `${(file.size / 1024).toFixed(0)} KB` : ".docx, .pdf, .txt or .md"}</span>
                  </span>
                </label>
                <input id="policy-upload-input" type="file" accept={ACCEPT} className="sr-only" disabled={busy || readOnly}
                       onChange={(e) => pick(e.target.files?.[0] ?? null)} data-testid="policy-upload-input" />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="sm:col-span-3">
                  <Label htmlFor="policy-upload-title">Title (optional)</Label>
                  <Input id="policy-upload-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} disabled={busy}
                         placeholder="Read from the document when left empty" data-testid="policy-upload-title" />
                </div>
                <div>
                  <Label htmlFor="policy-upload-kind">Kind</Label>
                  <Select id="policy-upload-kind" value={kind} onChange={(e) => setKind(e.target.value as DocKind | "")} disabled={busy}
                          data-testid="policy-upload-kind">
                    <option value="">Detect from the document</option>
                    <option value="policy">Policy</option>
                    <option value="circular">Circular</option>
                  </Select>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="policy-upload-reference">Reference (optional)</Label>
                  <Input id="policy-upload-reference" value={reference} onChange={(e) => setReference(e.target.value)} maxLength={80} disabled={busy}
                         placeholder="For example C-2026-03" data-testid="policy-upload-reference" />
                </div>
              </div>
              {busy ? (
                <p className="flex items-center gap-2 text-sm text-text-secondary" role="status" data-testid="policy-reading">
                  <Loader2 className="size-4 animate-spin text-accent" aria-hidden /> Reading the document…
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-5">
              {doc ? (
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm"
                     data-testid="policy-uploaded" data-id={doc.id}>
                  <span className="font-semibold text-text-primary">{doc.title}</span>
                  <KindBadge kind={doc.kind} />
                  {doc.reference ? <span className="font-mono text-xs text-text-secondary">{doc.reference}</span> : null}
                  <DocStatusPill status={doc.status} />
                  <span className="text-xs text-text-muted">{clauseWord(doc.clause_count)} · {bookLabel(doc.book)}</span>
                </div>
              ) : null}
              {interp ? <InterpretationView interp={interp} /> : <p className="text-sm text-text-muted">No interpretation was returned for this document.</p>}
              {doc && file ? <DealDeskImpact file={file} doc={doc} onAssessed={setAssessment} /> : null}
              {doc ? (
                <DecisionBlock docId={doc.id} question={interp?.question} onDecided={(r) => {
                  setDecided(true); onChanged?.();
                  if (assessment) {  // Round P: the same decision applies it to Deal Desk's checks and flags the pending deals
                    void rulebook.decide(assessment.id, r.added, "", doc.id).then((x) => setApplied(x.message), (e) => setApplied(friendlyMessage(e)));
                  }
                }} />
              ) : null}
              {applied ? <p role="status" className="text-sm text-text-primary" data-testid="policy-dealdesk-applied">{applied}</p> : null}
            </div>
          )}
          {error ? <p role="alert" className="mt-3 text-sm text-negative" data-testid="policy-add-error">{error}</p> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          {!uploaded ? (
            <>
              <Button variant="ghost" size="sm" onClick={close} disabled={busy} data-testid="policy-add-cancel-dialog">Cancel</Button>
              <Button size="sm" onClick={() => void upload()} disabled={!file || busy || readOnly} data-testid="policy-upload-submit">
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : <FileUp aria-hidden />} Read the document
              </Button>
            </>
          ) : (
            <Button size="sm" variant={decided ? "default" : "outline"} onClick={close} data-testid="policy-add-finish">
              {decided ? "Done" : "Decide later"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
