import assert from "node:assert/strict";
import { test } from "node:test";

import { type PackDocument, type PackSummary, checklist, dmy, fileHref, mn, packLine } from "./dealdesk-packs.ts";

const doc = (status: PackDocument["status"], label: string): PackDocument => ({
  doc_id: label, doc_type: "x", label, subject: null, title: label, issuer: null, issue_date: null, expiry_date: null, status,
  status_label: status, files: null,
});

test("checklist puts missing, then expired, then received, keeping the pack order", () => {
  const out = checklist([doc("received", "a"), doc("missing", "b"), doc("expired", "c"), doc("received", "d"), doc("missing", "e")]);
  assert.deepEqual(out.map((d) => d.label), ["b", "e", "c", "a", "d"]);
});

test("pack line reads like the checklist", () => {
  const p = { case: "New-to-bank SME, thin file", counts: { documents: 17, images: 15, expired: 2, missing: 10 } } as PackSummary;
  assert.equal(packLine(p), "New-to-bank SME, thin file · 17 documents, 15 photos · 2 expired, 10 missing");
  assert.equal(packLine({ ...p, counts: { documents: 37, images: 25, expired: 0, missing: 0 } }), "New-to-bank SME, thin file · 37 documents, 25 photos");
});

test("money, dates and links", () => {
  assert.equal(mn(12.45), "SAR 12.5m");
  assert.equal(mn(null), "–");
  assert.equal(dmy("2026-04-30"), "30/04/2026");
  assert.equal(dmy(null), "–");
  assert.ok(fileHref("c2", "pdf/01 a.pdf").endsWith("/api/v1/dealdesk/customer-packs/c2/file?path=pdf%2F01%20a.pdf"));
});
