"use client";

import * as React from "react";
import { Bold, Boxes, Italic, Link2, List, ListOrdered, Loader2, Paperclip, Quote, Send as SendIcon, Trash2, Underline, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { AttachmentCard } from "@/components/v5/mail/objects";
import { UserPicker } from "@/components/v5/mail/people";
import { OBJECT_LABEL, core, mailChanged, type Draft, type MailAttachment, type MailObject, type Mode, type ObjectType, type OutAttachment } from "@/lib/v5/core";
import { ws } from "@/lib/v5/workspace";
import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";
import { edition } from "@/lib/navigation";

export interface ComposeInit {
  mode: Mode; to: string[]; cc: string[]; bcc?: string[]; subject: string; body_html: string; attachments: OutAttachment[];
  thread_id?: string | null; in_reply_to?: string | null; draft_id?: string | null;
  /** Names and sizes of files already attached (from a draft or a forwarded message). */
  files?: Record<string, { name: string; size: number }>;
  /** When a reopened draft was last saved. */
  saved_at?: string;
  /** Reply and forward: the quoted message, kept below what is typed (shown on request) and sent with it. */
  quote_html?: string;
}

type Chip = { key: string; att: OutAttachment; view: MailAttachment | { kind: "file"; file_id: string; name: string; size: number } };

function toChips(items: OutAttachment[], names: Record<string, { name: string; size: number }>): Chip[] {
  return items.map((a, i) => a.kind === "object"
    ? { key: `o|${a.object.type}|${a.object.id}|${i}`, att: a, view: { kind: "object", object: a.object } }
    : { key: `f|${a.file_id}`, att: a, view: { kind: "file", file_id: a.file_id, name: names[a.file_id]?.name ?? "Attachment", size: names[a.file_id]?.size ?? 0 } });
}

function Btn({ onClick, label, children }: { onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={onClick} aria-label={label} title={label}
            data-testid={`rte-${label.toLowerCase().replace(/\s+/g, "-")}`}
            className="rounded p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary">{children}</button>
  );
}

/** Rich-text body: a contentEditable region with a small toolbar (bold, italic, underline, lists, quote, link).
 *  The server sanitises what is sent. A link is added from an inline field, so no browser prompt interrupts. */
function Editor({ html, onChange }: { html: string; onChange: (h: string) => void }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const range = React.useRef<Range | null>(null);
  const [linking, setLinking] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const [linkError, setLinkError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (ref.current && ref.current.innerHTML !== html && document.activeElement !== ref.current) ref.current.innerHTML = html;
  }, [html]);
  const cmd = (c: string, v?: string) => { ref.current?.focus(); document.execCommand(c, false, v); onChange(ref.current?.innerHTML ?? ""); };
  function startLink() {
    const sel = window.getSelection();
    range.current = sel && sel.rangeCount && ref.current?.contains(sel.anchorNode) ? sel.getRangeAt(0).cloneRange() : null;
    setUrl("");
    setLinkError(null);
    setLinking(true);
  }
  function applyLink() {
    const u = url.trim();
    if (!/^(https?:\/\/|mailto:|\/(?!\/))/i.test(u)) { setLinkError(`Use https://…, mailto:… or an in-app path such as ${edition() === "dealdesk" ? "/deal-desk" : "/early-warning"}.`); return; }
    ref.current?.focus();
    const sel = window.getSelection();
    if (sel && range.current) { sel.removeAllRanges(); sel.addRange(range.current); }
    if (!range.current || range.current.collapsed) {
      document.execCommand("insertHTML", false, `<a href="${u.replace(/"/g, "&quot;")}">${u.replace(/</g, "&lt;")}</a>`);
    } else {
      document.execCommand("createLink", false, u);
    }
    onChange(ref.current?.innerHTML ?? "");
    setLinking(false);
  }
  return (
    <div className="rounded-md border border-border bg-surface focus-within:border-accent">
      <div className="flex flex-wrap items-center gap-0.5 border-b border-border px-1.5 py-1" role="toolbar" aria-label="Formatting">
        <Btn onClick={() => cmd("bold")} label="Bold"><Bold className="size-3.5" /></Btn>
        <Btn onClick={() => cmd("italic")} label="Italic"><Italic className="size-3.5" /></Btn>
        <Btn onClick={() => cmd("underline")} label="Underline"><Underline className="size-3.5" /></Btn>
        <Btn onClick={() => cmd("insertUnorderedList")} label="Bulleted list"><List className="size-3.5" /></Btn>
        <Btn onClick={() => cmd("insertOrderedList")} label="Numbered list"><ListOrdered className="size-3.5" /></Btn>
        <Btn onClick={() => cmd("formatBlock", "blockquote")} label="Quote"><Quote className="size-3.5" /></Btn>
        <Btn onClick={startLink} label="Link"><Link2 className="size-3.5" /></Btn>
        {linking ? (
          <span className="ml-1 flex items-center gap-1" data-testid="rte-link-form">
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… or /path" aria-label="Link address" autoFocus
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyLink(); } if (e.key === "Escape") setLinking(false); }}
                   data-testid="rte-link-input" className="h-7 w-52 rounded border border-border bg-surface px-2 text-xs" />
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={applyLink} data-testid="rte-link-apply" className="rounded bg-accent px-2 py-1 text-xs text-accent-contrast">Add link</button>
            <button type="button" onClick={() => setLinking(false)} aria-label="Cancel link" className="text-text-muted"><X className="size-3.5" /></button>
            {linkError ? <span role="alert" className="text-[11px] text-negative" data-testid="rte-link-error">{linkError}</span> : null}
          </span>
        ) : null}
      </div>
      <div ref={ref} contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Message body"
           data-testid="compose-body" onInput={(e) => onChange((e.target as HTMLDivElement).innerHTML)}
           className="prose-mail min-h-[160px] max-h-[360px] overflow-y-auto px-3 py-2 text-sm leading-relaxed text-text-primary outline-none [&_a]:text-accent [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-text-secondary [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc" />
    </div>
  );
}

/** Attach a CreditProbe object: something already in the workspace, a borrower, an Early Warning list or any page. */
function ObjectPicker({ onPick, onClose }: { onPick: (o: MailObject) => void; onClose: () => void }) {
  const [source, setSource] = React.useState<"workspace" | "borrower" | "early-warning" | "page">("workspace");
  const [items, setItems] = React.useState<MailObject[] | null>(null);
  const [borrower, setBorrower] = React.useState("");
  const [domain, setDomain] = React.useState<"corporate" | "retail">("corporate");
  const [segment, setSegment] = React.useState("");
  const [path, setPath] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [ptype, setPtype] = React.useState<ObjectType>("cockpit-thread");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (source !== "workspace") return;
    let live = true;
    Promise.all([ws.investigations(), ws.analyses(), ws.documents(), ws.projects()]).then(([inv, an, doc, pr]) => {
      if (!live) return;
      setItems([
        ...inv.investigations.map((i): MailObject => ({ type: "investigation", id: i.id, label: i.title, href: `/investigations/${i.id}`, summary: i.summary.slice(0, 200) })),
        ...an.analyses.map((a): MailObject => ({ type: "analysis", id: a.id, label: a.title, href: `/analyses/${a.id}`, summary: a.description.slice(0, 200) })),
        ...doc.documents.map((d): MailObject => ({ type: "document", id: d.id, label: d.title, href: `/documents/${d.id}`, summary: d.summary.slice(0, 200) })),
        ...pr.projects.map((p): MailObject => ({ type: "project", id: p.id, label: p.name, href: `/projects/${p.id}`, summary: p.description.slice(0, 200) })),
      ]);
    }, (e: unknown) => { if (live) { setItems([]); setError(friendlyMessage(e)); } });
    return () => { live = false; };
  }, [source]);

  const period = domain === "corporate" ? "2026Q2" : "2026-06";
  function pickBorrower() {
    const id = borrower.trim().toUpperCase();
    if (!/^[A-Z]{2}\d{3,8}$/.test(id)) { setError("Enter a borrower or customer ID such as CB01312 or RC000123."); return; }
    if (edition() === "dealdesk") { onPick({ type: "borrower", id, label: `${id} (customer in Deal Desk)`, href: `/deal-desk/customer-packs?cif=${id}`, meta: { domain, period } }); return; }
    onPick({ type: "borrower", id, label: `${id} (Borrower 360, ${period})`, href: `/borrower-360?domain=${domain}&customer_id=${id}&period=${period}`, meta: { domain, period } });
  }
  function pickEws() {
    const seg = segment.trim();
    onPick({ type: "early-warning-list", id: `${domain}-${period}${seg ? `-${seg}` : ""}`, label: `Early Warning: ${seg || (domain === "corporate" ? "corporate book" : "retail book")}, ${period}`,
             href: `/early-warning?domain=${domain}${seg ? `&segment=${encodeURIComponent(seg)}` : ""}`, meta: { domain, period } });
  }
  function pickPage() {
    const p = path.trim().replace(/^https?:\/\/[^/]+/, "");
    if (!/^\/(?!\/)/.test(p)) { setError(`Paste an in-app address that starts with /, for example ${edition() === "dealdesk" ? "/deal-desk/review" : "/what-if?scenario=…"}`); return; }
    if (!label.trim()) { setError("Give the object a name."); return; }
    onPick({ type: ptype, id: p.slice(0, 120), label: label.trim().slice(0, 200), href: p.slice(0, 500) });
  }

  const tab = (k: typeof source, text: string) => (
    <button type="button" onClick={() => { setSource(k); setError(null); }} aria-pressed={source === k} data-testid={`pick-${k}`}
            className={`rounded-full px-3 py-1 text-xs font-medium ${source === k ? "bg-accent-muted text-accent" : "text-text-secondary hover:text-text-primary"}`}>{text}</button>
  );
  const input = "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none";
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-label="Attach a CreditProbe object" data-testid="object-picker" className="w-full max-w-[560px] rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-text-primary">Attach a CreditProbe object</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {tab("workspace", "Workspace")}{tab("borrower", "Borrower")}{edition() === "dealdesk" ? null : tab("early-warning", "Early Warning list")}{tab("page", "Another page")}
        </div>
        <div className="mt-4">
          {source === "workspace" ? (
            items === null ? <p className="text-sm text-text-muted">Loading…</p> : items.length === 0 ? <p className="text-sm text-text-muted">Nothing in your workspace yet.</p> : (
              <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border" data-testid="pick-workspace-list">
                {items.map((o) => (
                  <li key={`${o.type}|${o.id}`}>
                    <button type="button" onClick={() => onPick(o)} className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-surface-hover" data-object-id={o.id}>
                      <span className="mt-0.5 w-24 shrink-0 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-muted">{OBJECT_LABEL[o.type]}</span>
                      <span className="text-sm text-text-primary">{o.label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )
          ) : null}
          {source === "borrower" || source === "early-warning" ? (
            <div className="space-y-2">
              <select value={domain} onChange={(e) => setDomain(e.target.value as "corporate" | "retail")} className={input} aria-label="Book">
                <option value="corporate">Corporate book (2026Q2)</option><option value="retail">Retail book (2026-06)</option>
              </select>
              {source === "borrower"
                ? <input value={borrower} onChange={(e) => setBorrower(e.target.value)} placeholder="Borrower or customer ID, e.g. CB01312" className={input} aria-label="Borrower ID" data-testid="pick-borrower-id" />
                : <input value={segment} onChange={(e) => setSegment(e.target.value)} placeholder="Sector or product (optional), e.g. Construction" className={input} aria-label="Segment" />}
              <Button size="sm" onClick={source === "borrower" ? pickBorrower : pickEws} data-testid="pick-confirm">Attach</Button>
            </div>
          ) : null}
          {source === "page" ? (
            <div className="space-y-2">
              <select value={ptype} onChange={(e) => setPtype(e.target.value as ObjectType)} className={input} aria-label="Kind of object" data-testid="pick-page-type">
                {(["cockpit-thread", "attention-item", "whatif-thread", "whatif-scenario", "report", "analysis", "investigation", "project",
                   "scorecard-validation", "early-warning-list", "borrower", "document"] as ObjectType[]).map((t) => <option key={t} value={t}>{OBJECT_LABEL[t]}</option>)}
              </select>
              <input value={path} onChange={(e) => setPath(e.target.value)} placeholder={edition() === "dealdesk" ? "Address from the browser, e.g. /deal-desk/review" : "Address from the browser, e.g. /what-if?thread=…"} className={input} aria-label="Address" data-testid="pick-page-path" />
              <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Name shown in the message" className={input} aria-label="Name" data-testid="pick-page-label" />
              <Button size="sm" onClick={pickPage} data-testid="pick-confirm">Attach</Button>
            </div>
          ) : null}
          {error ? <p role="alert" className="mt-2 text-sm text-negative" data-testid="pick-error">{error}</p> : null}
        </div>
      </div>
    </div>
  );
}

const AUTOSAVE_MS = 2500;

function hhmm(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

/**
 * Compose, reply, reply all or forward. `variant="modal"` floats over the page, `inline` sits under a thread.
 * Drafts save themselves a few seconds after each change ("Saved" shows when), on Save draft, and on Close.
 * Discard deletes the draft. Saves never overlap, and Send waits for the one in flight, so a draft never outlives
 * the message it became.
 */
export function Compose({ init, variant = "modal", onClose, onSent }: {
  init: ComposeInit; variant?: "modal" | "inline"; onClose: () => void; onSent: (threadId: string) => void;
}) {
  const { effective, viewingAs } = useCoreAuth();
  const [to, setTo] = React.useState(init.to);
  const [cc, setCc] = React.useState(init.cc);
  const [bcc, setBcc] = React.useState(init.bcc ?? []);
  const [showCc, setShowCc] = React.useState(init.cc.length > 0);
  const [showBcc, setShowBcc] = React.useState((init.bcc ?? []).length > 0);
  const [subject, setSubject] = React.useState(init.subject);
  const [body, setBody] = React.useState(init.body_html);
  const [atts, setAtts] = React.useState<OutAttachment[]>(init.attachments);
  const [fileInfo, setFileInfo] = React.useState<Record<string, { name: string; size: number }>>(init.files ?? {});
  const [busy, setBusy] = React.useState<"" | "send" | "upload" | "discard">("");
  const [save, setSave] = React.useState<{ state: "idle" | "pending" | "saving" | "saved" | "error"; at?: string; error?: string }>(
    init.draft_id ? { state: "saved", at: init.saved_at } : { state: "idle" });
  const [error, setError] = React.useState<string | null>(null);
  const [picker, setPicker] = React.useState(false);
  const [showQuote, setShowQuote] = React.useState(false);
  const quote = init.quote_html ?? "";
  const fileRef = React.useRef<HTMLInputElement>(null);
  const draftId = React.useRef<string | null>(init.draft_id ?? null);
  const version = React.useRef(0);       // the newest edit number (mirrors `edits`)
  const savedVersion = React.useRef(0);  // the edit the last save carried
  const chain = React.useRef<Promise<void>>(Promise.resolve());
  const done = React.useRef(false);      // sent or discarded: no more saves

  const payload = React.useCallback(() => ({
    to, cc, bcc, subject, body_html: body + quote, attachments: atts, mode: init.mode, thread_id: init.thread_id ?? null, in_reply_to: init.in_reply_to ?? null,
  }), [to, cc, bcc, subject, body, quote, atts, init.mode, init.thread_id, init.in_reply_to]);
  const latest = React.useRef(payload);
  const [edits, setEdits] = React.useState(0);
  React.useEffect(() => { latest.current = payload; version.current = edits; }, [payload, edits]);

  const hasContent = !!(to.length || cc.length || bcc.length || subject.trim() || body.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim() || atts.length);
  const touch = () => setEdits((n) => n + 1);
  const edit = <T,>(setter: (v: T) => void) => (v: T) => { touch(); setter(v); };

  /** Save the newest content once any save in flight has finished. */
  const saveNow = React.useCallback((): Promise<void> => {
    const run = async () => {
      if (done.current || viewingAs || savedVersion.current === version.current) return;
      const v = version.current;
      setSave({ state: "saving" });
      try {
        const d = await core.saveDraft(latest.current() as Omit<Draft, "draft_id">, draftId.current ?? undefined);
        draftId.current = d.draft_id;
        savedVersion.current = v;
        // an edit made while this save was in flight is not in it: say so until the next save
        setSave(version.current === v ? { state: "saved", at: d.updated_at } : { state: "pending" });
        mailChanged();
      } catch (e) {
        setSave({ state: "error", error: friendlyMessage(e) });
      }
    };
    chain.current = chain.current.then(run, run);
    return chain.current;
  }, [viewingAs]);

  // Auto-save: a few seconds after the last change, while there is something worth keeping.
  React.useEffect(() => {
    if (!edits || !hasContent || viewingAs || done.current || edits === savedVersion.current) return;
    setSave((s) => (s.state === "saving" ? s : { ...s, state: "pending" }));
    const t = window.setTimeout(() => { void saveNow(); }, AUTOSAVE_MS);
    return () => window.clearTimeout(t);
  }, [edits, hasContent, viewingAs, saveNow]);

  async function send() {
    if (busy) return;
    setError(null);
    setBusy("send");
    try {
      await chain.current;  // a save in flight has its draft id before we send
      done.current = true;
      const r = await core.send({ ...latest.current(), draft_id: draftId.current }, `send-${draftId.current ?? Date.now()}-${subject.length}-${body.length}`);
      mailChanged();
      onSent(r.thread_id);
    } catch (e) {
      done.current = false;
      setError(friendlyMessage(e));
      setBusy("");
    }
  }

  async function close() {
    if (hasContent && !viewingAs) await saveNow();
    onClose();
  }

  async function discard() {
    setBusy("discard");
    await chain.current;
    done.current = true;
    if (draftId.current && !viewingAs) {
      try { await core.deleteDraft(draftId.current); } catch { /* already gone */ }
      mailChanged();
    }
    onClose();
  }

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy("upload");
    setError(null);
    try {
      for (const f of Array.from(files)) {
        const up = await core.upload(f);
        setFileInfo((m) => ({ ...m, [up.file_id]: { name: up.name, size: up.size } }));
        touch();
        setAtts((a) => [...a, { kind: "file", file_id: up.file_id }]);
      }
    } catch (e) { setError(friendlyMessage(e)); }
    finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  }

  const chips = toChips(atts, fileInfo);
  const heading = init.mode === "new" ? "New message" : init.mode === "forward" ? "Forward" : init.mode === "reply_all" ? "Reply all" : "Reply";
  const saveText = save.state === "saving" ? "Saving…" : save.state === "saved" ? `Saved${save.at ? ` ${hhmm(save.at)}` : ""}`
    : save.state === "pending" ? "Draft not yet saved" : save.state === "error" ? `Not saved: ${save.error}` : "";
  const form = (
    <div className="flex flex-col gap-2" data-testid="compose" data-mode={init.mode}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1"><UserPicker label="To" value={to} onChange={edit(setTo)} testId="compose-to" exclude={[...cc, ...bcc]} /></div>
        <div className="flex shrink-0 gap-2 pt-2 text-xs">
          {!showCc ? <button type="button" onClick={() => setShowCc(true)} className="text-accent hover:underline" data-testid="compose-add-cc">Add Cc</button> : null}
          {!showBcc ? <button type="button" onClick={() => setShowBcc(true)} className="text-accent hover:underline" data-testid="compose-add-bcc">Add Bcc</button> : null}
        </div>
      </div>
      {showCc ? <UserPicker label="Cc" value={cc} onChange={edit(setCc)} testId="compose-cc" exclude={[...to, ...bcc]} /> : null}
      {showBcc ? (
        <div>
          <UserPicker label="Bcc" value={bcc} onChange={edit(setBcc)} testId="compose-bcc" exclude={[...to, ...cc]} />
          <p className="pl-10 pt-0.5 text-[11px] text-text-muted">Bcc recipients get the message; nobody else sees that they did.</p>
        </div>
      ) : null}
      {init.mode === "reply" || init.mode === "reply_all" ? null : (
        <input value={subject} onChange={(e) => edit(setSubject)(e.target.value)} placeholder="Subject" aria-label="Subject" maxLength={300} data-testid="compose-subject"
               className="h-9 rounded-md border border-border bg-surface px-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
      )}
      <Editor html={body} onChange={edit(setBody)} />
      {quote ? (
        <div>
          <button type="button" onClick={() => setShowQuote((v) => !v)} aria-expanded={showQuote} data-testid="compose-quoted-toggle"
                  className="rounded border border-border px-1.5 py-0.5 text-[11px] text-text-muted hover:bg-surface-hover hover:text-text-primary">
            {showQuote ? "Hide quoted text" : "Show quoted text"}
          </button>
          {showQuote ? (
            <div className="mt-1 max-h-48 overflow-y-auto rounded-md border border-dashed border-border px-3 py-2 text-xs text-text-secondary [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3"
                 data-testid="compose-quoted" dangerouslySetInnerHTML={{ __html: quote }} />
          ) : null}
        </div>
      ) : null}
      {chips.length > 0 ? (
        <div className="flex flex-wrap gap-2" data-testid="compose-attachments">
          {chips.map((c) => (
            <AttachmentCard key={c.key} att={c.view} onRemove={() => { touch(); setAtts((a) => a.filter((x) => x !== c.att)); }} />
          ))}
        </div>
      ) : null}
      {viewingAs ? <p role="alert" className="text-sm text-warning">You are viewing as {viewingAs.name}. Stop viewing as to send mail.</p> : null}
      {error ? <p role="alert" className="text-sm text-negative" data-testid="compose-error">{error}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void send()} disabled={!to.length || !!busy || !!viewingAs} data-testid="compose-send">
          {busy === "send" ? <Loader2 className="animate-spin" aria-hidden /> : <SendIcon aria-hidden />} Send
        </Button>
        <input ref={fileRef} type="file" multiple hidden onChange={(e) => void onFiles(e.target.files)} data-testid="compose-file-input" />
        <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()} disabled={!!busy || !!viewingAs} data-testid="compose-attach-file">
          {busy === "upload" ? <Loader2 className="animate-spin" aria-hidden /> : <Paperclip aria-hidden />} Attach file
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setPicker(true)} disabled={!!viewingAs} data-testid="compose-attach-object"><Boxes aria-hidden /> Attach CreditProbe object</Button>
        <span className="flex-1" />
        <span className={cn("text-xs", save.state === "error" ? "text-negative" : "text-text-muted")} data-testid="compose-autosave" data-state={save.state} aria-live="polite">{saveText}</span>
        <Button variant="ghost" size="sm" onClick={() => void saveNow()} disabled={!!busy || !!viewingAs || !hasContent} data-testid="compose-save-draft">Save draft</Button>
        <Button variant="ghost" size="sm" onClick={() => void discard()} disabled={busy === "send"} data-testid="compose-discard"><Trash2 aria-hidden /> Discard</Button>
        <Button variant="ghost" size="sm" onClick={() => void close()} disabled={busy === "send"} data-testid="compose-close">Close</Button>
      </div>
      {picker ? <ObjectPicker onClose={() => setPicker(false)} onPick={(o) => { touch(); setAtts((a) => [...a, { kind: "object", object: o }]); setPicker(false); }} /> : null}
    </div>
  );

  if (variant === "inline") {
    return (
      <section className="rounded-lg border border-border bg-surface p-3" aria-label={heading} data-testid="compose-inline">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{heading}{effective ? ` · from ${effective.name}` : ""}</p>
        {form}
      </section>
    );
  }
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/30 p-4 sm:items-center" role="presentation">
      <div role="dialog" aria-label={heading} data-testid="compose-dialog" className="max-h-[92vh] w-full max-w-[760px] overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-text-primary">{heading}</h2>
          <button type="button" onClick={() => void close()} aria-label="Close" data-testid="compose-x" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        {form}
      </div>
    </div>
  );
}
