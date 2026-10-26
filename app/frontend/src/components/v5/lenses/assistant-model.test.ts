import { test } from "node:test";
import assert from "node:assert/strict";

import { POINTER, dashboardLines, stripRepeated } from "./assistant-model.ts";

const it = { headline: "Credit Card · Makkah, 2026-08: EAD SAR 64.8m.", lines: [{ text: "ECL rose SAR 0.62m to SAR 7.11m in 2026-08." }] };
const old = "**Makkah retail cards** · Credit Card · Makkah · as of 2026-08\n\nCredit Card · Makkah, 2026-08: EAD SAR 64.8m.\n- ECL rose SAR 0.62m to SAR 7.11m in 2026-08.\n\n8 KPIs and 12 tiles on the lens.";

test("the assistant does not repeat the dashboard interpretation", () => {
  const md = stripRepeated(old, dashboardLines(it));
  assert.ok(!md.includes("ECL rose") && !md.includes("EAD SAR 64.8m"), md);
  assert.ok(md.startsWith("**Makkah retail cards**") && md.includes(POINTER) && md.includes("8 KPIs and 12 tiles"));
});

test("answers that do not repeat it are untouched", () => {
  const md = "Done. Added DSCR distribution.\n\nThe lens now has 13 tiles.";
  assert.equal(stripRepeated(md, dashboardLines(it)), md);
  assert.equal(stripRepeated(old, []), old);
});
