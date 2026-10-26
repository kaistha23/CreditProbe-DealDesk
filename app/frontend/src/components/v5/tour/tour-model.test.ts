import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampIndex, firstPresent, sequenceTimes, isFemaleVoice, needsNavigation, pickTourVoice, stepMs, tourSpeed,
  totalLabel, LABELS,
} from "./tour-model.ts";

const V = (name: string, lang: string, localService = true) => ({ name, lang, localService });

const MAC = [V("Samantha", "en-US"), V("Ava (Premium)", "en-US"), V("Daniel", "en-GB"), V("Kate", "en-GB"),
             V("Nathan (Enhanced)", "en-US"), V("Evan", "en-US"), V("Evan (Enhanced)", "en-US"), V("Majed", "ar-SA"),
             V("Laila", "ar-SA"), V("Maged", "ar-SA"), V("Google UK English Female", "en-GB", false)];

test("English: Evan first, Enhanced before standard; then Nathan; then Daniel", () => {
  assert.equal(pickTourVoice(MAC, "en")?.name, "Evan (Enhanced)");
  assert.equal(pickTourVoice(MAC.filter((v) => !v.name.startsWith("Evan")), "en")?.name, "Nathan (Enhanced)");
  assert.equal(pickTourVoice([V("Kate", "en-GB"), V("Daniel", "en-GB")], "en")?.name, "Daniel");
});

test("Arabic: Maged", () => {
  assert.equal(pickTourVoice(MAC, "ar")?.name, "Maged");
  assert.equal(pickTourVoice([V("Tarik", "ar_EG"), V("Laila", "ar-SA")], "ar")?.name, "Tarik");
});

test("the tour voice is never female: no male voice means captions only", () => {
  const females = [V("Samantha", "en-US"), V("Kate", "en-GB"), V("Google UK English Female", "en-GB"),
                   V("Laila", "ar-SA"), V("Ava", "en-US"), V("Mariam", "ar-SA")];
  assert.equal(pickTourVoice(females, "en"), null);
  assert.equal(pickTourVoice(females, "ar"), null);
  for (const lang of ["en", "ar"] as const) {
    for (let i = 0; i < MAC.length; i++) {
      const pool = [...MAC.slice(i), ...MAC.slice(0, i)];   // any order
      const v = pickTourVoice(pool, lang);
      assert.ok(v && !isFemaleVoice(v.name), `${lang}: ${v?.name}`);
    }
  }
  assert.equal(pickTourVoice([], "en"), null);
});

test("an unnamed voice (gender unknown) is not used", () => {
  assert.equal(pickTourVoice([V("Grandma", "en-US"), V("Bubbles", "en-US")], "en"), null);
});

test("speed is bounded (walk-throughs only; it never starts the tour)", () => {
  assert.equal(tourSpeed("?tour_speed=8"), 8);
  assert.equal(tourSpeed("?tour_speed=100"), 20);
  assert.equal(tourSpeed("?tour_speed=x"), 1);
  assert.equal(stepMs({ duration_ms: 8000 }, 8), 1000);
  assert.equal(stepMs({ duration_ms: 8000 }, 1), 8000);
});

test("L1: the tour starts only from the header button (no first-login prompt, no ?tour=1, no start event)", async () => {
  const { readFileSync } = await import("node:fs");
  const launcher = readFileSync(new URL("./tour-launcher.tsx", import.meta.url), "utf8");
  const code = launcher.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/useSearchParams|tour_prompt|tourParam|shouldPrompt|addEventListener|CustomEvent|setTimeout/.test(code),
            "no URL, prompt, timer or event can start the tour");
  assert.ok(!code.includes("tour-prompt"), "no first-login prompt");
  // setOpen(true) appears once, inside `start`, and `start` is only wired to the button's onClick.
  assert.equal((code.match(/setOpen\(true\)/g) ?? []).length, 1);
  assert.equal((code.match(/\bstart\b/g) ?? []).length, 2, "start is defined once and used once");
  assert.ok(/onClick=\{start\}[^>]*data-testid="tour-take"/.test(code), "the header button calls start");
  const index = readFileSync(new URL("./index.ts", import.meta.url), "utf8");
  assert.ok(!index.includes("startTour"), "no start-from-anywhere export");
});

test("the first present selector wins; a bad selector is skipped", () => {
  const page = new Set(['[data-testid="dealdesk-step-proposal"]']);
  const has = (s: string) => { if (s.includes(":bad")) throw new Error("bad"); return page.has(s); };
  assert.equal(firstPresent(['[data-tour="dd-proposal-check"]', "x:bad", '[data-testid="dealdesk-step-proposal"]'], has),
               '[data-testid="dealdesk-step-proposal"]');
  assert.equal(firstPresent(['[data-tour="dd-stress"]'], has), null);
});

test("navigation is needed only when the page is elsewhere", () => {
  assert.equal(needsNavigation("/", "/"), false);
  assert.equal(needsNavigation("/lenses", "/"), true);
  assert.equal(needsNavigation("/early-warning", "/early-warning"), false);
  assert.equal(needsNavigation("/deal-desk/R12-TWA", "/deal-desk/R12-TWA"), false);
  assert.equal(needsNavigation("/deal-desk/R12-TWA", "/deal-desk"), true);
  assert.equal(needsNavigation("/deal-desk", "/deal-desk"), false);
  assert.equal(clampIndex(-1, 5), 0);
  assert.equal(clampIndex(9, 5), 4);
});

test("labels in both languages, same keys", () => {
  assert.deepEqual(Object.keys(LABELS.en).sort(), Object.keys(LABELS.ar).sort());
  assert.equal(totalLabel(150000, "en"), "3 min");
  assert.equal(totalLabel(120000, "ar"), "دقيقتان");
});

test("the header mounts the tour; the player has every control (K36)", async () => {
  const { readFileSync } = await import("node:fs");
  const header = readFileSync(new URL("../../layout/header.tsx", import.meta.url), "utf8");
  assert.ok(header.includes("<TourLauncher />"), "header mounts <TourLauncher />");
  const launcher = readFileSync(new URL("./tour-launcher.tsx", import.meta.url), "utf8");
  assert.ok(launcher.includes('"tour-take"'), "tour-take");
  const player = readFileSync(new URL("./tour-player.tsx", import.meta.url), "utf8");
  for (const id of ["tour-play", "tour-back", "tour-next", "tour-skip", "tour-captions", "tour-lang", "tour-caption", "tour-sources"]) {
    assert.ok(player.includes(`"${id}"`), id);
  }
  assert.ok(player.includes('nav[aria-label="Primary"]') || player.includes("a.click"), "navigation by clicking");
});

test("the highlight follows the two brief lines as their words come up", () => {
  const seq = [{ selector: "li:nth-child(1)", mark_en: "First:", mark_ar: "أولها:" },
               { selector: "li:nth-child(2)", mark_en: "Then:", mark_ar: "ثم:" }];
  const t = sequenceTimes("Every morning. First: a line. Then: another.", seq, "en");
  assert.deepEqual(t.map((x) => x.selector), ["li:nth-child(1)", "li:nth-child(2)"]);
  assert.ok(t[0].at > 0 && t[0].at < t[1].at && t[1].at < 1);
  assert.deepEqual(sequenceTimes("No lines today.", seq, "en"), []);
  assert.equal(sequenceTimes("كل صباح. أولها: سطر. ثم: آخر.", seq, "ar").length, 2);
});
