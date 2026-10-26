/**
 * R16 v: Noor's human-sounding voice, the offline neural add-on on the Deal Desk service (`/api/v1/voice`,
 * backend/agents_v5/voice): Kokoro for English, Piper (ar_JO Kareem) for Arabic. The text goes only to this computer's
 * own backend; nothing leaves the machine.
 *
 * `speakNeural` is reached only from a click (R16 M1): noor-voice.ts `speakText` (the store's `say`, itself called only
 * from speaker clicks), the tour's `speak` (after "Play with voice") and the sampler's Listen buttons. It fetches the WAV
 * (cached by text hash on the server, and as an object URL here) and plays it in one shared <audio>; a new line stops
 * the one playing. When the add-on is absent it resolves "absent" and the caller reads with the browser's voice and
 * says so (`NEURAL_ABSENT_NOTE`).
 *
 * Pure parts (`neuralSpeed`, `neuralCandidates`, `neuralLabel`, `neuralKey`) are tested in neural-voice.test.ts.
 */

export type NeuralGroup = "en" | "ar-gulf";

export interface NeuralVoice {
  /** R16 v2: "azure" is the optional cloud provider (ids `azure:<ShortName>`), off unless the service has its key. */
  id: string; engine: "kokoro" | "piper" | "azure"; name: string; lang: string; group: NeuralGroup; gender: "male" | "female";
  accent: string; note: string; installed?: boolean;
  /** R16 v2: "offline" (on this computer) or "cloud" (the text leaves the machine); `why` says why it cannot play here. */
  where?: "offline" | "cloud"; label?: string; why?: string | null;
}

/** R16 v2: the optional cloud provider (no key is ever sent to the browser). */
export interface CloudStatus { provider: string; configured: boolean; region: string | null; label: string; why: string | null; how_to_enable?: string }

export interface NeuralStatus {
  available: boolean; engines: { kokoro: boolean; piper: boolean; azure?: boolean }; missing: string[]; voices: NeuralVoice[];
  /** false when the backend could not be reached (not the same as "not installed"). */
  reached: boolean;
  cloud?: CloudStatus;
  /** R16 v2: per regional locale (ar-SA, ar-AE, en-IN), why no offline neural voice exists. */
  offline_catalogue?: Record<string, string>;
}

export const CLOUD_LABEL = "Cloud – text leaves the machine; demo with fictional data only";
export const CLOUD_OFF_NOTE = "The cloud voice is not available here (it is off unless the Deal Desk service has CP_TTS_CLOUD_KEY and CP_TTS_CLOUD_REGION), so the browser's voice is reading. Settings → Voice";

/** R16 v2: a cloud voice (its text leaves the machine), by row or by chosen id. */
export function isCloudVoice(v: Pick<NeuralVoice, "id"> & { where?: string } | string | null | undefined): boolean {
  if (!v) return false;
  if (typeof v === "string") return v.startsWith("azure:");
  return v.where === "cloud" || v.id.startsWith("azure:");
}

export type NeuralOutcome = "ended" | "stopped" | "absent" | "failed";

export const NEURAL_ABSENT_NOTE = "The neural voice add-on is not installed here, so the browser's voice is reading. Install it with ops/r16_install_tts.sh (Settings → Voice)";
export const NEURAL_INSTALL_HINT = "Run ops/r16_install_tts.sh on this computer (offline: wheels in vendor/wheels, models from the Mac pack), then restart the Deal Desk service.";

const UNAVAILABLE: NeuralStatus = { available: false, engines: { kokoro: false, piper: false }, missing: [], voices: [], reached: false };

function origin(): string {
  return (process.env.NEXT_PUBLIC_DEALDESK_API ?? "http://127.0.0.1:8508").replace(/\/$/, "");
}

/** The browser rate (0.5–1.5, 0.92 by default) as the neural speed. Same scale, bounded; 2 decimals (the cache key). */
export function neuralSpeed(rate: number | null | undefined): number {
  const r = Number.isFinite(Number(rate)) ? Number(rate) : 1;
  return Math.round(Math.min(1.5, Math.max(0.5, r)) * 100) / 100;
}

/** The sampler's OFFLINE neural rows for a language (R16 v2: cloud voices are in the regional tables, not here): male first (Anne asked for a calm male voice), then female, by name order kept. */
export function neuralCandidates(voices: readonly NeuralVoice[], group: NeuralGroup): NeuralVoice[] {
  const rank = (v: NeuralVoice) => (v.gender === "male" ? 0 : 1);
  return voices.filter((v) => v.group === group && !isCloudVoice(v)).map((v, i) => ({ v, i }))
    .sort((a, b) => rank(a.v) - rank(b.v) || a.i - b.i).map((x) => x.v);
}

export function neuralLabel(v: Pick<NeuralVoice, "name" | "accent" | "engine">): string {
  if (v.engine === "azure") return `${v.name} (${v.accent}, cloud – Azure neural)`;
  return `${v.name} (${v.accent}, ${v.engine === "piper" ? "Piper" : "Kokoro"} neural)`;
}

export function neuralKey(text: string, voice: string, speed: number): string {
  return `${voice}|${speed.toFixed(2)}|${text}`;
}

// ---------------------------------------------------------------- the backend

let cachedStatus: NeuralStatus | null = null;
let statusAt = 0;

/** What the add-on has (cached for a minute). Never throws: an unreachable backend is "not available". */
export async function neuralStatus(force = false): Promise<NeuralStatus> {
  if (!force && cachedStatus && Date.now() - statusAt < 60_000) return cachedStatus;
  try {
    const r = await fetch(`${origin()}/api/v1/voice/status`, { credentials: "include", cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    const b = await r.json() as Partial<NeuralStatus>;
    cachedStatus = { available: Boolean(b.available),
                     engines: { kokoro: Boolean(b.engines?.kokoro), piper: Boolean(b.engines?.piper), azure: Boolean(b.engines?.azure) },
                     missing: Array.isArray(b.missing) ? b.missing.map(String) : [],
                     voices: Array.isArray(b.voices) ? b.voices as NeuralVoice[] : [], reached: true,
                     ...(b.cloud && typeof b.cloud === "object" ? { cloud: b.cloud } : {}),
                     ...(b.offline_catalogue && typeof b.offline_catalogue === "object" ? { offline_catalogue: b.offline_catalogue } : {}) };
  } catch {
    cachedStatus = { ...UNAVAILABLE };
  }
  statusAt = Date.now();
  return cachedStatus;
}

export function forgetNeuralStatus(): void { cachedStatus = null; }

// ---------------------------------------------------------------- playing (one line at a time)

const urls = new Map<string, string>();
let audio: HTMLAudioElement | null = null;
let finish: ((o: NeuralOutcome) => void) | null = null;
let ticket = 0;

export function neuralPlaying(): boolean { return Boolean(audio && !audio.paused && !audio.ended); }

/** Stop the line playing (its promise resolves "stopped"). */
export function stopNeural(): void {
  ticket += 1;
  const f = finish;
  finish = null;
  try { audio?.pause(); } catch { /* ignore */ }
  f?.("stopped");
}

/** The pause between two chunks of a long line (the server ends each chunk without one). */
export const CHUNK_GAP_MS = 320;
const CHUNK_CHARS = 260;

/**
 * A long line in chunks, so the first words sound quickly while the rest is made: the first chunk is one sentence,
 * then sentences are grouped up to ~260 characters, never across a paragraph. A sentence ends at . ! ? ؟ followed by a space and not a digit
 * ("1.48 bn" stays whole), or at a new line.
 */
export function chunkText(text: string): string[] {
  const out: string[] = [];
  for (const para of String(text ?? "").split(/\n+/)) {
    const sentences = para.split(/(?<=[.!?؟]["”’)]?)\s+(?=[^\d\s])/).map((x) => x.trim()).filter(Boolean);
    let open = false;   // a paragraph starts a new chunk; the line's first chunk stays one sentence
    for (const one of sentences) {
      const last = out[out.length - 1];
      if (open && out.length > 1 && last.length + one.length + 1 <= CHUNK_CHARS) out[out.length - 1] = `${last} ${one}`;
      else out.push(one);
      open = true;
    }
  }
  return out;
}

async function fetchChunk(text: string, voice: string, lang: string, spd: number): Promise<string | "absent" | "failed"> {
  const key = neuralKey(text, voice, spd);
  const have = urls.get(key);
  if (have) return have;
  let r: Response;
  try {
    r = await fetch(`${origin()}/api/v1/voice/speak`, {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, lang, speed: spd }),
    });
  } catch {
    return "absent";   // the backend is not reachable: the browser's voice reads
  }
  if (r.status === 503) { forgetNeuralStatus(); return "absent"; }
  if (!r.ok) return "failed";
  const url = URL.createObjectURL(await r.blob());
  urls.set(key, url);
  if (urls.size > 80) {   // keep the newest lines only
    const [oldKey, oldUrl] = urls.entries().next().value as [string, string];
    URL.revokeObjectURL(oldUrl);
    urls.delete(oldKey);
  }
  return url;
}

function playUrl(url: string, onStart: () => void): Promise<NeuralOutcome> {
  audio = audio ?? new Audio();
  const a = audio;
  return new Promise<NeuralOutcome>((resolve) => {
    let done = false;
    const end = (o: NeuralOutcome) => { if (done) return; done = true; if (finish === end) finish = null; resolve(o); };
    finish = end;
    a.onplaying = onStart;
    a.onended = () => end("ended");
    a.onerror = () => end("failed");
    a.src = url;
    a.currentTime = 0;
    a.play().catch(() => end("failed"));
  });
}

/**
 * Say `text` with the neural voice `voice` at `speed` (from a click only). Resolves when the line ends ("ended"), is
 * stopped ("stopped"), when the add-on is not installed ("absent": the caller falls back to the browser's voice) or on
 * any other error ("failed"). `on.start` fires once, when sound starts; `on.end` once, when it is over. A long line is
 * played chunk by chunk (`chunkText`), the next chunk made while the current one plays.
 */
export async function speakNeural(text: string, voice: string, lang: string, speed: number,
                                  on: { start?: () => void; end?: () => void } = {}): Promise<NeuralOutcome> {
  stopNeural();
  const mine = ++ticket;
  if (typeof window === "undefined" || typeof Audio === "undefined") return "failed";
  const spd = neuralSpeed(speed);
  const chunks = chunkText(text);
  if (!chunks.length) return "failed";
  let started = false;
  const start = () => { if (!started) { started = true; on.start?.(); } };
  const over = (o: NeuralOutcome) => { if (started) on.end?.(); return o; };
  let next: Promise<string | "absent" | "failed"> = fetchChunk(chunks[0], voice, lang, spd);
  for (let i = 0; i < chunks.length; i++) {
    const url = await next;
    if (mine !== ticket) return over("stopped");   // another click came in while this chunk was being made
    if (url === "absent") return over(started ? "failed" : "absent");
    if (url === "failed") return over("failed");
    if (i + 1 < chunks.length) next = fetchChunk(chunks[i + 1], voice, lang, spd);
    const o = await playUrl(url, start);
    if (o !== "ended") return over(o);
    if (i + 1 < chunks.length) {
      await new Promise((ok) => setTimeout(ok, CHUNK_GAP_MS));
      if (mine !== ticket) return over("stopped");
    }
  }
  return over("ended");
}
