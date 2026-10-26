/**
 * Ask by voice (R14 n, K10). Push-to-talk on the browser's speech recogniser (Web Speech API): press the mic, speak,
 * press again (or pause) and the transcript lands in the box, never sent until the reader presses Ask. English (en-US)
 * or Arabic (ar-SA), following the reader's voice language.
 *
 * Privacy, said on the control: in Chrome the audio is processed by the browser's speech service (Google's servers).
 * The bank deployment replaces this with offline speech-to-text on the server (Whisper); see docs/STATUS_R14_N.md.
 *
 * `micLang`, `joinTranscript` and `micLabel` are pure (noor-mic.test.ts); `startListening` touches the browser.
 */

export type MicState = "unsupported" | "idle" | "listening" | "denied" | "error";

export const MIC_PRIVACY = "Audio is processed by the browser's speech service.";

export function micLang(voiceLanguage: "en" | "ar-gulf" | string): string {
  return voiceLanguage === "ar-gulf" ? "ar-SA" : "en-US";
}

/** What is already typed plus what was heard, one space between. */
export function joinTranscript(typed: string, heard: string): string {
  const a = String(typed ?? "").trimEnd();
  const b = String(heard ?? "").trim();
  if (!b) return a;
  return a ? `${a} ${b}` : b;
}

export function micLabel(state: MicState, lang: string): string {
  const language = lang.startsWith("ar") ? "Arabic" : "English";
  switch (state) {
    case "unsupported": return "Voice input is not available in this browser. Type the question instead.";
    case "listening": return `Listening (${language}). Press again to stop. ${MIC_PRIVACY}`;
    case "denied": return "The microphone is blocked for this site. Allow it in the browser's site settings.";
    case "error": return `Could not hear that. Press to try again. ${MIC_PRIVACY}`;
    default: return `Ask by voice (${language}): press, speak, press again. ${MIC_PRIVACY}`;
  }
}

interface RecognitionLike {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
}

function ctor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => RecognitionLike; webkitSpeechRecognition?: new () => RecognitionLike };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function micSupported(): boolean { return ctor() !== null; }

/**
 * Start listening. `onText(interim, final)` is called as words arrive; `onState` reports listening / idle / errors.
 * Returns a stop function.
 */
export function startListening(lang: string, on: {
  onText: (text: string, final: boolean) => void; onState: (s: MicState) => void;
}): () => void {
  const C = ctor();
  if (!C) { on.onState("unsupported"); return () => undefined; }
  const r = new C();
  r.lang = lang;
  r.continuous = false;
  r.interimResults = true;
  r.maxAlternatives = 1;
  let finalText = "";
  r.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) finalText += res[0].transcript;
      else interim += res[0].transcript;
    }
    on.onText((finalText + interim).trim(), !interim);
  };
  r.onerror = (e) => on.onState(e.error === "not-allowed" || e.error === "service-not-allowed" ? "denied" : "error");
  r.onend = () => on.onState("idle");
  try {
    r.start();
    on.onState("listening");
  } catch {
    on.onState("error");
  }
  return () => { try { r.stop(); } catch { /* ignore */ } };
}
