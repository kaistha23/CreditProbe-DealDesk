/** R16 v2: regional voices (Indian English, Arabic – Saudi, Arabic – UAE (Gulf)) grouped by accent, with whether each
 *  plays on this computer and why not; cloud voices labelled and off unless configured; nothing plays without a click. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { CLOUD_LABEL, isCloudVoice, neuralCandidates, neuralLabel, type NeuralStatus, type NeuralVoice } from "./neural-voice.ts";
import { choiceLine, normaliseChosen } from "./voice-choice.ts";
import { MAC_HOW, REGIONS, offlineNote, playId, regionSummary, regionalRows } from "./voice-regions.ts";

const cloudV = (id: string, name: string, lang: string, gender: "male" | "female", installed: boolean): NeuralVoice => ({
  id: `azure:${id}`, engine: "azure", name, lang, group: lang.startsWith("ar") ? "ar-gulf" : "en", gender, accent: lang,
  note: "", installed, where: "cloud", label: CLOUD_LABEL, why: installed ? null : "Cloud voices are off: CP_TTS_CLOUD_KEY and CP_TTS_CLOUD_REGION are not set",
});
const status = (on: boolean): NeuralStatus => ({
  available: true, engines: { kokoro: true, piper: true, azure: on }, missing: [], reached: true,
  voices: [
    { id: "am_michael", engine: "kokoro", name: "Michael", lang: "en-US", group: "en", gender: "male", accent: "American", note: "", installed: true, where: "offline" },
    { id: "ar_JO-kareem-medium", engine: "piper", name: "Kareem", lang: "ar-JO", group: "ar-gulf", gender: "male", accent: "Levantine", note: "", installed: true, where: "offline" },
    cloudV("ar-SA-ZariyahNeural", "Zariyah", "ar-SA", "female", on), cloudV("ar-SA-HamedNeural", "Hamed", "ar-SA", "male", on),
    cloudV("ar-AE-HamdanNeural", "Hamdan", "ar-AE", "male", on), cloudV("ar-AE-FatimaNeural", "Fatima", "ar-AE", "female", on),
    cloudV("en-IN-PrabhatNeural", "Prabhat", "en-IN", "male", on), cloudV("en-IN-NeerjaNeural", "Neerja", "en-IN", "female", on),
  ],
  cloud: { provider: "Azure Speech", configured: on, region: on ? "uaenorth" : null, label: CLOUD_LABEL, why: on ? null : "Cloud voices are off" },
  offline_catalogue: { "ar-SA": "No offline neural voice for Saudi Arabic: Piper's only Arabic voice is ar_JO Kareem; Kokoro has no Arabic." },
});
const MAC = [
  { name: "Rishi", lang: "en-IN", localService: true }, { name: "Veena (Enhanced)", lang: "en_IN", localService: true },
  { name: "Maged", lang: "ar-SA", localService: true }, { name: "Daniel", lang: "en-GB", localService: true },
  { name: "Majed", lang: "ar-001", localService: true },
];
const region = (id: string) => REGIONS.find((r) => r.id === id)!;

test("R16 v2: three regional accents, grouped under their language", () => {
  assert.deepEqual(REGIONS.map((r) => [r.id, r.group, r.title]), [
    ["en-IN", "en", "Indian English"], ["ar-SA", "ar-gulf", "Arabic – Saudi"], ["ar-AE", "ar-gulf", "Arabic – UAE (Gulf)"]]);
});

test("R16 v2: Indian English: Mac voices the browser exposes, the missing ones with how to get them, then cloud male and female", () => {
  const rows = regionalRows(region("en-IN"), MAC, status(false));
  assert.deepEqual(rows.map((r) => [r.kind, r.name, r.available]), [
    ["mac", "Veena (Enhanced)", true], ["mac", "Rishi", true],
    ["mac", "Rishi (Enhanced)", false], ["mac", "Veena", false],
    ["cloud", "Prabhat", false], ["cloud", "Neerja", false]]);
  assert.equal(rows[2].why, MAC_HOW);
  assert.ok(rows.filter((r) => r.kind === "cloud").every((r) => r.label === CLOUD_LABEL && /CP_TTS_CLOUD_KEY/.test(r.why)));
  assert.match(regionSummary(rows), /^2 available on this computer \(2 Mac voices, 0 offline neural, 0 cloud\)/);
  assert.ok(!rows.some((r) => r.name === "Daniel"), "en-GB is not Indian English");
});

test("R16 v2: Arabic – Saudi has Maged and the cloud pair; UAE has no Mac voice unless the browser has one", () => {
  const sa = regionalRows(region("ar-SA"), MAC, status(true));
  assert.deepEqual(sa.map((r) => [r.kind, r.name, r.gender, r.available]), [
    ["mac", "Maged", "male", true], ["mac", "Maged (Enhanced)", "male", false],
    ["cloud", "Hamed", "male", true], ["cloud", "Zariyah", "female", true]]);
  const ae = regionalRows(region("ar-AE"), MAC, status(false));
  assert.deepEqual(ae.map((r) => r.name), ["Hamdan", "Fatima"]);
  const ae2 = regionalRows(region("ar-AE"), [...MAC, { name: "Laila", lang: "ar-AE", localService: true }], status(false));
  assert.equal(ae2[0].name, "Laila");
  assert.equal(ae2[0].kind, "mac");
  assert.ok(!sa.some((r) => r.name === "Majed"), "ar-001 is not Saudi");
});

test("R16 v2: why there is no offline neural voice comes from the backend's catalogue check", () => {
  assert.match(offlineNote(region("ar-SA"), status(false)), /Kareem/);
  assert.match(offlineNote(region("en-IN"), null), /Piper or Kokoro/);
});

test("R16 v2: cloud voices never in the offline neural table; labels say cloud", () => {
  const st = status(true);
  assert.deepEqual(neuralCandidates(st.voices, "ar-gulf").map((v) => v.id), ["ar_JO-kareem-medium"]);
  assert.deepEqual(neuralCandidates(st.voices, "en").map((v) => v.id), ["am_michael"]);
  assert.ok(isCloudVoice("azure:ar-AE-FatimaNeural") && !isCloudVoice("am_michael"));
  assert.match(neuralLabel(st.voices[2]), /cloud/);
  const c = normaliseChosen({ "ar-gulf": { engine: "neural", name: "azure:ar-AE-FatimaNeural", lang: "ar-AE", rate: 1, pitch: 1, label: "Fatima" } });
  assert.match(choiceLine(c["ar-gulf"], true, "ar-gulf"), /Cloud – text leaves the machine; demo with fictional data only/);
  assert.equal(playId({ kind: "mac", name: "Rishi", lang: "en-IN" }), "Rishi|en-IN");
  assert.equal(playId({ kind: "cloud", name: "Hamed", lang: "ar-SA", voice: st.voices[3] }), "neural|azure:ar-SA-HamedNeural");
});

test("R16 v2: the sampler renders a table per accent, Listen and Use only from clicks, cloud label shown", () => {
  const src = readFileSync(new URL("./voice-sampler.tsx", import.meta.url), "utf8");
  assert.ok(src.includes("RegionalTable") && src.includes('data-testid="voice-region-listen"') && src.includes('data-testid="voice-region-use"'));
  assert.ok(src.includes("voice-cloud-label") && src.includes("CLOUD_LABEL"));
  // speak calls only inside click handlers (M1): no effect plays a regional voice
  const effects = src.split("React.useEffect(").slice(1).map((e) => e.split("}, [")[0]);
  assert.ok(effects.every((e) => !/playNeural|speakNeural|\.speak\(/.test(e)));
});
