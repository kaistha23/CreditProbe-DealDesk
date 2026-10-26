import assert from "node:assert/strict";
import { test } from "node:test";

import {
  OTHER_OPTIONS, QUALITY_LABEL, candidates, choiceLine, genderOf, missingDownloads, normaliseChosen, qualityOf, resolveChosen, sampleLines,
} from "./voice-choice.ts";
import { pickVoice } from "./noor-voice.ts";

const V = (name: string, lang: string, localService = true) => ({ name, lang, localService });

// A Mac with a few Enhanced/Premium voices downloaded, and Chrome's network voices.
const MAC = [V("Samantha", "en-US"), V("Ava (Premium)", "en-US"), V("Daniel", "en-GB"), V("Kate", "en-GB"),
             V("Evan (Enhanced)", "en-US"), V("Zoe (Premium)", "en-US"), V("Majed", "ar-001"), V("Maged", "ar-SA"),
             V("Laila", "ar-SA"), V("Thomas", "fr-FR"), V("Google UK English Male", "en-GB", false),
             V("Google UK English Female", "en-GB", false), V("Bubbles", "en-US")];

test("L2: the buffet lists English and Arabic voices, male and female, best quality first", () => {
  const c = candidates(MAC);
  assert.ok(!c.en.some((x) => x.name === "Thomas"), "French voices are left out");
  assert.deepEqual(c.en.slice(0, 2).map((x) => x.quality).sort(), ["premium", "premium"]);
  assert.ok(c.en.some((x) => x.gender === "male") && c.en.some((x) => x.gender === "female"), "both genders in English");
  assert.ok(c["ar-gulf"].some((x) => x.gender === "male") && c["ar-gulf"].some((x) => x.gender === "female"), "both in Arabic");
  assert.equal(c["ar-gulf"][0].lang, "ar-SA", "Saudi Arabic first among equals");
  const net = c.en.filter((x) => !x.local);
  // R16 M1: quality first (Google above plain), so network Google voices sit above plain system voices, labelled.
  assert.ok(net.length === 2 && net.every((x) => x.quality === "google"), "network voices, labelled Google");
  assert.match(net[0].source, /network/i);
  assert.ok(c.en.findIndex((x) => x.quality === "google") < c.en.findIndex((x) => x.quality === "standard"));
  assert.equal(genderOf("Bubbles"), "unknown");
  assert.equal(genderOf("Google UK English Female"), "female");
  assert.equal(genderOf("Google UK English Male"), "male");
  assert.equal(qualityOf("Evan (Enhanced)"), "enhanced");
  assert.equal(qualityOf("Siri Voice 2"), "siri");
});

test("L2: every voice reads the same two or three sentences of the real brief", () => {
  const script = "Good morning, Anne. Stage 2 rose in Construction. First: the Al Noor contractor slipped to Stage 2. Then: oil is lower. Last line.";
  const s = sampleLines(script, "en");
  assert.equal(s, "Good morning, Anne. Stage 2 rose in Construction. First: the Al Noor contractor slipped to Stage 2.");
  assert.ok(sampleLines("صباح الخير. ارتفعت المرحلة الثانية. أولاً: المقاول. ثم: النفط.", "ar-gulf").split(/[.؟]/).filter((x) => x.trim()).length === 3);
  assert.ok(sampleLines("", "en").length > 20, "fixed lines when the brief cannot be read");
  assert.equal(sampleLines("Five things. First: Stage 3 LGD of 44.1 percent against 94.9 percent. Then: SAR 1.73 bn. Last.", "en"),
               "Five things. First: Stage 3 LGD of 44.1 percent against 94.9 percent. Then: SAR 1.73 bn.", "decimals never split a sentence");
  assert.ok(!/\d/.test(sampleLines(null, "en")), "the fallback quotes no figure (N5)");
});

test("L2: no voice is fixed until chosen; a chosen voice (male or female) then wins, with its rate and pitch", () => {
  assert.deepEqual(normaliseChosen(undefined), { "en": null, "ar-gulf": null });
  assert.match(choiceLine(null, false, "en"), /not chosen yet/);
  const chosen = normaliseChosen({ "en": { name: "Zoe (Premium)", lang: "en-US", rate: 0.85, pitch: 1.05, chosen_by: "anne" }, "ar-gulf": null });
  assert.equal(resolveChosen(MAC, chosen.en)?.name, "Zoe (Premium)");
  const p = pickVoice(MAC, "en", "male", chosen.en);
  assert.equal(p.voice?.name, "Zoe (Premium)");
  assert.equal(p.chosen, true);
  // R16 M1: not chosen: no voice at all (Noor stays silent and says "Choose a voice in Settings → Voice")
  const q = pickVoice(MAC, "en", "male", null);
  assert.equal(q.voice, null);
  assert.ok(!q.chosen && q.notChosen);
  assert.match(choiceLine(null, false, "en"), /silent/);
  // chosen but not on this computer: silent too, and the line says so
  const gone = normaliseChosen({ "en": { name: "Nathan (Enhanced)", lang: "en-US", rate: 1, pitch: 1 } });
  assert.equal(resolveChosen(MAC, gone.en), null);
  assert.match(choiceLine(gone.en, false, "en"), /does not have it/);
  assert.equal(pickVoice(MAC, "en", "male", gone.en).voice, null);
  assert.equal(normaliseChosen({ "en": { name: "X", lang: "en-US", rate: 9, pitch: 0.1 } }).en?.rate, 1.5, "rate is bounded");
});

test("L2 / R16 v: cloud voices are listed with a clear label, never played; the offline neural voices are real now", () => {
  const cloud = OTHER_OPTIONS.filter((o) => o.kind === "cloud");
  assert.ok(cloud.length >= 2 && cloud.every((o) => /sends the text out/i.test(o.note) && /demo/i.test(o.note)));
  assert.ok(cloud.some((o) => o.group === "en"), "cloud en");
  // R16 v2: the Saudi Arabic cloud voices are real rows of the regional tables now (voice-regions.test.ts), not options
  assert.ok(!cloud.some((o) => /ar-SA/.test(o.name)));
  assert.equal(OTHER_OPTIONS.filter((o) => o.kind === "offline").length, 0, "Piper/Kokoro are in the neural table, not 'not installed'");
  const miss = missingDownloads(MAC).map((d) => d.name);
  assert.ok(miss.includes("Nathan (Enhanced)") && !miss.includes("Evan (Enhanced)") && !miss.includes("Maged"));
});

test("L2: Settings -> Voice is reachable by clicks and Noor and the tour read the choice", async () => {
  const { readFileSync } = await import("node:fs");
  const pages = readFileSync(new URL("../v5/admin/pages.tsx", import.meta.url), "utf8");
  assert.ok(pages.includes('router.push("/settings/voice")') && pages.includes('"settings-voice-open"'));
  const form = readFileSync(new URL("./noor-settings.tsx", import.meta.url), "utf8");
  assert.ok(form.includes('router.push("/settings/voice")'));
  const page = readFileSync(new URL("../../app/settings/voice/page.tsx", import.meta.url), "utf8");
  assert.ok(page.includes("<VoiceSampler />"));
  const sampler = readFileSync(new URL("./voice-sampler.tsx", import.meta.url), "utf8");
  for (const id of ["voice-rate-", "voice-pitch-", "voice-listen", "voice-use", "voice-options-", "voice-mac-downloads"]) assert.ok(sampler.includes(id), id);
  const tour = readFileSync(new URL("../v5/tour/tour-voice.ts", import.meta.url), "utf8");
  assert.ok(tour.includes("readChosen") && tour.includes("resolveChosen"), "the tour reads the chosen voice");
  const store = readFileSync(new URL("./noor-store.ts", import.meta.url), "utf8");
  assert.ok(store.includes("choiceFor(") && store.includes("writeChosen"), "Noor reads and shares the chosen voice");
});

test("R16 M1: the list is best first: Premium > Enhanced > Siri > Natural/Neural > Google > plain, with a quality label", () => {
  const voices = [V("Daniel", "en-GB"), V("Google UK English Male", "en-GB", false),
                  V("Microsoft Ryan Online (Natural) - English (United Kingdom)", "en-GB", false), V("Siri Voice 1", "en-US"),
                  V("Evan (Enhanced)", "en-US"), V("Jamie (Premium)", "en-GB"), V("Lee", "en-AU"), V("Moira", "en-IE"),
                  V("Rishi", "en-IN"), V("Fred", "en-US"),
                  V("Microsoft Hamed Online (Natural) - Arabic (Saudi Arabia)", "ar-SA", false), V("Maged", "ar-SA"),
                  V("Tarik", "ar-EG"), V("Majed (Enhanced)", "ar-001")];
  const c = candidates(voices);
  assert.deepEqual(c.en.slice(0, 5).map((x) => x.quality), ["premium", "enhanced", "siri", "natural", "google"]);
  assert.equal(c.en[0].name, "Jamie (Premium)");
  assert.ok(c.en.slice(5).every((x) => x.quality === "standard"), "plain voices last");
  for (const lang of ["en-GB", "en-US", "en-AU", "en-IE", "en-IN"]) assert.ok(c.en.some((x) => x.lang === lang), lang);
  assert.deepEqual(c["ar-gulf"].map((x) => x.name).slice(0, 2), ["Majed (Enhanced)", "Microsoft Hamed Online (Natural) - Arabic (Saudi Arabia)"]);
  assert.ok(c["ar-gulf"].some((x) => x.lang === "ar-EG"), "every ar-* region is listed");
  // among plain voices the K10 suggested male names come first (ordering only)
  assert.equal(c.en.find((x) => x.quality === "standard")?.name, "Daniel");
  assert.equal(qualityOf("Microsoft Ryan Online (Natural) - English (United Kingdom)"), "natural");
  assert.equal(qualityOf("Google US English"), "google");
  for (const q of ["premium", "enhanced", "siri", "natural", "google", "standard"] as const) assert.ok(QUALITY_LABEL[q]);
});

test("R16 v: the sampler lists the offline neural voices beside the browser's, with their install state", async () => {
  const { readFileSync } = await import("node:fs");
  const sampler = readFileSync(new URL("./voice-sampler.tsx", import.meta.url), "utf8");
  assert.ok(sampler.includes('"voice-piper-note"') && sampler.includes("NEURAL_INSTALL_HINT") && /Not installed here/.test(sampler));
  for (const id of ["voice-side-by-side-", "voice-neural-", "voice-neural-listen", "voice-neural-use", "voice-neural-play-all-"]) assert.ok(sampler.includes(id), id);
  assert.ok(/onClick=\{\(\) => onListen\(v\)\}/.test(sampler), "neural Listen is a click");
  assert.ok(!/interim voice/.test(sampler), "no interim voice is promised");
});

