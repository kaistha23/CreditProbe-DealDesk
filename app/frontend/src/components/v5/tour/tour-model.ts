/**
 * Noor's introduction tour (PLAN_R14 session t; R13_FEEDBACK K36, K36a): the pure part, tested by tour-model.test.ts.
 *
 * The script comes from the Deal Desk service (`GET /api/v1/tour/script`, backend/agents_v5/tour): steps
 * `{route, selectors, action, caption, voice, duration_ms, wait_for}` with live numbers already filled in and audited.
 * This file holds what the player decides without touching the page: the voice (male only, K10), when the tour starts
 * by itself, which selector is the target, how long a step lasts, and the control labels in both languages.
 */

export type TourLang = "en" | "ar";

export interface TourAction {
  type: "home" | "diagram" | "brief" | "click" | "ask" | "open_module" | "open_deal" | "panel";
  click?: string[];
  then?: string[];
  open?: string[];
  href?: string;
  tab?: "brief" | "ask";
  deal?: string;
  close_after?: boolean;
  /** Within one step, the highlight moves to each selector when the caption reaches its mark (e.g. two brief lines). */
  sequence?: { selector: string; mark_en: string; mark_ar: string }[];
}

export interface TourStep {
  n: number;
  key: string;
  title: string;
  route: string;
  action: TourAction;
  selectors: string[];
  optional: boolean;
  wait_for: string[];
  module: string;
  caption: string;
  voice: string;
  caption_en: string;
  caption_ar: string;
  title_en: string;
  title_ar: string;
  duration_ms: number;
  facts: string[];
  dropped: { clause: string; missing: string; why: string }[];
  unbacked: string[];
}

export interface TourFact {
  id: string; value: unknown; en: string; ar: string; domain: string; relation: string; method: string;
  keys: Record<string, unknown>; period: string;
}

export interface TourScript {
  version: string;
  lang: TourLang;
  dir: "ltr" | "rtl";
  steps: TourStep[];
  n_steps: number;
  duration_ms: number;
  facts: Record<string, TourFact>;
  claims: { unbacked: string[]; dropped: { step: string; clause: string; missing: string; why: string }[]; rule: string };
  voice: { en: string[]; ar: string[]; rate: number; pitch: number; gender: "male" };
}

export type TourStatus = "loading" | "playing" | "paused" | "done" | "error";

// ---------------------------------------------------------------- the voice (K10: male, calm; never female)

export interface VoiceLike { name: string; lang: string; localService?: boolean; default?: boolean }

export const TOUR_RATE = 0.92;
export const TOUR_PITCH = 0.9;

const FEMALE = /female|woman|samantha|laila|serena|kate|moira|susan|karen|tessa|victoria|fiona|zira|hazel|libby|sonia|mariam|zariyah|hoda|salma|amira|allison|ava|zoe|nora|joelle|noelle|siri female|google us english|google uk english female|majed female|lana|mona|amina|zeina/i;

/** Preference order per language (K10): English Evan, Nathan (Enhanced/Premium first), then Daniel; Arabic Maged. */
const PREFERRED: Record<TourLang, RegExp[]> = {
  en: [/\bevan\b/i, /\bnathan\b/i, /\bdaniel\b/i, /\baaron\b/i, /\barthur\b/i, /\bgoogle uk english male\b/i,
       /\bfred\b/i, /\balex\b/i, /\btom\b/i, /\bmale\b/i],
  ar: [/\bmaged\b/i, /\bmajed\b/i, /\btarik\b/i, /\bhamed\b/i, /\bnaayf\b/i, /\bshakir\b/i, /\bmale\b/i],
};

const quality = (name: string) => (/premium/i.test(name) ? 2 : /enhanced/i.test(name) ? 1 : 0);

/**
 * The tour's voice: the first male voice in the preference order, in the language (any region), Enhanced or Premium
 * before the standard one. Null when no named male voice is installed: the tour then plays with captions only, rather
 * than read with a voice that may be female.
 */
export function pickTourVoice<V extends VoiceLike>(voices: readonly V[], lang: TourLang): V | null {
  const base = lang === "ar" ? "ar" : "en";
  const pool = voices.filter((v) => v.lang.toLowerCase().replace("_", "-").startsWith(base) && !FEMALE.test(v.name));
  for (const re of PREFERRED[lang]) {
    const hits = pool.filter((v) => re.test(v.name));
    if (hits.length) {
      return [...hits].sort((a, b) => quality(b.name) - quality(a.name) || Number(!!b.localService) - Number(!!a.localService)
        || a.name.localeCompare(b.name))[0];
    }
  }
  return null;
}

export const isFemaleVoice = (name: string) => FEMALE.test(name);

// ---------------------------------------------------------------- when the tour starts, how long a step lasts

/** Playback speed for walk-throughs (`?tour_speed=8`); 1 for people. Bounded 1–20. */
export function tourSpeed(search: string): number {
  const v = Number(new URLSearchParams(search).get("tour_speed"));
  return Number.isFinite(v) && v >= 1 ? Math.min(20, v) : 1;
}

/** L1 (R15): the tour starts only from the header button; nothing else (sign-in, a link, a URL) starts it. */
export const TOUR_STARTS_ONLY_FROM = "tour-take" as const;

/** How long the step stays when no voice reads it (captions only, or a blocked voice). */
export function stepMs(step: Pick<TourStep, "duration_ms">, speed: number): number {
  return Math.max(400, Math.round(step.duration_ms / Math.max(1, speed)));
}

/**
 * When to move the highlight within a step: for each sequence item found in the text, the share of the text read
 * before its mark (0–1), in order. Items whose mark is not in the text are left out.
 */
export function sequenceTimes(text: string, seq: TourAction["sequence"], lang: TourLang): { selector: string; at: number }[] {
  if (!seq?.length || !text) return [];
  const out: { selector: string; at: number }[] = [];
  let from = 0;
  for (const it of seq) {
    const mark = lang === "ar" ? it.mark_ar : it.mark_en;
    const i = text.indexOf(mark, from);
    if (i < 0) continue;
    out.push({ selector: it.selector, at: i / text.length });
    from = i + mark.length;
  }
  return out;
}

export function clampIndex(i: number, n: number): number {
  return Math.max(0, Math.min(n - 1, i));
}

/** The first selector present on the page (`has` asks the page). */
export function firstPresent(selectors: readonly string[], has: (sel: string) => boolean): string | null {
  for (const s of selectors) {
    try {
      if (has(s)) return s;
    } catch {
      /* an invalid selector (e.g. :has-text on a browser without it) is not present */
    }
  }
  return null;
}

/** Does the page need to move for this step? Deal pages count as the Deal Desk only for their own steps. */
export function needsNavigation(path: string, route: string): boolean {
  if (route === "/") return path !== "/";
  return !(path === route || path.startsWith(`${route}/`)) || (route === "/deal-desk" && path !== "/deal-desk");
}

export function totalLabel(ms: number, lang: TourLang): string {
  const m = Math.max(1, Math.round(ms / 60000));
  return lang === "ar" ? (m === 1 ? "دقيقة واحدة" : m === 2 ? "دقيقتان" : `${m} دقائق`) : `${m} min`;
}

// ---------------------------------------------------------------- words on the controls

export const LABELS: Record<TourLang, Record<string, string>> = {
  en: {
    take: "Take the tour", play: "Play", pause: "Pause", back: "Back", next: "Next", skip: "Skip tour",
    captions: "Captions", close: "Close", step: "Step", of: "of", lang: "العربية", done: "That's the tour",
    restart: "Play again", noVoice: "Choose a voice in Settings → Voice to hear the tour: captions only.",
    voiceOn: "Play with voice", voiceOff: "Turn the voice off",
    blocked: "Press Play to hear Noor.", loading: "Getting the tour ready…", prompt: "New to CreditProbe?",
    promptBody: "Noor shows you round: what CreditProbe is, and every module, on your own data.", start: "Start the tour", later: "Not now",
    error: "The tour could not be loaded. Please try again in a moment.",
    diagramTop: "CreditProbe: the intelligence layer", diagramNoor: "Noor reads every system, every day",
    los: "Loan system", cbs: "Core banking", rating: "Rating", collections: "Collections", ews: "Early warning",
    records: "records", posts: "posts", scores: "scores", chases: "chases", flags: "flags",
    out: "Brief · Why · Ask · Deal Desk · What-If · Lenses", skipped: "skipped (not on this build)",
    sources: "Where these figures come from",
  },
  ar: {
    take: "جولة تعريفية", play: "تشغيل", pause: "إيقاف مؤقت", back: "السابق", next: "التالي", skip: "إنهاء الجولة",
    captions: "الترجمة", close: "إغلاق", step: "الخطوة", of: "من", lang: "English", done: "انتهت الجولة",
    restart: "إعادة التشغيل", noVoice: "اختاروا صوتاً من الإعدادات ← الصوت لسماع الجولة: الترجمة فقط.",
    voiceOn: "تشغيل مع الصوت", voiceOff: "إيقاف الصوت",
    blocked: "اضغطوا تشغيل لسماع نور.", loading: "جارٍ تجهيز الجولة…", prompt: "جديد على كريدت بروب؟",
    promptBody: "ترافقكم نور في جولة: ما هو كريدت بروب، وكل وحداته، على بياناتكم.", start: "ابدأ الجولة", later: "ليس الآن",
    error: "تعذّر تحميل الجولة. يرجى المحاولة بعد قليل.",
    diagramTop: "كريدت بروب: طبقة الذكاء", diagramNoor: "نور تقرأ كل الأنظمة كل يوم",
    los: "نظام القروض", cbs: "النظام المصرفي الأساسي", rating: "التصنيف", collections: "التحصيل", ews: "الإنذار المبكر",
    records: "يسجّل", posts: "يقيّد", scores: "يقيّم", chases: "يحصّل", flags: "ينبّه",
    out: "الموجز · لماذا · اسأل · مكتب الصفقات · ماذا لو · العدسات", skipped: "تم التخطي (غير متاح في هذا الإصدار)",
    sources: "مصدر هذه الأرقام",
  },
};
