"use client";

/**
 * The Playbook home: committee packs, risk reports, credit memos, scenario and validation reports.
 *
 * At the top, a chat box: "draft a credit memo for CB01312" starts a report and opens it; a question is
 * answered in place. Below it, the ways to start a document (a template, or an uploaded Word or PDF file),
 * then every report the reader can see, with its workflow status (Draft, In review, Approved, Presented),
 * owner, reviewers and due date.
 */

import { MicButton } from "@/components/noor/mic-button";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import {
  Building2, ClipboardCheck, FileText, FileUp, FlaskConical, Landmark, Loader2, PieChart, Search, Send, ShieldAlert, Sparkles, X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { useCoreAuth } from "@/components/v5/core/auth";
import { ErrorBox, Loading, SectionTitle } from "@/components/v5/workspace/parts";
import { cn } from "@/lib/utils";
import {
  type Book, type Message, type ReportRow, type ReportStatus, type Template, BOOK_LABEL, STATUS_LABEL, TEMPLATE_FALLBACK, WORKFLOW,
  playbook, reportHref,
} from "@/lib/v5/playbook";
import { day, useWs } from "@/lib/v5/workspace";

import { AnswerExtras, MessageText } from "./ai-thread";
import { PlaybookStartThread } from "./start-thread";
import { CommitteePlaybooks } from "./committee";
import { Initials, PeopleStack, ReportStatusPill, ReviewerPicker } from "./blocks";
import { PlaybookReport } from "./report";
import { friendlyMessage } from "@/lib/v5/errors";
import { backOr } from "@/lib/v5/back";
import { threadIdFor } from "@/lib/v5/thread-rule";

/** `/playbook` shows the home; `/playbook?report=<id>` shows that report. */
export function PlaybookScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const report = params.get("report");
  const thread = params.get("thread");
  // Asking from the home chat box opens the thread (PLAN_R5 G4). R7: the question is pushed into the address
  // (?ask=), so the home stays in history and Back returns to it; once the first answer is in, the thread id (or the
  // new report) replaces ?ask=, so the question is never asked twice.
  const asked = thread ? null : params.get("ask");
  if (report) return <PlaybookReport id={report} />;
  if (thread || asked) {
    return <PlaybookStartThread key="start" threadId={thread} initial={asked}
                                onBack={() => backOr(router, () => router.push("/playbook"))} />;
  }
  return <PlaybookHome onAsk={(q) => router.push(`/playbook?ask=${encodeURIComponent(q)}`)} />;
}

const SUGGESTIONS = [
  "I want to draft a corporate ECL report",
  "Draft a credit memo for CB01312",
  "Start the Q2 2026 credit committee pack",
  "Prepare a risk committee report on the corporate book",
  "Write a scenario report on the rating downgrade scenario",
];

export const TEMPLATE_ICON: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  "credit-committee-pack": Landmark,
  "risk-committee-report": ShieldAlert,
  "portfolio-review": PieChart,
  "borrower-credit-memo": Building2,
  "scenario-report": FlaskConical,
  "validation-report": ClipboardCheck,
};
const TEMPLATE_ORDER = ["credit-committee-pack", "risk-committee-report", "portfolio-review", "borrower-credit-memo", "scenario-report", "validation-report"];

function templateColour(id: string): string {
  const i = TEMPLATE_ORDER.indexOf(id);
  return `var(--ipm-chart-${(i < 0 ? 7 : i) + 1})`;
}

export function PlaybookHome({ onAsk }: { onAsk?: (q: string) => void }) {
  const { effective } = useCoreAuth();
  const viewer = effective?.username ?? "";
  const reports = useWs(() => playbook.reports(), `pb-reports|${viewer}`);
  const summary = useWs(() => playbook.summary(), `pb-summary|${viewer}`);
  const templates = useWs(() => playbook.templates(), "pb-templates");
  const [starting, setStarting] = React.useState<Template | null>(null);

  const templateList = React.useMemo(() => {
    const list = templates.data?.templates?.length ? templates.data.templates : templates.error ? TEMPLATE_FALLBACK : [];
    return [...list].sort((a, b) => rank(a.id) - rank(b.id));
  }, [templates.data, templates.error]);

  const s = summary.data;
  const total = reports.data?.reports?.length ?? null;
  return (
    <div className="space-y-5" data-testid="playbook-home" data-tour="playbook-home">
      <header className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold text-text-primary">Playbook</h1>
        <InfoPopover>
          Committee packs, risk reports and credit memos, drafted with the assistant from the books, imported from any screen,
          reviewed, approved and exported to Word.
        </InfoPopover>
      </header>

      <ChatBox onAsk={onAsk} />

      {s ? (
        <div className="grid grid-cols-4 gap-3" data-testid="playbook-summary">
          <Figure label="Awaiting my review" value={s.awaiting_my_review} sub="reports to review" tone={s.awaiting_my_review ? "warning" : undefined} />
          <Figure label="My reports" value={s.mine} sub={total !== null ? `${s.mine} of ${total} reports` : "owned by you"} />
          <Figure label="In review" value={s.by_status?.in_review ?? 0} sub={total !== null ? `${s.by_status?.in_review ?? 0} of ${total} reports` : "with reviewers"} />
          <Figure label="Overdue" value={s.overdue} sub="past the due date" tone={s.overdue ? "negative" : undefined} />
        </div>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <CommitteePlaybooks />

        <section data-testid="playbook-start">
          <SectionTitle>Start a document</SectionTitle>
          {templates.loading && !templateList.length ? <Loading what="Loading the templates…" /> : (
            <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
              {templateList.map((t) => {
                const Icon = TEMPLATE_ICON[t.id] ?? FileText;
                const colour = templateColour(t.id);
                return (
                  <li key={t.id}>
                    <button type="button" onClick={() => setStarting(t)} data-testid={`playbook-template-${t.id}`} title={t.description}
                            className="group flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-surface-hover">
                      <Icon className="size-4 shrink-0" style={{ color: colour }} aria-hidden />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-text-primary group-hover:text-accent">{t.name}</span>
                      <span className="shrink-0 text-[11px] tabular-nums text-text-muted">{(t.sections ?? []).length} sections</span>
                    </button>
                  </li>
                );
              })}
              <li><UploadCard /></li>
            </ul>
          )}
          {templates.error ? <p className="mt-2 text-[11px] text-text-muted">The standard templates are shown.</p> : null}
        </section>
      </div>

      <ReportList rows={reports.data?.reports ?? null} error={reports.error} />

      {starting ? <NewReportDialog template={starting} onClose={() => setStarting(null)} /> : null}
    </div>
  );
}

function rank(id: string): number {
  const i = TEMPLATE_ORDER.indexOf(id);
  return i < 0 ? 99 : i;
}

function Figure({ label, value, sub, tone }: { label: string; value: number; sub: string; tone?: "warning" | "negative" }) {
  return (
    <Card className="min-w-0 px-3.5 py-2.5" data-testid="playbook-kpi">
      <p className="truncate text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{label}</p>
      <p className={cn("text-[20px] font-bold leading-tight tabular-nums text-text-primary",
                       tone === "warning" && "text-warning", tone === "negative" && "text-negative")}>{value ?? 0}</p>
      <p className="truncate text-[11px] text-text-muted">{sub}</p>
    </Card>
  );
}

// ---------------------------------------------------------------- chat box

function ChatBox({ onAsk }: { onAsk?: (q: string) => void }) {
  const router = useRouter();
  const { viewingAs } = useCoreAuth();
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [threadId, setThreadId] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  async function send(raw: string) {
    const q = raw.trim();
    if (!q || busy) return;
    if (onAsk) { onAsk(q); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await playbook.start(q, threadIdFor("thread", threadId));  // this box is its own open thread (M6)
      if (r.report?.id) {
        router.push(reportHref(r.report.id));
        return;
      }
      setThreadId(r.thread_id);
      setMessages((m) => [...m, ...(r.messages ?? [])]);
      setText("");
      setBusy(false);
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  }

  const last = [...messages].reverse().find((m) => m.role === "assistant");
  return (
    <Card className="space-y-2.5 p-3 sm:p-4" data-testid="playbook-chat">
      {/* G-CHAT: the input and Send share one row; Send sits at its right end and never covers the chips below. */}
      <form onSubmit={(e) => { e.preventDefault(); void send(text); }} data-testid="playbook-chat-row"
            className="flex items-end gap-2 rounded-2xl border border-border-strong bg-surface p-2 pl-3 shadow-[0_1px_3px_rgb(0_0_0/0.06)] transition-colors focus-within:border-accent">
        <Sparkles className="mb-2.5 hidden size-4 shrink-0 text-accent sm:block" aria-hidden />
        <textarea ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} rows={2} disabled={busy}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); } }}
                  aria-label="Ask Playbook" data-testid="playbook-chat-input"
                  placeholder="Start or continue a document, e.g. “a credit memo”"
                  className="block min-h-[52px] min-w-0 flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-relaxed text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-60" />
        <MicButton value={text} onChange={setText} size="md" testId="playbook-mic" className="mb-1" />
        <Button type="submit" size="sm" disabled={busy || !text.trim()} data-testid="playbook-chat-send" aria-label="Send to Playbook"
                className="shrink-0 rounded-full px-4">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />} {busy ? "Working…" : "Send"}
        </Button>
      </form>
      <div className="flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((sug) => (
          <button key={sug} type="button" disabled={busy} data-testid="playbook-chat-suggestion"
                  onClick={() => { setText(sug); inputRef.current?.focus(); }}
                  className="rounded-full border border-border bg-surface px-2.5 py-0.5 text-[12px] text-text-secondary transition-colors hover:border-accent hover:text-accent disabled:opacity-50">
            {sug}
          </button>
        ))}
      </div>
      {viewingAs ? <p className="text-xs text-warning" role="alert">You are viewing as {viewingAs.name}: Playbook is read only until you stop viewing as.</p> : null}
      {error ? <p className="text-sm text-negative" role="alert" data-testid="playbook-chat-error">{error}</p> : null}
      {messages.length ? (
        <div className="space-y-2 border-t border-border pt-3" data-testid="playbook-chat-reply">
          {messages.map((m) => (
            <div key={m.id} className={cn("flex flex-col gap-1.5", m.role === "user" ? "items-end" : "items-start")}
                 data-testid="playbook-chat-message" data-role={m.role}>
              <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed",
                                 m.role === "user" ? "bg-accent text-accent-contrast" : "border border-border bg-surface-sunken text-text-primary")}>
                <MessageText text={m.text} role={m.role} />
              </div>
              {m.role === "assistant" ? (
                <div className="w-full max-w-[85%]">
                  <AnswerExtras message={m} busy={busy} onSend={m.id === last?.id ? (t) => void send(t) : undefined} />
                </div>
              ) : null}
            </div>
          ))}
          {busy ? <p className="flex items-center gap-2 text-xs text-text-muted" data-testid="playbook-chat-working"><Loader2 className="size-3.5 animate-spin" aria-hidden /> Working on it…</p> : null}
          {last?.suggestions?.length && !busy ? (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {last.suggestions.map((sug) => (
                <button key={sug} type="button" onClick={() => void send(sug)} data-testid="playbook-chat-followup"
                        className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-[12px] text-text-secondary hover:border-accent hover:text-accent">
                  {sug}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------- upload

function UploadCard() {
  const router = useRouter();
  const { viewingAs } = useCoreAuth();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [over, setOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  async function upload(file: File | null | undefined) {
    if (!file || busy) return;
    if (!/\.(docx|pdf|txt|md)$/i.test(file.name)) { setError("Choose a Word (.docx) or PDF file."); return; }
    if (file.size > 15 * 1024 * 1024) { setError("The file is larger than 15 MB."); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await playbook.upload(file);
      router.push(reportHref(r.id));
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <label data-testid="playbook-upload"
           onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); void upload(e.dataTransfer.files?.[0]); }}
           title="Drop a Word or PDF file here: its headings become the sections"
           className={cn("flex cursor-pointer items-center gap-2.5 px-3 py-2 transition-colors",
                         over ? "bg-accent-muted" : "hover:bg-surface-hover",
                         (busy || viewingAs) && "pointer-events-none opacity-60")}>
      <input ref={inputRef} type="file" className="sr-only" accept=".docx,.pdf,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             aria-label="Upload a Word or PDF document" data-testid="playbook-upload-input" disabled={busy || !!viewingAs}
             onChange={(e) => void upload(e.target.files?.[0])} />
      {busy ? <Loader2 className="size-4 shrink-0 animate-spin text-text-secondary" aria-hidden /> : <FileUp className="size-4 shrink-0 text-text-secondary" aria-hidden />}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-text-primary">{busy ? "Reading the document…" : "Upload a .docx or .pdf"}</span>
        {error ? <span className="block text-xs text-negative" role="alert" data-testid="playbook-upload-error">{error}</span> : null}
      </span>
    </label>
  );
}

// ---------------------------------------------------------------- new report

const fieldClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none";

function NewReportDialog({ template, onClose }: { template: Template; onClose: () => void }) {
  const router = useRouter();
  const { viewingAs, effective } = useCoreAuth();
  const defaultBook: Book = effective?.books?.length === 1 ? effective.books[0] : "corporate";
  const [title, setTitle] = React.useState(template.name);
  const [book, setBook] = React.useState<Book>(defaultBook);
  const [period, setPeriod] = React.useState("");
  const [due, setDue] = React.useState("");
  const [reviewers, setReviewers] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  async function create() {
    if (!title.trim() || busy || viewingAs) return;
    setBusy(true);
    setError(null);
    try {
      const r = await playbook.createReport({
        title: title.trim(), template: template.id, book, period: period.trim(), due_date: due || null, reviewers,
      });
      router.push(reportHref(r.id));
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  }

  const Icon = TEMPLATE_ICON[template.id] ?? FileText;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form role="dialog" aria-modal="true" aria-label={`New ${template.name}`} data-testid="playbook-new-dialog"
            onSubmit={(e) => { e.preventDefault(); void create(); }}
            className="w-full max-w-[540px] space-y-4 rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start gap-3">
          <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg"
                style={{ background: `color-mix(in oklab, ${templateColour(template.id)} 14%, transparent)` }}>
            <Icon className="size-[18px]" style={{ color: templateColour(template.id) }} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-text-primary">New {template.name.toLowerCase()}</h2>
            <p className="text-xs text-text-muted">Starts in Draft with {template.sections?.length ?? 0} sections, owned by you.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        {viewingAs ? <p role="alert" className="text-sm text-warning">You are viewing as {viewingAs.name}. Stop viewing as to start a report.</p> : null}
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-text-secondary">Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required autoFocus
                 className={fieldClass} data-testid="playbook-new-title" aria-label="Title" />
        </label>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-text-secondary">Book</span>
            <select value={book} onChange={(e) => setBook(e.target.value as Book)} className={fieldClass} data-testid="playbook-new-book" aria-label="Book">
              {(["corporate", "retail", "both"] as Book[]).map((b) => <option key={b} value={b}>{BOOK_LABEL[b]}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-text-secondary">Period</span>
            <input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder={book === "retail" ? "e.g. 2026-06" : "e.g. 2026Q2"}
                   className={fieldClass} data-testid="playbook-new-period" aria-label="Period" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-text-secondary">Due date</span>
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={fieldClass} data-testid="playbook-new-due" aria-label="Due date" />
          </label>
        </div>
        <div>
          <span className="mb-1 block text-xs font-medium text-text-secondary">Reviewers</span>
          <ReviewerPicker value={reviewers} onChange={setReviewers} testId="playbook-new-reviewers" />
        </div>
        {template.sections?.length ? (
          <p className="text-[11px] leading-relaxed text-text-muted">Sections: {template.sections.join(" · ")}</p>
        ) : null}
        {error ? <p role="alert" className="text-sm text-negative" data-testid="playbook-new-error">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={busy || !title.trim() || !!viewingAs} data-testid="playbook-new-confirm">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} Create the report
          </Button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- report list

type Filter = "all" | ReportStatus;
const FILTERS: Filter[] = ["all", ...WORKFLOW];

const ORIGIN_LABEL: Record<string, string> = { template: "From a template", upload: "Uploaded", import: "Started from an import" };

function ReportList({ rows, error }: { rows: ReportRow[] | null; error: string | null }) {
  const [filter, setFilter] = React.useState<Filter>("all");
  const [q, setQ] = React.useState("");
  const needle = q.trim().toLowerCase();
  const matching = (rows ?? []).filter((r) => !needle || [r.title, r.template_name, r.template, r.owner?.name, r.book, r.period,
    ...(r.reviewers ?? []).map((p) => p.name)].filter(Boolean).join(" ").toLowerCase().includes(needle));
  const counts = FILTERS.reduce<Record<Filter, number>>((acc, f) => {
    acc[f] = f === "all" ? matching.length : matching.filter((r) => r.status === f).length;
    return acc;
  }, { all: 0, draft: 0, in_review: 0, approved: 0, presented: 0 });
  const shown = filter === "all" ? matching : matching.filter((r) => r.status === filter);

  return (
    <section data-testid="playbook-reports">
      <SectionTitle>Reports and documents</SectionTitle>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-0.5" role="tablist" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)} data-testid={`playbook-filter-${f}`}
                    className={cn("rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                                  filter === f ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary")}>
              {f === "all" ? "All" : STATUS_LABEL[f]}
              <span className={cn("ml-1.5 tabular-nums", filter === f ? "opacity-90" : "text-text-muted")} data-testid={`playbook-filter-${f}-count`}>
                {rows ? counts[f] : "·"}
              </span>
            </button>
          ))}
        </div>
        <label className="relative ml-auto w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, owner, book, period" aria-label="Search reports"
                 data-testid="playbook-search"
                 className="h-8 w-full rounded-md border border-border bg-surface pl-8 pr-3 text-[13px] text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
        </label>
      </div>

      {error ? <ErrorBox error={error} /> : rows === null ? <Loading what="Loading reports…" /> : shown.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border py-8 text-center text-sm text-text-secondary" data-testid="playbook-reports-empty">
          {rows.length === 0 ? "No reports yet. Start one from a template above, or ask Playbook." : "No report matches."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="hidden grid-cols-[minmax(0,2.6fr)_minmax(0,1.3fr)_104px_minmax(0,1.1fr)_84px_96px_96px_40px] gap-3 border-b border-border bg-surface-sunken px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted lg:grid">
            <span>Title</span><span>Template</span><span>Status</span><span>Owner</span><span>Reviewers</span><span>Due</span><span>Updated</span>
            <span className="text-right">Ver.</span>
          </div>
          <ul className="divide-y divide-border">
            {shown.map((r) => (
              <li key={r.id}>
                <Link href={reportHref(r.id)} data-testid="playbook-report-row" data-id={r.id} data-status={r.status}
                      className="grid grid-cols-1 gap-1.5 px-4 py-3 transition-colors hover:bg-surface-hover lg:grid-cols-[minmax(0,2.6fr)_minmax(0,1.3fr)_104px_minmax(0,1.1fr)_84px_96px_96px_40px] lg:items-center lg:gap-3">
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[14px] font-medium text-text-primary">{r.title}</span>
                      <span className="lg:hidden"><ReportStatusPill status={r.status} /></span>
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-text-muted">
                      {[r.book ? BOOK_LABEL[r.book] ?? r.book : null, r.period ? `Period ${r.period}` : null,
                        `${r.section_count ?? 0} sections`, ORIGIN_LABEL[r.origin] ?? null].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="truncate text-[12px] text-text-secondary">{r.template_name || r.template}</span>
                  <span className="hidden lg:block"><ReportStatusPill status={r.status} /></span>
                  <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-text-secondary">
                    <Initials person={r.owner} size={22} className="ring-0" />
                    <span className="truncate">{r.owner?.name ?? "—"}</span>
                  </span>
                  <span className="flex items-center gap-2 text-[11px] text-text-muted lg:block">
                    <span className="lg:hidden">Reviewers</span><PeopleStack people={r.reviewers} max={3} size={22} />
                  </span>
                  <span className={cn("text-[12px] tabular-nums", r.overdue ? "font-semibold text-negative" : "text-text-secondary")}
                        data-overdue={r.overdue ? "true" : "false"}>
                    <span className="lg:hidden text-text-muted">Due </span>{r.due_date ? day(r.due_date) : "—"}
                    {r.overdue ? <span className="block text-[10px] font-semibold uppercase tracking-[0.06em]">Overdue</span> : null}
                  </span>
                  <span className="text-[12px] tabular-nums text-text-muted"><span className="lg:hidden">Updated </span>{day(r.updated_at)}</span>
                  <span className="text-[12px] tabular-nums text-text-muted lg:text-right"><span className="lg:hidden">Version </span>v{r.version}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
