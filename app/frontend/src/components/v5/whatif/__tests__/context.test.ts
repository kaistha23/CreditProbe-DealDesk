import assert from "node:assert/strict";
import { test } from "node:test";

import { checkPlainWords } from "../../ui/plain-words-model.ts";
import { TILE_KEYS, contextHeading, contextTiles, trendCell } from "../context.ts";

const fig = (key: string, value: number) => ({ key, label: key, value, unit: "sar_mn" as const, text: String(value) });

test("R16 m M4: the context tiles come in reading order and skip what the block lacks (book: no share)", () => {
  const figures = [fig("ecl", 5), fig("warned_owners", 3), fig("ead", 100), fig("stage3_ead", 7), fig("stage2_ead", 20), fig("owners", 9)];
  assert.deepEqual(contextTiles({ figures }).map((f) => f.key), ["ead", "stage2_ead", "stage3_ead", "ecl", "warned_owners"]);
  assert.deepEqual(contextTiles({ figures: [...figures, fig("share_pct", 12)] }).map((f) => f.key), [...TILE_KEYS]);
});

test("R16 m M4: heading names the subject and period; trend cells carry units", () => {
  assert.equal(contextHeading({ title: "Construction", period: "2026Q2" }), "Construction today · 2026Q2");
  assert.equal(trendCell("ead", 18695.2), "18.70bn");
  assert.equal(trendCell("ecl", 896.6), "896.6m");
  assert.equal(trendCell("stage23_pct", 79.21), "79.2%");
  assert.equal(trendCell("period", "2026Q2"), "2026Q2");
});

test("R16 m M4: the backend's plain-words lines pass the shared block's rules", () => {
  const lines = ["Construction: SAR 18.70bn lent, 12% of the book.", "79% is in Stage 2 or 3 (showing stress); ECL SAR 2.76bn.",
                 "Early Warning flags 383 borrowers.", "Stage 2+3 share rose from 57% to 79% since 2025Q2."];
  const c = checkPlainWords(lines);
  assert.ok(c.ok, c.problems.join("; "));
});
