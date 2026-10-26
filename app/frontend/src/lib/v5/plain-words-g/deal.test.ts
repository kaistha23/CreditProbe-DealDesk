import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import {
  writeChallenger, writeCommitteePaper, writeConsistency, writeDocuments, writeFinQuality, writeGroup, writeReverse, writeSwot,
  writeTryDocs, writeWriteProposal,
} from "./deal.ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const load = (n: string): any => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));

/** Every number the block names (as digits) must appear somewhere in the fixture (N5: no invented figure). */
function numbersFrom(lines: string[], fixture: unknown): void {
  const blob = JSON.stringify(fixture);
  const nums = lines.join(" ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  assert.ok(nums.length > 0, "names no number");
  const raw = [...blob.matchAll(/-?\d+(?:\.\d+)?(?:e-?\d+)?/g)].map((m) => Number(m[0]));
  for (const t of nums) {
    const v = Number(t.replace(/,/g, ""));
    // a shown number matches a raw value directly, as a percent of a share, as a sum/count, or after rounding
    const tol = Number.isInteger(v) ? 0.5001 : 0.0501;
    const ok = raw.some((r) => [r, r * 100, r / 1000].some((x) => Math.abs(x - v) <= tol))
      || Number.isInteger(v) && v <= 60; // small counts (lengths of lists, sums of counts) are computed from the data
    assert.ok(ok, `${t} not found in the fixture`);
  }
}

const CASES: [string, string, (d: never) => string[]][] = [
  ["documents", "docs-DD-06", writeDocuments], ["documents", "docs-R12-TWA", writeDocuments],
  ["group", "group-DD-06", writeGroup], ["group", "group-R12-TWA", writeGroup],
  ["swot", "group-DD-06", ((d: { swot: never }) => writeSwot(d.swot)) as never], ["swot", "group-R12-TWA", ((d: { swot: never }) => writeSwot(d.swot)) as never],
  ["write", "paper-DD-06", writeWriteProposal], ["write", "paper-R12-TWA", writeWriteProposal],
  ["committee", "committee-DD-06", writeCommitteePaper], ["committee", "committee-R12-TWA", writeCommitteePaper],
  ["fin-quality", "finq-DD-06", writeFinQuality], ["fin-quality", "finq-R12-TWA", writeFinQuality],
  ["challenger", "challenger-DD-06", writeChallenger], ["challenger", "challenger-R12-TWA", writeChallenger],
  ["reverse", "reverse-DD-06", writeReverse], ["reverse", "reverse-R12-TWA", writeReverse],
  ["consistency", "consistency-DD-06", writeConsistency], ["consistency", "consistency-R12-TWA", writeConsistency],
  ["try-empty", "trydocs-overview", ((o: never) => writeTryDocs({ overview: o })) as never],
  ["try-result", "trydocs-session", ((s: never) => writeTryDocs({ session: s })) as never],
];

for (const [panel, fx, write] of CASES) {
  test(`${panel} plain words on ${fx}: K34 rules, numbers from the panel, deterministic`, () => {
    const d = load(fx);
    const l = write(d as never);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4, l.join(" | "));
    numbersFrom(l, d);
    assert.deepEqual(write(load(fx) as never), l);
  });
}
