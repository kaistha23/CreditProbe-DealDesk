"use client";

/**
 * R16 b: share a business request inside CreditProbe (Mail on the Core service, as the deal Share does): the request as a
 * linked object (opens the studio on the request), the Word file attached if asked. The share is recorded on the request
 * (dd_business_request.shared_with).
 */

import Link from "next/link";
import * as React from "react";
import { X } from "lucide-react";

import { friendlyError, friendlyMessage } from "@/lib/v5/errors";

import { PrimaryButton, SecondaryButton } from "../kit";
import { fileHref, getJson } from "../papers/paper-view";
import { type BusinessRequest, brHref, brUrls, money } from "./model";

function coreOrigin(): string {
  return (process.env.NEXT_PUBLIC_WORKSPACE_API ?? "http://127.0.0.1:8505").replace(/\/$/, "");
}

interface User { username: string; name: string; title: string; initials: string }

async function core<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${coreOrigin()}${path}`, { credentials: "include", cache: "no-store", ...init });
  } catch {
    throw new Error("Mail is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(r.status === 401 ? "Sign in to share." : friendlyError("Mail", r.status, body));
  return body as T;
}

export function ShareRequestDialog({ p, onClose, onShared }: { p: BusinessRequest; onClose: () => void; onShared?: (to: string[]) => void }) {
  const [users, setUsers] = React.useState<User[] | null>(null);
  const [me, setMe] = React.useState("");
  const [error, setError] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [withWord, setWithWord] = React.useState(true);
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState("");
  const [key] = React.useState(() => `br-${p.request_id}-${Math.random().toString(36).slice(2, 12)}`);

  React.useEffect(() => {
    let live = true;
    Promise.all([core<{ users: User[] }>("/api/v1/users"), core<{ effective_user: User }>("/api/v1/auth/me").catch(() => null)])
      .then(([u, m]) => { if (live) { setUsers(u.users); setMe(m?.effective_user?.username ?? ""); } })
      .catch((e: unknown) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, []);

  const label = `Business request · ${p.customer}`;
  // "report" is a registered Mail object type (backend/mail_v5/store.py OBJECT_TYPES); kind says what it is
  const object = { type: "report", id: p.request_id, label, href: brHref(p.request_id),
                   summary: `${p.ask_text.slice(0, 140)} · proposed ${money(p.totals.proposed)}`, meta: { kind: "business-request", customer: p.customer, rm: p.rm } };

  const send = async () => {
    if (!picked.length) return;
    setSending(true);
    setError("");
    try {
      if (withWord) {
        const doc = await fetch(fileHref(brUrls.docx(p.request_id)), { credentials: "include" });
        if (!doc.ok) throw new Error("The Word file could not be built.");
        const form = new FormData();
        form.append("file", await doc.blob(), `Business request ${p.customer}.docx`);
        const file = await core<{ file_id: string }>("/api/v1/mail/files", { method: "POST", body: form });
        await core("/api/v1/mail/send", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], subject: label.slice(0, 200), mode: "new",
                                 body_html: `<p>${(note || "The business request for your review, with its Word file.").replace(/</g, "&lt;")}</p>`,
                                 attachments: [{ kind: "object", object }, { kind: "file", file_id: file.file_id }] }),
        });
      } else {
        await core("/api/v1/mail/share", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], note, objects: [object] }),
        });
      }
      await getJson(brUrls.share(p.request_id), { method: "POST", body: JSON.stringify({ to: picked }) }).catch(() => null);
      onShared?.(picked);
      setDone(`Shared with ${(users ?? []).filter((u) => picked.includes(u.username)).map((u) => u.name).join(", ")}.`);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Share the business request" data-testid="br-share-dialog">
      <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-surface p-6 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">Share the business request</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="br-share-close"><X size={16} /></button>
        </div>
        {done ? (
          <div className="space-y-2" data-testid="br-share-done">
            <p className="text-[13px] text-positive">{done}</p>
            <Link className="text-[12px] text-accent underline" href="/messages">Open CreditProbe Mail</Link>
          </div>
        ) : (
          <>
            {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
            {users ? (
              <div className="max-h-56 space-y-1 overflow-auto" data-testid="br-share-users">
                {users.filter((u) => u.username !== me).map((u) => (
                  <label key={u.username} className="flex items-center gap-2 text-[12px]">
                    <input type="checkbox" checked={picked.includes(u.username)} data-testid={`br-share-user-${u.username}`}
                           onChange={(e) => setPicked((x) => (e.target.checked ? [...x, u.username] : x.filter((y) => y !== u.username)))} />
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent-muted text-[9px] font-semibold">{u.initials}</span>
                    <span className="text-text-primary">{u.name}</span><span className="text-text-muted">· {u.title}</span>
                  </label>))}
              </div>) : error ? null : <div className="h-24 animate-pulse rounded-md bg-surface-hover" />}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note" rows={2} data-testid="br-share-note"
                      className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]" />
            <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={withWord} onChange={(e) => setWithWord(e.target.checked)}
                   data-testid="br-share-with-word" /> Attach the Word file</label>
            <div className="flex justify-end gap-2">
              <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
              <PrimaryButton onClick={() => void send()} disabled={!picked.length || sending} data-testid="br-share-send">{sending ? "Sending…" : "Send"}</PrimaryButton>
            </div>
          </>)}
      </div>
    </div>
  );
}
