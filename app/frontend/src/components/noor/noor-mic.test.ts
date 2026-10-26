import assert from "node:assert/strict";
import { test } from "node:test";

import { MIC_PRIVACY, joinTranscript, micLabel, micLang } from "./noor-mic.ts";

test("K10: the mic listens in English (en-US) or Arabic (ar-SA)", () => {
  assert.equal(micLang("en"), "en-US");
  assert.equal(micLang("ar-gulf"), "ar-SA");
});

test("the transcript is added to what is typed, never sent by itself", () => {
  assert.equal(joinTranscript("", "why did ECL rise"), "why did ECL rise");
  assert.equal(joinTranscript("In Construction,", " why did ECL rise "), "In Construction, why did ECL rise");
  assert.equal(joinTranscript("typed", ""), "typed");
});

test("the control says the audio goes to the browser's speech service", () => {
  assert.match(micLabel("idle", "en-US"), /browser's speech service/);
  assert.match(micLabel("listening", "ar-SA"), /Arabic/);
  assert.match(MIC_PRIVACY, /browser's speech service/);
  assert.match(micLabel("unsupported", "en-US"), /not available/);
});
