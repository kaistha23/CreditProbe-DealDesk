/**
 * The tour's speech: the voice chosen in Settings -> Voice (R15 L2) with its rate and pitch. R16 M1: only that voice;
 * with none chosen for the language the tour is captions only (no interim pick). And the tour speaks only after the
 * reader pressed its "Play with voice" control during this tour (tour-player.tsx); captions are the default.
 * `speak` resolves when the line ends, is cancelled, or cannot be spoken; `outcome` says which, so the player falls
 * back to the step's own timer (captions only) without ever stalling.
 */
import { speakNeural, stopNeural } from "../../noor/neural-voice.ts";
import { suggestVoice } from "../../noor/noor-voice.ts";
import { isNeural, readChosen, resolveChosen } from "../../noor/voice-choice.ts";

import type { TourLang } from "./tour-model.ts";

export type SpeakOutcome = "ended" | "cancelled" | "no-voice" | "blocked" | "unsupported";

function synth(): SpeechSynthesis | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  return window.speechSynthesis;
}

/** The browser's voices, waiting (at most `ms`) for Chrome's late `voiceschanged`. */
export function loadVoices(ms = 1500): Promise<SpeechSynthesisVoice[]> {
  const s = synth();
  if (!s) return Promise.resolve([]);
  const now = s.getVoices();
  if (now.length) return Promise.resolve(now);
  return new Promise((resolve) => {
    const done = () => { s.removeEventListener("voiceschanged", done); resolve(s.getVoices()); };
    s.addEventListener("voiceschanged", done);
    window.setTimeout(done, ms);
  });
}

/** R15 L2 / R16 M1: the voice chosen in Settings -> Voice for the language (with its rate and pitch), else null. */
export async function tourVoice(lang: TourLang):
    Promise<{ voice: SpeechSynthesisVoice | null; neural?: { id: string; lang: string }; rate: number; pitch: number } | null> {
  const choice = readChosen()[lang === "ar" ? "ar-gulf" : "en"];
  // R16 v: the offline neural voice chosen in Settings -> Voice.
  if (isNeural(choice)) return { voice: null, neural: { id: choice.name, lang: choice.lang }, rate: choice.rate, pitch: choice.pitch };
  const voices = await loadVoices();
  const mine = resolveChosen(voices, choice);
  return mine && choice ? { voice: mine, rate: choice.rate, pitch: choice.pitch } : null;
}

// ---------------------------------------------------------------- one voice at a time while the tour plays
//
// Pages the tour opens never read aloud on their own (R16 M1), but a stray speaker click could. While the tour plays, only the tour's lines are spoken: other utterances are dropped and other `cancel()` calls cannot cut a
// tour line short. `guardSpeech(false)` restores the browser's own methods when the tour closes.

const ours = new WeakSet<SpeechSynthesisUtterance>();
let saved: { speak: SpeechSynthesis["speak"]; cancel: SpeechSynthesis["cancel"] } | null = null;

export function guardSpeech(on: boolean): void {
  const s = synth();
  if (!s) return;
  try {
    if (on && !saved) {
      const speak0 = s.speak.bind(s);
      const cancel0 = s.cancel.bind(s);
      saved = { speak: speak0, cancel: cancel0 };
      Object.defineProperty(s, "speak", { configurable: true, writable: true,
        value: (u: SpeechSynthesisUtterance) => { if (ours.has(u)) speak0(u); } });
      Object.defineProperty(s, "cancel", { configurable: true, writable: true, value: () => { /* only the tour cancels */ } });
    } else if (!on && saved) {
      delete (s as unknown as Record<string, unknown>).speak;
      delete (s as unknown as Record<string, unknown>).cancel;
      saved = null;
    }
  } catch {
    saved = null;   // a browser that will not let the methods be wrapped: both may speak
  }
}

function realCancel(): void {
  const s = synth();
  if (!s) return;
  if (saved) saved.cancel();
  else s.cancel();
}

export function cancelSpeech(): void {
  try { realCancel(); } catch { /* nothing to cancel */ }
  stopNeural();
}

export function pauseSpeech(): void {
  try { synth()?.pause(); } catch { /* ignore */ }
}

export function resumeSpeech(): void {
  try { synth()?.resume(); } catch { /* ignore */ }
}

export async function speak(text: string, lang: TourLang): Promise<SpeakOutcome> {
  const picked = await tourVoice(lang);
  if (!picked) return "no-voice";
  let voice = picked.voice;
  if (picked.neural) {
    // R16 v: the neural line; if the add-on is absent, the browser's best male voice for the language reads it.
    const o = await speakNeural(text, picked.neural.id, picked.neural.lang, picked.rate);
    if (o === "ended") return "ended";
    if (o === "stopped") return "cancelled";
    if (o === "failed") return "blocked";
    voice = suggestVoice(await loadVoices(), lang === "ar" ? "ar-gulf" : "en").voice;
    if (!voice) return "no-voice";
  }
  const s = synth();
  if (!s) return "unsupported";
  if (!voice) return "no-voice";
  const v = voice;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    ours.add(u);
    u.voice = v;
    u.lang = v.lang;
    u.rate = picked.rate;
    u.pitch = picked.pitch;
    let settled = false;
    const end = (o: SpeakOutcome) => { if (!settled) { settled = true; resolve(o); } };
    u.onend = () => end("ended");
    u.onerror = (e) => end(e.error === "interrupted" || e.error === "canceled" ? "cancelled" : "blocked");
    try {
      realCancel();
      s.speak(u);
    } catch {
      end("blocked");
    }
  });
}
