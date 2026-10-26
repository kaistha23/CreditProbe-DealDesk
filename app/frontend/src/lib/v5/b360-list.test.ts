/**
 * Unit tests for the Borrower 360 list state in the address. No network.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_SIZE, activeFilterCount, apiQuery, columnsStorageKey, listEntries, nextSort, pageCount, readList,
  visibleColumns, withFilter,
} from "./b360-list.ts";

const params = (s: string) => new URLSearchParams(s);

test("an empty address is page one of the whole book in the default order", () => {
  const s = readList(params(""));
  assert.equal(s.page, 1);
  assert.equal(s.size, DEFAULT_SIZE);
  assert.equal(s.sort, "");
  assert.deepEqual(listEntries(s), []);
  assert.deepEqual(apiQuery(s), { offset: 0, limit: DEFAULT_SIZE });
});

test("the list round-trips through the address", () => {
  const url = "q=gulf&segment=Construction&stage=2&ews=high&ead_min=5&sort=ead&dir=desc&page=3&size=100";
  const s = readList(params(url));
  assert.equal(s.filters.segment, "Construction");
  assert.equal(s.page, 3);
  assert.equal(new URLSearchParams(listEntries(s)).toString(), url);
  assert.deepEqual(apiQuery(s), { q: "gulf", segment: "Construction", stage: "2", ews: "high", ead_min: "5",
                                  sort: "ead", dir: "desc", offset: 200, limit: 100 });
});

test("bad page, size and direction fall back to the defaults", () => {
  const s = readList(params("page=-2&size=7&dir=up"));
  assert.equal(s.page, 1);
  assert.equal(s.size, DEFAULT_SIZE);
  assert.equal(s.dir, "");
});

test("a filter change goes back to page one and drops a sub-sector of another sector", () => {
  const s = readList(params("segment=Construction&subsegment=Civil%20Infrastructure&page=4"));
  const parent = (sub: string) => (sub === "Civil Infrastructure" ? "Construction" : "Healthcare");
  const t = withFilter(s, "segment", "Healthcare", parent);
  assert.equal(t.page, 1);
  assert.equal(t.filters.subsegment, "");
  const u = withFilter(s, "region", "Riyadh", parent);
  assert.equal(u.filters.subsegment, "Civil Infrastructure");
  assert.equal(activeFilterCount(u), 3);
});

test("sorting: figures start high, text starts at A, a second click flips", () => {
  const d = { sort: "ews_score", dir: "desc" };
  const s = readList(params("page=2"));
  const a = nextSort(s, "ead", true, d);
  assert.deepEqual([a.sort, a.dir, a.page], ["ead", "desc", 1]);
  const b = nextSort(a, "ead", true, d);
  assert.equal(b.dir, "asc");
  assert.equal(nextSort(s, "name", false, d).dir, "asc");
  assert.equal(nextSort(s, "ews_score", true, d).dir, "asc");
});

test("page count", () => {
  assert.equal(pageCount(5412, 50), 109);
  assert.equal(pageCount(0, 50), 1);
});

test("the column chooser keeps the id, ignores unknown keys and falls back to the defaults", () => {
  const all = [{ key: "id", default: true }, { key: "name", default: true }, { key: "group_name", default: false },
               { key: "ead", default: true }];
  assert.deepEqual(visibleColumns(all, null), ["id", "name", "ead"]);
  assert.deepEqual(visibleColumns(all, JSON.stringify(["ead", "group_name", "nope"])), ["id", "group_name", "ead"]);
  assert.deepEqual(visibleColumns(all, "not json"), ["id", "name", "ead"]);
  assert.deepEqual(visibleColumns(all, JSON.stringify(["nope"])), ["id", "name", "ead"]);
  assert.equal(columnsStorageKey("anne", "retail"), "cp.b360.list.columns.anne.retail");
});
