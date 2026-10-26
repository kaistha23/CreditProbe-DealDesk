"use client";

/**
 * A deal's outputs, as in What-If: share through CreditProbe Mail (with the
 * Word report attached if asked), add it to a Playbook report, and download
 * the 5-page Word report. Mail goes to the Core service (port 8505) with the
 * session cookie (MAIL_API.md); Playbook through its Add-to-report dialog
 * (PLAYBOOK_API.md 7).
 */

import Link from "next/link";
import * as React from "react";
import { FileText, Share2, X } from "lucide-react";

import { AddToReportButton } from "@/components/v5/playbook/add-to-report";
import { cn } from "@/lib/utils";
import { type Proposal, money, reportHref } from "@/lib/v5/dealdesk";
import { type PlaybookSource, playbook } from "@/lib/v5/playbook";

import { PrimaryButton, SecondaryButton } from "./kit";
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

function ShareDialog({ p, onClose }: { p: Proposal; onClose: () => void }) {
  const [users, setUsers] = React.useState<User[] | null>(null);
  const [me, setMe] = React.useState("");
  const [error, setError] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [withReport, setWithReport] = React.useState(true);
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState("");
  const [key] = React.useState(() => `dealdesk-${p.proposal_id}-${Math.random().toString(36).slice(2, 12)}`);

  React.useEffect(() => {
    let live = true;
    Promise.all([core<{ users: User[] }>("/api/v1/users"), core<{ effective_user: User }>("/api/v1/auth/me").catch(() => null)])
      .then(([u, m]) => { if (live) { setUsers(u.users); setMe(m?.effective_user?.username ?? ""); } })
      .catch((e: unknown) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, []);

  const label = `${p.obligor.name} · ${p.proposal_id}`;
  const object = { type: "dealdesk-proposal", id: p.proposal_id, label, href: `/deal-desk/${p.proposal_id}`,
                   summary: `${p.obligor.sector} · ${p.obligor.internal_rating} · ask ${money(p.ask.amount, p.ask.currency)} over ${p.ask.tenor_years} years`,
                   meta: { sector: p.obligor.sector, rating: p.obligor.internal_rating } };

  const send = async () => {
    if (!picked.length) return;
    setSending(true);
    setError("");
    try {
      if (withReport) {
        const doc = await fetch(reportHref(p.proposal_id), { credentials: "include" });
        if (!doc.ok) throw new Error("The Word report could not be built.");
        const form = new FormData();
        form.append("file", await doc.blob(), `Deal Desk ${p.proposal_id}.docx`);
        const file = await core<{ file_id: string }>("/api/v1/mail/files", { method: "POST", body: form });
        await core("/api/v1/mail/send", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], subject: `Deal Desk: ${label}`.slice(0, 200), mode: "new",
                                 body_html: `<p>${(note || "The Deal Desk analysis and its Word report.").replace(/</g, "&lt;")}</p>`,
                                 attachments: [{ kind: "object", object }, { kind: "file", file_id: file.file_id }] }),
        });
      } else {
        await core("/api/v1/mail/share", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], note, objects: [object] }),
        });
      }
      setDone(`Shared with ${(users ?? []).filter((u) => picked.includes(u.username)).map((u) => u.name).join(", ")}.`);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Share" data-testid="dealdesk-share-dialog">
      <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-surface p-6 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">Share {p.obligor.name}</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="dealdesk-share-close"><X size={16} /></button>
        </div>
        {done ? (
          <div className="space-y-2" data-testid="dealdesk-share-done">
            <p className="text-[13px] text-positive">{done}</p>
            <Link className="text-[12px] text-accent underline" href="/messages">Open CreditProbe Mail</Link>
          </div>
        ) : (
          <>
            {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
            {users ? (
              <div className="max-h-56 space-y-1 overflow-auto" data-testid="dealdesk-share-users">
                {users.filter((u) => u.username !== me).map((u) => (
                  <label key={u.username} className="flex items-center gap-2 text-[12px]">
                    <input type="checkbox" checked={picked.includes(u.username)} data-testid={`dealdesk-share-user-${u.username}`}
                           onChange={(e) => setPicked((x) => (e.target.checked ? [...x, u.username] : x.filter((y) => y !== u.username)))} />
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent-muted text-[9px] font-semibold">{u.initials}</span>
                    <span className="text-text-primary">{u.name}</span><span className="text-text-muted">· {u.title}</span>
                  </label>))}
              </div>) : error ? null : <div className="h-24 animate-pulse rounded-md bg-surface-hover" />}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note" rows={2} data-testid="dealdesk-share-note"
                      className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]" />
            <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={withReport} onChange={(e) => setWithReport(e.target.checked)}
                   data-testid="dealdesk-share-with-report" /> Attach the Word report</label>
            <div className="flex justify-end gap-2">
              <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
              <PrimaryButton onClick={() => void send()} disabled={!picked.length || sending} data-testid="dealdesk-share-send">{sending ? "Sending…" : "Send"}</PrimaryButton>
            </div>
          </>)}
      </div>
    </div>
  );
}

export function DealActions({ proposal, hasRecommendation, disabled, onNotice, compact = false }: {
  proposal: Proposal; hasRecommendation: boolean; disabled: boolean; onNotice: (m: string) => void; compact?: boolean;
}) {
  const [sharing, setSharing] = React.useState(false);
  const source: PlaybookSource = { type: "dealdesk-proposal", id: proposal.proposal_id, label: `Deal Desk: ${proposal.obligor.name}`,
                                   href: `/deal-desk/${proposal.proposal_id}` };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="dealdesk-actions">
      <SecondaryButton onClick={() => setSharing(true)} disabled={disabled} data-testid="dealdesk-share" title="Share" aria-label="Share">
        <Share2 size={13} />{compact ? null : " Share"}</SecondaryButton>
      <AddToReportButton source={source} disabled={disabled || !hasRecommendation} testId="dealdesk-add-report" defaultTemplate="credit-committee-pack" className="h-8 text-[12px]"
                         build={async () => { const r = await playbook.section("dealdesk-proposal", proposal.proposal_id); return { ...r.section, source: r.source as PlaybookSource }; }}
                         onDone={(r) => onNotice(`Added to “${r.report_title}” in Playbook.`)} />
      <a href={reportHref(proposal.proposal_id)} data-testid="dealdesk-word"
         className={cn("inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover",
                       disabled && "pointer-events-none opacity-40")} title="Word report" aria-label="Word report"><FileText size={13} />{compact ? " Word" : " Word report"}</a>
      {sharing ? <ShareDialog p={proposal} onClose={() => setSharing(false)} /> : null}
    </div>
  );
}
