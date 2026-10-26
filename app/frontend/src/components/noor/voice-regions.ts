/**
 * R16 v2: regional voices in Settings → Voice, grouped by language and accent: Indian English, Arabic – Saudi and
 * Arabic – UAE (Gulf), beside the existing English (US/UK) and Arabic tables.
 *
 * For each region the sources, in order of preference:
 *   1. Mac system voices the browser exposes at runtime for that locale (en-IN Rishi, Veena and their Enhanced
 *      versions; ar-SA Maged; any ar-AE voice present). Expected Mac voices that are missing are listed with how to get them.
 *   2. Offline neural voices for the locale: none exists in the Piper or Kokoro catalogues (the backend's
 *      `offline_catalogue` says why; nothing is invented).
 *   3. The optional cloud provider (Azure Speech: ar-SA Hamed/Zariyah, ar-AE Hamdan/Fatima, en-IN Prabhat/Neerja),
 *      off unless the Deal Desk service has CP_TTS_CLOUD_KEY and CP_TTS_CLOUD_REGION; labelled
 *      "Cloud – text leaves the machine; demo with fictional data only"; played only from a Listen click on its row and
 *      used for Noor only if an administrator chooses it.
 *
 * Pure (node --test: voice-regions.test.ts).
 */
import type { NeuralStatus, NeuralVoice } from "./neural-voice.ts";
import { CLOUD_LABEL } from "./neural-voice.ts";
import { type ChoiceLang, type Gender, type Quality, type VoiceLike, genderOf, qualityOf } from "./voice-choice.ts";

export type RegionId = "en-IN" | "ar-SA" | "ar-AE";

export interface Region { id: RegionId; group: ChoiceLang; title: string; locale: RegExp }

export const REGIONS: Region[] = [
  { id: "en-IN", group: "en", title: "Indian English", locale: /^en[-_]in\b/i },
  { id: "ar-SA", group: "ar-gulf", title: "Arabic – Saudi", locale: /^ar[-_]sa\b/i },
  { id: "ar-AE", group: "ar-gulf", title: "Arabic – UAE (Gulf)", locale: /^ar[-_]ae\b/i },
];

/** The Mac system voices expected for each locale (System Settings → Accessibility → Spoken Content → Manage Voices).
 *  macOS has no Emirati (ar-AE) system voice that we know of; any ar-AE voice the browser exposes is still listed. */
export const MAC_REGIONAL: Record<RegionId, { name: string; gender: Gender }[]> = {
  "en-IN": [{ name: "Rishi (Enhanced)", gender: "male" }, { name: "Rishi", gender: "male" },
            { name: "Veena (Enhanced)", gender: "female" }, { name: "Veena", gender: "female" }],
  "ar-SA": [{ name: "Maged (Enhanced)", gender: "male" }, { name: "Maged", gender: "male" }],
  "ar-AE": [],
};

export const MAC_HOW = "Not on this Mac: System Settings → Accessibility → Spoken Content → System voice → Manage Voices, then reload this page.";

export type RowKind = "mac" | "offline" | "cloud";

export interface RegionalRow {
  key: string; kind: RowKind; name: string; lang: string; gender: Gender; quality?: Quality;
  /** Plays on this computer now. */
  available: boolean;
  /** Why not (when not available), in plain words. */
  why: string;
  /** For kind "mac": the browser voice; for "offline"/"cloud": the backend voice. */
  voice?: NeuralVoice;
  label?: string;
}

const norm = (l: string) => l.replace("_", "-");

/**
 * The rows for one region: Mac voices on this computer for the locale (best first), the expected Mac voices that are
 * missing, offline neural voices for the locale (none in the catalogues today), then the cloud voices.
 */
export function regionalRows(region: Region, voices: readonly VoiceLike[], status: NeuralStatus | null): RegionalRow[] {
  const rows: RegionalRow[] = [];
  const seen = new Set<string>();
  const here = voices.filter((v) => region.locale.test(norm(v.lang)));
  const qRank: Record<Quality, number> = { premium: 0, enhanced: 1, siri: 2, natural: 3, google: 4, standard: 5 };
  const gRank: Record<Gender, number> = { male: 0, unknown: 1, female: 2 };
  [...here].sort((a, b) => qRank[qualityOf(a.name)] - qRank[qualityOf(b.name)]
    || gRank[genderOf(a.name)] - gRank[genderOf(b.name)] || a.name.localeCompare(b.name)).forEach((v) => {
    const key = `${v.name}|${v.lang}`;
    if (seen.has(key)) return;
    seen.add(key);
    const local = v.localService !== false;
    rows.push({ key: `mac|${key}`, kind: "mac", name: v.name, lang: v.lang, gender: genderOf(v.name), quality: qualityOf(v.name),
                available: true, why: local ? "" : "Browser's network voice (text goes to the browser maker)" });
  });
  const have = new Set(here.map((v) => v.name.toLowerCase()));
  for (const m of MAC_REGIONAL[region.id]) {
    if (have.has(m.name.toLowerCase())) continue;
    rows.push({ key: `mac-missing|${m.name}`, kind: "mac", name: m.name, lang: region.id, gender: m.gender, quality: qualityOf(m.name),
                available: false, why: MAC_HOW });
  }
  const theirs = (status?.voices ?? []).filter((v) => norm(v.lang).toLowerCase() === region.id.toLowerCase());
  for (const v of theirs.filter((x) => x.where !== "cloud" && !x.id.startsWith("azure:"))) {
    rows.push({ key: `offline|${v.id}`, kind: "offline", name: v.name, lang: v.lang, gender: v.gender, voice: v,
                available: Boolean(v.installed), why: v.installed ? "" : v.why || "The offline add-on is not installed here." });
  }
  const male = (v: NeuralVoice) => (v.gender === "male" ? 0 : 1);
  for (const v of theirs.filter((x) => x.where === "cloud" || x.id.startsWith("azure:")).sort((a, b) => male(a) - male(b))) {
    rows.push({ key: `cloud|${v.id}`, kind: "cloud", name: v.name, lang: v.lang, gender: v.gender, voice: v, label: v.label || CLOUD_LABEL,
                available: Boolean(v.installed),
                why: v.installed ? "" : v.why || status?.cloud?.why || "Cloud voices are off here (not configured)." });
  }
  return rows;
}

/** Why no offline neural voice exists for the region (from the backend's catalogue check), or a plain fallback. */
export function offlineNote(region: Region, status: NeuralStatus | null): string {
  return status?.offline_catalogue?.[region.id]
    ?? `No offline neural voice for ${region.title} in the Piper or Kokoro catalogues.`;
}

/** One line per region: how many voices play here now, and from where. */
export function regionSummary(rows: readonly RegionalRow[]): string {
  const mac = rows.filter((r) => r.kind === "mac" && r.available).length;
  const cloud = rows.filter((r) => r.kind === "cloud" && r.available).length;
  const off = rows.filter((r) => r.kind === "offline" && r.available).length;
  const parts = [`${mac} Mac voice${mac === 1 ? "" : "s"}`, `${off} offline neural`, `${cloud} cloud`];
  return `${mac + off + cloud} available on this computer (${parts.join(", ")}).`;
}

/** The sampler's "playing" id for a row: the browser voice's `name|lang`, or `neural|<id>` for a backend voice. */
export function playId(r: Pick<RegionalRow, "kind" | "name" | "lang" | "voice">): string {
  return r.kind === "mac" ? `${r.name}|${r.lang}` : `neural|${r.voice?.id ?? r.name}`;
}
