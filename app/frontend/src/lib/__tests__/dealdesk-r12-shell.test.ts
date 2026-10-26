/** PLAN_R12 Session U: the Deal Desk shell (landing cards and tabs, step order, action bar, pipeline deals, workflow). */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");
const dir = "components/v5/dealdesk/";

test("R13 X (J9, J10): the R11 landing: header buttons Book and Parameters & policy, the centred chat box, one line of counters", () => {
  const h = read(dir + "home.tsx");
  assert.ok(!h.includes("NoorModuleBrief"), "no Noor strip");
  const header = h.slice(h.indexOf('data-testid="dealdesk-home"'), h.indexOf('data-testid="dealdesk-tab-book-panel"'));
  for (const id of ["dealdesk-tab-book", "dealdesk-tab-params", "/deal-desk/review"]) assert.ok(header.includes(id), `header: ${id}`);
  assert.ok(!h.includes('data-testid="dealdesk-tabs"'), "no tab strip: Book and Parameters are header buttons");
  assert.equal((h.match(/<ModuleLanding /g) ?? []).length, 1, "one chat box (the shared ModuleLanding)");
  const iChat = h.indexOf('<ModuleLanding ids="dealdesk"'), iCounters = h.indexOf("<LandingCards"), iPipe = h.indexOf('testId="dealdesk-pipeline"');
  assert.ok(iChat > -1 && iChat < iCounters && iCounters < iPipe, "chat, counters, pipeline (R11 order)");
  assert.ok(h.includes('<Slot name="BookTab"') && h.includes('<Slot name="ParametersTab"'), "Book (I) and Parameters (G) are mounted slots");
  assert.ok(h.includes('data-testid="dealdesk-mode"') && h.includes('mode === "pipeline" ? <PipelineMode'), "Single deal | Pipeline unchanged");
  assert.ok(h.includes('mode === "single" ? <ConditionsDueLine /> : null'));
  const cards = read(dir + "landing-cards.tsx");
  assert.ok(cards.includes("r12Api.cards()") && cards.includes('data-testid="dealdesk-cards-row"') && cards.includes("function Counter("));
  assert.ok(!cards.includes("function CardTile"), "no big cards");
  const ml = read("components/v5/landing/module-landing.tsx");
  assert.ok(ml.includes("export function ModuleLanding") && ml.includes("export function AskBar") && ml.includes("mx-auto w-full max-w-3xl"));
});

test("I15/I1/O2: the deal page steps, opening on Proposal, ticks from done", () => {
  const k = read(dir + "kit.tsx");
  assert.ok(k.includes("export function Stepper({ step, done, onStep }"));
  assert.ok(!k.includes('state === "locked"'), "no step is locked");
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes("const done = doneSet(visited, { hasOpt: Boolean(opt), hasRec: Boolean(rec) });"));
  assert.ok(t.includes("<Stepper step={step} done={done} onStep={go} />"));
  // PLAN_R14 (K31, R14 F): Upload leads to the Proposal check, which leads to Review
  assert.ok(t.includes('onNext={() => go("proposal-check")}') && t.includes('go("review")'), "Upload leads to Proposal check, then Review");
});

test("R13 X (J10): the R11 deal page; R12's add-ons behind one More menu; Optimise back on the composer bar", () => {
  const t = read(dir + "thread.tsx");
  assert.equal((t.match(/<MoreMenu /g) ?? []).length, 1, "one More menu");
  assert.ok(!t.includes("<ActionBar"), "no action bar row");
  assert.ok(!t.includes("<PrepareForCommitteeButton"), "Committee paper is in More");
  assert.ok(!t.includes('<Slot name="Group"') && !t.includes('<Slot name="Swot"'), "Group & SWOT are in More, not on the steps");
  const bar = read(dir + "action-bar.tsx");
  const more = bar.slice(bar.indexOf("export function MoreMenu"), bar.indexOf("export function DealBarActions"));
  // R14 U (K28): "Documents" with its count as an explained badge ("8 missing documents"), not "Documents (8)".
  assert.ok(more.includes('noun: "missing document"'), "the count is explained");
  assert.ok(more.includes('title: "Deal file"') && more.includes('title: "Intelligence"'), "two sections");
  const labels = ['label: "Documents"', '"Group & SWOT"', '"Write proposal"', '"Committee paper"', '"Try it on your documents"'];
  for (const l of labels) assert.ok(more.includes(l), l);
  const at = labels.map((l) => more.indexOf(l));
  assert.deepEqual(at, [...at].sort((x, y) => x - y), "the menu's order");
  assert.ok(bar.slice(bar.indexOf("export function DealBarActions")).includes('"dealdesk-optimise"'));
  const steps = read(dir + "steps.tsx");
  const proposal = steps.slice(steps.indexOf("export function ProposalStep"), steps.indexOf("export function AnalysisStep"));
  assert.ok(!proposal.includes("<DraftProposalButton"));
});

test("I21: every pipeline row opens the full deal, with the banner and Back to pipeline", () => {
  const pv = read(dir + "pipeline-view.tsx");
  assert.ok(!pv.includes('d.source === "Pipeline set"}'), "DecisionTable links enabled for the pipeline set");
  assert.ok(pv.includes("dealdesk-pipeline-deal-open-"));
  assert.ok(read(dir + "home.tsx").includes("?from=pipeline"));
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes('data-testid="dealdesk-pipeline-banner"') && t.includes('data-testid="dealdesk-back-to-pipeline"'));
});

test("I17: the workflow strip and the role view come from the engine", () => {
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes("r12Api.workflow(proposalId, false)") && t.includes("r12Api.move(proposalId, to)"));
  assert.ok(t.includes('data-testid="dealdesk-workflow"') && t.includes('data-testid="dealdesk-handover-log"'));
  assert.ok(!t.includes('data-testid="dealdesk-status"'), "the R11 status select gave way to the workflow");
});

test("Slots: an absent component leaves its slot empty; a failing one too", () => {
  const s = read(dir + "r12-slots.tsx");
  assert.ok(s.includes("if (!C) return null;") && s.includes("getDerivedStateFromError") && s.includes("this.state.failed ? null"));
});
