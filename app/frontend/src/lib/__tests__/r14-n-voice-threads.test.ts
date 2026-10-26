import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

/**
 * R14 n, checked against the source (the walk-through ops/r14_n_walkthrough.py checks the behaviour by clicking).
 * K10: a mic in every ask box and thread composer, a speaker on every answer; K16: no fixed desk thread anywhere;
 * K5/K7: the panel opens on a fresh thread and a brief line's actions run in that line's thread; K6: line actions
 * are always visible, below the line.
 */

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");

test("K10: the mic is in the Cockpit Ask, the Noor panel, every module landing and ask bar, every thread composer", () => {
  for (const f of ["components/home/home-ask.tsx", "components/noor/noor-panel.tsx", "components/v5/landing/module-landing.tsx",
                   "components/v5/thread/thread-shell.tsx", "components/cockpit-v4/thread-view.tsx",
                   "components/v5/scorecard/home.tsx", "components/v5/playbook/home.tsx"]) {
    assert.ok(read(f).includes("<MicButton"), f);
  }
  // the AskBar (Early Warning, Borrower 360) and the landing both carry it
  assert.equal((read("components/v5/landing/module-landing.tsx").match(/<MicButton/g) ?? []).length, 2);
});

test("K10: a speaker on every answer (module threads, the Cockpit thread, Noor's answers) and on every brief line", () => {
  assert.ok(read("components/v5/thread/thread-shell.tsx").includes("<AnswerSpeaker"));
  assert.ok(read("components/cockpit-v4/thread-view.tsx").includes("<AnswerSpeaker"));
  const turns = read("components/noor/turns.tsx");
  assert.ok((turns.match(/<Speaker /g) ?? []).length >= 3, "why, options, drivers");
  const brief = read("components/noor/noor-brief.tsx");
  assert.ok(brief.includes('data-testid="noor-line-speaker"') && brief.includes('data-testid="noor-listen"'));
});

test("K10 / R16 M1: Noor speaks only in the voice chosen in Settings -> Voice, at its rate and pitch (no interim voice)", () => {
  const v = read("components/noor/noor-voice.ts");
  assert.ok(v.includes('export type VoiceGender = "male";'));
  // R16 v: the browser utterance is made in browserSay, with the chosen voice's own rate and pitch
  assert.ok(v.includes("browserSay(s, text, voice, choice.rate, choice.pitch, on)") && v.includes("u.rate = rate") && v.includes("u.pitch = pitch"));
  assert.ok(!read("components/noor/noor-settings.tsx").includes('<option value="female">'));
});

test("K16: no fixed desk thread anywhere in the UI", () => {
  for (const f of ["components/v5/dealdesk/home.tsx", "components/noor/noor-dispatch.ts", "components/v5/dealdesk/desk-thread.tsx"]) {
    assert.ok(!/thread=desk(?![\w-])/.test(read(f).replace(/`\?thread=desk`|`thread=desk`/g, "")), f);
  }
});

test("K5 / K7: the panel opens on a fresh thread; a line's actions run in its own thread", () => {
  const s = read("components/noor/noor-store.ts");
  assert.ok(s.includes("if (open && !state.open) { set({ open: true }); newNoorThread(); return; }"));
  assert.ok(s.includes("threadOf(lineKey(item), subject(item))"));
});

test("K6: line actions always visible, below the line (no hover-only opacity)", () => {
  const b = read("components/noor/noor-brief.tsx");
  assert.ok(b.includes('data-testid="noor-line-actions"'));
  assert.ok(!b.includes("group-hover:opacity-100"));
});
