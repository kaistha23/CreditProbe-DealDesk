import assert from "node:assert/strict";
import test from "node:test";

import { type Signal, cellUnit, dmy, evidenceLine, fmtValue, isOpen, signalLine, sourceLine, tabs } from "./dealdesk-b360.ts";

test("values print in their unit", () => {
  assert.equal(fmtValue(12.449, "sar_mn"), "SAR 12.4m");
  assert.equal(fmtValue(14500000, "sar"), "SAR 14.5m");
  assert.equal(fmtValue(81.25, "pct"), "81.3%");
  assert.equal(fmtValue(3, "count"), "3");
  assert.equal(fmtValue("2026-10-21", "date"), "21 Oct 2026");
  assert.equal(fmtValue(null, "sar_mn"), "–");
  assert.equal(fmtValue("classified_substandard", "text"), "classified substandard");
  assert.equal(dmy("2026Q2"), "2026Q2");
});

test("a row can carry its own unit", () => {
  assert.equal(cellUnit({ key: "value", label: "Value", unit: "@unit" }, { unit: "sar" }), "sar");
  assert.equal(cellUnit({ key: "v", label: "V", unit: "pct" }, {}), "pct");
});

test("every fact names where it was read and when", () => {
  assert.equal(sourceLine({ label: "Account conduct", relation: "dd_account_conduct", domain: "deal_desk", date: "2026-08-28" }),
               "Account conduct · deal_desk.dd_account_conduct · 28 Aug 2026");
  assert.equal(sourceLine({ label: "Top customers", doc_label: "C2-25 · Top customers and suppliers", page: 1, line: 18, date: "2026-09-30", synthetic: true }),
               "C2-25 · Top customers and suppliers, page 1, line 18 · 30 Sep 2026 · seeded link");
  assert.equal(evidenceLine({ edge_id: "E-1", rel: "has_supplier", source_kind: "bank", source_label: "Supplier link (borrower_360.rel_edge_quarter, 2026Q2)",
                              date: "2026-06-30", synthetic: false }), "Supplier link (borrower_360.rel_edge_quarter, 2026Q2) · 30 Jun 2026");
});

const sig = (severity: Signal["severity"], title: string): Signal => ({
  signal_id: title, rule: "counterparty_distress", severity, title, sentence: title,
  focal: { node_id: "C-1", name: "X", proposal_id: "R16-C2" },
  counterparty: { node_id: "C-2", name: "Y", kind: "company", role: "supplier", roles: ["supplier"], role_label: "supplier", via: "" },
  standing: [], other_deals: [], evidence: [], synthetic: false, href: "",
});

test("the deal's line leads with the first signal in difficulty", () => {
  assert.equal(signalLine([]), "");
  assert.equal(signalLine([sig("high", "Al Kharj United Contracting, a supplier, is in a declined deal"), sig("medium", "B")]),
               "2 counterparty signals, 1 high: Al Kharj United Contracting, a supplier, is in a declined deal.");
  assert.equal(signalLine([sig("low", "Z is also a borrower")]), "1 counterparty signal: Z is also a borrower.");
});

test("tabs: overview, counterparty exposure, then the sections in order", () => {
  const t = tabs([{ key: "deals", title: "Deals", facts: [], tables: [], plain_words: [], empty: "", n: 3 },
                  { key: "learned", title: "What the uploads taught", facts: [], tables: [], plain_words: [], empty: "", n: 76 }],
                 { high: 1, medium: 2, low: 0, total: 3 });
  assert.deepEqual(t.map((x) => x.key), ["overview", "counterparty", "deals", "learned"]);
  assert.equal(t[1].count, 3);
  assert.equal(t[3].label, "Learned from uploads");
});

test("the ?b360 switch", () => {
  assert.equal(isOpen("1"), true);
  assert.equal(isOpen(null), false);
  assert.equal(isOpen("0"), false);
});
