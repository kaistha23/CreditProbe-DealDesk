"use client";

/**
 * R14 U (K34): the shared "In plain words" block at the top of every panel.
 *
 *   <PlainWords lines={["This checks …", "Set current ratio ≥1.40x …", "Agree headroom with the client."]} speak />
 *
 * 3–4 lines, ≤ 60 words, written by the panel owner's deterministic writer from the panel's own result (N4). The block
 * explains credit jargon in brackets on first use (plain-words-model.ts → glossFirstUse) unless `gloss={false}`.
 * `speak` shows a speaker button that reads the block (K10); the voice comes from Noor's store by default, and session
 * n can plug its own reader with `registerPlainWordsVoice`. While the panel loads, pass `loading`; the block keeps its
 * height so the panel does not jump.
 *
 * Stable API (sessions g, i, f, p consume it): `PlainWords`, `registerPlainWordsVoice`, and the model helpers
 * re-exported here. Add props, never rename them. Test ids: `plain-words` (or `testId`), `plain-words-line`,
 * `plain-words-speak`.
 */

import * as React from "react";
import { Sparkles, Square, Volume2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { speakOnClick as noorSpeak, stopSpeaking as noorStop } from "@/components/noor/noor-store";

import { checkPlainWords, glossFirstUse, spokenText } from "./plain-words-model";

export { checkPlainWords, glossFirstUse, spokenText, GLOSSARY, PLAIN_WORDS_LIMITS } from "./plain-words-model";

export interface PlainWordsVoice {
  speak: (text: string, opts?: { language?: "en" | "ar" }) => void;
  stop: () => void;
}

// R16 M1: `voice.speak` is called only from the speaker button's click (`toggle`); never on render or load.
let voice: PlainWordsVoice = { speak: (t) => noorSpeak(t), stop: () => noorStop() };

/** Session n: plug the house reader (male voice, script writer) here once; every block uses it. */
export function registerPlainWordsVoice(v: PlainWordsVoice) { voice = v; }

export interface PlainWordsProps {
  /** 3–4 short lines from the panel's own result. */
  lines: string[];
  /** Show the speaker button (reads `spoken` if given, else the lines). */
  speak?: boolean;
  /** A spoken script written for the ear (K10); defaults to the lines. */
  spoken?: string;
  /** Explain jargon in brackets on first use (default true). */
  gloss?: boolean;
  /** The heading; default "In plain words". */
  title?: string;
  /** Keep the block's place while the panel loads. */
  loading?: boolean;
  /** A custom speaker control in place of the default button (session n: its SpeakText with English and Arabic). */
  speaker?: React.ReactNode;
  /** A small trailing source note ("From dd_review_finding, 2026Q2"). */
  source?: React.ReactNode;
  className?: string;
  testId?: string;
}

export function PlainWords({ lines, speak, spoken, gloss = true, title = "In plain words", loading, source, speaker, className, testId = "plain-words" }: PlainWordsProps) {
  const [reading, setReading] = React.useState(false);
  const clean = React.useMemo(() => lines.map((l) => l.trim()).filter(Boolean), [lines]);
  const shown = React.useMemo(() => (gloss ? glossFirstUse(clean) : clean), [clean, gloss]);
  const check = React.useMemo(() => checkPlainWords(shown), [shown]);

  React.useEffect(() => {
    if (!reading) return;
    const t = window.setTimeout(() => setReading(false), Math.min(90_000, 400 * spokenText(clean).split(" ").length));
    return () => window.clearTimeout(t);
  }, [reading, clean]);
  React.useEffect(() => () => { if (reading) voice.stop(); }, [reading]);

  if (!loading && !clean.length) return null;
  const toggle = () => {
    if (reading) { voice.stop(); setReading(false); return; }
    voice.speak(spoken ?? spokenText(clean));
    setReading(true);
  };
  return (
    <section aria-label={title} data-testid={testId} data-plain-words="1" data-words={check.words} data-ok={check.ok ? "1" : "0"}
             className={cn("rounded-lg border border-ai-edge bg-ai-muted px-3.5 py-2.5", className)}>
      <div className="flex items-center gap-1.5">
        <Sparkles className="size-3.5 text-ai" aria-hidden />
        <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ai">{title}</h3>
        {speaker && !loading ? <span className="ml-auto" data-testid={`${testId}-speaker`}>{speaker}</span> : speak && !loading ? (
          <button type="button" onClick={toggle} aria-pressed={reading} data-testid={`${testId}-speak`}
                  aria-label={reading ? "Stop reading" : "Read this aloud"} title={reading ? "Stop reading" : "Read this aloud"}
                  className="ml-auto inline-flex size-6 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary">
            {reading ? <Square className="size-3" aria-hidden /> : <Volume2 className="size-3.5" aria-hidden />}
          </button>
        ) : null}
      </div>
      {loading ? (
        <div className="mt-1.5 space-y-1.5" aria-busy="true">
          <div className="h-3 w-11/12 animate-pulse rounded bg-surface-hover" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-surface-hover" />
          <div className="h-3 w-3/5 animate-pulse rounded bg-surface-hover" />
        </div>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {shown.map((l, i) => (
            <li key={i} data-testid={`${testId}-line`} className="text-[13px] leading-[1.45] text-text-primary">{l}</li>
          ))}
        </ul>
      )}
      {source && !loading ? <p className="mt-1 text-[11px] text-text-muted">{source}</p> : null}
    </section>
  );
}
