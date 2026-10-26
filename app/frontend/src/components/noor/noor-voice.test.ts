import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CHOOSE_VOICE_NOTE, VOICE_PITCH, VOICE_RATE, effectiveVoice, isFemaleVoice, pickVoice, suggestVoice, voiceLang, voiceStateFor,
  voiceStateLabel,
} from "./noor-voice.ts";

const V = (name: string, lang: string, extra: Partial<{ default: boolean; localService: boolean }> = {}) => ({ name, lang, ...extra });

// R16 M1: the K10 male-first order now only ORDERS the sampler's suggestions (`suggestVoice`); pickVoice speaks only
// with the chosen voice.
test("R14 K10 (suggestion order): English suggests Evan, Nathan, Daniel in that order, Enhanced/Premium first; never female", () => {
  const voices = [V("Samantha", "en-US", { localService: true }), V("Kate", "en-GB", { localService: true }),
                  V("Daniel", "en-GB"), V("Nathan (Enhanced)", "en-US"), V("Evan", "en-US"), V("Evan (Enhanced)", "en-US"),
                  V("Maged", "ar-SA")];
  const { voice, fallback } = suggestVoice(voices, "en");
  assert.equal(voice?.name, "Evan (Enhanced)");
  assert.equal(fallback, false);
  assert.equal(suggestVoice(voices.filter((v) => !v.name.startsWith("Evan")), "en").voice?.name, "Nathan (Enhanced)");
  assert.equal(suggestVoice([V("Samantha", "en-US"), V("Daniel", "en-GB"), V("Daniel (Premium)", "en-GB")], "en").voice?.name,
               "Daniel (Premium)");
});

test("Arabic suggests Maged; a female Arabic voice is never suggested", () => {
  const voices = [V("Kate", "en-GB"), V("Laila", "ar-AE"), V("Maged", "ar-SA"), V("Tarik", "ar_EG")];
  assert.equal(suggestVoice(voices, "ar-gulf").voice?.name, "Maged");
  const noMaged = suggestVoice([V("Laila", "ar-AE"), V("Daniel", "en-GB")], "ar-gulf");
  assert.equal(noMaged.voice?.name, "Daniel");
  assert.equal(noMaged.fallback, true);
});

test("the suggestion is never a female voice, whatever is installed", () => {
  const females = ["Samantha", "Kate", "Karen", "Moira", "Tessa", "Victoria", "Fiona", "Laila", "Mariam", "Ava (Premium)",
                   "Zoe (Enhanced)", "Allison", "Google US English", "Google UK English Female", "Microsoft Zira"];
  for (let i = 0; i < females.length; i++) {
    const pool = [...females.slice(i).map((n) => V(n, "en-US")), V("Thomas", "fr-FR")];
    const got = suggestVoice(pool, "en").voice;
    assert.ok(!got || !isFemaleVoice(got.name), String(got?.name));
  }
  const only = suggestVoice(females.map((n) => V(n, "en-GB")), "en");
  assert.equal(only.voice, null);
  assert.equal(only.noMale, true);
});

test("calm: rate 0.92, pitch 0.9", () => {
  assert.equal(VOICE_RATE, 0.92);
  assert.equal(VOICE_PITCH, 0.9);
});

test("no voice in the language: the suggestion falls back to an allowed voice", () => {
  const voices = [V("Kate", "en-GB"), V("Thomas", "fr-FR", { default: true })];
  const r = suggestVoice(voices, "ar-gulf");
  assert.equal(r.voice?.name, "Thomas");
  assert.equal(r.fallback, true);
});

test("no voices at all is no voice, not a crash", () => {
  assert.deepEqual(pickVoice([], "en", "male"), { voice: null, fallback: false });
});

test("the button's states, and a clear sentence when no voice is installed", () => {
  assert.equal(voiceStateFor(false, false, 0, false, false), "unsupported");
  assert.equal(voiceStateFor(true, false, 0, false, false), "loading");
  assert.equal(voiceStateFor(true, true, 0, false, false), "no-voice");
  assert.equal(voiceStateFor(true, true, 3, true, false), "fallback");
  assert.equal(voiceStateFor(true, true, 3, false, true), "speaking");
  assert.equal(voiceStateFor(true, true, 3, false, false), "ready");
  assert.match(voiceStateLabel("no-voice", true, "en"), /No voice is installed/);
  assert.match(voiceStateLabel("fallback", false, "ar-gulf"), /no Arabic voice installed/);
});

test("the reader's own choice wins over the bank default; languages map to BCP-47", () => {
  assert.deepEqual(effectiveVoice({ on: null, language: null }, { enabled: true, language: "en" }), { on: true, language: "en" });
  assert.deepEqual(effectiveVoice({ on: null, language: null }, { enabled: false, language: "en" }), { on: false, language: "en" });
  assert.deepEqual(effectiveVoice({ on: false, language: "ar-gulf" }, { enabled: true, language: "en" }), { on: false, language: "ar-gulf" });
  assert.equal(voiceLang("ar-gulf"), "ar-SA");
  assert.equal(voiceLang("en"), "en-GB");
});

test("R16 M1: with no voice chosen pickVoice returns no voice (never a random, interim or fallback voice)", () => {
  const voices = [V("Evan (Enhanced)", "en-US"), V("Daniel", "en-GB"), V("Maged", "ar-SA"), V("Samantha", "en-US", { default: true })];
  for (const lang of ["en", "ar-gulf"] as const) {
    const r = pickVoice(voices, lang, "male", null);
    assert.equal(r.voice, null, lang);
    assert.equal(r.notChosen, true, lang);
    assert.ok(!r.missing);
  }
  // chosen but not on this computer: still silent, and says so
  const gone = pickVoice(voices, "en", "male", { name: "Zoe (Premium)", lang: "en-US", rate: 1, pitch: 1 });
  assert.equal(gone.voice, null);
  assert.equal(gone.notChosen, true);
  assert.equal(gone.missing, true);
  // chosen and installed: that voice, whatever its gender
  const mine = pickVoice(voices, "en", "male", { name: "Samantha", lang: "en-US", rate: 0.9, pitch: 1 });
  assert.equal(mine.voice?.name, "Samantha");
  assert.equal(mine.chosen, true);
  // the state and the note
  assert.equal(voiceStateFor(true, true, 4, false, false, true), "not-chosen");
  assert.equal(voiceStateFor(true, true, 0, false, false, true), "no-voice");
  assert.equal(voiceStateLabel("not-chosen", true, "en"), CHOOSE_VOICE_NOTE);
  assert.match(CHOOSE_VOICE_NOTE, /Choose a voice in Settings → Voice/);
});
