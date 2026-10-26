import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { goalOfTurn, isGoal } from "../agent-goal.ts";

// The same corpus the backend's goal detection is tested on (tests/v5/agents_whatif/goal_corpus.json).
const corpus = JSON.parse(readFileSync(new URL("../../../../../../tests/v5/agents_whatif/goal_corpus.json", import.meta.url), "utf8")) as
  { goals: string[]; single: string[] };

test("every goal in the corpus offers Run as agent", () => {
  for (const g of corpus.goals) assert.equal(isGoal(g), true, g);
});

test("no single-scenario prompt or data question offers it (the chat is unchanged for those)", () => {
  for (const s of corpus.single) assert.equal(isGoal(s), false, s);
});

test("a turn already run as an agent is not offered again", () => {
  const goal = "are we provisioned enough for an oil shock?";
  assert.equal(goalOfTurn(goal, new Set()), goal);
  assert.equal(goalOfTurn(goal, new Set([goal])), "");
  assert.equal(goalOfTurn(`Run as agent: ${goal}`, new Set()), "");
  assert.equal(goalOfTurn("oil price -40%", new Set()), "");
});
