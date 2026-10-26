"use client";

/**
 * Noor's brief, one component everywhere (R12_FEEDBACK J3): in the panel, on the Home Brief tab and in a module brief.
 *
 *   an eyebrow with the data dates per source (R14 K9: "Corporate 2026Q2 · Deal Desk today", never "since yesterday")
 *   and a Listen button that reads the whole brief (K10: the headline, then one sentence per line);
 *   a headline sentence ("Five things to pay attention to, 1 critical.");
 *   at most five lines, each a fact with one severity dot, "New" only when its source refreshed since the last visit;
 *   below each line, always visible and left-aligned (K6): the source, then Why · What to do · Open and a speaker
 *   that reads the line's spoken script (40–70 s);
 *   the rest behind "n more", collapsed, below the list.
 *
 * No chip rows, no repeated controls, no notes. Why? opens the line's evidence (the deterministic Cockpit attention
 * card behind it) when the page can show it, else Noor's answer in the panel.
 */

import * as React from "react";
import { ChevronDown, Headphones } from "lucide-react";

import { cn } from "@/lib/utils";

import { type Brief, type BriefItem, headlineOf, severityLabel, severityTone } from "./noor-model";
import { askOptions, askWhy, listenBrief, openItem, speakLine, useNoor } from "./noor-store";
import { ProposeMonitoringButton } from "@/components/v5/dealdesk/flow-monitoring"; // R14 x (K35 (1)): f's action on brief lines
import type { MonitoringSubject } from "@/lib/v5/dealdesk-flow";

const DOT = {
  negative: "bg-negative", warning: "bg-warning", neutral: "bg-accent", muted: "bg-text-muted/60",
} as const;

export const MAX_LINES = 5;

export interface NoorBriefProps {
  brief: Brief;
  variant?: "page" | "panel" | "module";
  /** The page can open the evidence card itself (Home): return true when it did. */
  onEvidence?: (item: BriefItem) => boolean;
  /** Called before any action (the module brief opens the panel). */
  onAction?: () => void;
  /** Extra controls on the meta row (the speaker button on the Brief tab). */
  controls?: React.ReactNode;
  /** Fewer than five lines before "n more" (module briefs show three). */
  limit?: number;
  testId?: string;
}

export function NoorBrief({ brief, variant = "panel", onEvidence, onAction, controls, limit, testId = "noor-brief" }: NoorBriefProps) {
  const [expanded, setExpanded] = React.useState(false);
  const all = [...brief.items, ...brief.more];
  const max = Math.max(1, Math.min(limit ?? MAX_LINES, MAX_LINES));
  const shown = all.slice(0, max);
  const rest = all.slice(max);
  const page = variant === "page";
  return (
    <section data-testid={testId} aria-label={brief.title} className={cn(page ? "space-y-5" : "space-y-2.5")}>
      <header className="space-y-1.5">
        <div className="flex items-center gap-2">
          <p className={cn("min-w-0 flex-1 truncate font-semibold uppercase text-text-muted",
                           page ? "text-[11px] tracking-[0.14em]" : "text-[10.5px] tracking-[0.1em]")}
             data-testid="noor-brief-meta">
            {brief.assistant} · {eyebrow(brief)}
          </p>
          <ListenButton brief={brief} compact={!page} />
          {controls}
        </div>
        <p data-testid="noor-headline"
           className={cn("font-prose text-text-primary",
                         page ? "text-[22px] leading-snug tracking-[-0.01em]" : "text-[15px] leading-snug")}>
          {headlineOf(brief)}
        </p>
      </header>
      <ol className={cn("border-t border-border", page && "rounded-none")} data-testid={`${testId}-lines`} data-tour={page ? "brief-lines" : undefined}>
        {shown.map((it) => <Line key={it.id} item={it} page={page} onEvidence={onEvidence} onAction={onAction} />)}
        {expanded ? rest.map((it) => <Line key={it.id} item={it} page={page} onEvidence={onEvidence} onAction={onAction} />) : null}
      </ol>
      {rest.length ? (
        <button type="button" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded} data-testid="noor-more"
                className="inline-flex items-center gap-1 text-[12px] font-medium text-text-muted hover:text-text-primary focus-visible:text-text-primary">
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} aria-hidden />
          {expanded ? "Fewer" : `${rest.length} more`}
        </button>
      ) : null}
    </section>
  );
}

/** K9: the data dates per source family; the brief's own title only when no line carries a date. */
export function eyebrow(brief: Pick<Brief, "title" | "data_dates">): string {
  const dd = brief.data_dates ?? [];
  return dd.length ? dd.map((d) => d.text).join(" · ") : brief.title;
}

/** K10: Listen at the top of the brief: all issues, the headline then one sentence each. */
function ListenButton({ brief, compact }: { brief: Brief; compact: boolean }) {
  const { voice } = useNoor();
  const speaking = voice.state === "speaking";
  return (
    <button type="button" onClick={() => listenBrief(brief)} data-testid="noor-listen"
            aria-label={speaking ? "Stop reading" : "Listen to the brief"} disabled={voice.state === "unsupported"}
            className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border font-medium text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary disabled:opacity-40",
              compact ? "h-6 px-1.5 text-[11px]" : "h-7 px-2.5 text-[12px]", speaking && "border-accent text-accent")}>
      <Headphones className="size-3.5" aria-hidden />{compact ? null : (speaking ? "Stop" : "Listen")}
    </button>
  );
}

function Line({ item, page, onEvidence, onAction }: {
  item: BriefItem; page: boolean; onEvidence?: (item: BriefItem) => boolean; onAction?: () => void;
}) {
  const tone = severityTone(item.severity);
  const act = (fn: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); onAction?.(); fn(); };
  const why = () => { if (!(onEvidence && item.evidence?.length && onEvidence(item))) void askWhy(item); };
  const source = [item.source_label, item.since].filter(Boolean).join(" · ");
  return (
    <li data-testid={`noor-line-${item.id}`}
        className={cn("group relative flex gap-3 border-b border-border outline-none",
                      page ? "py-3.5" : "py-2.5")}>
      <span aria-label={`${severityLabel(item.severity)} priority`} title={`${severityLabel(item.severity)} priority`}
            className={cn("shrink-0 rounded-full", DOT[tone], page ? "mt-[9px] size-[7px]" : "mt-[7px] size-1.5")} />
      <div className="min-w-0 flex-1">
        <p className={cn("text-text-primary", page ? "text-[15px] leading-snug" : "text-[13px] leading-snug")}>
          {item.title}
          {item.new ? <span data-testid="noor-line-new"
                            className="ml-2 inline-block rounded-sm bg-accent/10 px-1 align-middle text-[10px] font-semibold uppercase tracking-[0.06em] text-accent">New</span> : null}
        </p>
        <p className={cn("mt-0.5 min-w-0 truncate text-text-muted", page ? "text-[12px]" : "text-[11.5px]")} data-testid="noor-line-source">
          {source}
        </p>
        {/* K6: the actions sit below the line, visible, left-aligned (not on hover at the right end). */}
        <nav aria-label="Actions" data-testid="noor-line-actions"
             className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px]">
          <TextLink onClick={act(why)} testId="noor-why" tour="brief-why">Why</TextLink>
          <span aria-hidden className="text-text-muted/50">·</span>
          <TextLink onClick={act(() => void askOptions(item))} testId="noor-options">What to do</TextLink>
          <span aria-hidden className="text-text-muted/50">·</span>
          <TextLink onClick={act(() => openItem(item))} testId="noor-open">Open</TextLink>
          <span aria-hidden className="text-text-muted/50">·</span>
          <button type="button" onClick={(e) => { e.stopPropagation(); void speakLine(item); }} data-testid="noor-line-speaker"
                  aria-label={`Listen: ${item.title}`} title="Listen: what it is, why, and what to do"
                  className="inline-flex items-center rounded-sm text-text-muted hover:text-text-primary">
            <SpeakerGlyph /></button>
          {monitorSubject(item) ? (<>
            <span aria-hidden className="text-text-muted/50">·</span>
            <ProposeMonitoringButton compact subject={monitorSubject(item) as MonitoringSubject} testId="noor-line-monitor" />
          </>) : null}
        </nav>
      </div>
    </li>
  );
}

function SpeakerGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M11 5 6 9H2v6h4l5 4V5z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M19 5a10 10 0 0 1 0 14" />
    </svg>
  );
}

function TextLink({ children, onClick, testId, tour }: { children: React.ReactNode; onClick: (e: React.MouseEvent) => void; testId: string; tour?: string }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId} data-tour={tour}
            className="rounded-sm font-medium text-accent underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none">
      {children}
    </button>
  );
}

/** R14 x (K35 (1)): "Propose for monitoring" on a brief line that names one borrower or one deal (f's form and relation). */
function monitorSubject(item: BriefItem): MonitoringSubject | null {
  const e = (item.entity ?? {}) as { kind?: string; id?: unknown; name?: unknown; deals?: unknown };
  if (e.kind === "borrower" && typeof e.id === "string" && e.id) {
    return { obligorId: e.id, obligorName: typeof e.name === "string" ? e.name : e.id, source: "brief", reason: item.title };
  }
  if (Array.isArray(e.deals) && e.deals.length === 1 && typeof e.deals[0] === "string") {
    return { proposalId: e.deals[0], source: "brief", reason: item.title };
  }
  return null;
}
