import { test } from "node:test";
import assert from "node:assert/strict";

import { checkPlainWords, checkUrls, filterBatch, pageCards, proposalUrls, richRuns, sectionLabel, voiceOf } from "./model.ts";
import { checkPlainWords as ruleCheck } from "../../ui/plain-words-model.ts";

test("urls encode the deal and carry the selected structure", () => {
  assert.equal(proposalUrls("R12 TWA").prepare, "/api/v1/dealdesk/proposals/R12%20TWA/credit-proposal");
  assert.equal(proposalUrls("R12-TWA", "counter:CP-D1").docx, "/api/v1/dealdesk/proposals/R12-TWA/bank-form.docx?structure=counter%3ACP-D1");
  assert.equal(checkUrls("R14-RWQ").demo("half"), "/api/v1/dealdesk/proposals/R14-RWQ/proposal-check?demo=half");
});

test("key concerns are bold and underlined; bold stays bold", () => {
  const r = richRuns("Plain **bold** and __concern__.");
  assert.deepEqual(r.map((x) => [x.text, x.bold, x.underline]), [["Plain ", false, false], ["bold", true, false], [" and ", false, false], ["concern", true, true], [".", false, false]]);
});

test("page cards follow the page map, parts open their first section, continuation pages fold in", () => {
  const s = (key: string, n: number | null) => ({ key, n, heading: key, voice: "credit" as const, part: n ? "anatomy" : "creditprobe", blocks: [], gaps: [] });
  const p = {
    sections: [s("header", 1), s("action", 2), s("facilities", 3), s("security", 4), s("cp_raroc", null), s("signatures", 20)],
    pages: { sections: { header: 1, action: 1, facilities: 2, security: 3, cp_raroc: 5, signatures: 9 }, total: 9 },
    parts: [{ key: "action", title: "ACTION REQUESTED", subtitle: "Business", sections: ["action", "facilities", "security"] },
            { key: "creditprobe", title: "CREDITPROBE ANALYSIS", subtitle: "", sections: ["cp_raroc"] },
            { key: "approvals", title: "APPROVALS", subtitle: "", sections: ["signatures"] }],
  };
  const c = pageCards(p);
  assert.deepEqual(c.map((x) => [x.page, x.to, x.sections.map((y) => y.key)]), [[1, 1, ["header", "action"]], [2, 2, ["facilities"]], [3, 4, ["security"]], [5, 8, ["cp_raroc"]], [9, 9, ["signatures"]]]);
  assert.equal(c[0].part?.title, "ACTION REQUESTED");
  assert.equal(c[1].landscape, true);
  assert.equal(sectionLabel(p.sections, "cp_raroc"), "CP1.");
  assert.equal(voiceOf({ voice: "credit", part: "creditprobe" }), "CreditProbe");
});

test("the check's plain words pass the K34 rules and state the numbers", () => {
  const lines = checkPlainWords({ customer: "Ruwaq Gulf Contracting Company", score: 75.5, grade: "C", critical: 4, sections_present: 19, rm: "Tariq Al-Mansouri",
    queries: new Array(15).fill(0).map((_, i) => ({ n: i + 1, section: 8, heading: "", severity: "major", title: "", query: "", check: "", defect_type: "" })),
    defects: [{ title: "RM claim contradicted: x", category: "accuracy" }, { title: "Not disclosed: y", category: "disclosure" }] as never });
  assert.equal(lines.length, 4);
  assert.match(lines[0], /76 of 100/);
  assert.ok(ruleCheck(lines).ok, JSON.stringify(ruleCheck(lines)));
});

test("batch filters", () => {
  const r = (pid: string, rm: string, score: number, critical: number) => ({ proposal_id: pid, rm, branch: "B", sector: "S", score, critical } as never);
  const rows = [r("A", "x", 30, 2), r("B", "y", 90, 0), r("C", "x", 60, 0)];
  assert.deepEqual(filterBatch(rows, { rm: "x" }).map((x: { proposal_id: string }) => x.proposal_id), ["A", "C"]);
  assert.deepEqual(filterBatch(rows, { maxScore: 70, criticalOnly: true }).map((x: { proposal_id: string }) => x.proposal_id), ["A"]);
});

test("R15 L12: the proposal wait names what is written and stops with a reason, never endless", async () => {
  const m = await import("./model.ts");
  assert.ok(m.PROPOSAL_TIMEOUT_MS > 0 && m.PROPOSAL_TIMEOUT_MS <= 180_000);
  assert.match(m.writingLine(0), /deal file/);
  assert.match(m.writingLine(10), /20 bank-form sections/);
  assert.match(m.writingLine(60), /Still writing/);
  const t = m.proposalTimeoutText(150_000);
  assert.match(t, /150 seconds/);
  assert.match(t, /try again/);
  assert.doesNotMatch(t, /Error|detail|500|Traceback/);
});
