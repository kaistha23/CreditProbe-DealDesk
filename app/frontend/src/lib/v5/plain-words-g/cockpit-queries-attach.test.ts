import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (p: string) => readFileSync(new URL(`../../../${p}`, import.meta.url), "utf8");

test("FX-R14-01: the Cockpit home renders the queries control without the attach row", () => {
  const home = src("components/cockpit-v4/cockpit-v4-home.tsx");
  assert.match(home, /<CockpitQueries state=\{v5q\} attach=\{false\} \/>/);
  const q = src("components/v5/queries/cockpit.tsx");
  assert.match(q, /attach = true/);
  assert.match(q, /\{attach \? <div className="relative flex flex-wrap/);
});
