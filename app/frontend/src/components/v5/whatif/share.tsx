"use client";

/**
 * Share a What-If thread or scenario through CreditProbe Mail, email its Word
 * report, and add it to the report pack (docs/v5/MAIL_API.md, contract v1).
 *
 * The Mail calls go to the Core service (port 8505) with the session cookie;
 * the sender is always the signed-in user. Nothing here names the user. The
 * calls are kept local to What-If so the module does not depend on the Core
 * client file landing first.
 */

import Link from "next/link";
import * as React from "react";
import { FilePlus2, Share2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { AddToReportButton } from "@/components/v5/playbook/add-to-report";
import { playbook, type PlaybookSource } from "@/lib/v5/playbook";
import { whatif } from "@/lib/v5/whatif";
import { friendlyError, friendlyMessage } from "@/lib/v5/errors";

function coreOrigin(): string {
  return (process.env.NEXT_PUBLIC_WORKSPACE_API ?? "http://127.0.0.1:8505").replace(/\/$/, "");
}

interface User { username: string; name: string; title: string; initials: string; team: string }

async function core<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${coreOrigin()}${path}`, { credentials: "include", cache: "no-store", ...init });
  } catch {
    throw new Error("Mail is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    throw new Error(r.status === 401 ? "Sign in to share." : friendlyError("Mail", r.status, body));
  }
  return body as T;
}

export interface ShareProps {
  kind: "whatif-thread" | "whatif-scenario";
  id: string;
  label: string;
  href: string;
  summary?: string;
  meta?: Record<string, unknown>;
  reportUrl?: string;
  disabled?: boolean;
  compact?: boolean;
}

export function ShareButton(props: ShareProps) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} disabled={props.disabled} data-testid={`whatif-share-${props.id}`}
              className={cn("inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover disabled:opacity-40")}>
        <Share2 size={13} /> {props.compact ? "" : "Share"}</button>
      {open ? <ShareDialog {...props} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function ShareDialog({ kind, id, label, href, summary, meta, reportUrl, onClose }: ShareProps & { onClose: () => void }) {
  const [users, setUsers] = React.useState<User[] | null>(null);
  const [me, setMe] = React.useState<string>("");
  const [error, setError] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [withReport, setWithReport] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState("");
  const [key] = React.useState(() => `whatif-${id}-${Math.random().toString(36).slice(2, 12)}`);

  React.useEffect(() => {
    let live = true;
    Promise.all([core<{ users: User[] }>("/api/v1/users"),
                 core<{ effective_user: User }>("/api/v1/auth/me").catch(() => null)])
      .then(([u, m]) => { if (live) { setUsers(u.users); setMe(m?.effective_user?.username ?? ""); } })
      .catch((e: unknown) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, []);

  const object = { type: kind, id, label: label.slice(0, 200), href, summary: (summary ?? "").slice(0, 400), meta: meta ?? {} };

  const send = async () => {
    if (!picked.length) return;
    setSending(true);
    setError("");
    try {
      if (withReport && reportUrl) {
        const doc = await fetch(reportUrl, { credentials: "include" });
        if (!doc.ok) throw new Error("The Word report could not be built.");
        const blob = await doc.blob();
        const form = new FormData();
        form.append("file", blob, `${label.replace(/[^\w -]+/g, "").slice(0, 60) || "what-if"}.docx`);
        const file = await core<{ file_id: string }>("/api/v1/mail/files", { method: "POST", body: form });
        await core("/api/v1/mail/send", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], subject: `What-If: ${label}`.slice(0, 200), mode: "new",
                                 body_html: `<p>${(note || "The What-If scenario and its Word report.").replace(/</g, "&lt;")}</p>`,
                                 attachments: [{ kind: "object", object }, { kind: "file", file_id: file.file_id }] }),
        });
      } else {
        await core("/api/v1/mail/share", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], note, objects: [object] }),
        });
      }
      const names = (users ?? []).filter((u) => picked.includes(u.username)).map((u) => u.name);
      setDone(`Shared with ${names.join(", ")}.`);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true"
         aria-label="Share" data-testid="whatif-share-dialog">
      <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-surface p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">Share “{label}”</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="whatif-share-close"><X size={16} /></button>
        </div>
        {done ? (
          <div className="space-y-2" data-testid="whatif-share-done">
            <p className="text-[13px] text-positive">{done}</p>
            <Link className="text-[12px] text-accent underline" href="/messages">Open CreditProbe Mail</Link>
          </div>
        ) : (
          <>
            {error ? <p className="text-[12px] text-negative" role="alert" data-testid="whatif-share-error">{error}</p> : null}
            {!users && !error ? <p className="text-[12px] text-text-muted">Loading the user directory…</p> : null}
            {users ? (
              <div className="max-h-56 space-y-1 overflow-auto" data-testid="whatif-share-users">
                {users.filter((u) => u.username !== me).map((u) => (
                  <label key={u.username} className="flex items-center gap-2 text-[12px]">
                    <input type="checkbox" checked={picked.includes(u.username)} data-testid={`whatif-share-user-${u.username}`}
                           onChange={(e) => setPicked((p) => (e.target.checked ? [...p, u.username] : p.filter((x) => x !== u.username)))} />
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent-muted text-[9px] font-semibold">{u.initials}</span>
                    <span className="text-text-primary">{u.name}</span><span className="text-text-muted">· {u.title}</span>
                  </label>))}
              </div>) : null}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note" rows={2}
                      data-testid="whatif-share-note"
                      className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]" />
            {reportUrl ? (
              <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={withReport}
                     onChange={(e) => setWithReport(e.target.checked)} data-testid="whatif-share-with-report" /> Email the Word report with it</label>) : null}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1 text-[12px]">Cancel</button>
              <button type="button" onClick={send} disabled={!picked.length || sending} data-testid="whatif-share-send"
                      className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40">
                {sending ? "Sending…" : "Send"}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** Add to report: into a Playbook report (PLAN_R3 S1-1), with the result's figures, decomposition and segments;
 *  and Add to pack: What-If's own Word report pack. */
export function AddToReport({ threadId, scenarioId, disabled, onDone }: { threadId?: string; scenarioId?: string; disabled?: boolean; onDone: (msg: string) => void }) {
  const type = threadId ? "whatif-thread" : "whatif-scenario";
  const id = (threadId ?? scenarioId) as string;
  const source: PlaybookSource = threadId
    ? { type: "whatif-thread", id, label: "What-If thread", href: `/what-if/thread/${id}` }
    : { type: "whatif-scenario", id, label: "What-If scenario", href: `/what-if?open=${encodeURIComponent(id)}` };
  return (
    <>
      <AddToReportButton source={source} disabled={disabled} testId={`whatif-add-report-${id}`} defaultTemplate="scenario-report"
                         build={async () => { const r = await playbook.section(type, id); return { ...r.section, source: r.source as PlaybookSource }; }}
                         onDone={(r) => onDone(`Added to “${r.report_title}” in Playbook.`)} />
      <AddToPack threadId={threadId} scenarioId={scenarioId} disabled={disabled} onDone={onDone} />
    </>
  );
}

function AddToPack({ threadId, scenarioId, disabled, onDone }: { threadId?: string; scenarioId?: string; disabled?: boolean; onDone: (msg: string) => void }) {
  const [busy, setBusy] = React.useState(false);
  return (
    <button type="button" disabled={disabled || busy} data-testid={`whatif-add-pack-${threadId ?? scenarioId}`}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await whatif.addToReport(threadId ? { thread_id: threadId } : { scenario_id: scenarioId });
                onDone(`Added “${r.added.name}” to the report pack (${r.items.length} item${r.items.length === 1 ? "" : "s"}). The pack is on the What-If page.`);
              } catch (e) { onDone(friendlyMessage(e)); } finally { setBusy(false); }
            }}
            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] hover:bg-surface-hover disabled:opacity-40">
      <FilePlus2 size={13} /> Add to pack</button>
  );
}
