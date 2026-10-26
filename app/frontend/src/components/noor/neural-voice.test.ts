/**
 * R16 v: the offline neural voice in the frontend. Pure helpers; the choice model (a neural choice is chosen even with
 * no browser voice); `speakNeural` against a fake backend (503 = absent, so the caller falls back to the browser voice;
 * 200 = plays and ends; a second identical line is not fetched again); `speakText` falls back to the browser's voice
 * with a note when the add-on is absent; and source scans that nothing speaks unless clicked (M1).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CLOUD_OFF_NOTE, NEURAL_ABSENT_NOTE, chunkText, neuralCandidates, neuralKey, neuralLabel, neuralSpeed, speakNeural, stopNeural, type NeuralVoice } from "./neural-voice.ts";
import { pickVoice } from "./noor-voice.ts";
import { choiceLine, isNeural, normaliseChosen, resolveChosen } from "./voice-choice.ts";

const NV = (id: string, group: "en" | "ar-gulf", gender: "male" | "female"): NeuralVoice =>
  ({ id, engine: group === "en" ? "kokoro" : "piper", name: id, lang: group === "en" ? "en-US" : "ar-JO", group, gender, accent: "x", note: "" });

test("R16 v: neural speed follows the Rate slider, bounded, two decimals", () => {
  assert.equal(neuralSpeed(0.92), 0.92);
  assert.equal(neuralSpeed(3), 1.5);
  assert.equal(neuralSpeed(0.1), 0.5);
  assert.equal(neuralSpeed(Number.NaN), 1);
  assert.equal(neuralKey("Hi.", "am_michael", 0.9), "am_michael|0.90|Hi.");
});

test("R16 v: a long line is played in chunks: one sentence first, then ~260 characters; decimals stay whole", () => {
  const t = "Good morning, Anne. Exposure is SAR 1.48 bn, up 12.5%. Two names are in Riyadh. One is in Jeddah.\nNext, the watch list.";
  assert.deepEqual(chunkText(t), ["Good morning, Anne.", "Exposure is SAR 1.48 bn, up 12.5%. Two names are in Riyadh. One is in Jeddah.", "Next, the watch list."]);
  const long = Array.from({ length: 12 }, (_, i) => `Sentence number ${i} is about the book and what changed in it today.`).join(" ");
  const c = chunkText(long);
  assert.equal(c[0], "Sentence number 0 is about the book and what changed in it today.");
  assert.ok(c.length >= 4 && c.every((x) => x.length <= 260), "chunks stay short");
  assert.equal(c.join(" "), long, "nothing is lost");
  assert.deepEqual(chunkText("صباح الخير. هل هذا واضح؟ نعم."), ["صباح الخير.", "هل هذا واضح؟ نعم."]);
  assert.deepEqual(chunkText("  "), []);
});

test("R16 v: neural rows per language, male first, female options kept", () => {
  const list = [NV("af_heart", "en", "female"), NV("am_michael", "en", "male"), NV("bm_george", "en", "male"), NV("ar_JO-kareem-medium", "ar-gulf", "male")];
  assert.deepEqual(neuralCandidates(list, "en").map((v) => v.id), ["am_michael", "bm_george", "af_heart"]);
  assert.deepEqual(neuralCandidates(list, "ar-gulf").map((v) => v.id), ["ar_JO-kareem-medium"]);
  assert.equal(neuralLabel({ name: "George", accent: "British", engine: "kokoro" }), "George (British, Kokoro neural)");
});

test("R16 v: a neural choice is kept, is chosen without any browser voice, and is never a browser voice", () => {
  const c = normaliseChosen({ "en": { engine: "neural", name: "am_michael", lang: "en-US", rate: 0.95, pitch: 1, label: "Michael (American, Kokoro neural)" } });
  assert.ok(isNeural(c.en) && c.en?.label?.startsWith("Michael"));
  assert.equal(resolveChosen([{ name: "am_michael", lang: "en-US" }], c.en), null);
  const p = pickVoice([], "en", "male", c.en);
  assert.ok(p.chosen && p.neural && !p.notChosen, "chosen even when the browser has no voice");
  assert.match(choiceLine(c.en, false, "en"), /offline neural voice on this computer/);
  assert.equal(normaliseChosen({ "en": { engine: "cloud", name: "x", lang: "en-US" } }).en?.engine, undefined, "only 'neural' is an engine");
});

type Handler = (() => void) | null;
class FakeAudio {
  static played: string[] = [];
  src = ""; currentTime = 0; paused = true; ended = false;
  onplaying: Handler = null; onended: Handler = null; onerror: Handler = null;
  play() { this.paused = false; FakeAudio.played.push(this.src); setTimeout(() => { this.onplaying?.(); setTimeout(() => { this.ended = true; this.onended?.(); }, 5); }, 1); return Promise.resolve(); }
  pause() { this.paused = true; }
}

function withFakes(status: number, run: (calls: { body: unknown }[]) => Promise<void>) {
  const g = globalThis as unknown as Record<string, unknown>;
  const saved = { window: g.window, Audio: g.Audio, fetch: g.fetch, URL: g.URL };
  const calls: { body: unknown }[] = [];
  g.window = {};
  g.Audio = FakeAudio;
  g.fetch = async (_url: string, init?: RequestInit) => {
    calls.push({ body: init?.body ? JSON.parse(String(init.body)) : null });
    return { status, ok: status === 200, blob: async () => new Blob([new Uint8Array(8)], { type: "audio/wav" }), json: async () => ({}) };
  };
  return run(calls).finally(() => { Object.assign(g, saved); });
}

test("R16 v: speakNeural plays the backend's WAV once per line and says when the add-on is absent", async () => {
  await withFakes(200, async (calls) => {
    let started = 0;
    const o = await speakNeural("Exposure is SAR 1.48 bn.", "bm_george", "en-GB", 0.92, { start: () => { started++; } });
    assert.equal(o, "ended");
    assert.equal(started, 1);
    assert.deepEqual(calls[0].body, { text: "Exposure is SAR 1.48 bn.", voice: "bm_george", lang: "en-GB", speed: 0.92 });
    assert.equal(await speakNeural("Exposure is SAR 1.48 bn.", "bm_george", "en-GB", 0.92), "ended");
    assert.equal(calls.length, 1, "the same line is not fetched twice");
    // a long line: each chunk is fetched once, the whole line plays to the end, start/end fire once
    let s2 = 0, e2 = 0;
    const before = calls.length;
    assert.equal(await speakNeural("First one. Second one here. Third one.", "bm_george", "en-GB", 0.92,
                                   { start: () => { s2++; }, end: () => { e2++; } }), "ended");
    assert.equal(calls.length - before, 2, "two chunks");
    assert.deepEqual([s2, e2], [1, 1]);
    const p = speakNeural("Another line.", "bm_george", "en-GB", 0.92);
    stopNeural();
    assert.equal(await p, "stopped");
  });
  await withFakes(503, async () => {
    assert.equal(await speakNeural("Hello.", "am_michael", "en-US", 1), "absent");
  });
});

test("R16 v: with the add-on absent, a click reads with the browser's voice and says so", async () => {
  const g = globalThis as unknown as Record<string, unknown>;
  const saved = { window: g.window, Audio: g.Audio, fetch: g.fetch, SpeechSynthesisUtterance: g.SpeechSynthesisUtterance };
  const spoken: { text: string; voice: string }[] = [];
  const voices = [{ name: "Daniel", lang: "en-GB", localService: true }, { name: "Samantha", lang: "en-US", localService: true }];
  g.window = { speechSynthesis: { getVoices: () => voices, cancel() {}, resume() {}, speak(u: { text: string; voice: { name: string } }) { spoken.push({ text: u.text, voice: u.voice.name }); } },
               SpeechSynthesisUtterance: class {} };
  g.SpeechSynthesisUtterance = class { text: string; voice: unknown; lang = ""; rate = 1; pitch = 1; constructor(t: string) { this.text = t; } };
  g.Audio = FakeAudio;
  g.fetch = async () => ({ status: 503, ok: false, json: async () => ({ available: false }) });
  try {
    const { speakText } = await import("./noor-voice.ts");
    const choice = normaliseChosen({ "en": { engine: "neural", name: "am_michael", lang: "en-US", rate: 0.9, pitch: 1 } }).en;
    const r = await speakText("Good morning.", "en", "male", {}, choice);
    assert.equal(r.note, NEURAL_ABSENT_NOTE);
    assert.equal(r.spoken, true);
    assert.deepEqual(spoken, [{ text: "Good morning.", voice: "Daniel" }], "the browser's best male voice stands in");
    // R16 v2: a chosen cloud voice with the cloud off here (503) says so, and the browser's voice reads
    const cloudChoice = normaliseChosen({ "en": { engine: "neural", name: "azure:en-IN-PrabhatNeural", lang: "en-IN", rate: 1, pitch: 1 } }).en;
    const r2 = await speakText("Good evening.", "en", "male", {}, cloudChoice);
    assert.equal(r2.note, CLOUD_OFF_NOTE);
    assert.match(r2.note ?? "", /CP_TTS_CLOUD_KEY/);
  } finally {
    Object.assign(g, saved);
  }
});

test("R16 v / M1: the neural voice speaks only from clicks", () => {
  const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
  const files: Record<string, string> = {
    voice: read("./noor-voice.ts"), tour: read("../v5/tour/tour-voice.ts"), sampler: read("./voice-sampler.tsx"),
    store: read("./noor-store.ts"), neural: read("./neural-voice.ts"),
  };
  // speakNeural is called in exactly three places: speakText (reached only via the store's private `say`), the tour's
  // speak (after "Play with voice") and the sampler's playNeural (a Listen click)
  assert.equal((files.voice.match(/\bspeakNeural\(/g) ?? []).length, 1);
  assert.equal((files.tour.match(/\bspeakNeural\(/g) ?? []).length, 1);
  assert.equal((files.sampler.match(/\bspeakNeural\(/g) ?? []).length, 1);
  assert.ok(!/\bspeakNeural\(/.test(files.store), "the store never calls the neural voice directly");
  // the sampler's playNeural runs from the Listen buttons' onClick (and chains itself for "Listen to all")
  const calls = files.sampler.split("\n").filter((l) => /\bplayNeural\(/.test(l) && !/const playNeural/.test(l));
  for (const l of calls) assert.ok(/onListen|onListenAll|rest\.length/.test(l), `playNeural outside a click: ${l.trim()}`);
  assert.ok(/onClick=\{\(\) => onListen\(v\)\}/.test(files.sampler) && /onClick=\{\(\) => onListenAll\(list\)\}/.test(files.sampler));
  const effects = files.sampler.split("React.useEffect(").slice(1).map((b) => b.slice(0, b.indexOf("}, [")));
  for (const e of effects) assert.ok(!/playNeural\(|speakNeural\(/.test(e), "no neural speech in an effect");
  // no autoplay anywhere
  assert.ok(!/autoplay/i.test(files.neural.replace(/\/\*[\s\S]*?\*\//g, "")), "no autoplay");
  // stopping speech stops the neural line too
  assert.ok(/export function stopSpeech[\s\S]*?stopNeural\(\)/.test(files.voice) && /cancelSpeech[\s\S]*?stopNeural\(\)/.test(files.tour));
});
