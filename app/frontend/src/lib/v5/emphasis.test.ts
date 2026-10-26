import { test } from "node:test";
import assert from "node:assert/strict";

import { emphasise, hasEmphasis } from "./emphasis.ts";

test("figures in prose are bolded when the answer has no emphasis", () => {
  const out = emphasise("Construction is SAR 18,695 million of the book, 12.16% of EAD, up 45 bps; DSCR 1.61x.");
  assert.match(out, /\*\*SAR 18,695 million\*\*/);
  assert.match(out, /\*\*12\.16%\*\*/);
  assert.match(out, /\*\*45 bps\*\*/);
  assert.match(out, /\*\*1\.61x\*\*/);
});

test("an answer that already has emphasis is unchanged", () => {
  const s = "**Yes** — RAROC is 28.1%.";
  assert.equal(emphasise(s), s);
});

test("tables, headings and code are left alone", () => {
  const s = "| a | 12% |\n|---|---|\n## 5% heading\n`LGD 45%`\nFinal 3.2%";
  const out = emphasise(s);
  assert.ok(out.startsWith("| a | 12% |\n|---|---|\n## 5% heading\n`LGD 45%`\n"));
  assert.match(out, /Final \*\*3\.2%\*\*/);
});

test("hasEmphasis says whether a strong will render", () => {
  assert.equal(hasEmphasis("No figures here."), false);
  assert.equal(hasEmphasis("RAROC 21.4%"), true);
});
