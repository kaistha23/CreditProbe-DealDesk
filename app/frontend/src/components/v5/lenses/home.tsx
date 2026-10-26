"use client";

/**
 * Lenses home (PLAN_R5 L1.1): a large chat box on top that builds a lens from a request, the Corporate/Retail
 * toggle, and below it the saved lenses (mine, shared with me, templates) as cards with thumbnails.
 * Asking (or opening a template) creates the lens and goes straight to it; its thread shows the process trace.
 */

import { landingQuestion, rememberPendingMemo } from "@/lib/v5/thread-actions-pending";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { BookOpen, Paperclip } from "lucide-react";

import { PlotlySpark } from "@/components/answer/spark";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useEws as useLoad } from "@/lib/v5/ews";
import { BOOK_WORD, type Book, type Card as LensCard, lenses, when } from "@/lib/v5/lenses";
import { friendlyMessage } from "@/lib/v5/errors";
import { startFresh } from "@/lib/v5/thread-rule";

import { CREATE_WORDS, CrmLibraryPanel, CrmUploadThread } from "./crm";
import { MetricPlanCard } from "./metric-plan"; // R16 M5: persona requests show a metric plan first
import { type MetricPlan, isPlan, mentionsPersona } from "@/lib/v5/lenses-plan";
import { MonitoringAgentButton, monitorTabOf } from "./monitoring";
import { ModuleLanding } from "@/components/v5/landing/module-landing";
import { PortfolioToolsMenu } from "@/components/v5/intel/portfolio"; // R13 ID

export function Spark({ values, className, ariaLabel = "Trend" }: { values: (number | null)[]; className?: string; ariaLabel?: string }) {
  const measured = values.filter((v) => typeof v === "number" && Number.isFinite(v));
  if (measured.length < 2) return null;
  return <PlotlySpark values={values} height={28} className={cn("h-7 w-full", className)} ariaLabel={ariaLabel} />;
}

function LensCardView({ card, onOpen, busy, prefix = "lens-card" }: { card: LensCard; onOpen: (c: LensCard) => void; busy: boolean; prefix?: string }) {
  return (
    <button type="button" onClick={() => onOpen(card)} disabled={busy} data-testid={`${prefix}-${card.kind !== "lens" ? card.template_key : card.lens_id}`}
            data-lens={card.lens_id} className="text-left disabled:opacity-60">
      <Card className="flex h-full flex-col gap-2 p-3 transition-colors hover:border-accent">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-text-primary">{card.name}</p>
            <p className="truncate text-[11px] text-text-muted">{BOOK_WORD[card.book]} · {/ book$/.test(card.scope_label) ? "Whole book" : card.scope_label} · {card.tiles} tiles</p>
          </div>
          {card.kind === "featured" ? <span className="rounded-full border border-accent px-2 py-0.5 text-[10px] text-accent">Featured</span>
            : card.kind === "template" ? <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-text-muted">Template</span>
            : !card.saved ? <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-text-muted">Draft</span> : null}
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1" data-testid="lens-card-thumb">
          {card.thumb.figures.map((f) => (
            <div key={f.label} className="min-w-0">
              <p className="truncate text-[10px] uppercase tracking-wide text-text-muted">{f.label}</p>
              <p className="text-[12px] font-semibold tabular-nums text-text-primary">{f.display}</p>
            </div>))}
        </div>
        <Spark values={card.thumb.spark} ariaLabel={`${card.name} trend`} />
        <p className="mt-auto truncate text-[11px] text-text-muted">{card.kind !== "lens" ? card.description : `${card.owner || "CreditProbe"} · ${when(card.updated_at)}`}</p>
      </Card>
    </button>
  );
}

function Section({ title, cards, empty, onOpen, busy, testId }: { title: string; cards: LensCard[]; empty: string; onOpen: (c: LensCard) => void;
  busy: boolean; testId: string }) {
  if (!cards.length && !empty) return null;
  return (
    <section className="space-y-2" data-testid={testId}>
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">{title}</h2>
      {cards.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4" data-testid={`${testId}-grid`}>
          {cards.map((c) => <LensCardView key={c.lens_id} card={c} onOpen={onOpen} busy={busy} prefix={testId === "lenses-featured" ? "lens-featured-card" : "lens-card"} />)}
        </div>) : <p className="text-[12px] text-text-muted">{empty}</p>}
    </section>
  );
}

export function LensesHome() {
  const router = useRouter();
  const params = useSearchParams();
  const book: Book = params.get("book") === "retail" ? "retail" : "corporate";
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const list = useLoad(() => lenses.list(book), `list-${book}`);
  const meta = useLoad(() => lenses.meta(book), `meta-${book}`);
  const [crmFile, setCrmFile] = React.useState<File | null>(null);
  const [crmKey, setCrmKey] = React.useState(0);
  const [createSignal, setCreateSignal] = React.useState(0);
  const [dragging, setDragging] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);
  const showLibrary = params.get("tab") === "library";
  const attach = (f: File | null | undefined) => { if (f) { setCrmFile(f); setCrmKey((k) => k + 1); setDraft(""); setError(""); } };

  const setBook = (b: Book) => router.replace(b === "corporate" ? "/lenses" : "/lenses?book=retail");

  // R16 M5: "CRO dashboard", "dashboard for an analyst": the plan first, the lens on "Build this dashboard"
  const [plan, setPlan] = React.useState<MetricPlan | null>(null);
  const build = async (body: { request?: string; template?: string; plan?: { persona: string; include: string[] } }) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      // R16 m (M6): every landing question, template or featured card is a NEW lens with its own NEW thread.
      // R16 t (M7): "give me a paper on X" builds the lens for X; its thread writes the Word paper once answered
      const lq = body.request ? landingQuestion(body.request) : null;
      const out = await lenses.create(startFresh("lenses", { ...body, ...(lq?.memo ? { request: lq.ask } : {}), book: body.request ? book : undefined }));
      if (lq?.memo && out.thread_id) rememberPendingMemo("lenses", out.thread_id, lq.memo);
      router.push(`/lenses/${out.lens.lens_id}`);
    } catch (e) { setError(friendlyMessage(e)); setBusy(false); }
  };
  const ask = (text: string) => {
    const q = text.trim();
    if (!q) return;
    // PLAN_R9 D3: after a circular is read in this chat, "create the dashboard" builds the CBUAE CRM lens
    if (crmFile && CREATE_WORDS.test(q)) { setDraft(""); setCreateSignal((n) => n + 1); return; }
    if (mentionsPersona(q)) { void planFor(q); return; }
    setPlan(null);
    void build({ request: q });
  };
  const planFor = async (q: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await lenses.plan({ request: q, book });
      setBusy(false);
      if (isPlan(r)) { setPlan(r); setCrmFile(null); return; }
      setPlan(null);
      void build({ request: q });
    } catch (e) { setError(friendlyMessage(e)); setBusy(false); }
  };
  const open = (c: LensCard) => {
    if (c.kind === "template" || c.kind === "featured") void build({ template: c.lens_id });
    else router.push(`/lenses/${c.lens_id}`);
  };

  return (
    <div className="space-y-6" data-testid="lenses-home">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-text-primary">Lenses</h1>
            <InfoPopover title="About Lenses">
              <p>A lens is a live dashboard you build by asking for it. Every figure is a query on the books, with its trace under the (i).
                Edit a lens by conversation (&ldquo;add DSCR distribution&rdquo;, &ldquo;show by region instead&rdquo;) or by hand from each tile&rsquo;s menu,
                then save, share, add it to a Playbook report or export it.</p>
            </InfoPopover>
          </div>
        </div>
        <div className="flex items-center gap-2">
        <button type="button" onClick={() => router.replace(showLibrary ? "/lenses" : "/lenses?tab=library")} data-testid="lenses-library"
                aria-pressed={showLibrary}
                className={cn("inline-flex items-center gap-1 rounded-md border px-3 py-1 text-[12px] font-medium",
                              showLibrary ? "border-accent bg-accent text-accent-contrast" : "border-border text-text-secondary hover:bg-surface-hover")}>
          <BookOpen size={13} /> Library</button>
        <MonitoringAgentButton key={book} scope={{ book, filters: [] }} initialTab={monitorTabOf(params.get("monitor"))}
                               className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-[12px] font-medium text-text-secondary hover:bg-surface-hover" />
        <PortfolioToolsMenu menu="lenses" />{/* R13 ID: portfolio tools */}
        <div className="inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Book">
          {(["corporate", "retail"] as Book[]).map((b) => (
            <button key={b} type="button" onClick={() => setBook(b)} data-testid={`lenses-book-${b}`} aria-pressed={book === b}
                    className={cn("rounded px-3 py-1 text-[12px] font-medium", book === b ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
              {BOOK_WORD[b]}</button>))}
        </div>
        </div>
      </div>

      {showLibrary ? <CrmLibraryPanel onClose={() => router.replace("/lenses")} /> : null}

      {/* R13 X (J7): the centred chat box (drop a circular on it) and small cards of your recent lenses; the library below. */}
      <ModuleLanding ids="lenses" title="Ask for a lens" value={draft} onChange={setDraft} onAsk={ask} busy={busy} error={error}
                     sendTestId="lenses-build" submitLabel="Build lens" rows={2}
                     placeholder={crmFile ? "Type 'create the dashboard', or ask for another lens"
                       : "Ask for a dashboard, or drop a circular here"}
                     examples={(meta.data?.examples ?? []).slice(0, 5)}
                     status={busy ? <span data-testid="lenses-building">Building the lens…</span> : null}
                     above={crmFile ? <CrmUploadThread key={crmKey} file={crmFile} book={book} createSignal={createSignal} onReset={() => setCrmFile(null)} />
                       : plan ? <MetricPlanCard key={`${plan.persona}-${plan.book}-${plan.request}`} plan={plan} busy={busy} onCancel={() => setPlan(null)}
                                                onBuild={(include) => void build({ request: plan.request, plan: { persona: plan.persona, include } })} /> : null}
                     dropTarget={{ dragging, onDragOver: (e) => { e.preventDefault(); setDragging(true); }, onDragLeave: () => setDragging(false),
                                   onDrop: (e) => { e.preventDefault(); setDragging(false); attach(e.dataTransfer.files?.[0]); } }}
                     leading={<>
                       <input ref={fileInput} type="file" accept=".pdf,.docx,.txt,.md" className="hidden" data-testid="lenses-upload-input"
                              onChange={(e) => { attach(e.target.files?.[0]); e.target.value = ""; }} />
                       <button type="button" onClick={() => fileInput.current?.click()} data-testid="lenses-attach" title="Upload a circular" aria-label="Upload a circular"
                               className="inline-flex size-8 items-center justify-center rounded-full border border-border text-text-secondary hover:border-accent hover:text-accent">
                         <Paperclip size={15} /></button></>}
                     recentTitle="Recent lenses" recentLoading={list.loading}
                     recent={[...(list.data?.mine ?? []), ...(list.data?.shared ?? [])].sort((x, y) => (y.updated_at ?? 0) - (x.updated_at ?? 0)).slice(0, 6).map((c) => ({
                       key: c.lens_id, title: c.name, testId: `lens-recent-${c.lens_id}`,
                       sub: `${BOOK_WORD[c.book]} · ${/ book$/.test(c.scope_label) ? "Whole book" : c.scope_label}`,
                       meta: `${c.owner || "CreditProbe"} · ${when(c.updated_at)}`, onOpen: () => open(c) }))} />

      {list.loading ? <Skeleton className="h-48 w-full" /> : list.error ? <p className="text-[13px] text-negative" role="alert">{list.error}</p> : list.data ? (
        <div className="space-y-6">
          <Section title="Featured" cards={list.data.featured ?? []} empty="" onOpen={open} busy={busy} testId="lenses-featured" />
          <Section title="My lenses" cards={list.data.mine} empty="Lenses you build or save appear here." onOpen={open} busy={busy} testId="lenses-mine" />
          <Section title="Shared with me" cards={list.data.shared} empty="Nothing shared with you yet." onOpen={open} busy={busy} testId="lenses-shared" />
          <Section title="Templates" cards={list.data.templates} empty="No templates for this book." onOpen={open} busy={busy} testId="lenses-templates" />
        </div>) : null}
    </div>
  );
}
