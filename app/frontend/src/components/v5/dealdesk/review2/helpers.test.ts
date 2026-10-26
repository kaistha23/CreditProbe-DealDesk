import { test } from "node:test";
import assert from "node:assert/strict";

import {
  type DocItem, type Finding, docsBadge, groupBySeverity, groupDocs, lineageText, money, openQueries, pct, queryForDoc, ratioValue, severityLine,
  sortFindings, times, underlineParts,
} from "./helpers.ts";

const f = (code: string, severity: Finding["severity"], point: number): Finding => ({
  finding_id: `X:${code}:1`, deal_id: "X", point, point_name: "", code, author: "B", severity, title: code, finding: "", evidence: [], measured: null,
  threshold: null, policy_ref: "", crm_article: "", doa_level: null, rule_ids: [], line_ids: [], status: "open",
});

test("findings group by severity, critical first, then by point", () => {
  const g = groupBySeverity([f("B", "major", 4), f("A", "critical", 6), f("C", "major", 2), f("N", "info", 11)]);
  assert.deepEqual(g.map((x) => x.severity), ["critical", "major", "info"]);
  assert.deepEqual(g[1].items.map((x) => x.code), ["C", "B"]);
  assert.deepEqual(sortFindings([f("Z", "minor", 1), f("Y", "critical", 9)]).map((x) => x.code), ["Y", "Z"]);
});

test("severity line drops zeros and notes", () => {
  assert.equal(severityLine({ critical: 7, major: 10, minor: 2, info: 3 }), "7 critical · 10 major · 2 minor");
  assert.equal(severityLine({ critical: 0, major: 0, minor: 0, info: 1 }), "No findings");
});

test("numbers", () => {
  assert.equal(money(117.65, "AED"), "AED 117.7m");
  assert.equal(money(-10, "SAR"), "−SAR 10.0m");
  assert.equal(money(null, "SAR"), "—");
  assert.equal(pct(0.505), "51%");
  assert.equal(times(2.727), "2.73x");
  assert.equal(ratioValue(1.5, "x", "AED"), "1.50x");
  assert.equal(ratioValue(50.48, "AED", "AED"), "AED 50.5m");
});

const doc = (rule_id: string, group: string, status: DocItem["status"]): DocItem => ({
  item_id: `${rule_id}:x`, rule_id, name: "Legal opinion on security", group, for: "Gulf Meridian Contracting LLC", for_kind: "deal", status,
  date: null, expires: null, clause: "Credit Policy 7.4.1", policy: "Credit Policy 2026.1", mandatory: true, severity: "major", note: null,
  updated_by: null, updated_at: null, status_source: "rule",
});

test("documents group and badge", () => {
  const g = groupDocs([doc("A", "Constitution", "received"), doc("B", "Legal", "expired"), doc("C", "Constitution", "pending")]);
  assert.deepEqual(g.map((x) => [x.group, x.items.length]), [["Constitution", 2], ["Legal", 1]]);
  assert.equal(docsBadge({ missing_count: 3 }), "Documents (3)");
  assert.equal(docsBadge({ missing_count: 0 }), "Documents");
  assert.match(queryForDoc(doc("B", "Legal", "expired")), /legal opinion on security for Gulf Meridian Contracting LLC \(the copy on file has expired\); required by Credit Policy 7\.4\.1\./);
});

test("open queries count queued and sent only", () => {
  const q = (status: "queued" | "sent" | "answered" | "closed") => ({ status }) as never;
  assert.equal(openQueries({ items: [q("queued"), q("sent"), q("answered"), q("closed")] }), 2);
  assert.equal(openQueries(null), 0);
});

test("underline the key concerns", () => {
  const parts = underlineParts("We note A. Then B. And A. again", ["A.", "B."]);
  assert.deepEqual(parts.filter((p) => p.underline).map((p) => p.text), ["A.", "B.", "A."]);
  assert.equal(parts.map((p) => p.text).join(""), "We note A. Then B. And A. again");
  assert.deepEqual(underlineParts("plain", []), [{ text: "plain", underline: false }]);
});

test("lineage in words", () => {
  assert.equal(lineageText({ relation: "dd_obligor_financials", key: { proposal_id: "PRP-B-ASB" }, period: "2026-10-13" }),
               "dd_obligor_financials · proposal_id PRP-B-ASB · 2026-10-13");
  assert.match(lineageText({ relation: "bureau_cbrbr", key: {}, period: null, via: "r11-evidence" }), /until the relation is populated/);
});
