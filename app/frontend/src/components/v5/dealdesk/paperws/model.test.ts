import { test } from "node:test";
import assert from "node:assert/strict";

import { busyLine, evidenceText, lineDiff, openBody, ordered, pendingBySection, pointIndex, pwHref, pwUrls, sectionNo, suggestions, versionLine } from "./model.ts";
import type { Provenance, PwPaper, PwPending } from "./model.ts";
import { afterInstructionComponent, emitInstructionApplied, registerAfterInstruction, registerInstructionApplied } from "./hooks.ts";

const PAPER: PwPaper = {
  doc_kind: "proposal", proposal_id: "DD-06", customer: "Dhahran", parts: [
    { key: "action", title: "ACTION REQUESTED", subtitle: "Business", sections: ["action", "facilities"] },
    { key: "creditprobe", title: "CREDITPROBE ANALYSIS", subtitle: "", sections: ["cp_raroc"] },
  ],
  sections: [
    { key: "header", n: 1, heading: "Header block", voice: "form", part: "anatomy", blocks: [], gaps: [] },
    { key: "action", n: 2, heading: "Action requested", voice: "business", part: "anatomy", blocks: [], gaps: [] },
    { key: "facilities", n: 3, heading: "Facilities", voice: "business", part: "anatomy", blocks: [], gaps: [] },
    { key: "cp_raroc", n: null, heading: "RAROC and SVA (CreditProbe)", voice: "credit", part: "creditprobe", blocks: [], gaps: [] },
    { key: "orphan", n: 20, heading: "Signatures", voice: "form", part: "anatomy", blocks: [], gaps: [] },
  ],
};

test("urls and the page a workspace opens on", () => {
  assert.equal(pwUrls.one("PW-1"), "/api/v1/dealdesk/paper-workspaces/PW-1");
  assert.equal(pwUrls.one("PW-1", 3), "/api/v1/dealdesk/paper-workspaces/PW-1?version=3");
  assert.equal(pwUrls.docx("PW-1", "final"), "/api/v1/dealdesk/paper-workspaces/PW-1/export.docx?version=final");
  assert.equal(pwUrls.list({ proposal_id: "DD-06", mine: true }), "/api/v1/dealdesk/paper-workspaces?proposal_id=DD-06&mine=true");
  assert.equal(pwHref("PW-1", "provenance"), "/deal-desk/paper/PW-1?view=provenance");
  assert.deepEqual(openBody("proposal", { proposalId: "DD-06", structure: "recommended" }), { kind: "proposal", proposal_id: "DD-06", structure: "recommended" });
  assert.deepEqual(openBody("request", { requestId: "BR-1" }), { kind: "request", ref: "BR-1" });
});

test("sections in print order with their part banners; numbers as in the Word", () => {
  const o = ordered(PAPER);
  assert.deepEqual(o.map((x) => x.section.key), ["header", "action", "facilities", "cp_raroc", "orphan"]);
  assert.equal(o[1].part?.title, "ACTION REQUESTED");
  assert.equal(o[2].part, null);
  assert.equal(sectionNo(PAPER.sections, "cp_raroc"), "CP1.");
  assert.equal(sectionNo(PAPER.sections, "facilities"), "3.");
  assert.equal(sectionNo(PAPER.sections, "facilities", "request"), "3.");
});

test("the mark: before / after lines and the newest pending change per section", () => {
  const d = lineDiff([{ t: "p", text: "A." }, { t: "bullets", items: ["x", "y"] }], [{ t: "p", text: "A." }, { t: "bullets", items: ["x", "z"] }]);
  assert.deepEqual(d, { removed: ["• y"], added: ["• z"] });
  const pend: PwPending[] = [
    { version: 2, action: "edit", instruction: "a", author: "Anne", at: 1, sections: [{ key: "action", heading: "2. Action", before: [], after: [] }] },
    { version: 4, action: "structure", instruction: "b", author: "Anne", at: 2, sections: [{ key: "action", heading: "2. Action", before: [], after: [] }, { key: "cp_raroc", heading: "CP1", before: [], after: [] }] },
  ];
  const m = pendingBySection(pend);
  assert.equal(m.get("action")?.version, 4);
  assert.equal(m.size, 2);
});

test("versions, evidence lines and the point index", () => {
  assert.match(versionLine({ n: 3, action: "structure", instruction: "x", author: "Anne", at: 1_790_000_000 }, 3), /^v3 \(final\) · Structure step · Anne · /);
  assert.equal(evidenceText({ kind: "document", label: "Audited FS FY2025", doc_id: "C1-13", page: 4 }), "Audited FS FY2025 [C1-13], page 4");
  assert.equal(evidenceText({ kind: "data", relation: "dd_tnc", row: "limit_id=W1", column: "margin_pct", value: 2.5 }), "dd_tnc · limit_id=W1 · margin_pct = 2.5");
  assert.equal(evidenceText({ kind: "analyst", version: 2, author: "Anne", instruction: "Shorten" }), "v2 · Anne · “Shorten”");
  assert.equal(evidenceText({ kind: "rule", text: "Lead with DSCR", author: "anne", at: "2026-10-24T09:00", scope: "me" }), "Lead with DSCR (anne, 2026-10-24, me)");
  const pv = { sections: [{ key: "a", points: [{ id: "a:0", block: 0, item: null, kind: "p", text: "t", evidence: [], traced: false, has_figure: false }] }] } as unknown as Provenance;
  assert.equal(pointIndex(pv).get("a:0")?.text, "t");
  assert.equal(pointIndex(null).size, 0);
});

test("suggestions and the busy line say what will happen", () => {
  assert.ok(suggestions("proposal", "synopsis", "Financial synopsis").includes("Shorten the financial synopsis"));
  assert.ok(suggestions("proposal", null, null).includes("Set the amount to SAR 20m"));
  assert.ok(suggestions("request", null, null).some((x) => x.includes("overdraft")));
  assert.match(busyLine("Set the amount to SAR 20m", "proposal"), /structure step/);
  assert.match(busyLine("Increase the overdraft to SAR 35m", "request"), /structure step/);
  assert.match(busyLine("Shorten the synopsis", "proposal"), /editing/);
});

test("onInstructionApplied: listeners are called and one that throws is ignored", () => {
  const got: string[] = [];
  const off1 = registerInstructionApplied(() => { throw new Error("x"); });
  const off2 = registerInstructionApplied((s, ins, ctx) => got.push(`${s.key}|${ins}|${ctx.version}`));
  emitInstructionApplied({ key: "synopsis", heading: "Financial synopsis" }, "Shorten", { wsId: "PW-1", kind: "proposal", proposalId: "DD-06", version: 2, structure: false });
  assert.deepEqual(got, ["synopsis|Shorten|2"]);
  off1(); off2();
  emitInstructionApplied({ key: "x", heading: "x" }, "y", { wsId: "PW-1", kind: "proposal", proposalId: "DD-06", version: 3, structure: false });
  assert.equal(got.length, 1);
  assert.equal(afterInstructionComponent(), null);
  const C = () => null;
  registerAfterInstruction(C);
  assert.equal(afterInstructionComponent(), C);
});
