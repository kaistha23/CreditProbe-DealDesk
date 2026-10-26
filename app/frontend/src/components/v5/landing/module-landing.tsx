"use client";

/**
 * R13 Session X (J7, J10): the one module landing for the conversational modules (Deal Desk, What-If, Lenses).
 * A sleek centred chat box with a short title above it, a few starter prompts under it, and small cards of recent work.
 * Less detail is more: no strip, no notes; the module's own tools sit in its header, its lists below the landing.
 *
 * Early Warning and Borrower 360 stay table-first: they use `AskBar`, the same box in one line above the table.
 */

import { MicButton } from "@/components/noor/mic-button";
import { useRouter } from "next/navigation";
import * as React from "react";
import { ArrowRight, ArrowUp, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export interface RecentItem {
  key: string;
  title: string;
  sub?: string;
  meta?: string;
  onOpen: () => void;
  testId?: string;
}

export interface ModuleLandingProps {
  /** The short title above the box ("Ask Deal Desk"). */
  title: string;
  value: string;
  onChange: (v: string) => void;
  onAsk: (text: string) => void;
  placeholder: string;
  busy?: boolean;
  /** Starter prompts under the box (3–6). */
  examples?: string[];
  /** Extra starter chips after the examples (e.g. "Help me shape a scenario"). */
  extraChips?: React.ReactNode;
  /** Controls inside the box, left of the text (an attach button) and right of it before Send (a model picker). */
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  /** Content inside the box above the text (an uploaded document's thread). */
  above?: React.ReactNode;
  submitLabel?: string;
  error?: string;
  status?: React.ReactNode;
  recent?: RecentItem[];
  recentTitle?: string;
  recentLoading?: boolean;
  recentEmpty?: string;
  /** "See all" on the recent row. */
  recentAll?: { label: string; onOpen: () => void; testId?: string };
  rows?: number;
  /** Test ids: `${ids}-chat`, `${ids}-ask`, `${ids}-ask-send`, `${ids}-example`, `${ids}-examples`, `${ids}-recent`. */
  ids: string;
  sendTestId?: string;
  dropTarget?: { dragging: boolean; onDragOver: React.DragEventHandler; onDragLeave: React.DragEventHandler; onDrop: React.DragEventHandler };
}

export function ModuleLanding(p: ModuleLandingProps) {
  const send = () => { if (p.value.trim() && !p.busy) p.onAsk(p.value); };
  const recent = p.recent ?? [];
  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 py-4" data-testid={`${p.ids}-landing`}>
      <div className="space-y-3">
        <h2 className="text-center text-[22px] font-semibold tracking-tight text-text-primary" data-testid={`${p.ids}-landing-title`}>{p.title}</h2>
        <div className={cn("rounded-2xl border border-border bg-surface shadow-[0_1px_3px_rgb(0_0_0/0.06)] transition-colors focus-within:border-accent",
                           p.dropTarget?.dragging ? "border-accent ring-2 ring-accent/30" : "")}
             data-testid={`${p.ids}-chat`} data-tour={`${p.ids}-chat`}
             onDragOver={p.dropTarget?.onDragOver} onDragLeave={p.dropTarget?.onDragLeave} onDrop={p.dropTarget?.onDrop}>
          {p.above ? <div className="border-b border-border px-4 py-3">{p.above}</div> : null}
          <form className="flex flex-col gap-1 px-3 pb-2.5 pt-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <textarea value={p.value} onChange={(e) => p.onChange(e.target.value)} rows={p.rows ?? 2} data-testid={`${p.ids}-ask`}
                      aria-label={p.title} placeholder={p.placeholder}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                      className="min-h-[48px] w-full resize-none bg-transparent px-1 text-[14px] leading-6 text-text-primary placeholder:text-text-muted focus:outline-none" />
            <div className="flex items-center gap-2">
              {p.leading}
              <div className="ml-auto flex items-center gap-2">
                {p.trailing}
                {/* R14 n (K10): ask by voice; the transcript shows in the box before sending. */}
                <MicButton value={p.value} onChange={p.onChange} size="md" testId={`${p.ids}-mic`} />
                <button type="submit" disabled={p.busy || !p.value.trim()} data-testid={p.sendTestId ?? `${p.ids}-ask-send`}
                        aria-label={p.submitLabel ?? "Ask"} title={p.submitLabel ?? "Ask"}
                        className="inline-flex size-8 items-center justify-center rounded-full bg-accent text-accent-contrast transition-opacity disabled:opacity-30">
                  {p.busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={16} />}</button>
              </div>
            </div>
          </form>
        </div>
        {p.examples?.length || p.extraChips ? (
          <div className="flex flex-wrap justify-center gap-1.5" data-testid={`${p.ids}-examples`}>
            {(p.examples ?? []).map((ex) => (
              <button key={ex} type="button" onClick={() => p.onAsk(ex)} disabled={p.busy} data-testid={`${p.ids}-example`}
                      className="rounded-full border border-border bg-surface px-3 py-1 text-[12px] text-text-secondary hover:border-accent hover:text-accent disabled:opacity-40">{ex}</button>))}
            {p.extraChips}
          </div>) : null}
        {p.error ? <p className="text-center text-[12px] text-negative" role="alert">{p.error}</p> : null}
        {p.status ? <div className="text-center text-[12px] text-text-muted">{p.status}</div> : null}
      </div>

      {recent.length || p.recentLoading || p.recentEmpty ? (
        <section className="space-y-2" data-testid={`${p.ids}-recent`}>
          <div className="flex items-baseline justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">{p.recentTitle ?? "Recent work"}</h3>
            {p.recentAll ? <button type="button" onClick={p.recentAll.onOpen} data-testid={p.recentAll.testId}
                                   className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">{p.recentAll.label} <ArrowRight size={12} /></button> : null}
          </div>
          {p.recentLoading && !recent.length ? <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => (
            <div key={i} className="h-[62px] animate-pulse rounded-lg border border-border bg-surface-hover/40" />))}</div> : null}
          {!p.recentLoading && !recent.length && p.recentEmpty ? <p className="text-[12px] text-text-muted">{p.recentEmpty}</p> : null}
          {recent.length ? (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {recent.map((r) => (
                <button key={r.key} type="button" onClick={r.onOpen} data-testid={r.testId ?? `${p.ids}-recent-card`}
                        className="group min-w-0 rounded-lg border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-accent">
                  <p className="truncate text-[13px] font-medium text-text-primary group-hover:text-accent" title={r.title}>{r.title}</p>
                  {r.sub ? <p className="truncate text-[11px] text-text-secondary" title={r.sub}>{r.sub}</p> : null}
                  {r.meta ? <p className="truncate text-[11px] text-text-muted">{r.meta}</p> : null}
                </button>))}
            </div>) : null}
        </section>) : null}
    </div>
  );
}

/** Table-first modules (Early Warning, Borrower 360): the ask box in one line above the table. */
export function AskBar({ value, onChange, onAsk, placeholder, busy, ids, label = "Ask" }: {
  value: string; onChange: (v: string) => void; onAsk: (text: string) => void; placeholder: string; busy?: boolean; ids: string; label?: string;
}) {
  return (
    <form className="flex items-center gap-2 rounded-full border border-border bg-surface py-1 pl-4 pr-1 shadow-[0_1px_2px_rgb(0_0_0/0.04)] focus-within:border-accent"
          data-testid={`${ids}-askbar`} data-tour={`${ids}-list`} onSubmit={(e) => { e.preventDefault(); if (value.trim() && !busy) onAsk(value); }}>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={label} data-testid={`${ids}-askbar-input`}
             className="h-8 min-w-0 flex-1 bg-transparent text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none" />
      <MicButton value={value} onChange={onChange} testId={`${ids}-mic`} />
      <button type="submit" disabled={busy || !value.trim()} aria-label={label} data-testid={`${ids}-askbar-send`}
              className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-contrast disabled:opacity-30">
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}</button>
    </form>
  );
}

/**
 * The one-line ask bar wired to the Cockpit engine (the Cockpit answers any question; Session H's Ask tab reads ?q=).
 * `before` runs first (Early Warning remembers the book so Back returns to it).
 */
export function CockpitAskBar({ ids, placeholder, before }: { ids: string; placeholder: string; before?: () => void }) {
  const router = useRouter();
  const [draft, setDraft] = React.useState("");
  return (
    <AskBar ids={ids} value={draft} onChange={setDraft} placeholder={placeholder}
            onAsk={(q) => { before?.(); router.push(`/?q=${encodeURIComponent(q.trim())}`); }} />
  );
}
