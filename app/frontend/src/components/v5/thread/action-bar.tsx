"use client";

/**
 * R16 t (M7): the one thread action bar on every answer in every module.
 *
 *   Share          copy the link, or send it in CreditProbe Mail (optionally with the Word memo attached)
 *   Trace          sources, queries, Data Domains relations and rows behind the answer (a side panel)
 *   Word           the house-style memo of this answer or of the whole thread (downloads the .docx)
 *   Add to report  the answer as a Playbook section
 *
 * A module wires it in three lines:
 *
 *   const ta = useThreadActions({ module: "whatif", threadId, title, href, busy });
 *   <ThreadActionsProvider value={ta}> … <AssistantTurn actions={{ index, question, answerId, sources }}> … </ThreadActionsProvider>
 *   in ask(q): if (ta.intercept(q, ask)) return;      // "write a memo" -> a Word document, never prose
 *   <MemoCards api={ta} /> after the turns
 *
 * Outside a thread (Cockpit answers, intel panels, Borrower 360, agent runs) `<ThreadActionBar getDoc={…} />` stands alone.
 * The answer's blocks are read from what the reader sees (lib/v5/thread-actions.ts → domBlocks); its sources come
 * from the module's own answer object. Every panel opens with the plain-words block.
 */

import * as React from "react";
import Link from "next/link";
import { Check, ChevronDown, Copy, Download, FileText, Loader2, Route, Share2, X } from "lucide-react";

import { AddToReportButton } from "@/components/v5/playbook/add-to-report";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import type { Block as PlaybookBlock, PlaybookSource } from "@/lib/v5/playbook";
import {
  type ActionDoc, type ActionSource, type MemoResult, type ModuleKey, MODULE_LABEL, answerDoc, composeDoc, domBlocks, memoPlainWords,
  planMemo, shareObject, sharePlainWords, toPlaybookBlocks, traceSources,
} from "@/lib/v5/thread-actions";
import type { TraceSnapshot } from "@/lib/v5/thread";
import { type TraceResult, coreOrigin, threadActions } from "@/lib/v5/thread-actions-client";
import { takePendingMemo } from "@/lib/v5/thread-actions-pending";

import { ListenButton } from "./listen";

// ------------------------------------------------------------------ the thread registry and the memo intent

interface Entry { index: number; question: string; answerId: string; sources: ActionSource[]; el: HTMLElement | null }
export interface MemoCardState { id: string; request: string; state: "working" | "done" | "error" | "empty" | "asking"; result?: MemoResult; message?: string }

export interface ThreadActionsApi {
  module: ModuleKey; threadId: string; title: string; href: string;
  register: (key: string, e: Entry) => () => void;
  threadDoc: () => ActionDoc;
  answers: () => number;
  /** A "write a memo / note / paper" request: handled (true) or not a request (false). `ask` asks a question first. */
  intercept: (text: string, ask?: (question: string) => unknown, opts?: { writeOnly?: boolean }) => boolean;
  cards: MemoCardState[];
}

const Ctx = React.createContext<ThreadActionsApi | null>(null);
export const ThreadActionsProvider = ({ value, children }: { value: ThreadActionsApi; children: React.ReactNode }) =>
  <Ctx.Provider value={value}>{children}</Ctx.Provider>;
export const useThreadActionsContext = () => React.useContext(Ctx);

function here(): string {
  if (typeof window === "undefined") return "/";
  return `${window.location.pathname}${window.location.search}`;
}

function docOf(module: ModuleKey, threadId: string, title: string, href: string, entries: Entry[]): ActionDoc {
  return composeDoc(module, threadId, title, href || here(), [...entries].sort((a, b) => a.index - b.index).map((e) => ({
    question: e.question, answer_id: e.answerId, blocks: domBlocks(e.el as unknown as Parameters<typeof domBlocks>[0]), sources: e.sources,
  })).filter((t) => t.blocks.length));
}

export function useThreadActions({ module, threadId, title, href = "", busy = false }: {
  module: ModuleKey; threadId: string; title: string; href?: string; busy?: boolean;
}): ThreadActionsApi {
  const reg = React.useRef(new Map<string, Entry>());
  const [tick, setTick] = React.useState(0);
  const [cards, setCards] = React.useState<MemoCardState[]>([]);
  const pending = React.useRef<{ cardId: string; baseline: number; plan: ReturnType<typeof planMemo>; text: string; at: number } | null>(null);
  const storeKey = `ta.memo.${module}.${threadId}`;

  React.useEffect(() => {
    let live = true;
    void Promise.resolve().then(() => {
      if (!live) return;
      let kept: MemoCardState[] = [];
      try {
        const raw = window.sessionStorage.getItem(storeKey);
        kept = raw ? (JSON.parse(raw) as MemoCardState[]).filter((c) => c.state === "done") : [];
      } catch { kept = []; }
      // a memo asked for with its question on a landing or in Noor: write it once this thread's answer is on screen
      const req = threadId && threadId !== "new" ? takePendingMemo(module, threadId) : null;
      const plan = req ? planMemo(req, 1) : null;
      if (req && plan && plan.action !== "none" && plan.action !== "empty") {
        const id = `m${Date.now().toString(36)}`;
        pending.current = { cardId: id, baseline: 0, plan: { action: "write", intent: plan.intent }, text: req, at: Date.now() };
        kept = [...kept, { id, request: req, state: "asking", message: `Writing the ${plan.intent.kind} once the answer is ready.` }];
      }
      setCards(kept);
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeKey]);
  const save = React.useCallback((next: MemoCardState[]) => {
    try { window.sessionStorage.setItem(storeKey, JSON.stringify(next.filter((c) => c.state === "done").slice(-12))); } catch { /* private window */ }
  }, [storeKey]);
  const update = React.useCallback((id: string, patch: Partial<MemoCardState>) => {
    setCards((cs) => { const next = cs.map((c) => (c.id === id ? { ...c, ...patch } : c)); save(next); return next; });
  }, [save]);

  const threadDoc = React.useCallback(() => docOf(module, threadId, title, href, [...reg.current.values()]), [module, threadId, title, href]);

  const write = React.useCallback(async (cardId: string, plan: ReturnType<typeof planMemo>, text: string) => {
    if (plan.action === "none" || plan.action === "empty") return;
    const doc = threadDoc();
    if (!doc.turns.length) { update(cardId, { state: "empty", message: "There is no answer in this thread to write up yet. Ask your question first." }); return; }
    const scope = plan.intent.scope;
    try {
      const r = await threadActions.memo(scope === "answer" ? answerDoc(doc, doc.turns.length - 1) : doc,
                                         { kind: plan.intent.kind, scope: "thread", to: plan.intent.to, trigger: "memo_intent", request_text: text });
      update(cardId, { state: "done", result: r });
    } catch (e) {
      update(cardId, { state: "error", message: e instanceof Error ? e.message : "The memo could not be written." });
    }
  }, [threadDoc, update]);

  const intercept = React.useCallback((text: string, ask?: (q: string) => unknown, opts?: { writeOnly?: boolean }) => {
    const plan = planMemo(text, [...reg.current.values()].filter((e) => e.el).length);
    if (plan.action === "none") return false;
    // a module that writes documents itself (Playbook) keeps "draft a paper on X"; only "write a memo of this" is ours
    if (opts?.writeOnly && plan.action !== "write") return false;
    const id = `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    if (plan.action === "empty") {
      setCards((cs) => [...cs, { id, request: text, state: "empty", message: plan.message }]);
      return true;
    }
    if (plan.action === "ask-then-write" && ask) {
      setCards((cs) => [...cs, { id, request: text, state: "asking", message: `Answering “${plan.question}” first, then writing the ${plan.intent.kind}.` }]);
      pending.current = { cardId: id, baseline: reg.current.size, plan, text, at: Date.now() };
      void Promise.resolve(ask(plan.question)).catch(() => update(id, { state: "error", message: "The question could not be answered, so the memo was not written." }));
      return true;
    }
    setCards((cs) => [...cs, { id, request: text, state: "working" }]);
    void write(id, plan, text);
    return true;
  }, [update, write]);

  // ask-then-write: write once the new answer is on screen and the module is no longer busy
  React.useEffect(() => {
    const p = pending.current;
    if (!p) return;
    if (Date.now() - p.at > 180_000) { pending.current = null; update(p.cardId, { state: "error", message: "The answer did not finish, so the memo was not written. Ask again." }); return; }
    if (busy || reg.current.size <= p.baseline) return;
    const t = window.setTimeout(() => {
      if (pending.current !== p) return;
      pending.current = null;
      update(p.cardId, { state: "working", message: undefined });
      void write(p.cardId, p.plan, p.text);
    }, 900);
    return () => window.clearTimeout(t);
  }, [tick, busy, update, write]);

  const register = React.useCallback((key: string, e: Entry) => {
    reg.current.set(key, e);
    setTick((x) => x + 1);
    return () => { if (reg.current.get(key) === e) reg.current.delete(key); };
  }, []);

  return React.useMemo(() => ({
    module, threadId, title, href, register, threadDoc, answers: () => reg.current.size, intercept, cards,
  }), [module, threadId, title, href, register, threadDoc, intercept, cards]);
}

// ------------------------------------------------------------------ the bar inside AssistantTurn

export interface TurnActionsProps { index: number; question: string; answerId?: string; sources?: ActionSource[];
  /** The process trace drawn above the answer (AssistantTurn passes its own). */
  trace?: TraceSnapshot | null }

/** Registers the answer with its thread and draws the bar under it (AssistantTurn renders this when given `actions`). */
export function TurnActions({ index, question, answerId = "", sources: own = [], trace, bodyRef, compact }: TurnActionsProps & {
  bodyRef: React.RefObject<HTMLElement | null>; compact?: boolean;
}) {
  const api = useThreadActionsContext();
  const sources = React.useMemo(() => [...own, ...traceSources(trace)], [own, trace]);
  const key = `${index}:${answerId}`;
  const srcKey = JSON.stringify(sources);
  React.useEffect(() => {
    if (!api) return;
    return api.register(key, { index, question, answerId: answerId || `a${index + 1}`, sources, el: bodyRef.current });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api?.register, key, question, srcKey]);
  const getDoc = React.useCallback((): ActionDoc => {
    const one = composeDoc(api?.module ?? "agents", api?.threadId ?? "", question || api?.title || "", api?.href || here(), [{
      question, answer_id: answerId || `a${index + 1}`, blocks: domBlocks(bodyRef.current as unknown as Parameters<typeof domBlocks>[0]), sources }]);
    return one;
  }, [api, question, answerId, index, sources, bodyRef]);
  if (!api) return null;
  return <ThreadActionBar module={api.module} threadId={api.threadId} answerId={answerId || `a${index + 1}`} getDoc={getDoc}
                          getThreadDoc={api.threadDoc} answers={api.answers} compact={compact} question={question} getEl={() => bodyRef.current} />;
}

// ------------------------------------------------------------------ the bar

const btn = "inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11.5px] text-text-secondary hover:bg-surface-hover hover:text-text-primary disabled:opacity-40";

export function ThreadActionBar({ module, threadId, answerId = "", getDoc, getThreadDoc, answers, compact, className, testId = "thread-actions", share = true, report = true, question, getEl, nearby }: {
  module: ModuleKey; threadId: string; answerId?: string;
  /** R16 n: the question this answers, and the answer element Listen narrates (default: the element the bar sits in). */
  question?: string; getEl?: () => Element | null; nearby?: boolean;
  /** This answer as a document (blocks as shown, sources from the module). */
  getDoc: () => ActionDoc;
  /** The whole thread; omitted where there is only one answer (a panel). */
  getThreadDoc?: () => ActionDoc;
  answers?: () => number;
  compact?: boolean; className?: string; testId?: string;
  /** false where the module's own row already shares the answer (Cockpit's Share in Mail). */
  share?: boolean;
  /** false where the module's own row already adds it to a report (Early Warning, Borrower 360 headers). */
  report?: boolean;
}) {
  const [panel, setPanel] = React.useState<null | "share" | "trace">(null);
  const [wordMenu, setWordMenu] = React.useState(false);
  const [writing, setWriting] = React.useState(false);
  const [memo, setMemo] = React.useState<MemoResult | null>(null);
  const [err, setErr] = React.useState("");
  const [shareScope, setShareScope] = React.useState<"answer" | "thread">("answer");
  const many = (answers?.() ?? 1) > 1 && !!getThreadDoc;
  const barRef = React.useRef<HTMLDivElement | null>(null);
  const answerEl = React.useCallback(() => getEl?.() ?? barRef.current?.parentElement ?? null, [getEl]);

  const word = async (scope: "answer" | "thread") => {
    setWordMenu(false); setWriting(true); setErr("");
    try {
      const doc = scope === "thread" && getThreadDoc ? getThreadDoc() : getDoc();
      const r = await threadActions.memo(doc, { scope: "thread", trigger: "word_button" });
      setMemo(r);
      await threadActions.download(r);
    } catch (e) { setErr(e instanceof Error ? e.message : "The Word memo could not be written."); }
    finally { setWriting(false); }
  };
  const doc0 = React.useMemo(() => ({ module, thread_id: threadId, title: MODULE_LABEL[module], href: here(), turns: [] }) as ActionDoc, [module, threadId]);
  const source: PlaybookSource = { type: "thread-answer", id: `${module}:${threadId || "view"}${answerId ? `:${answerId}` : ""}`.slice(0, 120),
                                   label: `${MODULE_LABEL[module]} answer`, href: doc0.href.slice(0, 480) };

  return (
    <div ref={barRef} className={cn("flex flex-wrap items-center gap-0.5 border-t border-border/60 pt-1.5", className)} data-testid={testId} data-thread-actions="" data-module={module}>
      <ListenButton module={module} question={question ?? ""} getEl={answerEl} compact={compact} testId={testId} nearby={nearby} />
      {share ? (
        <button type="button" className={btn} onClick={() => { setShareScope("answer"); setPanel("share"); }} data-testid={`${testId}-share`} title="Share this answer">
          <Share2 size={12} aria-hidden />{compact ? null : " Share"}</button>) : null}
      <button type="button" className={btn} onClick={() => setPanel("trace")} data-testid={`${testId}-trace`} title="Where this answer came from">
        <Route size={12} aria-hidden />{compact ? null : " Trace"}</button>
      <div className="relative">
        <button type="button" className={btn} disabled={writing} data-testid={`${testId}-word`} title="Word memo"
                onClick={() => (many ? setWordMenu((x) => !x) : void word("answer"))}>
          {writing ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <FileText size={12} aria-hidden />}
          {compact ? null : " Word"}{many ? <ChevronDown size={11} aria-hidden /> : null}</button>
        {wordMenu ? (
          <div className="absolute left-0 top-8 z-30 w-56 rounded-md border border-border bg-surface p-1 shadow-lg" role="menu" data-testid={`${testId}-word-menu`}>
            <button type="button" role="menuitem" className="block w-full rounded px-2 py-1.5 text-left text-[12px] hover:bg-surface-hover" onClick={() => void word("answer")}
                    data-testid={`${testId}-word-answer`}>Memo of this answer</button>
            <button type="button" role="menuitem" className="block w-full rounded px-2 py-1.5 text-left text-[12px] hover:bg-surface-hover" onClick={() => void word("thread")}
                    data-testid={`${testId}-word-thread`}>Memo of the whole thread ({answers?.() ?? 1} answers)</button>
          </div>) : null}
      </div>
      {report ? <AddToReportButton source={source} variant="ghost" size="sm" label={compact ? "" : "Add to report"} testId={`${testId}-report`}
                         className="h-7 px-2 text-[11.5px] text-text-secondary"
                         build={() => { const d = getDoc(); return { title: d.title.slice(0, 200), blocks: toPlaybookBlocks(d) as unknown as PlaybookBlock[],
                                                                      source: { ...source, label: `${MODULE_LABEL[module]}: ${d.title}`.slice(0, 200), href: (d.href || source.href).slice(0, 480) } }; }}
                         onDone={(r) => void threadActions.action(module, threadId, "report", r.report_id ?? "", answerId)} /> : null}
      {memo ? (
        <button type="button" className={cn(btn, "text-accent")} onClick={() => void threadActions.download(memo).catch((e: Error) => setErr(e.message))}
                data-testid={`${testId}-word-again`} title={memo.file_name}><Download size={12} aria-hidden /> {compact ? "" : "Download again"}</button>) : null}
      {err ? <span className="ml-1 text-[11px] text-negative" role="alert">{err}</span> : null}
      {panel === "share" ? (
        <ShareDialog getDoc={() => (shareScope === "thread" && getThreadDoc ? getThreadDoc() : getDoc())} scope={shareScope} answerId={answerId}
                     canThread={many} onScope={setShareScope} memo={null} onClose={() => setPanel(null)} />) : null}
      {panel === "trace" ? <TracePanel getDoc={getDoc} getThreadDoc={many ? getThreadDoc : undefined} onClose={() => setPanel(null)} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ Share

interface User { username: string; name: string; title: string; initials: string }

async function core<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try { r = await fetch(`${coreOrigin()}${path}`, { credentials: "include", cache: "no-store", ...init }); }
  catch { throw new Error("Mail is temporarily unavailable. Please try again in a moment."); }
  const body = await r.json().catch(() => null) as { detail?: unknown } | null;
  if (!r.ok) throw new Error(r.status === 401 ? "Sign in to share." : typeof body?.detail === "string" ? body.detail : "The message could not be sent.");
  return body as T;
}

export function ShareDialog({ getDoc, scope, answerId = "", canThread = false, onScope, memo, onClose }: {
  getDoc: () => ActionDoc; scope: "answer" | "thread"; answerId?: string; canThread?: boolean; onScope?: (s: "answer" | "thread") => void;
  memo: MemoResult | null; onClose: () => void;
}) {
  const [users, setUsers] = React.useState<User[] | null>(null);
  const [me, setMe] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [attach, setAttach] = React.useState(!!memo);
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const [error, setError] = React.useState("");
  const [key] = React.useState(() => `ta-${Math.random().toString(36).slice(2, 12)}`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const doc = React.useMemo(() => getDoc(), [getDoc, scope]);
  const object = shareObject(doc, scope, answerId);

  React.useEffect(() => {
    let live = true;
    Promise.all([core<{ users: User[] }>("/api/v1/users"), core<{ effective_user: User }>("/api/v1/auth/me").catch(() => null)])
      .then(([u, m]) => { if (live) { setUsers(u.users); setMe(m?.effective_user?.username ?? ""); } })
      .catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : "Mail is unavailable."); });
    return () => { live = false; };
  }, []);

  const copy = async () => {
    try { await navigator.clipboard.writeText(`${window.location.origin}${object.href}`); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { setError("The link could not be copied; it is " + object.href); }
  };
  const send = async () => {
    if (!picked.length) return;
    setSending(true); setError("");
    try {
      if (attach) {
        const m = memo ?? await threadActions.memo(doc, { scope: "thread", trigger: "word_button" });
        const form = new FormData();
        form.append("file", await threadActions.blob(m), m.file_name);
        const file = await core<{ file_id: string }>("/api/v1/mail/files", { method: "POST", body: form });
        await core("/api/v1/mail/send", {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
          body: JSON.stringify({ to: picked, cc: [], subject: object.label.slice(0, 200), mode: "new",
                                 body_html: `<p>${(note || "The answer from CreditProbe, with its Word memo.").replace(/</g, "&lt;")}</p>`,
                                 attachments: [{ kind: "object", object }, { kind: "file", file_id: file.file_id }] }),
        });
      } else {
        await core("/api/v1/mail/share", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
                                           body: JSON.stringify({ to: picked, cc: [], note, objects: [object] }) });
      }
      void threadActions.action(doc.module, doc.thread_id, "share", `${picked.length} recipient${picked.length === 1 ? "" : "s"}`, scope === "answer" ? answerId : "");
      setDone(`Shared with ${(users ?? []).filter((u) => picked.includes(u.username)).map((u) => u.name).join(", ")}.`);
    } catch (e) { setError(e instanceof Error ? e.message : "The message could not be sent."); }
    finally { setSending(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Share" data-testid="thread-share-dialog">
      <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-surface p-5 shadow-lg">
        <div className="flex items-center justify-between gap-2">
          <h2 className="truncate text-[14px] font-semibold text-text-primary">Share: {doc.title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="thread-share-close"><X size={16} /></button>
        </div>
        <PlainWords lines={sharePlainWords(doc, scope)} gloss={false} testId="thread-share-plain-words" />
        {canThread && onScope ? (
          <div className="flex gap-1 text-[12px]" role="radiogroup" aria-label="What to share">
            {(["answer", "thread"] as const).map((s) => (
              <button key={s} type="button" role="radio" aria-checked={scope === s} onClick={() => onScope(s)} data-testid={`thread-share-scope-${s}`}
                      className={cn("rounded-md border px-2 py-1", scope === s ? "border-accent bg-accent-muted text-text-primary" : "border-border text-text-secondary")}>
                {s === "answer" ? "This answer" : "Whole thread"}</button>))}
          </div>) : null}
        {done ? (
          <div className="space-y-2" data-testid="thread-share-done">
            <p className="text-[13px] text-positive">{done}</p>
            <Link className="text-[12px] text-accent underline" href="/messages">Open CreditProbe Mail</Link>
          </div>
        ) : (
          <>
            {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
            <button type="button" onClick={() => void copy()} data-testid="thread-share-copy"
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[12px] text-text-secondary hover:bg-surface-hover">
              {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />} {copied ? "Link copied" : "Copy link"}</button>
            {users ? (
              <div className="max-h-48 space-y-1 overflow-auto" data-testid="thread-share-users">
                {users.filter((u) => u.username !== me).map((u) => (
                  <label key={u.username} className="flex items-center gap-2 text-[12px]">
                    <input type="checkbox" checked={picked.includes(u.username)} data-testid={`thread-share-user-${u.username}`}
                           onChange={(e) => setPicked((x) => (e.target.checked ? [...x, u.username] : x.filter((y) => y !== u.username)))} />
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent-muted text-[9px] font-semibold">{u.initials}</span>
                    <span className="text-text-primary">{u.name}</span><span className="text-text-muted">· {u.title}</span>
                  </label>))}
              </div>) : error ? null : <div className="h-20 animate-pulse rounded-md bg-surface-hover" />}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note" rows={2} data-testid="thread-share-note"
                      className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]" />
            <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)}
                   data-testid="thread-share-attach" /> Attach the Word memo</label>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-[12px]">Cancel</button>
              <button type="button" onClick={() => void send()} disabled={!picked.length || sending} data-testid="thread-share-send"
                      className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">{sending ? "Sending…" : "Send"}</button>
            </div>
          </>)}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Trace

export function TracePanel({ getDoc, getThreadDoc, onClose }: { getDoc: () => ActionDoc; getThreadDoc?: () => ActionDoc; onClose: () => void }) {
  const [scope, setScope] = React.useState<"answer" | "thread">("answer");
  const [t, setT] = React.useState<TraceResult | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void Promise.resolve().then(() => {
      if (!live) return;
      setT(null); setError("");
      const doc = scope === "thread" && getThreadDoc ? getThreadDoc() : getDoc();
      return threadActions.trace(doc).then((r) => { if (live) setT(r); }).catch((e: Error) => { if (live) setError(e.message); });
    });
    return () => { live = false; };
  }, [scope, getDoc, getThreadDoc]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20" role="dialog" aria-modal="true" aria-label="Trace" data-testid="thread-trace-panel" onClick={onClose}>
      <aside className="h-full w-full max-w-[480px] space-y-4 overflow-auto border-l border-border bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">Trace</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="thread-trace-close"><X size={16} /></button>
        </div>
        {getThreadDoc ? (
          <div className="flex gap-1 text-[12px]">
            {(["answer", "thread"] as const).map((s) => (
              <button key={s} type="button" onClick={() => setScope(s)} data-testid={`thread-trace-scope-${s}`}
                      className={cn("rounded-md border px-2 py-1", scope === s ? "border-accent bg-accent-muted text-text-primary" : "border-border text-text-secondary")}>
                {s === "answer" ? "This answer" : "Whole thread"}</button>))}
          </div>) : null}
        <PlainWords lines={t?.plain_words ?? []} loading={!t && !error} gloss={false} testId="thread-trace-plain-words" />
        {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        {t ? (
          <>
            <Section title={`Data Domains relations (${t.relations.length})`} testId="thread-trace-relations">
              {t.relations.length ? (
                <table className="w-full text-[11.5px]"><tbody>
                  {t.relations.map((r) => (
                    <tr key={r.relation} className="border-b border-border/60 align-top">
                      <td className="py-1 pr-2 font-mono text-[11px] text-text-primary">{r.relation}</td>
                      <td className="py-1 pr-2 text-text-secondary">{r.label}{r.domain ? <span className="text-text-muted"> · {r.domain}</span> : null}</td>
                      <td className="py-1 text-right">{r.registered
                        ? <span className="rounded bg-positive/10 px-1.5 py-0.5 text-[10px] text-positive">registered</span>
                        : <span className="rounded bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">not registered</span>}</td>
                    </tr>))}
                </tbody></table>) : <p className="text-[12px] text-text-muted">No relation was named by this answer.</p>}
            </Section>
            <Section title={`Queries (${t.queries.length})`} testId="thread-trace-queries">
              {t.queries.length ? t.queries.map((q, i) => (
                <details key={i} className="rounded-md border border-border px-2 py-1 text-[11.5px]">
                  <summary className="cursor-pointer text-text-primary">{q.label}{q.rows != null ? <span className="text-text-muted"> · {q.rows} rows</span> : null}</summary>
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words bg-surface-hover p-2 font-mono text-[10.5px] text-text-secondary">{q.sql}</pre>
                  {q.relations.length ? <p className="mt-1 text-[11px] text-text-muted">Reads {q.relations.join(", ")}</p> : null}
                </details>)) : <p className="text-[12px] text-text-muted">No query ran for this answer (the module computed it with its engine).</p>}
            </Section>
            <Section title={`Rows (${t.rows.length})`} testId="thread-trace-rows">
              {t.rows.length ? (
                <ul className="space-y-1 text-[11.5px]">
                  {t.rows.slice(0, 40).map((r, i) => (
                    <li key={i} className="text-text-secondary"><span className="font-mono text-[11px] text-text-primary">{r.relation}</span>{" "}
                      {Object.entries(r.keys).map(([k, v]) => `${k}=${v}`).join(", ")}{r.period ? ` · ${r.period}` : ""}</li>))}
                </ul>) : <p className="text-[12px] text-text-muted">No named row.</p>}
            </Section>
            <Section title={`All sources (${t.sources.length})`} testId="thread-trace-sources">
              <ul className="space-y-1 text-[11.5px]">
                {t.sources.map((s, i) => (
                  <li key={i} className="text-text-secondary"><span className="mr-1 rounded bg-surface-hover px-1 text-[10px] uppercase text-text-muted">{s.kind}</span>{s.label}</li>))}
                {!t.sources.length ? <li className="text-text-muted">The figures are as shown on screen.</li> : null}
              </ul>
            </Section>
          </>) : null}
      </aside>
    </div>
  );
}

function Section({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5" data-testid={testId}>
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{title}</h3>
      {children}
    </section>
  );
}

// ------------------------------------------------------------------ memo cards (the answer to "write a memo")

export function MemoCards({ api, compact }: { api: ThreadActionsApi; compact?: boolean }) {
  if (!api.cards.length) return null;
  return <>{api.cards.map((c) => <MemoCard key={c.id} card={c} threadDoc={api.threadDoc} compact={compact} />)}</>;
}

/** One "write a memo" exchange: the request, then the written document (plain words, Download Word, Share). */
export function MemoCard({ card, threadDoc, compact }: { card: MemoCardState; threadDoc: () => ActionDoc; compact?: boolean }) {
  const [share, setShare] = React.useState(false);
  const [err, setErr] = React.useState("");
  const r = card.result;
  return (
    <div className="space-y-2" data-testid="thread-memo" data-state={card.state}>
      <div className="flex justify-end">
        <p className={cn("max-w-3xl whitespace-pre-line rounded-lg bg-accent px-3 py-2 text-accent-contrast", compact ? "text-[12px]" : "text-[13px]")}>{card.request}</p>
      </div>
      <div className="space-y-2 rounded-lg border border-border bg-surface p-3" data-testid="thread-memo-answer">
        {card.state === "done" && r ? (
          <>
            <PlainWords lines={memoPlainWords(r)} gloss={false} testId="thread-memo-plain-words" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 text-[12.5px] text-text-primary"><FileText size={14} className="text-accent" aria-hidden />{r.file_name}</span>
              <span className="text-[11px] text-text-muted">{Math.max(1, Math.round(r.bytes / 1024))} KB · Word</span>
              <button type="button" onClick={() => void threadActions.download(r).catch((e: Error) => setErr(e.message))} data-testid="thread-memo-download"
                      className="ml-auto inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast"><Download size={13} aria-hidden /> Download Word</button>
              <button type="button" onClick={() => setShare(true)} data-testid="thread-memo-share"
                      className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-[12px] text-text-secondary hover:bg-surface-hover"><Share2 size={13} aria-hidden /> Share</button>
            </div>
            {err ? <p className="text-[11px] text-negative" role="alert">{err}</p> : null}
            {share ? <ShareDialog getDoc={threadDoc} scope="thread" memo={r} onClose={() => setShare(false)} /> : null}
          </>
        ) : card.state === "working" || card.state === "asking" ? (
          <p className="inline-flex items-center gap-2 text-[12.5px] text-text-secondary" data-testid="thread-memo-working">
            <Loader2 size={13} className="animate-spin" aria-hidden /> {card.message ?? "Writing the Word document from this thread…"}</p>
        ) : (
          <p className={cn("text-[12.5px]", card.state === "error" ? "text-negative" : "text-text-secondary")} data-testid="thread-memo-message">{card.message}</p>
        )}
      </div>
    </div>
  );
}
