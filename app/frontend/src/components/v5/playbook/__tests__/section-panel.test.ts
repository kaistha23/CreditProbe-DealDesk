import assert from "node:assert/strict";
import { test } from "node:test";

import type { Message } from "../../../../lib/v5/playbook.ts";
import { canInsert, mergedOf, panelChips } from "../section-panel.ts";

const msg = (id: string, role: "user" | "assistant", actions: Message["actions"] = [], suggestions: string[] = []): Message =>
  ({ id, role, at: "2026-10-13T09:00:00Z", author: null, text: id, actions, suggestions }) as Message;

test("an answer that proposes report content offers Insert into this section until it is inserted", () => {
  const answer = msg("m2", "assistant", [{ kind: "answer", label: "" }, { kind: "can_apply", label: "Portfolio overview", section_id: "s1" }]);
  assert.equal(canInsert(answer, {}), true);
  assert.equal(canInsert(msg("m1", "user"), {}), false);
  assert.equal(canInsert(msg("m3", "assistant", [{ kind: "answer", label: "", refused: true }]), {}), false);
  const merged = { m2: { version: 7, where: "at the end" } };
  assert.equal(canInsert(answer, merged), false);
  assert.deepEqual(mergedOf(answer, merged), { version: 7, where: "at the end" });
});

test("a stored merge is read back from the thread", () => {
  const done = msg("m4", "assistant", [{ kind: "merged", label: "Scenarios", version: 3, where: "at the end" } as never]);
  assert.deepEqual(mergedOf(done, {}), { version: 3, where: "at the end" });
  assert.equal(mergedOf(msg("m5", "assistant"), {}), null);
});

test("the chips follow the last answer, else the section starters, at most four", () => {
  const starters = ["What should go in this section?", "ECL by sector", "Draft it from the data", "What drove ECL this quarter?", "Extra"];
  assert.deepEqual(panelChips([], starters), starters.slice(0, 4));
  assert.deepEqual(panelChips([msg("a", "assistant", [], ["Show it as a chart"])], starters), ["Show it as a chart"]);
  assert.deepEqual(panelChips([], undefined), []);
});
