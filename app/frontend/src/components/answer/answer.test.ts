import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { TOOL_PHRASES, bankerChips, bankerLabel, bankerText, hasInternalName } from "./banker.ts";
import { figuresIn, foldProse, plainHeadline, splitHeadline } from "./headline.ts";

test("I9: the chips from the R11 feedback read in banker language", () => {
  assert.equal(bankerLabel("Run pipeline_optimise on the book"), "Optimise the pipeline on the book");
  assert.equal(bankerLabel("Re-test with pipeline_test"), "Re-test with the pipeline test");
  assert.equal(bankerLabel("`stress_lab` at two notches"), "The stress lab at two notches");
  assert.equal(bankerLabel("Show ead_sar_mn by stage_2_share"), "Show EAD SAR million by stage 2 share");
  assert.ok(!hasInternalName(bankerLabel("Then call whatif_run_scenario and fetch_group_exposure")));
});

test("ordinary English that happens to be a tool name is left alone", () => {
  for (const s of ["Optimise", "Compare the counter-offers", "How does this hold if we stress revenue?", "What are my options?",
    "Use the headroom left in construction"]) assert.equal(bankerText(s), s);
});

test("every snake_case tool has both phrases, and no phrase is itself a tool name", () => {
  for (const [name, [action, noun]] of Object.entries(TOOL_PHRASES)) {
    assert.ok(action && noun, name);
    assert.ok(!hasInternalName(`${action} ${noun}`), name);
    assert.ok(!/_/.test(action + noun), name);
  }
});

test("chips: mapped, deduplicated, empty ones dropped, at most four, the sent text mapped too", () => {
  const out = bankerChips([{ label: "Run pipeline_test", send: "Run pipeline_test now" }, { label: "Test against the pipeline", send: "x" },
    { label: "" }, { label: "Why does the ask fail?", send: "Why does the ask fail?" }, { label: "A" }, { label: "B" }, { label: "C" }]);
  assert.deepEqual(out.map((c) => c.label), ["Test against the pipeline", "Why does the ask fail?", "A", "B"]);
  assert.equal(out[0].send, "Test against the pipeline now");
});

test("a long chip is cut at a word with an ellipsis", () => {
  const l = bankerLabel("How does the recommended structure hold if the obligor is downgraded by two notches next year?", 40);
  assert.ok(l.length <= 40 && l.endsWith("…"), l);
});

test("the headline is the first sentence, a lead-in label dropped, numbers unsplit", () => {
  const h = splitHeadline("**Answer:** Lifetime RAROC is 14.2%, below the 15.0% hurdle. The ask fails on margin.\n\nDetail follows.");
  assert.equal(h.headline, "Lifetime RAROC is 14.2%, below the 15.0% hurdle.");
  assert.equal(h.rest, "The ask fails on margin.\n\nDetail follows.");
  assert.equal(splitHeadline("ECL rises to SAR 1.25 bn, about 1.5x, e.g. in construction. Stage 2 grows.").headline, "ECL rises to SAR 1.25 bn, about 1.5x, e.g. in construction.");
});

test("an answer opening with a table, list or heading has no headline", () => {
  for (const s of ["| a | b |\n|---|---|\n| 1 | 2 |", "- one\n- two", "## Heading\n\ntext"]) {
    assert.equal(splitHeadline(s).headline, "", s);
    assert.equal(splitHeadline(s).rest, s);
  }
});

test("a bold run cut by the headline stays balanced; plain headline drops markers", () => {
  const h = splitHeadline("**The ask fails. It needs 40 bps more.** Then more.");
  assert.equal((h.headline.match(/\*\*/g) ?? []).length % 2, 0);
  assert.equal((h.rest.match(/\*\*/g) ?? []).length % 2, 0);
  assert.equal(plainHeadline("**Answer:** RAROC is **14.2%**. More."), "RAROC is 14.2%.");
});

test("a long body folds behind Show more; a short one never does", () => {
  const long = Array.from({ length: 8 }, (_, i) => `Paragraph ${i} ${"word ".repeat(40).trim()}`).join("\n\n");
  const f = foldProse(long);
  assert.ok(f.more && f.hidden > 0 && f.open.length < long.length);
  assert.equal(`${f.open}\n\n${f.more}`, long, "nothing is lost");
  assert.equal(foldProse("One.\n\nTwo.").more, "");
});

test("key figures are found in prose", () => {
  assert.deepEqual(figuresIn("RAROC **14.2%** vs 15%, SAR 2.5 bn, +35 bps, 3 notches"), ["14.2%", "15%", "SAR 2.5 bn", "+35 bps", "3 notches"]);
});

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");

test("the renderer is exported with the theme, and adopted by every conversational layer", () => {
  const index = src("./index.ts");
  for (const name of ["Answer", "AnswerFrame", "AnswerProse", "AnswerTable", "AnswerChart", "AnswerFigures", "AnswerChips", "AnswerHeadline", "bankerChips", "Plot"]) {
    assert.ok(new RegExp(`\\b${name}\\b`).test(index), name);
  }
});
