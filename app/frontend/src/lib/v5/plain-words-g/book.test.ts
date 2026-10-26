import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import { writeCalls, writeEclBridge, writeExits, writeHeadroom, writeRenewals, writeRwa, writeWorkout } from "./book.ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const load = (n: string): any => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));

const CASES: [string, string, (d: never) => string[]][] = [
  ["headroom", "headroom", writeHeadroom], ["exits", "exits", writeExits], ["rwa", "rwa", writeRwa],
  ["ecl-bridge", "ecl-bridge", writeEclBridge], ["workout", "workout", writeWorkout],
  ["renewals", "renewals", writeRenewals], ["calls", "calls", writeCalls],
];

for (const [name, fx, w] of CASES) {
  test(`${name} plain words: K34 rules, 3–4 lines, a number from the panel, deterministic`, () => {
    const d = load(fx);
    const l = w(d as never);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4, l.join(" | "));
    assert.ok(/\d/.test(l.join(" ")));
    assert.ok(!/n\/a/.test(l.join(" ")), l.join(" | "));
    assert.deepEqual(w(d as never), l);
  });
}

test("who to call and renewals say they show material names and what stays in the full list", () => {
  const c = writeCalls(load("calls")).join(" ");
  assert.match(c, /material names \(owing at least SAR 50m\)/);
  assert.match(c, /2,405 smaller names/);
  const r = writeRenewals(load("renewals")).join(" ");
  assert.match(r, /242 material renewals/);
  assert.match(r, /4,789 smaller renewals/);
});

test("ECL bridge names the base forecast and the moderate stress path", () => {
  const t = writeEclBridge(load("ecl-bridge")).join(" ");
  assert.match(t, /Base path: SAR 7\.9bn/);
  assert.match(t, /moderate stress scenario it reaches SAR 8\.3bn/);
});

test("whole-book scope is worded as such", () => {
  const d = { ...load("calls"), scope: "all" };
  assert.match(writeCalls(d).join(" "), /in the whole book/);
});
