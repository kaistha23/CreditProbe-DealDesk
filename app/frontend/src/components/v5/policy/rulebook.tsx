"use client";

/**
 * Round P: Policy Docs as the rulebook. Four kinds — Regulation, Internal credit policy, Gold-standard documents, Global rules —
 * on top of R16's library (upload → interpret → approve → versioned pack), and the Deal Desk impact of an upload:
 * the thresholds it sets, the checks and parameters it moves, and the live pipeline with and without it.
 *
 *   <KindTabs view={view} onView={setView} />                       the four kinds (plus All documents, the library as it was)
 *   <DealDeskImpact file={file} doc={doc} onAssessed={setA} />       inside "Add a policy or circular", after the upload
 *   <ImpactPanel a={assessment} decide />                            one assessment, with Apply / Keep on record when pending
 *   <AssessmentsPanel kind="regulation" />  <GoldPanel />  <GlobalRulesPanel />
 */

import Link from "next/link";
import * as React from "react";
import { AlertTriangle, ArrowRight, Check, FileUp, Loader2, Scale, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RulesList } from "@/components/v5/rules/rules-list";
import { cn } from "@/lib/utils";
import { type AssessKind, type Assessment, type Gold, type Kind, assessKindOf, rulebook } from "@/lib/v5/dealdesk-rules";
import { friendlyMessage } from "@/lib/v5/errors";

export type View = "all" | "regulation" | "policy" | "gold" | "rules";
const VIEWS: { id: View; label: string }[] = [
  { id: "all", label: "All documents" }, { id: "regulation", label: "Regulation" }, { id: "policy", label: "Internal credit policy" },
  { id: "gold", label: "Gold-standard documents" }, { id: "rules", label: "Global rules" },
];

function Sub({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{children}</h3>;
}

export function KindTabs({ view, onView }: { view: View; onView: (v: View) => void }) {
  const [kinds, setKinds] = React.useState<Kind[] | null>(null);
  React.useEffect(() => { rulebook.kinds().then((r) => setKinds(r.kinds), () => setKinds(null)); }, [view]);
  const count = (id: View) => kinds?.find((k) => k.id === id)?.count;
  return (
    <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-1" role="tablist" aria-label="Kind of Policy Docs" data-testid="policy-kinds">
      {VIEWS.map((v) => (
        <button key={v.id} type="button" role="tab" aria-selected={view === v.id} onClick={() => onView(v.id)} data-testid={`policy-kind-${v.id}`}
                className={cn("rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                              view === v.id ? "bg-accent-muted text-accent" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary")}>
          {v.label}{count(v.id) !== undefined ? <span className="ml-1.5 text-xs tabular-nums text-text-muted">{count(v.id)}</span> : null}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- the impact of one upload

export function ImpactPanel({ a, decide = false, onDecided }: { a: Assessment; decide?: boolean; onDecided?: (a: Assessment) => void }) {
  const imp = a.impact;
  const [busy, setBusy] = React.useState<"yes" | "no" | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  async function go(approve: boolean) {
    setBusy(approve ? "yes" : "no"); setError(null);
    try { const r = await rulebook.decide(a.id, approve); setMsg(r.message); onDecided?.(r.assessment); }
    catch (e) { setError(friendlyMessage(e)); } finally { setBusy(null); }
  }
  const failing = imp.deals.filter((d) => d.new_failures.length);
  return (
    <div className="space-y-5" data-testid="rulebook-impact" data-id={a.id} data-status={a.status}>
      <section>
        <Sub>Summary for Deal Desk</Sub>
        <p className="text-sm leading-[1.65] text-text-primary" data-testid="rulebook-summary">{a.summary}</p>
        <p className="mt-1 text-xs text-text-muted">{a.reading.method === "model" ? "Read by the AI model; every threshold is quoted from the document." : "Read by CreditProbe's policy reader; every threshold is quoted from the document."}</p>
      </section>

      <section data-testid="rulebook-params">
        <Sub>Thresholds and the Deal Desk checks they move ({imp.parameters.length})</Sub>
        {imp.parameters.length === 0 ? <p className="text-sm text-text-muted">No threshold that a Deal Desk check reads.</p> : (
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader><TableRow><TableHead>Check</TableHead><TableHead>Deals</TableHead><TableHead>In force → proposed</TableHead><TableHead>Clause</TableHead><TableHead>Where it lives today</TableHead></TableRow></TableHeader>
              <TableBody>
                {imp.parameters.map((p) => (
                  <TableRow key={`${p.param}|${p.segment}`} className="align-top" data-testid="rulebook-param" data-param={p.param}>
                    <TableCell className="py-2"><span className="block font-mono text-xs font-semibold">{p.check}</span><span className="text-sm">{p.label}</span></TableCell>
                    <TableCell className="py-2 text-sm">{p.segment === "all" ? "All corporate deals" : p.segment}</TableCell>
                    <TableCell className="py-2 text-sm">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-text-muted">{p.current_display}</span><ArrowRight className="size-3.5 text-warning" aria-label="becomes" />
                        <span className="font-semibold text-text-primary">{p.proposed_display}</span>
                        <Badge variant={p.direction === "tighter" ? "warning" : p.direction === "new" ? "accent" : "default"} className="text-[10px]">{p.direction}</Badge>
                      </span>
                    </TableCell>
                    <TableCell className="py-2 text-sm" title={p.quote}><span className="font-mono text-xs">{p.clause}</span><span className="mt-0.5 block text-xs text-text-muted">“{p.quote.slice(0, 140)}{p.quote.length > 140 ? "…" : ""}”</span></TableCell>
                    <TableCell className="py-2 text-xs text-text-secondary">{p.where}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {a.reading.unread?.length ? (
          <p className="mt-2 text-xs text-text-muted" data-testid="rulebook-unread">
            Also required, with no Deal Desk check today: {a.reading.unread.map((u) => `${u.clause} “${u.quote.slice(0, 90)}${u.quote.length > 90 ? "…" : ""}”`).join("; ")}
          </p>
        ) : null}
      </section>

      <section>
        <Sub>Deal types</Sub>
        <div className="flex flex-wrap gap-1.5" data-testid="rulebook-deal-types">
          {[...imp.deal_types.sectors, ...imp.deal_types.products].map((x) => (
            <span key={x} className="rounded-md border border-border bg-surface-sunken px-2 py-0.5 text-xs text-text-primary">{x}</span>
          ))}
        </div>
      </section>

      <section data-testid="rulebook-pipeline">
        <Sub>Impact on the live pipeline</Sub>
        <p className="flex items-start gap-2 text-[15px] font-semibold text-text-primary" data-testid="rulebook-pipeline-headline">
          <AlertTriangle className={cn("mt-0.5 size-4 shrink-0", imp.pipeline.would_fail ? "text-warning" : "text-positive")} aria-hidden />
          {imp.pipeline.headline}
        </p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-warning/40 bg-warning-muted/40 p-3" data-testid="rulebook-if-applied">
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.06em] text-text-secondary">If applied</p>
            <ul className="list-disc space-y-1 pl-4 text-sm text-text-primary">{imp.if_applied.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div className="rounded-lg border border-border bg-surface-sunken p-3" data-testid="rulebook-if-not">
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.06em] text-text-secondary">If not applied</p>
            <ul className="list-disc space-y-1 pl-4 text-sm text-text-primary">{imp.if_not_applied.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        </div>
        {imp.deals.length ? (
          <div className="mt-3 max-h-[320px] overflow-y-auto rounded-lg border border-border">
            <Table>
              <TableHeader><TableRow><TableHead>Deal</TableHead><TableHead>Sector · product</TableHead><TableHead>Today</TableHead><TableHead>If applied</TableHead><TableHead>Why</TableHead></TableRow></TableHeader>
              <TableBody>
                {[...failing, ...imp.deals.filter((d) => !d.new_failures.length)].map((d) => (
                  <TableRow key={d.proposal_id} className="align-top" data-testid="rulebook-deal-row" data-id={d.proposal_id} data-new-fail={d.new_failures.length ? "true" : "false"}>
                    <TableCell className="py-2 text-sm"><Link href={`/deal-desk/${encodeURIComponent(d.proposal_id)}`} className="font-mono text-xs font-semibold text-accent hover:underline">{d.proposal_id}</Link>
                      <span className="block">{d.customer}</span><span className="block text-xs text-text-muted">{d.rm} · {d.status.replace("_", " ")}</span></TableCell>
                    <TableCell className="py-2 text-sm">{d.sector}<span className="block text-xs text-text-muted">{d.product}</span></TableCell>
                    <TableCell className="py-2"><Badge variant={d.today === "fail" ? "negative" : "positive"} className="text-[10px] uppercase">{d.today}</Badge></TableCell>
                    <TableCell className="py-2"><Badge variant={d.if_applied === "fail" ? "negative" : "positive"} className="text-[10px] uppercase">{d.if_applied}</Badge></TableCell>
                    <TableCell className="py-2 text-xs text-text-secondary">
                      {d.new_failures.map((f) => <span key={f.check} className="block"><span className="font-mono">{f.check}</span> {f.why} ({a.reference || "clause"} {f.clause})</span>)}
                      {!d.new_failures.length && d.already_failing.length ? <span className="block text-text-muted">Already failing: {d.already_failing.map((f) => f.why).join("; ")}</span> : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
        <p className="mt-1 text-[11px] text-text-muted">{imp.method}.</p>
      </section>

      {a.status !== "pending" ? (
        <p className={cn("rounded-lg border p-3 text-sm", a.status === "approved" ? "border-positive/40 bg-positive-muted" : "border-border bg-surface-sunken")}
           role="status" data-testid="rulebook-decided" data-status={a.status}>
          {a.status === "approved"
            ? <>Applied by {a.decided_by || "—"} on {a.decided_at.slice(0, 10)}: {a.flagged} pending deal{a.flagged === 1 ? "" : "s"} flagged with the clause cited; every later deal is checked against it.</>
            : <>Kept on record by {a.decided_by || "—"} on {a.decided_at.slice(0, 10)}; Deal Desk&apos;s checks are unchanged.</>}
          {msg ? <span className="mt-1 block text-text-secondary">{msg}</span> : null}
        </p>
      ) : decide ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/30 bg-accent-muted/40 p-3" data-testid="rulebook-decision">
          <span className="text-[15px] font-semibold text-text-primary">Apply this to Deal Desk?</span>
          <Button size="sm" onClick={() => void go(true)} disabled={!!busy} data-testid="rulebook-approve">
            {busy === "yes" ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Yes, apply and flag the deals</Button>
          <Button size="sm" variant="outline" onClick={() => void go(false)} disabled={!!busy} data-testid="rulebook-reject">
            {busy === "no" ? <Loader2 className="animate-spin" aria-hidden /> : <X aria-hidden />} No, keep on record</Button>
        </div>
      ) : null}
      {error ? <p role="alert" className="text-sm text-negative">{error}</p> : null}
    </div>
  );
}

/** Inside the add flow: the uploaded file read for Deal Desk, once. The add flow's own decision applies it (onAssessed). */
export function DealDeskImpact({ file, doc, onAssessed }: {
  file: File; doc: { id: string; kind: string; title: string; reference: string }; onAssessed?: (a: Assessment) => void;
}) {
  const [a, setA] = React.useState<Assessment | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const once = React.useRef(false);
  React.useEffect(() => {
    if (once.current) return;
    once.current = true;
    rulebook.assess(file, { kind: assessKindOf(doc.kind), reference: doc.reference, policy_doc_id: doc.id })
      .then((r) => { setA(r.assessment); onAssessed?.(r.assessment); }, (e) => setError(friendlyMessage(e)));
  }, [file, doc, onAssessed]);
  return (
    <section className="rounded-lg border border-border p-4" data-testid="policy-dealdesk-impact">
      <h3 className="mb-3 flex items-center gap-2 text-[15px] font-semibold text-text-primary"><Scale className="size-4 text-accent" aria-hidden /> Deal Desk impact</h3>
      {error ? <p role="alert" className="text-sm text-negative">{error}</p> : !a ? (
        <p className="flex items-center gap-2 text-sm text-text-secondary" role="status"><Loader2 className="size-4 animate-spin text-accent" aria-hidden /> Running Deal Desk&apos;s checks on every pending deal, with and without it…</p>
      ) : <ImpactPanel a={a} />}
    </section>
  );
}

/** The document page: its Deal Desk assessment(s), decidable while pending. */
export function DocImpact({ docId }: { docId: string }) {
  const [rows, setRows] = React.useState<Assessment[] | null>(null);
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    rulebook.assessments({ policy_doc_id: docId }).then(async (r) => {
      const full = await Promise.all(r.assessments.map((x) => rulebook.assessment(x.id).then((y) => y.assessment)));
      setRows(full);
    }, () => setRows([]));
  }, [docId, tick]);
  if (!rows || rows.length === 0) return null;
  return (
    <Card className="space-y-3 p-4" data-testid="policy-doc-impact">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold"><Scale className="size-4 text-accent" aria-hidden /> Deal Desk impact</h2>
      {rows.map((a) => <ImpactPanel key={a.id} a={a} decide onDecided={() => setTick((n) => n + 1)} />)}
    </Card>
  );
}

// ---------------------------------------------------------------- Regulation and Internal credit policy

export function AssessmentsPanel({ kind }: { kind: AssessKind }) {
  const [rows, setRows] = React.useState<Assessment[] | null>(null);
  const [open, setOpen] = React.useState<Assessment | null>(null);
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => { rulebook.assessments({ kind }).then((r) => setRows(r.assessments), () => setRows([])); }, [kind, tick]);
  const word = kind === "regulation" ? "regulation or circular" : "credit policy";
  return (
    <Card className="space-y-3 p-4" data-testid={`rulebook-assessments-${kind}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Scale className="size-4 text-accent" aria-hidden />
        <h2 className="text-[15px] font-semibold text-text-primary">Read for Deal Desk</h2>
        <span className="text-xs text-text-muted">Each {word} added here is summarised, run against every pending deal, and applied only when approved.</span>
      </div>
      {!rows ? <p className="text-sm text-text-muted">Loading…</p> : rows.length === 0 ? (
        <p className="text-sm text-text-muted">None yet. Use “Add a policy or circular”: CreditProbe reads it and shows its impact on the pipeline before anything changes.</p>
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {rows.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => { if (open?.id === a.id) setOpen(null); else void rulebook.assessment(a.id).then((r) => setOpen(r.assessment)); }}
                      className="grid w-full gap-1 px-3 py-2 text-left text-sm hover:bg-surface-hover md:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_110px]"
                      data-testid="rulebook-assessment-row" data-id={a.id} data-status={a.status}>
                <span className="font-medium text-text-primary">{a.title}{a.reference ? <span className="ml-2 font-mono text-xs text-text-muted">{a.reference}</span> : null}</span>
                <span className="text-text-secondary">{a.impact.pipeline?.headline}</span>
                <span><Badge variant={a.status === "approved" ? "positive" : a.status === "pending" ? "warning" : "default"} className="text-[10px] uppercase">{a.status === "approved" ? "applied" : a.status}</Badge></span>
              </button>
              {open?.id === a.id ? <div className="border-t border-border p-3"><ImpactPanel a={open} decide onDecided={(x) => { setOpen(x); setTick((n) => n + 1); }} /></div> : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- Gold-standard documents

export function GoldPanel() {
  const [list, setList] = React.useState<Gold[] | null>(null);
  const [cur, setCur] = React.useState<Gold | null>(null);
  const [pick, setPick] = React.useState<Set<string>>(new Set());
  const [busy, setBusy] = React.useState<string | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => { rulebook.gold().then((r) => setList(r.gold), () => setList([])); }, [tick]);
  const show = (g: Gold) => { setCur(g); setPick(new Set(g.comparison.differences.map((d) => d.id))); setMsg(null); };
  async function upload(f: File | null) {
    if (!f) return;
    setBusy("upload"); setError(null);
    try { const r = await rulebook.goldUpload(f); show(r.gold); setTick((n) => n + 1); } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(null); }
  }
  async function apply() {
    if (!cur) return;
    setBusy("apply"); setError(null);
    try { const r = await rulebook.goldApply(cur.id, [...pick]); setCur(r.gold); setMsg(r.message); setTick((n) => n + 1); }
    catch (e) { setError(friendlyMessage(e)); } finally { setBusy(null); }
  }
  return (
    <div className="space-y-4" data-testid="rulebook-gold">
      <Card className="space-y-3 p-4">
        <h2 className="text-[15px] font-semibold text-text-primary">Gold-standard documents</h2>
        <p className="text-sm text-text-secondary">A proposal the bank considers ideal. CreditProbe compares it with how it writes the credit proposal today (section order, content, headings, units, wording, tone) and proposes the rules that would close the gap.</p>
        <label className={cn("flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-border-strong px-4 py-4 hover:bg-surface-hover", busy && "pointer-events-none opacity-60")}>
          {busy === "upload" ? <Loader2 className="size-5 animate-spin text-accent" aria-hidden /> : <FileUp className="size-5 text-accent" aria-hidden />}
          <span className="text-sm font-medium text-text-primary">{busy === "upload" ? "Comparing with how CreditProbe writes today…" : "Upload a gold-standard proposal (.docx, .pdf, .txt)"}</span>
          <input type="file" accept=".docx,.pdf,.txt,.md" className="sr-only" data-testid="rulebook-gold-input" onChange={(e) => void upload(e.target.files?.[0] ?? null)} />
        </label>
        {error ? <p role="alert" className="text-sm text-negative">{error}</p> : null}
      </Card>
      {cur ? (
        <Card className="space-y-3 p-4" data-testid="rulebook-gold-compare" data-id={cur.id} data-status={cur.status}>
          <p className="text-[15px] font-semibold text-text-primary">{cur.title}</p>
          <p className="text-sm text-text-secondary" data-testid="rulebook-gold-summary">{cur.comparison.summary}</p>
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader><TableRow><TableHead className="w-8" /><TableHead>Difference</TableHead><TableHead>Today</TableHead><TableHead>Gold standard</TableHead><TableHead>Rule if applied</TableHead></TableRow></TableHeader>
              <TableBody>
                {cur.comparison.differences.map((d) => (
                  <TableRow key={d.id} className="align-top" data-testid="rulebook-gold-diff" data-area={d.area}>
                    <TableCell className="py-2"><input type="checkbox" aria-label={`Apply ${d.id}`} disabled={cur.status !== "pending"} checked={pick.has(d.id)}
                      onChange={(e) => setPick((p) => { const n = new Set(p); if (e.target.checked) n.add(d.id); else n.delete(d.id); return n; })} /></TableCell>
                    <TableCell className="py-2 text-sm"><Badge variant="outline" className="mr-1 text-[10px] uppercase">{d.area}</Badge>{d.finding}</TableCell>
                    <TableCell className="py-2 text-xs text-text-secondary">{d.today}</TableCell>
                    <TableCell className="py-2 text-xs text-text-primary">{d.gold}</TableCell>
                    <TableCell className="py-2 text-xs text-text-secondary">{d.rule.text}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {cur.status === "pending" && cur.comparison.differences.length ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/30 bg-accent-muted/40 p-3">
              <span className="text-[15px] font-semibold">Apply these?</span>
              <span className="text-xs text-text-secondary">{pick.size} become the bank&apos;s rules; the document joins the house-style corpus.</span>
              <Button size="sm" className="ml-auto" disabled={!!busy || pick.size === 0} onClick={() => void apply()} data-testid="rulebook-gold-apply">
                {busy === "apply" ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Yes, apply {pick.size}</Button>
              <Button size="sm" variant="outline" disabled={!!busy} data-testid="rulebook-gold-dismiss"
                      onClick={() => void rulebook.goldDismiss(cur.id).then((r) => { setCur(r.gold); setTick((n) => n + 1); })}>No</Button>
            </div>
          ) : (
            <p className="text-sm text-text-secondary" role="status" data-testid="rulebook-gold-result">
              {msg ?? (cur.status === "applied" ? `Applied by ${cur.applied_by}: ${cur.applied.length} rules (see Global rules).` : cur.status === "dismissed" ? "Dismissed: nothing changed." : "")}
            </p>
          )}
        </Card>
      ) : null}
      {list && list.length ? (
        <Card className="p-0">
          <ul className="divide-y divide-border">
            {list.map((g) => (
              <li key={g.id}><button type="button" className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-surface-hover" data-testid="rulebook-gold-row"
                                     onClick={() => show(g)}>
                <span className="font-medium">{g.title}</span><span className="text-text-muted">{g.comparison.differences.length} differences</span>
                <Badge variant={g.status === "applied" ? "positive" : g.status === "pending" ? "warning" : "default"} className="ml-auto text-[10px] uppercase">{g.status}</Badge>
              </button></li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- Global rules

export function GlobalRulesPanel() {
  return (
    <div className="space-y-3" data-testid="rulebook-global-rules">
      <Card className="p-4">
        <h2 className="text-[15px] font-semibold text-text-primary">Global rules</h2>
        <p className="mt-1 text-sm text-text-secondary">
          The bank&apos;s writing rules, applied to every credit request and credit proposal CreditProbe drafts, and listed under “Rules applied” on each document.
          The first twelve are seeded from the style of the two SIB proposals (synthetic stand-ins until SIB&apos;s documents arrive); rules approved from a gold standard
          and analysts&apos; rules saved for the bank join them. The Head of Credit and the risk team can change them.
        </p>
      </Card>
      <RulesList scope="bank" addScope="bank" testId="global-rules" />
    </div>
  );
}
