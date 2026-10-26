import { test } from "node:test";
import assert from "node:assert/strict";

import { DROPDOWN, badgeTooltip, flatten, moveFocus, typeahead, visibleSections } from "./dropdown-model.ts";

const items = [
  { key: "a", label: "Documents" },
  { key: "b", label: "Group & SWOT", disabled: true },
  { key: "c", label: "Write proposal" },
  { key: "d", label: "Committee paper" },
];

test("house geometry (K28): min width 260, 32 px rows, 16 px icons", () => {
  assert.equal(DROPDOWN.minWidth, 260);
  assert.equal(DROPDOWN.rowHeight, 32);
  assert.equal(DROPDOWN.iconSize, 16);
});

test("arrow keys wrap and skip disabled rows", () => {
  assert.equal(moveFocus(items, -1, "ArrowDown"), 0);
  assert.equal(moveFocus(items, 0, "ArrowDown"), 2);
  assert.equal(moveFocus(items, 3, "ArrowDown"), 0);
  assert.equal(moveFocus(items, 0, "ArrowUp"), 3);
  assert.equal(moveFocus(items, 2, "ArrowUp"), 0);
  assert.equal(moveFocus(items, -1, "ArrowUp"), 3);
  assert.equal(moveFocus(items, 2, "Home"), 0);
  assert.equal(moveFocus(items, 0, "End"), 3);
  assert.equal(moveFocus(items, 2, "x"), 2);
});

test("no focusable row → -1", () => {
  assert.equal(moveFocus([{ key: "a", disabled: true }], -1, "ArrowDown"), -1);
  assert.equal(moveFocus([], -1, "ArrowDown"), -1);
});

test("typeahead finds the next row by first letter", () => {
  assert.equal(typeahead(items, -1, "c"), 3);
  assert.equal(typeahead(items, 0, "w"), 2);
  assert.equal(typeahead(items, 0, "g"), 0); // disabled row skipped, nothing else: unchanged
  assert.equal(typeahead(items, 0, "?"), 0);
});

test("sections: empty ones dropped; flatten keeps order", () => {
  const s = [{ title: "Deal file", items: items.slice(0, 2) }, { title: "Empty", items: [] }, { title: "Intelligence", items: items.slice(2) }];
  assert.deepEqual(visibleSections(s).map((x) => x.title), ["Deal file", "Intelligence"]);
  assert.deepEqual(flatten(s).map((x) => x.key), ["a", "b", "c", "d"]);
});

test("a count badge always carries its words (K28)", () => {
  assert.equal(badgeTooltip(8, "open item"), "8 open items");
  assert.equal(badgeTooltip(1, "open item"), "1 open item");
  assert.equal(badgeTooltip(3, "query"), "3 queries");
  assert.equal(badgeTooltip(2, "day"), "2 days");
  assert.equal(badgeTooltip(0, "open item"), null);
  assert.equal(badgeTooltip(null, "open item"), null);
});
