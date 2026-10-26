"use client";

import Link from "next/link";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UserAvatar } from "@/components/v5/core/user-menu";
import { core, mailWhen } from "@/lib/v5/core";
import { useWs } from "@/lib/v5/workspace";

const ACTIONS = ["", "login", "login_failed", "logout", "view_as", "send", "share", "file_upload", "draft_save", "bulk", "admin_read"];

/** Administrator only: every user's mailbox, and the audit log. */
export function MailAdmin() {
  const boxes = useWs(() => core.mailboxes(), "mailboxes");
  const [actor, setActor] = React.useState("");
  const [action, setAction] = React.useState("");
  const [page, setPage] = React.useState(0);
  const PAGE = 25;
  const audit = useWs(() => core.audit({ actor, action, limit: PAGE, offset: page * PAGE }), `audit|${actor}|${action}|${page}`);

  return (
    <div className="space-y-6" data-testid="mail-admin">
      <section id="admin-mailboxes" className="scroll-mt-4">
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Every mailbox</h2>
        <Card className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>User</TableHead><TableHead>Role</TableHead><TableHead className="text-right">Inbox</TableHead><TableHead className="text-right">Unread</TableHead>
                <TableHead className="text-right">Sent</TableHead><TableHead className="text-right">Drafts</TableHead><TableHead className="text-right">Archive</TableHead><TableHead /></TableRow>
            </TableHeader>
            <TableBody>
              {(boxes.data?.mailboxes ?? []).map((b) => (
                <TableRow key={b.user.username} data-testid={`mailbox-${b.user.username}`}>
                  <TableCell><span className="inline-flex items-center gap-2"><UserAvatar user={b.user} size={22} />{b.user.name}</span></TableCell>
                  <TableCell className="text-text-secondary">{b.user.role}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.counts.inbox}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.counts.unread}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.counts.sent}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.counts.drafts}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.counts.archive}</TableCell>
                  <TableCell className="text-right"><Link href={`/messages?mailbox=${b.user.username}`} className="text-accent hover:underline" data-testid={`open-mailbox-${b.user.username}`}>Open mailbox</Link></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </section>
      <section id="admin-audit" className="scroll-mt-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Audit log</h2>
          <select value={actor} onChange={(e) => { setActor(e.target.value); setPage(0); }} aria-label="Filter by user" data-testid="audit-actor"
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs">
            <option value="">All users</option>
            {(boxes.data?.mailboxes ?? []).map((b) => <option key={b.user.username} value={b.user.username}>{b.user.name}</option>)}
          </select>
          <select value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} aria-label="Filter by action" data-testid="audit-action"
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs">
            {ACTIONS.map((a) => <option key={a} value={a}>{a || "All actions"}</option>)}
          </select>
          <span className="ml-auto text-xs text-text-muted" data-testid="audit-total">{audit.data ? `${audit.data.total} events` : ""}</span>
        </div>
        <Card className="overflow-x-auto p-0">
          <Table>
            <TableHeader><TableRow><TableHead>When (UTC)</TableHead><TableHead>User</TableHead><TableHead>Acting as</TableHead><TableHead>Action</TableHead><TableHead>Target</TableHead></TableRow></TableHeader>
            <TableBody data-testid="audit-rows">
              {(audit.data?.events ?? []).map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap tabular-nums">{mailWhen(e.at)}</TableCell>
                  <TableCell>{e.actor ?? "—"}</TableCell>
                  <TableCell>{e.effective_user && e.effective_user !== e.actor ? e.effective_user : ""}</TableCell>
                  <TableCell><code className="text-xs">{e.action}</code></TableCell>
                  <TableCell className="max-w-[320px] truncate text-text-secondary">{e.target}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
        <div className="mt-2 flex items-center gap-2 text-xs">
          <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-2 py-1 disabled:opacity-40" data-testid="audit-prev">Previous</button>
          <span className="text-text-muted">Page {page + 1}</span>
          <button type="button" disabled={!audit.data || (page + 1) * PAGE >= audit.data.total} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-2 py-1 disabled:opacity-40" data-testid="audit-next">Next</button>
        </div>
      </section>
    </div>
  );
}
