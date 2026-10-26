import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isLandingInput, startFresh, threadIdFor, threadViewKey } from "./thread-rule.ts";

// ---------------------------------------------------------------- R16 m (M6): the shared rule

test("M6: every input except a thread's own composer is a landing input", () => {
  for (const o of ["landing", "ask-bar", "cockpit", "noor"] as const) assert.equal(isLandingInput(o), true, o);
  assert.equal(isLandingInput("thread"), false);
});

test("M6: only input typed inside an open thread sends that thread's id", () => {
  for (const o of ["landing", "ask-bar", "cockpit", "noor"] as const) assert.equal(threadIdFor(o, "wt-1"), null, o);
  assert.equal(threadIdFor("thread", "wt-1"), "wt-1");
  assert.equal(threadIdFor("thread", null), null);
});

test("M6: startFresh never carries a thread id, a run id or a continue flag", () => {
  const body = startFresh("whatif", { domain: "corporate", question: "Q2", thread_id: "wt-1", threadId: "wt-1", continue: true, run_id: "wq-1" });
  assert.deepEqual(body, { domain: "corporate", question: "Q2" });
  assert.deepEqual(startFresh("lenses", { request: "Q1" }), { request: "Q1" });
});

test("M6: walk Q1 -> back -> Q2 opens two threads; a follow-up typed inside keeps its id", () => {
  // A tiny in-memory service obeying the request the rule builds: no id -> create, an id -> append.
  const threads = new Map<string, string[]>();
  let n = 0;
  const post = (q: string, threadId: string | null) => {
    const id = threadId ?? `t-${++n}`;
    threads.set(id, [...(threads.get(id) ?? []), q]);
    return id;
  };
  let open: string | null = null;
  open = post("Q1", threadIdFor("landing", open));      // landing
  const first = open;
  open = post("Q2", threadIdFor("landing", open));      // back at the landing, the previous thread still "open" in memory
  assert.notEqual(open, first);
  assert.deepEqual(threads.get(open), ["Q2"]);          // Q1 absent from Q2's thread
  assert.equal(post("Q3", threadIdFor("thread", open)), open);
  assert.deepEqual(threads.get(open), ["Q2", "Q3"]);
});

test("M6: thread views are keyed by module and id, so another thread never reuses one", () => {
  assert.notEqual(threadViewKey("whatif", "wt-1"), threadViewKey("whatif", "wt-2"));
  assert.equal(threadViewKey("lenses", "L1"), "lenses:L1");
});

// ---------------------------------------------------------------- every landing goes through the rule (source checks)

const src = (p: string) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");

test("M6: What-If landing and library cards create through startFresh; the thread page is keyed by id", () => {
  const home = src("components/v5/whatif/home.tsx");
  assert.match(home, /whatif\.createThread\(startFresh\("whatif", body\)\)/);
  assert.doesNotMatch(home, /whatif\.ask\(/, "the landing never asks into an existing thread");
  assert.match(src("app/what-if/thread/[threadId]/page.tsx"), /key=\{threadViewKey\("whatif", threadId\)\}/);
});

test("M6: Lenses landing creates through startFresh; the lens page and its assistant are keyed", () => {
  assert.match(src("components/v5/lenses/home.tsx"), /lenses\.create\(startFresh\("lenses",/);
  assert.match(src("app/lenses/[lensId]/page.tsx"), /key=\{threadViewKey\("lenses", lensId\)\}/);
  assert.match(src("components/v5/lenses/lens-view.tsx"), /<LensAssistant key=\{threadViewKey\("lens-thread", lens\.thread_id\)\}/);
});

test("M6: Scorecard landing creates through startFresh; its thread page (which asks ?ask= once) is keyed", () => {
  assert.match(src("components/v5/scorecard/home.tsx"), /scorecard\.createThread\(startFresh\("scorecard",/);
  assert.match(src("app/scorecard-validation/thread/[threadId]/page.tsx"), /key=\{threadViewKey\("scorecard", threadId\)\}/);
});

test("M6: Deal Desk landing opens a new desk thread; its thread page is keyed", () => {
  assert.match(src("components/v5/dealdesk/desk-thread.tsx"), /threadFor\("landing"\)/);
  assert.match(src("components/v5/dealdesk/home.tsx"), /openDeskThread\(router, question\)/);
  assert.match(src("app/deal-desk/thread/[threadId]/page.tsx"), /key=\{threadViewKey\("dealdesk", threadId\)\}/);
});

test("M6: Playbook ?ask= starts with no thread id and resets a view that showed another thread", () => {
  const st = src("components/v5/playbook/start-thread.tsx");
  assert.match(st, /send\(initial, threadIdFor\("landing", threadId\)\)/);
  assert.match(st, /setMessages\(\[\]\);\s*\n\s*setTid\(null\);/);
  assert.match(src("components/v5/playbook/home.tsx"), /playbook\.start\(q, threadIdFor\("thread", threadId\)\)/);
});

test("M6: Noor and the Home Ask dispatch every question to a NEW engine thread", () => {
  const d = src("components/noor/noor-dispatch.ts");
  assert.match(d, /whatif\.createThread\(startFresh\("whatif",/);
  assert.match(d, /lenses\.create\(startFresh\("lenses",/);
  assert.match(d, /startRun\(startFresh\("cockpit",/);
  assert.match(d, /dealdesk\.newDeskThread\(q\)/);
  assert.match(src("components/home/home-ask.tsx"), /await dispatch\(engine, q,/);
});

test("M6: Early Warning and Borrower 360 ask bars hand the question to the Ask box (a new Cockpit thread), never a thread id", () => {
  const ml = src("components/v5/landing/module-landing.tsx");
  assert.match(ml, /router\.push\(`\/\?q=\$\{encodeURIComponent\(q\.trim\(\)\)\}`\)/);
  assert.doesNotMatch(ml, /thread_id|threadId/);
});
