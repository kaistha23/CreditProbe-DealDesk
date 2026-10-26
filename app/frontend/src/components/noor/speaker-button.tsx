"use client";

/**
 * The speaker button (J1). A click is the user gesture Chrome needs: it turns the reader's voice on (kept for them)
 * and reads the brief now; while reading, the same button stops. R16 M1: this click (or another speaker / Listen
 * click) is the ONLY way Noor speaks; with no voice chosen in Settings → Voice it stays silent and `VoiceChoiceNote`
 * says "Choose a voice in Settings → Voice", with a button to that page. The state is always visible: off, ready, reading,
 * another voice standing in for the language, or no voice installed (said in words, not by silence).
 */

import * as React from "react";
import { Loader2, Volume2, VolumeX, X } from "lucide-react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";

import type { Brief } from "./noor-model";
import { dismissVoiceNotice, prepareVoice, speakerButton, useNoor } from "./noor-store";
import { VOICE_SETTINGS_HREF, voiceStateLabel } from "./noor-voice";

export function SpeakerButton({ brief, size = "sm", showProblem = false }: {
  brief?: Brief | null; size?: "sm" | "md"; showProblem?: boolean;
}) {
  const { voice } = useNoor();
  React.useEffect(() => { prepareVoice(); }, []);
  const label = voiceStateLabel(voice.state, voice.on, voice.language);
  const speaking = voice.state === "speaking";
  const broken = voice.state === "no-voice" || voice.state === "unsupported";
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={() => speakerButton(brief)} aria-label={label} title={label}
              aria-pressed={speaking} data-testid="noor-speaker" data-voice-state={voice.state} data-voice-on={voice.on}
              disabled={voice.state === "unsupported"}
              className={cn("flex items-center justify-center rounded-md transition-colors disabled:opacity-35",
                size === "md" ? "size-8" : "size-7",
                speaking ? "bg-accent/15 text-accent" : "text-text-muted hover:bg-surface-hover hover:text-text-primary")}>
        {voice.state === "loading" ? <Loader2 className="size-4 animate-spin" aria-hidden />
          : voice.on && !broken && voice.state !== "not-chosen" ? <Volume2 className={cn("size-4", speaking && "animate-pulse")} aria-hidden />
          : <VolumeX className="size-4" aria-hidden />}
      </button>
      {showProblem && broken ? (
        <span className="text-[11.5px] text-text-muted" role="status" data-testid="noor-voice-problem">{label}</span>
      ) : null}
    </span>
  );
}

/** One quiet line when the voice cannot be heard here (no voice installed, or no speech in this browser). */
export function VoiceNotice({ className }: { className?: string }) {
  const { voice } = useNoor();
  if (voice.state !== "no-voice" && voice.state !== "unsupported") return null;
  return (
    <p className={cn("text-[11.5px] text-text-muted", className)} role="status" data-testid="noor-voice-problem">
      {voiceStateLabel(voice.state, voice.on, voice.language)}
    </p>
  );
}

/**
 * R16 M1: the short note after a speaker click when no voice is chosen for the language. Mounted once in the top bar
 * (every screen), so every speaker (brief, lines, answers, "In plain words") shows it. The button opens Settings → Voice.
 */
export function VoiceChoiceNote() {
  const { voice } = useNoor();
  const router = useRouter();
  if (!voice.notice) return null;
  return (
    <div role="status" data-testid="noor-voice-choose"
         className="fixed bottom-4 left-1/2 z-[70] flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] text-text-primary shadow-lg">
      <VolumeX className="size-4 shrink-0 text-text-muted" aria-hidden />
      <button type="button" data-testid="noor-voice-choose-open" className="font-medium text-accent hover:underline"
              onClick={() => { dismissVoiceNotice(); router.push(VOICE_SETTINGS_HREF); }}>{voice.notice}</button>
      <button type="button" aria-label="Dismiss" onClick={dismissVoiceNotice}
              className="rounded p-0.5 text-text-muted hover:bg-surface-hover hover:text-text-primary"><X className="size-3.5" aria-hidden /></button>
    </div>
  );
}
