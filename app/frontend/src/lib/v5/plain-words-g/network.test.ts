import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import { writeContagion, writeEmployer, writeEmployerRanking, writeEvent } from "./network.ts";

const load = (f: string) => JSON.parse(readFileSync(new URL(`./fixtures/${f}.json`, import.meta.url), "utf8"));

const cases: [string, string, (d: never) => string[], RegExp][] = [
  ["contagion", "net-contagion", writeContagion as (d: never) => string[], /SAR 195m/],
  ["employer", "net-employer", writeEmployer as (d: never) => string[], /SAR 167m/],
  ["event", "net-event", writeEvent as (d: never) => string[], /\+SAR 87\.0m/],
  ["employers", "net-employers", writeEmployerRanking as (d: never) => string[], /Turaif First Properties leads: SAR 34\.3m/],
];

for (const [name, fx, write, number] of cases) {
  test(`network plain words (${name}): K34 rules and a number from the panel`, () => {
    const d = load(fx);
    const l = write(d as never);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4);
    assert.match(l.join(" "), number);
    assert.deepEqual(write(d as never), l);
  });
}

test("contagion with no linked names still writes a block with a number", () => {
  const d = load("net-contagion");
  d.totals.names = 0; d.names = [];
  const l = writeContagion(d);
  assert.ok(checkPlainWords(l).ok, l.join(" | "));
});
