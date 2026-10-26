/**
 * R16 m (M1): "Voice is bad; it speaks on login. Never speak unless the speaker button is pressed."
 *
 * Source scans: Noor has no automatic speech path. The only route to speech (`say` in noor-store.ts) is private and
 * reached only from the click handlers; every caller of those handlers in the app is an onClick; the brief load and
 * the sign-in path never speak; the bank's voice default is off.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const SRC = join(here, "..", "..");
const read = (p: string) => readFileSync(join(here, p), "utf8");

/** Top-level function blocks of a module: name -> body (up to the next top-level function or section). */
function functions(code: string): Map<string, string> {
  const out = new Map<string, string>();
  const re = /^(?:export\s+)?(?:async\s+)?function\s+(\w+)/gm;
  const hits = [...code.matchAll(re)];
  hits.forEach((m, i) => out.set(m[1], code.slice(m.index, i + 1 < hits.length ? hits[i + 1].index : code.length)));
  return out;
}

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { if (name !== "node_modules") walk(p, acc); }
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.ts$/.test(name)) acc.push(p);
  }
  return acc;
}

const store = read("noor-store.ts");

test("M1: autoSpeak is gone, and nothing in the store speaks on its own", () => {
  assert.ok(!/\bautoSpeak\s*\(/.test(store), "no autoSpeak call");
  assert.ok(!/function\s+autoSpeak/.test(store), "no autoSpeak function");
  assert.ok(!/hadGesture/.test(store), "no 'speak once the page had a gesture' path");
  assert.ok(!/export\s+function\s+speak\s*\(/.test(store), "no exported speak() reachable from non-click paths");
});

test("M1: the brief load path (sign-in, panel open, bell) never speaks", () => {
  const fns = functions(store);
  const load = fns.get("loadBrief");
  assert.ok(load, "loadBrief exists");
  assert.ok(!/\b(say|speak|speakText|speakNow|speakerButton|listenBrief)\s*\(/.test(load!), "loadBrief does not speak");
  const top = readFileSync(join(here, "noor-topbar.tsx"), "utf8");
  assert.ok(!/\b(say|speak|speakText|speakNow|speakerButton|listenBrief|speakLine|speakOnClick)\s*\(/.test(top), "the top bar (sign-in) does not speak");
});

test("M1: `say` (the only route to speech) is called only from the click handlers", () => {
  const allowed = new Set(["speakerButton", "speakNow", "speakOnClick"]);
  for (const [name, body] of functions(store)) {
    const calls = body.replace(/^function\s+say\s*\(/, "").match(/\bsay\s*\(/g) ?? [];
    if (name === "say") continue;
    if (calls.length) assert.ok(allowed.has(name), `${name} calls say()`);
  }
  // speakText (the browser's speech) is called only by say
  for (const [name, body] of functions(store)) if (/\bspeakText\s*\(/.test(body)) assert.equal(name, "say");
});

test("M1: every caller of a speaking function in the app is a click handler", () => {
  const names = /\b(speakerButton|speakNow|listenBrief|speakLine|speakOnClick)\s*\(/;
  for (const file of walk(SRC)) {
    if (file.endsWith("noor-store.ts")) continue;
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      if (!names.test(line) || /^\s*(import|export\s+function|\*|\/\/)/.test(line)) return;
      const ok = /onClick=/.test(line) || /\{\s*speak:\s*\(t\)\s*=>\s*noorSpeak\(t\)/.test(line);
      assert.ok(ok, `${file}:${i + 1} calls a speaking function outside a click: ${line.trim()}`);
    });
    // nothing else in the app calls the browser's speech directly, except the tour and the sampler's Listen buttons
    const code = lines.join("\n");
    if (/speechSynthesis/.test(code) && /\.speak\s*\(/.test(code)) {
      assert.ok(/tour-voice\.ts$|voice-sampler\.tsx$|noor-voice\.ts$/.test(file), `${file} speaks directly`);
    }
  }
});

test("M1: 'In plain words' speaks only from its speaker button's click", () => {
  const pw = readFileSync(join(SRC, "components", "v5", "ui", "plain-words.tsx"), "utf8");
  const uses = pw.match(/voice\.speak\(/g) ?? [];
  assert.equal(uses.length, 1, "one call");
  const toggle = pw.slice(pw.indexOf("const toggle"), pw.indexOf("};", pw.indexOf("const toggle")));
  assert.ok(toggle.includes("voice.speak("), "inside toggle");
  assert.ok(/onClick=\{toggle\}/.test(pw), "toggle is the button's onClick");
  assert.ok(pw.includes("speakOnClick"), "the default reader is the click path");
});

test("M1: the sampler speaks only from Listen clicks", () => {
  const s = read("voice-sampler.tsx");
  assert.ok(/onClick=\{\(\) => \(playing === id \? stop\(\) : play\(c\)\)\}/.test(s));
  const effects = s.split("React.useEffect(").slice(1).map((b) => b.slice(0, b.indexOf("}, [")));
  for (const e of effects) assert.ok(!/\bplay\(|\.speak\(/.test(e), "no speech in an effect");
});

test("M1: bank and reader defaults are voice off; a click with no chosen voice shows the note", () => {
  assert.match(store, /voice: \{ enabled: false, gender: "male", language: "en" \}/);
  assert.match(store, /voice: \{ on: false, language: "en", state: "loading"/);
  const say = functions(store).get("say")!;
  assert.ok(say.includes("showNotice(CHOOSE_VOICE_NOTE)"), "silent with a note when not chosen");
  const btn = read("speaker-button.tsx");
  assert.ok(btn.includes("export function VoiceChoiceNote") && btn.includes("VOICE_SETTINGS_HREF"), "note links to Settings → Voice");
  assert.ok(read("noor-topbar.tsx").includes("<VoiceChoiceNote />"), "mounted on every screen");
});
