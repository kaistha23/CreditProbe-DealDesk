import { test } from "node:test";
import assert from "node:assert/strict";

import { dealScore, findNamedDeal, idKey, ratio, searchDeals } from "./deal-search.ts";

const rows = [
  { proposal_id: "DD-03", obligor_name: "Al Khobar Modern Cold Storage Company" },
  { proposal_id: "DD-06", obligor_name: "Dhahran Continental Industries" },
  { proposal_id: "PL-03", obligor_name: "Red Sea Marine Works Company" },
  { proposal_id: "PL-11", obligor_name: "Yanbu Glass Industries Company" },
  { proposal_id: "PL-15", obligor_name: "Riyadh Cloud Data Centres Company" },
  { proposal_id: "R12-ESC", obligor_name: "Marina Vista Developments" },
  { proposal_id: "R12-SYN", obligor_name: "Najd Petrochemical Company" },
  { proposal_id: "R12-TWA", obligor_name: "Al Sahel Building Materials Trading LLC", deal_name: "Al Sahel — working capital renewal" },
  { proposal_id: "R12-TWB", obligor_name: "Gulf Meridian Contracting", deal_name: "Gulf Meridian Contracting — new project limit and renewal" },
];

test("ratio equals Python's difflib on short words", () => {
  assert.equal(Math.round(ratio("sahal", "sahel") * 1000) / 1000, 0.8);
  assert.equal(ratio("abc", "abc"), 1);
  assert.equal(ratio("abc", "xyz"), 0);
});

test("same scores as the backend (backend/dealdesk/deal_list.py)", () => {
  assert.equal(dealScore("al sahal", "Al Sahel Building Materials Trading LLC", "R12-TWA"), 0.765);
  assert.equal(dealScore("gulf meridan", "Gulf Meridian Contracting", "R12-TWB"), 0.8217);
  assert.equal(dealScore("twa", "x", "R12-TWA"), 0.9);
  assert.equal(dealScore("dd 6", "x", "DD-06"), 1);
  assert.equal(idKey("DD-06"), "dd6");
});

test("K17 search: fuzzy on name and id", () => {
  const top = (q: string) => searchDeals(rows, q)[0]?.proposal_id ?? null;
  assert.equal(top("al sahal"), "R12-TWA");
  assert.equal(top("gulf meridan"), "R12-TWB");
  assert.equal(top("twa"), "R12-TWA");
  assert.equal(top("dd06"), "DD-06");
  assert.equal(top("zzzz"), null);
  assert.equal(top("al company"), null);
  assert.equal(searchDeals(rows, "").length, rows.length);
});

test("K17 Ask: a deal named in a question opens the deal; other questions do not", () => {
  const f = (q: string) => findNamedDeal(q, rows)?.proposal_id ?? null;
  assert.equal(f("Why does Al Sahal fail?"), "R12-TWA");
  assert.equal(f("what about gulf meridian contracting"), "R12-TWB");
  assert.equal(f("tell me about DD-03"), "DD-03");
  assert.equal(f("Is Najd Petrochemical approvable?"), "R12-SYN");
  assert.equal(f("renewal for Yanbu glass"), "PL-11");
  for (const q of ["How much real-estate headroom is left this quarter?", "Which proposals breach a hard limit?",
                   "How much sector headroom is left?", "What is the ECL in Riyadh?"]) assert.equal(f(q), null, q);
});
