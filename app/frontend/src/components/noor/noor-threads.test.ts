import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_THREADS, type Turn, addThreadTurn, findThread, historyOf, lineKey, newThread, putThread, restoreThreads,
  spokenSummary,
} from "./noor-model.ts";

const ask = (text: string): Turn => ({ id: `q-${text}`, kind: "ask", text, module: "cockpit" });

test("K7: a fresh thread is empty and scoped to the page", () => {
  const th = newThread("ews");
  assert.equal(th.turns.length, 0);
  assert.equal(th.module, "ews");
  assert.equal(th.key, null);
});

test("K5: each brief line has its own thread; reopening the line resumes it", () => {
  let threads = [] as ReturnType<typeof newThread>[];
  const a = addThreadTurn(newThread("cockpit", lineKey({ id: "crm:CRM-9.23" }), "Stage 3 floor"), ask("Why? Stage 3 floor"));
  threads = putThread(threads, a);
  const b = addThreadTurn(newThread("cockpit", lineKey({ id: "crm:CRM-6.12" }), "Cross-default"), ask("Why? Cross-default"));
  threads = putThread(threads, b);
  assert.notEqual(a.id, b.id);
  assert.equal(findThread(threads, "line:crm:CRM-9.23")?.id, a.id);
  // the second line's Why is not in the first line's thread
  assert.ok(!findThread(threads, "line:crm:CRM-9.23")!.turns.some((t) => t.kind === "ask" && t.text.includes("Cross-default")));
  // history: every other thread that holds something, newest first
  assert.deepEqual(historyOf(threads, b.id).map((t) => t.id), [a.id]);
});

test("K16: a new thread takes its first question as its title", () => {
  const th = addThreadTurn(newThread("cockpit"), ask("Which sectors are over appetite?"));
  assert.equal(th.title, "Which sectors are over appetite?");
  const again = addThreadTurn(th, ask("And in retail?"));
  assert.equal(again.title, "Which sectors are over appetite?");
});

test("threads are capped and survive a reload without pending turns", () => {
  let threads = [] as ReturnType<typeof newThread>[];
  for (let i = 0; i < MAX_THREADS + 5; i++) threads = putThread(threads, { ...newThread("x"), updated: i });
  assert.equal(threads.length, MAX_THREADS);
  const th = { ...newThread("x"), turns: [ask("q"), { id: "p1", kind: "pending", text: "…" } as Turn] };
  const back = restoreThreads(JSON.stringify({ threads: [th], current: th.id }));
  assert.equal(back.current, th.id);
  assert.equal(back.threads[0].turns.length, 1);
  assert.deepEqual(restoreThreads("not json"), { threads: [], current: null });
});

test("K10: an answer's spoken summary reads its prose, not its tables", () => {
  const prose = "Construction ECL rose SAR 120.5m this quarter.\nSector\tECL\tChange\nConstruction 1,234 12%\n"
    + "Most of the rise comes from Stage 2 migration in contractors.";
  const s = spokenSummary(prose);
  assert.match(s, /120.5 million riyals/);
  assert.match(s, /Stage 2 migration/);
  assert.ok(!s.includes("1,234"));
});
