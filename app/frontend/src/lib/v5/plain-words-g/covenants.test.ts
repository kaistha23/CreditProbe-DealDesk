import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import type { CovenantDesign } from "../intel-ib.ts";
import { writeCovenants } from "./covenants.ts";

const load = (n: string) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8")) as CovenantDesign;

for (const f of ["covenants", "covenants-dd02"]) {
  test(`covenant designer plain words (${f}): passes the K34 rules and names the panel's numbers`, () => {
    const d = load(f);
    const l = writeCovenants(d);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4);
    const rec = d.covenants.find((x) => x.recommended);
    if (rec) assert.ok(l.join(" ").includes(rec.proposed.threshold.toFixed(2)) || l.join(" ").includes(`${rec.proposed.threshold.toFixed(0)}%`));
    assert.match(l.join(" "), /Early Warning/);
    assert.deepEqual(writeCovenants(d), l); // deterministic
  });
}
