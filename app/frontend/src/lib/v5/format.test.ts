import assert from "node:assert/strict";
import { test } from "node:test";

import { auto, bps, cell, count, header, hoverTemplate, kindOf, pct, ratio, RAW_FLOAT, sar, tidyText } from "./format.ts";

test("R6 E2: table cells by key, by header in words, booleans and raw floats as text", () => {
  // screen 09: the DD-01 stress table
  assert.equal(cell(0.2810632681763545, "lifetime_raroc"), "28.1%");
  assert.equal(cell(0.8882297289798154, "sva"), "SAR 0.89m");
  assert.equal(cell(true, "clears_hurdle"), "Yes");
  assert.equal(cell(false, "clears_hurdle"), "No");
  // a stored block with words for headers and no keys
  assert.equal(cell(0.2810632681763545, "", "Lifetime RAROC"), "28.1%");
  assert.equal(cell(0.8882297289798154, "", "SVA"), "SAR 0.89m");
  assert.equal(cell(0.8882297289798154, "", "SVA (SAR m)"), "SAR 0.89m");
  assert.equal(cell(0.281, "", "Return (%)"), "28.1%");
  assert.equal(cell("0.2810632681763545", "", "Lifetime RAROC"), "28.1%");
  // already formatted text passes through; the safety net rounds what the column says nothing about
  assert.equal(cell("SAR 30.0m", "", "Value"), "SAR 30.0m");
  assert.equal(cell("1.61x", "", "DSCR"), "1.61x");
  assert.equal(cell(3.14159265, "", "Something"), "3.14");
  assert.equal(cell(null), "–");
  assert.ok(RAW_FLOAT.test("0.2810632681763545") && !RAW_FLOAT.test("0.2811"));
  assert.equal(auto(true, "clears_hurdle"), "Yes");
  assert.equal(auto("0.12345678", "share"), "12.3%");
  assert.equal(kindOf("clears_hurdle"), "num");
  assert.equal(header("clears_hurdle"), "Clears hurdle");
  assert.equal(hoverTemplate("lifetime_raroc"), "%{x}<br>%{y:.1%}<extra></extra>");
  assert.equal(hoverTemplate("ead_sar_mn", "x", "y"), "%{y}<br>SAR %{x:,.1f}m<extra></extra>");
});

test("amounts in SAR m or bn", () => {
  assert.equal(sar(1234.5), "SAR 1.23bn");
  assert.equal(sar(12.34), "SAR 12.3m");
  assert.equal(sar(5.678), "SAR 5.68m");
  assert.equal(sar(950, "bn"), "SAR 0.95bn");
  assert.equal(sar(null), "–");
});

test("percentages, ratios, bps, counts", () => {
  assert.equal(pct(0.1218), "12.2%");
  assert.equal(pct(0.0512), "5.12%");
  assert.equal(pct(12.18, { scale: "points" }), "12.2%");
  assert.equal(pct(0.031, { signed: true }), "+3.10%");
  assert.equal(ratio(1.23456), "1.23");
  assert.equal(bps(43.6), "44 bps");
  assert.equal(count(12345), "12,345");
  assert.equal(bps(-0.3), "0 bps");
  assert.equal(auto(2.531, "lgd_change_pp"), "2.53pp");
});

test("auto by key: no raw fraction shares, no long decimals", () => {
  assert.equal(auto(0.1218, "headroom_share"), "12.2%");
  assert.equal(auto(14.74, "coverage_pct"), "14.7%");
  assert.equal(auto(18695.2, "ead_sar_mn"), "SAR 18.70bn");
  assert.equal(auto(1.234567, "dscr"), "1.23");
  assert.equal(auto(236, "borrowers"), "236");
  assert.equal(auto(0.1534, "raroc"), "15.3%");
  assert.equal(auto(25, "margin_bps"), "25 bps");
  assert.equal(auto("Construction", "sector"), "Construction");
  assert.equal(kindOf("Limit"), "sar");
});

test("headers in plain words with units", () => {
  assert.equal(header("headroom_share"), "Headroom share (%)");
  assert.equal(header("headroom_sar_mn"), "Headroom (SAR m)");
  assert.equal(header("ead_sar_mn"), "EAD (SAR m)");
  assert.equal(header("raroc"), "RAROC (%)");
  assert.equal(header("limit_type"), "Limit type");
  assert.equal(header("Share of book"), "Share of book");
});

test("tidyText rounds long decimals in prose and leaves versions alone", () => {
  assert.equal(tidyText("RAROC 0.153412 vs hurdle 0.15"), "RAROC 0.15 vs hurdle 0.15");
  assert.equal(tidyText("rule set gw-ews-1.3.0 and 12.5%"), "rule set gw-ews-1.3.0 and 12.5%");
  assert.equal(tidyText("SAR 1,234.5678m"), "SAR 1,234.57m");
});
