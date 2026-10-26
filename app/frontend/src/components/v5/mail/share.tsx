"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import * as React from "react";
import { Loader2, Share2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { AttachmentCard } from "@/components/v5/mail/objects";
import { UserPicker, useDirectory } from "@/components/v5/mail/people";
import { core, mailChanged, type MailObject } from "@/lib/v5/core";
import { friendlyMessage } from "@/lib/v5/errors";

/**
 * Share anything in CreditProbe with colleagues: picks people, takes an optional note, and sends it through
 * CreditProbe Mail with the object attached. Every Share button in the system opens this one dialog.
 */
export function ShareDialog({ objects, subject, onClose }: { objects: MailObject[]; subject?: string; onClose: () => void }) {
  const { viewingAs } = useCoreAuth();
  const users = useDirectory();
  const [to, setTo] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<{ thread_id: string; names: string[] } | null>(null);
  // One idempotency key per opened dialog, made when Share is first pressed: a retry after a network error reuses it
  // (no second message), a new dialog gets a new one.
  const keyRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    // Capture phase and stopped: an Escape that closes this dialog must not also close the drawer under it.
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  async function send() {
    if (!to.length || busy) return;
    setBusy(true);
    setError(null);
    if (!keyRef.current) keyRef.current = `share-${crypto.randomUUID()}`;
    try {
      const r = await core.share({ to, note, objects, subject }, keyRef.current);
      setDone({ thread_id: r.thread_id, names: r.recipients.map((u) => users.find((x) => x.username === u)?.name ?? u) });
      mailChanged();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-label="Share" data-testid="share-dialog" className="w-full max-w-[520px] rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Share</h2>
            <p className="text-xs text-text-muted">Sent to CreditProbe Mail with a link back to the same view.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="share-close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {objects.map((o) => <AttachmentCard key={`${o.type}|${o.id}`} att={{ kind: "object", object: o }} />)}
        </div>
        {done ? (
          <div className="mt-4 space-y-3" data-testid="share-done">
            <p className="text-sm text-positive">Shared with {done.names.join(", ")}.</p>
            <div className="flex gap-2">
              <Button asChild variant="outline" size="sm"><Link href={`/messages?folder=sent&thread=${done.thread_id}`} data-testid="share-open-mail">Open in Mail</Link></Button>
              <Button size="sm" onClick={onClose} data-testid="share-finish">Done</Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            {viewingAs ? <p role="alert" className="text-sm text-warning">You are viewing as {viewingAs.name}. Stop viewing as to share.</p> : null}
            <UserPicker label="To" value={to} onChange={setTo} testId="share-to" />
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note (optional)" rows={3} maxLength={8000}
                      aria-label="Note" data-testid="share-note"
                      className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
            {error ? <p role="alert" className="text-sm text-negative" data-testid="share-error">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onClose} data-testid="share-cancel">Cancel</Button>
              <Button size="sm" onClick={() => void send()} disabled={!to.length || busy || !!viewingAs} data-testid="share-send">
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} Share
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** A Share button for any CreditProbe object. */
export function ShareButton({ object, label = "Share", variant = "outline", size = "sm", testId = "share-button" }: {
  object: MailObject | MailObject[]; label?: string; variant?: "outline" | "ghost" | "default" | "subtle"; size?: "sm" | "default";
  testId?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const objects = Array.isArray(object) ? object : [object];
  return (
    <>
      <Button variant={variant} size={size} onClick={() => setOpen(true)} data-testid={testId}>
        <Share2 aria-hidden /> {label}
      </Button>
      {open ? <ShareDialog objects={objects} onClose={() => setOpen(false)} /> : null}
    </>
  );
}


/** The address of the screen the reader is on, without the in-place `embed` flag: what a recipient's link opens. */
export function currentHref(pathname: string, search: URLSearchParams): string {
  const q = new URLSearchParams(search.toString());
  q.delete("embed");
  const s = q.toString();
  return pathname + (s ? `?${s}` : "");
}

/** Share the screen the reader is on (an Early Warning list, a Borrower 360 page): the link brings the recipient back to it. */
export function ShareCurrent({ type, id, label, summary, meta, testId = "share-button", variant = "outline" }: {
  type: MailObject["type"]; id: string; label: string; summary?: string; meta?: Record<string, unknown>; testId?: string;
  variant?: "outline" | "ghost" | "default" | "subtle";
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  return <ShareButton object={{ type, id, label, href: currentHref(pathname, params), summary, meta }} testId={testId} variant={variant} />;
}
