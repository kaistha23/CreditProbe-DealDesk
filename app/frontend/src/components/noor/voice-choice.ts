/**
 * R15 a (L2): the voice buffet's pure model and the chosen voice, one per language.
 *
 * Settings → Voice lists every voice this computer exposes to the browser (Mac system voices, with Enhanced, Premium
 * and Siri voices where the system exposes them; Edge's "Online (Natural)" neural voices; Google voices), male and
 * female, English (en-GB, en-US, en-AU, en-IE, en-IN, …) and Arabic (ar-SA, ar-*), best first; each reads the same lines of
 * a real brief. R16 v: the offline neural voices (Kokoro for English, Piper for Arabic, the add-on on this computer)
 * are listed beside them and play through /api/v1/voice; cloud neural voices are listed as options only, never played. The voice Anne chooses per language (with its rate and pitch) becomes the
 * bank's default (`voice.chosen` in Noor's settings) and is used by Noor and the tour. R16 M1: until a voice is
 * chosen for a language Noor and the tour stay SILENT in it (no interim voice) and say "Choose a voice in Settings → Voice".
 *
 * Pure (node --test: voice-choice.test.ts), except `readChosen` / `writeChosen` (localStorage, so the tour, which does
 * not load Noor's settings, reads the same choice).
 */

export type ChoiceLang = "en" | "ar-gulf";
export const CHOICE_LANGS: ChoiceLang[] = ["en", "ar-gulf"];

export interface ChosenVoice {
  name: string; lang: string; rate: number; pitch: number; chosen_by?: string; chosen_at?: string;
  /** R16 v: "neural" = the offline neural add-on (`name` is its voice id, e.g. am_michael); absent = a browser voice. */
  engine?: "neural"; label?: string;
}

/** R16 v: the choice is an offline neural voice (Kokoro / Piper on this computer), not a browser voice. */
export function isNeural(c: ChosenVoice | null | undefined): c is ChosenVoice & { engine: "neural" } {
  return Boolean(c && c.engine === "neural");
}
export type Chosen = Record<ChoiceLang, ChosenVoice | null>;

export const NO_CHOICE: Chosen = { "en": null, "ar-gulf": null };
export const RATE = { min: 0.5, max: 1.5, step: 0.02, start: 0.92 } as const;
export const PITCH = { min: 0.5, max: 1.5, step: 0.02, start: 0.9 } as const;

export interface VoiceLike { name: string; lang: string; localService?: boolean; default?: boolean; voiceURI?: string }

export type Gender = "male" | "female" | "unknown";
/** R16 M1: best first — Premium > Enhanced > Siri > Natural/Neural (e.g. Edge "Online (Natural)") > Google > plain. */
export type Quality = "premium" | "enhanced" | "siri" | "natural" | "google" | "standard";

/** Names the Mac (and Chrome, Windows, Android) use, by the voice's gender. A name not here is "unknown". */
const FEMALE_NAMES = /\b(female|woman|samantha|serena|kate|moira|susan|karen|tessa|victoria|fiona|zira|hazel|libby|sonia|mariam|zariyah|hoda|salma|amira|allison|ava|zoe|nicky|joelle|noelle|kathy|vicki|princess|shelley|sandy|flo|grandma|laila|lana|mona|amina|zeina|isha|veena|catherine|martha|kathy|stephanie|jenny|aria|emma|libby|maisie|nora|siri voice 2|siri voice 4)\b/i;
const MALE_NAMES = /\b(male|man|evan|nathan|daniel|maged|majed|tarik|george|arthur|david|mark|ryan|thomas|fred|alex|aaron|tom|oliver|lee|rishi|hamed|naayf|shakir|gordon|reed|rocko|eddy|grandpa|ralph|junior|albert|jamie|guy|christopher|siri voice 1|siri voice 3)\b/i;

export function genderOf(name: string): Gender {
  const n = name.replace(/\(.*?\)/g, " ");
  if (/\bfemale\b/i.test(n)) return "female";
  if (/\bmale\b/i.test(n)) return "male";
  const f = FEMALE_NAMES.test(n);
  const m = MALE_NAMES.test(n);
  return f && !m ? "female" : m && !f ? "male" : "unknown";
}

export function qualityOf(name: string): Quality {
  if (/premium/i.test(name)) return "premium";
  if (/enhanced/i.test(name)) return "enhanced";
  if (/\bsiri\b/i.test(name)) return "siri";
  if (/\b(natural|neural)\b/i.test(name)) return "natural";
  if (/^google\b/i.test(name.trim())) return "google";
  return "standard";
}

export const QUALITY_LABEL: Record<Quality, string> = {
  premium: "Premium", enhanced: "Enhanced", siri: "Siri", natural: "Natural (neural)", google: "Google", standard: "Standard",
};

export const QUALITY_RANK: Record<Quality, number> = { premium: 0, enhanced: 1, siri: 2, natural: 3, google: 4, standard: 5 };

/** R14 K10's male-first names, kept by R16 M1 only to order voices of the same quality in the list (never to pick). */
const SUGGESTED: Record<ChoiceLang, RegExp[]> = { "en": [/^evan\b/i, /^nathan\b/i, /^daniel\b/i], "ar-gulf": [/^maged\b/i, /^majed\b/i] };
const GENDER_RANK: Record<Gender, number> = { male: 0, unknown: 1, female: 2 };

function suggestedRank(c: { name: string; group: ChoiceLang }): number {
  const i = SUGGESTED[c.group].findIndex((re) => re.test(c.name));
  return i < 0 ? 9 : i;
}

export function langGroup(lang: string): ChoiceLang | null {
  const l = lang.toLowerCase().replace("_", "-");
  if (l.startsWith("en")) return "en";
  if (l.startsWith("ar")) return "ar-gulf";
  return null;
}

export interface Candidate {
  name: string; lang: string; group: ChoiceLang; gender: Gender; quality: Quality; local: boolean;
  /** Where it comes from, in plain words. */
  source: string;
}

/**
 * The installed voices worth listening to: English and Arabic only, best first. Order: quality (Premium, Enhanced,
 * Siri, Natural/Neural, Google, plain), then the K10 suggested male names (Evan, Nathan, Daniel; Maged, Majed), then
 * male / not stated / female, then on this computer before network, then region (en-GB, en-US, en-AU/IE/IN; ar-SA),
 * then name.
 */
export function candidates(voices: readonly VoiceLike[]): Record<ChoiceLang, Candidate[]> {
  const out: Record<ChoiceLang, Candidate[]> = { "en": [], "ar-gulf": [] };
  const seen = new Set<string>();
  for (const v of voices) {
    const group = langGroup(v.lang);
    if (!group || seen.has(`${v.name}|${v.lang}`)) continue;
    seen.add(`${v.name}|${v.lang}`);
    const local = v.localService !== false;
    out[group].push({ name: v.name, lang: v.lang, group, gender: genderOf(v.name), quality: qualityOf(v.name), local,
                      source: local ? "On this computer (system voice)" : "Browser's network voice (text goes to the browser maker)" });
  }
  const rankLang = (c: Candidate) => {
    const l = c.lang.toLowerCase().replace("_", "-");
    if (c.group === "ar-gulf") return l.startsWith("ar-sa") ? 0 : /^ar-(ae|kw|qa|bh|om)/.test(l) ? 1 : 2;
    return l.startsWith("en-gb") ? 0 : l.startsWith("en-us") ? 1 : /^en-(au|ie|in)/.test(l) ? 2 : 3;
  };
  for (const g of CHOICE_LANGS) {
    out[g].sort((a, b) => QUALITY_RANK[a.quality] - QUALITY_RANK[b.quality] || suggestedRank(a) - suggestedRank(b)
      || GENDER_RANK[a.gender] - GENDER_RANK[b.gender] || Number(b.local) - Number(a.local)
      || rankLang(a) - rankLang(b) || a.name.localeCompare(b.name));
  }
  return out;
}

/** Mac voices that sound natural but are often not downloaded yet (System Settings → Accessibility → Spoken Content →
 *  System voice → Manage Voices). Listed only when missing from this computer. */
export const MAC_DOWNLOADS: { name: string; group: ChoiceLang; gender: Gender; quality: Quality }[] = [
  { name: "Evan (Enhanced)", group: "en", gender: "male", quality: "enhanced" },
  { name: "Nathan (Enhanced)", group: "en", gender: "male", quality: "enhanced" },
  { name: "Daniel (Enhanced)", group: "en", gender: "male", quality: "enhanced" },
  { name: "Jamie (Premium)", group: "en", gender: "male", quality: "premium" },
  { name: "Lee (Premium)", group: "en", gender: "male", quality: "premium" },
  { name: "Zoe (Premium)", group: "en", gender: "female", quality: "premium" },
  { name: "Ava (Premium)", group: "en", gender: "female", quality: "premium" },
  { name: "Serena (Premium)", group: "en", gender: "female", quality: "premium" },
  { name: "Majed (Enhanced)", group: "ar-gulf", gender: "male", quality: "enhanced" },
  { name: "Maged", group: "ar-gulf", gender: "male", quality: "standard" },
  { name: "Mariam (Enhanced)", group: "ar-gulf", gender: "female", quality: "enhanced" },
];

/** Voices to download that this computer does not have (by the name before the bracket, any region). */
export function missingDownloads(voices: readonly VoiceLike[]): typeof MAC_DOWNLOADS {
  const have = new Set(voices.map((v) => v.name.toLowerCase()));
  const base = (n: string) => n.replace(/\s*\(.*\)\s*$/, "").toLowerCase();
  const haveBase = new Set(voices.filter((v) => qualityOf(v.name) === "standard").map((v) => base(v.name)));
  return MAC_DOWNLOADS.filter((d) => !have.has(d.name.toLowerCase()) && !(d.quality === "standard" && haveBase.has(base(d.name))));
}

export interface OtherOption { id: string; name: string; group: ChoiceLang; gender: Gender; kind: "offline" | "cloud"; note: string }

/** Options that are NOT set up: listed so Anne can weigh them, never played or used here. R16 v: the offline neural
 *  voices (Kokoro, Piper) are no longer here: they are real, listed and playable in their own table (neural-voice.ts).
 *  R16 v2: the Saudi Arabic cloud voices are no longer here either: they are rows in the regional tables
 *  (voice-regions.ts), playable when the optional cloud provider is configured. */
export const OTHER_OPTIONS: OtherOption[] = [
  { id: "cloud-en-neural-m", name: "Cloud neural English, male (e.g. en-GB Ryan Neural)", group: "en", gender: "male", kind: "cloud",
    note: "Cloud neural voice: sends the text out of the bank to a speech service. Demo use only; not set up." },
  { id: "cloud-en-neural-f", name: "Cloud neural English, female (e.g. en-GB Sonia Neural)", group: "en", gender: "female", kind: "cloud",
    note: "Cloud neural voice: sends the text out of the bank to a speech service. Demo use only; not set up." },
];

/** Fixed sample lines, used only when the live brief cannot be read (they quote no figure: N5). */
export const FALLBACK_LINES: Record<ChoiceLang, string> = {
  "en": "Good morning. Here is what changed in the book since yesterday. First, the lines that need your decision today; then the names behind them.",
  "ar-gulf": "صباح الخير. هذا ما تغيّر في المحفظة منذ الأمس. أولاً، البنود التي تحتاج قراركم اليوم، ثم الأسماء التي وراءها.",
};

/** The same two or three sentences of the real brief for every voice: the brief's spoken script, cut at a sentence. */
export function sampleLines(script: string | null | undefined, group: ChoiceLang, max = 3): string {
  const t = String(script ?? "").replace(/\s+/g, " ").trim();
  if (!t) return FALLBACK_LINES[group];
  // A sentence ends at . ! ? ؟ followed by a space and not a digit ("44.1 percent" and "1.73 bn" stay whole).
  const parts = t.split(/(?<=[.!?؟]["”’)]?)\s+(?=[^\d\s])/);
  const out: string[] = [];
  for (const p of parts) {
    if (out.length >= max) break;
    if (out.join(" ").length + p.length > 320 && out.length >= 2) break;
    out.push(p.trim());
  }
  return out.join(" ") || FALLBACK_LINES[group];
}

export const clamp = (x: number, r: { min: number; max: number }) => Math.min(r.max, Math.max(r.min, Number.isFinite(x) ? x : r.min));

/** The installed voice for a choice: the same name (and the same language when there are two), else null. */
export function resolveChosen<V extends VoiceLike>(voices: readonly V[], choice: ChosenVoice | null | undefined): V | null {
  if (!choice || isNeural(choice)) return null;   // R16 v: a neural voice is not one of the browser's
  const same = voices.filter((v) => v.name === choice.name);
  return same.find((v) => v.lang === choice.lang) ?? same[0] ?? null;
}

/** What the page and the Noor settings say about one language's voice. */
export function choiceLine(choice: ChosenVoice | null, installed: boolean, group: ChoiceLang): string {
  const lang = group === "ar-gulf" ? "Arabic" : "English";
  if (!choice) return `${lang}: not chosen yet, so Noor stays silent in ${lang}. Listen below and press "Use for ${lang}".`;
  const who = choice.chosen_by ? ` (chosen by ${choice.chosen_by})` : "";
  // R16 v2: a cloud voice (azure:…) says that its text leaves the machine.
  if (isNeural(choice) && choice.name.startsWith("azure:")) return `${lang}: ${choice.label || choice.name}, a cloud voice (Cloud – text leaves the machine; demo with fictional data only), speed ${choice.rate.toFixed(2)}${who}.`;
  if (isNeural(choice)) return `${lang}: ${choice.label || choice.name}, the offline neural voice on this computer, speed ${choice.rate.toFixed(2)}${who}.`;
  if (!installed) return `${lang}: ${choice.name}${who}, but this computer does not have it; Noor stays silent in ${lang} until it is installed or another voice is chosen.`;
  return `${lang}: ${choice.name}, rate ${choice.rate.toFixed(2)}, pitch ${choice.pitch.toFixed(2)}${who}.`;
}

export function normaliseChosen(v: unknown): Chosen {
  const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
  const one = (x: unknown): ChosenVoice | null => {
    if (!x || typeof x !== "object") return null;
    const c = x as Record<string, unknown>;
    if (typeof c.name !== "string" || !c.name || typeof c.lang !== "string") return null;
    return { name: c.name, lang: c.lang, rate: clamp(Number(c.rate ?? RATE.start), RATE), pitch: clamp(Number(c.pitch ?? PITCH.start), PITCH),
             ...(c.engine === "neural" ? { engine: "neural" as const } : {}),
             ...(typeof c.label === "string" && c.label ? { label: c.label } : {}),
             ...(typeof c.chosen_by === "string" ? { chosen_by: c.chosen_by } : {}),
             ...(typeof c.chosen_at === "string" ? { chosen_at: c.chosen_at } : {}) };
  };
  return { "en": one(o["en"]), "ar-gulf": one(o["ar-gulf"]) };
}

// ---------------------------------------------------------------- kept in the browser too (the tour reads it)

const KEY = "cp.voice.chosen";

export function readChosen(): Chosen {
  try { return normaliseChosen(JSON.parse(window.localStorage.getItem(KEY) || "{}")); } catch { return NO_CHOICE; }
}

export function writeChosen(c: Chosen): void {
  try { window.localStorage.setItem(KEY, JSON.stringify(c)); } catch { /* storage off: the bank setting still holds it */ }
}
