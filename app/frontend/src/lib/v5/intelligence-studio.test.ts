import { test } from "node:test";
import assert from "node:assert/strict";

import { count, coverageBars, pct, readerSeries, secs, stageLabel, tokens, type Customers, type Reader } from "./intelligence-studio.ts";

test("counts show a dash when the store is absent, never a zero", () => {
  assert.equal(count(null), "–");
  assert.equal(count(undefined), "–");
  assert.equal(count(0), "0");
  assert.equal(count(1234), "1,234");
});

test("percent, tokens and seconds", () => {
  assert.equal(pct(92.45), "92.5%");
  assert.equal(pct(100), "100%");
  assert.equal(pct(null), "–");
  assert.equal(tokens(38250), "38.3k");
  assert.equal(tokens(5157), "5,157");
  assert.equal(secs(4210), "4.2 s");
});

test("stage labels in plain words", () => {
  assert.equal(stageLabel("ENGINE_FIRST_WRITE"), "Writing from the engine's results (one call)");
  assert.equal(stageLabel("BANKFORM_POLISH"), "Bankform polish");
});

test("the reader series keeps only weeks with documents", () => {
  const p = (period: string, documents: number, acc: number | null) => ({ period, documents, readable: documents, corrected: 0, recon_agrees: 0,
    recon_differs: 0, recon_flags: 0, fields_read: 0, fields_confirmed: 0, fields_offered: 0, fields_flagged: 0, reader_accuracy_pct: acc, field_agreement_pct: null });
  const r = { periods: [p("2026-W42", 0, null), p("2026-W43", 5, 80)], totals: p("", 5, 80), field_states: false } as unknown as Reader;
  assert.deepEqual(readerSeries(r), { x: ["2026-W43"], accuracy: [80], documents: [5] });
});

test("coverage bars follow the source order", () => {
  const c = { coverage: [{ source: "deal_register", label: "Deal register (LOS)", customers: 52, pct: 98.1 },
                         { source: "bureau", label: "Bureau", customers: 10, pct: 18.9 }] } as unknown as Customers;
  assert.deepEqual(coverageBars(c).map((b) => b.label), ["Deal register (LOS)", "Bureau"]);
});
