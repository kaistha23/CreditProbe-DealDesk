"use client";

/**
 * The microphone button (R14 n, K10): push-to-talk into any ask box. The transcript is shown in the box before
 * sending; nothing is sent by voice alone. Used in the Cockpit Ask, the Noor panel, every module ask box and thread
 * composer. Labelled: the audio is processed by the browser's speech service.
 */

import * as React from "react";
import { Mic, MicOff } from "lucide-react";

import { cn } from "@/lib/utils";

import { type MicState, joinTranscript, micLabel, micLang, micSupported, startListening } from "./noor-mic";
import { useNoor } from "./noor-store";

const noSubscribe = () => () => undefined;

export function MicButton({ value, onChange, className, size = "sm", testId = "noor-mic" }: {
  /** The box's current text (heard words are added after it). */
  value: string;
  onChange: (text: string) => void;
  className?: string;
  size?: "sm" | "md";
  testId?: string;
}) {
  const { voice } = useNoor();
  const lang = micLang(voice.language);
  const [heard, setState] = React.useState<MicState>("idle");
  const supported = React.useSyncExternalStore(noSubscribe, micSupported, () => true);
  const state: MicState = supported ? heard : "unsupported";
  const stop = React.useRef<(() => void) | null>(null);
  const base = React.useRef("");
  React.useEffect(() => () => stop.current?.(), []);
  const label = micLabel(state, lang);
  const listening = state === "listening";
  const toggle = () => {
    if (listening) { stop.current?.(); stop.current = null; setState("idle"); return; }
    base.current = value;
    stop.current = startListening(lang, {
      onText: (heard) => onChange(joinTranscript(base.current, heard)),
      onState: setState,
    });
  };
  return (
    <span className="relative inline-flex">
    {listening || state === "denied" || state === "error" ? (
      <span role="status" data-testid={`${testId}-status`}
            className="pointer-events-none absolute bottom-full right-0 z-50 mb-1.5 w-64 rounded-md border border-border bg-surface px-2.5 py-1.5 text-left text-[11px] leading-snug text-text-secondary shadow-md">
        {label}</span>) : null}
    <button type="button" onClick={toggle} aria-label={label} title={label} aria-pressed={listening}
            data-testid={testId} data-mic-state={state} data-mic-lang={lang}
            disabled={state === "unsupported"}
            className={cn("flex shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-35",
              size === "md" ? "size-8" : "size-7",
              listening ? "bg-negative/15 text-negative" : "text-text-muted hover:bg-surface-hover hover:text-text-primary",
              className)}>
      {state === "denied" ? <MicOff className="size-4" aria-hidden />
        : <Mic className={cn("size-4", listening && "animate-pulse")} aria-hidden />}
    </button>
    </span>
  );
}

