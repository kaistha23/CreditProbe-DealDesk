// PLAN_R5 P2: assistant markdown becomes real parts; tables are never raw pipes.
import assert from "node:assert/strict";
import { test } from "node:test";

import { hasRichMarkdown, numericColumn, parseMarkdown } from "./markdown.ts";

const SCREEN_04 = `## Rating distribution of ECL — 2026Q2

**Rating grade table (drop-in for the section)**

| Rating grade | Borrowers | % EAD |
|---|---|---|
| AA to A- | 677 | 12.0% |
| CCC and below | 408 | 7.9% |

**Proposed wording**

> ECL remains concentrated in the weakest grades.
>
> The build is spread across the curve.

**Detail worth naming in the text**
- B+ is the single largest mover
- CCC is the staging watch item`;

test("a pipe table is a table part with its header and rows", () => {
  const parts = parseMarkdown(SCREEN_04);
  assert.deepEqual(parts.map((p) => p.type), ["heading", "paragraph", "table", "paragraph", "quote", "paragraph", "list"]);
  const t = parts[2];
  assert.ok(t.type === "table");
  assert.deepEqual(t.header, ["Rating grade", "Borrowers", "% EAD"]);
  assert.deepEqual(t.rows[1], ["CCC and below", "408", "7.9%"]);
});

test("quotes lose their markers; a label right above a list is its own paragraph", () => {
  const parts = parseMarkdown(SCREEN_04);
  const q = parts[4];
  assert.ok(q.type === "quote");
  assert.deepEqual(q.paragraphs, ["ECL remains concentrated in the weakest grades.", "The build is spread across the curve."]);
  const l = parts[6];
  assert.ok(l.type === "list" && l.items.length === 2);
});

test("rich markdown is detected; figures columns align as numbers", () => {
  assert.ok(hasRichMarkdown(SCREEN_04));
  assert.ok(!hasRichMarkdown("Plain **bold** text."));
  assert.ok(numericColumn(["677", "1,596", "SAR 3.89bn", "+64.2", "12.0%"]));
  assert.ok(!numericColumn(["AA to A-", "BBB"]));
});
