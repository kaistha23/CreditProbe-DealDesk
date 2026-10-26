/**
 * Noor's voice (R12_FEEDBACK J1, R14 K10, R15 L2, R16 M1).
 *
 * R16 M1 ("Voice is bad; it speaks on login"): Noor NEVER speaks on its own. There is no automatic speech on sign-in,
 * on a brief loading, on the panel opening, on an answer arriving or in the tour: speech starts only from a click on a
 * speaker / Listen control, in that moment. And it speaks only with the voice chosen in Settings -> Voice for the
 * language: with no voice chosen (or the chosen one not on this computer) a click stays silent and the reader is told
 * "Choose a voice in Settings -> Voice". No interim or random voice is ever picked.
 *
 * Chrome returns no voices until `voiceschanged` fires: `loadVoices` waits for it (with a timeout).
 *
 * `pickVoice`, `suggestVoice` and `voiceStateFor` are pure (noor-voice.test.ts); the rest touches
 * `window.speechSynthesis`.
 */

import { CLOUD_OFF_NOTE, NEURAL_ABSENT_NOTE, isCloudVoice, speakNeural, stopNeural } from "./neural-voice.ts";
import { type ChosenVoice, isNeural, resolveChosen } from "./voice-choice.ts";

export type VoiceLanguage = "en" | "ar-gulf";
/** R14 n (K10): Noor speaks with a male voice only. */
export type VoiceGender = "male";

export interface VoiceLike { name: string; lang: string; default?: boolean; localService?: boolean }

/** What the speaker button shows. */
export type VoiceState =
  | "unsupported"   // this browser has no speech synthesis
  | "loading"       // waiting for the browser's voices
  | "no-voice"      // speech synthesis exists but no voice is installed
  | "not-chosen"    // R16 M1: no voice chosen in Settings -> Voice for the language (or not on this computer): silent
  | "fallback"      // kept for older callers; pickVoice no longer falls back to another voice
  | "ready"
  | "speaking";

export function voiceLang(lang: VoiceLanguage): string {
  return lang === "ar-gulf" ? "ar-SA" : "en-GB";
}

const FEMALE = /female|woman|samantha|laila|serena|kate|moira|susan|karen|tessa|victoria|fiona|zira|hazel|libby|sonia|mariam|zariyah|hoda|salma|amira|ava|allison|zoe|nicky|joelle|noelle|kathy|vicki|princess|shelley|sandy|flo|grandma|majed_f|google us english|google uk english female/i;
const MALE = /\bmale\b|\bman\b|evan|nathan|daniel|maged|majed|tarik|george|arthur|david|mark|ryan|thomas|fred|alex|aaron|tom|oliver|lee|rishi|hamed|naayf|shakir|google uk english male/i;

/**
 * R14 n (K10), kept by R16 M1 only to ORDER the sampler's list (`suggestVoice`), never to pick a voice to speak. The order Anne chose on the Mac: English Evan, Nathan, Daniel (Enhanced or
 * Premium before the plain voice of the same name); Arabic Maged. Then any other voice whose name says male, then a
 * voice whose name says nothing about gender. A female voice is never suggested.
 */
export const PREFERRED: Record<VoiceLanguage, RegExp[]> = {
  "en": [/^evan\b/i, /^nathan\b/i, /^daniel\b/i],
  "ar-gulf": [/^maged\b/i, /^majed\b/i],
};

export const VOICE_RATE = 0.92;
export const VOICE_PITCH = 0.9;

function quality(name: string): number {
  return /premium/i.test(name) ? 2 : /enhanced/i.test(name) ? 1 : 0;
}

export function isFemaleVoice(name: string): boolean {
  return FEMALE.test(name) && !MALE.test(name.replace(/female/i, ""));
}

/**
 * R16 M1: the voice to speak with is the one chosen in Settings -> Voice for the language, and only that one. With no
 * choice (`notChosen`), or a choice this computer does not have (`notChosen` and `missing`), the voice is null and Noor
 * stays silent: no interim, random or fallback voice.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function pickVoice<V extends VoiceLike>(voices: readonly V[], _lang: VoiceLanguage, _gender: VoiceGender = "male",
                                              chosen: ChosenVoice | null = null):
    { voice: V | null; fallback: boolean; chosen?: boolean; notChosen?: boolean; missing?: boolean; neural?: boolean } {
  // R16 v: a neural voice (the offline add-on) is chosen even when the browser has no voice at all.
  if (isNeural(chosen)) return { voice: null, fallback: false, chosen: true, neural: true };
  if (!voices.length) return { voice: null, fallback: false };
  const mine = resolveChosen(voices, chosen);
  if (mine) return { voice: mine, fallback: false, chosen: true };
  return { voice: null, fallback: false, notChosen: true, ...(chosen ? { missing: true } : {}) };
}

/**
 * The male-first suggestion (R14 K10 order: Evan, Nathan, Daniel; Arabic Maged), used ONLY to order the sampler's list
 * in Settings -> Voice (`rankSuggested`). Never female. Same language first; preferred names in order,
 * Enhanced/Premium before plain, then other male voices, then voices of unknown gender, local before network. If the
 * language has no allowed voice: another language's allowed voice (fallback). Null when no male or neutral voice exists.
 */
export function suggestVoice<V extends VoiceLike>(voices: readonly V[], lang: VoiceLanguage):
    { voice: V | null; fallback: boolean; noMale?: boolean } {
  if (!voices.length) return { voice: null, fallback: false };
  const allowed = voices.filter((v) => !isFemaleVoice(v.name));
  if (!allowed.length) return { voice: null, fallback: false, noMale: true };
  const want = voiceLang(lang).toLowerCase();
  const base = want.slice(0, 2);
  const norm = (v: V) => v.lang.toLowerCase().replace("_", "-");
  const best = (pool: V[]) => [...pool].sort((a, b) => suggestScore(b, lang) - suggestScore(a, lang) || a.name.localeCompare(b.name))[0];
  const sameLang = allowed.filter((v) => norm(v).startsWith(base));
  if (sameLang.length) return { voice: best(sameLang), fallback: false };
  const en = allowed.filter((v) => norm(v).startsWith("en"));
  return { voice: best(en.length ? en : allowed), fallback: true };
}

/** The K10 preference score of one voice (higher first); female voices score below everything. */
export function suggestScore(v: VoiceLike, lang: VoiceLanguage): number {
  if (isFemaleVoice(v.name)) return -1;
  const want = voiceLang(lang).toLowerCase();
  const p = PREFERRED[lang].findIndex((re) => re.test(v.name));
  return (p >= 0 ? 100 - p * 10 + quality(v.name) * 3 : 0) + (MALE.test(v.name) ? 5 : 0)
    + (v.lang.toLowerCase().replace("_", "-") === want ? 2 : 0) + (v.localService ? 1 : 0);
}

export function voiceStateFor(supported: boolean, loaded: boolean, count: number, fallback: boolean,
                              speaking: boolean, notChosen = false): VoiceState {
  if (!supported) return "unsupported";
  if (!loaded) return "loading";
  if (!count) return "no-voice";
  if (notChosen) return "not-chosen";
  if (speaking) return "speaking";
  return fallback ? "fallback" : "ready";
}

/** What the speaker button says about the state (its tooltip and the line under it when something is wrong). */
export function voiceStateLabel(state: VoiceState, on: boolean, lang: VoiceLanguage): string {
  const language = lang === "ar-gulf" ? "Arabic" : "English";
  switch (state) {
    case "unsupported": return "This browser cannot read aloud.";
    case "loading": return "Getting the browser's voices ready…";
    case "no-voice": return "No voice is installed on this computer. Add one in the system's speech settings to hear Noor.";
    case "not-chosen": return CHOOSE_VOICE_NOTE;
    case "fallback": return on ? `No ${language} voice is installed; reading with another voice. Stop reading` : `Read aloud (no ${language} voice installed; another voice reads)`;
    case "speaking": return "Stop reading";
    default: return on ? "Read the brief aloud" : "Read the brief aloud (only when you press this)";
  }
}

/** R16 M1: the short note a speaker click shows when no voice is chosen for the language. */
export const CHOOSE_VOICE_NOTE = "Choose a voice in Settings → Voice";
export const VOICE_SETTINGS_HREF = "/settings/voice";

// ---------------------------------------------------------------- the reader's choice, kept

export interface VoicePref { on: boolean | null; language: VoiceLanguage | null }

const KEY = (user: string) => `noor.voice.${user || "anon"}`;

export function readPref(user: string): VoicePref {
  try {
    const raw = window.localStorage.getItem(KEY(user));
    if (!raw) return { on: null, language: null };
    const v = JSON.parse(raw) as Partial<VoicePref>;
    return { on: typeof v.on === "boolean" ? v.on : null,
             language: v.language === "en" || v.language === "ar-gulf" ? v.language : null };
  } catch {
    return { on: null, language: null };
  }
}

export function writePref(user: string, pref: VoicePref): void {
  try { window.localStorage.setItem(KEY(user), JSON.stringify(pref)); } catch { /* a browser without storage forgets */ }
}

/** The effective setting: the reader's own choice when they made one, else the bank's default. */
export function effectiveVoice(pref: VoicePref, bank: { enabled: boolean; language: VoiceLanguage }):
    { on: boolean; language: VoiceLanguage } {
  return { on: pref.on ?? bank.enabled, language: pref.language ?? bank.language };
}

// ---------------------------------------------------------------- the browser's speech

type Synth = SpeechSynthesis;

function synth(): Synth | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  return window.speechSynthesis;
}

export function speechSupported(): boolean {
  return synth() !== null && typeof window !== "undefined" && "SpeechSynthesisUtterance" in window;
}

let cached: SpeechSynthesisVoice[] = [];
let loadedOnce = false;

/** The installed voices, waiting for `voiceschanged` (Chrome fills the list late) up to `timeoutMs`. */
export function loadVoices(timeoutMs = 2500): Promise<SpeechSynthesisVoice[]> {
  const s = synth();
  if (!s) return Promise.resolve([]);
  const now = s.getVoices();
  if (now.length) { cached = now; loadedOnce = true; return Promise.resolve(now); }
  return new Promise((ok) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      s.removeEventListener?.("voiceschanged", onChange);
      cached = s.getVoices();
      loadedOnce = true;
      ok(cached);
    };
    const onChange = () => { if (s.getVoices().length) finish(); };
    s.addEventListener?.("voiceschanged", onChange);
    // Some browsers (Safari) never fire the event but fill the list after a tick; poll a little as well.
    let tries = 0;
    const poll = () => { if (done) return; if (s.getVoices().length || tries++ > timeoutMs / 250) finish(); else setTimeout(poll, 250); };
    setTimeout(poll, 250);
  });
}

export function voicesLoaded(): boolean { return loadedOnce; }
export function knownVoices(): SpeechSynthesisVoice[] { return cached; }

/**
 * Speak `text` with the chosen voice (a browser voice, or R16 v's offline neural voice). Call ONLY from a click handler (R16 M1). Resolves to what happened, so the
 * button can show it: "not-chosen" when no voice is chosen for the language (nothing is spoken).
 */
export async function speakText(text: string, lang: VoiceLanguage, gender: VoiceGender = "male",
                                on: { start?: () => void; end?: () => void } = {}, choice: ChosenVoice | null = null):
    Promise<{ spoken: boolean; state: VoiceState; voice: string; note?: string }> {
  // R16 v: the chosen neural voice (the offline add-on on this computer). If the add-on is absent, the browser's
  // best male voice for the language reads instead, and the caller shows NEURAL_ABSENT_NOTE.
  if (isNeural(choice)) {
    stopSpeech();
    let started = false;
    const outcome = await speakNeural(text, choice.name, choice.lang, choice.rate, {
      start: () => { started = true; on.start?.(); }, end: () => { if (started) on.end?.(); },
    });
    if (outcome !== "absent") {
      return outcome === "failed" && !started ? { spoken: false, state: "ready", voice: choice.name }
        : { spoken: true, state: "ready", voice: choice.name };
    }
    // R16 v2: a chosen cloud voice that is off here (no key) says so instead.
    const note = isCloudVoice(choice.name) ? CLOUD_OFF_NOTE : NEURAL_ABSENT_NOTE;
    const s0 = synth();
    if (!s0 || !speechSupported()) return { spoken: false, state: "unsupported", voice: "", note };
    const pool = cached.length ? cached : await loadVoices();
    const stand = suggestVoice(pool, lang).voice;
    if (!stand) return { spoken: false, state: "no-voice", voice: "", note };
    return { ...browserSay(s0, text, stand, choice.rate, VOICE_PITCH, on), note };
  }
  const s = synth();
  if (!s || !speechSupported()) return { spoken: false, state: "unsupported", voice: "" };
  // Chrome: cancel() then speak() in the same tick can drop the utterance; resume() unsticks a paused queue.
  s.cancel();
  stopNeural();
  const voices = cached.length ? cached : await loadVoices();
  if (!voices.length) return { spoken: false, state: "no-voice", voice: "" };
  const { voice } = pickVoice(voices, lang, gender, choice);
  // R16 M1: no chosen voice, no speech (never a random or interim voice).
  if (!voice || !choice) return { spoken: false, state: "not-chosen", voice: "" };
  // The chosen voice's own rate and pitch (L2).
  return browserSay(s, text, voice, choice.rate, choice.pitch, on);
}

function browserSay(s: Synth, text: string, voice: SpeechSynthesisVoice, rate: number, pitch: number,
                    on: { start?: () => void; end?: () => void }): { spoken: boolean; state: VoiceState; voice: string } {
  const u = new SpeechSynthesisUtterance(text);
  u.lang = voice.lang;
  u.voice = voice;
  u.rate = rate;
  u.pitch = pitch;
  u.onstart = () => on.start?.();
  u.onend = () => on.end?.();
  u.onerror = () => on.end?.();
  try { s.resume(); } catch { /* ignore */ }
  s.speak(u);
  return { spoken: true, state: "speaking", voice: voice.name };
}

export function stopSpeech(): void {
  try { synth()?.cancel(); } catch { /* ignore */ }
  stopNeural();
}
