import { test } from "node:test";
import assert from "node:assert/strict";

import { type CustomerFile, type Facts, batchFiles, groupChecklist, plainWords, prefillFromFacts, reconTone, statusTone } from "./dealdesk-intake-model.ts";

const view = {
  intake_id: "IN-T", proposal_id: "", as_of: "2026-10-21", created_at: "", documents_n: 12, by_method: { Word: 9, "photo (OCR)": 3 }, by_method_text: "",
  profile: { customer_name: "Qimmat Al Waha Trading Co.", cr_number: "1010777001", city: "Riyadh", activity: "", legal_form: "", sector: "Wholesale Trade", contractor: false },
  bank: { existing: true, how: "CR", sources: [] }, documents: [],
  checklist: [
    { req_group: "kyc", doc_type: "national_id", requirement: "ID", subject: "A", status: "received", doc_ids: "D1", reason: "", valid_until: "", rule_ref: "" },
    { req_group: "kyc", doc_type: "national_id", requirement: "ID", subject: "B", status: "missing", doc_ids: "", reason: "", valid_until: "", rule_ref: "" },
    { req_group: "extras", doc_type: "project_list", requirement: "P", subject: "c", status: "not_applicable", doc_ids: "", reason: "", valid_until: "", rule_ref: "" },
  ],
  counts: { received: 1, missing: 1, expired: 0, not_applicable: 1, required: 2 },
  groups: [{ key: "kyc", label: "KYC" }, { key: "company_legal", label: "Company legal" }, { key: "extras", label: "Other documents" }],
  reconciliation: [{ test: "x", topic: "revenue", title: "Revenue growth vs account credits at the Bank", status: "differs", severity: 3, a: 1, b: 2, c: null,
                     gap_pct: null, unit_note: "", sentence: "", evidence: [] }],
  plain_words: [],
} as unknown as CustomerFile;

test("plain words: at most 4 lines and 60 words, says photos, existing customer and the first flag", () => {
  const pw = plainWords(view);
  assert.ok(pw.length <= 4 && pw.join(" ").split(/\s+/).length <= 60);
  assert.match(pw[0], /3 of them photos/);
  assert.match(pw.join(" "), /Already banks with us/);
  assert.match(pw[3], /Revenue growth vs account credits/);
});

test("checklist groups count only what is needed", () => {
  const g = groupChecklist(view.checklist, view.groups);
  assert.deepEqual(g.map((x) => [x.key, x.received, x.required]), [["kyc", 1, 2], ["extras", 0, 0]]);
});

test("tones", () => {
  assert.equal(statusTone("missing"), "negative");
  assert.equal(statusTone("expired"), "warning");
  assert.equal(reconTone({ status: "agrees", severity: 0 }), "positive");
  assert.equal(reconTone({ status: "flag", severity: 3 }), "negative");
});

test("prefill reads the latest audited year, the ask and the sector", () => {
  const f = {
    intake_id: "IN-T", proposal_id: "", profile: view.profile, bank: { existing: true, how: "", sources: [], group_name: "Naseem Holding Group" },
    financials: { FY2024: { revenue: 100e6 }, FY2025: { revenue: 138e6, operating_profit: 12e6, depreciation: 3e6, short_term_borrowings: 20e6, long_term_borrowings: 10e6 } },
    latest: { facility_request_letter: { requested_total: 75e6 } },
  } as unknown as Facts;
  const p = prefillFromFacts(f, ["Wholesale Trade", "Construction"]);
  assert.deepEqual(p, { name: "Qimmat Al Waha Trading Co.", cr_number: "1010777001", sector: "Wholesale Trade", revenue: "138.0", ebitda: "15.0",
                        total_debt: "30.0", amount: "75.0", group_name: "Naseem Holding Group" });
});

test("batches keep the pages of one photographed document together", () => {
  const names = ["a.docx", "b.pdf", "13_fs_p1.jpg", "c.docx", "d.docx", "13_fs_p2.jpg", "e.pdf", "f.pdf", "g.pdf"].map((name) => ({ name }));
  const b = batchFiles(names, 4).map((x) => x.map((f) => f.name));
  assert.deepEqual(b, [["a.docx", "b.pdf", "13_fs_p1.jpg", "13_fs_p2.jpg"], ["c.docx", "d.docx", "e.pdf", "f.pdf"], ["g.pdf"]]);
  assert.equal(b.flat().length, names.length);
});
