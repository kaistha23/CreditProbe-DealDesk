"use client";

/**
 * Speakers (R14 n, K10).
 *
 *   <SpeakText en ar />        reads a given spoken text (a brief line's script, an answer's spoken summary).
 *   <AnswerSpeaker target />   on a module answer: reads that answer's spoken summary, taken from its prose (headline
 *                              and sentences), never its tables, charts or traces (`spokenSummary`, pure).
 *
 * Both go through the one Noor voice (male, calm, the reader's language) and stop on a second click.
 */

import * as React from "react";
import { Volume2 } from "lucide-react";

import { cn } from "@/lib/utils";

import { spokenSummary } from "./noor-model";
import { speakNow, useNoor } from "./noor-store";

export function SpeakText({ en, ar, label = "Listen", className, testId = "noor-speak" }: {
  en: string | (() => string); ar?: string | null; label?: string; className?: string; testId?: string;
}) {
  const { voice } = useNoor();
  const speaking = voice.state === "speaking";
  return (
    <button type="button" aria-label={speaking ? "Stop reading" : label} title={speaking ? "Stop reading" : label}
            data-testid={testId} onClick={(e) => { e.stopPropagation(); speakNow(typeof en === "function" ? en() : en, ar); }}
            disabled={voice.state === "unsupported"}
            className={cn("inline-flex size-6 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary disabled:opacity-35",
              className)}>
      <Volume2 className="size-3.5" aria-hidden />
    </button>
  );
}

/** A speaker for an answer drawn by a module: reads the answer's prose from the element it sits in. */
export function AnswerSpeaker({ target, className, testId = "answer-speaker" }: {
  target: React.RefObject<HTMLElement | null>; className?: string; testId?: string;
}) {
  return (
    <SpeakText en={() => spokenSummary(proseOf(target.current))} label="Listen to this answer" className={className}
               testId={testId} />
  );
}

/** The prose of an answer element: paragraphs and headings, not tables, charts, traces or buttons. */
function proseOf(el: HTMLElement | null): string {
  if (!el) return "";
  const parts: string[] = [];
  el.querySelectorAll("h1, h2, h3, h4, p, li").forEach((n) => {
    if (n.closest("table, figure, svg, button, nav, [data-trace], [data-no-speak], .js-plotly-plot")) return;
    const t = (n as HTMLElement).innerText?.trim();
    if (t) parts.push(t);
  });
  return parts.join("\n");
}
