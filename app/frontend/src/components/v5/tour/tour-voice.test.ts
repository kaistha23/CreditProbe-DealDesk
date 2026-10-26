/**
 * R16 m (M1): the tour is captions only by default; it speaks only after the reader pressed its "Play with voice"
 * control during this tour, and only with the voice chosen in Settings → Voice (no interim pick).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { LABELS } from "./tour-model.ts";

const player = readFileSync(new URL("./tour-player.tsx", import.meta.url), "utf8");
const voiceSrc = readFileSync(new URL("./tour-voice.ts", import.meta.url), "utf8");

test("M1: the tour does not speak by default (voice off until its own control is pressed)", () => {
  assert.match(player, /const \[voiceOn, setVoiceOn\] = React\.useState\(false\)/);
  assert.match(player, /const voiceRef = React\.useRef\(false\)/);
  // the step runner reads a voice only when the reader turned it on
  assert.match(player, /speed === 1 && voiceRef\.current \? await tourVoice\(s\.lang\) : null/);
  assert.ok(player.includes('testId="tour-voice"') && player.includes("onClick={toggleVoice}"), "the control is a click");
  // the only places that set voiceRef to true are inside toggleVoice
  const sets = [...player.matchAll(/voiceRef\.current = (\w+)/g)].map((m) => m[1]);
  assert.deepEqual(sets, ["next"]);
  const toggle = player.slice(player.indexOf("const toggleVoice"), player.indexOf("const close"));
  assert.ok(toggle.includes("const next = !voiceRef.current"));
  // speak() is called only in the runner (gated by `voice`) and in toggleVoice
  const calls = player.split("\n").filter((l) => /\bspeak\(/.test(l) && !/^import/.test(l.trim()));
  assert.equal(calls.length, 2, calls.join("\n"));
  assert.ok(LABELS.en.voiceOn && LABELS.ar.voiceOn && LABELS.en.voiceOff && LABELS.ar.voiceOff);
  assert.match(LABELS.en.noVoice, /Choose a voice in Settings → Voice/);
});

test("M1: the tour reads only the chosen voice; with none chosen it is captions only", async () => {
  assert.ok(!/pickTourVoice/.test(voiceSrc), "no interim male pick");
  const voices = [{ name: "Evan (Enhanced)", lang: "en-US" }, { name: "Maged", lang: "ar-SA" }];
  const store: Record<string, string> = {};
  const g = globalThis as unknown as { window?: unknown };
  const before = g.window;
  g.window = {
    speechSynthesis: { getVoices: () => voices, addEventListener() {}, removeEventListener() {} },
    localStorage: { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v; } },
    setTimeout,
  };
  try {
    const { tourVoice } = await import("./tour-voice.ts");
    assert.equal(await tourVoice("en"), null, "not chosen: silent");
    store["cp.voice.chosen"] = JSON.stringify({ "en": { name: "Evan (Enhanced)", lang: "en-US", rate: 0.9, pitch: 1 } });
    const got = await tourVoice("en");
    assert.equal(got?.voice?.name, "Evan (Enhanced)");
    assert.equal(got?.rate, 0.9);
    assert.equal(await tourVoice("ar"), null, "Arabic not chosen: silent");
    // R16 v: a chosen offline neural voice is the tour's voice too
    store["cp.voice.chosen"] = JSON.stringify({ "ar-gulf": { engine: "neural", name: "ar_JO-kareem-medium", lang: "ar-JO", rate: 1, pitch: 1 } });
    const ar = await tourVoice("ar");
    assert.equal(ar?.voice, null);
    assert.deepEqual(ar?.neural, { id: "ar_JO-kareem-medium", lang: "ar-JO" });
  } finally {
    g.window = before;
  }
});
