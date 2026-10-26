import { test } from "node:test";
import assert from "node:assert/strict";

import { countsLine, finQualityUrl, gradeTone, ordered, sevTone, sourceLine, statusLabel, type Signal } from "./model.ts";

const sig = (code: string, family: string, flag: boolean | null, severity: Signal["severity"]): Signal => ({
  code, family, family_label: family, label: code, value: 1, display: "1", unit: "share", threshold: 0.2, op: ">", threshold_display: "> 20%",
  flag, severity, period: "FY2025", source: { relation: "dd_financials_detail" }, sources: [], text: "", basis: "", policy_ref: "", note: "",
});

test("urls for a deal and a Book row, encoded", () => {
  assert.equal(finQualityUrl({ proposalId: "R12-TWA" }), "/api/v1/dealdesk/fin-quality/R12-TWA");
  assert.equal(finQualityUrl({ facilityId: "R12-TWA:L0" }), "/api/v1/dealdesk/fin-quality/book/R12-TWA%3AL0");
  assert.equal(finQualityUrl({}), null);
});

test("tones follow the grade and the severity", () => {
  assert.equal(gradeTone("D"), "negative");
  assert.equal(gradeTone("C"), "warning");
  assert.equal(gradeTone("A"), "positive");
  assert.equal(sevTone("critical"), "negative");
  assert.equal(sevTone("medium"), "warning");
  assert.equal(sevTone("not_assessable"), "neutral");
});

test("flagged first by severity, then within, then not assessable", () => {
  const fam = ["related_party", "audit"];
  const out = ordered([sig("AU-01", "audit", false, "none"), sig("RP-02", "related_party", true, "high"), sig("AU-02", "audit", true, "critical"),
                       sig("RC-03", "receivables", null, "not_assessable")], fam);
  assert.deepEqual(out.map((s) => s.code), ["AU-02", "RP-02", "AU-01", "RC-03"]);
  assert.equal(statusLabel(out[0]), "critical");
  assert.equal(statusLabel(out[2]), "within");
  assert.equal(statusLabel(out[3]), "no data");
});

test("counts and source lines", () => {
  assert.equal(countsLine({ flagged: 10, signals: 24, assessable: 22, limited: false }), "10 of 24 flagged · 22 assessable");
  assert.equal(countsLine({ flagged: 0, signals: 24, assessable: 3, limited: true }), "0 of 24 flagged · 3 assessable · limited data");
  assert.equal(sourceLine({ source: { relation: "dd_project" }, period: "FY2025" }), "dd_project · FY2025");
  assert.equal(sourceLine({ source: null, period: null }), "Data Domains");
});
