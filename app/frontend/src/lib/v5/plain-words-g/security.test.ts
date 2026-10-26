import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import type { Security } from "../../../components/v5/dealdesk/intel/approval/model.ts";
import { writeSecurity } from "./security.ts";

const load = (n: string) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8")) as Security;

for (const f of ["security", "security-twa"]) {
  test(`security value plain words (${f})`, () => {
    const s = load(f);
    const l = writeSecurity(s);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4);
    assert.match(l.join(" "), /SAR \d|\d+\.\d%/);
    if (s.needs_price) assert.match(l.join(" "), /Make it approvable/);
    assert.deepEqual(writeSecurity(s), l);
  });
}
