"use client";

/**
 * The one thread frame (PLAN_R5 G4, docs/v5/THREAD_API.md 1.1): a header, the conversation scrolling in the
 * middle, and the composer pinned at the bottom with the follow-up chips and the module's primary actions
 * (Create report, Execute scenario, Optimise, Add to section) beside Send. Look and spacing follow the frozen
 * Cockpit thread: right-aligned accent question bubble, the process trace above each answer.
 */

import * as React from "react";
import { Send } from "lucide-react";

import { bankerChips } from "@/components/answer/banker";
import { A as ANSWER_STYLE } from "@/components/answer/styles";
import { cn } from "@/lib/utils";
import type { TraceSnapshot } from "@/lib/v5/thread";

import { MicButton } from "@/components/noor/mic-button";
import { AnswerSpeaker } from "@/components/noor/speak-text";

import { ProcessTrace } from "./process-trace";
import { TurnActions, type TurnActionsProps } from "./action-bar";

export interface Chip { label: string; send: string }

export interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  placeholder?: string;
  busy?: boolean;
  disabled?: boolean;
  chips?: Chip[];
  onChip?: (c: Chip) => void;
  leading?: React.ReactNode;
  actions?: React.ReactNode;
  /** Prefix of the data-testids: `${testId}-composer`, `${testId}-send`, `${testId}-chips`, `${testId}-actions`. */
  testId?: string;
  sendLabel?: string;
  /** Send is the primary button when the module has no primary action of its own. */
  primarySend?: boolean;
  rows?: number;
  /** Override the composer / send data-testids (modules keeping their existing sweep ids). */
  inputTestId?: string;
  sendTestId?: string;
  /** One data-testid for every chip (modules keeping their existing sweep ids); default `${testId}-chip-<slug>`. */
  chipTestId?: string;
}

export function slug(s: string): string {
  return s.toLowerCase().replace(/\W+/g, "-");
}

export function Composer({ value, onChange, onSubmit, placeholder, busy = false, disabled = false, chips = [], onChip, leading,
                           actions, testId = "thread", sendLabel = "Send", primarySend, rows = 2, compact = false, inputTestId, sendTestId, chipTestId }: ComposerProps & { compact?: boolean }) {
  const primary = primarySend ?? !actions;
  // PLAN_R12 N2 (I9): follow-up chips in banker language only, at most four.
  const shown = bankerChips(chips, 4);
  return (
    <div className="space-y-2" data-testid={`${testId}-composer-bar`}>
      {shown.length ? (
        <div className="flex flex-wrap gap-1.5" data-testid={`${testId}-chips`}>
          {shown.map((c) => (
            <button key={c.label} type="button" disabled={busy || disabled} onClick={() => (onChip ? onChip(c) : onSubmit(c.send))}
                    data-testid={chipTestId ?? `${testId}-chip-${slug(c.label)}`}
                    className={ANSWER_STYLE.chip}>
              {c.label}</button>))}
        </div>) : null}
      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (!busy && value.trim()) onSubmit(value); }}>
        {leading}
        {/* R10 G-CHAT (img07, img13): module actions sit before the input so Send is always the right end of the row */}
        {actions ? <div className="flex shrink-0 items-end gap-2" data-testid={`${testId}-actions`}>{actions}</div> : null}
        <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows} placeholder={placeholder} disabled={disabled}
                  data-testid={inputTestId ?? `${testId}-composer`} aria-label={placeholder || "Message"}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!busy && value.trim()) onSubmit(value); } }}
                  className={cn("min-h-[44px] flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-text-primary focus:border-accent focus:outline-none",
                                compact ? "text-[12px]" : "text-[13px]")} />
        {/* R14 n (K10): ask by voice in every thread; the transcript shows in the box before sending. */}
        {disabled ? null : <MicButton value={value} onChange={onChange} size="md" testId={`${testId}-mic`} className="mb-1" />}
        <button type="submit" disabled={busy || disabled || !value.trim()} data-testid={sendTestId ?? `${testId}-send`}
                className={cn("inline-flex items-center gap-1 rounded-md px-3 py-2 text-[13px] font-medium disabled:opacity-40",
                              primary ? "bg-accent text-accent-contrast" : "border border-border text-text-primary hover:bg-surface-hover")}>
          <Send size={14} aria-hidden /> {sendLabel}</button>
      </form>
    </div>
  );
}

export function ThreadShell({ header, children, composer, compact = false, scrollKey, notice, testId = "thread-shell", scrollOnMount = true }: {
  header?: React.ReactNode; children: React.ReactNode; composer: ComposerProps; compact?: boolean;
  scrollKey?: unknown; notice?: React.ReactNode; testId?: string;
  /** R7 U2: false keeps the page at its top on the first render (Deal Desk opens on its charts, not on the composer). */
  scrollOnMount?: boolean;
}) {
  const bottom = React.useRef<HTMLDivElement | null>(null);
  const first = React.useRef(true);
  React.useEffect(() => {
    if (first.current) { first.current = false; if (compact || !scrollOnMount) return; }
    bottom.current?.scrollIntoView({ behavior: "smooth", block: compact ? "nearest" : "end" });
  }, [scrollKey, compact, scrollOnMount]);
  return (
    <div className={cn("flex flex-col", compact ? "gap-3" : "min-h-[calc(100dvh-7.5rem)] gap-4")} data-testid={testId}>
      {header}
      {notice}
      {/* The conversation takes the free height, so the chat box sits at the bottom even on a short thread (G4). */}
      <div className={cn(compact ? "space-y-3" : "flex-1 space-y-5")} data-testid="thread-turns">
        {children}
        <div ref={bottom} />
      </div>
      <div className={cn("sticky bottom-0 z-20 -mx-1 border-t border-border bg-surface/95 px-1 backdrop-blur", compact ? "py-2" : "py-3")}
           data-testid="thread-composer">
        <Composer {...composer} compact={compact} />
      </div>
    </div>
  );
}

export function UserTurn({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div className="flex justify-end" data-testid="thread-turn-user">
      <p className={cn("max-w-3xl whitespace-pre-line rounded-lg bg-accent px-3 py-2 text-accent-contrast", compact ? "max-w-[92%] text-[12px]" : "text-[13px]")}>{text}</p>
    </div>
  );
}

export function AssistantTurn({ trace, children, compact = false, testId = "thread-turn-assistant", actions }: {
  trace?: TraceSnapshot | null; children?: React.ReactNode; compact?: boolean; testId?: string;
  /** R16 t (M7): Share, Trace, Word and Add to report under the answer (inside a ThreadActionsProvider). */
  actions?: TurnActionsProps | null;
}) {
  const body = React.useRef<HTMLDivElement | null>(null);
  return (
    <div className="space-y-2" data-testid={testId}>
      {trace ? <ProcessTrace snapshot={trace} compact={compact} /> : null}
      {/* R14 n (K10): a speaker on every answer, reading its spoken summary (its prose, never its tables). */}
      {children ? (
        <div ref={body} className="relative">
          <AnswerSpeaker target={body} testId="answer-speaker" className="absolute -right-1 -top-1 z-10 bg-surface/80" />
          {children}
        </div>) : null}
      {children && actions ? <TurnActions trace={trace} {...actions} bodyRef={body} compact={compact} /> : null}
    </div>
  );
}
