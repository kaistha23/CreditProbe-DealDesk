import assert from "node:assert/strict";
import { test } from "node:test";

import { ASK_PLACEHOLDER, STARTERS, startersFor, tabFrom } from "./starters.ts";
import { engineFor } from "../noor/noor-route.ts";

const P = (o: Record<string, string>) => ({ get: (k: string) => o[k] ?? null });

test("Brief is the landing tab; Ask by ?tab=ask or a question in the address", () => {
  assert.equal(tabFrom(P({})), "brief");
  assert.equal(tabFrom(P({ tab: "ask" })), "ask");
  assert.equal(tabFrom(P({ q: "ECL by stage" })), "ask");
  assert.equal(tabFrom(P({ tab: "brief", q: "x" })), "brief");
});

test("four to six starters per book, on the book's calendar, reaching more than one engine", () => {
  for (const book of ["corporate", "retail"] as const) {
    const s = startersFor(book, book === "corporate" ? "quarter" : "month");
    assert.ok(s.length >= 4 && s.length <= 6);
    assert.ok(s.every((x) => !x.includes("{period}")));
    assert.ok(new Set(s.map(engineFor)).size >= 2, book);
  }
  assert.ok(startersFor("corporate", "quarter")[0].endsWith("this quarter"));
  assert.equal(STARTERS.corporate.length, 6);
});

test("the placeholder is the one Anne asked for", () => {
  assert.equal(ASK_PLACEHOLDER, "Ask me anything, from ECL decomposition to early warning…");
});
