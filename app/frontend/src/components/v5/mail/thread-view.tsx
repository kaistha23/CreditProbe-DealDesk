"use client";

import * as React from "react";
import { Archive, ArchiveRestore, ChevronDown, ChevronUp, Forward, MailOpen, Reply, ReplyAll, Star, Tag, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { UserAvatar } from "@/components/v5/core/user-menu";
import { Compose, type ComposeInit } from "@/components/v5/mail/compose";
import { AttachmentCard, LabelChip } from "@/components/v5/mail/objects";
import { core, mailChanged, mailWhen, replyAllRecipients, replySubject, splitQuoted, type Label, type MailMessage, type MailThread, type OutAttachment } from "@/lib/v5/core";
import { cn } from "@/lib/utils";

function quote(m: MailMessage): string {
  return `<blockquote><p>On ${mailWhen(m.sent_at)} UTC, ${m.sender.name} wrote:</p>${m.body_html}</blockquote>`;
}

function forwardBody(m: MailMessage, subject: string): string {
  const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return `<blockquote><p>---------- Forwarded message ----------<br>From: ${esc(m.sender.name)}<br>Date: ${mailWhen(m.sent_at)} UTC<br>Subject: ${esc(subject)}<br>To: ${esc(m.to.map((u) => u.name).join(", "))}</p>${m.body_html}</blockquote>`;
}

function outAttachments(m: MailMessage): { atts: OutAttachment[]; files: Record<string, { name: string; size: number }> } {
  const files: Record<string, { name: string; size: number }> = {};
  const atts = m.attachments.map((a): OutAttachment => {
    if (a.kind === "file") { files[a.file_id] = { name: a.name, size: a.size }; return { kind: "file", file_id: a.file_id }; }
    return { kind: "object", object: a.object };
  });
  return { atts, files };
}

function LabelMenu({ thread, labels, onChanged }: { thread: MailThread; labels: Label[]; onChanged: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const toggle = async (l: string) => {
    await core.setLabels(thread.thread_id, thread.labels.includes(l) ? [] : [l], thread.labels.includes(l) ? [l] : []);
    onChanged();
  };
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid="thread-labels"><Tag aria-hidden /> Label</Button>
      {open ? (
        <div className="absolute left-0 z-30 mt-1 w-56 rounded-md border border-border bg-surface p-1 shadow-lg" data-testid="label-menu">
          {labels.map((l) => (
            <label key={l.name} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover">
              <input type="checkbox" checked={thread.labels.includes(l.name)} onChange={() => void toggle(l.name)} data-testid={`label-toggle-${l.name}`} />
              <span className="size-2 rounded-full" style={{ background: l.color }} aria-hidden />{l.name}
            </label>
          ))}
          <form className="flex gap-1 border-t border-border p-1 pt-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { void core.setLabels(thread.thread_id, [name.trim()], []).then(() => { setName(""); onChanged(); }); } }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New label" maxLength={40} aria-label="New label"
                   className="min-w-0 flex-1 rounded border border-border bg-surface px-2 py-1 text-xs" data-testid="label-new" />
            <Button size="sm" type="submit" variant="outline">Add</Button>
          </form>
        </div>
      ) : null}
    </div>
  );
}

const BODY = "mail-body text-sm leading-relaxed text-text-primary [&_a]:text-accent [&_a]:underline [&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-text-secondary [&_li]:ml-5 [&_ol]:list-decimal [&_p]:my-1.5 [&_ul]:list-disc";

function Message({ m, me, expanded, onToggle, readOnly, onAct, onOpenObject, last }: {
  m: MailMessage; me: string; expanded: boolean; onToggle: () => void; readOnly: boolean;
  onAct: (mode: "reply" | "reply_all" | "forward", m: MailMessage) => void;
  onOpenObject: React.ComponentProps<typeof AttachmentCard>["onOpen"]; last: boolean;
}) {
  const recipients = [...m.to, ...m.cc];
  const bcc = m.bcc ?? [];
  const [showQuoted, setShowQuoted] = React.useState(false);
  const parts = splitQuoted(m.body_html);
  const name = (u: { username: string; name: string }) => (u.username === me ? "me" : u.name);
  return (
    <article className={cn("rounded-lg border bg-surface", m.unread ? "border-accent/50" : "border-border")} data-testid="mail-message" data-message-id={m.message_id} data-unread={m.unread ? "true" : "false"}>
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex w-full items-start gap-3 px-4 py-3 text-left">
        <UserAvatar user={m.sender} size={32} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold text-text-primary" data-testid="message-sender">{m.sender.name}</span>
            <span className="text-xs text-text-muted">{m.sender.role}</span>
            {m.kind === "share" ? <span className="rounded-full bg-accent-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-accent">Shared</span> : null}
          </span>
          <span className="block truncate text-xs text-text-muted" data-testid="message-recipients">
            to <span data-testid="message-to">{m.to.map(name).join(", ")}</span>
            {m.cc.length ? <>, cc <span data-testid="message-cc">{m.cc.map(name).join(", ")}</span></> : null}
            {bcc.length ? <>, bcc <span data-testid="message-bcc">{bcc.map(name).join(", ")}</span></> : null}
          </span>
          {!expanded ? <span className="mt-1 block truncate text-sm text-text-secondary">{m.body_text.slice(0, 160)}</span> : null}
        </span>
        <span className="shrink-0 text-xs text-text-muted" data-testid="message-time">{mailWhen(m.sent_at)} UTC</span>
      </button>
      {m.attachments.length ? (
        <div className={cn("flex flex-wrap gap-2 px-4 pb-3", expanded && "border-t border-border pt-3")} data-testid="message-attachments">
          {m.attachments.map((a, i) => <AttachmentCard key={i} att={a} onOpen={onOpenObject} />)}
        </div>
      ) : null}
      {expanded ? (
        <div className="border-t border-border px-4 py-3">
          <dl className="mb-2 grid grid-cols-[auto_1fr] gap-x-2 text-xs text-text-muted" data-testid="message-headers">
            <dt>From</dt><dd className="text-text-secondary">{m.sender.name} · {m.sender.role}</dd>
            <dt>To</dt><dd className="text-text-secondary">{m.to.map((u) => u.name).join(", ")}</dd>
            {m.cc.length ? <><dt>Cc</dt><dd className="text-text-secondary">{m.cc.map((u) => u.name).join(", ")}</dd></> : null}
            {bcc.length ? <><dt>Bcc</dt><dd className="text-text-secondary" data-testid="message-headers-bcc">{bcc.map((u) => u.name).join(", ")}</dd></> : null}
            <dt>Date</dt><dd className="text-text-secondary">{mailWhen(m.sent_at)} UTC</dd>
          </dl>
          <div className={BODY} data-testid="message-body" dangerouslySetInnerHTML={{ __html: parts.main }} />
          {parts.quoted ? (
            <div className="mt-1">
              <button type="button" onClick={() => setShowQuoted((v) => !v)} aria-expanded={showQuoted} data-testid="quoted-toggle"
                      className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-text-muted hover:bg-surface-hover hover:text-text-primary">
                {showQuoted ? <ChevronUp className="size-3" aria-hidden /> : <ChevronDown className="size-3" aria-hidden />}
                {showQuoted ? "Hide quoted text" : "Show quoted text"}
              </button>
              {showQuoted ? <div className={BODY} data-testid="message-quoted" dangerouslySetInnerHTML={{ __html: parts.quoted }} /> : null}
            </div>
          ) : null}
          {!readOnly ? (
            <div className="mt-3 flex gap-1.5">
              {last ? (
                <>
                  <Button variant="outline" size="sm" onClick={() => onAct("reply", m)} data-testid="mail-reply"><Reply aria-hidden /> Reply</Button>
                  {recipients.length > 1 || m.sender.username !== me ? (
                    <Button variant="outline" size="sm" onClick={() => onAct("reply_all", m)} data-testid="mail-reply-all"><ReplyAll aria-hidden /> Reply all</Button>
                  ) : null}
                </>
              ) : null}
              <Button variant="outline" size="sm" onClick={() => onAct("forward", m)} data-testid="mail-forward"><Forward aria-hidden /> Forward</Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

/** One conversation: its messages, the actions on it, and the reply composer. */
export function ThreadView({ thread, labels, mailbox, onChanged, onOpenObject, onSent, onClose }: {
  thread: MailThread; labels: Label[]; mailbox: string; onChanged: () => void; onClose?: () => void;
  onOpenObject: React.ComponentProps<typeof AttachmentCard>["onOpen"]; onSent: (threadId: string) => void;
}) {
  const { effective, viewingAs } = useCoreAuth();
  const me = effective?.username ?? "";
  const readOnly = !!viewingAs || (mailbox !== "" && mailbox !== me);
  const [open, setOpen] = React.useState<Set<string>>(new Set());
  const [composeInit, setComposeInit] = React.useState<ComposeInit | null>(null);
  const lastId = thread.messages[thread.messages.length - 1].message_id;
  const expanded = (m: MailMessage) => open.has(m.message_id) || m.message_id === lastId || m.unread;
  const flip = (id: string) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  function act(mode: "reply" | "reply_all" | "forward", m: MailMessage) {
    const { atts, files } = outAttachments(m);
    if (mode === "forward") {
      setComposeInit({ mode, to: [], cc: [], bcc: [], subject: thread.subject.toLowerCase().startsWith("fwd:") ? thread.subject : `Fwd: ${thread.subject}`,
                       body_html: "", quote_html: forwardBody(m, thread.subject), attachments: atts, thread_id: thread.thread_id, in_reply_to: m.message_id, files });
      return;
    }
    const to = mode === "reply_all" ? replyAllRecipients(m, me) : { to: m.sender.username !== me ? [m.sender.username] : m.to.map((u) => u.username), cc: [] };
    setComposeInit({ mode, to: to.to, cc: to.cc, bcc: [], subject: replySubject(thread.subject), body_html: "", quote_html: quote(m), attachments: [], thread_id: thread.thread_id, in_reply_to: m.message_id });
  }

  const run = async (fn: () => Promise<unknown>) => { try { await fn(); } finally { mailChanged(); onChanged(); } };

  return (
    <div className="space-y-3" data-testid="thread-view" data-thread-id={thread.thread_id}>
      <header>
        <div className="flex items-start gap-2">
          <h2 className="min-w-0 flex-1 text-lg font-semibold text-text-primary" data-testid="thread-subject">{thread.subject}</h2>
          <span className="shrink-0 pt-1 text-xs text-text-muted" data-testid="thread-count">{thread.messages.length} message{thread.messages.length === 1 ? "" : "s"}</span>
          {onClose ? <button type="button" onClick={onClose} aria-label="Close conversation" data-testid="thread-close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button> : null}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {thread.labels.map((l) => <LabelChip key={l} name={l} color={labels.find((x) => x.name === l)?.color} testId="thread-label" />)}
        </div>
        {!readOnly ? (
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <Button variant="ghost" size="sm" aria-pressed={thread.starred} onClick={() => void run(() => core.setStar(thread.thread_id, !thread.starred))} data-testid="thread-star">
              <Star className={cn(thread.starred && "fill-warning text-warning")} aria-hidden /> {thread.starred ? "Starred" : "Star"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void run(() => core.setArchive(thread.thread_id, !thread.archived))} data-testid="thread-archive">
              {thread.archived ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />} {thread.archived ? "Move to Inbox" : "Archive"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void run(() => core.setRead(thread.thread_id, false))} data-testid="thread-mark-unread"><MailOpen aria-hidden /> Mark unread</Button>
            <LabelMenu thread={thread} labels={labels} onChanged={() => { mailChanged(); onChanged(); }} />
          </div>
        ) : null}
      </header>
      {thread.messages.map((m, i) => (
        <Message key={m.message_id} m={m} me={me} expanded={expanded(m)} onToggle={() => flip(m.message_id)} readOnly={readOnly}
                 onAct={act} onOpenObject={onOpenObject} last={i === thread.messages.length - 1} />
      ))}
      {composeInit ? (
        <Compose key={`${composeInit.mode}|${composeInit.in_reply_to}`} variant="inline" init={composeInit} onClose={() => setComposeInit(null)}
                 onSent={(id) => { setComposeInit(null); onSent(id); }} />
      ) : null}
    </div>
  );
}
