import { test } from "node:test";
import assert from "node:assert/strict";

import { answerOrder, headline, isQueryQuestion, PREPARED_QUESTIONS } from "./cockpit-queries.ts";

test("auditor and regulator questions are queries", () => {
  assert.equal(isQueryQuestion("Answer the auditor's question on 30+ DPD loans still in Stage 1"), true);
  assert.equal(isQueryQuestion("Draft a response to the CBUAE on Stage 3 floors"), true);
  assert.equal(isQueryQuestion("Open letter Q4"), true);
  assert.equal(isQueryQuestion("q5"), true);
  for (const p of PREPARED_QUESTIONS) assert.equal(isQueryQuestion(p.question), true, p.question);
});

test("portfolio questions and product help stay with the Cockpit agent", () => {
  for (const q of [
    "What is driving Stage 2 and ECL growth?", "Which sectors deteriorated most this quarter?",
    "Show EAD by sector for the latest quarter.", "Which borrowers were downgraded this quarter?",
    "Why is risk building across the corporate book?", "Who are you?", "What can CreditProbe do?",
    "Why did construction ECL rise?", "",
  ]) assert.equal(isQueryQuestion(q), false, q);
});

test("the answer to the question leads, then the rest of the letter", () => {
  const order = answerOrder([{ n: 1 }, { n: 2 }, { n: 3 }], 2).map((a) => a.n);
  assert.deepEqual(order, [2, 1, 3]);
  assert.deepEqual(answerOrder([{ n: 1 }], 9).map((a) => a.n), [1]);
});

test("the headline is the first sentence, key figures kept bold", () => {
  assert.equal(headline("Stage 1 + 2 ECL is **SAR 1.67bn**, **2.78%** of CRWA. No shortfall."), "Stage 1 + 2 ECL is **SAR 1.67bn**, **2.78%** of CRWA.");
  assert.equal(headline("One line only"), "One line only");
});
