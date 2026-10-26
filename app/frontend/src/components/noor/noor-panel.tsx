"use client";

/**
 * Noor's right side panel (I13.2). It opens from "Ask Noor" in the top bar and stays open while Show me moves between
 * modules. R14 n (K5, K7, K16): it opens on an EMPTY thread scoped to the page; each brief line has its own thread;
 * earlier threads are in the history list (the clock button), reopened on demand. Ask by voice with the mic; every
 * answer has a speaker.
 */

import * as React from "react";

import { edition } from "@/lib/navigation";
import { ArrowUp, History, Plus, Settings2, X } from "lucide-react";

import { cn } from "@/lib/utils";

import { MicButton } from "./mic-button";
import { MODULES, PERSONAS, type NoorThread, type Turn, historyOf } from "./noor-model";
import { NoorSettingsForm } from "./noor-settings";
import { ask, clearThread, loadBrief, openPanel, selectThread, toggleHistory, toggleSettings, useNoor } from "./noor-store";
import { voiceStateLabel } from "./noor-voice";
import { SpeakerButton } from "./speaker-button";
import { TurnView } from "./turns";
import { MemoCards, ThreadActionsProvider, TurnActions, useThreadActions } from "@/components/v5/thread/action-bar";
import { type ActionSource, noorSources } from "@/lib/v5/thread-actions";

/** R16 t (M7): the answers in a Noor thread that carry Share, Trace, Word and Add to report. */
const ANSWER_KINDS = new Set(["brief", "why", "options", "drivers", "committee", "here"]);

function answerMeta(turns: Turn[], i: number): { question: string; sources: ActionSource[] } {
  const t = turns[i];
  let question = "";
  for (let j = i - 1; j >= 0; j -= 1) { const p = turns[j]; if (p.kind === "ask") { question = p.text; break; } if (ANSWER_KINDS.has(p.kind)) break; }
  if (t.kind === "why") return { question: question || `Why: ${t.item.title}`, sources: noorSources(t.answer.trace?.length ? t.answer.trace : t.item.trace) };
  if (t.kind === "options" || t.kind === "drivers" || t.kind === "committee") return { question: question || t.item.title, sources: noorSources(t.item.trace) };
  if (t.kind === "here") return { question: question || t.question, sources: t.answer.deal_id ? [{ kind: "row", label: `Deal ${t.answer.deal_id}`, relation: "dd_deal", domain: "deal_desk", keys: { proposal_id: t.answer.deal_id } }] : [] };
  if (t.kind === "brief") return { question: question || "Today's brief", sources: noorSources(t.brief.items.flatMap((x) => x.trace).slice(0, 30)) };
  return { question, sources: [] };
}

function NoorAnswer({ turn, index, meta }: { turn: Turn; index: number; meta: { question: string; sources: ActionSource[] } }) {
  const body = React.useRef<HTMLDivElement | null>(null);
  return (
    <div className="space-y-1">
      <div ref={body}><TurnView turn={turn} /></div>
      <TurnActions index={index} question={meta.question} answerId={turn.id} sources={meta.sources} bodyRef={body} compact />
    </div>
  );
}

export function NoorPanel() {
  const s = useNoor();
  const [text, setText] = React.useState("");
  const thread = React.useRef<HTMLDivElement | null>(null);
  const target = scrollTarget(s.turns);
  // K5: switching to a thread shows it from its top.
  React.useEffect(() => { thread.current?.scrollTo({ top: 0 }); }, [s.switched]);
  // The newest exchange is brought to the top of the thread: the question, then its answer growing below it.
  React.useEffect(() => {
    if (!target) return;
    const el = thread.current?.querySelector(`[data-turn="${target}"]`);
    el?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [target, s.open]);
  const history = historyOf(s.threads, s.current);
  const ta = useThreadActions({ module: "noor", threadId: s.current ?? "noor", busy: s.busy,
                                title: s.threads.find((x) => x.id === s.current)?.title || "Noor thread" });
  const open = s.threads.find((t) => t.id === s.current);
  React.useEffect(() => {
    if (!s.open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") openPanel(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.open]);
  if (!s.open) return null;
  const persona = PERSONAS.find((p) => p.id === s.persona);
  return (
    <>
    {/* Side by side, not on top: from 1200px the page makes room for the panel, so Show me lands next to it. */}
    <style>{"@media (min-width: 1200px) { main { margin-right: 420px; } }"}</style>
    <aside role="complementary" aria-label={`Ask ${s.settings.name}`} data-testid="noor-panel" data-tour="brief-why-answer"
           className="fixed bottom-0 right-0 top-12 z-40 flex w-[420px] max-w-[100vw] flex-col border-l border-border bg-surface shadow-[-12px_0_32px_-20px_rgba(0,0,0,0.25)]">
      <header className="flex items-center gap-2 border-b border-border px-5 py-3">
        <NoorMark />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold leading-tight text-text-primary" data-testid="noor-name">{s.settings.name}</p>
          <p className="truncate text-[11px] text-text-muted" data-testid="noor-context">
            {open && open.turns.length ? open.title : `${persona?.label ?? s.persona} · on ${s.module.label}`}</p>
        </div>
        <SpeakerButton brief={s.brief} />
        <IconButton label="New thread" onClick={() => clearThread()} testId="noor-new-thread">
          <Plus className="size-4" aria-hidden /></IconButton>
        <IconButton label={`Earlier threads (${history.length})`} onClick={toggleHistory} active={s.historyOpen}
                    testId="noor-history-button">
          <History className="size-4" aria-hidden /></IconButton>
        <IconButton label="Noor's name and voice" onClick={toggleSettings} active={s.settingsOpen}>
          <Settings2 className="size-4" aria-hidden /></IconButton>
        <IconButton label="Close" onClick={() => openPanel(false)}><X className="size-4" aria-hidden /></IconButton>
      </header>
      {s.settingsOpen ? <div className="border-b border-border px-4 py-3"><NoorSettingsForm /></div> : null}
      {s.historyOpen ? <ThreadHistory threads={history} /> : null}
      {s.voice.state === "no-voice" ? (
        <p className="border-b border-border px-4 py-1.5 text-[11.5px] text-text-muted" role="status" data-testid="noor-voice-problem">
          {voiceStateLabel(s.voice.state, s.voice.on, s.voice.language)}</p>
      ) : null}
      <div ref={thread} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5" data-testid="noor-thread">
        {s.turns.length === 0 ? (
          <div className="space-y-1 text-[13px] text-text-muted" data-testid="noor-empty-thread">
            <p>A new thread on {s.module.label}. Ask me anything, or start with today&apos;s brief.</p>
            {history.length ? <p className="text-[12px]">Earlier threads are under the clock button above.</p> : null}
          </div>
        ) : (
          <ThreadActionsProvider value={ta}>
            {s.turns.map((t, i) => (
              <div key={t.id} data-turn={t.id} className="scroll-mt-2">
                {ANSWER_KINDS.has(t.kind) ? <NoorAnswer turn={t} index={i} meta={answerMeta(s.turns, i)} /> : <TurnView turn={t} />}
              </div>))}
            <MemoCards api={ta} compact />
          </ThreadActionsProvider>)}
        <div className="h-[40vh]" aria-hidden />
      </div>
      <footer className="border-t border-border px-4 pb-3 pt-3">
        <form className="flex items-end gap-2 rounded-xl border border-border bg-canvas px-3 py-2 focus-within:border-accent"
              onSubmit={(e) => { e.preventDefault(); if (!ta.intercept(text, undefined, { writeOnly: true })) void ask(text); setText(""); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} dir="auto"
                 placeholder="Ask me anything, from ECL decomposition to early warning…"
                 aria-label={`Ask ${s.settings.name}`} data-testid="noor-input" style={{ outline: "none" }}
                 className="h-7 min-w-0 flex-1 bg-transparent font-user text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none" />
          <MicButton value={text} onChange={setText} testId="noor-mic" />
          <button type="submit" disabled={!text.trim() || s.busy} aria-label="Ask"
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-contrast transition-opacity disabled:opacity-30">
            <ArrowUp className="size-4" aria-hidden /></button>
        </form>
        <div className="mt-2 flex items-center gap-3 text-[11.5px] text-text-muted">
          <button type="button" onClick={() => void loadBrief(edition() === "dealdesk" ? { module: "dealdesk" } : {})} data-testid="noor-chip-brief"
                  className="font-medium hover:text-text-primary">Today&apos;s brief</button>
          {["dealdesk", "ews", "whatif", "lenses"].includes(s.module.id) ? (<>
            <span aria-hidden>·</span>
            <button type="button" onClick={() => void loadBrief({ module: s.module.id })} data-testid="noor-chip-module"
                    className="font-medium hover:text-text-primary">What matters in {s.module.label}</button></>) : null}
        </div>
      </footer>
    </aside>
    </>
  );
}

/** The turn to bring to the top: the latest question with its answer, else the latest brief or note. */
export function scrollTarget(turns: Turn[]): string | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.kind === "ask" || t.kind === "brief" || t.kind === "note" || t.kind === "routed" || t.kind === "error") return t.id;
  }
  return null;
}

export function NoorMark({ className }: { className?: string }) {
  // نور, "light": a small sun in the accent colour.
  return (
    <span aria-hidden className={cn("flex size-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent", className)}>
      <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    </span>
  );
}

/** K7: earlier threads, newest first; opening one resumes it (it is never merged into another). */
function ThreadHistory({ threads }: { threads: NoorThread[] }) {
  return (
    <nav aria-label="Earlier threads" className="max-h-[45vh] overflow-y-auto border-b border-border px-2 py-2" data-testid="noor-history">
      <p className="px-2 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Earlier threads</p>
      {threads.length ? threads.map((t) => (
        <button key={t.id} type="button" onClick={() => selectThread(t.id)} data-testid="noor-history-item"
                className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-hover">
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-text-primary">{t.title}</span>
          <span className="shrink-0 text-[11px] text-text-muted">
            {(MODULES.find((m) => m.id === t.module)?.label ?? "").replace(/^the /, "")} · {ago(t.updated)}</span>
        </button>
      )) : <p className="px-2 py-1 text-[12px] text-text-muted">No earlier threads yet.</p>}
    </nav>
  );
}

function ago(ms: number): string {
  const m = Math.max(0, Math.round((Date.now() - ms) / 60000));
  if (m < 1) return "now";
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} h` : `${Math.round(h / 24)} d`;
}

function IconButton({ label, onClick, children, disabled = false, active = false, testId }: {
  label: string; onClick: () => void; children: React.ReactNode; disabled?: boolean; active?: boolean; testId?: string;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label} data-testid={testId}
            className={cn("flex size-7 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary disabled:opacity-35",
              active && "bg-surface-hover text-text-primary")}>
      {children}
    </button>
  );
}
