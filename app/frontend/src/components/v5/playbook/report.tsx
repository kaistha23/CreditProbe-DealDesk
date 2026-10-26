"use client";

/**
 * One Playbook report: `/playbook?report=<id>[&section=<sid>][&version=<n>]`.
 *
 * The header carries the workflow (Draft -> In review -> Approved -> Presented) with the moves the reader
 * may make, the owner, reviewers and due date, and the actions: Export to Word, Share through Mail,
 * Versions, Comments and Import. The main column is the document, section by section, each editable in
 * place while the report is open for editing. The side column is the thread with the assistant, which
 * drafts, revises and imports sections and moves the report through its workflow.
 *
 * `version=<n>` opens a read-only snapshot of that version, with Restore.
 */

import { PanelActions } from "@/components/v5/thread/panel-actions";
import { playbookSources } from "@/lib/v5/thread-actions";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { useUrlState } from "@/lib/v5/back";
import { ArrowDown, ArrowUp, Check, Download, FileDown, History, Import, Loader2, MessageSquare, MessageSquarePlus, Paperclip, Pencil, Plus, RotateCcw, Search, Send, Sparkles, Trash2, X } from "lucide-react";

import { useWideContent } from "@/components/layout/content-width";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCoreAuth } from "@/components/v5/core/auth";
import { ShareButton } from "@/components/v5/mail/share";
import { ErrorBox, Loading } from "@/components/v5/workspace/parts";
import { fileSize } from "@/lib/v5/core";
import { cn } from "@/lib/utils";
import {
  type Block, type Comment, type Message, type Report, type ReportStatus, type Section, type Source, BOOK_LABEL,
  SECTION_STATUS_LABEL, STATUS_LABEL, WORKFLOW, playbook, transitionLabel,
} from "@/lib/v5/playbook";
import { day, useWs, when } from "@/lib/v5/workspace";
import { LiveTrace, ProcessTrace } from "@/components/v5/thread";
import { messageTrace, traceBase } from "@/lib/v5/playbook";
import { newTraceId } from "@/lib/v5/thread";

import { AnswerExtras, chipActions, MessageText, SectionAssistantPanel } from "./ai-thread";
import { BlockView, Blocks, Initials, PeopleStack, Provenance, ReportStatusPill, ReviewerPicker } from "./blocks";
import { friendlyMessage } from "@/lib/v5/errors";

type SideTab = "assistant" | "comments" | "versions";

const fieldClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none";

function errText(e: unknown): string {
  return friendlyMessage(e);
}

export function PlaybookReport({ id }: { id: string }) {
  useWideContent();
  const router = useRouter();
  const params = useSearchParams();
  const sectionParam = params.get("section");
  const versionRaw = params.get("version");
  const versionN = versionRaw && /^\d+$/.test(versionRaw) ? Number(versionRaw) : null;
  const embed = params.get("embed") === "1";
  const { viewingAs, effective } = useCoreAuth();
  const viewer = effective?.username ?? "";

  const loaded = useWs(() => playbook.report(id), `pb-report|${id}|${viewer}`);
  const [fresh, setFresh] = React.useState<Report | null>(null);
  const report = fresh && fresh.id === id ? fresh : loaded.data;
  const snapshot = useWs(() => (versionN ? playbook.version(id, versionN) : Promise.resolve(null)), `pb-version|${id}|${versionN ?? ""}`);
  const snapshotMode = versionN !== null;
  const shown: Report | null = snapshotMode ? snapshot.data?.report ?? null : report;

  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [tab, setTab] = useUrlState<SideTab>("side", "assistant", "replace");
  const [commentTarget, setCommentTarget] = React.useState<string>("");
  const [importing, setImporting] = React.useState(false);
  // R10 C2: the section whose "Ask AI" side panel is open (one at a time).
  const [askSection, setAskSection] = React.useState<string | null>(null);
  const closeAsk = React.useCallback(() => setAskSection(null), []);
  const sideRef = React.useRef<HTMLDivElement>(null);
  const commentInputRef = React.useRef<HTMLTextAreaElement>(null);

  const onReport = React.useCallback((r: Report) => { setFresh(r); }, []);
  const thread = useThread(id, onReport);

  const href = React.useCallback((section?: string | null, version?: number | null) => {
    const p = new URLSearchParams();
    p.set("report", id);
    if (section) p.set("section", section);
    if (version) p.set("version", String(version));
    if (embed) p.set("embed", "1");
    return `/playbook?${p.toString()}`;
  }, [id, embed]);
  // Scroll to `?section=` once it is on the page (a link from an import, an assistant action, Mail).
  const scrolled = React.useRef<string | null>(null);
  const goSection = React.useCallback((sid: string) => {
    const el = document.getElementById(`section-${sid}`);
    if (el) { scrolled.current = sid; el.scrollIntoView({ behavior: "smooth", block: "start" }); }
    router.replace(href(sid), { scroll: false });
  }, [router, href]);

  async function run(label: string, fn: () => Promise<Report>): Promise<Report | null> {
    setBusy(label);
    setError(null);
    try {
      const r = await fn();
      setFresh(r);
      return r;
    } catch (e) {
      setError(errText(e));
      return null;
    } finally {
      setBusy(null);
    }
  }

  const sectionCount = shown?.sections?.length ?? 0;
  React.useEffect(() => {
    if (!sectionParam || scrolled.current === sectionParam || !sectionCount) return;
    const el = document.getElementById(`section-${sectionParam}`);
    if (!el) return;
    scrolled.current = sectionParam;
    window.requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [sectionParam, sectionCount]);

  const openSide = (t: SideTab) => {
    setTab(t);
    window.requestAnimationFrame(() => {
      const el = sideRef.current;
      if (el && el.getBoundingClientRect().top > window.innerHeight) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
  const commentOn = (sid: string) => {
    setCommentTarget(sid);
    openSide("comments");
    window.setTimeout(() => commentInputRef.current?.focus(), 60);
  };

  const back = (
    <BackButton fallback={{ href: "/playbook", label: "Playbook" }} testId="playbook-back" />
  );

  const loadError = snapshotMode ? snapshot.error : loaded.error && !report ? loaded.error : null;
  if (loadError) return <div className="space-y-4" data-testid="playbook-report">{back}<ErrorBox error={loadError} /></div>;
  if (!shown) return <div className="space-y-4" data-testid="playbook-report">{back}<Loading what={snapshotMode ? "Opening the version…" : "Opening the report…"} /></div>;

  const r = shown;
  const canEdit = !snapshotMode && !!r.can_edit && !viewingAs;
  const canWrite = !snapshotMode && !viewingAs;
  const sections = r.sections ?? [];
  const comments = r.comments ?? [];
  const openComments = comments.filter((c) => !c.resolved).length;
  const locked = r.status === "approved" || r.status === "presented";

  return (
    <div className={cn(embed ? "space-y-3" : "space-y-5")} data-testid="playbook-report" data-id={r.id} data-status={r.status}
         data-version={r.version}>
      <div className="space-y-2">
        {back}
        {snapshotMode ? (
          <SnapshotBanner version={versionN ?? r.version} report={r} current={report} canRestore={!!report?.can_edit && !viewingAs}
                          busy={busy === "restore"}
                          onRestore={async () => {
                            const out = await run("restore", () => playbook.restore(id, versionN ?? 0));
                            if (out) router.push(href());
                          }}
                          currentHref={href()} />
        ) : null}
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{r.template_name || r.template || "Report"}</p>
            <TitleEditor title={r.title} canEdit={canEdit} busy={busy === "title"}
                         onSave={(title) => run("title", () => playbook.update(id, { title }))} />
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-secondary">
              <ReportStatusPill status={r.status} testId="playbook-status" />
              {r.book ? <span>{BOOK_LABEL[r.book] ?? r.book}</span> : null}
              {r.period ? <span>· Period {r.period}</span> : null}
              <span>· Version {r.version}</span>
              <span>· {sections.length} sections</span>
              <span className="text-text-muted">· Updated {when(r.updated_at)}</span>
            </p>
          </div>
          {!snapshotMode ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button asChild variant="outline" size="sm">
                <a href={playbook.exportUrl(r.id)} data-testid="playbook-export" download aria-label="Export to Word">
                  <FileDown aria-hidden /> Export Word
                </a>
              </Button>
              <ShareButton testId="playbook-share" object={{
                type: "report", id: r.id, label: r.title, href: `/playbook?report=${r.id}`,
                summary: [r.template_name, STATUS_LABEL[r.status] ?? r.status_label, r.period ? `Period ${r.period}` : null, `version ${r.version}`]
                  .filter(Boolean).join(" · "),
                meta: { template: r.template, status: r.status, book: r.book, period: r.period, version: r.version },
              }} />
              <Button variant={tab === "versions" ? "subtle" : "outline"} size="sm" onClick={() => openSide("versions")} data-testid="playbook-versions"
                      aria-pressed={tab === "versions"}>
                <History aria-hidden /> Versions
              </Button>
              <Button variant={tab === "comments" ? "subtle" : "outline"} size="sm" onClick={() => openSide("comments")} data-testid="playbook-comments"
                      aria-pressed={tab === "comments"}>
                <MessageSquare aria-hidden /> Comments
                {openComments ? <span className="rounded-full bg-accent px-1.5 text-[10px] font-semibold tabular-nums text-accent-contrast">{openComments}</span> : null}
              </Button>
              {canEdit ? (
                <Button size="sm" onClick={() => setImporting(true)} data-testid="playbook-import">
                  <Import aria-hidden /> Import
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <Workflow report={r} canMove={canWrite} busy={busy === "status"}
                onMove={(to, note) => run("status", () => playbook.setStatus(id, to, note))} />

      <People report={r} canEdit={canEdit} busy={busy === "people"}
              onSave={(body) => run("people", () => playbook.update(id, body))} />

      {error ? (
        <div className="flex items-start gap-2 rounded-lg border border-negative/30 bg-negative-muted px-3 py-2 text-sm text-negative" role="alert" data-testid="playbook-error">
          <span className="min-w-0 flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss"><X className="size-4" aria-hidden /></button>
        </div>
      ) : null}
      {viewingAs ? <p className="text-xs text-warning" role="alert">You are viewing as {viewingAs.name}: this report is read only until you stop viewing as.</p> : null}
      {!snapshotMode && !r.can_edit && !viewingAs ? (
        <p className="rounded-md border border-border bg-surface-sunken px-3 py-2 text-xs text-text-secondary" data-testid="playbook-locked">
          {locked ? `This report is ${STATUS_LABEL[r.status].toLowerCase()} and locked. Reopen it as a draft to change it.`
                  : "You can read and comment on this report. Only its owner and team can change it."}
        </p>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <main className="min-w-0 space-y-4">
          {sections.length > 2 ? <Contents sections={sections} href={href} active={sectionParam} /> : null}
          {sections.length === 0 ? (
            <Card className="p-8 text-center text-sm text-text-secondary" data-testid="playbook-no-sections">
              This report has no sections yet. {canEdit ? "Add one below, import from another screen, or ask the assistant." : ""}
            </Card>
          ) : (
            <ol className="space-y-4">
              {sections.map((s, i) => (
                <li key={s.id}>
                  <SectionCard reportId={id} section={s} index={i} total={sections.length} canEdit={canEdit} canWrite={canWrite}
                               highlighted={s.id === sectionParam}
                               openComments={comments.filter((c) => c.section_id === s.id && !c.resolved).length}
                               busy={busy} run={run} onComment={() => commentOn(s.id)}
                               onAsk={(text) => { setTab("assistant"); void thread.send(text); }}
                               onReport={onReport} snapshotMode={snapshotMode}
                               asking={askSection === s.id} onOpenAI={() => setAskSection(askSection === s.id ? null : s.id)} />
                </li>
              ))}
            </ol>
          )}
          {canEdit ? <AddSection busy={busy === "add-section"} onAdd={(title) => run("add-section", () => playbook.addSection(id, { title, blocks: [], position: "end" }))} /> : null}
          <Files report={r} href={href} />
        </main>

        <aside ref={sideRef} className="min-w-0 scroll-mt-4 lg:sticky lg:top-4">
          <Card className="flex flex-col overflow-hidden p-0 lg:max-h-[calc(100dvh-7rem)]">
            <div className="flex border-b border-border" role="tablist" aria-label="Side panel">
              {(["assistant", "comments", "versions"] as SideTab[]).map((t) => (
                <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)} data-testid={`playbook-tab-${t}`}
                        className={cn("-mb-px flex-1 border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors",
                                      tab === t ? "border-accent text-accent" : "border-transparent text-text-secondary hover:text-text-primary")}>
                  {t === "assistant" ? "Assistant" : t === "comments" ? `Comments${openComments ? ` (${openComments})` : ""}` : "Versions"}
                </button>
              ))}
            </div>
            {tab === "assistant" ? (
              <ThreadPanel thread={thread} canWrite={canWrite} snapshotMode={snapshotMode} goSection={goSection} />
            ) : tab === "comments" ? (
              <CommentsPanel report={r} canWrite={canWrite} target={commentTarget} setTarget={setCommentTarget} inputRef={commentInputRef}
                             href={href}
                             onComment={(c) => {
                               if (!report) return;
                               const list = report.comments ?? [];
                               const next = list.some((x) => x.id === c.id) ? list.map((x) => (x.id === c.id ? c : x)) : [...list, c];
                               setFresh({ ...report, comments: next });
                             }} />
            ) : (
              <VersionsPanel report={report ?? r} active={versionN} href={href} />
            )}
          </Card>
        </aside>
      </div>

      {askSection && !snapshotMode && sections.some((s) => s.id === askSection) ? (
        <SectionAssistantPanel key={askSection} reportId={id} sectionId={askSection}
                               title={sections.find((s) => s.id === askSection)?.title ?? ""}
                               canWrite={canEdit} onReport={onReport} onClose={closeAsk} />
      ) : null}

      {importing && report ? (
        <ImportDialog report={report} onClose={() => setImporting(false)}
                      onImported={(next) => {
                        const before = new Set((report.sections ?? []).map((s) => s.id));
                        setFresh(next);
                        setImporting(false);
                        const added = (next.sections ?? []).find((s) => !before.has(s.id));
                        if (added) { scrolled.current = null; goSection(added.id); }
                      }} />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- header pieces

function TitleEditor({ title, canEdit, busy, onSave }: {
  title: string; canEdit: boolean; busy: boolean; onSave: (title: string) => Promise<unknown>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(title);
  const save = async () => {
    const t = text.trim();
    if (t && t !== title) await onSave(t);
    setEditing(false);
  };
  if (editing) {
    return (
      <form className="mt-0.5 flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} autoFocus aria-label="Report title"
               data-testid="playbook-title-input" disabled={busy}
               onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setText(title); setEditing(false); } }}
               className="min-w-0 flex-1 rounded-md border border-accent bg-surface px-2 py-1 text-2xl font-semibold text-text-primary focus:outline-none" />
        <Button type="submit" size="sm" disabled={busy || !text.trim()} data-testid="playbook-title-save">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Save
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => { setText(title); setEditing(false); }}>Cancel</Button>
      </form>
    );
  }
  return (
    <h1 className="group flex items-start gap-2 text-2xl font-semibold text-text-primary" data-testid="playbook-title">
      <span className="min-w-0">{title}</span>
      {canEdit ? (
        <button type="button" onClick={() => { setText(title); setEditing(true); }} aria-label="Rename the report" data-testid="playbook-title-edit"
                className="mt-1.5 rounded-md p-1 text-text-muted opacity-60 transition-opacity hover:bg-surface-hover hover:text-text-primary group-hover:opacity-100">
          <Pencil className="size-4" aria-hidden />
        </button>
      ) : null}
    </h1>
  );
}

function SnapshotBanner({ version, report, current, canRestore, busy, onRestore, currentHref }: {
  version: number; report: Report; current: Report | null; canRestore: boolean; busy: boolean; onRestore: () => void; currentHref: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-info/30 bg-info-muted px-4 py-2.5 text-sm" data-testid="playbook-snapshot"
         role="status">
      <History className="size-4 shrink-0 text-info" aria-hidden />
      <span className="min-w-0 flex-1 text-text-primary">
        You are reading <strong>version {version}</strong>, read only, as saved {when(report.updated_at)}.
        {current ? <span className="text-text-secondary"> The current version is {current.version}.</span> : null}
      </span>
      {canRestore && current && current.version !== version ? (
        <Button size="sm" onClick={onRestore} disabled={busy} data-testid="playbook-version-restore">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />} Restore this version
        </Button>
      ) : null}
      <Button asChild variant="outline" size="sm">
        <Link href={currentHref} data-testid="playbook-version-current">Back to the current version</Link>
      </Button>
    </div>
  );
}

function Workflow({ report, canMove, busy, onMove }: {
  report: Report; canMove: boolean; busy: boolean; onMove: (to: ReportStatus, note: string) => Promise<unknown>;
}) {
  const steps = report.workflow?.length ? report.workflow : WORKFLOW;
  const at = Math.max(0, steps.indexOf(report.status));
  const [pending, setPending] = React.useState<ReportStatus | null>(null);
  const [note, setNote] = React.useState("");
  const moves = canMove ? report.allowed_transitions ?? [] : [];
  const last = (report.history ?? []).at(-1);

  return (
    <Card className="space-y-3 p-4" data-testid="playbook-workflow">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <ol className="flex min-w-0 flex-1 items-center" aria-label="Workflow">
          {steps.map((s, i) => {
            const done = i < at;
            const current = i === at;
            return (
              <li key={s} className={cn("flex items-center", i < steps.length - 1 && "flex-1")} aria-current={current ? "step" : undefined}
                  data-testid={`playbook-step-${s}`} data-state={done ? "done" : current ? "current" : "todo"}>
                <span className="flex items-center gap-2">
                  <span className={cn("inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold",
                                      done ? "border-positive bg-positive text-white"
                                        : current ? "border-accent bg-accent-muted text-accent" : "border-border bg-surface text-text-muted")}>
                    {done ? <Check className="size-3.5" aria-hidden /> : i + 1}
                  </span>
                  <span className={cn("whitespace-nowrap text-[13px]", current ? "font-semibold text-text-primary" : done ? "text-text-secondary" : "text-text-muted")}>
                    {STATUS_LABEL[s] ?? s}
                  </span>
                </span>
                {i < steps.length - 1 ? <span aria-hidden className={cn("mx-3 h-0.5 min-w-4 flex-1 rounded", done ? "bg-positive" : "bg-border")} /> : null}
              </li>
            );
          })}
        </ol>
        {moves.length ? (
          <div className="flex flex-wrap gap-2">
            {moves.map((to) => {
              const forward = steps.indexOf(to) > at;
              return (
                <Button key={to} size="sm" variant={forward ? "default" : "outline"} disabled={busy} data-testid={`playbook-status-${to}`}
                        aria-pressed={pending === to}
                        onClick={() => { setPending(pending === to ? null : to); setNote(""); }}>
                  {transitionLabel(report.status, to)}
                </Button>
              );
            })}
          </div>
        ) : null}
      </div>
      {pending ? (
        <form className="space-y-2 rounded-md border border-border bg-surface-sunken p-3" data-testid="playbook-status-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const target = pending;
                await onMove(target, note.trim());
                setPending(null);
                setNote("");
              }}>
          <label className="block text-xs font-medium text-text-secondary">
            {transitionLabel(report.status, pending)}: add a note for the record (optional)
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000} data-testid="playbook-status-note"
                      placeholder={pending === "draft" ? "What needs to change" : "e.g. Reviewed with the committee secretary"}
                      className={cn(fieldClass, "mt-1 resize-y font-normal")} />
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setPending(null)}>Cancel</Button>
            <Button type="submit" size="sm" disabled={busy} data-testid="playbook-status-confirm">
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} {transitionLabel(report.status, pending)}
            </Button>
          </div>
        </form>
      ) : null}
      {last ? (
        <p className="text-[11px] text-text-muted" data-testid="playbook-last-move">
          {last.from ? `${STATUS_LABEL[last.from] ?? last.from} → ` : ""}{STATUS_LABEL[last.to] ?? last.to} by {last.who?.name ?? "CreditProbe"}, {when(last.at)}
          {last.note ? <>: <span className="text-text-secondary">“{last.note}”</span></> : null}
        </p>
      ) : null}
    </Card>
  );
}

function People({ report, canEdit, busy, onSave }: {
  report: Report; canEdit: boolean; busy: boolean;
  onSave: (body: { reviewers?: string[]; due_date?: string | null }) => Promise<Report | null>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [reviewers, setReviewers] = React.useState<string[]>([]);
  const [due, setDue] = React.useState(report.due_date ?? "");
  const [dueFor, setDueFor] = React.useState(report.due_date ?? "");
  // Follow the report when it changes underneath (the assistant set a due date).
  if ((report.due_date ?? "") !== dueFor) { setDueFor(report.due_date ?? ""); setDue(report.due_date ?? ""); }

  const saveDue = (v: string) => {
    if (v === (report.due_date ?? "")) return;
    void onSave({ due_date: v || null });
  };

  return (
    <div className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)]" data-testid="playbook-people">
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Owner</p>
        <p className="flex items-center gap-2 text-sm text-text-primary" data-testid="playbook-owner">
          <Initials person={report.owner} size={26} className="ring-0" />
          <span className="min-w-0">
            <span className="block truncate font-medium">{report.owner?.name ?? "—"}</span>
            {report.owner?.title ? <span className="block truncate text-[11px] text-text-muted">{report.owner.title}</span> : null}
          </span>
        </p>
      </div>
      <div>
        <p className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">
          Reviewers
          {canEdit && !editing ? (
            <button type="button" onClick={() => { setReviewers((report.reviewers ?? []).map((p) => p.username)); setEditing(true); }}
                    className="normal-case tracking-normal text-accent hover:underline" data-testid="playbook-reviewers-edit">Edit</button>
          ) : null}
        </p>
        {editing ? (
          <div className="space-y-2">
            <ReviewerPicker value={reviewers} onChange={setReviewers} testId="playbook-reviewers" />
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} data-testid="playbook-reviewers-save"
                      onClick={async () => { const out = await onSave({ reviewers }); if (out) setEditing(false); }}>
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : (report.reviewers ?? []).length ? (
          <div className="flex flex-wrap items-center gap-2" data-testid="playbook-reviewer-list">
            <PeopleStack people={report.reviewers} max={5} size={26} />
            <span className="text-sm text-text-secondary">{report.reviewers.map((p) => p.name).join(", ")}</span>
          </div>
        ) : (
          <p className="text-sm text-text-muted">No reviewers yet.</p>
        )}
      </div>
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Due date</p>
        {canEdit ? (
          <input type="date" value={due} aria-label="Due date" data-testid="playbook-due" disabled={busy}
                 onChange={(e) => { setDue(e.target.value); if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) saveDue(e.target.value); }}
                 onBlur={(e) => { if (!e.target.value) saveDue(""); }}
                 className={cn(fieldClass, "h-9 py-1", report.overdue && "border-negative/50 text-negative")} />
        ) : (
          <p className={cn("text-sm", report.overdue ? "font-semibold text-negative" : "text-text-primary")} data-testid="playbook-due-text">
            {report.due_date ? day(report.due_date) : "—"}
          </p>
        )}
        {report.overdue ? <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-negative">Overdue</p> : null}
      </div>
    </div>
  );
}

function Contents({ sections, href, active }: { sections: Section[]; href: (s?: string | null) => string; active: string | null }) {
  return (
    <nav aria-label="Contents" className="rounded-lg border border-border bg-surface px-4 py-3" data-testid="playbook-contents">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Contents</p>
      <ol className="grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
        {sections.map((s, i) => (
          <li key={s.id} className="flex min-w-0 items-baseline gap-2">
            <span className="w-5 shrink-0 text-right tabular-nums text-text-muted">{i + 1}.</span>
            <Link href={href(s.id)} replace scroll={false}
                  onClick={() => document.getElementById(`section-${s.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
                  className={cn("truncate hover:text-accent hover:underline", s.id === active ? "font-medium text-accent" : "text-text-secondary",
                                s.status === "empty" && "italic text-text-muted")}>
              {s.title}
            </Link>
          </li>
        ))}
      </ol>
    </nav>
  );
}

// ---------------------------------------------------------------- sections

const SECTION_TONE: Record<string, string> = {
  empty: "border-dashed border-border text-text-muted",
  drafted: "border-info/30 bg-info-muted text-info",
  imported: "border-accent/30 bg-accent-muted text-accent",
  edited: "border-positive/30 bg-positive-muted text-positive",
};

function SectionCard({ reportId, section, index, total, canEdit, canWrite, highlighted, openComments, busy, run, onComment, onAsk, snapshotMode, asking, onOpenAI }: {
  reportId: string; section: Section; index: number; total: number; canEdit: boolean; canWrite: boolean; highlighted: boolean;
  openComments: number; busy: string | null; run: (label: string, fn: () => Promise<Report>) => Promise<Report | null>;
  onComment: () => void; onAsk: (text: string) => void; onReport: (r: Report) => void; snapshotMode: boolean;
  asking: boolean; onOpenAI: () => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const s = section;
  const blocks = s.blocks ?? [];
  const mine = busy?.endsWith(`:${s.id}`) ?? false;
  return (
    <Card id={`section-${s.id}`} data-testid="playbook-section" data-id={s.id} data-status={s.status}
          className={cn("scroll-mt-4 p-5 transition-shadow sm:p-6", (highlighted || asking) && "ring-2 ring-accent/60 shadow-md")}>
      <header className="mb-4 flex flex-wrap items-start gap-2 border-b border-border pb-3">
        <div className="min-w-0 flex-1">
          <h2 className="flex items-baseline gap-2 text-[18px] font-semibold text-text-primary" data-testid="playbook-section-title">
            <span className="tabular-nums text-text-muted">{index + 1}.</span>
            <span className="min-w-0">{s.title}</span>
          </h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
            <span className={cn("rounded-full border px-2 py-0.5 font-medium", SECTION_TONE[s.status] ?? SECTION_TONE.drafted)}>
              {SECTION_STATUS_LABEL[s.status] ?? s.status}
            </span>
            <Provenance source={s.source} />
            {s.updated_at ? <span>Updated {when(s.updated_at)}{s.updated_by ? ` by ${s.updated_by.name}` : ""}</span> : null}
          </div>
        </div>
        {!editing ? (
          <div className="flex flex-wrap items-center gap-0.5" data-testid="playbook-section-tools">
            {!snapshotMode ? (
              <Button variant={asking ? "subtle" : "ghost"} size="sm" onClick={onOpenAI} aria-pressed={asking}
                      data-testid="playbook-section-ask" aria-label={`Ask AI about ${s.title}`}>
                <Sparkles aria-hidden /> Ask AI
              </Button>
            ) : null}
            {canWrite ? (
              <Button variant="ghost" size="sm" onClick={onComment} data-testid="playbook-section-comment" aria-label={`Comment on ${s.title}`}>
                <MessageSquarePlus aria-hidden /> Comment
                {openComments ? <span className="rounded-full bg-accent-muted px-1.5 text-[10px] font-semibold tabular-nums text-accent">{openComments}</span> : null}
              </Button>
            ) : null}
            {canEdit ? (
              <>
                <Button variant="ghost" size="sm" onClick={() => setEditing(true)} data-testid="playbook-section-edit" aria-label={`Edit ${s.title}`}>
                  <Pencil aria-hidden /> Edit
                </Button>
                <Button variant="ghost" size="icon" className="size-8" disabled={index === 0 || !!busy} aria-label="Move up" title="Move up"
                        data-testid="playbook-section-up" onClick={() => void run(`move:${s.id}`, () => playbook.moveSection(reportId, s.id, "up"))}>
                  <ArrowUp aria-hidden />
                </Button>
                <Button variant="ghost" size="icon" className="size-8" disabled={index === total - 1 || !!busy} aria-label="Move down" title="Move down"
                        data-testid="playbook-section-down" onClick={() => void run(`move:${s.id}`, () => playbook.moveSection(reportId, s.id, "down"))}>
                  <ArrowDown aria-hidden />
                </Button>
                <Button variant="ghost" size="icon" className="size-8 hover:text-negative" disabled={!!busy} aria-label={`Delete ${s.title}`} title="Delete"
                        data-testid="playbook-section-delete"
                        onClick={() => { if (window.confirm(`Delete the section “${s.title}”? It stays in the version history.`)) void run(`delete:${s.id}`, () => playbook.deleteSection(reportId, s.id)); }}>
                  {mine ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />}
                </Button>
              </>
            ) : null}
          </div>
        ) : null}
      </header>
      {editing ? (
        <SectionEditor section={s} busy={busy === `save:${s.id}`} onCancel={() => setEditing(false)}
                       onSave={async (title, next) => {
                         const out = await run(`save:${s.id}`, () => playbook.updateSection(reportId, s.id, { title, blocks: next }));
                         if (out) setEditing(false);
                       }} />
      ) : blocks.length ? (
        <Blocks blocks={blocks} />
      ) : (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center">
          <p className="text-sm text-text-secondary">Not written yet.</p>
          {canEdit ? (
            <Button variant="outline" size="sm" className="mt-3" onClick={() => onAsk(`Draft the ${s.title} section`)} data-testid="playbook-section-draft">
              <Sparkles aria-hidden /> Draft with the assistant
            </Button>
          ) : null}
        </div>
      )}
    </Card>
  );
}

type Editable = Block & { _key: string };

function SectionEditor({ section, busy, onSave, onCancel }: {
  section: Section; busy: boolean; onSave: (title: string, blocks: Block[]) => Promise<void>; onCancel: () => void;
}) {
  const [title, setTitle] = React.useState(section.title);
  const [blocks, setBlocks] = React.useState<Editable[]>(() =>
    (section.blocks ?? []).map((b, i) => ({ ...b, _key: b.id ?? `b${i}` }) as Editable));
  const counter = React.useRef(0);

  const patch = (key: string, change: Partial<Block>) =>
    setBlocks((list) => list.map((b) => (b._key === key ? ({ ...b, ...change } as Editable) : b)));
  const remove = (key: string) => setBlocks((list) => list.filter((b) => b._key !== key));
  const add = (kind: "paragraph" | "bullets" | "heading") => {
    counter.current += 1;
    const key = `new${counter.current}`;
    const block: Editable = kind === "paragraph" ? { kind, text: "", _key: key }
      : kind === "bullets" ? { kind, items: [""], _key: key } : { kind, text: "", level: 3, _key: key };
    setBlocks((list) => [...list, block]);
  };

  const clean = (): Block[] => blocks.map((b) => {
    const { _key, ...rest } = b;
    void _key;
    if (rest.kind === "bullets") return { ...rest, items: (rest.items ?? []).map((x) => x.trim()).filter(Boolean) };
    return rest as Block;
  }).filter((b) => !((b.kind === "paragraph" || b.kind === "heading") && !b.text.trim()) && !(b.kind === "bullets" && !b.items.length));

  return (
    <form className="space-y-4" data-testid="playbook-section-editor"
          onSubmit={(e) => { e.preventDefault(); if (title.trim()) void onSave(title.trim(), clean()); }}
          onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel(); } }}>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Section title</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required className={cn(fieldClass, "font-semibold")}
               data-testid="playbook-section-title-input" aria-label="Section title" />
      </label>
      {blocks.map((b, i) => (
        <div key={b._key} className="group relative" data-testid="playbook-block-edit" data-kind={b.kind}>
          {b.kind === "paragraph" ? (
            <textarea value={b.text} onChange={(e) => patch(b._key, { text: e.target.value })} aria-label={`Paragraph ${i + 1}`}
                      rows={Math.min(14, Math.max(4, Math.ceil((b.text?.length ?? 0) / 90) + (b.text?.split("\n").length ?? 1)))}
                      data-testid="playbook-block-input" className={cn(fieldClass, "resize-y leading-relaxed")}
                      placeholder="Write the paragraph (**bold**, *italic*)" />
          ) : b.kind === "heading" ? (
            <div className="flex gap-2">
              <select value={b.level ?? 2} onChange={(e) => patch(b._key, { level: Number(e.target.value) as 2 | 3 })} aria-label="Heading level"
                      className={cn(fieldClass, "w-28")}>
                <option value={2}>Heading</option><option value={3}>Subheading</option>
              </select>
              <input value={b.text} onChange={(e) => patch(b._key, { text: e.target.value })} aria-label={`Heading ${i + 1}`}
                     data-testid="playbook-block-input" className={cn(fieldClass, "font-semibold")} />
            </div>
          ) : b.kind === "bullets" ? (
            <textarea value={(b.items ?? []).join("\n")} aria-label={`Bullet points ${i + 1}, one per line`}
                      onChange={(e) => patch(b._key, { items: e.target.value.split("\n") })}
                      rows={Math.min(14, Math.max(3, (b.items ?? []).length + 1))} data-testid="playbook-block-input"
                      className={cn(fieldClass, "resize-y")} placeholder="One bullet point per line" />
          ) : (
            <div className="rounded-lg border border-border bg-surface-sunken p-3">
              <p className="mb-2 text-[11px] text-text-muted">Figures from the books: not edited here. Ask the assistant to refresh or revise them.</p>
              <div className="pointer-events-none opacity-90"><BlockView block={b} /></div>
            </div>
          )}
          <button type="button" onClick={() => remove(b._key)} aria-label={`Remove block ${i + 1}`} title="Remove this block"
                  className="absolute -right-2 -top-2 hidden rounded-full border border-border bg-surface p-1 text-text-muted shadow-sm hover:text-negative group-hover:block group-focus-within:block">
            <X className="size-3" aria-hidden />
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button type="button" variant="ghost" size="sm" onClick={() => add("paragraph")}><Plus aria-hidden /> Paragraph</Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => add("bullets")}><Plus aria-hidden /> Bullet points</Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => add("heading")}><Plus aria-hidden /> Subheading</Button>
        <span className="ml-auto flex gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel} data-testid="playbook-section-cancel">Cancel</Button>
          <Button type="submit" size="sm" disabled={busy || !title.trim()} data-testid="playbook-section-save">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Save section
          </Button>
        </span>
      </div>
    </form>
  );
}

function AddSection({ busy, onAdd }: { busy: boolean; onAdd: (title: string) => Promise<Report | null> }) {
  const [open, setOpen] = React.useState(false);
  const [title, setTitle] = React.useState("");
  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} data-testid="playbook-section-add">
        <Plus aria-hidden /> Add a section
      </Button>
    );
  }
  return (
    <form className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border p-3"
          onSubmit={async (e) => { e.preventDefault(); if (!title.trim()) return; const out = await onAdd(title.trim()); if (out) { setTitle(""); setOpen(false); } }}>
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus placeholder="Section title"
             aria-label="New section title" data-testid="playbook-section-add-title" className={cn(fieldClass, "min-w-[220px] flex-1")}
             onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } }} />
      <Button type="submit" size="sm" disabled={busy || !title.trim()} data-testid="playbook-section-add-confirm">
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Plus aria-hidden />} Add
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
    </form>
  );
}

function Files({ report, href }: { report: Report; href: (s?: string | null) => string }) {
  const files = report.files ?? [];
  if (!files.length) return null;
  const titles = new Map((report.sections ?? []).map((s) => [s.id, s.title]));
  return (
    <Card className="p-4" data-testid="playbook-files">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        <Paperclip className="size-3.5" aria-hidden /> Files
      </p>
      <ul className="divide-y divide-border">
        {files.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
            <a href={playbook.fileUrl(report.id, f.id)} download={f.name} data-testid="playbook-file" data-id={f.id}
               className="inline-flex min-w-0 items-center gap-1.5 font-medium text-accent hover:underline">
              <Download className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{f.name}</span>
            </a>
            <span className="text-xs text-text-muted">{fileSize(f.size ?? 0)}</span>
            <span className="text-xs text-text-muted">{f.uploaded_by ? `${f.uploaded_by.name}, ` : ""}{day(f.uploaded_at)}</span>
            {f.section_id && titles.get(f.section_id) ? (
              <Link href={href(f.section_id)} replace scroll={false} className="text-xs text-text-secondary hover:text-accent hover:underline">
                With “{titles.get(f.section_id)}”
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------- the thread

interface ThreadState {
  messages: Message[]; loading: boolean; loadError: string | null; pending: string | null; error: string | null; traceId: string;
  send: (text: string) => Promise<void>;
}

function useThread(id: string, onReport: (r: Report) => void): ThreadState {
  const loaded = useWs(() => playbook.thread(id), `pb-thread|${id}`);
  const [extra, setExtra] = React.useState<{ id: string; list: Message[] }>({ id, list: [] });
  const [pending, setPending] = React.useState<string | null>(null);
  const [traceId, setTraceId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const sending = React.useRef(false);

  const send = React.useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || sending.current) return;
    sending.current = true;
    setPending(text);
    setError(null);
    const trace = newTraceId();
    setTraceId(trace);
    try {
      const r = await playbook.say(id, text, trace);
      setExtra((e) => ({ id, list: [...(e.id === id ? e.list : []), ...(r.messages ?? [])] }));
      if (r.report) onReport(r.report);
    } catch (e) {
      setError(errText(e));
    } finally {
      sending.current = false;
      setPending(null);
    }
  }, [id, onReport]);

  const messages = React.useMemo(() => {
    const seen = new Set<string>();
    const out: Message[] = [];
    for (const m of [...(loaded.data?.messages ?? []), ...(extra.id === id ? extra.list : [])]) {
      const key = m.id ?? `${m.role}|${m.at}|${m.text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(m);
    }
    return out;
  }, [loaded.data, extra, id]);

  return { messages, loading: loaded.loading, loadError: loaded.error, pending, error, send, traceId };
}

const THREAD_STARTERS = ["Draft every empty section", "Summarise the report", "Send for review"];

function ThreadPanel({ thread, canWrite, snapshotMode, goSection }: {
  thread: ThreadState; canWrite: boolean; snapshotMode: boolean; goSection: (sid: string) => void;
}) {
  const [text, setText] = React.useState("");
  const listRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const count = thread.messages.length;

  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [count, thread.pending]);

  const submit = async () => {
    const t = text.trim();
    if (!t || thread.pending) return;
    setText("");
    await thread.send(t);
  };
  const fill = (s: string) => { setText(s); inputRef.current?.focus(); };
  const last = [...thread.messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="playbook-thread">
      <div ref={listRef} className="min-h-[220px] flex-1 space-y-3 overflow-y-auto px-4 py-3 lg:max-h-[calc(100dvh-20rem)]">
        {thread.loadError ? <p className="text-xs text-negative" role="alert">{thread.loadError}</p> : null}
        {thread.loading && !count ? <Loading what="Loading the thread…" /> : null}
        {!thread.loading && !count && !thread.pending ? (
          <div className="py-6 text-center">
            <Sparkles className="mx-auto size-5 text-accent" aria-hidden />
            <p className="mt-2 text-sm text-text-secondary">Ask the assistant to draft or revise a section, import from another screen, or move the report on.</p>
            {canWrite ? (
              <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                {THREAD_STARTERS.map((s) => (
                  <button key={s} type="button" onClick={() => fill(s)} data-testid="playbook-thread-suggestion"
                          className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-text-secondary hover:border-accent hover:text-accent">{s}</button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {thread.messages.map((m) => <Bubble key={m.id ?? `${m.at}|${m.text}`} message={m} goSection={goSection} />)}
        {thread.pending ? (
          <>
            <Bubble message={{ id: "pending", role: "user", at: "", author: null, text: thread.pending, actions: [], suggestions: [] }} goSection={goSection} />
            <div data-testid="playbook-thread-working"><LiveTrace base={traceBase()} traceId={thread.traceId} compact /></div>
          </>
        ) : null}
        {thread.error ? <p className="text-xs text-negative" role="alert" data-testid="playbook-thread-error">{thread.error}</p> : null}
      </div>
      {last?.suggestions?.length && canWrite && !thread.pending ? (
        <div className="flex flex-wrap gap-1.5 border-t border-border px-4 py-2">
          {last.suggestions.map((s) => (
            <button key={s} type="button" onClick={() => fill(s)} data-testid="playbook-thread-suggestion"
                    className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-[12px] text-text-secondary hover:border-accent hover:text-accent">{s}</button>
          ))}
        </div>
      ) : null}
      <form className="border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <div className="flex items-end gap-1.5 rounded-xl border border-border-strong bg-surface p-1.5 focus-within:border-accent">
          <textarea ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} rows={2} disabled={!canWrite}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); } }}
                    placeholder={snapshotMode ? "Open the current version to talk to the assistant" : canWrite ? "Ask the assistant: draft, revise, import, send for review…" : "Read only"}
                    aria-label="Message the assistant" data-testid="playbook-thread-input"
                    className="block min-w-0 flex-1 resize-none bg-transparent py-1 pl-1.5 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-60" />
          <Button type="submit" size="icon" disabled={!canWrite || !text.trim() || !!thread.pending} aria-label="Send" data-testid="playbook-thread-send"
                  className="size-8 shrink-0 rounded-lg">
            {thread.pending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
          </Button>
        </div>
      </form>
    </div>
  );
}

function Bubble({ message, goSection }: { message: Message; goSection: (sid: string) => void }) {
  const mine = message.role === "user";
  const trace = mine ? null : messageTrace(message);
  return (
    <div className={cn("flex flex-col gap-1", mine ? "items-end" : "items-start")} data-testid="playbook-message" data-role={message.role}>
      {trace ? <div className="w-full max-w-[96%]"><ProcessTrace snapshot={trace} compact /></div> : null}
      <div className={cn("max-w-[92%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed",
                         mine ? "rounded-br-md bg-accent text-accent-contrast" : "rounded-bl-md border border-border bg-surface-sunken text-text-primary")}>
        <MessageText text={message.text} role={mine ? "user" : "assistant"} />
      </div>
      {!mine ? <div className="w-full max-w-[96%]"><AnswerExtras message={message} /></div> : null}
      {/* R16 t (M7): Share, Trace, Word and Add to report on each assistant answer of the report thread */}
      {!mine && message.text ? (
        <div className="w-full max-w-[96%]">
          <PanelActions module="playbook" id={message.id} title={message.text.split("\n")[0].slice(0, 120) || "Playbook answer"} container='[data-testid="playbook-message"]'
                        testId="playbook-message-actions" sources={playbookSources(message.actions)} />
        </div>) : null}
      {chipActions(message.actions).length ? (
        <div className="flex max-w-[92%] flex-wrap gap-1">
          {chipActions(message.actions).map((a, i) => a.section_id ? (
            <button key={`${a.kind}-${i}`} type="button" onClick={() => goSection(a.section_id as string)} data-testid="playbook-message-action"
                    data-kind={a.kind} data-section={a.section_id}
                    className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent-muted px-2 py-0.5 text-[11px] text-accent hover:border-accent">
              <Check className="size-3" aria-hidden /> {a.label}
            </button>
          ) : (
            <span key={`${a.kind}-${i}`} data-testid="playbook-message-action" data-kind={a.kind}
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-text-secondary">
              <Check className="size-3" aria-hidden /> {a.label}
            </span>
          ))}
        </div>
      ) : null}
      {message.at ? <span className="px-1 text-[10px] text-text-muted">{mine ? message.author?.name ?? "You" : "Playbook"} · {when(message.at)}</span> : null}
    </div>
  );
}

// ---------------------------------------------------------------- comments

function CommentsPanel({ report, canWrite, target, setTarget, inputRef, href, onComment }: {
  report: Report; canWrite: boolean; target: string; setTarget: (s: string) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>; href: (s?: string | null) => string; onComment: (c: Comment) => void;
}) {
  const [showResolved, setShowResolved] = React.useState(false);
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const comments = report.comments ?? [];
  const titles = new Map((report.sections ?? []).map((s) => [s.id, s.title]));
  const list = [...comments].filter((c) => showResolved || !c.resolved).sort((a, b) => (a.at < b.at ? 1 : -1));
  const resolvedCount = comments.filter((c) => c.resolved).length;

  async function add() {
    const text = body.trim();
    if (!text || busy) return;
    setBusy("add");
    setError(null);
    try {
      onComment(await playbook.addComment(report.id, text, target || null));
      setBody("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(null);
    }
  }
  async function resolve(cid: string) {
    setBusy(cid);
    setError(null);
    try { onComment(await playbook.resolveComment(report.id, cid)); } catch (e) { setError(errText(e)); } finally { setBusy(null); }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="playbook-comments-panel">
      {canWrite ? (
        <form className="space-y-2 border-b border-border p-3" onSubmit={(e) => { e.preventDefault(); void add(); }}>
          <label className="flex items-center gap-2 text-xs text-text-secondary">
            On
            <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Comment on" data-testid="playbook-comment-target"
                    className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-primary">
              <option value="">The whole report</option>
              {(report.sections ?? []).map((s, i) => <option key={s.id} value={s.id}>{i + 1}. {s.title}</option>)}
            </select>
          </label>
          <textarea ref={inputRef} value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={8000}
                    placeholder="Add a comment for the owner and reviewers" aria-label="Comment" data-testid="playbook-comment-input"
                    className={cn(fieldClass, "resize-y text-[13px]")} />
          {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={!body.trim() || busy === "add"} data-testid="playbook-comment-add">
              {busy === "add" ? <Loader2 className="animate-spin" aria-hidden /> : <MessageSquarePlus aria-hidden />} Comment
            </Button>
          </div>
        </form>
      ) : null}
      <div className="flex items-center justify-between px-4 pt-3 text-[11px] text-text-muted">
        <span>{comments.length - resolvedCount} open{resolvedCount ? `, ${resolvedCount} resolved` : ""}</span>
        {resolvedCount ? (
          <button type="button" className="text-accent hover:underline" onClick={() => setShowResolved((v) => !v)}>
            {showResolved ? "Hide resolved" : "Show resolved"}
          </button>
        ) : null}
      </div>
      <ul className="min-h-[120px] flex-1 space-y-2 overflow-y-auto p-3 lg:max-h-[calc(100dvh-26rem)]">
        {list.length === 0 ? <li className="py-6 text-center text-sm text-text-muted">No comments{showResolved ? "" : " open"}.</li> : list.map((c) => (
          <li key={c.id} data-testid="playbook-comment" data-id={c.id} data-resolved={c.resolved ? "true" : "false"}
              className={cn("rounded-lg border p-3", c.resolved ? "border-border bg-surface-sunken opacity-75" : "border-border bg-surface")}>
            <div className="flex items-center gap-2 text-xs">
              <Initials person={c.author} size={22} className="ring-0" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-text-primary">{c.author?.name ?? "CreditProbe"}</span>
                <span className="block text-[10px] text-text-muted">{when(c.at)}</span>
              </span>
              {c.resolved ? (
                <span className="rounded-full bg-positive-muted px-2 py-0.5 text-[10px] font-semibold text-positive">Resolved</span>
              ) : canWrite ? (
                <Button variant="ghost" size="sm" className="h-7 px-2" disabled={busy === c.id} onClick={() => void resolve(c.id)}
                        data-testid="playbook-comment-resolve">
                  {busy === c.id ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Resolve
                </Button>
              ) : null}
            </div>
            {c.section_id && titles.get(c.section_id) ? (
              <Link href={href(c.section_id)} replace scroll={false}
                    onClick={() => document.getElementById(`section-${c.section_id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
                    className="mt-1.5 inline-block max-w-full truncate rounded bg-surface-sunken px-1.5 py-0.5 text-[11px] text-text-secondary hover:text-accent">
                On “{titles.get(c.section_id)}”
              </Link>
            ) : null}
            <p className="mt-1.5 whitespace-pre-line text-[13px] leading-relaxed text-text-primary">{c.body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- versions

function VersionsPanel({ report, active, href }: { report: Report; active: number | null; href: (s?: string | null, v?: number | null) => string }) {
  const router = useRouter();
  const versions = useWs(() => playbook.versions(report.id), `pb-versions|${report.id}|${report.version}`);
  const rows = versions.data?.versions ?? [];
  const history = [...(report.history ?? [])].reverse();
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 lg:max-h-[calc(100dvh-14rem)]" data-testid="playbook-versions-panel">
      <div>
        <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Versions</p>
        {versions.error ? <p className="px-1 text-xs text-negative" role="alert">{versions.error}</p> : versions.loading && !rows.length ? (
          <Loading what="Loading versions…" />
        ) : rows.length === 0 ? <p className="px-1 text-sm text-text-muted">No versions yet.</p> : (
          <ul className="space-y-1">
            {rows.map((v) => {
              const current = v.version === report.version;
              const open = active === v.version || (active === null && current);
              return (
                <li key={v.version}>
                  <button type="button" data-testid="playbook-version-row" data-version={v.version} aria-current={open ? "true" : undefined}
                          onClick={() => router.push(current ? href() : href(null, v.version))}
                          className={cn("w-full rounded-md border px-3 py-2 text-left transition-colors",
                                        open ? "border-accent/40 bg-accent-muted" : "border-transparent hover:border-border hover:bg-surface-hover")}>
                    <span className="flex items-center gap-2 text-[13px]">
                      <span className="font-semibold tabular-nums text-text-primary">v{v.version}</span>
                      <span className="min-w-0 flex-1 truncate text-text-secondary">{v.action}</span>
                      {current ? <span className="rounded-full bg-positive-muted px-1.5 text-[10px] font-semibold text-positive">Current</span> : null}
                    </span>
                    {v.summary ? <span className="mt-0.5 block line-clamp-2 text-[12px] text-text-secondary">{v.summary}</span> : null}
                    <span className="mt-0.5 block text-[10px] text-text-muted">{v.who?.name ?? "CreditProbe"} · {when(v.at)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {history.length ? (
        <div data-testid="playbook-history">
          <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Status history</p>
          <ol className="space-y-2 border-l border-border pl-3">
            {history.map((h, i) => (
              <li key={`${h.at}-${i}`} className="text-[12px]">
                <span className="flex flex-wrap items-center gap-1.5">
                  {h.from ? <><ReportStatusPill status={h.from} /><span className="text-text-muted">→</span></> : null}
                  <ReportStatusPill status={h.to} />
                </span>
                <span className="mt-0.5 block text-[11px] text-text-muted">{h.who?.name ?? "CreditProbe"} · {when(h.at)}</span>
                {h.note ? <span className="mt-0.5 block text-text-secondary">“{h.note}”</span> : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- import

const SOURCE_ORDER = [
  "cockpit-thread", "investigation", "attention-item", "early-warning-list", "borrower", "whatif-scenario", "whatif-thread",
  "data-extract", "analysis", "scorecard-validation", "crm-compliance", "policy-document", "circular", "document", "project",
];

function ImportDialog({ report, onClose, onImported }: { report: Report; onClose: () => void; onImported: (r: Report) => void }) {
  const sources = useWs(() => playbook.sources(), `pb-sources|${report.id}`);
  const [q, setQ] = React.useState("");
  const [type, setType] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const all = React.useMemo(() => sources.data?.sources ?? [], [sources.data]);
  const types = React.useMemo(() => {
    const m = new Map<string, string>();
    for (const s of all) if (!m.has(s.type)) m.set(s.type, s.type_label || s.type);
    return [...m.entries()].sort((a, b) => orderOf(a[0]) - orderOf(b[0]));
  }, [all]);
  const needle = q.trim().toLowerCase();
  const filtered = all.filter((s) => (!type || s.type === type)
    && (!needle || `${s.label} ${s.summary} ${s.type_label} ${s.id}`.toLowerCase().includes(needle)));
  const groups = types.map(([t, label]) => ({ type: t, label, items: filtered.filter((s) => s.type === t) })).filter((g) => g.items.length);

  async function choose(s: Source) {
    if (busy || !s.available) return;
    setBusy(`${s.type}|${s.id}`);
    setError(null);
    try {
      onImported(await playbook.importSource(report.id, s.type, s.id));
    } catch (e) {
      setError(errText(e));
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Import into the report" data-testid="playbook-import-dialog"
           className="flex max-h-[85dvh] w-full max-w-[680px] flex-col rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-border p-5 pb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Import into the report</h2>
            <p className="mt-0.5 text-xs text-text-muted">
              Choose a Cockpit answer, an investigation, an attention item, a list or a scenario. It is added as a new section,
              with its figures from the books and a link back.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" aria-hidden /></button>
        </div>
        <div className="space-y-2 border-b border-border px-5 py-3">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus placeholder="Search by name, borrower, segment…" aria-label="Search sources"
                   data-testid="playbook-source-search"
                   className="h-9 w-full rounded-md border border-border bg-surface pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
          </label>
          {types.length > 1 ? (
            <div className="flex flex-wrap gap-1">
              <TypeChip active={!type} onClick={() => setType("")} label={`All (${all.length})`} />
              {types.map(([t, label]) => (
                <TypeChip key={t} active={type === t} onClick={() => setType(type === t ? "" : t)}
                          label={`${label} (${all.filter((s) => s.type === t).length})`} />
              ))}
            </div>
          ) : null}
        </div>
        <div className="min-h-[200px] flex-1 overflow-y-auto px-5 py-3">
          {sources.error ? <ErrorBox error={sources.error} /> : sources.loading ? <Loading what="Finding what can be imported…" /> : groups.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-muted" data-testid="playbook-sources-empty">
              {all.length ? "Nothing matches." : "Nothing to import yet."}
            </p>
          ) : groups.map((g) => (
            <section key={g.type} className="mb-4">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{g.label}</p>
              <ul className="space-y-1">
                {g.items.map((s) => {
                  const key = `${s.type}|${s.id}`;
                  return (
                    <li key={key}>
                      <button type="button" onClick={() => void choose(s)} disabled={!s.available || !!busy}
                              data-testid="playbook-source-row" data-type={s.type} data-id={s.id}
                              className={cn("flex w-full items-start gap-3 rounded-md border border-border px-3 py-2 text-left transition-colors",
                                            s.available ? "hover:border-accent/60 hover:bg-surface-hover" : "cursor-not-allowed opacity-60",
                                            busy === key && "border-accent bg-accent-muted")}>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-text-primary">{s.label}</span>
                          {s.summary ? <span className="mt-0.5 block line-clamp-2 text-[12px] text-text-secondary">{s.summary}</span> : null}
                        </span>
                        {busy === key ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-accent" aria-hidden />
                          : !s.available ? <span className="shrink-0 text-[11px] text-text-muted">Not available</span>
                          : <Plus className="mt-0.5 size-4 shrink-0 text-text-muted" aria-hidden />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {(sources.data?.unavailable ?? []).length ? (
            <div className="mt-2 space-y-1 rounded-md bg-surface-sunken px-3 py-2 text-[11px] text-text-muted" data-testid="playbook-sources-unavailable">
              {(sources.data?.unavailable ?? []).map((u) => <p key={u.type}>{u.type}: {u.reason}</p>)}
            </div>
          ) : null}
        </div>
        {error ? <p className="border-t border-border px-5 py-2 text-sm text-negative" role="alert" data-testid="playbook-import-error">{error}</p> : null}
      </div>
    </div>
  );
}

function orderOf(t: string): number {
  const i = SOURCE_ORDER.indexOf(t);
  return i < 0 ? 99 : i;
}

function TypeChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
            className={cn("rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
                          active ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent/60")}>
      {label}
    </button>
  );
}
