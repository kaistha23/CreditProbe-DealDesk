"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { backOr } from "@/lib/v5/back";
import * as React from "react";
import {
  Archive, ArchiveRestore, ArrowLeft, FileEdit, Inbox, Layers, ListFilter, MailCheck, MailOpen, Paperclip, PenSquare, Plus,
  ScrollText, Search, Send, Shield, Star, Tag, Users, X,
} from "lucide-react";

import { useWideContent } from "@/components/layout/content-width";
import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { UserAvatar } from "@/components/v5/core/user-menu";
import { MailAdmin } from "@/components/v5/mail/admin";
import { Compose, type ComposeInit } from "@/components/v5/mail/compose";
import { LabelChip, ObjectPanel } from "@/components/v5/mail/objects";
import { useDirectory } from "@/components/v5/mail/people";
import { ThreadView } from "@/components/v5/mail/thread-view";
import {
  core, hasFilters, listWhen, mailChanged, type BulkAction, type Folder, type Label, type MailCounts, type MailFilters,
  type MailObject, type ThreadSummary,
} from "@/lib/v5/core";
import { useWs } from "@/lib/v5/workspace";
import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";

const FOLDERS: { id: Folder; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "starred", label: "Starred", icon: Star },
  { id: "sent", label: "Sent", icon: Send },
  { id: "drafts", label: "Drafts", icon: FileEdit },
  { id: "archive", label: "Archive", icon: Archive },
  { id: "all", label: "All mail", icon: Layers },
];
const FOLDER_NAME: Record<Folder, string> = { inbox: "Inbox", starred: "Starred", sent: "Sent", drafts: "Drafts", archive: "Archive", all: "All mail" };
const LABEL_COLOURS = ["#2563eb", "#d97706", "#dc2626", "#0d9488", "#7c3aed", "#16a34a", "#db2777", "#475569"];

function isFolder(v: string | null): v is Folder {
  return v === "inbox" || v === "sent" || v === "drafts" || v === "archive" || v === "starred" || v === "all";
}

/** A small menu of labels, for bulk "Label as" and "Move to". */
function LabelPick({ labels, testId, text, icon, onPick, disabled }: {
  labels: Label[]; testId: string; text: string; icon: React.ReactNode; onPick: (name: string) => void; disabled?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" disabled={disabled} onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid={testId}>{icon} {text}</Button>
      {open ? (
        <ul className="absolute left-0 z-30 mt-1 w-48 rounded-md border border-border bg-surface p-1 shadow-lg" data-testid={`${testId}-menu`}>
          {labels.map((l) => (
            <li key={l.name}>
              <button type="button" onClick={() => { setOpen(false); onPick(l.name); }} data-testid={`${testId}-option-${l.name}`}
                      className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-hover">
                <span className="size-2 rounded-full" style={{ background: l.color }} aria-hidden />{l.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Create a label with a colour, from the folders pane. */
function NewLabel({ onMade, disabled }: { onMade: () => void; disabled: boolean }) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [color, setColor] = React.useState(LABEL_COLOURS[0]);
  const [error, setError] = React.useState<string | null>(null);
  if (disabled) return null;
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} data-testid="label-create"
              className="mt-1 flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-text-muted hover:bg-surface-hover hover:text-text-primary">
        <Plus className="size-3.5" aria-hidden /> New label
      </button>
    );
  }
  return (
    <form className="mt-1 space-y-1.5 rounded-md border border-border p-2" data-testid="label-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            core.createLabel(name.trim(), color).then(() => { setName(""); setOpen(false); setError(null); mailChanged(); onMade(); },
              (err: unknown) => setError(friendlyMessage(err)));
          }}>
      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Label name" aria-label="Label name" autoFocus
             data-testid="label-create-name" className="w-full rounded border border-border bg-surface px-2 py-1 text-xs" />
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Colour">
        {LABEL_COLOURS.map((c) => (
          <button key={c} type="button" role="radio" aria-checked={color === c} aria-label={c} onClick={() => setColor(c)} data-testid={`label-create-color-${c.slice(1)}`}
                  className={cn("size-4 rounded-full ring-offset-1", color === c && "ring-2 ring-text-primary")} style={{ background: c }} />
        ))}
      </div>
      {error ? <p role="alert" className="text-[11px] text-negative">{error}</p> : null}
      <div className="flex gap-1">
        <Button size="sm" type="submit" data-testid="label-create-submit">Create</Button>
        <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>
  );
}

/** The search filters (server side): from, to, has attachment, label, date range. */
function FilterPanel({ filters, labels, onApply, onClose }: {
  filters: MailFilters; labels: Label[]; onApply: (f: MailFilters) => void; onClose: () => void;
}) {
  const users = useDirectory();
  const [f, setF] = React.useState<MailFilters>(filters);
  const field = "h-8 w-full rounded-md border border-border bg-surface px-2 text-xs text-text-primary focus:border-accent focus:outline-none";
  const set = (patch: Partial<MailFilters>) => setF((x) => ({ ...x, ...patch }));
  return (
    <form className="grid grid-cols-2 gap-2 rounded-md border border-border bg-surface-sunken/40 p-2 text-xs" data-testid="mail-filters"
          onSubmit={(e) => { e.preventDefault(); onApply(f); }}>
      <label className="space-y-0.5"><span className="text-text-muted">From</span>
        <select value={f.from ?? ""} onChange={(e) => set({ from: e.target.value })} className={field} data-testid="filter-from" aria-label="From">
          <option value="">Anyone</option>
          {users.map((u) => <option key={u.username} value={u.username}>{u.name}</option>)}
        </select>
      </label>
      <label className="space-y-0.5"><span className="text-text-muted">To</span>
        <select value={f.to ?? ""} onChange={(e) => set({ to: e.target.value })} className={field} data-testid="filter-to" aria-label="To">
          <option value="">Anyone</option>
          {users.map((u) => <option key={u.username} value={u.username}>{u.name}</option>)}
        </select>
      </label>
      <label className="space-y-0.5"><span className="text-text-muted">Label</span>
        <select value={f.label ?? ""} onChange={(e) => set({ label: e.target.value })} className={field} data-testid="filter-label" aria-label="Label">
          <option value="">Any label</option>
          {labels.map((l) => <option key={l.name} value={l.name}>{l.name}</option>)}
        </select>
      </label>
      <label className="flex items-end gap-1.5 pb-1.5">
        <input type="checkbox" checked={!!f.has_attachment} onChange={(e) => set({ has_attachment: e.target.checked })} data-testid="filter-has-attachment" />
        <span>Has attachment</span>
      </label>
      <label className="space-y-0.5"><span className="text-text-muted">After (from date)</span>
        <input type="date" value={f.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} className={field} data-testid="filter-date-from" aria-label="From date" />
      </label>
      <label className="space-y-0.5"><span className="text-text-muted">Before (to date)</span>
        <input type="date" value={f.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} className={field} data-testid="filter-date-to" aria-label="To date" />
      </label>
      <div className="col-span-2 flex gap-1.5">
        <Button size="sm" type="submit" data-testid="filter-apply">Search</Button>
        <Button size="sm" type="button" variant="ghost" onClick={() => { onApply({ q: f.q }); setF({ q: f.q }); }} data-testid="filter-clear">Clear filters</Button>
        <span className="flex-1" />
        <Button size="sm" type="button" variant="ghost" onClick={onClose} data-testid="filter-close">Close</Button>
      </div>
    </form>
  );
}

/** One conversation in the list: select, star, who, subject, preview, attachment, time, labels, unread. */
function Row({ t, viewing, selected, checked, readOnly, labelColour, onOpen, onCheck, onStar }: {
  t: ThreadSummary; viewing: string; selected: boolean; checked: boolean; readOnly: boolean;
  labelColour: (name: string) => string | undefined; onOpen: () => void; onCheck: (v: boolean) => void; onStar: () => void;
}) {
  const id = t.thread_id ?? t.draft_id ?? "";
  const others = (t.senders?.length ? t.senders : t.participants).filter((p) => p.username !== viewing);
  const who = t.draft_id
    ? `Draft to ${t.participants.map((p) => p.name.split(" ")[0]).join(", ") || "nobody yet"}`
    : others.map((p) => p.name.split(" ")[0]).slice(0, 3).join(", ") || "Me";
  const avatar = t.draft_id ? null : others[0] ?? t.last_sender ?? null;
  return (
    <li data-testid="mail-row" data-thread-id={id} data-unread={t.unread ? "true" : "false"} data-starred={t.starred ? "true" : "false"}
        onClick={onOpen}
        className={cn("group flex cursor-pointer items-start gap-2 px-2.5 py-2.5 hover:bg-surface-hover", selected && "bg-accent-muted/40", checked && "bg-accent-muted/25")}>
      <span className="flex flex-col items-center gap-1.5 pt-0.5" onClick={(e) => e.stopPropagation()}>
        {!readOnly && !t.draft_id ? (
          <input type="checkbox" checked={checked} onChange={(e) => onCheck(e.target.checked)} aria-label={`Select ${t.subject}`} data-testid="row-select" className="size-3.5" />
        ) : <span className="size-3.5" />}
        {!t.draft_id ? (
          <button type="button" onClick={onStar} disabled={readOnly} aria-pressed={t.starred} aria-label={t.starred ? "Unstar" : "Star"} data-testid="row-star"
                  className="text-text-muted hover:text-warning disabled:cursor-default">
            <Star className={cn("size-3.5", t.starred && "fill-warning text-warning")} aria-hidden />
          </button>
        ) : null}
      </span>
      {avatar ? <UserAvatar user={avatar} size={30} /> : <span className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-surface-sunken text-text-muted"><FileEdit className="size-3.5" aria-hidden /></span>}
      <button type="button" className="min-w-0 flex-1 text-left" data-testid="row-open" onClick={(e) => { e.stopPropagation(); onOpen(); }}>
        <span className="flex items-baseline gap-1.5">
          {t.unread ? <span className="size-2 shrink-0 self-center rounded-full bg-accent" data-testid="row-unread-dot" aria-label="Unread" /> : null}
          <span className={cn("min-w-0 flex-1 truncate text-sm", t.unread ? "font-semibold text-text-primary" : "text-text-secondary")} data-testid="row-sender">
            {t.draft_id ? <em>{who}</em> : who}{t.message_count > 1 ? <span className="ml-1 text-[11px] font-normal text-text-muted">({t.message_count})</span> : null}
          </span>
          {t.has_attachments ? <Paperclip className="size-3.5 shrink-0 text-text-muted" aria-label="Has attachments" data-testid="row-attachment" /> : null}
          <span className={cn("shrink-0 text-[11px] tabular-nums", t.unread ? "font-semibold text-text-primary" : "text-text-muted")} data-testid="row-time" title={t.last_at}>{listWhen(t.last_at)}</span>
        </span>
        <span className={cn("block truncate text-sm", t.unread ? "font-semibold text-text-primary" : "text-text-primary")} data-testid="row-subject">{t.subject}</span>
        <span className="block truncate text-xs text-text-muted" data-testid="row-snippet">{t.snippet}</span>
        {t.labels.length ? (
          <span className="mt-1 flex flex-wrap gap-1">{t.labels.map((l) => <LabelChip key={l} name={l} color={labelColour(l)} />)}</span>
        ) : null}
      </button>
    </li>
  );
}

/** CreditProbe Mail: folders and labels | conversations | the reading pane. Folder, thread, search, filters,
 *  label and mailbox all live in the address, so Back and links work. */
export function MailApp() {
  // Three panes need the full width of the content column (PLAN_R10 S3).
  useWideContent();
  const router = useRouter();
  const params = useSearchParams();
  const { effective, viewingAs, isAdmin } = useCoreAuth();
  const folder: Folder = isFolder(params.get("folder")) ? (params.get("folder") as Folder) : "inbox";
  const threadId = params.get("thread");
  const label = params.get("label") ?? "";
  const mailbox = params.get("mailbox") ?? "";
  const admin = params.get("admin") === "1" && isAdmin;
  const composeTo = params.get("to");
  const draftParam = params.get("draft");
  const composeOpen = params.get("compose") === "1" || !!draftParam;
  const filters: MailFilters = {
    from: params.get("from") ?? "", to: params.get("rcpt") ?? "", has_attachment: params.get("att") === "1",
    date_from: params.get("after") ?? "", date_to: params.get("before") ?? "",
  };
  const [q, setQ] = React.useState(params.get("q") ?? "");
  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const [showFilters, setShowFilters] = React.useState(false);
  const [reload, setReload] = React.useState(0);
  const [panel, setPanel] = React.useState<MailObject | null>(null);
  const [toast, setToast] = React.useState<string | null>(null);
  const [checked, setChecked] = React.useState<Set<string>>(new Set());
  const [bulkError, setBulkError] = React.useState<string | null>(null);
  const viewing = mailbox || effective?.username || "";
  const readOnly = !!viewingAs || (!!mailbox && mailbox !== effective?.username);

  // R7: opening a message, a folder, a label or the administration is a step (pushed, so Back returns to it);
  // typing a search or a filter refines the same step (replaced).
  const go = React.useCallback((patch: Record<string, string | null>, mode: "replace" | "push" = "replace") => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) { if (v === null || v === "") next.delete(k); else next.set(k, v); }
    const s = next.toString();
    const url = `/messages${s ? `?${s}` : ""}`;
    if (mode === "push") router.push(url, { scroll: false }); else router.replace(url, { scroll: false });
  }, [params, router]);

  const bump = React.useCallback(() => { setReload((r) => r + 1); mailChanged(); }, []);
  React.useEffect(() => {
    const on = () => setReload((r) => r + 1);
    window.addEventListener("cp-v5-mail-changed", on);
    // New mail arrives while Mail is open: the list re-reads with the header's poll.
    const t = window.setInterval(on, 20000);
    return () => { window.removeEventListener("cp-v5-mail-changed", on); window.clearInterval(t); };
  }, []);

  // Search is applied to the address after a pause so each keystroke is not a request.
  React.useEffect(() => {
    const t = window.setTimeout(() => { if ((params.get("q") ?? "") !== q) go({ q: q || null }); }, 300);
    return () => window.clearTimeout(t);
  }, [q, params, go]);

  const search = params.get("q") ?? "";
  const listKey = `${folder}|${search}|${unreadOnly}|${label}|${mailbox}|${filters.from}|${filters.to}|${filters.has_attachment}|${filters.date_from}|${filters.date_to}|${effective?.username}`;
  // A change of folder or filter clears the selection.
  const [selFor, setSelFor] = React.useState(listKey);
  if (selFor !== listKey) { setSelFor(listKey); setChecked(new Set()); }
  const folders = useWs(() => core.folders(mailbox), `folders|${mailbox}|${reload}|${effective?.username}`, `folders|${mailbox}`);
  const list = useWs(() => core.threads({ folder, q: search, unread: unreadOnly, label, mailbox, ...filters }), `threads|${listKey}|${reload}`, `threads|${listKey}`);
  // While a conversation re-reads after a change (a star, a label), the last copy of the same one stays on screen.
  const thread = useWs(() => (threadId && !admin ? core.thread(threadId, mailbox) : Promise.resolve(null)),
                       `thread|${threadId}|${mailbox}|${reload}|${effective?.username}`, `${threadId}|${mailbox}`);
  const shownThread = thread.data;

  // Opening a conversation marks it read, once per opening (a signed-in reader only; reading another
  // mailbox changes nothing). "Mark unread" on the open conversation then stays unread until it is opened again.
  const markedRef = React.useRef<string | null>(null);
  React.useEffect(() => { markedRef.current = null; }, [threadId]);
  React.useEffect(() => {
    const t = thread.data;
    if (!t || readOnly || !t.unread || markedRef.current === t.thread_id) return;
    markedRef.current = t.thread_id;
    core.setRead(t.thread_id, true).then(() => { mailChanged(); }, () => undefined);
  }, [thread.data, readOnly]);

  // A saved draft is read on demand; a new message is addressed from ?to=
  const draftLoad = useWs(() => (draftParam ? core.draft(draftParam) : Promise.resolve(null)), `draft|${draftParam}`);
  const draft = React.useMemo<ComposeInit | null>(() => {
    if (!composeOpen) return null;
    if (draftParam) {
      const d = draftLoad.data;
      if (!d) return draftLoad.error ? { mode: "new", to: [], cc: [], bcc: [], subject: "", body_html: "", attachments: [] } : null;
      return { mode: d.mode, to: d.to, cc: d.cc, bcc: d.bcc ?? [], subject: d.subject, body_html: d.body_html, attachments: d.attachments,
               thread_id: d.thread_id, in_reply_to: d.in_reply_to, draft_id: d.draft_id, files: d.files, saved_at: d.updated_at };
    }
    return { mode: "new", to: composeTo ? composeTo.split(",") : [], cc: [], bcc: [], subject: "", body_html: "", attachments: [] };
  }, [composeOpen, draftParam, composeTo, draftLoad.data, draftLoad.error]);

  const counts: MailCounts | undefined = folders.data?.counts;
  const labels: Label[] = React.useMemo(() => folders.data?.labels ?? [], [folders.data]);
  const colourOf = React.useCallback((n: string) => labels.find((l) => l.name === n)?.color, [labels]);
  const items = list.data?.threads ?? null;
  const selectable = (items ?? []).filter((t) => t.thread_id).map((t) => t.thread_id as string);
  const allChecked = selectable.length > 0 && selectable.every((id) => checked.has(id));

  function openItem(t: ThreadSummary) {
    if (t.draft_id) go({ draft: t.draft_id, compose: "1", thread: null }, "push");
    else go({ thread: t.thread_id, compose: null, draft: null, admin: null }, "push");
  }

  async function bulk(action: BulkAction, labelName = "") {
    const ids = [...checked];
    if (!ids.length) return;
    setBulkError(null);
    try {
      const r = await core.bulk(ids, action, labelName);
      const verb: Record<BulkAction, string> = { archive: "archived", unarchive: "moved to Inbox", read: "marked read", unread: "marked unread",
        star: "starred", unstar: "unstarred", label: `labelled ${labelName}`, unlabel: `unlabelled ${labelName}`, move: `moved to ${labelName}` };
      setToast(`${r.updated} conversation${r.updated === 1 ? "" : "s"} ${verb[action]}.`);
      setChecked(new Set());
      bump();
    } catch (e) { setBulkError(friendlyMessage(e)); }
  }

  async function star(t: ThreadSummary) {
    if (!t.thread_id || readOnly) return;
    try { await core.setStar(t.thread_id, !t.starred); } finally { bump(); }
  }

  const folderCount = (f: Folder): { n: number; kind: "unread" | "total" } | undefined => {
    if (!counts) return undefined;
    if (f === "drafts") return { n: counts.drafts, kind: "total" };
    if (f === "inbox") return { n: counts.unread, kind: "unread" };
    if (f === "sent") return undefined;
    return { n: counts.unread_by_folder?.[f] ?? (f === "starred" ? counts.starred : 0), kind: counts.unread_by_folder ? "unread" : "total" };
  };

  const applyFilters = (f: MailFilters) => {
    go({ from: f.from || null, rcpt: f.to || null, att: f.has_attachment ? "1" : null, after: f.date_from || null,
         before: f.date_to || null, label: f.label || null, folder: f.label && folder === "inbox" ? "all" : (folder === "inbox" ? null : folder), thread: null });
    setShowFilters(false);
  };
  const activeFilters: { key: string; text: string; clear: Record<string, null> }[] = [
    ...(filters.from ? [{ key: "from", text: `From: ${filters.from}`, clear: { from: null } }] : []),
    ...(filters.to ? [{ key: "to", text: `To: ${filters.to}`, clear: { rcpt: null } }] : []),
    ...(filters.has_attachment ? [{ key: "att", text: "Has attachment", clear: { att: null } }] : []),
    ...(label ? [{ key: "label", text: `Label: ${label}`, clear: { label: null } }] : []),
    ...(filters.date_from ? [{ key: "after", text: `After ${filters.date_from}`, clear: { after: null } }] : []),
    ...(filters.date_to ? [{ key: "before", text: `Before ${filters.date_to}`, clear: { before: null } }] : []),
  ];
  const filtering = !!search || hasFilters({ ...filters, label });
  const listTitle = label ? `Label: ${label}` : FOLDER_NAME[folder];

  // PLAN_R10 S3: Mail like Gmail/Outlook. Top: one search bar. Left rail: Compose, folders, labels. Middle: the
  // message list. Right: the reading pane. Three panes from 768 px up, filling the window height; no folder list on
  // top of the mail at any width a desktop uses (Anne's img15 was a zoomed 1440 px window under the old lg break).
  return (
    <div className="flex flex-col gap-3 md:h-[calc(100dvh-8.5rem)] md:min-h-[520px]" data-testid="mail-app">
      <header className="flex shrink-0 flex-wrap items-center gap-3" data-testid="mail-top">
        <h1 className="text-xl font-semibold text-text-primary md:w-[184px]">Mail</h1>
        <div className="relative min-w-0 flex-1 md:max-w-[720px]">
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 focus-within:border-accent" data-testid="mail-searchbar">
            <Search className="size-4 shrink-0 text-text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search mail" aria-label="Search mail" data-testid="mail-search"
                   className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-text-muted" />
            {q ? <button type="button" onClick={() => setQ("")} aria-label="Clear search" data-testid="mail-search-clear" className="text-text-muted hover:text-text-primary"><X className="size-3.5" /></button> : null}
            <button type="button" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters} data-testid="mail-filters-toggle" title="Search filters"
                    aria-label="Search filters"
                    className={cn("rounded-full p-1.5", showFilters || activeFilters.length ? "bg-accent-muted text-accent" : "text-text-muted hover:bg-surface-hover hover:text-text-primary")}>
              <ListFilter className="size-4" aria-hidden />
            </button>
          </div>
          {showFilters ? (
            <div className="absolute inset-x-0 top-11 z-30 shadow-lg">
              <FilterPanel filters={{ ...filters, label, q: search }} labels={labels} onApply={applyFilters} onClose={() => setShowFilters(false)} />
            </div>
          ) : null}
        </div>
        {mailbox && mailbox !== effective?.username ? (
          <span className="rounded-md border border-warning/40 bg-warning-muted px-2 py-1 text-xs text-warning" data-testid="mailbox-banner">
            Reading {mailbox}&apos;s mailbox. Read only.{" "}
            <Link href="/messages?admin=1" className="underline" data-testid="mailbox-back"
                  onClick={(e) => { e.preventDefault(); backOr(router, () => router.push("/messages?admin=1")); }}>Back to all mailboxes</Link>
          </span>
        ) : null}
        {viewingAs ? <span className="rounded-md border border-warning/40 bg-warning-muted px-2 py-1 text-xs text-warning" data-testid="viewing-banner">Viewing {viewingAs.name}&apos;s mail. Read only.</span> : null}
        {isAdmin ? (
          <Button variant={admin ? "default" : "ghost"} size="sm" className="ml-auto" onClick={() => go({ admin: admin ? null : "1", thread: null, mailbox: null }, "push")} data-testid="mail-admin-toggle">
            <Shield aria-hidden /> Administration
          </Button>
        ) : null}
      </header>

      <div className={cn("grid min-h-0 flex-1 gap-3",
                         // Like Gmail and Outlook on a narrower window: with a message open, the rail folds away below
                         // 1280 px so the reading pane keeps a readable width; from 1280 px all three panes show.
                         threadId && !admin
                           ? "md:grid-cols-[minmax(240px,320px)_minmax(0,1fr)] xl:grid-cols-[184px_minmax(260px,360px)_minmax(0,1fr)]"
                           : "md:grid-cols-[184px_minmax(240px,360px)_minmax(0,1fr)]")} data-testid="mail-panes">
        {/* Pane 1: the left rail — Compose, folders, labels */}
        <nav aria-label="Mail folders" className={cn("min-h-0 overflow-y-auto pr-1", admin && "hidden md:block", threadId && !admin && "hidden xl:block")} data-testid="mail-folders">
          <Button onClick={() => go({ compose: "1", draft: null })} disabled={readOnly} data-testid="mail-compose"
                  className="mb-3 h-10 w-full justify-start gap-2 rounded-2xl px-4 shadow-sm"><PenSquare aria-hidden /> Compose</Button>
          <ul className="space-y-0.5">
            {FOLDERS.map(({ id, label: text, icon: Icon }) => {
              const c = folderCount(id);
              const current = folder === id && !label && !admin;
              return (
                <li key={id}>
                  <button type="button" onClick={() => go({ folder: id === "inbox" ? null : id, thread: null, label: null, compose: null, draft: null, admin: null }, "push")}
                          aria-current={current ? "page" : undefined} data-testid={`folder-${id}`}
                          className={cn("flex w-full items-center gap-2 rounded-r-full px-3 py-1.5 text-sm", current ? "bg-accent-muted font-medium text-accent" : "text-text-secondary hover:bg-surface-hover")}>
                    <Icon className="size-4" aria-hidden /><span className="flex-1 text-left">{text}</span>
                    {c && c.n ? <span className={cn("text-xs tabular-nums", c.kind === "unread" && "font-semibold")} data-testid={`folder-${id}-count`} data-kind={c.kind}
                                      title={c.kind === "unread" ? `${c.n} unread` : `${c.n}`}>{c.n}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 px-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Labels</p>
          <ul className="mt-1 space-y-0.5" data-testid="mail-labels">
            {labels.map((l) => (
              <li key={l.name}>
                <button type="button" onClick={() => go({ folder: "all", label: l.name, thread: null, admin: null }, "push")} data-testid={`label-${l.name}`}
                        aria-current={label === l.name && !admin ? "page" : undefined} data-count={l.count} data-unread={l.unread ?? 0}
                        className={cn("flex w-full items-center gap-2 rounded-r-full px-3 py-1.5 text-sm", label === l.name && !admin ? "bg-accent-muted font-medium text-accent" : "text-text-secondary hover:bg-surface-hover")}>
                  <span className="size-2.5 rounded-full" style={{ background: l.color }} aria-hidden />
                  <span className="flex-1 truncate text-left">{l.name}</span>
                  <span className="text-xs tabular-nums" data-testid={`label-count-${l.name}`}>
                    {l.unread ? <strong title={`${l.unread} unread of ${l.count}`}>{l.unread}</strong> : (l.count || "")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <NewLabel disabled={readOnly} onMade={bump} />
          {isAdmin ? (
            <>
              <p className="mt-4 px-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Administration</p>
              <ul className="mt-1 space-y-0.5">
                <li>
                  <button type="button" data-testid="admin-nav-mailboxes" aria-current={admin ? "page" : undefined}
                          onClick={() => { go({ admin: "1", thread: null, mailbox: null }); window.setTimeout(() => document.getElementById("admin-mailboxes")?.scrollIntoView({ block: "start" }), 50); }}
                          className="flex w-full items-center gap-2 rounded-r-full px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-hover">
                    <Users className="size-4" aria-hidden /> All mailboxes
                  </button>
                </li>
                <li>
                  <button type="button" data-testid="admin-nav-audit"
                          onClick={() => { go({ admin: "1", thread: null, mailbox: null }); window.setTimeout(() => document.getElementById("admin-audit")?.scrollIntoView({ block: "start" }), 50); }}
                          className="flex w-full items-center gap-2 rounded-r-full px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-hover">
                    <ScrollText className="size-4" aria-hidden /> Audit log
                  </button>
                </li>
              </ul>
            </>
          ) : null}
        </nav>

        {admin ? (
          <section aria-label="Administration" className="min-h-0 min-w-0 md:col-span-2 md:overflow-y-auto md:pr-1">
            <div className="mb-2 md:hidden">
              <Button variant="ghost" size="sm" onClick={() => backOr(router, () => go({ admin: null }))} data-testid="admin-back"><ArrowLeft aria-hidden /> Back</Button>
            </div>
            <MailAdmin />
          </section>
        ) : (
          <>
            {/* Pane 2: the message list */}
            <section aria-label="Conversations" className={cn("flex min-h-0 min-w-0 flex-col rounded-lg border border-border bg-surface", threadId && "hidden md:flex")} data-testid="mail-list-pane">
              <div className="space-y-2 border-b border-border px-2 py-1.5">
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  {!readOnly && folder !== "drafts" ? (
                    <input type="checkbox" checked={allChecked} disabled={!selectable.length} aria-label="Select all"
                           onChange={(e) => setChecked(e.target.checked ? new Set(selectable) : new Set())} data-testid="mail-select-all" />
                  ) : null}
                  <span className="truncate font-medium text-text-primary" data-testid="mail-list-title">{listTitle}</span>
                  <span className="flex-1" />
                  <label className="flex shrink-0 items-center gap-1.5">
                    <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} data-testid="mail-unread-only" /> Unread only
                  </label>
                </div>
                {activeFilters.length ? (
                  <div className="flex flex-wrap gap-1" data-testid="mail-active-filters">
                    {activeFilters.map((f) => (
                      <span key={f.key} className="inline-flex items-center gap-1 rounded-full bg-accent-muted px-2 py-0.5 text-[11px] text-accent" data-testid="filter-chip" data-filter={f.key}>
                        {f.text}<button type="button" onClick={() => go({ ...f.clear, thread: null })} aria-label={`Remove ${f.text}`} data-testid={`filter-chip-clear-${f.key}`}><X className="size-3" /></button>
                      </span>
                    ))}
                  </div>
                ) : null}
                {checked.size > 0 ? (
                  <div className="flex flex-wrap items-center gap-0.5 rounded-md bg-accent-muted/40 px-1 py-0.5" data-testid="mail-bulk-bar" role="toolbar" aria-label="Selected conversations">
                    <span className="px-1.5 text-xs font-medium text-accent" data-testid="mail-selected-count">{checked.size} selected</span>
                    {folder === "archive"
                      ? <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void bulk("unarchive")} data-testid="bulk-unarchive"><ArchiveRestore aria-hidden /> Move to Inbox</Button>
                      : <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void bulk("archive")} data-testid="bulk-archive"><Archive aria-hidden /> Archive</Button>}
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void bulk("read")} data-testid="bulk-read"><MailCheck aria-hidden /> Mark read</Button>
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void bulk("unread")} data-testid="bulk-unread"><MailOpen aria-hidden /> Mark unread</Button>
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void bulk("star")} data-testid="bulk-star"><Star aria-hidden /> Star</Button>
                    <LabelPick labels={labels} testId="bulk-label" text="Label" icon={<Tag aria-hidden />} onPick={(n) => void bulk("label", n)} />
                    <LabelPick labels={labels} testId="bulk-move" text="Move to" icon={<Layers aria-hidden />} onPick={(n) => void bulk("move", n)} />
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setChecked(new Set())} data-testid="bulk-clear" aria-label="Clear selection"><X aria-hidden /></Button>
                  </div>
                ) : null}
                {bulkError ? <p role="alert" className="text-xs text-negative" data-testid="bulk-error">{bulkError}</p> : null}
              </div>
              {list.error ? <p role="alert" className="p-4 text-sm text-negative" data-testid="mail-error">{list.error}</p> : null}
              {items === null && !list.error ? <p className="p-4 text-sm text-text-muted">Loading…</p> : null}
              {items && items.length === 0 ? <p className="p-6 text-center text-sm text-text-muted" data-testid="mail-empty">{filtering ? "No messages match your search." : "Nothing here."}</p> : null}
              <ul className="min-h-0 flex-1 divide-y divide-border overflow-y-auto" data-testid="mail-list">
                {(items ?? []).map((t) => {
                  const id = t.thread_id ?? t.draft_id ?? "";
                  return (
                    <Row key={id} t={t} viewing={viewing} selected={id === (threadId ?? draftParam)} checked={!!t.thread_id && checked.has(t.thread_id)}
                         readOnly={readOnly} labelColour={colourOf} onOpen={() => openItem(t)} onStar={() => void star(t)}
                         onCheck={(v) => setChecked((s) => { const n = new Set(s); if (v) n.add(id); else n.delete(id); return n; })} />
                  );
                })}
              </ul>
              {list.data ? <p className="border-t border-border px-3 py-1.5 text-[11px] text-text-muted" data-testid="mail-total">{list.data.total} conversation{list.data.total === 1 ? "" : "s"}</p> : null}
            </section>

            {/* Pane 3: the reading pane */}
            <section aria-label="Message" className={cn("min-h-0 min-w-0 md:overflow-y-auto md:pr-1", !threadId && "hidden md:block")} data-testid="mail-reading-pane">
              {threadId ? (
                <div className="mb-2">
                  <Button variant="ghost" size="sm" onClick={() => backOr(router, () => go({ thread: null }))} data-testid="mail-back"><ArrowLeft aria-hidden /> Back</Button>
                </div>
              ) : null}
              {thread.error ? <p role="alert" className="rounded-lg border border-negative/30 p-4 text-sm text-negative" data-testid="thread-error">{thread.error}</p>
                : shownThread ? (
                  <ThreadView thread={shownThread} labels={labels} mailbox={mailbox} onChanged={bump} onOpenObject={(o) => setPanel(o)} onClose={() => go({ thread: null })}
                              onSent={(id) => { setToast("Sent."); bump(); go({ thread: id, folder: "sent", label: null }); }} />
                ) : threadId ? <p className="text-sm text-text-muted">Loading…</p>
                  : <div className="flex h-full min-h-[240px] items-center justify-center rounded-lg border border-dashed border-border text-sm text-text-muted" data-testid="mail-select">Select a conversation to read it.</div>}
            </section>
          </>
        )}
      </div>

      {draft ? (
        <Compose key={draft.draft_id ?? `new|${composeTo}`} init={draft} onClose={() => { bump(); go({ compose: null, draft: null, to: null }); }}
                 onSent={(id) => { setToast("Sent."); bump(); go({ compose: null, draft: null, to: null, thread: id, folder: "sent", label: null }); }} />
      ) : null}
      {panel ? <ObjectPanel object={panel} onClose={() => setPanel(null)} /> : null}
      {toast ? (
        <div role="status" data-testid="mail-toast" className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-text-primary px-4 py-2 text-sm text-surface shadow-lg">
          {toast}<button type="button" className="ml-3 underline" onClick={() => setToast(null)} data-testid="mail-toast-dismiss">Dismiss</button>
        </div>
      ) : null}
    </div>
  );
}
