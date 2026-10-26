import { test } from "node:test";
import assert from "node:assert/strict";

import { checkPlainWords, glossFirstUse, spokenText, wordCount } from "./plain-words-model.ts";

const covenant = [
  "This checks which covenant levels would have warned early on similar borrowers.",
  "Set current ratio at 1.40x and DSCR at 1.60x: they would have warned 3 quarters early on 4 in 10 bad cases.",
  "Today's levels leave little cushion, so agree headroom with the client.",
];

test("jargon is explained on first use only", () => {
  const g = glossFirstUse(["RAROC is 14.5% against 15.0%.", "Raise RAROC by pricing."]);
  assert.match(g[0], /^RAROC \(return on the capital the risk uses\) is 14\.5%/);
  assert.equal(g[1], "Raise RAROC by pricing.");
});

test("an existing explanation is not doubled; words inside other words never match", () => {
  const g = glossFirstUse(["RAROC (return on risk capital) is 14.5%; data updated today."]);
  assert.equal(g[0], "RAROC (return on risk capital) is 14.5%; data updated today.");
});

test("K34 rules: a good block passes", () => {
  const c = checkPlainWords(covenant);
  assert.equal(c.ok, true, c.problems.join("; "));
  assert.ok(c.words <= 60);
});

test("K34 rules: too long, too many lines, no number, debug text", () => {
  const long = Array.from({ length: 70 }, () => "word").join(" ");
  assert.ok(checkPlainWords([long, "1"]).problems.some((p) => /words/.test(p)));
  assert.ok(checkPlainWords(["a 1", "b", "c", "d", "e"]).problems.some((p) => /lines/.test(p)));
  assert.ok(checkPlainWords(["No numbers here at all."]).problems.some((p) => /number/.test(p)));
  assert.ok(checkPlainWords(["Value is undefined 3"]).problems.some((p) => /debug/.test(p)));
});

test("unexplained jargon fails when glossing is off", () => {
  const c = checkPlainWords(["LGD is 45%."], { glossed: false });
  assert.ok(c.problems.some((p) => /LGD/.test(p)));
});

test("glosses do not count against the 60 words", () => {
  const lines = glossFirstUse(["RAROC 14.5%, SVA SAR -0.05m, LGD 17%, PD 0.84%, EAD SAR 170m, ECL SAR 2m."]);
  assert.ok(wordCount(lines) > 30);
  assert.equal(checkPlainWords(lines).ok, true);
});

test("spoken text reads units", () => {
  assert.equal(spokenText(["Shortfall SAR 878.5m", "Leverage 3.98x vs 4.00x"]),
    "Shortfall SAR 878.5 million. Leverage 3.98 times vs 4.00 times.");
  assert.equal(spokenText(["Up 40bps, 0.5pp below hurdle; book SAR 1.73bn"]),
    "Up 40 basis points, 0.5 percentage points below hurdle; book SAR 1.73 billion.");
});
