import assert from "node:assert/strict";
import { test } from "node:test";

import { deskThreadHref, recentFirst, threadFor, titleFrom } from "./thread-rule.ts";

test("K16: every question from a landing, ask bar, Cockpit or a fresh Noor panel opens a new thread", () => {
  for (const o of ["landing", "ask-bar", "cockpit", "noor"] as const) {
    assert.deepEqual(threadFor(o, "T-1"), { kind: "new" }, o);
    assert.deepEqual(threadFor(o, null), { kind: "new" }, o);
  }
});

test("K16: only a question typed inside an open thread continues it", () => {
  assert.deepEqual(threadFor("thread", "T-1"), { kind: "continue", threadId: "T-1" });
  assert.deepEqual(threadFor("thread", null), { kind: "new" });
});

test("a title from the first question: one line, short, cut at a word", () => {
  assert.equal(titleFrom("  Which proposals\n breach a hard limit? "), "Which proposals breach a hard limit?");
  const long = titleFrom("word ".repeat(40));
  assert.ok(long.length <= 80 && long.endsWith("…"));
  assert.equal(titleFrom(""), "New thread");
});

test("Recent work: newest first", () => {
  const rows = recentFirst([{ id: "a", updated: 1 }, { id: "b", updated: 3 }, { id: "c", updated: 2 }]);
  assert.deepEqual(rows.map((r) => r.id), ["b", "c", "a"]);
});

test("Deal Desk thread URL has its own id, never thread=desk", () => {
  assert.equal(deskThreadHref("DK-1"), "/deal-desk/thread/DK-1");
  assert.equal(deskThreadHref("DK-1", "a b"), "/deal-desk/thread/DK-1?q=a%20b");
  assert.ok(!deskThreadHref("DK-1").includes("thread=desk"));
});
