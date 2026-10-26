/** R15 session b: Deal Desk fixes (L7, L8, L10, L11, L12, L13): pure helpers and wiring. */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import { approvalView, rarocTileSub } from "../v5/dealdesk-engines.ts";

const src = (p: string) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");

test("L13: the RAROC tile says price only, against the hurdle", () => {
  assert.equal(rarocTileSub(true, 0.16), "Clears the 16.0% hurdle · price only");
  assert.equal(rarocTileSub(false, 0.16), "Below the 16.0% hurdle · price only");
});

test("L13: the first return view is the one the approval test uses", () => {
  const rv = { basis: "deal" as const, rule: "", views: [
    { key: "deal" as const, label: "Deal only (used for approval)", line: "", raroc: 0.196, formula: null, clears: true, used_for_approval: true },
    { key: "relationship" as const, label: "Whole relationship (for pricing talks)", line: "", raroc: 0.235, formula: null, clears: true, used_for_approval: false },
  ] };
  assert.equal(approvalView(rv)?.key, "deal");
  assert.equal(approvalView({ ...rv, views: rv.views.map((v) => ({ ...v, used_for_approval: v.key === "relationship" })) })?.key, "relationship");
  assert.equal(approvalView(null), null);
});

test("L13: the deal page and the Review banner read the one story sentence; the PD chip is in words", () => {
  const steps = src("components/v5/dealdesk/steps.tsx");
  assert.ok(steps.includes("<DealStoryLine e={e} />"));
  assert.ok(steps.includes("ReturnViewSwitch"));
  assert.ok(!steps.includes(">PD model: outside training range<"));
  assert.ok(src("components/v5/dealdesk/review-workspace.tsx").includes("verdict.story"));
  const story = src("components/v5/dealdesk/deal-story.tsx");
  assert.ok(story.includes("used for approval") && story.includes("for pricing talks only"));
});

test("L8: account behaviour labels deposits as a pricing view and capacity has one answer", () => {
  const ab = src("components/v5/dealdesk/account-behaviour.tsx");
  assert.ok(ab.includes("Relationship + deposits (pricing talks)"));
  assert.ok(ab.includes("Cross-check: leverage limit alone"));
  assert.ok(!ab.includes('"Capacity: EBITDA · cash flow"'));
  assert.ok(ab.includes("deposit_formula"));
});

test("L12: Review's Draft proposal is the bank-form writer", () => {
  const rw = src("components/v5/dealdesk/review-workspace.tsx");
  assert.ok(rw.includes('<PrepareProposalButton proposalId={proposalId} label="Draft proposal"'));
  assert.ok(!rw.includes("<DraftProposalButton"));
});

test("L7: no RM proposal on file is a plain state with three actions, never a spinner or a raw message", async () => {
  const { noProposalState, checkUrls } = await import("../../components/v5/dealdesk/proposal/model.ts");
  const r = noProposalState(true);
  assert.equal(r.title, "No RM proposal on file for this renewal yet");
  assert.deepEqual(r.actions.map((a) => a.key), ["upload", "record", "draft"]);
  assert.equal(r.actions[2].label, "Draft the renewal proposal from data");
  assert.equal(noProposalState(false).title, "No RM proposal on file for this deal yet");
  assert.equal(checkUrls("DD-104").record, "/api/v1/dealdesk/proposals/DD-104/proposal-check?use=record");
  const pc = src("components/v5/dealdesk/proposal/proposal-check.tsx");
  assert.ok(pc.includes('data-testid="dealdesk-proposal-check-none"') && pc.includes("e.status === 404"));
});

test("L11: the brief goes to Mail as escaped paragraphs and finds the RM's Mail user", async () => {
  const { briefHtml, matchUser } = await import("../../components/v5/dealdesk/proposal/model.ts");
  assert.equal(briefHtml("Line <1>\nline 2\n\nNext"), "<p>Line &lt;1&gt;<br>line 2</p><p>Next</p>");
  const users = [{ name: "Khalid Al-Otaibi", username: "khalid.alotaibi" }, { name: "Sara Al-Qahtani", username: "sara.alqahtani" }];
  assert.equal(matchUser("Khalid Al-Otaibi", users)?.username, "khalid.alotaibi");
  assert.equal(matchUser("K. Al-Otaibi", users)?.username, "khalid.alotaibi");
  assert.equal(matchUser("Omar Unknown", users), null);
  assert.equal(matchUser("", users), null);
  const pc = src("components/v5/dealdesk/proposal/proposal-check.tsx");
  assert.ok(pc.includes("<RmBrief ") && pc.includes("<ProposalDocButton ") && pc.includes("<SectionScores "));
  assert.ok(src("components/v5/dealdesk/review-workspace.tsx").includes("ProposalDocFromCheck"));
  assert.ok(src("components/v5/dealdesk/documents-panel.tsx").includes("ProposalDocFromCheck"));
});
