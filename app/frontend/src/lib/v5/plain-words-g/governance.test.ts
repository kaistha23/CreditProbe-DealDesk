import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import { writeDoa, writeExceptions, writeRmTrack } from "./governance.ts";

const load = (f: string) => JSON.parse(readFileSync(new URL(`./fixtures/${f}.json`, import.meta.url), "utf8"));

const cases: [string, string, (d: never) => string[], RegExp][] = [
  ["exceptions", "gov-exceptions", writeExceptions as (d: never) => string[], /8\.1%/],
  ["rm-track", "gov-rm-track", writeRmTrack as (d: never) => string[], /91 RMs/],
  ["doa", "gov-doa", writeDoa as (d: never) => string[], /6,666 files/],
];

for (const [name, fx, write, number] of cases) {
  test(`governance plain words (${name}): K34 rules, a number from the panel, demo seed said`, () => {
    const d = load(fx);
    const l = write(d as never);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4);
    assert.match(l.join(" "), number);
    assert.match(l.join(" "), /demo seed/);
    assert.deepEqual(write(d as never), l);
  });
}

test("RM track record names the weakest ranked RM when one scores below 50", () => {
  const d = load("gov-rm-track");
  d.rows.push({ ...d.rows[0], id: "RM9999", name: "Dana Al-Bishi", score: 11, oe: 2.08, thin: false });
  const l = writeRmTrack(d);
  assert.match(l.join(" "), /Coach Dana Al-Bishi first: score 11, defaults 2\.1 times/);
  assert.ok(checkPlainWords(l).ok, l.join(" | "));
});
