import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import type { InspectionPack } from "../intel-governance.ts";
import { writeInspection, writeInspectionEmpty } from "./inspection.ts";

const pack = JSON.parse(readFileSync(new URL("./fixtures/inspection.json", import.meta.url), "utf8")) as InspectionPack;

test("inspection responder plain words: result names count, EAD and the pack reference", () => {
  const l = writeInspection(pack);
  const c = checkPlainWords(l);
  assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
  assert.ok(l.join(" ").includes(pack.pack_id));
  assert.match(l.join(" "), /5 borrowers, SAR [\d,.]+m EAD/);
  assert.match(l.join(" "), /demo register/);
  assert.deepEqual(writeInspection(pack), l);
});

test("inspection responder plain words: empty state says when to use it and what you get", () => {
  const l = writeInspectionEmpty(3);
  const c = checkPlainWords(l);
  assert.ok(c.ok, c.problems.join("; "));
  assert.match(l[0], /regulator, an auditor or internal audit/);
  assert.match(l.join(" "), /Word pack and an Excel/);
});

test("the fixture carries the K15 answers", () => {
  assert.equal(pack.answers?.length, 5);
  for (const a of pack.answers ?? []) {
    assert.ok(a.href?.startsWith("/borrower-360?") && a.stage_path && a.approval?.text && a.conditions?.text);
  }
});
